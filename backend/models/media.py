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
# Leaf entity: MediaItem (one archival file, audio/text/image/video).
# Mirrors GameItem/GameItemBundle deliberately (see backend/models/game.py).
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
    media_item_bundle_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("media_item_bundles.id", ondelete="CASCADE"),
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

    bundle: Optional["MediaItemBundle"] = Relationship(back_populates="items")


class MediaItemCreate(SQLModel):
    title: str
    media_kind: MediaKind
    file_path: str
    file_size_bytes: Optional[int] = None
    cover_art_path: Optional[str] = None
    description: Optional[str] = None
    media_item_bundle_id: Optional[int] = None
    sort_index: int = 0


class MediaItemUpdate(SQLModel):
    title: Optional[str] = None
    cover_art_path: Optional[str] = None
    description: Optional[str] = None
    media_item_bundle_id: Optional[int] = None
    sort_index: Optional[int] = None


def _compute_cover_art_url(cover_art_path: Optional[str]) -> Optional[str]:
    """Same pattern as GameItemRead._compute_cover_art_url: cover art is
    served through main.py's static /media/{file_path} route, which resolves
    any path under LIBRARY_PATH, not specifically the MEDIA_PATH subtree, so
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


class LinkedGameRef(SQLModel):
    """One GameItemBundle a MediaItem/MediaItemBundle is linked to, via MediaLink."""

    link_id: int
    game_item_bundle_id: int
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
    media_item_bundle_id: Optional[int] = None
    sort_index: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tags: list[TagRead] = []
    linked_game: list[LinkedGameRef] = []

    @model_validator(mode="after")
    def _fill_cover_art_url(self) -> "MediaItemRead":
        self.cover_art_url = _compute_cover_art_url(self.cover_art_path)
        return self


# ---------------------------------------------------------------------------
# Parent entity: MediaItemBundle (grouping of same-kind media, e.g. a
# multi-track OST). Mirrors GameItemBundle's items relationship.
# ---------------------------------------------------------------------------


class MediaItemBundle(SQLModel, table=True):
    __tablename__ = "media_item_bundles"

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
        back_populates="bundle",
        sa_relationship_kwargs={
            "order_by": "MediaItem.sort_index",
            "cascade": "all, delete-orphan",
        },
    )


class MediaItemBundleCreate(SQLModel):
    title: str
    media_kind: MediaKind
    description: Optional[str] = None
    cover_art_path: Optional[str] = None


class MediaItemBundleUpdate(SQLModel):
    title: Optional[str] = None
    description: Optional[str] = None
    cover_art_path: Optional[str] = None


class MediaItemBundleRead(SQLModel):
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
    linked_game: list[LinkedGameRef] = []

    @model_validator(mode="after")
    def _fill_cover_art_url(self) -> "MediaItemBundleRead":
        self.cover_art_url = _compute_cover_art_url(self.cover_art_path)
        return self


# ---------------------------------------------------------------------------
# MediaLink, Media <-> Game join. Exactly one of media_item_id /
# media_item_bundle_id must be set per row. A model_validator(mode="after")
# does not fire on direct construction (MediaLink(...) + db.add()) on a
# SQLModel table=True class, same bug class as GameItemBundle.item_type
# (see backend/models/game.py). @validates on each FK field individually
# does not work either: sqlmodel_table_construct() setattr()s every field in
# class-declaration order (media_item_id before media_item_bundle_id), so
# constructing with only the *second*-declared field passed causes the
# first-declared field's validator to fire first, while the second field is
# still unset, it sees both as None and incorrectly raises "neither set"
# before the real value is ever assigned. Whichever field is declared first
# always breaks single-field construction of the *other* field. Fixed the
# same way as GameItemBundle.item_type: a model_post_init override runs
# the check once, after the full object is built and both fields hold their
# final values.
# ---------------------------------------------------------------------------


class MediaLink(SQLModel, table=True):
    __tablename__ = "media_links"

    id: Optional[int] = Field(default=None, primary_key=True)
    media_item_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("media_items.id", ondelete="CASCADE"), nullable=True),
    )
    media_item_bundle_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("media_item_bundles.id", ondelete="CASCADE"), nullable=True),
    )
    game_item_bundle_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("game_item_bundles.id", ondelete="CASCADE"), nullable=False
        )
    )
    link_note: Optional[str] = None

    def model_post_init(self, __context: object) -> None:
        has_item = self.media_item_id is not None
        has_bundle = self.media_item_bundle_id is not None
        if has_item == has_bundle:
            raise ValueError(
                "Exactly one of media_item_id or media_item_bundle_id must be set on a "
                f"MediaLink (got media_item_id={self.media_item_id!r}, "
                f"media_item_bundle_id={self.media_item_bundle_id!r})."
            )


class MediaLinkCreate(SQLModel):
    game_item_bundle_id: int
    link_note: Optional[str] = None


class MediaLinkRead(SQLModel):
    id: int
    media_item_id: Optional[int] = None
    media_item_bundle_id: Optional[int] = None
    game_item_bundle_id: int
    link_note: Optional[str] = None


# ---------------------------------------------------------------------------
# Read-model builders, tags via the generic get_tags_for_entity(_entities)
# helper Game already uses (backend/models/tag.py), called here with the
# "media_item"/"media_item_bundle" entity_type strings.
# ---------------------------------------------------------------------------


def _linked_game_for(
    entity_type: str, entity_id: int, db: "Session"
) -> list[LinkedGameRef]:
    return _linked_game_for_many(entity_type, [entity_id], db).get(entity_id, [])


def _linked_game_for_many(
    entity_type: str, entity_ids: list[int], db: "Session"
) -> dict[int, list[LinkedGameRef]]:
    if not entity_ids:
        return {}
    from sqlalchemy import select as _select

    from backend.models.game import GameItemBundle

    link_col = MediaLink.media_item_id if entity_type == "media_item" else MediaLink.media_item_bundle_id
    rows = db.execute(
        _select(link_col, MediaLink.id, MediaLink.link_note, GameItemBundle)
        .join(GameItemBundle, GameItemBundle.id == MediaLink.game_item_bundle_id)
        .where(link_col.in_(entity_ids))
    ).all()
    result: dict[int, list[LinkedGameRef]] = {}
    for owner_id, link_id, link_note, bundle in rows:
        result.setdefault(owner_id, []).append(
            LinkedGameRef(
                link_id=link_id,
                game_item_bundle_id=bundle.id,
                title=bundle.title,
                slug=bundle.slug,
                link_note=link_note,
            )
        )
    return result


def item_to_read(item: MediaItem, db: "Session") -> MediaItemRead:
    read = MediaItemRead.model_validate(item)
    read.tags = get_tags_for_entity("media_item", item.id, db)
    read.linked_game = _linked_game_for("media_item", item.id, db)
    return read


def items_to_read_bulk(items: list[MediaItem], db: "Session") -> list[MediaItemRead]:
    if not items:
        return []
    item_ids = [i.id for i in items]
    tag_map = get_tags_for_entities("media_item", item_ids, db)
    linked_map = _linked_game_for_many("media_item", item_ids, db)
    reads = []
    for i in items:
        read = MediaItemRead.model_validate(i)
        read.tags = tag_map.get(i.id, [])
        read.linked_game = linked_map.get(i.id, [])
        reads.append(read)
    return reads


def media_item_bundle_to_read(bundle: MediaItemBundle, db: "Session") -> MediaItemBundleRead:
    read = MediaItemBundleRead.model_validate(bundle)
    read.items = items_to_read_bulk(list(bundle.items), db)
    read.tags = get_tags_for_entity("media_item_bundle", bundle.id, db)
    read.linked_game = _linked_game_for("media_item_bundle", bundle.id, db)
    return read


def media_item_bundle_to_read_bulk(
    bundles: list[MediaItemBundle], db: "Session"
) -> list[MediaItemBundleRead]:
    if not bundles:
        return []
    bundle_ids = [c.id for c in bundles]
    tag_map = get_tags_for_entities("media_item_bundle", bundle_ids, db)
    linked_map = _linked_game_for_many("media_item_bundle", bundle_ids, db)
    reads = []
    for c in bundles:
        read = MediaItemBundleRead.model_validate(c)
        read.items = items_to_read_bulk(list(c.items), db)
        read.tags = tag_map.get(c.id, [])
        read.linked_game = linked_map.get(c.id, [])
        reads.append(read)
    return reads
