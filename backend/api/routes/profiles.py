import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import require_permission
from backend.models.launch_history import LaunchHistory
from backend.models.library import LibraryItem, LibraryItemRead
from backend.models.profile import Profile, ProfileCreate, ProfileRead, ProfileUpdate
from backend.models.user import User

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


def _with_stats(profile: Profile, db: Session) -> ProfileRead:
    (item_count,) = db.query(func.count(LibraryItem.id)).filter(LibraryItem.profile_id == profile.id).one()
    total_launches, last_launched_at = db.query(
        func.count(LaunchHistory.id),
        func.max(LaunchHistory.started_at),
    ).filter(LaunchHistory.profile_id == profile.id).one()
    read = ProfileRead.model_validate(profile)
    read.item_count = item_count or 0
    read.total_launches = int(total_launches or 0)
    read.last_launched_at = last_launched_at
    return read


def _slugify(name: str) -> str:
    s = re.sub(r'\s+', '-', name.lower())
    return re.sub(r'[^a-z0-9-]', '', s)


def _unique_slug(base: str, exclude_id: int, db: Session) -> str:
    candidate = base
    n = 2
    while db.query(Profile).filter(Profile.slug == candidate, Profile.id != exclude_id).first():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


@router.get("", response_model=list[ProfileRead])
def list_profiles(era: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Profile)
    if era:
        q = q.filter(Profile.era == era)
    return [_with_stats(p, db) for p in q.all()]


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
    return _with_stats(profile, db)


@router.get("/{slug}/items", response_model=list[LibraryItemRead])
def get_profile_items(slug: str, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.slug == slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return db.query(LibraryItem).filter(LibraryItem.profile_id == profile.id).all()


@router.patch("/{slug}", response_model=ProfileRead)
def update_profile(slug: str, body: ProfileUpdate, db: Session = Depends(get_db), _: User = require_permission("can_manage_profiles")):
    profile = db.query(Profile).filter(Profile.slug == slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(profile, key, value)
    if 'name' in updates:
        profile.slug = _unique_slug(_slugify(profile.name), profile.id, db)
    db.commit()
    db.refresh(profile)
    return _with_stats(profile, db)


@router.delete("/{slug}", status_code=204)
def delete_profile(slug: str, db: Session = Depends(get_db), _: User = require_permission("can_manage_profiles")):
    profile = db.query(Profile).filter(Profile.slug == slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    if profile.is_bundled:
        raise HTTPException(status_code=403, detail="Bundled profiles cannot be deleted.")
    db.delete(profile)
    db.commit()
