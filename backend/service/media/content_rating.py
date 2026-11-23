"""Media content-rating rules (MED-8).

A media bundle linked to software inherits its visibility from that
software: it is visible to a non-owner only when EVERY linked game passes
that user's rating and unrated filter. A bundle with no linked game is
judged on its own ``content_rating`` through the same predicate. Both
branches reuse content_rating_visible (backend/core/dependencies.py), the
single rating predicate games already use, so the two domains cannot drift.

Only links whose game row still exists count as "linked". A stale link
(should not happen, see delete_links_for in backend/models/media.py) is
ignored, so the bundle falls back to its own rating rather than to an
empty, always-passing set of linked games.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import and_, not_, or_, select

from backend.core.dependencies import (
    _load_rating_ordinals,
    content_rating_visible,
    normalize_content_rating,
    rating_change_requires_confirmation,
)
from backend.core.logger import get_logger
from backend.models.game import GameItemBundle
from backend.models.media import MediaLink

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.models.media import MediaItemBundle
    from backend.models.user import UserItem

_GAME = "game_item_bundle"
_log = get_logger(__name__)


def _game_link_condition(entity_type: str, media_id_matches: Callable):
    """Join condition from MediaLink to the GameItemBundle on its other side,
    for links whose media side is *entity_type* and whose media id satisfies
    *media_id_matches*. Checks both columns: make_entity_link's canonical
    ordering puts the game on side a today, but readers never rely on it
    (same convention as _linked_items_for_many)."""
    return or_(
        and_(
            MediaLink.entity_a_type == _GAME,
            MediaLink.entity_a_id == GameItemBundle.id,
            MediaLink.entity_b_type == entity_type,
            media_id_matches(MediaLink.entity_b_id),
        ),
        and_(
            MediaLink.entity_b_type == _GAME,
            MediaLink.entity_b_id == GameItemBundle.id,
            MediaLink.entity_a_type == entity_type,
            media_id_matches(MediaLink.entity_a_id),
        ),
    )


def _linked_games_select(entity_type: str, id_column):
    """Correlated select of the existing games linked to the outer row whose
    id is *id_column*."""
    return (
        select(GameItemBundle.id)
        .select_from(MediaLink)
        .join(GameItemBundle, _game_link_condition(entity_type, lambda col: col == id_column))
    )


def media_rating_visible(entity_type: str, id_column, own_rating_column, active_user: "UserItem"):
    """SQL predicate for the effective-rating rule, evaluated per outer row
    of *id_column* as two correlated EXISTS subqueries (no per-row Python,
    no N+1). Owner bypass is the caller's responsibility.

    Linked: no linked game may fail content_rating_visible. Unlinked:
    *own_rating_column* must pass it. An unresolvable ceiling or an unknown
    rating fails closed exactly as it does for games, since the predicate
    is the same one.
    """
    linked = _linked_games_select(entity_type, id_column)
    has_game = linked.exists()
    has_failing_game = linked.where(not_(content_rating_visible(GameItemBundle.content_rating, active_user))).exists()
    return or_(
        and_(has_game, not_(has_failing_game)),
        and_(not_(has_game), content_rating_visible(own_rating_column, active_user)),
    )


def has_linked_game(entity_type: str, entity_id: int, db: "Session") -> bool:
    """True when (*entity_type*, *entity_id*) is linked to at least one
    existing game, the same "linked" test media_rating_visible applies."""
    from sqlalchemy import literal

    stmt = _linked_games_select(entity_type, literal(entity_id)).exists()
    return bool(db.execute(select(stmt)).scalar())


def linked_games_by_media(
    entity_type: str, entity_ids: list[int], db: "Session"
) -> dict[int, dict[int, Optional[str]]]:
    """{media id: {linked game id: that game's content_rating}} in one query.
    Ids with no existing linked game are absent. "" is reported as None,
    the same unrated value the visibility filter treats it as."""
    if not entity_ids:
        return {}
    id_set = set(entity_ids)
    rows = db.execute(
        select(
            MediaLink.entity_a_type,
            MediaLink.entity_a_id,
            MediaLink.entity_b_id,
            GameItemBundle.id,
            GameItemBundle.content_rating,
        )
        .select_from(MediaLink)
        .join(GameItemBundle, _game_link_condition(entity_type, lambda col: col.in_(id_set)))
    ).all()
    result: dict[int, dict[int, Optional[str]]] = {}
    for a_type, a_id, b_id, game_id, rating in rows:
        media_id = a_id if a_type == entity_type else b_id
        result.setdefault(media_id, {})[game_id] = rating or None
    return result


def linked_game_ratings(entity_type: str, entity_ids: list[int], db: "Session") -> dict[int, list[Optional[str]]]:
    """Every linked game's content_rating per media id, in one query. Ids
    with no linked game are absent. Used for display only, never for the
    visibility decision, which stays in SQL (media_rating_visible)."""
    return {
        media_id: list(games.values()) for media_id, games in linked_games_by_media(entity_type, entity_ids, db).items()
    }


def effective_content_rating(
    own: Optional[str], linked_ratings: Optional[list[Optional[str]]]
) -> tuple[Optional[str], bool]:
    """(effective rating, is_inherited) for display.

    Linked: the strictest linked rating by ordinal, an unknown rating
    counting as strictest. None when every linked game is unrated.
    Unlinked: the bundle's own rating.
    """
    if not linked_ratings:
        return (own or None), False
    rated = sorted({r for r in linked_ratings if r})
    if not rated:
        return None, True
    ordinals = _load_rating_ordinals()
    return max(rated, key=lambda r: ordinals.get(r, float("inf"))), True


def checked_media_rating_change(
    bundle: "MediaItemBundle", raw: Optional[str], *, confirm_rating_change: bool, db: "Session"
) -> Optional[str]:
    """Validate a PATCH of a media bundle's own content_rating and return the
    normalized value to store.

    Raises:
        HTTPException: 422 if the bundle is linked to software (its rating
            is inherited and its own value is not used). 409 if the change
            lowers, clears or changes the scheme of a set rating without
            *confirm_rating_change*, mirroring update_library_collection's
            guard for games. Null to rated needs no confirmation.
    """
    if has_linked_game("media_item_bundle", bundle.id, db):
        raise HTTPException(
            status_code=422,
            detail=(
                "content_rating cannot be set on media linked to software. "
                "Its rating is inherited from the linked software."
            ),
        )
    new_rating = normalize_content_rating(raw)
    old_rating = bundle.content_rating or None
    if rating_change_requires_confirmation(old_rating, new_rating):
        if not confirm_rating_change:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"content_rating change from {old_rating!r} to {new_rating!r} would "
                    "lower, clear, or change the scheme of an already-set rating. Re-submit with "
                    "confirm_rating_change=true to proceed."
                ),
            )
        _log.warning(
            "content_rating lowered/cleared on media_item_bundle id=%s: %r -> %r (confirmed by caller)",
            bundle.id,
            old_rating,
            new_rating,
        )
    return new_rating
