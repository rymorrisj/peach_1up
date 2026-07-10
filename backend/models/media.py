from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic import model_validator
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlmodel import Field, Relationship, SQLModel

from backend.constants_generated import MediaKind
from backend.models.tag import TagRead, get_tags_for_entities, get_tags_for_entity

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Leaf entity: MediaItem (one archival file — audio/text/image/video).
# Mirrors SoftwareItem/SoftwareCollection deliberately (see backend/models/software.py).
# ---------------------------------------------------------------------------


class MediaItem(SQLModel, table=True):
    __tablename__ = "media_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: Optional[str] = Field(default=None, index=True, unique=True)
    title: str
    media_kind: MediaKind = Field(sa_column=Column(String, nullable=False))
    file_path: str
    file_size_bytes: Optional[int] = None
    cover_art_path: Optional[str] = None
    description: Optional[str] = None
    media_collection_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("media_collections.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    sort_index: int = 0
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )

    collection: Optional["MediaCollection"] = Relationship(back_populates="items")


class MediaItemCreate(SQLModel):
    title: str
    media_kind: MediaKind
    file_path: str
    file_size_bytes: Optional[int] = None
    cover_art_path: Optional[str] = None
    description: Optional[str] = None
    media_collection_id: Optional[int] = None
    sort_index: int = 0


class MediaItemUpdate(SQLModel):
    title: Optional[str] = None
    cover_art_path: Optional[str] = None
    description: Optional[str] = None
    media_collection_id: Optional[int] = None
    sort_index: Optional[int] = None


def _compute_cover_art_url(cover_art_path: Optional[str]) -> Optional[str]:
    """Same pattern as SoftwareItemRead._compute_cover_art_url: cover art is
    served through main.py's static /media/{file_path} route, which resolves
    any path under LIBRARY_PATH — not specifically the MEDIA_PATH subtree — so
    this works unchanged for the Media domain's own MEDIA_PATH-rooted files."""
    if not cover_art_path:
        return None
    try:
        from backend.service.utils import settings as _s

        lib_root = Path(_s.get("LIBRARY_PATH"))
        rel = Path(cover_art_path).resolve().relative_to(lib_root.resolve())
        return "/media/" + rel.as_posix()
    except ValueError:
        return None


class LinkedSoftwareRef(SQLModel):
    """One SoftwareCollection a MediaItem/MediaCollection is linked to, via MediaLink."""

    link_id: int
    software_collection_id: int
    title: str
    slug: Optional[str] = None
    link_note: Optional[str] = None


class MediaItemRead(SQLModel):
    id: int
    slug: Optional[str] = None
    title: str
    media_kind: MediaKind
    file_path: str
    file_size_bytes: Optional[int] = None
    cover_art_path: Optional[str] = None
    cover_art_url: Optional[str] = None
    description: Optional[str] = None
    media_collection_id: Optional[int] = None
    sort_index: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tags: list[TagRead] = []
    linked_software: list[LinkedSoftwareRef] = []

    @model_validator(mode="after")
    def _fill_cover_art_url(self) -> "MediaItemRead":
        self.cover_art_url = _compute_cover_art_url(self.cover_art_path)
        return self


# ---------------------------------------------------------------------------
# Parent entity: MediaCollection (grouping of same-kind media, e.g. a
# multi-track OST). Mirrors SoftwareCollection's items relationship.
# ---------------------------------------------------------------------------


class MediaCollection(SQLModel, table=True):
    __tablename__ = "media_collections"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: Optional[str] = Field(default=None, index=True, unique=True)
    title: str
    media_kind: MediaKind = Field(sa_column=Column(String, nullable=False))
    description: Optional[str] = None
    cover_art_path: Optional[str] = None
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )

    items: list["MediaItem"] = Relationship(
        back_populates="collection",
        sa_relationship_kwargs={
            "order_by": "MediaItem.sort_index",
            "cascade": "all, delete-orphan",
        },
    )


class MediaCollectionCreate(SQLModel):
    title: str
    media_kind: MediaKind
    description: Optional[str] = None
    cover_art_path: Optional[str] = None


class MediaCollectionUpdate(SQLModel):
    title: Optional[str] = None
    description: Optional[str] = None
    cover_art_path: Optional[str] = None


class MediaCollectionRead(SQLModel):
    id: int
    slug: Optional[str] = None
    title: str
    media_kind: MediaKind
    description: Optional[str] = None
    cover_art_path: Optional[str] = None
    cover_art_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    items: list[MediaItemRead] = []
    tags: list[TagRead] = []
    linked_software: list[LinkedSoftwareRef] = []

    @model_validator(mode="after")
    def _fill_cover_art_url(self) -> "MediaCollectionRead":
        self.cover_art_url = _compute_cover_art_url(self.cover_art_path)
        return self


# ---------------------------------------------------------------------------
# MediaLink — Media <-> Software join. Exactly one of media_item_id /
# media_collection_id must be set per row. Validated with a model_validator
# directly on the table model, matching the established pattern in
# backend/models/software.py (SoftwareCollection._derive_item_type_from_era),
# rather than a service-layer check — that is the precedent this codebase
# already follows for a single-row cross-field invariant on a table model.
# ---------------------------------------------------------------------------


class MediaLink(SQLModel, table=True):
    __tablename__ = "media_links"

    id: Optional[int] = Field(default=None, primary_key=True)
    media_item_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("media_items.id", ondelete="CASCADE"), nullable=True),
    )
    media_collection_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("media_collections.id", ondelete="CASCADE"), nullable=True),
    )
    software_collection_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("software_collections.id", ondelete="CASCADE"), nullable=False
        )
    )
    link_note: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "MediaLink":
        has_item = self.media_item_id is not None
        has_collection = self.media_collection_id is not None
        if has_item == has_collection:
            raise ValueError(
                "Exactly one of media_item_id or media_collection_id must be set on a "
                f"MediaLink (got media_item_id={self.media_item_id!r}, "
                f"media_collection_id={self.media_collection_id!r})."
            )
        return self


class MediaLinkCreate(SQLModel):
    software_collection_id: int
    link_note: Optional[str] = None


class MediaLinkRead(SQLModel):
    id: int
    media_item_id: Optional[int] = None
    media_collection_id: Optional[int] = None
    software_collection_id: int
    link_note: Optional[str] = None


# ---------------------------------------------------------------------------
# Read-model builders — tags via the generic get_tags_for_entity(_entities)
# helper Software already uses (backend/models/tag.py), called here with the
# new "media_item"/"media_collection" entity_type strings.
# ---------------------------------------------------------------------------


def _linked_software_for(
    entity_type: str, entity_id: int, db: "Session"
) -> list[LinkedSoftwareRef]:
    return _linked_software_for_many(entity_type, [entity_id], db).get(entity_id, [])


def _linked_software_for_many(
    entity_type: str, entity_ids: list[int], db: "Session"
) -> dict[int, list[LinkedSoftwareRef]]:
    if not entity_ids:
        return {}
    from sqlalchemy import select as _select

    from backend.models.software import SoftwareCollection

    link_col = MediaLink.media_item_id if entity_type == "media_item" else MediaLink.media_collection_id
    rows = db.execute(
        _select(link_col, MediaLink.id, MediaLink.link_note, SoftwareCollection)
        .join(SoftwareCollection, SoftwareCollection.id == MediaLink.software_collection_id)
        .where(link_col.in_(entity_ids))
    ).all()
    result: dict[int, list[LinkedSoftwareRef]] = {}
    for owner_id, link_id, link_note, collection in rows:
        result.setdefault(owner_id, []).append(
            LinkedSoftwareRef(
                link_id=link_id,
                software_collection_id=collection.id,
                title=collection.title,
                slug=collection.slug,
                link_note=link_note,
            )
        )
    return result


def item_to_read(item: MediaItem, db: "Session") -> MediaItemRead:
    read = MediaItemRead.model_validate(item)
    read.tags = get_tags_for_entity("media_item", item.id, db)
    read.linked_software = _linked_software_for("media_item", item.id, db)
    return read


def items_to_read_bulk(items: list[MediaItem], db: "Session") -> list[MediaItemRead]:
    if not items:
        return []
    item_ids = [i.id for i in items]
    tag_map = get_tags_for_entities("media_item", item_ids, db)
    linked_map = _linked_software_for_many("media_item", item_ids, db)
    reads = []
    for i in items:
        read = MediaItemRead.model_validate(i)
        read.tags = tag_map.get(i.id, [])
        read.linked_software = linked_map.get(i.id, [])
        reads.append(read)
    return reads


def collection_to_read(collection: MediaCollection, db: "Session") -> MediaCollectionRead:
    read = MediaCollectionRead.model_validate(collection)
    read.items = items_to_read_bulk(list(collection.items), db)
    read.tags = get_tags_for_entity("media_collection", collection.id, db)
    read.linked_software = _linked_software_for("media_collection", collection.id, db)
    return read


def collections_to_read_bulk(
    collections: list[MediaCollection], db: "Session"
) -> list[MediaCollectionRead]:
    if not collections:
        return []
    collection_ids = [c.id for c in collections]
    tag_map = get_tags_for_entities("media_collection", collection_ids, db)
    linked_map = _linked_software_for_many("media_collection", collection_ids, db)
    reads = []
    for c in collections:
        read = MediaCollectionRead.model_validate(c)
        read.items = items_to_read_bulk(list(c.items), db)
        read.tags = tag_map.get(c.id, [])
        read.linked_software = linked_map.get(c.id, [])
        reads.append(read)
    return reads
