"""Media item and bundle delete (MED-17).

Mirrors game delete's delete_media handling: the caller's per-delete choice
wins, else the global delete_media_on_removal setting. When files are to be
removed, only app-owned files no other row uses are removed
(file_cleanup.removable_media_files), every cover pointing at them is
cleared in the same transaction, and the unlink happens after the commit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

from backend.service.media.file_cleanup import (
    clear_cover_references, path_variants, removable_media_files, remove_files,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.models.media import MediaItem, MediaItemBundle


class MediaDeletePreview(BaseModel):
    """What a delete with files removed would do, for the confirm dialog."""
    file_count: int
    removable_file_count: int
    game_cover_count: int
    app_cover_count: int
    media_cover_count: int


def should_delete_media(delete_media: Optional[bool]) -> bool:
    if delete_media is not None:
        return delete_media
    from backend.core.settings import get_settings
    return bool(get_settings().get("delete_media_on_removal", False))


def _scope(item: Optional["MediaItem"], bundle: Optional["MediaItemBundle"]) -> list["MediaItem"]:
    return list(bundle.items) if bundle is not None else [item]


def delete_preview(
    db: "Session", *, item: Optional["MediaItem"] = None, bundle: Optional["MediaItemBundle"] = None,
) -> MediaDeletePreview:
    from backend.models.app import AppItem
    from backend.models.game import GameItem
    from backend.models.media import MediaItem, MediaItemBundle

    items = _scope(item, bundle)
    ids = {i.id for i in items}
    paths = {i.file_path for i in items if i.file_path}
    removable = removable_media_files(paths, ids, db)
    variants: set[str] = set()
    for raw in removable:
        variants |= path_variants(raw)
    game_covers = app_covers = media_covers = 0
    if variants:
        game_covers = db.query(GameItem.id).filter(GameItem.cover_art_path.in_(variants)).count()
        app_covers = db.query(AppItem.id).filter(AppItem.cover_art_path.in_(variants)).count()
        bundle_q = db.query(MediaItemBundle.id).filter(MediaItemBundle.cover_art_path.in_(variants))
        if bundle is not None:
            bundle_q = bundle_q.filter(MediaItemBundle.id != bundle.id)
        item_q = db.query(MediaItem.id).filter(MediaItem.cover_art_path.in_(variants), MediaItem.id.notin_(ids))
        media_covers = bundle_q.count() + item_q.count()
    return MediaDeletePreview(
        file_count=len(paths),
        removable_file_count=len(removable),
        game_cover_count=game_covers,
        app_cover_count=app_covers,
        media_cover_count=media_covers,
    )


def delete_media_entity(
    db: "Session",
    *,
    item: Optional["MediaItem"] = None,
    bundle: Optional["MediaItemBundle"] = None,
    delete_files: bool,
) -> list[str]:
    """Delete one item or one bundle (with its items) and its MediaLink
    rows in one commit; with *delete_files*, also clear covers that point at
    the removed files and unlink them after the commit. Returns the paths
    actually removed."""
    from backend.models.media import delete_links_for

    items = _scope(item, bundle)
    ids = {i.id for i in items}
    doomed = removable_media_files([i.file_path for i in items], ids, db) if delete_files else []
    try:
        if doomed:
            clear_cover_references(doomed, db)
        for i in items:
            delete_links_for("media_item", i.id, db)
        if bundle is not None:
            delete_links_for("media_item_bundle", bundle.id, db)
            db.delete(bundle)
        else:
            db.delete(item)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return remove_files(doomed, db)
