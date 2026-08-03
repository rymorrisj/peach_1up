from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic import model_validator
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, and_, func, or_
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


def _compute_media_url(path: Optional[str]) -> Optional[str]:
    """Resolve any library-rooted absolute path to its servable /media/{file_path}
    URL (main.py's static route, which resolves any path under LIBRARY_PATH, not
    specifically the MEDIA_PATH subtree). Shared by cover_art_url and file_url on
    both MediaItemRead and MediaItemBundleRead, one path-resolution rule instead
    of a copy per field."""
    if not path:
        return None
    try:
        from backend.service.utils import settings as _s

        lib_root = Path(_s.get("LIBRARY_PATH"))
        resolved = Path(path).resolve()
        rel = resolved.relative_to(lib_root.resolve())
        if not resolved.exists():
            return None
        return "/media/" + rel.as_posix()
    except ValueError:
        return None


class LinkedEntityRef(SQLModel):
    """One counterpart entity a linked entity is connected to via MediaLink.

    entity_type/entity_id name the counterpart (never the entity this ref is
    attached to on a given Read model)."""

    link_id: int
    entity_type: str
    entity_id: int
    title: str
    slug: Optional[str] = None
    link_note: Optional[str] = None


class MediaItemRead(SQLModel):
    id: int
    slug: Optional[str] = None
    title: str
    media_kind: MediaKind
    file_path: str
    file_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    cover_art_path: Optional[str] = None
    cover_art_url: Optional[str] = None
    description: Optional[str] = None
    media_item_bundle_id: Optional[int] = None
    sort_index: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tags: list[TagRead] = []
    linked_items: list[LinkedEntityRef] = []

    @model_validator(mode="after")
    def _fill_computed_urls(self) -> "MediaItemRead":
        self.cover_art_url = _compute_media_url(self.cover_art_path)
        self.file_url = _compute_media_url(self.file_path)
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
    linked_items: list[LinkedEntityRef] = []

    @model_validator(mode="after")
    def _fill_cover_art_url(self) -> "MediaItemBundleRead":
        self.cover_art_url = _compute_media_url(self.cover_art_path)
        return self


# ---------------------------------------------------------------------------
# MediaLink, polymorphic entity-to-entity join (Media <-> Game, Media <-> App,
# Media <-> Media, ...). entity_a/entity_b are unordered from a caller's
# perspective; make_entity_link() below is the only supported way to build a
# row, since it applies the canonical-ordering rule every write path
# (backend/api/routes/entity_links.py, the delete-cleanup call sites below)
# depends on: a self-referential pair (e.g. two MediaItem rows) always lands
# sorted ascending by (entity_type, entity_id) as entity_a/entity_b, so the
# same pair can never be stored twice under swapped columns, and a lookup
# never needs to check both orderings for a duplicate.
#
# No DB-level foreign key on either pair, matching EntityTag's documented
# reasoning exactly (backend/models/tag.py): SQLite cannot FK one column to
# multiple target tables, so integrity (existence, cascade-on-delete) is
# enforced at the application layer instead. Unlike EntityTag, a stale
# MediaLink row is not just inert decoration, it would resurface as a wrong,
# clickable deeplink if its entity_id were ever reused, so callers deleting
# an entity that can appear on either side of a link MUST call
# delete_links_for() first; see backend/service/games/items.py's
# delete_library_collection, backend/service/apps/items.py's
# delete_app_item_bundle, and this module's delete_media_item(_bundle) below.
# ---------------------------------------------------------------------------


class MediaLink(SQLModel, table=True):
    __tablename__ = "media_links"
    __table_args__ = (
        UniqueConstraint("entity_a_type", "entity_a_id", "entity_b_type", "entity_b_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    entity_a_type: str = Field(sa_column=Column(String, nullable=False, index=True))
    entity_a_id: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    entity_b_type: str = Field(sa_column=Column(String, nullable=False, index=True))
    entity_b_id: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    link_note: Optional[str] = None


class MediaLinkCreate(SQLModel):
    target_entity_type: str
    target_entity_id: int
    link_note: Optional[str] = None


class MediaLinkRead(SQLModel):
    id: int
    entity_a_type: str
    entity_a_id: int
    entity_b_type: str
    entity_b_id: int
    link_note: Optional[str] = None


def make_entity_link(
    entity_type: str,
    entity_id: int,
    target_entity_type: str,
    target_entity_id: int,
    *,
    link_note: Optional[str] = None,
) -> MediaLink:
    """Construct a MediaLink with entity_a/entity_b sorted ascending by
    (type, id). The single choke-point every write path must go through,
    replacing the old model_post_init XOR check (that invariant no longer
    exists under this shape, all four columns are always required).

    Raises:
        ValueError: If both sides name the exact same entity (a link cannot
            point an entity at itself).
    """
    a = (entity_type, entity_id)
    b = (target_entity_type, target_entity_id)
    if a == b:
        raise ValueError(
            f"Cannot link an entity to itself (entity_type={entity_type!r}, entity_id={entity_id!r})."
        )
    lo, hi = (a, b) if a < b else (b, a)
    return MediaLink(
        entity_a_type=lo[0], entity_a_id=lo[1],
        entity_b_type=hi[0], entity_b_id=hi[1],
        link_note=link_note,
    )


def _link_target_model(entity_type: str) -> Optional[type]:
    """entity_type -> model backing it. Single source of truth for both
    counterpart title/slug resolution (_linked_items_for_many below) and
    existence-checks when creating a link (backend/api/routes/entity_links.py
    imports this directly rather than hand-maintaining a second copy).
    Deferred imports avoid a module-load-order dependency between media.py,
    game.py, and app.py."""
    if entity_type == "game_item_bundle":
        from backend.models.game import GameItemBundle
        return GameItemBundle
    if entity_type == "app_item_bundle":
        from backend.models.app import AppItemBundle
        return AppItemBundle
    if entity_type == "media_item":
        return MediaItem
    if entity_type == "media_item_bundle":
        return MediaItemBundle
    return None


def unique_media_slug(title: str, db: "Session") -> str:
    """Slug uniqueness spans both media_items and media_item_bundles — the
    two share the /media/{slug}-style namespace, so a title collision
    between an item and a bundle is treated the same as a same-table
    collision. Shared by backend/api/routes/media.py's create routes and
    backend/service/games/media_link.py's Accept All flow, a single choke
    point rather than two hand-maintained copies of the same cross-table
    uniqueness rule."""
    from backend.service.utils.slug_generator import unique_slug

    return unique_slug(
        title,
        lambda s: (
            db.query(MediaItem).filter(MediaItem.slug == s).first() is not None
            or db.query(MediaItemBundle).filter(MediaItemBundle.slug == s).first() is not None
        ),
    )


def delete_links_for(entity_type: str, entity_id: int, db: "Session") -> None:
    """Remove every MediaLink row involving (entity_type, entity_id) on
    either side. Callers must run this before (or as part of, same
    transaction) deleting the entity itself: MediaLink carries no DB-level
    foreign key, so there is no ON DELETE CASCADE to rely on, unlike
    EntityTag (left to go stale on delete today), a stale MediaLink is not
    optional to clean up here, see the module-level comment above."""
    db.query(MediaLink).filter(
        or_(
            and_(MediaLink.entity_a_type == entity_type, MediaLink.entity_a_id == entity_id),
            and_(MediaLink.entity_b_type == entity_type, MediaLink.entity_b_id == entity_id),
        )
    ).delete()


# ---------------------------------------------------------------------------
# Read-model builders, tags via the generic get_tags_for_entity(_entities)
# helper Game already uses (backend/models/tag.py), called here with the
# "media_item"/"media_item_bundle" entity_type strings.
# ---------------------------------------------------------------------------


def _linked_items_for(
    entity_type: str, entity_id: int, db: "Session"
) -> list[LinkedEntityRef]:
    return _linked_items_for_many(entity_type, [entity_id], db).get(entity_id, [])


def _linked_items_for_many(
    entity_type: str, entity_ids: list[int], db: "Session"
) -> dict[int, list[LinkedEntityRef]]:
    """Bulk variant: one MediaLink query plus one bulk query per distinct
    counterpart entity_type found, instead of a per-entity N+1.

    A matched row's "my" id may land on either the a or b side depending on
    the canonical-ordering rule make_entity_link() applied at write time, so
    each row is inspected to find which side belongs to entity_ids and treats
    the other side as the counterpart. A counterpart row that no longer
    exists (should not happen once every delete path calls
    delete_links_for(), kept here as a defensive skip, not a crash, matching
    this codebase's degrade-and-skip convention elsewhere, e.g. game.py's
    _leaf_to_read) is silently omitted rather than raised.
    """
    if not entity_ids:
        return {}
    from sqlalchemy import select as _select

    id_set = set(entity_ids)
    rows = db.execute(
        _select(MediaLink).where(
            or_(
                and_(MediaLink.entity_a_type == entity_type, MediaLink.entity_a_id.in_(id_set)),
                and_(MediaLink.entity_b_type == entity_type, MediaLink.entity_b_id.in_(id_set)),
            )
        )
    ).scalars().all()

    # (my_entity_id, link, counterpart_type, counterpart_id) per matched row.
    pending: list[tuple[int, "MediaLink", str, int]] = []
    ids_by_target_type: dict[str, set[int]] = {}
    for link in rows:
        if link.entity_a_type == entity_type and link.entity_a_id in id_set:
            my_id, counterpart_type, counterpart_id = link.entity_a_id, link.entity_b_type, link.entity_b_id
        else:
            my_id, counterpart_type, counterpart_id = link.entity_b_id, link.entity_a_type, link.entity_a_id
        pending.append((my_id, link, counterpart_type, counterpart_id))
        ids_by_target_type.setdefault(counterpart_type, set()).add(counterpart_id)

    titles: dict[tuple[str, int], tuple[str, Optional[str]]] = {}
    for target_type, ids in ids_by_target_type.items():
        model = _link_target_model(target_type)
        if model is None:
            continue
        found = db.execute(_select(model).where(model.id.in_(ids))).scalars().all()
        for obj in found:
            titles[(target_type, obj.id)] = (obj.title, getattr(obj, "slug", None))

    result: dict[int, list[LinkedEntityRef]] = {}
    for my_id, link, counterpart_type, counterpart_id in pending:
        title_slug = titles.get((counterpart_type, counterpart_id))
        if title_slug is None:
            continue
        title, slug = title_slug
        result.setdefault(my_id, []).append(
            LinkedEntityRef(
                link_id=link.id,
                entity_type=counterpart_type,
                entity_id=counterpart_id,
                title=title,
                slug=slug,
                link_note=link.link_note,
            )
        )
    return result


def item_to_read(item: MediaItem, db: "Session") -> MediaItemRead:
    read = MediaItemRead.model_validate(item)
    read.tags = get_tags_for_entity("media_item", item.id, db)
    read.linked_items = _linked_items_for("media_item", item.id, db)
    return read


def items_to_read_bulk(items: list[MediaItem], db: "Session") -> list[MediaItemRead]:
    if not items:
        return []
    item_ids = [i.id for i in items]
    tag_map = get_tags_for_entities("media_item", item_ids, db)
    linked_map = _linked_items_for_many("media_item", item_ids, db)
    reads = []
    for i in items:
        read = MediaItemRead.model_validate(i)
        read.tags = tag_map.get(i.id, [])
        read.linked_items = linked_map.get(i.id, [])
        reads.append(read)
    return reads


def media_item_bundle_to_read(bundle: MediaItemBundle, db: "Session") -> MediaItemBundleRead:
    read = MediaItemBundleRead.model_validate(bundle)
    read.items = items_to_read_bulk(list(bundle.items), db)
    read.tags = get_tags_for_entity("media_item_bundle", bundle.id, db)
    read.linked_items = _linked_items_for("media_item_bundle", bundle.id, db)
    return read


def media_item_bundle_to_read_bulk(
    bundles: list[MediaItemBundle], db: "Session"
) -> list[MediaItemBundleRead]:
    if not bundles:
        return []
    bundle_ids = [c.id for c in bundles]
    tag_map = get_tags_for_entities("media_item_bundle", bundle_ids, db)
    linked_map = _linked_items_for_many("media_item_bundle", bundle_ids, db)
    reads = []
    for c in bundles:
        read = MediaItemBundleRead.model_validate(c)
        read.items = items_to_read_bulk(list(c.items), db)
        read.tags = tag_map.get(c.id, [])
        read.linked_items = linked_map.get(c.id, [])
        reads.append(read)
    return reads
