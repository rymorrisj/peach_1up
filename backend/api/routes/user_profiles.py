from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.user_profile import ProfilePermissions, UserProfile
from backend.schemas.user_profile import UserProfileCreate, UserProfileRead, UserProfileUpdate

router = APIRouter(prefix="/api/v1/profiles/users", tags=["user-profiles"])

_ACTIVE_PROFILE_KEY = "active_user_profile_id"


class PinRequest(BaseModel):
    pin: str | None = None


@router.get("", response_model=list[UserProfileRead])
def list_user_profiles(db: Session = Depends(get_db)):
    return db.query(UserProfile).all()


@router.post("", response_model=UserProfileRead, status_code=201)
def create_user_profile(body: UserProfileCreate, db: Session = Depends(get_db)):
    from passlib.context import CryptContext
    crypt = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12, deprecated="auto")
    pin_hash = crypt.hash(body.pin) if body.pin else None
    profile = UserProfile(
        name=body.name,
        avatar_path=body.avatar_path,
        pin_hash=pin_hash,
        is_owner=body.is_owner,
    )
    db.add(profile)
    db.flush()
    perms = ProfilePermissions(profile_id=profile.id)
    db.add(perms)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/current")
def get_current_profile(request: Request, db: Session = Depends(get_db)):
    profile_id = request.session.get(_ACTIVE_PROFILE_KEY) if hasattr(request, "session") else None
    if not profile_id:
        owner = db.query(UserProfile).filter(UserProfile.is_owner.is_(True)).first()
        return owner
    return db.get(UserProfile, profile_id)


@router.patch("/{profile_id}", response_model=UserProfileRead)
def update_user_profile(profile_id: int, body: UserProfileUpdate, db: Session = Depends(get_db)):
    profile = db.get(UserProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found.")
    if body.name is not None:
        profile.name = body.name
    if body.avatar_path is not None:
        profile.avatar_path = body.avatar_path
    if body.pin is not None:
        from passlib.context import CryptContext
        crypt = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12, deprecated="auto")
        profile.pin_hash = crypt.hash(body.pin)
    db.commit()
    db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=204)
def delete_user_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.get(UserProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found.")
    if profile.is_owner:
        raise HTTPException(status_code=403, detail="Owner profile cannot be deleted.")
    db.delete(profile)
    db.commit()


@router.post("/{profile_id}/switch")
def switch_profile(profile_id: int, body: PinRequest, request: Request, db: Session = Depends(get_db)):
    profile = db.get(UserProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found.")
    if profile.pin_hash:
        if not body.pin:
            raise HTTPException(status_code=401, detail="PIN required.")
        from passlib.context import CryptContext
        crypt = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12, deprecated="auto")
        if not crypt.verify(body.pin, profile.pin_hash):
            raise HTTPException(status_code=401, detail="Incorrect PIN.")
    if hasattr(request, "session"):
        request.session[_ACTIVE_PROFILE_KEY] = profile_id
    return {"switched_to": profile_id}
