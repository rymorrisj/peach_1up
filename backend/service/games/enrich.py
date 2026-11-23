from __future__ import annotations

import filecmp
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional

from fastapi import HTTPException

from backend.core.logger import get_logger
from backend.models.game import GameItemBundle, GameItem
from backend.service.games.media_link import single_apply
from backend.service.utils.asset_fetch import commit_temp_image, fetch_image_to_temp, final_image_path

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_log = get_logger(__name__)


def _fetch_leaf_cover(entity: GameItem, cover_art_url: str) -> tuple[Optional[Path], bool]:
    """Fetch this leaf's cover into its app-owned path (leaf_covers.py).

    Returns (dest, created): dest is None when the fetched bytes equal the
    leaf's current cover file, so nothing changed; created is True when dest
    did not exist before, so a failed commit can remove it.

    Raises:
        HTTPException: 503 if MEDIA_PATH is not configured, else as
            fetch_image_to_temp / final_image_path.
    """
    from backend.service.games.leaf_covers import app_owned_leaf_cover, leaf_cover_stem
    from backend.service.utils.path_utils import asset_staging_root, game_covers_root

    try:
        covers_dir = game_covers_root()
        staging = asset_staging_root()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="MEDIA_PATH is not configured.") from exc

    tmp, ext = fetch_image_to_temp(cover_art_url, staging)
    try:
        dest = final_image_path(covers_dir, leaf_cover_stem(entity.id), ext)
        current = app_owned_leaf_cover(entity.cover_art_path, entity.id)
        if current == dest and dest.is_file() and filecmp.cmp(tmp, dest, shallow=False):
            return None, False
        created = not dest.exists()
        # overwrite=True: dest is this leaf's own app-owned file.
        commit_temp_image(tmp, dest, overwrite=True)
        return dest, created
    finally:
        tmp.unlink(missing_ok=True)


def enrich_entity(
    entity_type: Literal["game_item_bundle", "game_item"],
    entity_id: int,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    publisher: Optional[str] = None,
    developer: Optional[str] = None,
    genre: Optional[list[str]] = None,
    year: Optional[int] = None,
    content_rating: Optional[str] = None,
    metadata_source: Optional[str] = None,
    cover_art_url: Optional[str] = None,
    external_links: Optional[list[dict]] = None,
    external_game_id: Optional[int] = None,
    confirm_rating_change: bool = False,
    db: "Session",
) -> tuple:
    """Apply fetched metadata. metadata_fetched_at is stamped only when a
    stored value actually changed (META-23). A per-disc cover re-fetch holds
    the same in-process lock Accept All uses, keyed by disc, so two
    concurrent re-fetches of one disc return 409 instead of racing on its
    cover file."""
    fields = dict(
        title=title, description=description, publisher=publisher, developer=developer,
        genre=genre, year=year, content_rating=content_rating, metadata_source=metadata_source,
        cover_art_url=cover_art_url, external_links=external_links,
        external_game_id=external_game_id,
        confirm_rating_change=confirm_rating_change, db=db,
    )
    if entity_type == "game_item" and cover_art_url:
        with single_apply(
            ("game_item_cover", entity_id),
            detail="A cover re-fetch for this disc is already running. Wait for it to finish.",
        ):
            return _enrich_entity(entity_type, entity_id, **fields)
    return _enrich_entity(entity_type, entity_id, **fields)


def _enrich_entity(
    entity_type: Literal["game_item_bundle", "game_item"],
    entity_id: int,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    publisher: Optional[str] = None,
    developer: Optional[str] = None,
    genre: Optional[list[str]] = None,
    year: Optional[int] = None,
    content_rating: Optional[str] = None,
    metadata_source: Optional[str] = None,
    cover_art_url: Optional[str] = None,
    external_links: Optional[list[dict]] = None,
    external_game_id: Optional[int] = None,
    confirm_rating_change: bool = False,
    db: "Session",
) -> tuple:
    metadata_fields = {k: v for k, v in {
        "title": title,
        "description": description,
        "publisher": publisher,
        "developer": developer,
        "year": year,
        "metadata_source": metadata_source,
        "external_links": external_links,
        "external_game_id": external_game_id,
    }.items() if v is not None}

    if content_rating is not None:
        # Normalise free-form ratings (e.g. TheGamesDB "M - Mature 17+") onto
        # the known vocabulary. An unrecognised value is written as null rather
        # than stored verbatim, so it can never slip past the content-rating
        # filter as an unknown string. content_rating=None means "leave as-is".
        from backend.core.dependencies import normalize_content_rating
        metadata_fields["content_rating"] = normalize_content_rating(content_rating)

    new_cover: Optional[Path] = None
    new_cover_created = False
    stale_cover: Optional[str] = None

    if entity_type == "game_item_bundle":
        # Metadata lives on the collection; cover art belongs on the individual leaves.
        entity = db.get(GameItemBundle, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Software collection not found.")
        if cover_art_url:
            raise HTTPException(
                status_code=422,
                detail=(
                    "cover_art_url is not supported for game_item_bundle; "
                    "apply cover art to individual game_item discs instead."
                ),
            )
        if "content_rating" in metadata_fields:
            from backend.core.dependencies import rating_change_requires_confirmation
            new_rating = metadata_fields["content_rating"]
            old_rating = entity.content_rating
            if rating_change_requires_confirmation(old_rating, new_rating):
                if not confirm_rating_change:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"content_rating change from {old_rating!r} to {new_rating!r} would "
                            "lower or clear an already-set rating. Re-submit with "
                            "confirm_rating_change=true to proceed."
                        ),
                    )
                _log.warning(
                    "content_rating lowered/cleared on game_item_bundle id=%s: %r -> %r "
                    "(confirmed by caller)",
                    entity_id, old_rating, new_rating,
                )
        changed = False
        for key, value in metadata_fields.items():
            if getattr(entity, key) != value:
                setattr(entity, key, value)
                changed = True
        if genre is not None:
            from backend.models.metadata_lookup import (
                get_genres_for_game_item_bundle, set_genres_for_game_item_bundle,
            )
            if sorted(get_genres_for_game_item_bundle(entity_id, db)) != sorted(set(genre)):
                # No provider hint here, metadata_source is a display string (e.g.
                # "TheGamesDB"), not the internal provider key genres are cached
                # under. Genre rows already exist by this point (created moments
                # earlier when get_metadata_details() resolved them), so this
                # matches purely by name; only a genre name that was never
                # resolved through a provider would fall through to a fresh
                # "manual"-provider row here.
                set_genres_for_game_item_bundle(db, entity_id, list(dict.fromkeys(genre)))
                changed = True
        if changed:
            entity.metadata_fetched_at = datetime.now(timezone.utc)

    elif entity_type == "game_item":
        # Leaf: per-disc cover art only, no metadata fields (those go on the collection).
        entity = db.get(GameItem, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Software item not found.")
        if metadata_fields or genre is not None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "game_item does not support metadata fields (title, description, etc.); "
                    "apply those to the parent game_item_bundle."
                ),
            )
        if cover_art_url:
            new_cover, new_cover_created = _fetch_leaf_cover(entity, cover_art_url)
            if new_cover is not None:
                stale_cover = entity.cover_art_path
                entity.cover_art_path = str(new_cover)
                entity.metadata_fetched_at = datetime.now(timezone.utc)

    else:
        raise HTTPException(status_code=422, detail=f"Invalid entity_type: {entity_type!r}")

    try:
        db.commit()
    except BaseException:
        db.rollback()
        if new_cover is not None and new_cover_created:
            new_cover.unlink(missing_ok=True)
        raise
    if new_cover is not None and stale_cover:
        from backend.service.games.leaf_covers import app_owned_leaf_cover, remove_app_owned_leaf_covers

        stale = app_owned_leaf_cover(stale_cover, entity_id)
        if stale is not None and stale != new_cover:
            remove_app_owned_leaf_covers([(entity_id, stale_cover)], db)
    db.refresh(entity)
    return entity, entity_type
