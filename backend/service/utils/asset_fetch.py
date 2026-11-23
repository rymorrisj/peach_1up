"""Shared server-side image download: SSRF-safe, streamed, size-capped.

The Accept All flow (backend/service/games/media_link.py) fetches
provider-supplied https image URLs into the library through it.

The URL comes from the client, so it is untrusted input.
Every request, including every redirect hop, is validated before it is
sent (META-4):

- scheme is https, port is 443, no userinfo
- host is one of the provider image CDNs (metadata_providers.ASSET_CDN_HOSTS)
- every address the host resolves to is public (not private, loopback,
  link-local, reserved, multicast, unspecified or otherwise non-global)

Redirects are never followed automatically; at most _MAX_REDIRECTS hops are
followed by hand, each validated as above.

Bodies stream to a temp file and reach their final path only through
os.replace (META-6, META-21), so a failed download never leaves a partial
file at the destination.

DNS-rebinding residue: the host is resolved here for validation, and then
resolved again by the HTTP client when it connects. A resolver that answers
differently between the two lookups can still steer the connection to an
address that was never checked. Exposure is limited to the allowlisted CDN
hostnames, so exploiting it requires control of IGDB's or TheGamesDB's DNS.
Closing it fully needs connect-time IP pinning in the transport.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import tempfile
import time
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


class AssetFetchFailure(HTTPException):
    """HTTPException tagged with why a download failed, so a background job
    can report the real reason without parsing the detail text.

    kind is "time_budget" (deadline passed), "upstream" (the CDN answered
    with *upstream_status*) or "network" (DNS failure).
    """

    def __init__(self, status_code: int, detail: str, *, kind: str, upstream_status: int | None = None):
        super().__init__(status_code=status_code, detail=detail)
        self.kind = kind
        self.upstream_status = upstream_status


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
    except OSError:
        raise AssetFetchFailure(502, "Asset host could not be resolved.", kind="network")
    if not addresses:
        raise AssetFetchFailure(502, "Asset host resolved to no addresses.", kind="network")
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


_SNIFF_BYTES = 12


def _library_root() -> Path:
    from backend.service.utils import settings as _s
    return Path(_s.get("LIBRARY_PATH")).resolve()


def _require_under_library(path: Path, lib_root: Path, what: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(lib_root):
        raise _reject(f"Resolved asset {what} is outside LIBRARY_PATH.")
    return resolved


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() > deadline:
        raise AssetFetchFailure(
            422, "Asset download exceeded the time budget for this request.", kind="time_budget",
        )


def _request_timeout(deadline: float | None) -> float:
    if deadline is None:
        return _TIMEOUT
    return max(0.1, min(_TIMEOUT, deadline - time.monotonic()))


def _stream_body_to(fh, resp, max_bytes: int, deadline: float | None) -> bytes:
    """Write the response body to *fh* chunk by chunk, never holding more
    than one chunk in memory. Returns the first _SNIFF_BYTES for the format
    sniff."""
    head = b""
    total = 0
    for chunk in resp.iter_bytes():
        _check_deadline(deadline)
        total += len(chunk)
        if total > max_bytes:
            raise _reject(f"Asset image exceeds the {max_bytes // 1024 ** 2} MB size limit")
        if len(head) < _SNIFF_BYTES:
            head += chunk[: _SNIFF_BYTES - len(head)]
        fh.write(chunk)
    return head


def fetch_image_to_temp(
    url: str,
    staging_dir: Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    deadline: float | None = None,
) -> tuple[Path, str]:
    """Stream *url* into a new temp file inside *staging_dir* and return
    ``(temp_path, ext)``. Nothing outside *staging_dir* is touched.

    - every request target (original and each redirect hop) passes
      _validate_request_url before it is sent; at most _MAX_REDIRECTS hops
    - declared Content-Type is in _ALLOWED_MIME_TYPES and the body's magic
      bytes match an allowlisted raster format; ext comes from the bytes
    - the body is written chunk by chunk, capped at max_bytes and aborted
      mid-stream on overflow or once *deadline* (time.monotonic()) passes

    The temp file is removed on every failure.

    Raises:
        HTTPException: 422 on any of the above violations, 502 if the fetch
            itself fails.
    """
    lib_root = _library_root()
    staging = _require_under_library(staging_dir, lib_root, "staging directory")

    current = url
    _validate_request_url(current)
    _check_deadline(deadline)

    staging.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix="dl-", suffix=".part", dir=staging)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as fh:
            head: bytes | None = None
            content_type = ""
            with httpx2.Client(timeout=_request_timeout(deadline), follow_redirects=False) as client:
                for hop in range(_MAX_REDIRECTS + 1):
                    _check_deadline(deadline)
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
                            raise AssetFetchFailure(
                                502, f"Asset fetch failed with status {e.response.status_code}.",
                                kind="upstream", upstream_status=e.response.status_code,
                            )

                        _check_response_url(resp.url)

                        content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                        if content_type not in _ALLOWED_MIME_TYPES:
                            raise _reject(f"Asset url returned a disallowed content-type: {content_type}")

                        head = _stream_body_to(fh, resp, max_bytes, deadline)
                        break

        if head is None:  # pragma: no cover, the loop always breaks or raises
            raise HTTPException(status_code=502, detail="Asset fetch produced no response")
        ext = _sniff_image_ext(head)
        if ext is None:
            raise _reject(f"Asset body is not a recognised raster image (declared {content_type})")
        return tmp, ext
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def final_image_path(dest_dir: Path, filename_stem: str, ext: str) -> Path:
    """The containment-checked final path ``dest_dir/{safe stem}{ext}``.

    Raises:
        HTTPException: 422 if dest_dir or the final path leaves
            LIBRARY_PATH, or the final path escapes dest_dir.
    """
    lib_root = _library_root()
    dest_dir_resolved = _require_under_library(dest_dir, lib_root, "destination")
    stem = safe_basename(filename_stem, fallback="asset")
    try:
        dest = resolve_under(dest_dir_resolved, f"{stem}{ext}")
    except ValueError:
        raise _reject("Resolved asset path escapes its destination directory.")
    if not dest.is_relative_to(lib_root):
        raise _reject("Resolved asset path is outside LIBRARY_PATH.")
    return dest


def commit_temp_image(tmp: Path, dest: Path, *, overwrite: bool) -> None:
    """Move a fetched temp file onto *dest* with os.replace.

    Without *overwrite* the destination is first claimed with an exclusive
    create, so an existing file is never replaced; the claim is removed
    again if the move fails.

    Raises:
        HTTPException: 409 if *dest* exists and overwrite is False.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    claimed = False
    if not overwrite:
        try:
            with dest.open("xb"):
                pass
        except FileExistsError:
            raise HTTPException(status_code=409, detail=f"Asset destination already exists: {dest.name}")
        claimed = True
    try:
        os.replace(tmp, dest)
    except BaseException:
        if claimed:
            dest.unlink(missing_ok=True)
        raise


def download_remote_image(
    url: str,
    dest_dir: Path,
    *,
    filename_stem: str = "cover",
    max_bytes: int = DEFAULT_MAX_BYTES,
    overwrite: bool = False,
    staging_dir: Path | None = None,
    deadline: float | None = None,
) -> Path:
    """Fetch *url* (fetch_image_to_temp) and move it to
    ``dest_dir/{filename_stem}{ext}`` (commit_temp_image). The temp file
    lives in *staging_dir*, or in dest_dir when none is given, and never
    survives a failure.

    Raises:
        HTTPException: as fetch_image_to_temp, final_image_path and
            commit_temp_image.
    """
    final_dir = _require_under_library(dest_dir, _library_root(), "destination")
    tmp, ext = fetch_image_to_temp(url, staging_dir or final_dir, max_bytes=max_bytes, deadline=deadline)
    try:
        dest = final_image_path(final_dir, filename_stem, ext)
        commit_temp_image(tmp, dest, overwrite=overwrite)
    finally:
        tmp.unlink(missing_ok=True)
    return dest
