from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission
from backend.models.launch_history import LaunchHistory
from backend.models.library import LibraryCollection, LibraryCollectionRead, collections_to_read_bulk
from backend.models.pagination import Page
from backend.models.profile import Profile, ProfileCreate, ProfileRead, ProfileUpdate
from backend.models.user import User
from backend.service.utils.slug_generator import unique_slug

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


def _with_stats(profile: Profile, db: Session) -> ProfileRead:
    (item_count,) = db.query(func.count(LibraryCollection.id)).filter(LibraryCollection.profile_id == profile.id).one()
    total_launches, last_launched_at = db.query(
        func.count(LaunchHistory.id),
        func.max(LaunchHistory.started_at),
    ).filter(LaunchHistory.profile_id == profile.id).one()
    read = ProfileRead.model_validate(profile)
    read.item_count = item_count or 0
    read.total_launches = int(total_launches or 0)
    read.last_launched_at = last_launched_at
    return read


def _with_stats_bulk(profiles: list[Profile], db: Session) -> list[ProfileRead]:
    ids = [p.id for p in profiles]
    if not ids:
        return []

    item_counts = dict(
        db.query(LibraryCollection.profile_id, func.count(LibraryCollection.id))
        .filter(LibraryCollection.profile_id.in_(ids))
        .group_by(LibraryCollection.profile_id)
        .all()
    )
    launch_stats = {
        profile_id: (total, last)
        for profile_id, total, last in db.query(
            LaunchHistory.profile_id,
            func.count(LaunchHistory.id),
            func.max(LaunchHistory.started_at),
        )
        .filter(LaunchHistory.profile_id.in_(ids))
        .group_by(LaunchHistory.profile_id)
        .all()
    }

    results = []
    for profile in profiles:
        total_launches, last_launched_at = launch_stats.get(profile.id, (0, None))
        read = ProfileRead.model_validate(profile)
        read.item_count = item_counts.get(profile.id, 0)
        read.total_launches = int(total_launches or 0)
        read.last_launched_at = last_launched_at
        results.append(read)
    return results


@router.get("", response_model=list[ProfileRead])
def list_profiles(era: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_active_user)):
    q = db.query(Profile)
    if era:
        q = q.filter(Profile.era == era)
    return _with_stats_bulk(q.all(), db)


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
def get_profile(slug: str, db: Session = Depends(get_db), _: User = Depends(get_active_user)):
    profile = db.query(Profile).filter(Profile.slug == slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return _with_stats(profile, db)


@router.get("/{slug}/items", response_model=Page[LibraryCollectionRead])
def get_profile_items(
    slug: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    profile = db.query(Profile).filter(Profile.slug == slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    q = db.query(LibraryCollection).filter(LibraryCollection.profile_id == profile.id)
    total = q.count()
    rows = q.order_by(LibraryCollection.id).offset(offset).limit(limit).all()
    return Page(items=collections_to_read_bulk(rows, db), total=total, limit=limit, offset=offset)


@router.patch("/{slug}", response_model=ProfileRead)
def update_profile(slug: str, body: ProfileUpdate, db: Session = Depends(get_db), _: User = require_permission("can_manage_profiles")):
    profile = db.query(Profile).filter(Profile.slug == slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(profile, key, value)
    if 'name' in updates:
        profile.slug = unique_slug(
            profile.name,
            lambda s: db.query(Profile).filter(Profile.slug == s, Profile.id != profile.id).first() is not None,
            fallback="profile",
        )
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
