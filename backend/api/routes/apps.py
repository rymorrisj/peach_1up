from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission
from backend.models.app import (
    AppCollection, AppCollectionCreate, AppCollectionRead, AppCollectionUpdate,
    AppItem, AppItemRead, AppItemUpdate, app_to_read, apps_to_read_bulk,
)
from backend.models.pagination import Page
from backend.models.user import User
from backend.service.apps import items as app_svc
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL

router = APIRouter(prefix="/api/v1", tags=["apps"])


# ---------------------------------------------------------------------------
# List + create
# ---------------------------------------------------------------------------


@router.get("/apps", response_model=Page[AppCollectionRead])
def list_apps(
    environment_id: int | None = None,
    category: str | None = None,
    tag: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    q = db.query(AppCollection)
    if environment_id is not None:
        q = q.filter(AppCollection.environment_id == environment_id)
    if category:
        q = q.filter(AppCollection.category == category)
    if tag:
        from backend.models.tag import EntityTag, Tag
        subq = (
            db.query(EntityTag.entity_id)
            .join(Tag, EntityTag.tag_id == Tag.id)
            .filter(EntityTag.entity_type == "app_collection", Tag.name == tag)
            .subquery()
        )
        q = q.filter(AppCollection.id.in_(subq))
    total = q.count()
    rows = q.order_by(AppCollection.id).offset(offset).limit(limit).all()
    return Page(items=apps_to_read_bulk(rows, db), total=total, limit=limit, offset=offset)


@router.post("/apps", response_model=AppCollectionRead, status_code=201)
def create_app(
    body: AppCollectionCreate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_manage_apps"),
):
    collection = app_svc.create_app_collection(body, db)
    return app_to_read(collection, db)


# ---------------------------------------------------------------------------
# Single-collection read / update / delete
# ---------------------------------------------------------------------------


@router.get("/appcollection/{collection_id}", response_model=AppCollectionRead)
def get_app(
    collection_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    collection = db.get(AppCollection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="App collection not found.")
    return app_to_read(collection, db)


@router.patch("/appcollection/{collection_id}", response_model=AppCollectionRead)
def update_app(
    collection_id: int,
    body: AppCollectionUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_manage_apps"),
):
    return app_to_read(app_svc.update_app_collection(collection_id, body, db), db)


@router.post("/appcollection/{collection_id}/confirm-delete")
def issue_delete_token(
    collection_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_manage_apps"),
):
    collection = db.get(AppCollection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="App collection not found.")
    token = confirmation_tokens.issue("app_collection", collection_id)
    return {"confirmation_token": token, "expires_in_seconds": TOKEN_TTL}


@router.delete("/appcollection/{collection_id}", status_code=204)
def delete_app(
    collection_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_manage_apps"),
):
    app_svc.delete_app_collection(collection_id, confirmation_token, db)


# ---------------------------------------------------------------------------
# Single-item read / update
# ---------------------------------------------------------------------------


def _visible_leaf(leaf_id: int, db: Session) -> AppItem:
    leaf = db.get(AppItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="App item not found.")
    return leaf


@router.get("/appitem/{leaf_id}", response_model=AppItemRead)
def get_app_item(
    leaf_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    return AppItemRead.model_validate(_visible_leaf(leaf_id, db))


@router.patch("/appitem/{leaf_id}", response_model=AppItemRead)
def update_app_item(
    leaf_id: int,
    body: AppItemUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_manage_apps"),
):
    leaf = db.get(AppItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="App item not found.")
    return AppItemRead.model_validate(app_svc.update_app_leaf(leaf.app_collection_id, leaf_id, body, db))


@router.delete("/appitem/{leaf_id}", status_code=204)
def delete_app_item(
    leaf_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_manage_apps"),
):
    leaf = db.get(AppItem, leaf_id)
    if leaf is None:
        raise HTTPException(status_code=404, detail="App item not found.")
    db.delete(leaf)
    db.commit()
