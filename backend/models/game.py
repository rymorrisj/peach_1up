from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import model_validator
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import validates
from sqlmodel import Field, Relationship, SQLModel

from backend.constants import PC_ERAS
from backend.constants_generated import EraValue, FileType, ItemType
from backend.models.drive import Drive, DriveRead
from backend.models.media import LinkedEntityRef
from backend.models.tag import TagRead, get_tags_for_entities, get_tags_for_entity

_YEAR_MIN = 1970
_YEAR_MAX = 2050

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Leaf entity: GameItem (one disc / media record within a bundle).
# Single-disc games are bundles-of-one.
# ---------------------------------------------------------------------------

class GameItem(SQLModel, table=True):
    __tablename__ = "game_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    game_item_bundle_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("game_item_bundles.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    disc_number: int = 1
    file_path: str = Field(sa_column=Column(String, nullable=False, index=True))
    executable_path: Optional[str] = None
    cover_art_path: Optional[str] = None
    file_type: Optional[FileType] = Field(default=None, sa_column=Column(String))
    folder_path: Optional[str] = Field(default=None, index=True)
    detection_reason: Optional[str] = None
    file_size_bytes: Optional[int] = None
    # One-time snapshot of the source folder/file name at import time, before
    # any slug-based rename. Lets a later scan match a disk path back to this
    # row even after the on-disk name has since diverged from the DB slug.
    original_name: Optional[str] = None
    # True only when folder_path was created/renamed exclusively for this item
    # (or, for a multi-disc set, this bundle) by the ingest pipeline itself
    #, safe to rmtree on delete. False/None means folder_path is a pre-existing
    # directory the ingest pipeline does not own (e.g. the parent of a loose
    # file ingested with no SOFTWARE_PATH configured) and must never be rmtree'd;
    # None covers rows written before this column existed, treated the same as
    # False. See _delete_leaf_media_folders.
    folder_owned: Optional[bool] = None
    # Set when a Fetch Metadata Keep last successfully applied cover art to
    # this leaf (see enrich_entity(), backend/service/games/enrich.py). None
    # means never fetched. Leaf-level Fetch Metadata only ever applies
    # cover_art_url, never the full metadata fields a bundle-level fetch
    # applies, but it is a real, currently-supported fetch path, so it gets
    # its own tracking column rather than being folded into the bundle's.
    metadata_fetched_at: Optional[datetime] = None
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )

    game_item_bundle: Optional["GameItemBundle"] = Relationship(
        back_populates="items"
    )

class GameItemRead(SQLModel):
    id: int
    game_item_bundle_id: int
    disc_number: int
    file_path: str
    executable_path: Optional[str] = None
    cover_art_path: Optional[str] = None
    cover_art_url: Optional[str] = None
    file_type: Optional[FileType] = None
    folder_path: Optional[str] = None
    detection_reason: Optional[str] = None
    file_size_bytes: Optional[int] = None
    metadata_fetched_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _compute_cover_art_url(self) -> "GameItemRead":
        if not self.cover_art_path:
            return self
        try:
            from backend.service.utils import settings as _s

            lib_root = Path(_s.get("LIBRARY_PATH"))
            resolved = Path(self.cover_art_path).resolve()
            rel = resolved.relative_to(lib_root.resolve())
            if resolved.exists():
                self.cover_art_url = "/media/" + rel.as_posix()
        except ValueError:
            pass
        return self

class GameItemUpdate(SQLModel):
    executable_path: Optional[str] = None
    cover_art_path: Optional[str] = None


class GameItemReorder(SQLModel):
    # Every leaf id belonging to the bundle, top-to-bottom. The first id
    # becomes the new launch disc. disc_number columns are existing data, not
    # a schema change, this only adds a write path for them.
    disc_order: list[int]

# ---------------------------------------------------------------------------
# Parent entity: GameItemBundle (the game). Owns metadata, the writable drive
# (DOS), and the ordered leaf list.
# ---------------------------------------------------------------------------


def derive_item_type(era: EraValue) -> ItemType:
    """era is the source of truth for item_type: PC eras -> "pc", everything else -> "console"."""
    return "pc" if era in PC_ERAS else "console"


class GameItemBundle(SQLModel, table=True):
    __tablename__ = "game_item_bundles"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: Optional[str] = Field(default=None, index=True, unique=True)
    title: str
    sort_title: Optional[str] = None
    era: EraValue = Field(sa_column=Column(String, nullable=False))
    # Derived-and-validated from era on write (see _derive_item_type_from_era below);
    # default=None only so construction can omit it before the validator fills it in,
    # the stored column is NOT NULL.
    item_type: ItemType = Field(default=None, sa_column=Column(String, nullable=False))
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    developer: Optional[str] = None
    year: Optional[int] = None
    external_game_id: Optional[int] = None
    metadata_source: Optional[str] = None
    content_rating: Optional[str] = Field(default=None, index=True)
    launch_commands: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))
    # Trailer/video links fetched from a metadata provider (TheGamesDB's
    # youtube field, IGDB's videos field), never downloaded, stored verbatim
    # as-is. Shape: list of {"type": str, "url": str}, "type" is "trailer"
    # for every entry today; a typed list rather than a scalar column since
    # IGDB alone can already return more than one video per game. Same
    # JSON-column pattern as launch_commands above.
    external_links: Optional[list[dict]] = Field(default=None, sa_column=Column(JSON))
    # Set when a Fetch Metadata Keep last successfully applied metadata to
    # this bundle (see enrich_entity(), backend/service/games/enrich.py).
    # None means never fetched. Surfaced on the detail page and used to warn
    # before a re-fetch, since every fetch call costs the user's provider
    # API credits/allowance.
    metadata_fetched_at: Optional[datetime] = None
    installed: bool = False
    requires_install: bool = False
    launch_review_flagged: bool = Field(default=False)
    # None = inherit the global delete_media_on_removal setting. True/False
    # explicitly overrides it for this bundle only.
    delete_media_override: Optional[bool] = None

    environment_item_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("environment_items.id", ondelete="SET NULL"), nullable=True),
    )
    profile_item_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("profile_items.id", ondelete="SET NULL"), nullable=True),
    )
    drive_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("drives.id"), nullable=True),
    )
    # Logical FKs to game_items.id. Not DB-level constraints to avoid a circular
    # reference between game_item_bundles and game_items during table creation.
    launch_disk_id: Optional[int] = Field(default=None)
    # Which leaf's art is shown as the stack front-face. Falls back to launch_disk_id when null.
    display_disk_id: Optional[int] = Field(default=None)

    last_launched_at: Optional[datetime] = None
    launch_count: int = 0
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )

    items: list["GameItem"] = Relationship(
        back_populates="game_item_bundle",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "GameItem.disc_number",
        },
    )

    drive: Optional["Drive"] = Relationship(
        back_populates="game_item_bundle",
        sa_relationship_kwargs={
            "foreign_keys": "Drive.game_item_bundle_id",
            "uselist": False,
        },
    )

    @validates("item_type")
    def _validate_item_type(self, key: str, value: Optional[ItemType]) -> Optional[ItemType]:
        derived = derive_item_type(self.era)
        if value is not None and value != derived:
            raise ValueError(
                f"item_type {value!r} conflicts with era {self.era!r} "
                f"(era implies {derived!r}). item_type is derived from era, not independently settable."
            )
        return value

    def model_post_init(self, __context: object) -> None:
        # SQLModel's table-model __setattr__ writes each field twice per
        # assignment (once via SQLAlchemy instrumentation, once via Pydantic),
        # the second write always re-applies the raw incoming value, so a
        # value *transformed* by returning something different from
        # @validates never survives. That means item_type can only be
        # reliably derived here, as an explicit direct assignment after the
        # whole object is built, not by returning a different value from
        # _validate_item_type above (which exists solely to reject an
        # explicitly-conflicting item_type before construction completes).
        self.item_type = derive_item_type(self.era)


class GameItemBundleCreate(SQLModel):
    title: str
    file_path: str
    era: EraValue = "unknown"
    profile_item_id: Optional[int] = None
    environment_item_id: Optional[int] = None


class GameItemBundleUpdate(SQLModel):
    title: Optional[str] = None
    sort_title: Optional[str] = None
    era: Optional[EraValue] = None
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = Field(default=None, ge=_YEAR_MIN, le=_YEAR_MAX)
    external_game_id: Optional[int] = None
    metadata_source: Optional[str] = None
    content_rating: Optional[str] = None
    launch_commands: Optional[list[str]] = None
    external_links: Optional[list[dict]] = None
    launch_review_flagged: Optional[bool] = None
    installed: Optional[bool] = None
    requires_install: Optional[bool] = None
    delete_media_override: Optional[bool] = None
    environment_item_id: Optional[int] = None
    profile_item_id: Optional[int] = None
    display_disk_id: Optional[int] = None
    launch_disk_id: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def _reject_dead_fields(cls, data: object) -> object:
        if isinstance(data, dict) and "drive_size_mb" in data:
            raise ValueError(
                "drive_size_mb is not a valid update field and has no database column."
            )
        return data


class GameItemBundleRead(SQLModel):
    id: int
    slug: Optional[str] = None
    title: str
    sort_title: Optional[str] = None
    era: str
    item_type: ItemType
    category: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    developer: Optional[str] = None
    genres: list[str] = []
    year: Optional[int] = None
    external_game_id: Optional[int] = None
    metadata_source: Optional[str] = None
    content_rating: Optional[str] = None
    launch_commands: Optional[list[str]] = None
    external_links: Optional[list[dict]] = None
    metadata_fetched_at: Optional[datetime] = None
    installed: bool = False
    requires_install: bool = False
    launch_review_flagged: bool = False
    delete_media_override: Optional[bool] = None
    environment_item_id: Optional[int] = None
    profile_item_id: Optional[int] = None
    drive_id: Optional[int] = None
    launch_disk_id: Optional[int] = None
    display_disk_id: Optional[int] = None
    last_launched_at: Optional[datetime] = None
    launch_count: int = 0
    created_at: datetime
    updated_at: datetime
    items: list[GameItemRead] = []
    drive: Optional[DriveRead] = None
    tags: list[TagRead] = []
    linked_items: list[LinkedEntityRef] = []
    # Pre-launch UX gate. Computed at read time (not stored) in
    # game_item_bundle_to_read / game_item_bundles_to_read_bulk via the shared
    # compute_launch_blocked_reason. "no_profile" when the bundle has no launch
    # profile (pc or console); "no_environment" when this is a PC bundle with no
    # resolvable Environment (neither environment_item_id nor an era-matched
    # system Environment fallback); "environment_era_mismatch" when a resolved
    # Environment's era does not match the bundle's era; "environment_not_installed"
    # when a resolved, era-matched Environment has not had its OS installed yet;
    # None when the item clears every gate.
    launch_blocked_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Scan / import DTOs (unchanged shape).
# ---------------------------------------------------------------------------


class ScanPreviewItem(SQLModel):
    title: str
    file_path: str
    detected_era: Optional[str] = None
    is_loose: bool
    is_zip: bool


class ScanStatus(SQLModel):
    running: bool
    job_id: Optional[str] = None
    error: Optional[str] = None


class ImportErrorItem(SQLModel):
    path: str
    reason: str


class ImportResult(SQLModel):
    imported: int
    skipped: int
    errors: list[ImportErrorItem]


# ---------------------------------------------------------------------------
# Read-model builders.
# ---------------------------------------------------------------------------


def _leaf_to_read(leaf: GameItem) -> Optional[GameItemRead]:
    """Validate one leaf into a GameItemRead, isolating a single bad row.

    A leaf whose DB-persisted ``file_type`` predates the current FileType
    vocabulary (the column is a bare String and enforces no Literal) would raise
    ValidationError and, unguarded, 500 the entire GET /library list. Here that
    failure is contained to the offending row: the file_type is coerced to None
    and the row still renders (degrade). If it still cannot validate, the row is
    dropped from the response (skip) with a logged warning rather than taking the
    whole list down with it.
    """
    from pydantic import ValidationError

    from backend.core.logger import get_logger

    try:
        return GameItemRead.model_validate(leaf)
    except ValidationError as exc:
        log = get_logger(__name__)
        leaf_id = getattr(leaf, "id", None)
        log.warning(
            "Library item %s failed read validation (%s); serving with file_type "
            "nulled. This usually means a file_type value not in the current "
            "FileType set was persisted before validation existed.",
            leaf_id, exc,
        )
        try:
            payload = {
                name: getattr(leaf, name, None)
                for name in GameItemRead.model_fields
                if name != "cover_art_url"
            }
            payload["file_type"] = None
            return GameItemRead.model_validate(payload)
        except ValidationError as exc2:
            log.warning(
                "Library item %s is unreadable even after degrading file_type; "
                "dropping it from the response: %s",
                leaf_id, exc2,
            )
            return None


def _leaves_for_bundle(bundle_id: int, db: "Session") -> list[GameItem]:
    from sqlalchemy import select as _select

    return list(
        db.execute(
            _select(GameItem)
            .where(GameItem.game_item_bundle_id == bundle_id)
            .order_by(GameItem.disc_number)
        ).scalars().all()
    )


def _launch_blocked_reason(c: "GameItemBundle", environment) -> Optional[str]:
    """Thin adapter over the shared compute_launch_blocked_reason (see
    backend/service/utils/era_defaults.py). Returns "no_profile" when the bundle
    has no profile (pc or console), "no_environment" for a PC bundle with no
    resolvable Environment, "environment_era_mismatch" or
    "environment_not_installed" for a resolvable-but-unlaunchable Environment,
    else None. is_pc is derived from item_type. *environment* is the already
    -resolved EnvironmentItem (or None) for this bundle."""
    from backend.service.utils.era_defaults import compute_launch_blocked_reason

    return compute_launch_blocked_reason(
        is_pc=c.item_type == "pc",
        era=c.era,
        profile_item_id=c.profile_item_id,
        environment=environment,
    )


def game_item_bundle_to_read(c: "GameItemBundle", db: "Session") -> GameItemBundleRead:
    """Build a GameItemBundleRead, nesting ordered leaves, tags, and genres."""
    from backend.models.metadata_lookup import get_genres_for_game_item_bundle
    from backend.service.utils.era_defaults import resolve_environment_for_launch_gate

    from backend.models.media import _linked_items_for

    read = GameItemBundleRead.model_validate(c)
    read.items = [r for i in c.items if (r := _leaf_to_read(i)) is not None]
    read.tags = get_tags_for_entity("game_item_bundle", c.id, db)
    read.genres = get_genres_for_game_item_bundle(c.id, db)
    read.linked_items = _linked_items_for("game_item_bundle", c.id, db)
    environment = (
        resolve_environment_for_launch_gate(c.environment_item_id, c.era, db)
        if c.item_type == "pc" else None
    )
    read.launch_blocked_reason = _launch_blocked_reason(c, environment)
    return read


def game_item_bundles_to_read_bulk(
    bundles: list["GameItemBundle"], db: "Session"
) -> list[GameItemBundleRead]:
    """game_item_bundle_to_read over a list in bulk queries (all leaves, all
    tags, all genres, all linked items) instead of the per-bundle N+1."""
    from sqlalchemy import select as _select

    from backend.models.media import _linked_items_for_many
    from backend.models.metadata_lookup import get_genres_for_game_item_bundles
    from backend.service.utils.era_defaults import resolve_environments_for_launch_gate_bulk

    if not bundles:
        return []

    bundle_ids = [c.id for c in bundles]
    leaves = db.execute(
        _select(GameItem)
        .where(GameItem.game_item_bundle_id.in_(bundle_ids))
        .order_by(GameItem.game_item_bundle_id, GameItem.disc_number)
    ).scalars().all()

    leaves_by_bundle: dict[int, list[GameItemRead]] = {}
    for leaf in leaves:
        leaf_read = _leaf_to_read(leaf)
        if leaf_read is None:
            continue
        leaves_by_bundle.setdefault(leaf.game_item_bundle_id, []).append(leaf_read)

    tag_map = get_tags_for_entities("game_item_bundle", bundle_ids, db)
    genre_map = get_genres_for_game_item_bundles(bundle_ids, db)
    linked_map = _linked_items_for_many("game_item_bundle", bundle_ids, db)

    # Batched Environment resolution (explicit id + era-matched system
    # fallback) for every PC bundle, instead of a per-bundle lookup (N+1).
    pc_bundles = [c for c in bundles if c.item_type == "pc"]
    environment_by_bundle_id = resolve_environments_for_launch_gate_bulk(pc_bundles, db)

    reads: list[GameItemBundleRead] = []
    for c in bundles:
        read = GameItemBundleRead.model_validate(c)
        read.items = leaves_by_bundle.get(c.id, [])
        read.tags = tag_map.get(c.id, [])
        read.genres = genre_map.get(c.id, [])
        read.linked_items = linked_map.get(c.id, [])
        read.launch_blocked_reason = _launch_blocked_reason(c, environment_by_bundle_id.get(c.id))
        reads.append(read)
    return reads
