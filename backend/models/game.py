from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, TYPE_CHECKING

from pydantic import computed_field, model_validator
from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import validates
from sqlmodel import Field, Relationship, SQLModel

from backend.constants import PC_PLATFORMS
from backend.constants_generated import PlatformValue, FileType, ItemType
from backend.models.drive import Drive, DriveRead
from backend.models.media import LinkedEntityRef
from backend.models.tag import TagRead, get_tags_for_entities, get_tags_for_entity

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.models.user import UserItem

_YEAR_MIN = 1970
_YEAR_MAX = 2050

# ---------------------------------------------------------------------------
# Leaf entity: GameItem (one disc / media record within a bundle).
# Single-disc games are bundles-of-one.
# ---------------------------------------------------------------------------

# Five-state hash verification status for a single leaf, set from
# formatscout.classify()'s ClassifyResult.status (same five string
# values, see classify.py / result.py for the full definitions):
#   "verified"     sha1 exactly matches a hash_index.json entry. The only
#                  state that reads as a positive confirmation.
#   "caution"      md5 or crc32 exactly matches an entry, no sha1 match.
#                  Real index coverage, weaker confidence than "verified".
#   "mismatch"     no hash matched, but the title approximately matches an
#                  indexed title. Expected to happen often against an
#                  inherently incomplete public hash catalog, not itself a
#                  sign the file is bad, see classify.py.
#   "not_in_index" no hash matched and no confident title match either.
#                  Neutral "we have no data", not a warning.
#   "unchecked"    default. Never verified at all, e.g. a row created before
#                  this field existed, or the file could not be hashed.
VerificationStatus = Literal["verified", "caution", "not_in_index", "mismatch", "unchecked"]


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
    # , safe to rmtree on delete. False/None means folder_path is a pre-existing
    # directory the ingest pipeline does not own (e.g. the parent of a loose
    # file ingested with no SOFTWARE_PATH configured) and must never be rmtree'd;
    # None covers rows written before this column existed, treated the same as
    # False. See _delete_leaf_media_folders.
    folder_owned: Optional[bool] = None
    # Legacy: stamped when a per-disc cover was fetched for this leaf. That
    # flow is gone (the game cover now comes from Accept All, see
    # media_link.py), so nothing writes this column any more.
    metadata_fetched_at: Optional[datetime] = None
    # Set automatically at ingest time from formatscout.classify()
    # (see _prepare_item / _prepare_multi_disc in
    # backend/service/games/items.py, one classify() call per disc), and
    # refreshed on demand by the /api/v1/game-item/{leaf_id}/verify and
    # /api/v1/game-item-bundle/{collection_id}/verify endpoints.
    verification_status: VerificationStatus = Field(default="unchecked", sa_column=Column(String, nullable=False))
    # ClassifyResult.similarity (title_match.py's SequenceMatcher ratio),
    # persisted only when verification_status is "mismatch", the only status
    # fuzzy_title_match() ever produces a score for. None for every other
    # status, including a re-check that resolves to "unchecked" or
    # "not_in_index" without a classify() call (see
    # _reverify_leaf_in_session). Not returned to the frontend as a raw
    # number, GameItemRead exposes it so the UI can choose message wording,
    # never display it directly.
    verification_similarity: Optional[float] = Field(default=None, sa_column=Column(Float))
    # This leaf's own computed sha1 (hash_file()'s result), persisted
    # whenever classify() successfully hashes the file, regardless of
    # verification_status. Used as classify()'s own re-check baseline and to
    # avoid ever needing to parse a hash back out of detection_reason. Never
    # returned by the API, GameItemRead deliberately omits it. A caller
    # needing the raw hash should use the formatscout package
    # directly rather than reading it off a GameItem.
    sha1: Optional[str] = Field(default=None, sa_column=Column(String))
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False),
    )

    game_item_bundle: Optional["GameItemBundle"] = Relationship(back_populates="items")


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
    # sha1 is deliberately not exposed here, or anywhere else in the API. The
    # raw hash is not needed by any caller, and a caller that does need it
    # should use the formatscout package directly.
    verification_status: VerificationStatus = "unchecked"
    # None unless verification_status is "mismatch", see GameItem's field
    # comment. Exposed so the frontend can pick message wording, not meant
    # to be shown to the user as a raw number.
    verification_similarity: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _compute_cover_art_url(self) -> "GameItemRead":
        if not self.cover_art_path:
            return self
        from backend.service.utils.path_utils import is_untrusted_remote_path

        # MED-10 read side: no resolve()/exists() on a stored UNC or device path.
        if is_untrusted_remote_path(self.cover_art_path):
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


def derive_item_type(platform: PlatformValue) -> ItemType:
    """platform is the source of truth for item_type: PC platforms -> "pc", everything else -> "console"."""
    return "pc" if platform in PC_PLATFORMS else "console"


class GameCoverCandidate(SQLModel):
    """One linked Media image the caller may use as this game's cover."""

    media_item_id: int
    title: str
    asset_type: Optional[str] = None
    file_url: str
    media_item_bundle_id: Optional[int] = None
    is_current: bool = False


class GameCoverFromMedia(SQLModel):
    media_item_id: int


class GameItemBundle(SQLModel, table=True):
    __tablename__ = "game_item_bundles"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: Optional[str] = Field(default=None, index=True, unique=True)
    title: str
    sort_title: Optional[str] = None
    platform: PlatformValue = Field(sa_column=Column(String, nullable=False))
    # Derived-and-validated from platform on write (see _derive_item_type_from_platform below);
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
    # this bundle (see enrich_game_bundle(), backend/service/games/enrich.py).
    # None means never fetched. Surfaced on the detail page and used to warn
    # before a re-fetch, since every fetch call costs the user's provider
    # API credits/allowance.
    metadata_fetched_at: Optional[datetime] = None
    installed: bool = False
    requires_install: bool = False
    launch_review_flagged: bool = Field(default=False)
    # Whether the platform is proven: formatscout's detection was
    # authoritative (ScanResult.authoritative, incl. the PS3 folder structure), the user chose
    # the platform at import, the user changed it later, or the user confirmed a
    # detected platform after seeing the game run. Never true while platform is
    # "unknown". Written at ingest, by PATCH (see _apply_platform_change and
    # _validate_platform_confirmation in service/games/items.py), never by create.
    platform_confirmed: bool = Field(default=False)
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
        derived = derive_item_type(self.platform)
        if value is not None and value != derived:
            raise ValueError(
                f"item_type {value!r} conflicts with platform {self.platform!r} "
                f"(platform implies {derived!r}). item_type is derived from platform, not independently settable."
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
        self.item_type = derive_item_type(self.platform)


class GameItemBundleCreate(SQLModel):
    title: str
    file_path: str
    platform: PlatformValue = "unknown"
    profile_item_id: Optional[int] = None
    environment_item_id: Optional[int] = None


class GameItemBundleUpdate(SQLModel):
    title: Optional[str] = None
    sort_title: Optional[str] = None
    platform: Optional[PlatformValue] = None
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
    # Only `true` is accepted (the "Confirm platform" action), and only when
    # the resulting platform is known. Enforced by _validate_platform_confirmation in
    # service/games/items.py, which needs the stored platform this model cannot see.
    platform_confirmed: Optional[bool] = None
    environment_item_id: Optional[int] = None
    profile_item_id: Optional[int] = None
    display_disk_id: Optional[int] = None
    launch_disk_id: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def _reject_dead_fields(cls, data: object) -> object:
        if isinstance(data, dict) and "drive_size_mb" in data:
            raise ValueError("drive_size_mb is not a valid update field and has no database column.")
        return data


# How far the bundle's platform can be trusted, computed per read (never stored):
#   "confirmed"  the stored platform_confirmed flag is true (authoritative
#                detection, a user-chosen or user-changed platform, or an explicit
#                Confirm).
#   "verified"   not confirmed, but every disc hash-verified.
#   "unreviewed" a guess nothing has proven, including platform "unknown".
PlatformReview = Literal["confirmed", "verified", "unreviewed"]


class GameItemBundleRead(SQLModel):
    id: int
    slug: Optional[str] = None
    title: str
    sort_title: Optional[str] = None
    platform: str
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
    # Hidden (None) for restricted accounts by the two read builders below.
    external_links: Optional[list[dict]] = None
    metadata_fetched_at: Optional[datetime] = None
    installed: bool = False
    requires_install: bool = False
    launch_review_flagged: bool = False
    # Stored flag, see GameItemBundle.platform_confirmed. platform_review below is what
    # the UI reads, this is exposed so a client can tell "confirmed" apart.
    platform_confirmed: bool = False
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
    # evaluate_launch_readiness (call_site="item"). "no_profile" when the bundle
    # has no launch profile (pc or console); "no_environment" when this is a PC
    # bundle with no Environment chosen; "environment_not_provisioned" when the
    # chosen Environment has no working image and its platform can never get
    # one auto-provisioned; "environment_not_installed" when the chosen
    # Environment has not had its OS installed yet; None when the item clears
    # every gate.
    launch_blocked_reason: Optional[str] = None
    # Computed at read time (not stored) by _rollup_verification_item below,
    # the worst-severity status among this bundle's items. "verified" only
    # when every disc is "verified"; any disc in a weaker state pulls the
    # whole bundle down to that state (see _VERIFICATION_SEVERITY).
    verification_status: VerificationStatus = "unchecked"
    # verification_similarity of whichever leaf's status won the rollup
    # above, not an independent computation. None unless that leaf's own
    # status is "mismatch".
    verification_similarity: Optional[float] = None
    # Computed at read time (not stored) by _compute_platform_review below, how much
    # to trust this bundle's platform. Set after verification_status, it reads it.
    platform_review: PlatformReview = "unreviewed"
    # Computed at read time (not stored) by _bundle_has_launched below: True
    # when any LaunchHistory row exists for this bundle, whatever its outcome.
    # Set on the single-bundle (detail) read only. None on list reads, which
    # would otherwise pay one query per bundle (launch_count and
    # last_launched_at are never written, so they are no usable source).
    has_launched: Optional[bool] = None

    @computed_field
    @property
    def external_provider(self) -> Optional[str]:
        """Provider key that issued external_game_id, read from
        metadata_source; None when it is blank or not a known provider (an
        id stored before the provider was recorded), so the client searches
        instead of looking the id up."""
        from backend.service.metadata_providers import provider_key_for

        return provider_key_for(self.metadata_source)


# Worst-wins severity order for the bundle-level rollup, highest number is
# most severe and wins. caution is the most severe state: an actual partial
# hash match (md5/crc32) against the index is real, specific signal that
# something is off. mismatch sits just above the neutral not_in_index/
# unchecked tier, not above caution, since a title-only match against an
# inherently incomplete public hash catalog is expected to happen often and
# is not itself a sign of a bad file, unlike a genuine partial hash hit.
# not_in_index vs. unchecked is not spec-mandated either: both are lumped
# together there as one non-problem tier below mismatch. Ranking unchecked
# one step above not_in_index is a judgment call, not a spec requirement, an
# unchecked disc is more actionable ("go verify it") than a disc that was
# already checked and genuinely has no index data, so it is surfaced first
# when a bundle has a mix of the two and nothing worse.
_VERIFICATION_SEVERITY: dict[VerificationStatus, int] = {
    "verified": 0,
    "not_in_index": 1,
    "unchecked": 2,
    "mismatch": 3,
    "caution": 4,
}


def _rollup_verification_item(items: list[GameItemRead]) -> GameItemRead | None:
    """Worst-status-wins rollup across a bundle's leaves, see
    _VERIFICATION_SEVERITY for the ordering and its one judgment call.
    Returns the winning leaf itself, not just its status, so the caller can
    also carry over that leaf's verification_similarity. Empty *items* is
    defensive only, a bundle always has at least one leaf.
    """
    if not items:
        return None
    return max(items, key=lambda item: _VERIFICATION_SEVERITY[item.verification_status])


def _compute_platform_review(platform_confirmed: bool, verification_status: VerificationStatus) -> PlatformReview:
    """Three-way platform trust signal, see PlatformReview: "confirmed" when the stored
    flag is set, else "verified" when the rolled-up verification_status is
    verified, else "unreviewed". Reads no detection_reason text."""
    if platform_confirmed:
        return "confirmed"
    if verification_status == "verified":
        return "verified"
    return "unreviewed"


def _bundle_has_launched(bundle_id: int, db: "Session") -> bool:
    """True when at least one LaunchHistory row exists for *bundle_id*. Looks at
    nothing but existence: not error_message, exit_code, ended_at or whether a
    process is still running. One EXISTS query, so only the single-bundle read
    calls it."""
    from sqlalchemy import exists, select as _select

    from backend.models.launch_history import LaunchHistory

    return bool(db.execute(_select(exists().where(LaunchHistory.game_item_bundle_id == bundle_id))).scalar())


# ---------------------------------------------------------------------------
# Scan / import DTOs (unchanged shape).
# ---------------------------------------------------------------------------


class ScanPreviewItem(SQLModel):
    title: str
    file_path: str
    detected_platform: Optional[str] = None
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
            leaf_id,
            exc,
        )
        try:
            payload = {name: getattr(leaf, name, None) for name in GameItemRead.model_fields if name != "cover_art_url"}
            payload["file_type"] = None
            return GameItemRead.model_validate(payload)
        except ValidationError as exc2:
            log.warning(
                "Library item %s is unreadable even after degrading file_type; dropping it from the response: %s",
                leaf_id,
                exc2,
            )
            return None


def _leaves_for_bundle(bundle_id: int, db: "Session") -> list[GameItem]:
    from sqlalchemy import select as _select

    return list(
        db.execute(_select(GameItem).where(GameItem.game_item_bundle_id == bundle_id).order_by(GameItem.disc_number))
        .scalars()
        .all()
    )


def _launch_blocked_reason(c: "GameItemBundle", environment) -> Optional[str]:
    """Thin adapter over the shared evaluate_launch_readiness (see
    backend/service/utils/platform_defaults.py), call_site="item" since this is the
    read-time signal for a launchable bundle, never a direct Environment
    launch. Returns "no_profile" when the bundle has no profile (pc or
    console), "no_environment" for a PC bundle with no Environment chosen,
    "environment_not_provisioned" or "environment_not_installed" for a chosen
    but unlaunchable Environment,
    else None. is_pc is derived from item_type. *environment* is the already
    -resolved EnvironmentItem (or None) for this bundle."""
    from backend.service.utils.platform_defaults import evaluate_launch_readiness

    return evaluate_launch_readiness(
        call_site="item",
        is_pc=c.item_type == "pc",
        profile_item_id=c.profile_item_id,
        environment=environment,
    )


def game_item_bundle_to_read(c: "GameItemBundle", db: "Session", *, viewer: "UserItem") -> GameItemBundleRead:
    """Build a GameItemBundleRead, nesting ordered leaves, tags, and genres.

    *viewer* (the active user) is required so linked media and app titles
    are filtered to what that user can see, the reverse of MED-7."""
    from backend.models.metadata_lookup import get_genres_for_game_item_bundle
    from backend.service.utils.platform_defaults import resolve_environment_for_launch_gate

    from backend.core.dependencies import is_restricted_account
    from backend.models.media import _linked_items_for

    read = GameItemBundleRead.model_validate(c)
    if is_restricted_account(viewer, db):
        read.external_links = None
    read.items = [r for i in c.items if (r := _leaf_to_read(i)) is not None]
    read.tags = get_tags_for_entity("game_item_bundle", c.id, db)
    read.genres = get_genres_for_game_item_bundle(c.id, db)
    read.linked_items = _linked_items_for("game_item_bundle", c.id, db, viewer=viewer)
    environment = resolve_environment_for_launch_gate(c.environment_item_id, db) if c.item_type == "pc" else None
    read.launch_blocked_reason = _launch_blocked_reason(c, environment)
    _worst = _rollup_verification_item(read.items)
    read.verification_status = _worst.verification_status if _worst is not None else "unchecked"
    read.verification_similarity = _worst.verification_similarity if _worst is not None else None
    read.platform_review = _compute_platform_review(c.platform_confirmed, read.verification_status)
    read.has_launched = _bundle_has_launched(c.id, db)
    return read


def game_item_bundles_to_read_bulk(
    bundles: list["GameItemBundle"], db: "Session", *, viewer: "UserItem"
) -> list[GameItemBundleRead]:
    """game_item_bundle_to_read over a list in bulk queries (all leaves, all
    tags, all genres, all linked items) instead of the per-bundle N+1."""
    from sqlalchemy import select as _select

    from backend.models.media import _linked_items_for_many
    from backend.models.metadata_lookup import get_genres_for_game_item_bundles
    from backend.service.utils.platform_defaults import resolve_environments_for_launch_gate_bulk

    if not bundles:
        return []

    bundle_ids = [c.id for c in bundles]
    leaves = (
        db.execute(
            _select(GameItem)
            .where(GameItem.game_item_bundle_id.in_(bundle_ids))
            .order_by(GameItem.game_item_bundle_id, GameItem.disc_number)
        )
        .scalars()
        .all()
    )

    leaves_by_bundle: dict[int, list[GameItemRead]] = {}
    for leaf in leaves:
        leaf_read = _leaf_to_read(leaf)
        if leaf_read is None:
            continue
        leaves_by_bundle.setdefault(leaf.game_item_bundle_id, []).append(leaf_read)

    tag_map = get_tags_for_entities("game_item_bundle", bundle_ids, db)
    genre_map = get_genres_for_game_item_bundles(bundle_ids, db)
    linked_map = _linked_items_for_many("game_item_bundle", bundle_ids, db, viewer=viewer)

    # Batched Environment resolution for every PC bundle, instead of a
    # per-bundle lookup (N+1).
    pc_bundles = [c for c in bundles if c.item_type == "pc"]
    environment_by_bundle_id = resolve_environments_for_launch_gate_bulk(pc_bundles, db)

    from backend.core.dependencies import is_restricted_account

    hide_links = is_restricted_account(viewer, db)
    reads: list[GameItemBundleRead] = []
    for c in bundles:
        read = GameItemBundleRead.model_validate(c)
        if hide_links:
            read.external_links = None
        read.items = leaves_by_bundle.get(c.id, [])
        read.tags = tag_map.get(c.id, [])
        read.genres = genre_map.get(c.id, [])
        read.linked_items = linked_map.get(c.id, [])
        read.launch_blocked_reason = _launch_blocked_reason(c, environment_by_bundle_id.get(c.id))
        _worst = _rollup_verification_item(read.items)
        read.verification_status = _worst.verification_status if _worst is not None else "unchecked"
        read.verification_similarity = _worst.verification_similarity if _worst is not None else None
        read.platform_review = _compute_platform_review(c.platform_confirmed, read.verification_status)
        reads.append(read)
    return reads
