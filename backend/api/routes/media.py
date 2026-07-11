import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission
from backend.core.logger import get_logger
from backend.models.media import (
    MediaCollection, MediaCollectionCreate, MediaCollectionRead, MediaCollectionUpdate,
    MediaItem, MediaItemCreate, MediaItemRead, MediaItemUpdate,
    MediaLink, MediaLinkCreate, MediaLinkRead,
    collection_to_read, collections_to_read_bulk, item_to_read, items_to_read_bulk,
)
from backend.models.pagination import Page
from backend.models.software import SoftwareCollection
from backend.models.user import User
from backend.service.utils.slug_generator import unique_slug

router = APIRouter(prefix="/api/v1/media", tags=["media"])
logger = get_logger(__name__)


def _unique_media_slug(title: str, db: Session) -> str:
    """Slug uniqueness spans both media_items and media_collections — the two
    share the /media/{slug}-style namespace, so a title collision between an
    item and a collection is treated the same as a same-table collision."""
    return unique_slug(
        title,
        lambda s: (
            db.query(MediaItem).filter(MediaItem.slug == s).first() is not None
            or db.query(MediaCollection).filter(MediaCollection.slug == s).first() is not None
        ),
    )


# ---------------------------------------------------------------------------
# Items — list + create
# ---------------------------------------------------------------------------


@router.get("", response_model=Page[MediaItemRead])
def list_media_items(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    q = db.query(MediaItem).order_by(MediaItem.id)
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return Page(items=items_to_read_bulk(rows, db), total=total, limit=limit, offset=offset)


@router.post("", response_model=MediaItemRead, status_code=201)
def create_media_item(
    body: MediaItemCreate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_media"),
):
    item = MediaItem(**body.model_dump(), slug=_unique_media_slug(body.title, db))
    db.add(item)
    db.commit()
    db.refresh(item)
    return item_to_read(item, db)


# ---------------------------------------------------------------------------
# Items — read / update / delete
# ---------------------------------------------------------------------------


@router.get("/{item_id}", response_model=MediaItemRead)
def get_media_item(item_id: int, db: Session = Depends(get_db), _: User = Depends(get_active_user)):
    item = db.get(MediaItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Media item not found.")
    return item_to_read(item, db)


@router.patch("/{item_id}", response_model=MediaItemRead)
def update_media_item(
    item_id: int,
    body: MediaItemUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_media"),
):
    item = db.get(MediaItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Media item not found.")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item_to_read(item, db)


@router.delete("/{item_id}", status_code=204)
def delete_media_item(
    item_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_media"),
):
    item = db.get(MediaItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Media item not found.")
    db.delete(item)
    db.commit()


# ---------------------------------------------------------------------------
# Collections — create / read / update / delete
# ---------------------------------------------------------------------------


@router.post("/collections", response_model=MediaCollectionRead, status_code=201)
def create_media_collection(
    body: MediaCollectionCreate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_media"),
):
    collection = MediaCollection(**body.model_dump(), slug=_unique_media_slug(body.title, db))
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection_to_read(collection, db)


@router.get("/collections", response_model=Page[MediaCollectionRead])
def list_media_collections(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    q = db.query(MediaCollection).order_by(MediaCollection.id)
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return Page(items=collections_to_read_bulk(rows, db), total=total, limit=limit, offset=offset)


@router.get("/collections/{collection_id}", response_model=MediaCollectionRead)
def get_media_collection(
    collection_id: int, db: Session = Depends(get_db), _: User = Depends(get_active_user)
):
    collection = db.get(MediaCollection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Media collection not found.")
    return collection_to_read(collection, db)


@router.patch("/collections/{collection_id}", response_model=MediaCollectionRead)
def update_media_collection(
    collection_id: int,
    body: MediaCollectionUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_media"),
):
    collection = db.get(MediaCollection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Media collection not found.")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(collection, key, value)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection_to_read(collection, db)


@router.delete("/collections/{collection_id}", status_code=204)
def delete_media_collection(
    collection_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_media"),
):
    collection = db.get(MediaCollection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Media collection not found.")
    db.delete(collection)
    db.commit()


# ---------------------------------------------------------------------------
# Link / unlink a MediaItem or MediaCollection to a SoftwareCollection.
#
# doc 03's route table only listed item-level linking (/media/{id}/link);
# the collections/{id}/link counterpart below closes that gap — the doc's own
# prose names "an OST collection linked to a game" as a canonical case, so a
# MediaCollection needs the same link/unlink surface as a MediaItem.
# ---------------------------------------------------------------------------


@router.post("/{item_id}/link", response_model=MediaLinkRead, status_code=201)
def link_media_item(
    item_id: int,
    body: MediaLinkCreate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_media"),
):
    item = db.get(MediaItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Media item not found.")
    if not db.get(SoftwareCollection, body.software_collection_id):
        raise HTTPException(status_code=404, detail="Software collection not found.")
    link = MediaLink(
        media_item_id=item_id,
        software_collection_id=body.software_collection_id,
        link_note=body.link_note,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@router.delete("/{item_id}/link", status_code=204)
def unlink_media_item(
    item_id: int,
    software_collection_id: int = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_media"),
):
    link = (
        db.query(MediaLink)
        .filter(
            MediaLink.media_item_id == item_id,
            MediaLink.software_collection_id == software_collection_id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Link not found.")
    db.delete(link)
    db.commit()


@router.post("/collections/{collection_id}/link", response_model=MediaLinkRead, status_code=201)
def link_media_collection(
    collection_id: int,
    body: MediaLinkCreate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_media"),
):
    collection = db.get(MediaCollection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Media collection not found.")
    if not db.get(SoftwareCollection, body.software_collection_id):
        raise HTTPException(status_code=404, detail="Software collection not found.")
    link = MediaLink(
        media_collection_id=collection_id,
        software_collection_id=body.software_collection_id,
        link_note=body.link_note,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@router.delete("/collections/{collection_id}/link", status_code=204)
def unlink_media_collection(
    collection_id: int,
    software_collection_id: int = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_media"),
):
    link = (
        db.query(MediaLink)
        .filter(
            MediaLink.media_collection_id == collection_id,
            MediaLink.software_collection_id == software_collection_id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Link not found.")
    db.delete(link)
    db.commit()


# ---------------------------------------------------------------------------
# Archive upload — reuses begin_upload/stream_upload_to_disk exactly as the
# relocated OS-install-media route does (backend/api/routes/environments.py).
# This endpoint only stages bytes on disk under MEDIA_PATH and returns the
# resulting path/slug/size; creating the MediaItem row is a separate
# POST /api/v1/media call with that file_path, mirroring how install-media
# also stops at the upload and never itself writes a DB row.
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_media_archive(
    file: UploadFile,
    _: User = require_permission("can_edit_media"),
):
    if not file.filename:
        raise HTTPException(status_code=422, detail="A filename is required.")

    from backend.core.settings import get_settings
    from backend.service.utils.upload_utils import DEFAULT_MAX_BYTES, begin_upload, stream_upload_to_disk

    svc = get_settings()
    max_bytes = int(svc.get("UPLOAD_MAX_BYTES", DEFAULT_MAX_BYTES) or DEFAULT_MAX_BYTES)
    media_root = Path(svc.get_env_var("MEDIA_PATH")).resolve()

    dest_dir, dest_path = begin_upload(media_root, file.filename)

    try:
        written = await stream_upload_to_disk(file, dest_path, max_bytes)
    except HTTPException:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    return {"path": str(dest_path), "slug": dest_dir.name, "size_bytes": written}
