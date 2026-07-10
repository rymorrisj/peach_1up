import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from backend.constants import PC_ERAS
from backend.core.dependencies import require_permission
from backend.models.user import User

router = APIRouter(prefix="/api/v1/media", tags=["media"])


@router.post("/upload")
async def upload_media(
    file: UploadFile,
    era: str = Form(...),
    media_type: str = Form(...),
    _: User = require_permission("can_edit_software"),
):
    """Stream-write an uploaded OS install/disk image for environment registration.

    Game media uploads use the chunked endpoints under
    /api/v1/software/uploads (init → chunks → complete), which chain into the
    full library ingest pipeline (era detection, profile assignment, dedup).
    OS images are Environment fields, not SoftwareItems — never scanned, never
    deduped against the library — so they keep this minimal upload-only path.

    Args:
        file:       Multipart file upload.
        era:        Gaming era string (e.g. 'win98'). Must be a PC era.
        media_type: Must be 'os' — 'game' uses the library chunked upload flow.

    Returns:
        { path, slug, size_bytes }
    """
    if media_type != "os":
        raise HTTPException(
            status_code=400,
            detail="media_type must be 'os'. Game media uploads use the /api/v1/software/uploads chunked flow.",
        )
    if era not in PC_ERAS:
        raise HTTPException(
            status_code=422,
            detail=f"OS media requires a PC era: {', '.join(sorted(PC_ERAS))}.",
        )
    if not file.filename:
        raise HTTPException(status_code=422, detail="A filename is required.")

    from backend.core.settings import get_settings
    from backend.service.utils.upload_utils import DEFAULT_MAX_BYTES, begin_upload, stream_upload_to_disk

    svc = get_settings()
    max_bytes = int(svc.get("UPLOAD_MAX_BYTES", DEFAULT_MAX_BYTES) or DEFAULT_MAX_BYTES)
    os_root = (Path(svc.get_env_var("OS_PATH")).resolve() / era)

    dest_dir, dest_path = begin_upload(os_root, file.filename)

    try:
        written = await stream_upload_to_disk(file, dest_path, max_bytes)
    except HTTPException:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    return {"path": str(dest_path), "slug": dest_dir.name, "size_bytes": written}
