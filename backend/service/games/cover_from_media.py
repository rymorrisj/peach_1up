"""Use a linked Media image as a game's cover art.

Candidates are the image items of every media item or media bundle linked
to the game, narrowed by the caller's own visibility (get_filtered_media_items,
which applies the blocklist and media_rating_visible). A missing, hidden,
unlinked or non-image id is one and the same "not found", so nothing here
can be used to probe for media the caller may not see.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy import or_

from backend.core.dependencies import get_filtered_media_items
from backend.models.media import MediaItem, MediaItemRead, _linked_items_for
from backend.service.games.leaf_covers import effective_display_leaf, require_cover_in_library
from backend.service.media.file_cleanup import path_keys
from backend.service.utils.media_extensions import INLINE_IMAGE_TYPES
from backend.service.utils.path_utils import normalise_path

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.models.game import GameItem, GameItemBundle
    from backend.models.user import UserItem

_NOT_FOUND = "Media item not found."


def linked_image_items(game_id: int, viewer: "UserItem", db: "Session") -> list[MediaItemRead]:
    """Image items linked to *game_id* directly or through a linked media
    bundle, that *viewer* may see and whose file resolves to a /media URL."""
    refs = _linked_items_for("game_item_bundle", game_id, db, viewer=viewer)
    item_ids = {r.entity_id for r in refs if r.entity_type == "media_item"}
    bundle_ids = {r.entity_id for r in refs if r.entity_type == "media_item_bundle"}
    if not item_ids and not bundle_ids:
        return []
    rows = (
        get_filtered_media_items(viewer, db)
        .filter(
            MediaItem.media_kind == "image",
            or_(MediaItem.id.in_(item_ids), MediaItem.media_item_bundle_id.in_(bundle_ids)),
        )
        .order_by(MediaItem.media_item_bundle_id, MediaItem.sort_index, MediaItem.id)
        .all()
    )
    reads = [MediaItemRead.model_validate(row) for row in rows]
    return [read for read in reads if read.file_url is not None]


def current_cover_matches(game: "GameItemBundle", item: MediaItemRead) -> bool:
    leaf = effective_display_leaf(game)
    if leaf is None or not leaf.cover_art_path:
        return False
    return bool(path_keys(item.file_path) & path_keys(leaf.cover_art_path))


def set_cover_from_media_item(
    game: "GameItemBundle", media_item_id: int, viewer: "UserItem", db: "Session"
) -> "GameItem":
    """Write the item's file to the game's effective display disc."""
    item = next((i for i in linked_image_items(game.id, viewer, db) if i.id == media_item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    leaf = effective_display_leaf(game)
    if leaf is None:
        raise HTTPException(status_code=422, detail="This game has no discs.")
    try:
        resolved = normalise_path(item.file_path)
    except ValueError:
        raise HTTPException(status_code=422, detail="This media file cannot be used as cover art.") from None
    require_cover_in_library(resolved, item.file_path)
    if resolved.suffix.lower() not in INLINE_IMAGE_TYPES or not resolved.is_file():
        raise HTTPException(status_code=422, detail="This media file cannot be used as cover art.")
    leaf.cover_art_path = str(resolved)
    db.commit()
    db.refresh(leaf)
    return leaf
