import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core import rate_limit
from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission
from backend.models.library_set import (
    LibrarySet, LibrarySetItem, LibrarySetItemRead, LibrarySetItemUpdate,
    LibrarySetRead, LibrarySetUpdate, set_to_read, sets_to_read_bulk,
)
from backend.models.media_restriction import MediaRestriction
from backend.models.pagination import Page
from backend.models.user import User

router = APIRouter(prefix="/api/v1/library", tags=["library"])

_UPLOAD_RATE_LIMIT = 10
_UPLOAD_RATE_WINDOW_SECONDS = 60.0


def _enforce_rate_limit(bucket: str, request: Request, limit: int, window_seconds: float) -> None:
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = rate_limit.check_and_record(f"{bucket}:{client_ip}", limit, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests, please slow down.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


class RestrictionsBody(BaseModel):
    user_ids: list[int]


@router.get("/sets", response_model=Page[LibrarySetRead])
def list_library_sets(
    era: str | None = None,
    profile_assigned: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    q = db.query(LibrarySet)
    if era:
        q = q.filter(LibrarySet.era == era)
    if profile_assigned is True:
        q = q.filter(LibrarySet.profile_id.isnot(None))
    elif profile_assigned is False:
        q = q.filter(LibrarySet.profile_id.is_(None))
    total = q.count()
    rows = q.order_by(LibrarySet.title).offset(offset).limit(limit).all()
    return Page(items=sets_to_read_bulk(rows, db), total=total, limit=limit, offset=offset)


@router.post("/sets", response_model=LibrarySetRead, status_code=201)
async def create_library_set(
    request: Request,
    title: str = Form(...),
    era: str = Form("unknown"),
    profile_id: Optional[int] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    """Create a multi-disc set from N uploaded files."""
    _enforce_rate_limit("library-upload", request, _UPLOAD_RATE_LIMIT, _UPLOAD_RATE_WINDOW_SECONDS)

    from backend.core.settings import get_settings
    from backend.service.utils.upload_utils import (
        DEFAULT_MAX_BYTES,
        begin_upload,
        stream_upload_to_disk,
    )

    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required.")

    svc = get_settings()
    max_bytes = int(svc.get("UPLOAD_MAX_BYTES", DEFAULT_MAX_BYTES) or DEFAULT_MAX_BYTES)
    media_root = Path(svc.get_env_var("MEDIA_PATH")).resolve()

    uploaded_paths: list[tuple[Path, Path]] = []
    try:
        for f in files:
            if not f.filename:
                raise HTTPException(status_code=422, detail="Each file must have a filename.")
            dest_dir, dest_path = begin_upload(media_root, f.filename)
            try:
                await stream_upload_to_disk(f, dest_path, max_bytes)
            except HTTPException:
                shutil.rmtree(dest_dir, ignore_errors=True)
                raise
            except Exception as exc:
                shutil.rmtree(dest_dir, ignore_errors=True)
                raise HTTPException(status_code=500, detail=f"Upload failed for {f.filename}: {exc}") from exc
            uploaded_paths.append((dest_dir, dest_path))
    except HTTPException:
        for dest_dir, _ in uploaded_paths:
            shutil.rmtree(dest_dir, ignore_errors=True)
        raise

    from backend.service.utils.smart_media_detector import detect as _smart_detect
    from backend.service.utils.era_defaults import defaults_for_era, lookup_platform_and_profile

    launch_disc_path = uploaded_paths[0][1]
    _scan = _smart_detect(launch_disc_path)
    detected_era: str = _scan.era if _scan.era is not None else era

    detected_platform_id: int | None = None
    detected_profile_id: int | None = None
    if detected_era and detected_era != "unknown":
        _emulator_slug, _profile_era = defaults_for_era(detected_era)
        if _emulator_slug and _profile_era:
            detected_platform_id, detected_profile_id = lookup_platform_and_profile(
                _emulator_slug, _profile_era, db
            )

    resolved_profile_id = detected_profile_id if profile_id is None else profile_id

    library_set = LibrarySet(
        title=title,
        era=detected_era,
        platform_id=detected_platform_id,
        profile_id=resolved_profile_id,
    )
    db.add(library_set)
    db.flush()

    items: list[LibrarySetItem] = []
    for disc_number, (_, dest_path) in enumerate(uploaded_paths, start=1):
        item = LibrarySetItem(
            set_id=library_set.id,
            disc_number=disc_number,
            media_path=str(dest_path),
            file_size_bytes=dest_path.stat().st_size if dest_path.exists() else None,
        )
        db.add(item)
        items.append(item)
    db.flush()

    library_set.launch_disk_id = items[0].id
    db.add(library_set)
    db.commit()
    db.refresh(library_set)
    return set_to_read(library_set, db)


@router.get("/sets/{set_id}", response_model=LibrarySetRead)
def get_library_set(
    set_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    s = db.get(LibrarySet, set_id)
    if not s:
        raise HTTPException(status_code=404, detail="Library set not found.")
    return set_to_read(s, db)


@router.patch("/sets/{set_id}", response_model=LibrarySetRead)
def update_library_set(
    set_id: int,
    body: LibrarySetUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    from sqlalchemy import select as _select
    s = db.get(LibrarySet, set_id)
    if not s:
        raise HTTPException(status_code=404, detail="Library set not found.")
    if body.display_disk_id is not None:
        item_ids = set(
            db.execute(_select(LibrarySetItem.id).where(LibrarySetItem.set_id == set_id)).scalars().all()
        )
        if body.display_disk_id not in item_ids:
            raise HTTPException(status_code=422, detail="disc does not belong to this set.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return set_to_read(s, db)


@router.get("/sets/{set_id}/restrictions")
def get_set_restrictions(
    set_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    if not db.get(LibrarySet, set_id):
        raise HTTPException(status_code=404, detail="Library set not found.")
    rows = db.query(MediaRestriction).filter(MediaRestriction.library_set_id == set_id).all()
    return {"restricted_user_ids": [r.user_id for r in rows]}


@router.put("/sets/{set_id}/restrictions")
def set_set_restrictions(
    set_id: int,
    body: RestrictionsBody,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    if not db.get(LibrarySet, set_id):
        raise HTTPException(status_code=404, detail="Library set not found.")
    db.query(MediaRestriction).filter(MediaRestriction.library_set_id == set_id).delete()
    for user_id in body.user_ids:
        db.add(MediaRestriction(user_id=user_id, library_set_id=set_id))
    db.commit()
    return {"restricted_user_ids": body.user_ids}


@router.patch("/sets/{set_id}/items/{item_id}")
def update_library_set_item(
    set_id: int,
    item_id: int,
    body: LibrarySetItemUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    item = db.get(LibrarySetItem, item_id)
    if not item or item.set_id != set_id:
        raise HTTPException(status_code=404, detail="Item not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return LibrarySetItemRead.model_validate(item)
