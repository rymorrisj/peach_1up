from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from backend.models.app import AppCollection
    from backend.models.drive import Drive
    from backend.models.software import SoftwareCollection


@dataclass
class LaunchableEntity:
    """Fully-resolved inputs for a single launch of a library collection.

    All fields are plain values — no ORM objects except drive (pre-resolved to
    avoid divergent lookup patterns) and _db_collection (back-ref for the
    installed=True write-back after loose-file hydration).
    """

    collection_id: int

    profile_id: int | None
    era: str
    item_type: str
    environment_id: int | None
    slug: str | None
    media_path: str
    executable_path: str | None
    # None = never configured (media file may auto-run); [] = explicitly cleared
    # (no auto-run, drop to the DOS prompt); non-empty = run these commands.
    launch_commands: list[str] | None = None
    launch_review_flagged: bool = False

    # Which table collection_id points into. "software" (SoftwareCollection,
    # the default) or "app" (AppCollection) — lets downstream code (drive
    # hydration, the coordinator's history write) pick the right sibling model
    # without a second resolution path duplicating everything above it.
    source_type: str = "software"

    # Environment hydration fields (DOS pattern-1 copy gate).
    installed: bool = False
    requires_install: bool = False
    media_type: str | None = None
    # Source folder of loose files to copy onto the drive. media_path is
    # reassigned to a single resolved launch file at add time (items.py), so
    # folder_path is the authoritative directory for loose-file hydration.
    folder_path: str | None = None

    # Pre-resolved Drive ORM object (None if no drive associated). Populated from
    # the collection's SoftwareCollection.drive relationship (None for non-DOS).
    drive: "Drive | None" = None

    # All disc media_paths in disc_number order (a collection-of-one yields a
    # single-element list — the multi-image builder no-ops when len <= 1).
    disc_paths: list[str] = field(default_factory=list)

    # ORM back-reference for collection.installed write-back after loose-file copy.
    # Holds a SoftwareCollection when source_type == "software", an
    # AppCollection when source_type == "app".
    _db_collection: "SoftwareCollection | AppCollection | None" = None


def resolve_launchable(
    collection_id: int,
    db: "Session",
) -> LaunchableEntity:
    """Resolve a SoftwareCollection into a LaunchableEntity via its launch leaf.

    Raises ValueError if the collection or its launch leaf is not found, or if
    no launch disc is configured.
    """
    from backend.models.software import SoftwareCollection, SoftwareItem

    c = db.get(SoftwareCollection, collection_id)
    if c is None:
        raise ValueError(f"SoftwareCollection {collection_id} not found")
    if not c.launch_disk_id:
        raise ValueError(f"SoftwareCollection {collection_id} has no launch disc configured")
    launch_leaf = db.get(SoftwareItem, c.launch_disk_id)
    if launch_leaf is None:
        raise ValueError(
            f"SoftwareCollection {collection_id}: launch disc leaf {c.launch_disk_id} not found"
        )
    all_leaves = (
        db.query(SoftwareItem)
        .filter(SoftwareItem.software_collection_id == c.id)
        .order_by(SoftwareItem.disc_number)
        .all()
    )

    return LaunchableEntity(
        collection_id=c.id,
        profile_id=c.profile_id,
        era=c.era,
        item_type=c.item_type,
        environment_id=c.environment_id,
        slug=c.slug,
        media_path=launch_leaf.file_path,
        folder_path=launch_leaf.folder_path,
        executable_path=launch_leaf.executable_path,
        launch_commands=c.launch_commands,
        launch_review_flagged=bool(c.launch_review_flagged),
        installed=c.installed,
        requires_install=c.requires_install,
        media_type=str(launch_leaf.file_type) if launch_leaf.file_type is not None else None,
        drive=c.drive,
        disc_paths=[leaf.file_path for leaf in all_leaves],
        _db_collection=c,
    )


def resolve_launchable_app(
    app_collection_id: int,
    db: "Session",
) -> LaunchableEntity:
    """Resolve an AppCollection into a LaunchableEntity via its launch item.

    Apps are always PC (item_type is fixed, not derived/stored) and always
    carry a non-null environment_id, so era is read off the linked
    Environment rather than the collection itself (see backend/models/app.py
    for why era is not duplicated onto AppCollection). drive is resolved from
    AppCollection.drive, the Drive row keyed by app_collection_id, mirroring
    how resolve_launchable reads SoftwareCollection.drive (see
    backend/models/drive.py for the exactly-one-of ownership rule enforced
    on Drive).

    Raises ValueError if the collection, its Environment, or its launch item
    is not found, or if no launch item is configured.
    """
    from backend.models.app import AppCollection, AppItem
    from backend.models.environment import Environment

    c = db.get(AppCollection, app_collection_id)
    if c is None:
        raise ValueError(f"AppCollection {app_collection_id} not found")
    environment = db.get(Environment, c.environment_id)
    if environment is None:
        raise ValueError(f"AppCollection {app_collection_id}: Environment {c.environment_id} not found")
    if not c.launch_disk_id:
        raise ValueError(f"AppCollection {app_collection_id} has no launch item configured")
    launch_item = db.get(AppItem, c.launch_disk_id)
    if launch_item is None:
        raise ValueError(
            f"AppCollection {app_collection_id}: launch item {c.launch_disk_id} not found"
        )
    all_items = (
        db.query(AppItem)
        .filter(AppItem.app_collection_id == c.id)
        .order_by(AppItem.id)
        .all()
    )

    return LaunchableEntity(
        collection_id=c.id,
        profile_id=c.profile_id,
        era=environment.era,
        item_type="pc",
        environment_id=c.environment_id,
        slug=c.slug,
        media_path=launch_item.file_path,
        folder_path=launch_item.folder_path,
        executable_path=launch_item.executable_path,
        launch_commands=c.launch_commands,
        launch_review_flagged=False,
        installed=c.installed,
        requires_install=c.requires_install,
        media_type=str(launch_item.file_type) if launch_item.file_type is not None else None,
        drive=c.drive,
        disc_paths=[item.file_path for item in all_items],
        source_type="app",
        _db_collection=c,
    )
