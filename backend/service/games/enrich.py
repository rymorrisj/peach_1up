from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional

from fastapi import HTTPException

from backend.core.logger import get_logger
from backend.models.game import GameItemBundle, GameItem
from backend.service.utils.asset_fetch import download_remote_image

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_log = get_logger(__name__)


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
    }.items() if v is not None}

    if content_rating is not None:
        # Normalise free-form ratings (e.g. TheGamesDB "M - Mature 17+") onto
        # the known vocabulary. An unrecognised value is written as null rather
        # than stored verbatim, so it can never slip past the content-rating
        # filter as an unknown string. content_rating=None means "leave as-is".
        from backend.core.dependencies import normalize_content_rating
        metadata_fields["content_rating"] = normalize_content_rating(content_rating)

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
        for key, value in metadata_fields.items():
            setattr(entity, key, value)
        if metadata_fields or genre is not None:
            entity.metadata_fetched_at = datetime.now(timezone.utc)
        if genre is not None:
            from backend.models.metadata_lookup import set_genres_for_game_item_bundle
            # No provider hint here — metadata_source is a display string (e.g.
            # "TheGamesDB"), not the internal provider key genres are cached
            # under. Genre rows already exist by this point (created moments
            # earlier when get_metadata_details() resolved them), so this
            # matches purely by name; only a genre name that was never
            # resolved through a provider would fall through to a fresh
            # "manual"-provider row here.
            set_genres_for_game_item_bundle(db, entity_id, genre)

    elif entity_type == "game_item":
        # Leaf: per-disc cover art only — no metadata fields (those go on the collection).
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
            dest_dir = Path(entity.folder_path) if entity.folder_path else Path(entity.file_path).parent
            entity.cover_art_path = str(download_remote_image(cover_art_url, dest_dir))
            entity.metadata_fetched_at = datetime.now(timezone.utc)

    else:
        raise HTTPException(status_code=422, detail=f"Invalid entity_type: {entity_type!r}")

    db.commit()
    db.refresh(entity)
    return entity, entity_type
