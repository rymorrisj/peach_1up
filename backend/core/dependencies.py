import re

from fastapi import Depends, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.identity import parse_session_cookie, validate_session
from backend.core.logger import get_logger
from backend.models.library import LibraryCollection
from backend.models.media_restriction import MediaRestriction
from backend.models.user import User

_log = get_logger(__name__)

_DEFAULT_RATING_ORDINALS: dict[str, int] = {
    "EC": 0,
    "E": 1,
    "E10+": 2,
    "T": 3,
    "M": 4,
    "AO": 5,
    "PEGI 3": 0,
    "PEGI 7": 1,
    "PEGI 12": 2,
    "PEGI 16": 3,
    "PEGI 18": 4,
}


def _load_rating_ordinals() -> dict[str, int]:
    """Return the rating ordinal map from settings.yaml (key: rating_ordinals) or defaults.

    Falls back to _DEFAULT_RATING_ORDINALS when settings are unavailable
    (RuntimeError before init) or malformed (TypeError/ValueError) — the
    default vocabulary is the safe, restrictive baseline, never a widening.
    """
    try:
        from backend.core.settings import get_settings
        custom = get_settings().get("rating_ordinals")
        if isinstance(custom, dict):
            return {str(k): int(v) for k, v in custom.items()}
    except (RuntimeError, TypeError, ValueError):
        pass
    return dict(_DEFAULT_RATING_ORDINALS)


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
    canonical = {k.casefold(): k for k in _DEFAULT_RATING_ORDINALS}
    if text.casefold() in canonical:
        return canonical[text.casefold()]
    # Fall back to the leading token, e.g. "M - Mature 17+" -> "M",
    # "E10+ - Everyone 10+" -> "E10+", "ESRB: T" -> "ESRB" (unrecognised -> None).
    lead = re.split(r"\s*[-:–]\s*", text, maxsplit=1)[0].strip()
    return canonical.get(lead.casefold())


def validate_max_content_rating(value: str | None) -> str | None:
    """Return *value* if it is a recognised rating key, else raise ValueError.

    ``None`` means "no ceiling" and always passes. An unknown value must be
    rejected on write: get_filtered_collections looks the ceiling up in the
    ordinal map, gets ``None`` for an unrecognised value, and then skips the
    rating filter entirely — silently uncapping the user. Rejecting here keeps
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


def get_active_user(request: Request, db: Session = Depends(get_db)) -> User:
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


def require_self_or_admin(request: Request, active_user: User = Depends(get_active_user)) -> User:
    user_id = int(request.path_params.get("user_id", 0))
    if active_user.id != user_id and not active_user.is_admin:
        raise HTTPException(status_code=403, detail="Permission denied.")
    return active_user


def require_admin_or_self_manage(request: Request, active_user: User = Depends(get_active_user)) -> User:
    """Allow owner/admin to target any user, or a user with can_manage_users to target themselves.

    Used by PATCH /users/{id} and POST /users/{id}/reset-pin so a sub-account can edit
    its own name/PIN without granting any capability over other users' accounts.
    can_manage_users never widens access to other targets and never bypasses the
    owner-target guard each caller still applies after this dependency passes.
    """
    if active_user.is_owner or active_user.is_admin:
        return active_user
    user_id = int(request.path_params.get("user_id", 0))
    if active_user.id == user_id and active_user.can_manage_users:
        return active_user
    raise HTTPException(status_code=403, detail="Permission denied.")


def require_library_or_platform_editor(active_user: User = Depends(get_active_user)) -> User:
    """Allow owners and anyone who can edit the library or platforms (e.g. filesystem browsing)."""
    if active_user.is_owner or active_user.can_edit_library or active_user.can_edit_platforms:
        return active_user
    raise HTTPException(
        status_code=403,
        detail="Permission denied: requires can_edit_library or can_edit_platforms.",
    )


def require_permission(flag: str):
    """Dependency factory that enforces a boolean permission flag on the active user.

    Owner accounts bypass all permission checks. Usage::

        @router.post("/items")
        def create_item(_: User = require_permission("can_edit_library"), ...):
            ...
    """
    def _check(active_user: User = Depends(get_active_user)) -> User:
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


def get_filtered_collections(active_user: User, db: Session):
    """Return a LibraryCollection query filtered to what *active_user* may see.

    Owner sees all collections. For non-owners:
    - ``block_unrated_media=True`` excludes collections with null/empty content_rating.
    - ``max_content_rating`` limits results to ratings at or below the ordinal threshold.
      For a user with a ceiling, collections whose rating is unrecognised are DENIED,
      not passed through — an unknown rating must never leak past a parental cap.
      Null/empty ratings are governed separately by ``block_unrated_media`` above.

    Returns a SQLAlchemy Query that callers can chain additional filters onto.
    """
    q = db.query(LibraryCollection)

    if active_user.is_owner:
        return q

    restricted_ids = db.query(MediaRestriction.library_collection_id).filter(
        MediaRestriction.user_id == active_user.id
    ).scalar_subquery()
    q = q.filter(LibraryCollection.id.not_in(restricted_ids))

    if active_user.block_unrated_media:
        q = q.filter(
            LibraryCollection.content_rating.isnot(None),
            LibraryCollection.content_rating != "",
        )

    if active_user.max_content_rating:
        ordinal_map = _load_rating_ordinals()
        max_ord = ordinal_map.get(active_user.max_content_rating)
        if max_ord is not None:
            allowed = {r for r, o in ordinal_map.items() if o <= max_ord}
            q = q.filter(
                or_(
                    LibraryCollection.content_rating.is_(None),
                    LibraryCollection.content_rating == "",
                    LibraryCollection.content_rating.in_(list(allowed)),
                )
            )

    return q


def get_filtered_collection(id_or_slug: int | str, active_user: User, db: Session) -> LibraryCollection:
    """Return a single LibraryCollection if *active_user* is allowed to see it.

    Reuses get_filtered_collections' owner-bypass and restriction/rating filters,
    narrowed to one collection. Raises 404 (not a different status) whether the
    collection doesn't exist or is filtered out, so existence isn't leaked to
    callers who shouldn't see it.
    """
    q = get_filtered_collections(active_user, db)
    if isinstance(id_or_slug, int):
        q = q.filter(LibraryCollection.id == id_or_slug)
    else:
        q = q.filter(LibraryCollection.slug == id_or_slug)
    collection = q.first()
    if collection is None:
        raise HTTPException(status_code=404, detail="Library collection not found.")
    return collection
