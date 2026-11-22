from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import (
    get_active_user, get_filtered_entity_query, reject_old_era_query_param, require_permission,
)
from backend.models.launch_history import LaunchHistory
from backend.models.game import GameItemBundle, GameItemBundleRead, game_item_bundles_to_read_bulk
from backend.models.pagination import Page
from backend.models.profile import ProfileItem, ProfileItemCreate, ProfileItemRead, ProfileItemUpdate
from backend.models.user import UserItem
from backend.service.utils.slug_generator import unique_slug

router = APIRouter(prefix="/api/v1/profile-items", tags=["profiles"])


def _visible_games(viewer: UserItem, db: Session):
    """GameItemBundle query narrowed to what *viewer* may see, so a profile's
    item listing and item_count never include or count a hidden game."""
    return get_filtered_entity_query("game_item_bundle", viewer, db)


def _with_stats(profile: ProfileItem, db: Session, viewer: UserItem) -> ProfileItemRead:
    item_count = _visible_games(viewer, db).filter(GameItemBundle.profile_item_id == profile.id).count()
    total_launches, last_launched_at = db.query(
        func.count(LaunchHistory.id),
        func.max(LaunchHistory.started_at),
    ).filter(LaunchHistory.profile_item_id == profile.id).one()
    read = ProfileItemRead.model_validate(profile)
    read.item_count = item_count or 0
    read.total_launches = int(total_launches or 0)
    read.last_launched_at = last_launched_at
    return read


def _with_stats_bulk(profiles: list[ProfileItem], db: Session, viewer: UserItem) -> list[ProfileItemRead]:
    ids = [p.id for p in profiles]
    if not ids:
        return []

    item_counts = dict(
        _visible_games(viewer, db)
        .with_entities(GameItemBundle.profile_item_id, func.count(GameItemBundle.id))
        .filter(GameItemBundle.profile_item_id.in_(ids))
        .group_by(GameItemBundle.profile_item_id)
        .all()
    )
    launch_stats = {
        profile_item_id: (total, last)
        for profile_item_id, total, last in db.query(
            LaunchHistory.profile_item_id,
            func.count(LaunchHistory.id),
            func.max(LaunchHistory.started_at),
        )
        .filter(LaunchHistory.profile_item_id.in_(ids))
        .group_by(LaunchHistory.profile_item_id)
        .all()
    }

    results = []
    for profile in profiles:
        total_launches, last_launched_at = launch_stats.get(profile.id, (0, None))
        read = ProfileItemRead.model_validate(profile)
        read.item_count = item_counts.get(profile.id, 0)
        read.total_launches = int(total_launches or 0)
        read.last_launched_at = last_launched_at
        results.append(read)
    return results


@router.get("", response_model=Page[ProfileItemRead], dependencies=[Depends(reject_old_era_query_param)])
def list_profiles(
    platform: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    q = db.query(ProfileItem)
    if platform:
        q = q.filter(ProfileItem.platform == platform)
    total = q.count()
    rows = q.order_by(ProfileItem.id).offset(offset).limit(limit).all()
    return Page(items=_with_stats_bulk(rows, db, active_user), total=total, limit=limit, offset=offset)


@router.post("", response_model=ProfileItemRead, status_code=201)
def create_profile(body: ProfileItemCreate, db: Session = Depends(get_db), _: UserItem = require_permission("can_manage_game")):
    existing = db.query(ProfileItem).filter(ProfileItem.slug == body.slug).first()
    if existing:
        raise HTTPException(status_code=409, detail="Profile slug already exists.")
    profile = ProfileItem(**body.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/{slug}", response_model=ProfileItemRead)
def get_profile(slug: str, db: Session = Depends(get_db), active_user: UserItem = Depends(get_active_user)):
    profile = db.query(ProfileItem).filter(ProfileItem.slug == slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return _with_stats(profile, db, active_user)


@router.get("/{slug}/items", response_model=Page[GameItemBundleRead])
def get_profile_items(
    slug: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    profile = db.query(ProfileItem).filter(ProfileItem.slug == slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    # Only games the viewer can see, so a hidden title is never listed or counted.
    q = _visible_games(active_user, db).filter(GameItemBundle.profile_item_id == profile.id)
    total = q.count()
    rows = q.order_by(GameItemBundle.id).offset(offset).limit(limit).all()
    return Page(items=game_item_bundles_to_read_bulk(rows, db, viewer=active_user), total=total, limit=limit, offset=offset)


@router.patch("/{slug}", response_model=ProfileItemRead)
def update_profile(
    slug: str,
    body: ProfileItemUpdate,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_game"),
):
    profile = db.query(ProfileItem).filter(ProfileItem.slug == slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(profile, key, value)
    if 'name' in updates:
        profile.slug = unique_slug(
            profile.name,
            lambda s: db.query(ProfileItem).filter(ProfileItem.slug == s, ProfileItem.id != profile.id).first() is not None,
            fallback="profile",
        )
    db.commit()
    db.refresh(profile)
    return _with_stats(profile, db, active_user)


@router.delete("/{slug}", status_code=204)
def delete_profile(slug: str, db: Session = Depends(get_db), _: UserItem = require_permission("can_manage_game")):
    profile = db.query(ProfileItem).filter(ProfileItem.slug == slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    if profile.is_bundled:
        raise HTTPException(status_code=403, detail="Bundled profiles cannot be deleted.")
    db.delete(profile)
    db.commit()
