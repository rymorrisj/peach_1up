"""Shared server-side image download: SSRF-safe, streamed, size-capped.

Generalized out of backend/service/games/enrich.py's original
_download_cover_art (the Keep flow's per-leaf cover art fetch), which now
calls download_remote_image() below instead of carrying its own copy. The
Accept All flow (backend/service/games/media_link.py) uses it too, for the
same reason: both are "fetch one image from a provider-supplied https URL
into a library directory" with identical trust boundaries, only the
destination filename differs.

Both callers receive the URL from the client, so it is untrusted input.
Every request, including every redirect hop, is validated before it is
sent (META-4):

- scheme is https, port is 443, no userinfo
- host is one of the provider image CDNs (metadata_providers.ASSET_CDN_HOSTS)
- every address the host resolves to is public (not private, loopback,
  link-local, reserved, multicast, unspecified or otherwise non-global)

Redirects are never followed automatically; at most _MAX_REDIRECTS hops are
followed by hand, each validated as above.

DNS-rebinding residue: the host is resolved here for validation, and then
resolved again by the HTTP client when it connects. A resolver that answers
differently between the two lookups can still steer the connection to an
address that was never checked. Exposure is limited to the allowlisted CDN
hostnames, so exploiting it requires control of IGDB's or TheGamesDB's DNS.
Closing it fully needs connect-time IP pinning in the transport.
"""

from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx2
from fastapi import HTTPException

from backend.service.metadata_providers import ASSET_CDN_HOSTS
from backend.service.utils.path_utils import resolve_under, safe_basename

_TIMEOUT = 15.0
DEFAULT_MAX_BYTES = 20 * 1024 * 1024  # 20 MB
_MAX_REDIRECTS = 3
_HTTPS_PORT = 443
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# Declared Content-Type allowlist (META-20). image/svg+xml is deliberately
# absent: SVG is active content and must never land in the library.
_ALLOWED_MIME_TYPES = frozenset({
    "image/jpeg",
    "image/jpg",  # non-standard alias some CDNs send
    "image/png",
    "image/gif",
    "image/webp",
})


def _sniff_image_ext(data: bytes) -> str | None:
    """Return the file extension for *data*'s real format, from its magic
    bytes, or None if it is not one of the allowlisted raster formats. The
    saved extension comes from here, never from the declared Content-Type."""
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _is_forbidden_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for any address a server-side fetch must never reach."""
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        addr = mapped
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
        or not addr.is_global
    )


def _is_forbidden_redirect_host(host: str) -> bool:
    """Return True if the host is a private/internal address that should not be reached.

    Lexical check only (an IP literal or "localhost"); a hostname is not
    resolved here. _validate_request_url additionally resolves every
    hostname and checks each resulting address.
    """
    if host.lower().rstrip(".") == "localhost":
        return True
    # httpx2.URL.host strips brackets from IPv6 literals, so ip_address() can parse directly
    try:
        return _is_forbidden_ip(ipaddress.ip_address(host.split("%", 1)[0]))
    except ValueError:
        return False


def _resolve_host_addresses(host: str, port: int) -> list[str]:
    """Every address *host* resolves to. Split out so tests can substitute
    a fake resolver without touching the network."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def _reject(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _validate_request_url(url: str) -> None:
    """Validate one request target (the original URL or a redirect hop)
    before anything is sent to it.

    Raises:
        HTTPException: 422 if the URL breaks any rule, 502 if DNS fails.
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise _reject("Asset url is malformed")
    if parts.scheme != "https":
        raise _reject("Asset url must use https")
    if parts.username is not None or parts.password is not None:
        raise _reject("Asset url must not contain credentials")
    host = (parts.hostname or "").lower().rstrip(".")
    if host not in ASSET_CDN_HOSTS:
        raise _reject("Asset url host is not an allowed metadata provider CDN")
    if port is not None and port != _HTTPS_PORT:
        raise _reject("Asset url must use the default https port")
    try:
        addresses = _resolve_host_addresses(host, _HTTPS_PORT)
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"Asset host could not be resolved: {exc}")
    if not addresses:
        raise HTTPException(status_code=502, detail="Asset host resolved to no addresses")
    for raw in addresses:
        try:
            addr = ipaddress.ip_address(raw.split("%", 1)[0])
        except ValueError:
            raise _reject("Asset host resolved to an unparseable address")
        if _is_forbidden_ip(addr):
            raise _reject("Asset host resolves to a private or reserved address")


def _check_response_url(resp_url) -> None:
    """Defensive, lexical re-check of the URL the client actually fetched.
    With automatic redirects off it must equal the validated target, so
    this should never fire; it guards against a transport that redirects
    anyway."""
    scheme = getattr(resp_url, "scheme", None)
    host = (getattr(resp_url, "host", None) or "").lower().rstrip(".")
    if scheme != "https" or host not in ASSET_CDN_HOSTS or _is_forbidden_redirect_host(host):
        raise _reject("Asset redirect target must be an https non-private host")


def _write_exclusive(dest: Path, data: bytes, *, overwrite: bool) -> None:
    if overwrite:
        dest.write_bytes(data)
        return
    try:
        with dest.open("xb") as fh:
            fh.write(data)
    except FileExistsError:
        raise HTTPException(status_code=409, detail=f"Asset destination already exists: {dest.name}")


def download_remote_image(
    url: str,
    dest_dir: Path,
    *,
    filename_stem: str = "cover",
    max_bytes: int = DEFAULT_MAX_BYTES,
    overwrite: bool = False,
) -> Path:
    """Stream *url* into *dest_dir* as ``{filename_stem}{ext}``, enforcing:

    - every request target (original and each redirect hop) passes
      _validate_request_url before it is sent; at most _MAX_REDIRECTS hops
    - dest_dir and the final file path both resolve under LIBRARY_PATH
      (every legitimate destination, SOFTWARE_PATH's per-item cover art and
      MEDIA_PATH's Media library, is a subtree of it)
    - filename_stem is reduced to a safe basename
    - declared Content-Type is in _ALLOWED_MIME_TYPES and the body's magic
      bytes match an allowlisted raster format; ext comes from the bytes
    - response body capped at max_bytes, aborted mid-stream on overflow
    - the file is created exclusively unless *overwrite* is set (the Keep
      flow's per-leaf cover re-fetch is the one caller that replaces)

    Raises:
        HTTPException: 422 on any of the above violations, 409 if the
            destination exists and overwrite is False, 502 if the fetch
            itself fails.
    """
    from backend.service.utils import settings as _s
    lib_root = Path(_s.get("LIBRARY_PATH")).resolve()
    dest_dir_resolved = dest_dir.resolve()
    if not dest_dir_resolved.is_relative_to(lib_root):
        raise _reject("Resolved asset destination is outside LIBRARY_PATH.")

    current = url
    _validate_request_url(current)

    data: bytes | None = None
    content_type = ""
    with httpx2.Client(timeout=_TIMEOUT, follow_redirects=False) as client:
        for hop in range(_MAX_REDIRECTS + 1):
            with client.stream("GET", current) as resp:
                if resp.status_code in _REDIRECT_STATUSES:
                    location = resp.headers.get("location")
                    if not location:
                        raise HTTPException(status_code=502, detail="Asset redirect has no Location header")
                    if hop == _MAX_REDIRECTS:
                        raise _reject(f"Asset url exceeded {_MAX_REDIRECTS} redirects")
                    current = urljoin(current, location)
                    _validate_request_url(current)
                    continue

                try:
                    resp.raise_for_status()
                except httpx2.HTTPStatusError as e:
                    raise HTTPException(status_code=502, detail=f"Asset fetch failed: {e}")

                _check_response_url(resp.url)

                content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if content_type not in _ALLOWED_MIME_TYPES:
                    raise _reject(f"Asset url returned a disallowed content-type: {content_type}")

                # Stream body incrementally, abort before full download if limit is exceeded
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise _reject(f"Asset image exceeds the {max_bytes // 1024 ** 2} MB size limit")
                    chunks.append(chunk)
                data = b"".join(chunks)
                break

    if data is None:  # pragma: no cover, the loop always breaks or raises
        raise HTTPException(status_code=502, detail="Asset fetch produced no response")

    ext = _sniff_image_ext(data)
    if ext is None:
        raise _reject(f"Asset body is not a recognised raster image (declared {content_type})")

    stem = safe_basename(filename_stem, fallback="asset")
    dest_dir_resolved.mkdir(parents=True, exist_ok=True)
    try:
        dest = resolve_under(dest_dir_resolved, f"{stem}{ext}")
    except ValueError:
        raise _reject("Resolved asset path escapes its destination directory.")
    if not dest.is_relative_to(lib_root):
        raise _reject("Resolved asset path is outside LIBRARY_PATH.")
    _write_exclusive(dest, data, overwrite=overwrite)
    return dest
