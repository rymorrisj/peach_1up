from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import require_permission
from backend.models.profile import Profile, ProfileCreate, ProfileRead, ProfileUpdate
from backend.models.user import User

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileRead])
def list_profiles(era: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Profile)
    if era:
        q = q.filter(Profile.era == era)
    return q.all()


@router.post("", response_model=ProfileRead, status_code=201)
def create_profile(body: ProfileCreate, db: Session = Depends(get_db), _: User = require_permission("can_manage_profiles")):
    existing = db.query(Profile).filter(Profile.slug == body.slug).first()
    if existing:
        raise HTTPException(status_code=409, detail="Profile slug already exists.")
    profile = Profile(**body.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/{slug}", response_model=ProfileRead)
def get_profile(slug: str, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.slug == slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return profile


@router.patch("/{slug}", response_model=ProfileRead)
def update_profile(slug: str, body: ProfileUpdate, db: Session = Depends(get_db), _: User = require_permission("can_manage_profiles")):
    profile = db.query(Profile).filter(Profile.slug == slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


@router.delete("/{slug}", status_code=204)
def delete_profile(slug: str, db: Session = Depends(get_db), _: User = require_permission("can_manage_profiles")):
    profile = db.query(Profile).filter(Profile.slug == slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    if profile.is_bundled:
        raise HTTPException(status_code=403, detail="Bundled profiles cannot be deleted.")
    db.delete(profile)
    db.commit()
