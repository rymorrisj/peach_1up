from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from backend.core.dependencies import require_permission
from backend.models.user import User
from backend.service.utils.slug_generator import slugify

router = APIRouter(prefix="/api/v1/media", tags=["media"])

_PC_ERAS = frozenset({"dos", "win31", "win95", "win98", "winxp"})
_DEFAULT_MAX_BYTES = 25 * 1024 ** 3  # 25 GB


@router.post("/upload")
async def upload_media(
    file: UploadFile,
    era: str = Form(...),
    media_type: str = Form(...),
    _: User = require_permission("can_edit_library"),
):
    """Stream-write an uploaded media file to the configured library directory.

    Args:
        file:       Multipart file upload.
        era:        Gaming era string (e.g. 'win98'). OS media requires a PC era.
        media_type: 'os' for OS disk images, 'game' for game media.

    Returns:
        { path, slug, size_bytes }
    """
    if media_type not in ("os", "game"):
        raise HTTPException(status_code=422, detail="media_type must be 'os' or 'game'.")
    if media_type == "os" and era not in _PC_ERAS:
        raise HTTPException(
            status_code=422,
            detail=f"OS media requires a PC era: {', '.join(sorted(_PC_ERAS))}.",
        )
    if not file.filename:
        raise HTTPException(status_code=422, detail="A filename is required.")

    from backend.core.settings import get_settings
    svc = get_settings()
    max_bytes = int(svc.get("UPLOAD_MAX_BYTES", _DEFAULT_MAX_BYTES) or _DEFAULT_MAX_BYTES)

    if media_type == "os":
        base = Path(svc.get_env_var("OS_PATH")).resolve()
    else:
        base = Path(svc.get_env_var("MEDIA_PATH")).resolve()

    slug = slugify(Path(file.filename).stem, fallback="upload")
    dest_dir = base / era / slug if media_type == "os" else base / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file.filename

    written = 0
    try:
        with dest_path.open("wb") as fh:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB chunks — no full-file memory load
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
    except HTTPException:
        raise
    except Exception as exc:
        if dest_path.exists():
            dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    return {"path": str(dest_path), "slug": slug, "size_bytes": written}
