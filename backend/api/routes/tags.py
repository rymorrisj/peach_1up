from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission
from backend.models.library import LibraryCollection
from backend.models.tag import EntityTag, Tag, TagCreate, TagRead
from backend.models.user import User

router = APIRouter(prefix="/api/v1/tags", tags=["tags"])


def _tag_read(tag: Tag, db: Session) -> TagRead:
    count = (
        db.query(func.count(EntityTag.entity_id))
        .filter(EntityTag.tag_id == tag.id)
        .scalar()
        or 0
    )
    return TagRead(id=tag.id, name=tag.name, color=tag.color, item_count=count, is_system=tag.is_system)


@router.get("", response_model=list[TagRead])
def list_tags(db: Session = Depends(get_db), _: User = Depends(get_active_user)):
    tags = db.query(Tag).order_by(Tag.name).all()
    return [_tag_read(t, db) for t in tags]


@router.post("", response_model=TagRead, status_code=201)
def create_tag(
    body: TagCreate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tag name cannot be blank.")
    if db.query(Tag).filter(Tag.name == name).first():
        raise HTTPException(status_code=409, detail="A tag with that name already exists.")
    tag = Tag(name=name, color=body.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return _tag_read(tag, db)


@router.delete("/{tag_id}", status_code=204)
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found.")
    if tag.is_system:
        raise HTTPException(status_code=403, detail="System tags cannot be deleted.")
    db.delete(tag)
    db.commit()


@router.post("/{tag_id}/collections/{collection_id}", status_code=204)
def add_tag_to_collection(
    tag_id: int,
    collection_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    if not db.get(Tag, tag_id):
        raise HTTPException(status_code=404, detail="Tag not found.")
    if not db.get(LibraryCollection, collection_id):
        raise HTTPException(status_code=404, detail="Library collection not found.")
    exists = (
        db.query(EntityTag)
        .filter(
            EntityTag.tag_id == tag_id,
            EntityTag.entity_type == "library_collection",
            EntityTag.entity_id == collection_id,
        )
        .first()
    )
    if not exists:
        db.add(EntityTag(tag_id=tag_id, entity_type="library_collection", entity_id=collection_id))
        db.commit()


@router.delete("/{tag_id}/collections/{collection_id}", status_code=204)
def remove_tag_from_collection(
    tag_id: int,
    collection_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    link = (
        db.query(EntityTag)
        .filter(
            EntityTag.tag_id == tag_id,
            EntityTag.entity_type == "library_collection",
            EntityTag.entity_id == collection_id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Tag not assigned to this collection.")
    db.delete(link)
    db.commit()
