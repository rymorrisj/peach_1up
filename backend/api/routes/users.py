import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission, require_self_or_admin
from backend.core.identity import clear_session, generate_identity_secret
from backend.core.logger import get_logger
from backend.models.user import User, UserRead

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class UserCreate(BaseModel):
    name: str
    pin: str | None = None
    can_launch_media: bool = True
    can_edit_platforms: bool = False
    can_edit_library: bool = False
    can_manage_profiles: bool = False
    can_edit_settings: bool = False
    is_admin: bool = False
    max_content_rating: str | None = None
    block_unrated_media: bool = False
    session_token_ttl: int | None = None


class UserPatch(BaseModel):
    name: str | None = None
    can_launch_media: bool | None = None
    can_edit_platforms: bool | None = None
    can_edit_library: bool | None = None
    can_manage_profiles: bool | None = None
    can_edit_settings: bool | None = None
    is_admin: bool | None = None
    max_content_rating: str | None = None
    block_unrated_media: bool | None = None
    pin_required: bool | None = None
    session_token_ttl: int | None = None


class ResetPinBody(BaseModel):
    pin: str


def _hash_pin(pin: str) -> str:
    from argon2.low_level import Type, hash_secret
    salt = os.urandom(16)
    return hash_secret(
        secret=pin.encode(),
        salt=salt,
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        type=Type.ID,
    ).decode()


def _validate_pin(pin: str) -> None:
    import re
    if not re.fullmatch(r"\d{4,6}", pin):
        raise HTTPException(status_code=422, detail="PIN must be 4–6 digits.")


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)):
    # Intentionally unauthenticated: this is the account list the switch-user
    # screen needs to render before anyone is signed in (mirrors /auth/switch,
    # which also requires no prior session). UserRead excludes pin_hash and
    # all other secrets, so this only ever exposes names/flags, never proof
    # of identity.
    return db.query(User).all()


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.post("", response_model=UserRead, status_code=201)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    pin_hash: str | None = None
    if body.pin is not None:
        _validate_pin(body.pin)
        pin_hash = _hash_pin(body.pin)

    user = User(
        name=body.name,
        is_owner=False,
        pin_required=body.pin is not None,
        pin_hash=pin_hash,
        identity_token_secret=generate_identity_secret(),
        can_launch_media=body.can_launch_media,
        can_edit_platforms=body.can_edit_platforms,
        can_edit_library=body.can_edit_library,
        can_manage_profiles=body.can_manage_profiles,
        can_edit_settings=body.can_edit_settings,
        is_admin=body.is_admin,
        max_content_rating=body.max_content_rating,
        block_unrated_media=body.block_unrated_media,
        session_token_ttl=body.session_token_ttl,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    body: UserPatch,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.is_owner:
        raise HTTPException(status_code=403, detail="Owner account cannot be modified here.")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    active_user: User = Depends(require_self_or_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.is_owner:
        raise HTTPException(status_code=403, detail="Owner account cannot be deleted.")

    owner = db.query(User).filter(User.is_owner.is_(True)).first()
    owner_id = owner.id if owner else None

    from backend.models.media_restriction import MediaRestriction
    from backend.models.profile import Profile
    db.query(MediaRestriction).filter(MediaRestriction.user_id == user_id).delete(synchronize_session=False)
    db.query(Profile).filter(Profile.user_id == user_id).update(
        {Profile.user_id: owner_id}, synchronize_session=False
    )

    db.delete(user)
    db.commit()


@router.post("/{user_id}/reset-pin", response_model=UserRead)
def reset_pin(
    user_id: int,
    body: ResetPinBody,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    _validate_pin(body.pin)
    user.pin_hash = _hash_pin(body.pin)
    user.pin_required = True
    user.failed_pin_attempts = 0
    user.is_locked = False
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/unlock", response_model=UserRead)
def unlock_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.is_locked = False
    user.failed_pin_attempts = 0
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/force-logout", response_model=UserRead)
def force_logout(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.is_owner:
        raise HTTPException(status_code=403, detail="Owner account cannot be modified here.")
    clear_session(db, user)
    db.refresh(user)
    return user
