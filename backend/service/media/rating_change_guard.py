"""Effective-rating confirmation guard for actions that change which games a
media unit inherits its rating from: entity-link create and delete, game
delete, and moving a media item into another bundle or out to standalone
(MED-8 follow-up).

A "media unit" is what the visibility filter judges
(get_filtered_media_item_bundles / get_filtered_media_items in
backend/core/dependencies.py): a MediaItemBundle, or a MediaItem with no
parent bundle. An item inside a bundle is judged by its bundle alone, so its
own item-level links never change who can see it and are not a unit here.

Each *_effects function returns one (before, after) effective-rating pair per
affected unit, computed with effective_content_rating.
require_rating_change_confirmation applies rating_change_requires_confirmation
to every pair, the same rule a PATCH of a bundle's own rating uses: lowering,
clearing (including becoming unrated) or changing the scheme needs
confirm_rating_change=true, anything else passes. The 409 carries a count
only, never a title, so it cannot name media the caller is not allowed to see.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import and_, or_

from backend.core.dependencies import rating_change_requires_confirmation
from backend.core.logger import get_logger
from backend.models.game import GameItemBundle
from backend.models.media import MediaItem, MediaItemBundle, MediaLink
from backend.service.media.content_rating import effective_content_rating, linked_games_by_media

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_GAME = "game_item_bundle"
_BUNDLE = "media_item_bundle"
_ITEM = "media_item"

# error_type of the structured 409 detail, matched by the frontend's
# useRatingChangeConfirm hook.
RATING_CHANGE_ERROR_TYPE = "rating_change_requires_confirmation"

MediaUnit = tuple[str, int]
RatingChange = tuple[Optional[str], Optional[str]]
_UnitState = tuple[Optional[str], dict[int, Optional[str]]]

_log = get_logger(__name__)


def _effective(own: Optional[str], games: dict[int, Optional[str]]) -> Optional[str]:
    """Effective rating of a unit with own rating *own* and linked *games*."""
    return effective_content_rating(own, list(games.values()))[0]


def _unit_states(units: Iterable[MediaUnit], db: "Session") -> dict[MediaUnit, _UnitState]:
    """(own rating, {linked game id: rating}) per unit, in bulk queries. A
    standalone item has no rating column, so its own rating is None, the
    same cast(null()) get_filtered_media_items judges it with."""
    units = set(units)
    bundle_ids = [i for t, i in units if t == _BUNDLE]
    item_ids = [i for t, i in units if t == _ITEM]
    own_by_bundle: dict[int, Optional[str]] = {}
    if bundle_ids:
        own_by_bundle = dict(
            db.query(MediaItemBundle.id, MediaItemBundle.content_rating)
            .filter(MediaItemBundle.id.in_(bundle_ids))
            .all()
        )
    bundle_games = linked_games_by_media(_BUNDLE, bundle_ids, db)
    item_games = linked_games_by_media(_ITEM, item_ids, db)
    states: dict[MediaUnit, _UnitState] = {}
    for unit in units:
        entity_type, entity_id = unit
        if entity_type == _BUNDLE:
            states[unit] = (own_by_bundle.get(entity_id) or None, bundle_games.get(entity_id, {}))
        else:
            states[unit] = (None, item_games.get(entity_id, {}))
    return states


def _media_unit(entity_type: str, entity_id: int, db: "Session") -> Optional[MediaUnit]:
    """The unit a link on (*entity_type*, *entity_id*) feeds, or None when
    that side cannot affect visibility (not media, or an item in a bundle)."""
    if entity_type == _BUNDLE:
        return (_BUNDLE, entity_id)
    if entity_type == _ITEM:
        item = db.get(MediaItem, entity_id)
        if item is not None and item.media_item_bundle_id is None:
            return (_ITEM, entity_id)
    return None


def link_change_effects(
    entity_type: str,
    entity_id: int,
    target_entity_type: str,
    target_entity_id: int,
    *,
    adding: bool,
    db: "Session",
) -> list[RatingChange]:
    """Effect of creating (*adding*) or deleting one link. Only a
    game-to-media-unit link can change a rating; anything else is []."""
    if entity_type == _GAME and target_entity_type != _GAME:
        game_id, media_side = entity_id, (target_entity_type, target_entity_id)
    elif target_entity_type == _GAME and entity_type != _GAME:
        game_id, media_side = target_entity_id, (entity_type, entity_id)
    else:
        return []
    unit = _media_unit(*media_side, db)
    if unit is None:
        return []
    own, games = _unit_states([unit], db)[unit]
    after = dict(games)
    if adding:
        game = db.get(GameItemBundle, game_id)
        if game is None:
            return []
        after[game_id] = game.content_rating or None
    else:
        after.pop(game_id, None)
    return [(_effective(own, games), _effective(own, after))]


def game_removal_effects(game_id: int, db: "Session") -> list[RatingChange]:
    """Effect of deleting game *game_id* (and with it every link it has) on
    every media unit linked to it."""
    links = db.query(MediaLink).filter(
        or_(
            and_(MediaLink.entity_a_type == _GAME, MediaLink.entity_a_id == game_id),
            and_(MediaLink.entity_b_type == _GAME, MediaLink.entity_b_id == game_id),
        )
    ).all()
    bundle_ids: set[int] = set()
    item_ids: set[int] = set()
    for link in links:
        if link.entity_a_type == _GAME and link.entity_a_id == game_id:
            other_type, other_id = link.entity_b_type, link.entity_b_id
        else:
            other_type, other_id = link.entity_a_type, link.entity_a_id
        if other_type == _BUNDLE:
            bundle_ids.add(other_id)
        elif other_type == _ITEM:
            item_ids.add(other_id)
    standalone_ids: set[int] = set()
    if item_ids:
        standalone_ids = {
            row_id for (row_id,) in db.query(MediaItem.id).filter(
                MediaItem.id.in_(item_ids), MediaItem.media_item_bundle_id.is_(None),
            )
        }
    units = {(_BUNDLE, i) for i in bundle_ids} | {(_ITEM, i) for i in standalone_ids}
    changes: list[RatingChange] = []
    for own, games in _unit_states(units, db).values():
        after = {g: r for g, r in games.items() if g != game_id}
        changes.append((_effective(own, games), _effective(own, after)))
    return changes


def item_move_effects(item: MediaItem, new_bundle_id: Optional[int], db: "Session") -> list[RatingChange]:
    """Effect on *item* of moving it to *new_bundle_id* (None: standalone).
    In a bundle it takes the bundle's effective rating; standalone it takes
    the effective rating of its own item-level links."""
    if new_bundle_id == item.media_item_bundle_id:
        return []

    def _unit_for(bundle_id: Optional[int]) -> MediaUnit:
        return (_BUNDLE, bundle_id) if bundle_id is not None else (_ITEM, item.id)

    before_unit = _unit_for(item.media_item_bundle_id)
    after_unit = _unit_for(new_bundle_id)
    states = _unit_states([before_unit, after_unit], db)
    return [(_effective(*states[before_unit]), _effective(*states[after_unit]))]


def require_rating_change_confirmation(
    changes: list[RatingChange], *, confirm_rating_change: bool, action: str
) -> None:
    """Raise 409 when any change loosens an effective rating and the caller
    has not confirmed. *action* names the operation in the message and log.

    Raises:
        HTTPException: 409 with detail {error_type, message, affected_count}.
            The count may include media the caller cannot see; no title,
            id or rating of any affected unit is included.
    """
    loosened = sum(1 for before, after in changes if rating_change_requires_confirmation(before, after))
    if not loosened:
        return
    if not confirm_rating_change:
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": RATING_CHANGE_ERROR_TYPE,
                "message": (
                    f"This {action} would lower, clear, or change the scheme of the effective "
                    f"content rating of {loosened} media item(s), changing who can see them. "
                    "Re-submit with confirm_rating_change=true to proceed."
                ),
                "affected_count": loosened,
            },
        )
    _log.warning(
        "Effective content_rating loosened on %d media unit(s) by %s (confirmed by caller)",
        loosened, action,
    )
