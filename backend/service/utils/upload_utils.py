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

DEFAULT_MAX_BYTES = 25 * 1024 ** 3  # 25 GB — absolute per-file cap
_CHUNK_SIZE = 1024 * 1024  # 1 MB — avoids loading the full file into memory

# Chunked / background upload tuning (all overridable via settings of the same
# UPPER_SNAKE name). See api/routes/uploads.py and service/library/chunked_uploads.py.
DEFAULT_BACKGROUND_THRESHOLD_BYTES = 5 * 1024 ** 3   # 5 GB — finalize inline at/under, background above
DEFAULT_CHUNK_MAX_BYTES = 64 * 1024 ** 2             # 64 MB — largest single chunk the server will accept
DEFAULT_SCAN_NAV_THRESHOLD_BYTES = 1 * 1024 ** 3     # 1 GB — scans above surface in the nav bell
DEFAULT_UPLOAD_TMP_TTL_SECONDS = 24 * 3600           # orphaned tmp_chunks dirs older than this are swept
TMP_CHUNKS_DIRNAME = "tmp_chunks"


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


def find_existing_duplicate(media_root: Path, uploaded_path: Path, uploaded_size: int) -> Path | None:
    """Search media_root for a file byte-identical to uploaded_path.

    Browser uploads always land in a fresh, uniquely-named directory (see
    begin_upload), so re-uploading content that's already in the library —
    e.g. re-adding a file after its prior library item was removed, which
    intentionally leaves the media file on disk — would otherwise always be
    treated as new. The actual lookup is index-backed (media_dup_index) rather
    than a fresh directory scan per call; see that module for the build/cache/
    invalidation design.

    Returns the path of the matching existing file, or None.
    """
    from backend.service.library.items import _MEDIA_SUFFIXES
    from backend.service.utils import media_dup_index
    from backend.service.utils.file_types import all_supported_extensions

    # .img is deliberately excluded even though some eras list it under
    # supported_media: drive images are app-generated containers, never
    # something a browser upload could legitimately match against, and
    # they're rewritten in place on every pre-install launch (see
    # drive_hydration.hydrate_drive_for_item) and unlinked on item removal —
    # the most volatile file type under media_root, for zero dedup benefit.
    candidate_exts = (_MEDIA_SUFFIXES | all_supported_extensions()) - {".img"}

    return media_dup_index.find_duplicate(media_root, candidate_exts, uploaded_path, uploaded_size)
