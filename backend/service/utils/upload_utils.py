"""Shared multipart upload helpers for media.py (OS images) and library.py (game media).

Both endpoints need the same two things: an unguessable, collision-free, traversal-safe
destination path, and a size-capped chunked write. This module is the single
choke-point for both, mirroring how path_utils.normalise_path centralises path
validation elsewhere.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile

from backend.service.utils.path_utils import resolve_under, sanitize_filename
from backend.service.utils.slug_generator import unique_slug

DEFAULT_MAX_BYTES = 25 * 1024 ** 3  # 25 GB
_CHUNK_SIZE = 1024 * 1024  # 1 MB — avoids loading the full file into memory


def begin_upload(base_dir: Path, filename: str) -> tuple[Path, Path]:
    """Allocate a fresh, traversal-safe destination for an uploaded file.

    The raw filename is sanitized to a safe basename, then placed in its own
    slug-named subdirectory under *base_dir* (collision-suffixed if the slug
    is already in use on disk) so concurrent or repeated uploads can never
    silently overwrite an existing file.

    Args:
        base_dir: Allowlisted root the upload must resolve under (e.g. MEDIA_PATH,
                   or OS_PATH/{era}).
        filename: Raw filename from the multipart upload.

    Returns:
        (dest_dir, dest_path) — dest_dir has already been created on disk.

    Raises:
        HTTPException(400): If the resolved destination would escape base_dir.
    """
    safe_name = sanitize_filename(filename)
    safe_stem = Path(safe_name).stem

    base_dir.mkdir(parents=True, exist_ok=True)
    unique_stem = unique_slug(safe_stem, lambda s: (base_dir / s).exists())

    try:
        dest_dir = resolve_under(base_dir, unique_stem)
        dest_path = resolve_under(dest_dir, safe_name)
    except ValueError as exc:
        from backend.core.logger import get_logger
        get_logger(__name__).warning("Upload rejected — path escapes base directory: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid filename.") from exc

    dest_dir.mkdir(parents=True, exist_ok=False)
    return dest_dir, dest_path


async def stream_upload_to_disk(file: UploadFile, dest_path: Path, max_bytes: int) -> int:
    """Stream *file* to *dest_path* in chunks, enforcing *max_bytes*.

    On a size-cap violation the partial file is removed and HTTPException(413)
    is raised. Callers are responsible for removing dest_path's parent directory
    on any other failure (it was created solely for this upload).

    Returns:
        Total bytes written.
    """
    written = 0
    with dest_path.open("wb") as fh:
        while True:
            chunk = await file.read(_CHUNK_SIZE)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                fh.close()
                dest_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds the maximum allowed size ({max_bytes // 1024 ** 3} GB).",
                )
            fh.write(chunk)
    return written
