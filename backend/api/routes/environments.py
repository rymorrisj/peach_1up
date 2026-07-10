import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from backend.constants import PC_ERAS
from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission
from backend.core.logger import get_logger
from backend.models.environment import Environment, EnvironmentCreate, EnvironmentRead, EnvironmentUpdate
from backend.models.user import User
from backend.service.environments import environments as plat_svc
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL

router = APIRouter(prefix="/api/v1/environments", tags=["environments"], redirect_slashes=False)
logger = get_logger(__name__)


@router.get("", response_model=list[EnvironmentRead])
def list_platforms(db: Session = Depends(get_db), _: User = Depends(get_active_user)):
    platforms = db.query(Environment).all()
    result = []
    for p in platforms:
        data = EnvironmentRead.model_validate(p)
        # Recomputed live, not read from the persisted status column, so this
        # always reflects current disk state — same freshness the Emulators
        # page already gets from get_install_path() on every request.
        data.status = plat_svc.compute_live_status(p)
        if p.working_image_path:
            try:
                data.working_image_size_bytes = Path(p.working_image_path).stat().st_size
            except OSError:
                pass
        if p.base_image_path:
            try:
                data.base_image_size_bytes = Path(p.base_image_path).stat().st_size
            except OSError:
                pass
        result.append(data)
    return result


@router.post("", response_model=EnvironmentRead, status_code=201)
def create_platform(body: EnvironmentCreate, db: Session = Depends(get_db), _: User = require_permission("can_edit_environments")):
    return plat_svc.create_platform(body, db)


@router.get("/{platform_id}", response_model=EnvironmentRead)
def get_platform(platform_id: int, db: Session = Depends(get_db), _: User = Depends(get_active_user)):
    platform = db.get(Environment, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Environment not found.")
    data = EnvironmentRead.model_validate(platform)
    # Recomputed live, matching list_platforms, so the detail page can't
    # disagree with the list page for the same platform on the same load.
    data.status = plat_svc.compute_live_status(platform)
    return data


@router.patch("/{platform_id}", response_model=EnvironmentRead)
def update_platform(platform_id: int, body: EnvironmentUpdate, db: Session = Depends(get_db), _: User = require_permission("can_edit_environments")):
    return plat_svc.update_platform(platform_id, body, db)


@router.post("/{platform_id}/confirm-delete")
def issue_delete_token(platform_id: int, db: Session = Depends(get_db), _: User = require_permission("can_edit_environments")):
    if not db.get(Environment, platform_id):
        raise HTTPException(status_code=404, detail="Environment not found.")
    return {"confirmation_token": confirmation_tokens.issue("environment", platform_id, "delete"), "expires_in_seconds": TOKEN_TTL}


@router.delete("/{platform_id}", status_code=204)
def delete_platform(
    platform_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_environments"),
):
    plat_svc.delete_platform(platform_id, confirmation_token, db)


@router.post("/{platform_id}/health")
def platform_health(platform_id: int, db: Session = Depends(get_db), _: User = require_permission("can_edit_environments")):
    platform = db.get(Environment, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Environment not found.")
    return plat_svc.check_platform_health(platform, db)


@router.post("/{slug}/install-media")
async def upload_install_media(
    slug: str,
    file: UploadFile,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_environments"),
):
    """Stream-write an uploaded OS install/disk image for the named Environment.

    Environment infrastructure, not a SoftwareItem — never scanned, never
    deduped against the library (relocated from the former
    POST /api/v1/media/upload, which trusted a form-supplied era; this route
    derives era from the Environment record itself).

    Returns:
        { path, slug, size_bytes }
    """
    environment = db.query(Environment).filter(Environment.slug == slug).first()
    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found.")
    if environment.era not in PC_ERAS:
        raise HTTPException(
            status_code=422,
            detail=f"OS install media requires a PC-era environment: {', '.join(sorted(PC_ERAS))}.",
        )
    if not file.filename:
        raise HTTPException(status_code=422, detail="A filename is required.")

    from backend.core.settings import get_settings
    from backend.service.utils.upload_utils import DEFAULT_MAX_BYTES, begin_upload, stream_upload_to_disk

    svc = get_settings()
    max_bytes = int(svc.get("UPLOAD_MAX_BYTES", DEFAULT_MAX_BYTES) or DEFAULT_MAX_BYTES)
    os_root = Path(svc.get_env_var("OS_PATH")).resolve() / environment.era

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
