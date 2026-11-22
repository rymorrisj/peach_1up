import re

from fastapi import Depends, HTTPException, Request
from sqlalchemy import and_, or_, true
from sqlalchemy.orm import Session

from backend.constants_generated import CONTENT_RATINGS
from backend.core.database import get_db
from backend.core.identity import parse_session_cookie, validate_session
from backend.core.logger import get_logger
from backend.models.app import AppItem, AppItemBundle
from backend.models.game import GameItem, GameItemBundle
from backend.models.media import MediaItem, MediaItemBundle
from backend.models.media_restriction import MediaRestriction
from backend.models.user import UserItem

_log = get_logger(__name__)


def _derive_rating_ordinals() -> dict[str, int]:
    """Derive rating ordinals from CONTENT_RATINGS (config/constants.yaml).

    Ordinal = index within its scheme group (ESRB, PEGI, ...), in declared
    list order, each scheme's own severity ladder starts back at 0. This
    replaces a hand-maintained duplicate of the rating list that had to be
    kept in sync by hand; CONTENT_RATINGS is now the single source.
    """
    ordinals: dict[str, int] = {}
    counters: dict[str, int] = {}
    for entry in CONTENT_RATINGS:
        scheme = entry["scheme"]
        ordinal = counters.get(scheme, 0)
        ordinals[entry["value"]] = ordinal
        counters[scheme] = ordinal + 1
    return ordinals


_BASE_RATING_ORDINALS: dict[str, int] = _derive_rating_ordinals()

# Scheme grouping (ESRB, PEGI, ...) is not part of the ordinal override key —
# rating_ordinals only remaps severity within a scheme, so this always comes
# from the base CONTENT_RATINGS list, never the settings override.
_BASE_RATING_SCHEMES: dict[str, str] = {entry["value"]: entry["scheme"] for entry in CONTENT_RATINGS}


def _load_rating_ordinals() -> dict[str, int]:
    """Return the rating ordinal map from settings (key: rating_ordinals) or defaults.

    Falls back to _BASE_RATING_ORDINALS when settings are unavailable
    (RuntimeError before init) or malformed (TypeError/ValueError), the
    default vocabulary is the safe, restrictive baseline, never a widening.
    """
    try:
        from backend.core.settings import get_settings
        custom = get_settings().get("rating_ordinals")
        if isinstance(custom, dict):
            return {str(k): int(v) for k, v in custom.items()}
    except (RuntimeError, TypeError, ValueError):
        pass
    return dict(_BASE_RATING_ORDINALS)


def normalize_content_rating(raw: str | None) -> str | None:
    """Map a free-form rating string onto the known rating vocabulary.

    Sources like TheGamesDB return ratings such as ``"M - Mature 17+"`` or
    ``"E - Everyone"``; only the leading code is meaningful. Any value that
    does not resolve to a recognised key returns ``None`` (stored as unrated)
    rather than a guessed default, so the content-rating filter never has to
    reason about a string it doesn't understand.
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    canonical = {k.casefold(): k for k in _BASE_RATING_ORDINALS}
    if text.casefold() in canonical:
        return canonical[text.casefold()]
    # Fall back to the leading token, e.g. "M - Mature 17+" -> "M",
    # "E10+ - Everyone 10+" -> "E10+", "ESRB: T" -> "ESRB" (unrecognised -> None).
    lead = re.split(r"\s*[-:–]\s*", text, maxsplit=1)[0].strip()
    return canonical.get(lead.casefold())


def rating_change_requires_confirmation(old: str | None, new: str | None) -> bool:
    """Return True if moving content_rating from *old* to *new* lowers or clears
    an already-set rating, and therefore must not be written without explicit
    confirmation (an item moving below a sub-account's max_content_rating, or
    an unrated-visible gap, is a parental-control filter opening silently).

    ``old is None`` means there was nothing to protect yet, so any value is
    allowed through. Ratings from different schemes (ESRB vs PEGI) or any
    value missing from the known scheme/ordinal maps are not provably
    non-lowering, so they are conservatively treated as requiring
    confirmation too.
    """
    if old is None or new == old:
        return False
    if new is None:
        return True
    old_scheme = _BASE_RATING_SCHEMES.get(old)
    new_scheme = _BASE_RATING_SCHEMES.get(new)
    if old_scheme is None or new_scheme is None or old_scheme != new_scheme:
        return True
    ordinals = _load_rating_ordinals()
    old_ord = ordinals.get(old)
    new_ord = ordinals.get(new)
    if old_ord is None or new_ord is None:
        return True
    return new_ord < old_ord


def validate_max_content_rating(value: str | None) -> str | None:
    """Return *value* if it is a recognised rating key, else raise ValueError.

    ``None`` means "no ceiling" and always passes. An unknown value must be
    rejected on write: get_filtered_game_item_bundles looks the ceiling up in the
    ordinal map, gets ``None`` for an unrecognised value, and then skips the
    rating filter entirely, silently uncapping the user. Rejecting here keeps
    that bypass closed.
    """
    if value is None:
        return None
    known = _load_rating_ordinals()
    if value not in known:
        raise ValueError(
            f"Unknown max_content_rating {value!r}; expected one of: "
            f"{', '.join(sorted(known))}."
        )
    return value


def get_active_user(request: Request, db: Session = Depends(get_db)) -> UserItem:
    cookie = request.cookies.get("peach_token")
    if not cookie:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    parsed = parse_session_cookie(cookie)
    if parsed is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    user = validate_session(db, parsed[0], parsed[1])
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return user


def require_self_or_admin(request: Request, active_user: UserItem = Depends(get_active_user)) -> UserItem:
    user_item_id = int(request.path_params.get("user_item_id", 0))
    if active_user.id != user_item_id and not active_user.is_admin:
        raise HTTPException(status_code=403, detail="Permission denied.")
    return active_user


def require_admin_or_self_manage(request: Request, active_user: UserItem = Depends(get_active_user)) -> UserItem:
    """Allow owner/admin to target any user, or a user with can_manage_users to target themselves.

    Used by PATCH /user-items/{id} and POST /user-items/{id}/reset-pin so a sub-account can edit
    its own name/PIN without granting any capability over other users' accounts.
    can_manage_users never widens access to other targets and never bypasses the
    owner-target guard each caller still applies after this dependency passes.
    """
    if active_user.is_owner or active_user.is_admin:
        return active_user
    user_item_id = int(request.path_params.get("user_item_id", 0))
    if active_user.id == user_item_id and active_user.can_manage_users:
        return active_user
    raise HTTPException(status_code=403, detail="Permission denied.")


def require_owner_or_admin(active_user: UserItem = Depends(get_active_user)) -> UserItem:
    """Allow only owner or admin accounts. Used where a capability is reserved to
    household administrators with no per-flag equivalent, e.g. deleting launch
    history for any user."""
    if active_user.is_owner or active_user.is_admin:
        return active_user
    raise HTTPException(status_code=403, detail="Permission denied: requires owner or admin.")


def require_game_or_environment_editor(active_user: UserItem = Depends(get_active_user)) -> UserItem:
    """Allow owners and anyone who can edit the game library or environments (e.g. filesystem browsing)."""
    if active_user.is_owner or active_user.can_manage_game or active_user.can_manage_environment:
        return active_user
    raise HTTPException(
        status_code=403,
        detail="Permission denied: requires can_manage_game or can_manage_environment.",
    )


def require_permission(flag: str):
    """Dependency factory that enforces a boolean permission flag on the active user.

    Owner accounts bypass all permission checks. Usage::

        @router.post("/items")
        def create_item(_: UserItem = require_permission("can_manage_game"), ...):
            ...
    """
    def _check(active_user: UserItem = Depends(get_active_user)) -> UserItem:
        if active_user.is_owner:
            return active_user
        if not getattr(active_user, flag, False):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: requires {flag}.",
            )
        return active_user
    _check.__name__ = f"require_{flag}"
    return Depends(_check)


def _restricted_bundle_ids(restriction_column, active_user: UserItem, db: Session):
    """Subquery of *_item_bundle ids MediaRestriction blocklists for *active_user*.

    Shared membership check behind every domain's (Game/Media/App) filtered-query
    helper, parameterized only by which MediaRestriction FK column to key off
    (e.g. ``MediaRestriction.game_item_bundle_id``). Owner bypass is each caller's
    responsibility, checked before this is ever invoked.

    The ``restriction_column.isnot(None)`` guard is required, not defensive
    boilerplate: MediaRestriction is one shared table for all three domains, so a
    user's rows include NULLs in this column whenever they also have a
    restriction targeting a *different* domain (e.g. filtering on
    media_item_bundle_id while the same user also has a Game restriction row,
    which leaves media_item_bundle_id NULL on that row). SQL's ``NOT IN``
    against a list containing NULL evaluates to UNKNOWN for every row, not
    TRUE, so without this filter, one cross-domain restriction row would
    silently blank out this user's entire query for every other domain.
    """
    return db.query(restriction_column).filter(
        MediaRestriction.user_item_id == active_user.id,
        restriction_column.isnot(None),
    ).scalar_subquery()


def get_filtered_game_item_bundles(active_user: UserItem, db: Session):
    """Return a GameItemBundle query filtered to what *active_user* may see.

    Owner sees all collections. For non-owners:
    - ``block_unrated_media=True`` excludes collections with null/empty content_rating.
    - ``max_content_rating`` limits results to ratings at or below the ordinal threshold.
      For a user with a ceiling, collections whose rating is unrecognised are DENIED,
      not passed through, an unknown rating must never leak past a parental cap. If the
      user's own ceiling cannot be resolved to a known ordinal (e.g. a ``rating_ordinals``
      settings change orphaned a previously-valid value), this fails closed: no rated
      content passes, rather than silently dropping the ceiling entirely.
      Null/empty ratings are governed separately by ``block_unrated_media`` above.

    Returns a SQLAlchemy Query that callers can chain additional filters onto.
    """
    q = db.query(GameItemBundle)

    if active_user.is_owner:
        return q

    restricted_ids = _restricted_bundle_ids(MediaRestriction.game_item_bundle_id, active_user, db)
    q = q.filter(GameItemBundle.id.not_in(restricted_ids))
    return q.filter(content_rating_visible(GameItemBundle.content_rating, active_user))


def content_rating_visible(rating_column, active_user: UserItem):
    """SQL predicate: a row whose rating lives in *rating_column* passes
    *active_user*'s ``block_unrated_media`` and ``max_content_rating`` filter.

    The one visibility rule behind get_filtered_game_item_bundles and the
    media effective-rating rule (backend/service/media/content_rating.py),
    parameterized only by which column holds the rating. Fail-closed rules
    are documented on get_filtered_game_item_bundles. Owner bypass is each
    caller's responsibility. Never evaluates to SQL NULL, so it is safe to
    negate with ``not_()``.
    """
    clauses = []
    if active_user.block_unrated_media:
        clauses.append(and_(rating_column.isnot(None), rating_column != ""))

    if active_user.max_content_rating:
        ordinal_map = _load_rating_ordinals()
        max_ord = ordinal_map.get(active_user.max_content_rating)
        # An unresolvable ceiling must fail closed (deny all rated content),
        # not silently disable the rating filter, see get_filtered_game_item_bundles.
        allowed = {r for r, o in ordinal_map.items() if o <= max_ord} if max_ord is not None else set()
        clauses.append(
            or_(
                rating_column.is_(None),
                rating_column == "",
                rating_column.in_(list(allowed)),
            )
        )

    return and_(true(), *clauses)


def get_filtered_game_item_bundle(id_or_slug: int | str, active_user: UserItem, db: Session) -> GameItemBundle:
    """Return a single GameItemBundle if *active_user* is allowed to see it.

    Reuses get_filtered_game_item_bundles' owner-bypass and restriction/rating filters,
    narrowed to one collection. Raises 404 (not a different status) whether the
    collection doesn't exist or is filtered out, so existence isn't leaked to
    callers who shouldn't see it.
    """
    q = get_filtered_game_item_bundles(active_user, db)
    if isinstance(id_or_slug, int):
        q = q.filter(GameItemBundle.id == id_or_slug)
    else:
        q = q.filter(GameItemBundle.slug == id_or_slug)
    collection = q.first()
    if collection is None:
        raise HTTPException(status_code=404, detail="Software collection not found.")
    return collection


# ---------------------------------------------------------------------------
# App: mirrors Game exactly, manual blocklist only, no content_rating concept
# (AppItemBundle has no such column, see backend/models/app.py). The
# "/app-items" list route already returns AppItemBundle rows (same shape as
# Game's "/game-items"), so get_filtered_app_items/_app_item follow that same
# naming, despite the function bodies operating on AppItemBundle, not AppItem.
# ---------------------------------------------------------------------------


def get_filtered_app_items(active_user: UserItem, db: Session):
    """Return an AppItemBundle query filtered to what *active_user* may see.

    Owner sees all collections. Manual blocklist only (MediaRestriction), Apps have
    no content_rating/max_content_rating concept to filter on.
    """
    q = db.query(AppItemBundle)
    if active_user.is_owner:
        return q
    restricted_ids = _restricted_bundle_ids(MediaRestriction.app_item_bundle_id, active_user, db)
    return q.filter(AppItemBundle.id.not_in(restricted_ids))


def get_filtered_app_item(id_or_slug: int | str, active_user: UserItem, db: Session) -> AppItemBundle:
    """Return a single AppItemBundle if *active_user* is allowed to see it.

    Raises 404 whether the collection doesn't exist or is filtered out, so
    existence isn't leaked to callers who shouldn't see it.
    """
    q = get_filtered_app_items(active_user, db)
    if isinstance(id_or_slug, int):
        q = q.filter(AppItemBundle.id == id_or_slug)
    else:
        q = q.filter(AppItemBundle.slug == id_or_slug)
    collection = q.first()
    if collection is None:
        raise HTTPException(status_code=404, detail="App collection not found.")
    return collection


# ---------------------------------------------------------------------------
# Media: restriction is scoped to MediaItemBundle (mirrors Game/App), but
# unlike Game/App, individual MediaItem rows can stand alone with no parent
# bundle (media_item_bundle_id is nullable). Media also exposes its own
# top-level "/media-items" list + "/media-item/{id}" detail routes for that
# leaf entity, Game/App leaves have no such bulk route, so there was no
# equivalent naming slot for them. get_filtered_media_item_bundles/_bundle
# below is the direct Game/App mirror (bundle-level, used by
# "/media-item-bundles" + "/media-item-bundle/{id}"); get_filtered_media_items/
# _media_item is the leaf-level pair (used by "/media-items" +
# "/media-item/{id}"), null-safe for standalone items.
# ---------------------------------------------------------------------------


def get_filtered_media_item_bundles(active_user: UserItem, db: Session):
    """Return a MediaItemBundle query filtered to what *active_user* may see.

    Owner sees all collections. Non-owners: the MediaRestriction blocklist,
    then the effective-rating rule (media_rating_visible): a bundle linked
    to software is visible only if every linked game passes this user's
    rating filter, an unlinked bundle is judged on its own content_rating.
    """
    from backend.service.media.content_rating import media_rating_visible

    q = db.query(MediaItemBundle)
    if active_user.is_owner:
        return q
    restricted_ids = _restricted_bundle_ids(MediaRestriction.media_item_bundle_id, active_user, db)
    return q.filter(
        MediaItemBundle.id.not_in(restricted_ids),
        media_rating_visible(
            "media_item_bundle", MediaItemBundle.id, MediaItemBundle.content_rating, active_user,
        ),
    )


def get_filtered_media_item_bundle(id_or_slug: int | str, active_user: UserItem, db: Session) -> MediaItemBundle:
    """Return a single MediaItemBundle if *active_user* is allowed to see it.

    Raises 404 whether the collection doesn't exist or is filtered out, so
    existence isn't leaked to callers who shouldn't see it.
    """
    q = get_filtered_media_item_bundles(active_user, db)
    if isinstance(id_or_slug, int):
        q = q.filter(MediaItemBundle.id == id_or_slug)
    else:
        q = q.filter(MediaItemBundle.slug == id_or_slug)
    item = q.first()
    if item is None:
        raise HTTPException(status_code=404, detail="Media collection not found.")
    return item


def get_filtered_media_items(active_user: UserItem, db: Session):
    """Return a MediaItem query filtered to what *active_user* may see.

    Owner sees all items. Non-owners: an item in a bundle is visible exactly
    when its bundle is (get_filtered_media_item_bundles, blocklist plus
    effective rating). An item with no parent bundle has no blocklist row
    and no rating column of its own, so it goes through the same
    effective-rating rule on its own item-level links with an unrated own
    rating: it needs every linked game to pass, or, unlinked, it is treated
    as unrated (hidden from block_unrated_media accounts), failing closed.
    """
    from sqlalchemy import String, cast, null

    from backend.service.media.content_rating import media_rating_visible

    q = db.query(MediaItem)
    if active_user.is_owner:
        return q
    visible_bundle_ids = (
        get_filtered_media_item_bundles(active_user, db).with_entities(MediaItemBundle.id).subquery()
    )
    return q.filter(
        or_(
            and_(
                MediaItem.media_item_bundle_id.is_(None),
                media_rating_visible("media_item", MediaItem.id, cast(null(), String), active_user),
            ),
            MediaItem.media_item_bundle_id.in_(visible_bundle_ids.select()),
        )
    )


def get_filtered_media_item(item_id: int, active_user: UserItem, db: Session) -> MediaItem:
    """Return a single MediaItem if *active_user* is allowed to see it.

    Raises 404 whether the item doesn't exist or is filtered out, so
    existence isn't leaked to callers who shouldn't see it.
    """
    item = get_filtered_media_items(active_user, db).filter(MediaItem.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Media item not found.")
    return item


# ---------------------------------------------------------------------------
# Polymorphic entity_type dispatch over the filtered helpers above, for
# routes that take an (entity_type, entity_id) pair (entity links, tag
# assignments) and for linked-title resolution in the read builders.
# ---------------------------------------------------------------------------


def _filtered_game_leaf(leaf_id: int, active_user: UserItem, db: Session) -> GameItem:
    """A GameItem leaf is visible exactly when its parent bundle is."""
    leaf = db.get(GameItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="Software item not found.")
    get_filtered_game_item_bundle(leaf.game_item_bundle_id, active_user, db)
    return leaf


def _filtered_app_leaf(leaf_id: int, active_user: UserItem, db: Session) -> AppItem:
    """An AppItem leaf is visible exactly when its parent bundle is."""
    leaf = db.get(AppItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="App item not found.")
    get_filtered_app_item(leaf.app_item_bundle_id, active_user, db)
    return leaf


_FILTERED_ENTITY_LOOKUPS = {
    "game_item_bundle": get_filtered_game_item_bundle,
    "game_item": _filtered_game_leaf,
    "app_item_bundle": get_filtered_app_item,
    "app_item": _filtered_app_leaf,
    "media_item_bundle": get_filtered_media_item_bundle,
    "media_item": get_filtered_media_item,
}

# entity_types that carry a visibility rule. Anything else (environments,
# ROM packs, controller mappings) has no per-user filter.
VISIBILITY_FILTERED_ENTITY_TYPES: frozenset[str] = frozenset(_FILTERED_ENTITY_LOOKUPS)


def get_filtered_entity(entity_type: str, entity_id: int, active_user: UserItem, db: Session):
    """Return one row of *entity_type* if *active_user* may see it.

    Missing and hidden both raise the same ``404 "{entity_type} not found."``,
    so the response never distinguishes the two.

    Raises:
        HTTPException: 404 when missing or filtered out.
        ValueError: If *entity_type* has no visibility rule (callers check
            VISIBILITY_FILTERED_ENTITY_TYPES first).
    """
    lookup = _FILTERED_ENTITY_LOOKUPS.get(entity_type)
    if lookup is None:
        raise ValueError(f"No visibility rule for entity_type {entity_type!r}.")
    try:
        return lookup(entity_id, active_user, db)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail=f"{entity_type} not found.") from None
        raise


_FILTERED_BUNDLE_QUERIES = {
    "game_item_bundle": get_filtered_game_item_bundles,
    "app_item_bundle": get_filtered_app_items,
    "media_item_bundle": get_filtered_media_item_bundles,
    "media_item": get_filtered_media_items,
}


def get_filtered_entity_query(entity_type: str, active_user: UserItem, db: Session):
    """The filtered list query for a link target *entity_type*, or None when
    there is none. Used to resolve linked titles so a counterpart the viewer
    cannot see is never named."""
    builder = _FILTERED_BUNDLE_QUERIES.get(entity_type)
    return builder(active_user, db) if builder is not None else None
