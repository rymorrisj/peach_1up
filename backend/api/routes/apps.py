from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission
from backend.models.app import (
    AppItemBundle, AppItemBundleCreate, AppItemBundleRead, AppItemBundleUpdate,
    AppItem, AppItemRead, AppItemUpdate, app_item_bundle_to_read, app_item_bundles_to_read_bulk,
)
from backend.models.pagination import Page
from backend.models.user import UserItem
from backend.service.apps import items as app_svc
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL

router = APIRouter(prefix="/api/v1", tags=["apps"])


# ---------------------------------------------------------------------------
# List + create
# ---------------------------------------------------------------------------


@router.get("/app-items", response_model=Page[AppItemBundleRead])
def list_apps(
    environment_item_id: int | None = None,
    category: str | None = None,
    tag: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    q = db.query(AppItemBundle)
    if environment_item_id is not None:
        q = q.filter(AppItemBundle.environment_item_id == environment_item_id)
    if category:
        q = q.filter(AppItemBundle.category == category)
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
    rows = q.order_by(AppItemBundle.id).offset(offset).limit(limit).all()
    return Page(items=app_item_bundles_to_read_bulk(rows, db), total=total, limit=limit, offset=offset)


@router.post("/app-items", response_model=AppItemBundleRead, status_code=201)
def create_app_item_bundle(
    body: AppItemBundleCreate,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_app"),
):
    collection = app_svc.create_app_item_bundle(body, db)
    return app_item_bundle_to_read(collection, db)


# ---------------------------------------------------------------------------
# Single-collection read / update / delete
# ---------------------------------------------------------------------------


@router.get("/app-item-bundle/{collection_id}", response_model=AppItemBundleRead)
def get_app_item_bundle(
    collection_id: int,
    db: Session = Depends(get_db),
    _: UserItem = Depends(get_active_user),
):
    collection = db.get(AppItemBundle, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="App collection not found.")
    return app_item_bundle_to_read(collection, db)


@router.patch("/app-item-bundle/{collection_id}", response_model=AppItemBundleRead)
def update_app_item_bundle(
    collection_id: int,
    body: AppItemBundleUpdate,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_app"),
):
    return app_item_bundle_to_read(app_svc.update_app_item_bundle(collection_id, body, db), db)


@router.post("/app-item-bundle/{collection_id}/confirm-delete")
def issue_delete_token(
    collection_id: int,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_app"),
):
    collection = db.get(AppItemBundle, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="App collection not found.")
    token = confirmation_tokens.issue("app_item_bundle", collection_id)
    return {"confirmation_token": token, "expires_in_seconds": TOKEN_TTL}


@router.delete("/app-item-bundle/{collection_id}", status_code=204)
def delete_app_item_bundle(
    collection_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_app"),
):
    app_svc.delete_app_item_bundle(collection_id, confirmation_token, db)


# ---------------------------------------------------------------------------
# Single-item read / update
# ---------------------------------------------------------------------------


def _visible_leaf(leaf_id: int, db: Session) -> AppItem:
    leaf = db.get(AppItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="App item not found.")
    return leaf


@router.get("/app-item/{leaf_id}", response_model=AppItemRead)
def get_app_item(
    leaf_id: int,
    db: Session = Depends(get_db),
    _: UserItem = Depends(get_active_user),
):
    return AppItemRead.model_validate(_visible_leaf(leaf_id, db))


@router.patch("/app-item/{leaf_id}", response_model=AppItemRead)
def update_app_item(
    leaf_id: int,
    body: AppItemUpdate,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_app"),
):
    leaf = db.get(AppItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="App item not found.")
    return AppItemRead.model_validate(app_svc.update_app_leaf(leaf.app_item_bundle_id, leaf_id, body, db))


@router.delete("/app-item/{leaf_id}", status_code=204)
def delete_app_item(
    leaf_id: int,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_app"),
):
    leaf = db.get(AppItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="App item not found.")
    db.delete(leaf)
    db.commit()
