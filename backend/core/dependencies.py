from fastapi import Depends, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.library import LibraryItem
from backend.models.media_restriction import MediaRestriction
from backend.models.user import User

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
    """Return the rating ordinal map from settings.yaml (key: rating_ordinals) or defaults."""
    try:
        from backend.core.settings import get_settings
        custom = get_settings().get("rating_ordinals")
        if isinstance(custom, dict):
            return {str(k): int(v) for k, v in custom.items()}
    except (RuntimeError, TypeError, ValueError):
        pass
    return dict(_DEFAULT_RATING_ORDINALS)


def get_active_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Return the currently active user for this session.

    Falls back to the owner account when:
    - no active_user_id is stored in the session
    - the session user no longer exists in the database

    Raises 503 if no owner account exists.
    """

    try:
        from backend.core.settings import get_settings
    except RuntimeError:
        pass

    owner = db.query(User).filter(User.is_owner.is_(True)).first()
    if owner is None:
        raise HTTPException(status_code=503, detail="No owner account configured.")

    user_id = request.session.get("active_user_id")
    if user_id is None:
        return owner

    user = db.get(User, user_id)
    if user is None:
        return owner

    return user


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


def get_filtered_library(active_user: User, db: Session):
    """Return a LibraryItem query filtered to what *active_user* is allowed to see.

    Owner sees all items. For non-owners:
    - ``block_unrated_media=True`` excludes items with null or empty content_rating.
    - ``max_content_rating`` limits results to ratings at or below the ordinal threshold;
      items with unrecognised rating strings pass through (foreign rating systems).

    Returns a SQLAlchemy Query that callers can chain additional filters onto.
    """
    q = db.query(LibraryItem)

    if active_user.is_owner:
        return q

    restricted_ids = db.query(MediaRestriction.library_item_id).filter(
        MediaRestriction.user_id == active_user.id
    ).scalar_subquery()
    q = q.filter(LibraryItem.id.not_in(restricted_ids))

    if active_user.block_unrated_media:
        q = q.filter(
            LibraryItem.content_rating.isnot(None),
            LibraryItem.content_rating != "",
        )

    if active_user.max_content_rating:
        ordinal_map = _load_rating_ordinals()
        max_ord = ordinal_map.get(active_user.max_content_rating)
        if max_ord is not None:
            allowed = {r for r, o in ordinal_map.items() if o <= max_ord}
            known = set(ordinal_map.keys())
            q = q.filter(
                or_(
                    LibraryItem.content_rating.is_(None),
                    LibraryItem.content_rating == "",
                    LibraryItem.content_rating.in_(list(allowed)),
                    ~LibraryItem.content_rating.in_(list(known)),
                )
            )

    return q
