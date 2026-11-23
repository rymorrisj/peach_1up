from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from backend.core.logger import get_logger
from backend.models.game import GameItemBundle
from backend.service.media.rating_change_guard import RATING_CHANGE_ERROR_TYPE
from backend.service.metadata_providers import PROVIDER_LABELS, provider_key_for
from backend.service.metadata_providers.links import clean_provider_links, replace_provider_links

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_log = get_logger(__name__)

# Columns copied as-is. title is handled separately (never null) and
# content_rating, metadata_source, external_links and genre have their own rules.
_PLAIN_FIELDS = ("description", "publisher", "developer", "year", "external_game_id")


def _canonical_source(raw: str | None) -> str | None:
    """A recognised provider name or key stored as its display name, so the
    provider behind external_game_id can be read back reliably; anything
    else is stored as given."""
    key = provider_key_for(raw)
    return PROVIDER_LABELS[key] if key else raw


def enrich_game_bundle(
    entity_id: int,
    fields: dict[str, Any],
    *,
    confirm_rating_change: bool = False,
    db: "Session",
) -> GameItemBundle:
    """Apply the fetched metadata in *fields* to a game bundle.

    Only keys present in *fields* are touched; everything else stays as it
    is. A key present with a null value clears that field, except title,
    which is refused. external_links replaces only provider-sourced
    entries (links.replace_provider_links). A rating change that would
    lower, clear or change the scheme of a set rating needs
    confirm_rating_change, otherwise nothing at all is applied (409); a
    caller that wants the other fields without the rating leaves the
    content_rating key out. metadata_fetched_at is stamped only when a
    stored value actually changed (META-23).

    Raises:
        HTTPException: 404 if the bundle doesn't exist, 422 for a null
            title, 409 (structured detail) when the rating needs
            confirmation.
    """
    entity = db.get(GameItemBundle, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Software collection not found.")

    values: dict[str, Any] = {key: fields[key] for key in _PLAIN_FIELDS if key in fields}
    if "title" in fields:
        if not isinstance(fields["title"], str) or not fields["title"].strip():
            raise HTTPException(status_code=422, detail="title cannot be cleared.")
        values["title"] = fields["title"]
    if "metadata_source" in fields:
        values["metadata_source"] = _canonical_source(fields["metadata_source"])
    if "external_links" in fields:
        values["external_links"] = replace_provider_links(
            entity.external_links,
            clean_provider_links(fields["external_links"]),
        )
    if "content_rating" in fields:
        # Normalise free-form ratings (e.g. TheGamesDB "M - Mature 17+") onto
        # the known vocabulary. An unrecognised value is written as null rather
        # than stored verbatim, so it can never slip past the content-rating
        # filter as an unknown string.
        from backend.core.dependencies import normalize_content_rating, rating_change_reason

        new_rating = normalize_content_rating(fields["content_rating"])
        old_rating = entity.content_rating
        reason = rating_change_reason(old_rating, new_rating)
        if reason is not None:
            if not confirm_rating_change:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error_type": RATING_CHANGE_ERROR_TYPE,
                        "reason": reason,
                        "current_rating": old_rating,
                        "new_rating": new_rating,
                        "message": (
                            f"content_rating change from {old_rating!r} to {new_rating!r} would "
                            "lower, clear or change the scheme of an already-set rating. Re-submit "
                            "with confirm_rating_change=true to proceed, or leave content_rating out."
                        ),
                    },
                )
            _log.warning(
                "content_rating lowered/cleared on game_item_bundle id=%s: %r -> %r (confirmed by caller)",
                entity_id,
                old_rating,
                new_rating,
            )
        values["content_rating"] = new_rating

    changed = False
    for key, value in values.items():
        if getattr(entity, key) != value:
            setattr(entity, key, value)
            changed = True
    if "genre" in fields:
        from backend.models.metadata_lookup import (
            get_genres_for_game_item_bundle,
            set_genres_for_game_item_bundle,
        )

        names = list(dict.fromkeys(fields["genre"] or []))
        if sorted(get_genres_for_game_item_bundle(entity_id, db)) != sorted(names):
            # No provider hint here, metadata_source is a display string (e.g.
            # "TheGamesDB"), not the internal provider key genres are cached
            # under. Genre rows already exist by this point (created moments
            # earlier when get_metadata_details() resolved them), so this
            # matches purely by name; only a genre name that was never
            # resolved through a provider would fall through to a fresh
            # "manual"-provider row here.
            set_genres_for_game_item_bundle(db, entity_id, names)
            changed = True
    if changed:
        entity.metadata_fetched_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except BaseException:
        db.rollback()
        raise
    db.refresh(entity)
    return entity
