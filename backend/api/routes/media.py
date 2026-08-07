import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

from backend.core.database import get_db
from backend.core.dependencies import (
    get_active_user, get_filtered_media_item, get_filtered_media_item_bundle,
    get_filtered_media_item_bundles, get_filtered_media_items, require_permission,
)
from backend.core.logger import get_logger
from backend.models.media import (
    MediaItemBundle, MediaItemBundleCreate, MediaItemBundleRead, MediaItemBundleUpdate,
    MediaItem, MediaItemCreate, MediaItemRead, MediaItemUpdate,
    delete_links_for, unique_media_slug, _linked_items_for,
    media_item_bundle_to_read, media_item_bundle_to_read_bulk, item_to_read, items_to_read_bulk,
)
from backend.models.pagination import Page
from backend.models.user import UserItem
from backend.service.utils.sort_utils import apply_bundle_sort

router = APIRouter(prefix="/api/v1", tags=["media"])
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Items, list + create
# ---------------------------------------------------------------------------


@router.get("/media-items", response_model=Page[MediaItemRead])
def list_media_items(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    q = get_filtered_media_items(active_user, db).order_by(MediaItem.id)
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return Page(items=items_to_read_bulk(rows, db), total=total, limit=limit, offset=offset)


@router.post("/media-items", response_model=MediaItemRead, status_code=201)
def create_media_item(
    body: MediaItemCreate,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_media"),
):
    # Every item gets a collection-of-one MediaItemBundle on creation when the
    # caller doesn't attach it to an existing one, mirroring App's
    # create_app_item_bundle (backend/service/apps/items.py): bundle first,
    # flush for its id, then the item referencing it. Without this the item
    # is never reachable from the library list, which only ever queries
    # GET /api/v1/media-item-bundles, not /media-items directly.
    # Reserve the item's own slug against the title first. The implicit
    # bundle below shares the same title but is a technical pairing, not a
    # second title claim, so it must not consume a slot in the item's
    # title/title-2/title-3 sequence, that sequence belongs to genuine
    # cross-table title collisions between distinct items/bundles.
    item_slug = unique_media_slug(body.title, db)

    bundle_id = body.media_item_bundle_id
    if bundle_id is None:
        bundle = MediaItemBundle(
            title=body.title,
            media_kind=body.media_kind,
            cover_art_path=body.cover_art_path,
            slug=unique_media_slug(f"{body.title} Collection", db),
        )
        db.add(bundle)
        db.flush()
        bundle_id = bundle.id

    item = MediaItem(
        **body.model_dump(exclude={"media_item_bundle_id"}),
        media_item_bundle_id=bundle_id,
        slug=item_slug,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item_to_read(item, db)


# ---------------------------------------------------------------------------
# Items, read / update / delete
# ---------------------------------------------------------------------------


@router.get("/media-item/{item_id}", response_model=MediaItemRead)
def get_media_item(
    item_id: int, db: Session = Depends(get_db), active_user: UserItem = Depends(get_active_user)
):
    return item_to_read(get_filtered_media_item(item_id, active_user, db), db)


@router.patch("/media-item/{item_id}", response_model=MediaItemRead)
def update_media_item(
    item_id: int,
    body: MediaItemUpdate,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_media"),
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


@router.delete("/media-item/{item_id}", status_code=204)
def delete_media_item(
    item_id: int,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_media"),
):
    item = db.get(MediaItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Media item not found.")
    delete_links_for("media_item", item_id, db)
    db.delete(item)
    db.commit()


# ---------------------------------------------------------------------------
# Collections, create / read / update / delete
# ---------------------------------------------------------------------------


@router.post("/media-item-bundles", response_model=MediaItemBundleRead, status_code=201)
def create_media_item_bundle(
    body: MediaItemBundleCreate,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_media"),
):
    collection = MediaItemBundle(**body.model_dump(), slug=unique_media_slug(body.title, db))
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return media_item_bundle_to_read(collection, db)


@router.get("/media-item-bundles", response_model=Page[MediaItemBundleRead])
def list_media_item_bundles(
    tag: str | None = None,
    sort: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    q = get_filtered_media_item_bundles(active_user, db)
    if tag:
        from backend.models.tag import EntityTag, Tag
        subq = (
            db.query(EntityTag.entity_id)
            .join(Tag, EntityTag.tag_id == Tag.id)
            .filter(EntityTag.entity_type == "media_item_bundle", Tag.name == tag)
            .subquery()
        )
        q = q.filter(MediaItemBundle.id.in_(subq))
    total = q.count()
    rows = apply_bundle_sort(q, MediaItemBundle, sort).offset(offset).limit(limit).all()
    return Page(items=media_item_bundle_to_read_bulk(rows, db), total=total, limit=limit, offset=offset)


@router.get("/media-item-bundle/{collection_id}", response_model=MediaItemBundleRead)
def get_media_item_bundle(
    collection_id: int, db: Session = Depends(get_db), active_user: UserItem = Depends(get_active_user)
):
    return media_item_bundle_to_read(get_filtered_media_item_bundle(collection_id, active_user, db), db)


@router.patch("/media-item-bundle/{collection_id}", response_model=MediaItemBundleRead)
def update_media_item_bundle(
    collection_id: int,
    body: MediaItemBundleUpdate,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_media"),
):
    collection = db.get(MediaItemBundle, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Media collection not found.")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(collection, key, value)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return media_item_bundle_to_read(collection, db)


class MediaCoverArtToGamesBody(SQLModel):
    file_path: str


@router.post("/media-item-bundle/{collection_id}/apply-cover-art-to-linked-games", response_model=list[int])
def apply_cover_art_to_linked_games(
    collection_id: int,
    body: MediaCoverArtToGamesBody,
    db: Session = Depends(get_db),
    _media: UserItem = require_permission("can_manage_media"),
    _game: UserItem = require_permission("can_manage_game"),
):
    """Reuse one of this media collection's files as cover art for every
    game_item_bundle linked to it via MediaLink. Additive to the existing
    Media-only "Set as cover art" action (PATCH /media-item-bundle/{id}),
    which this does not touch or replace.

    Applies to every linked game, not just one: MediaLink has no cardinality
    limit (backend/models/media.py), and there is no existing UI pattern in
    this codebase for picking one of several linked entities, so a single
    click here updates all of them rather than silently choosing one.

    Writes through the same leaf a game's cover art is actually displayed
    from (display_disk_id, falling back to launch_disk_id, falling back to
    the first disc by disc_number), matching resolveLeafCoverArt
    (frontend/src/pages/Software/types.ts) exactly. Writing any other leaf
    would be silently invisible, since nothing reads from it for display.
    """
    collection = db.get(MediaItemBundle, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Media collection not found.")
    if not any(item.file_path == body.file_path for item in collection.items):
        raise HTTPException(status_code=422, detail="file_path does not belong to this media item.")

    from backend.models.game import GameItemBundle, GameItemUpdate
    from backend.service.games.items import update_library_leaf

    linked_game_ids = [
        ref.entity_id for ref in _linked_items_for("media_item_bundle", collection_id, db)
        if ref.entity_type == "game_item_bundle"
    ]
    if not linked_game_ids:
        raise HTTPException(status_code=404, detail="This media item has no linked games.")

    updated: list[int] = []
    for game_id in linked_game_ids:
        bundle = db.get(GameItemBundle, game_id)
        if not bundle or not bundle.items:
            continue
        target_leaf_id = bundle.display_disk_id or bundle.launch_disk_id
        leaf = next((i for i in bundle.items if i.id == target_leaf_id), None) or bundle.items[0]
        update_library_leaf(game_id, leaf.id, GameItemUpdate(cover_art_path=body.file_path), db)
        updated.append(game_id)
    return updated


@router.delete("/media-item-bundle/{collection_id}", status_code=204)
def delete_media_item_bundle(
    collection_id: int,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_media"),
):
    collection = db.get(MediaItemBundle, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Media collection not found.")
    delete_links_for("media_item_bundle", collection_id, db)
    db.delete(collection)
    db.commit()


# ---------------------------------------------------------------------------
# Link / unlink routes moved to backend/api/routes/entity_links.py, see
# create_entity_link / delete_entity_link there. This domain's link surface
# is no longer Game-specific (MediaLink is now a polymorphic entity-to-entity
# join, see backend/models/media.py), so it no longer belongs to this file.
# ---------------------------------------------------------------------------
# Archive upload, reuses begin_upload/stream_upload_to_disk exactly as the
# relocated OS-install-media route does (backend/api/routes/environments.py).
# This endpoint only stages bytes on disk under MEDIA_PATH and returns the
# resulting path/slug/size; creating the MediaItem row is a separate
# POST /api/v1/media call with that file_path, mirroring how install-media
# also stops at the upload and never itself writes a DB row.
# ---------------------------------------------------------------------------


@router.post("/media-items/upload")
async def upload_media_archive(
    file: UploadFile,
    _: UserItem = require_permission("can_manage_media"),
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
