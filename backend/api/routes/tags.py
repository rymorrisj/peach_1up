from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission
from backend.models.library import LibraryItem
from backend.models.tag import LibraryItemTag, Tag, TagCreate, TagRead
from backend.models.user import User

router = APIRouter(prefix="/api/v1/tags", tags=["tags"])


def _tag_read(tag: Tag, db: Session) -> TagRead:
    count = (
        db.query(func.count(LibraryItemTag.library_item_id))
        .filter(LibraryItemTag.tag_id == tag.id)
        .scalar()
        or 0
    )
    return TagRead(id=tag.id, name=tag.name, item_count=count)


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
    tag = Tag(name=name)
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
    db.delete(tag)
    db.commit()


@router.post("/{tag_id}/items/{item_id}", status_code=204)
def add_tag_to_item(
    tag_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    if not db.get(Tag, tag_id):
        raise HTTPException(status_code=404, detail="Tag not found.")
    if not db.get(LibraryItem, item_id):
        raise HTTPException(status_code=404, detail="Library item not found.")
    exists = (
        db.query(LibraryItemTag)
        .filter(LibraryItemTag.tag_id == tag_id, LibraryItemTag.library_item_id == item_id)
        .first()
    )
    if not exists:
        db.add(LibraryItemTag(tag_id=tag_id, library_item_id=item_id))
        db.commit()


@router.delete("/{tag_id}/items/{item_id}", status_code=204)
def remove_tag_from_item(
    tag_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    link = (
        db.query(LibraryItemTag)
        .filter(LibraryItemTag.tag_id == tag_id, LibraryItemTag.library_item_id == item_id)
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Tag not assigned to this item.")
    db.delete(link)
    db.commit()
