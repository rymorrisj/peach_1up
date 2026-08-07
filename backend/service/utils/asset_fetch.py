"""Shared server-side image download: SSRF-safe, streamed, size-capped.

Generalized out of backend/service/games/enrich.py's original
_download_cover_art (the Keep flow's per-leaf cover art fetch), which now
calls download_remote_image() below instead of carrying its own copy. The
Accept All flow (backend/service/games/media_link.py) uses it too, for the
same reason: both are "fetch one image from a provider-supplied https URL
into a library directory" with identical trust boundaries, only the
destination filename differs.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path

import httpx
from fastapi import HTTPException

_TIMEOUT = 15.0
DEFAULT_MAX_BYTES = 20 * 1024 * 1024  # 20 MB

_MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _is_forbidden_redirect_host(host: str) -> bool:
    """Return True if the host is a private/internal address that should not be reached."""
    if host.lower() == "localhost":
        return True
    # httpx.URL.host strips brackets from IPv6 literals, so ip_address() can parse directly
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
    except ValueError:
        return False


def download_remote_image(
    url: str,
    dest_dir: Path,
    *,
    filename_stem: str = "cover",
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> Path:
    """Stream *url* into *dest_dir* as ``{filename_stem}{ext}``, enforcing:

    - https-only source URL
    - dest_dir must resolve under LIBRARY_PATH (every legitimate destination,
      SOFTWARE_PATH's per-item cover art and MEDIA_PATH's Media library, is a
      subtree of it)
    - the redirect target (after following redirects) must also be https and
      not a private/loopback/link-local/reserved address
    - response content-type must be image/*
    - response body capped at max_bytes, aborted mid-stream on overflow

    Raises:
        HTTPException: 422 on any of the above violations, 502 if the fetch
            itself fails.
    """
    if not url.startswith("https://"):
        raise HTTPException(status_code=422, detail="Asset url must use https")

    from backend.service.utils import settings as _s
    lib_root = Path(_s.get("LIBRARY_PATH")).resolve()
    dest_dir_resolved = dest_dir.resolve()
    try:
        dest_dir_resolved.relative_to(lib_root)
    except ValueError:
        raise HTTPException(status_code=422, detail="Resolved asset destination is outside LIBRARY_PATH.")

    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
        with client.stream("GET", url) as resp:
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(status_code=502, detail=f"Asset fetch failed: {e}")

            # Re-validate the final URL after redirects, scheme and host may differ from the original
            final_url = resp.url
            if final_url.scheme != "https" or _is_forbidden_redirect_host(final_url.host):
                raise HTTPException(
                    status_code=422,
                    detail="Asset redirect target must be an https non-private host",
                )

            content_type = resp.headers.get("content-type", "").split(";")[0].strip()
            if not content_type.startswith("image/"):
                raise HTTPException(
                    status_code=422,
                    detail=f"Asset url returned non-image content-type: {content_type}",
                )

            # Stream body incrementally, abort before full download if limit is exceeded
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Asset image exceeds the {max_bytes // 1024 ** 2} MB size limit",
                    )
                chunks.append(chunk)
            data = b"".join(chunks)

    ext = _MIME_TO_EXT.get(content_type, ".jpg")
    dest_dir_resolved.mkdir(parents=True, exist_ok=True)
    dest = dest_dir_resolved / f"{filename_stem}{ext}"
    dest.write_bytes(data)
    return dest
