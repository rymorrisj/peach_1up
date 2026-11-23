import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

from backend.core.database import get_db
from backend.core.dependencies import (
    get_active_user,
    get_filtered_media_item,
    get_filtered_media_item_bundle,
    get_filtered_media_item_bundles,
    get_filtered_media_items,
    normalize_content_rating,
    require_permission,
)
from backend.constants_generated import MediaKind
from backend.core.logger import get_logger
from backend.models.media import (
    MediaItemBundle,
    MediaItemBundleCreate,
    MediaItemBundleRead,
    MediaItemBundleUpdate,
    MediaItem,
    MediaItemCreate,
    MediaItemRead,
    MediaItemUpdate,
    unique_media_slug,
    _linked_items_for,
    media_item_bundle_to_read,
    media_item_bundle_to_read_bulk,
    item_to_read,
    items_to_read_bulk,
)
from backend.models.pagination import Page
from backend.models.user import UserItem
from backend.service.media.content_rating import checked_media_rating_change
from backend.service.media.delete import MediaDeletePreview, delete_media_entity, delete_preview, should_delete_media
from backend.service.media.rating_change_guard import item_move_effects, require_rating_change_confirmation
from backend.service.utils.media_extensions import INLINE_IMAGE_TYPES, check_media_extension
from backend.service.utils.path_utils import media_root, normalise_path
from backend.service.utils.sort_utils import apply_bundle_sort

router = APIRouter(prefix="/api/v1", tags=["media"])
logger = get_logger(__name__)


def _media_root() -> Path:
    """MEDIA_PATH resolved, or 503 when it is unset or blank (never the
    working directory)."""
    try:
        return media_root()
    except ValueError, RuntimeError:
        raise HTTPException(status_code=503, detail="MEDIA_PATH is not configured.")


def _confined_to_media_root(raw: str, field: str) -> Path:
    """Canonicalise a client-supplied path with normalise_path (no null
    byte, UNC, device or drive-relative form) and confine it to MEDIA_PATH.
    The one confinement rule behind cover_art_path and file_path.

    Raises:
        HTTPException: 400 on any rejection (logged), 503 if MEDIA_PATH is
            not configured.
    """
    root = _media_root()
    try:
        resolved = normalise_path(raw)
    except ValueError as exc:
        logger.warning("Rejected media %s %r: %s", field, raw, exc)
        raise HTTPException(status_code=400, detail=f"{field}: {exc}")
    if not resolved.is_relative_to(root):
        logger.warning("Rejected media %s %r: resolves outside MEDIA_PATH (%s)", field, raw, resolved)
        raise HTTPException(status_code=400, detail=f"{field} must be inside the media library (MEDIA_PATH).")
    return resolved


def _validated_media_file_path(raw: str) -> str:
    """Canonical MediaItem.file_path, confined to MEDIA_PATH. Runs on item
    create, the only route that writes this column from request input
    (MediaItemUpdate has no file_path). Existence is not checked: the
    upload routes stage the file first and return this path."""
    return str(_confined_to_media_root(raw, "file_path"))


def _validated_cover_art_path(raw: Optional[str]) -> Optional[str]:
    """Canonicalise a client-supplied cover_art_path and confine it to
    MEDIA_PATH (MED-3). Runs on item and bundle create and PATCH, the only
    routes that write this column from request input.

    None or blank clears the cover. Anything else must normalise cleanly
    (no null byte, UNC, device or drive-relative form), resolve inside
    MEDIA_PATH, be an existing file, and be an inline-servable image, since
    it is only ever rendered as an <img> from /media.

    Raises:
        HTTPException: 400 on any rejection (logged), 503 if MEDIA_PATH is
            not configured.
    """
    if raw is None or not raw.strip():
        return None
    resolved = _confined_to_media_root(raw, "cover_art_path")
    if resolved.suffix.lower() not in INLINE_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="cover_art_path must be a png, jpg, gif, webp, bmp or avif image.")
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"cover_art_path does not exist: {resolved}")
    return str(resolved)


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
    return Page(items=items_to_read_bulk(rows, db, viewer=active_user), total=total, limit=limit, offset=offset)


@router.post("/media-items", response_model=MediaItemRead, status_code=201)
def create_media_item(
    body: MediaItemCreate,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_media"),
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
    try:
        check_media_extension(body.file_path, body.media_kind)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    cover_art_path = _validated_cover_art_path(body.cover_art_path)
    file_path = _validated_media_file_path(body.file_path)
    item_slug = unique_media_slug(body.title, db)

    bundle_id = body.media_item_bundle_id
    if bundle_id is not None:
        # Same 404 as a missing bundle, so a hidden bundle can be neither
        # attached to nor confirmed to exist.
        get_filtered_media_item_bundle(bundle_id, active_user, db)
    else:
        bundle = MediaItemBundle(
            title=body.title,
            media_kind=body.media_kind,
            cover_art_path=cover_art_path,
            slug=unique_media_slug(f"{body.title} Collection", db),
        )
        db.add(bundle)
        db.flush()
        bundle_id = bundle.id

    item = MediaItem(
        **body.model_dump(exclude={"media_item_bundle_id", "cover_art_path", "file_path"}),
        file_path=file_path,
        cover_art_path=cover_art_path,
        media_item_bundle_id=bundle_id,
        slug=item_slug,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item_to_read(item, db, viewer=active_user)


# ---------------------------------------------------------------------------
# Items, read / update / delete
# ---------------------------------------------------------------------------


@router.get("/media-item/{item_id}", response_model=MediaItemRead)
def get_media_item(item_id: int, db: Session = Depends(get_db), active_user: UserItem = Depends(get_active_user)):
    return item_to_read(get_filtered_media_item(item_id, active_user, db), db, viewer=active_user)


@router.patch("/media-item/{item_id}", response_model=MediaItemRead)
def update_media_item(
    item_id: int,
    body: MediaItemUpdate,
    confirm_rating_change: bool = Query(False),
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_media"),
):
    # Visibility filter first: a hidden item, or a hidden target bundle,
    # returns the same 404 as a missing one.
    item = get_filtered_media_item(item_id, active_user, db)
    fields = body.model_dump(exclude_unset=True)
    if fields.get("media_item_bundle_id") is not None:
        get_filtered_media_item_bundle(fields["media_item_bundle_id"], active_user, db)
    if "media_item_bundle_id" in fields:
        # Moving the item (into another bundle, or out to standalone with
        # null) switches which rating it is judged by.
        require_rating_change_confirmation(
            item_move_effects(item, fields["media_item_bundle_id"], db),
            confirm_rating_change=confirm_rating_change,
            action="media item move",
        )
    if "cover_art_path" in fields:
        fields["cover_art_path"] = _validated_cover_art_path(fields["cover_art_path"])
    for key, value in fields.items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item_to_read(item, db, viewer=active_user)


def _check_delete_token(token: Optional[str], resource: str, resource_id: int) -> None:
    """Every media delete needs a confirmation token from its confirm-delete
    endpoint, the two-step rule for destructive operations (SECURITY.md).

    Raises:
        HTTPException: 400 on a missing or invalid token.
    """
    from backend.service.utils import confirmation_tokens

    if token is None:
        raise HTTPException(
            status_code=400,
            detail="Deleting media needs a confirmation token from the confirm-delete endpoint.",
        )
    if not confirmation_tokens.consume(token, resource, resource_id):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")


def _log_media_delete(user: UserItem, resource: str, resource_id: int, removed: list[str]) -> None:
    logger.info(
        "Destructive operation: user %s deleted %s %s, %d file(s) removed from disk",
        user.id,
        resource,
        resource_id,
        len(removed),
    )


def _confirm_delete_response(resource: str, resource_id: int) -> dict:
    from backend.service.utils import confirmation_tokens

    token = confirmation_tokens.issue(resource, resource_id)
    return {"confirmation_token": token, "expires_in_seconds": confirmation_tokens.TOKEN_TTL}


@router.post("/media-item/{item_id}/confirm-delete")
def confirm_delete_media_item(
    item_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_media"),
):
    get_filtered_media_item(item_id, active_user, db)
    return _confirm_delete_response("media_item", item_id)


@router.get("/media-item/{item_id}/delete-preview", response_model=MediaDeletePreview)
def preview_delete_media_item(
    item_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_media"),
):
    return delete_preview(db, item=get_filtered_media_item(item_id, active_user, db))


@router.delete("/media-item/{item_id}", status_code=204)
def delete_media_item(
    item_id: int,
    confirmation_token: Optional[str] = Query(None),
    delete_media: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_media"),
):
    """*delete_media*, when given, is the confirm dialog's choice for this
    delete only; omitted, the global delete_media_on_removal setting applies.
    *confirmation_token* is required (400 without a valid one)."""
    # Same 404 as a missing item, so a hidden item is neither deletable nor
    # confirmed to exist.
    item = get_filtered_media_item(item_id, active_user, db)
    _check_delete_token(confirmation_token, "media_item", item_id)
    removed = delete_media_entity(db, item=item, delete_files=should_delete_media(delete_media))
    _log_media_delete(active_user, "media_item", item_id, removed)


# ---------------------------------------------------------------------------
# Collections, create / read / update / delete
# ---------------------------------------------------------------------------


@router.post("/media-item-bundles", response_model=MediaItemBundleRead, status_code=201)
def create_media_item_bundle(
    body: MediaItemBundleCreate,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_media"),
):
    # A new bundle has no links yet, so its own rating always applies and
    # null to rated needs no confirmation. Same normaliser as games.
    collection = MediaItemBundle(
        **body.model_dump(exclude={"cover_art_path", "content_rating"}),
        cover_art_path=_validated_cover_art_path(body.cover_art_path),
        content_rating=normalize_content_rating(body.content_rating),
        slug=unique_media_slug(body.title, db),
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return media_item_bundle_to_read(collection, db, viewer=active_user)


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
    return Page(
        items=media_item_bundle_to_read_bulk(rows, db, viewer=active_user), total=total, limit=limit, offset=offset
    )


@router.get("/media-item-bundle/{collection_id}", response_model=MediaItemBundleRead)
def get_media_item_bundle(
    collection_id: int, db: Session = Depends(get_db), active_user: UserItem = Depends(get_active_user)
):
    return media_item_bundle_to_read(
        get_filtered_media_item_bundle(collection_id, active_user, db),
        db,
        viewer=active_user,
    )


@router.patch("/media-item-bundle/{collection_id}", response_model=MediaItemBundleRead)
def update_media_item_bundle(
    collection_id: int,
    body: MediaItemBundleUpdate,
    confirm_rating_change: bool = Query(False),
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_media"),
):
    # Same 404 as a missing bundle, so a hidden bundle is neither patchable
    # nor confirmed to exist (mirrors update_game_item_bundle).
    collection = get_filtered_media_item_bundle(collection_id, active_user, db)
    fields = body.model_dump(exclude_unset=True)
    if "cover_art_path" in fields:
        fields["cover_art_path"] = _validated_cover_art_path(fields["cover_art_path"])
    if "content_rating" in fields:
        fields["content_rating"] = checked_media_rating_change(
            collection,
            fields["content_rating"],
            confirm_rating_change=confirm_rating_change,
            db=db,
        )
    for key, value in fields.items():
        setattr(collection, key, value)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return media_item_bundle_to_read(collection, db, viewer=active_user)


class MediaCoverArtToGamesBody(SQLModel):
    file_path: str


@router.post("/media-item-bundle/{collection_id}/apply-cover-art-to-linked-games", response_model=list[int])
def apply_cover_art_to_linked_games(
    collection_id: int,
    body: MediaCoverArtToGamesBody,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_media"),
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
    collection = get_filtered_media_item_bundle(collection_id, active_user, db)
    if not any(item.file_path == body.file_path for item in collection.items):
        raise HTTPException(status_code=422, detail="file_path does not belong to this media item.")

    from backend.models.game import GameItemBundle
    from backend.service.games.leaf_covers import effective_display_leaf, require_cover_in_library

    linked_game_ids = [
        ref.entity_id
        for ref in _linked_items_for("media_item_bundle", collection_id, db, viewer=active_user)
        if ref.entity_type == "game_item_bundle"
    ]
    if not linked_game_ids:
        raise HTTPException(status_code=404, detail="This media item has no linked games.")

    # Same normalise and existence check update_library_leaf applies to
    # cover_art_path, done once; then every game in one commit (MED-18).
    try:
        cover_path = normalise_path(body.file_path)
    except ValueError as exc:
        logger.warning("Rejected cover_art_path %r: %s", body.file_path, exc)
        raise HTTPException(status_code=400, detail="cover_art_path is not a valid path.") from None
    require_cover_in_library(cover_path, body.file_path)
    if not cover_path.exists():
        logger.warning("Rejected cover_art_path %r: does not exist", body.file_path)
        raise HTTPException(status_code=400, detail="cover_art_path does not exist.")

    updated: list[int] = []
    try:
        for game_id in linked_game_ids:
            bundle = db.get(GameItemBundle, game_id)
            leaf = effective_display_leaf(bundle) if bundle else None
            if leaf is None:
                continue
            leaf.cover_art_path = str(cover_path)
            updated.append(game_id)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return updated


@router.post("/media-item-bundle/{collection_id}/confirm-delete")
def confirm_delete_media_item_bundle(
    collection_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_media"),
):
    get_filtered_media_item_bundle(collection_id, active_user, db)
    return _confirm_delete_response("media_item_bundle", collection_id)


@router.get("/media-item-bundle/{collection_id}/delete-preview", response_model=MediaDeletePreview)
def preview_delete_media_item_bundle(
    collection_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_media"),
):
    return delete_preview(db, bundle=get_filtered_media_item_bundle(collection_id, active_user, db))


@router.delete("/media-item-bundle/{collection_id}", status_code=204)
def delete_media_item_bundle(
    collection_id: int,
    confirmation_token: Optional[str] = Query(None),
    delete_media: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_media"),
):
    """Same delete_media and confirmation_token rules as delete_media_item.
    Also drops every item's MediaLink rows, not just the bundle's."""
    collection = get_filtered_media_item_bundle(collection_id, active_user, db)
    _check_delete_token(confirmation_token, "media_item_bundle", collection_id)
    removed = delete_media_entity(db, bundle=collection, delete_files=should_delete_media(delete_media))
    _log_media_delete(active_user, "media_item_bundle", collection_id, removed)


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
    media_kind: Optional[MediaKind] = Query(default=None),
    _: UserItem = require_permission("can_manage_media"),
):
    if not file.filename:
        raise HTTPException(status_code=422, detail="A filename is required.")
    # Extension allowlist (MED-11): *media_kind*'s set when the caller names
    # one, else the union over every kind. POST /media-items re-checks the
    # stored file_path against the item's actual kind.
    try:
        check_media_extension(file.filename, media_kind)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    from backend.core.settings import get_settings
    from backend.service.utils.upload_utils import DEFAULT_MAX_BYTES, begin_upload, stream_upload_to_disk

    svc = get_settings()
    max_bytes = int(svc.get("UPLOAD_MAX_BYTES", DEFAULT_MAX_BYTES) or DEFAULT_MAX_BYTES)
    dest_dir, dest_path = begin_upload(_media_root(), file.filename)

    try:
        written = await stream_upload_to_disk(file, dest_path, max_bytes)
    except HTTPException:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    return {"path": str(dest_path), "slug": dest_dir.name, "size_bytes": written}
