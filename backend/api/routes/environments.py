import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from backend.constants import PC_ERAS
from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission
from backend.core.logger import get_logger
from backend.models.environment import EnvironmentItem, EnvironmentItemCreate, EnvironmentItemRead, EnvironmentItemUpdate
from backend.models.user import UserItem
from backend.service.environments import environments as plat_svc
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL
from backend.service.utils.era_defaults import (
    CANDIDATE_EVAL_PROFILE_SENTINEL, evaluate_launch_readiness,
)

router = APIRouter(prefix="/api/v1/environment-items", tags=["environments"], redirect_slashes=False)
logger = get_logger(__name__)


@router.get("", response_model=list[EnvironmentItemRead])
def list_environment_items(
    era: str | None = Query(
        default=None,
        description=(
            "When supplied, each row's launch_blocked_reason is computed against "
            "this era, for a platform-picker candidate list. Omitted, the response "
            "is the unfiltered platform catalog with launch_blocked_reason left null "
            "on every row, unchanged from before this parameter existed."
        ),
    ),
    db: Session = Depends(get_db),
    _: UserItem = Depends(get_active_user),
):
    platforms = db.query(EnvironmentItem).all()
    result = []
    for p in platforms:
        data = EnvironmentItemRead.model_validate(p)
        # Recomputed live, never persisted, so this always reflects current
        # disk state — same freshness the Emulators page already gets from
        # get_install_path() on every request.
        data.is_present = plat_svc.compute_environment_presence(p)
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
        if era is not None:
            # Precedence matches PlatformField.tsx's pre-existing client-side
            # order (era mismatch, then presence, then installed): era
            # mismatch and "not present" are checked here directly since
            # evaluate_launch_readiness covers neither (era mismatch it does
            # cover, but checking it here first avoids a wasted call into it
            # for the common "wrong era" case; presence it structurally never
            # covers, see CANDIDATE_EVAL_PROFILE_SENTINEL's neighbor comment
            # in era_defaults.py). Whatever remains (not provisioned, not
            # installed) is exactly what evaluate_launch_readiness already
            # computes correctly per candidate, no new query, this loops the
            # platforms list already fetched above.
            if p.era != era:
                data.launch_blocked_reason = "environment_era_mismatch"
            elif not data.is_present:
                data.launch_blocked_reason = "environment_not_present"
            else:
                data.launch_blocked_reason = evaluate_launch_readiness(
                    call_site="item",
                    environment=p,
                    is_pc=True,
                    era=era,
                    profile_item_id=CANDIDATE_EVAL_PROFILE_SENTINEL,
                )
        result.append(data)
    return result


@router.post("", response_model=EnvironmentItemRead, status_code=201)
def create_environment_item(body: EnvironmentItemCreate, db: Session = Depends(get_db), _: UserItem = require_permission("can_manage_environment")):
    return plat_svc.create_environment_item(body, db)


@router.get("/{id}", response_model=EnvironmentItemRead)
def get_environment_item(id: int, db: Session = Depends(get_db), _: UserItem = Depends(get_active_user)):
    platform = db.get(EnvironmentItem, id)
    if not platform:
        raise HTTPException(status_code=404, detail="Environment not found.")
    data = EnvironmentItemRead.model_validate(platform)
    # Recomputed live, matching list_environment_items, so the detail page can't
    # disagree with the list page for the same platform on the same load.
    data.is_present = plat_svc.compute_environment_presence(platform)
    return data


@router.patch("/{id}", response_model=EnvironmentItemRead)
def update_environment_item(id: int, body: EnvironmentItemUpdate, db: Session = Depends(get_db), _: UserItem = require_permission("can_manage_environment")):
    return plat_svc.update_environment_item(id, body, db)


@router.post("/{id}/confirm-delete")
def issue_delete_token(id: int, db: Session = Depends(get_db), _: UserItem = require_permission("can_manage_environment")):
    if not db.get(EnvironmentItem, id):
        raise HTTPException(status_code=404, detail="Environment not found.")
    return {"confirmation_token": confirmation_tokens.issue("environment_item", id, "delete"), "expires_in_seconds": TOKEN_TTL}


@router.delete("/{id}", status_code=204)
def delete_environment_item(
    id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_environment"),
):
    plat_svc.delete_environment_item(id, confirmation_token, db)


@router.post("/{id}/health")
def environment_item_health(id: int, db: Session = Depends(get_db), _: UserItem = require_permission("can_manage_environment")):
    platform = db.get(EnvironmentItem, id)
    if not platform:
        raise HTTPException(status_code=404, detail="Environment not found.")
    return plat_svc.check_environment_item_health(platform, db)


@router.post("/{slug}/install-media")
async def upload_install_media(
    slug: str,
    file: UploadFile,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_environment"),
):
    """Stream-write an uploaded OS install/disk image for the named EnvironmentItem.

    Environment infrastructure, not a SoftwareItem — never scanned, never
    deduped against the library (relocated from the former
    POST /api/v1/media/upload, which trusted a form-supplied era; this route
    derives era from the Environment record itself).

    Returns:
        { path, slug, size_bytes }
    """
    environment = db.query(EnvironmentItem).filter(EnvironmentItem.slug == slug).first()
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
