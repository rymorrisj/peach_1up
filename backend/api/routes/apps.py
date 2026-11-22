from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import (
    get_active_user, get_filtered_app_item, get_filtered_app_items, get_filtered_entity, reject_old_era_query_param,
    require_permission,
)
from backend.models.app import (
    AppItemBundle, AppItemBundleCreate, AppItemBundleRead, AppItemBundleUpdate,
    AppItem, AppItemRead, AppItemUpdate, app_item_bundle_to_read, app_item_bundles_to_read_bulk,
)
from backend.models.pagination import Page
from backend.models.user import UserItem
from backend.service.apps import items as app_svc
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL
from backend.service.utils.sort_utils import apply_bundle_sort

router = APIRouter(prefix="/api/v1", tags=["apps"])


# ---------------------------------------------------------------------------
# List + create
# ---------------------------------------------------------------------------


@router.get("/app-items", response_model=Page[AppItemBundleRead], dependencies=[Depends(reject_old_era_query_param)])
def list_apps(
    platform: str | None = None,
    environment_item_id: int | None = None,
    category: str | None = None,
    tag: str | None = None,
    profile_assigned: bool | None = None,
    sort: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    q = get_filtered_app_items(active_user, db)
    if platform:
        q = q.filter(AppItemBundle.platform == platform)
    if environment_item_id is not None:
        q = q.filter(AppItemBundle.environment_item_id == environment_item_id)
    if category:
        q = q.filter(AppItemBundle.category == category)
    if profile_assigned is True:
        q = q.filter(AppItemBundle.profile_item_id.isnot(None))
    elif profile_assigned is False:
        q = q.filter(AppItemBundle.profile_item_id.is_(None))
    if tag:
        from backend.models.tag import EntityTag, Tag
        subq = (
            db.query(EntityTag.entity_id)
            .join(Tag, EntityTag.tag_id == Tag.id)
            .filter(EntityTag.entity_type == "app_item_bundle", Tag.name == tag)
            .subquery()
        )
        q = q.filter(AppItemBundle.id.in_(subq))
    total = q.count()
    rows = apply_bundle_sort(q, AppItemBundle, sort).offset(offset).limit(limit).all()
    return Page(items=app_item_bundles_to_read_bulk(rows, db, viewer=active_user), total=total, limit=limit, offset=offset)


@router.post("/app-items", response_model=AppItemBundleRead, status_code=201)
def create_app_item_bundle(
    body: AppItemBundleCreate,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_app"),
):
    collection = app_svc.create_app_item_bundle(body, db)
    return app_item_bundle_to_read(collection, db, viewer=active_user)


# ---------------------------------------------------------------------------
# Single-collection read / update / delete
# ---------------------------------------------------------------------------


@router.get("/app-item-bundle/{collection_id}", response_model=AppItemBundleRead)
def get_app_item_bundle(
    collection_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    return app_item_bundle_to_read(get_filtered_app_item(collection_id, active_user, db), db, viewer=active_user)


@router.patch("/app-item-bundle/{collection_id}", response_model=AppItemBundleRead)
def update_app_item_bundle(
    collection_id: int,
    body: AppItemBundleUpdate,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_app"),
):
    # Same 404 as a missing bundle, so a hidden bundle is neither patchable
    # nor confirmed to exist.
    get_filtered_app_item(collection_id, active_user, db)
    return app_item_bundle_to_read(
        app_svc.update_app_item_bundle(collection_id, body, db), db, viewer=active_user,
    )


@router.post("/app-item-bundle/{collection_id}/confirm-delete")
def issue_delete_token(
    collection_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_app"),
):
    get_filtered_app_item(collection_id, active_user, db)
    token = confirmation_tokens.issue("app_item_bundle", collection_id)
    return {"confirmation_token": token, "expires_in_seconds": TOKEN_TTL}


@router.delete("/app-item-bundle/{collection_id}", status_code=204)
def delete_app_item_bundle(
    collection_id: int,
    confirmation_token: str = Query(...),
    delete_media: bool | None = Query(None),
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_app"),
):
    """*delete_media*, when given, applies to this delete only and is never
    persisted (see DELETE /game-item-bundle/{id})."""
    # Checked before the service consumes the token, so a hidden bundle
    # 404s exactly like a missing one and the token stays unspent.
    get_filtered_app_item(collection_id, active_user, db)
    app_svc.delete_app_item_bundle(collection_id, confirmation_token, db, delete_media=delete_media)


# ---------------------------------------------------------------------------
# Single-item read / update
# ---------------------------------------------------------------------------


def _visible_leaf(leaf_id: int, active_user: UserItem, db: Session) -> AppItem:
    """Return a leaf whose parent bundle the caller is allowed to see, else
    the same 404 as a missing leaf (a hidden parent must not answer with the
    bundle's own "not found" detail, which would reveal the leaf exists)."""
    try:
        return get_filtered_entity("app_item", leaf_id, active_user, db)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="App item not found.") from None
        raise


@router.get("/app-item/{leaf_id}", response_model=AppItemRead)
def get_app_item(
    leaf_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    return AppItemRead.model_validate(_visible_leaf(leaf_id, active_user, db))


@router.patch("/app-item/{leaf_id}", response_model=AppItemRead)
def update_app_item(
    leaf_id: int,
    body: AppItemUpdate,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_app"),
):
    leaf = _visible_leaf(leaf_id, active_user, db)
    return AppItemRead.model_validate(app_svc.update_app_leaf(leaf.app_item_bundle_id, leaf_id, body, db))


@router.delete("/app-item/{leaf_id}", status_code=204)
def delete_app_item(
    leaf_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_app"),
):
    leaf = _visible_leaf(leaf_id, active_user, db)
    db.delete(leaf)
    db.commit()
