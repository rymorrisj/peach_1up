from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.user import User


def get_active_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Return the currently active user for this session.

    Falls back to the owner account when:
    - auth is disabled in settings (AUTH_ENABLED is falsy)
    - no active_user_id is stored in the session
    - the session user no longer exists in the database

    Raises 503 if no owner account exists.
    """
    auth_enabled = False
    try:
        from backend.core.settings import get_settings
        auth_enabled = bool(get_settings().get("AUTH_ENABLED", False))
    except RuntimeError:
        pass

    owner = db.query(User).filter(User.is_owner.is_(True)).first()
    if owner is None:
        raise HTTPException(status_code=503, detail="No owner account configured.")

    if not auth_enabled:
        return owner

    user_id = request.session.get("active_user_id")
    if user_id is None:
        return owner

    user = db.get(User, user_id)
    if user is None:
        return owner

    return user
