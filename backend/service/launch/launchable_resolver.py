from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from backend.models.drive import Drive
    from backend.models.library import LibraryCollection


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
    slug: str | None
    media_path: str
    executable_path: str | None
    # None = never configured (media file may auto-run); [] = explicitly cleared
    # (no auto-run, drop to the DOS prompt); non-empty = run these commands.
    launch_commands: list[str] | None = None
    launch_review_flagged: bool = False

    # Environment hydration fields (DOS pattern-1 copy gate).
    installed: bool = False
    requires_install: bool = False
    media_type: str | None = None
    # Source folder of loose files to copy onto the drive. media_path is
    # reassigned to a single resolved launch file at add time (items.py), so
    # folder_path is the authoritative directory for loose-file hydration.
    folder_path: str | None = None

    # Pre-resolved Drive ORM object (None if no drive associated). Populated from
    # the collection's LibraryCollection.drive relationship (None for non-DOS).
    drive: "Drive | None" = None

    # All disc media_paths in disc_number order (a collection-of-one yields a
    # single-element list — the multi-image builder no-ops when len <= 1).
    disc_paths: list[str] = field(default_factory=list)

    # ORM back-reference for collection.installed write-back after loose-file copy.
    _db_collection: "LibraryCollection | None" = None


def resolve_launchable(
    collection_id: int,
    db: "Session",
) -> LaunchableEntity:
    """Resolve a LibraryCollection into a LaunchableEntity via its launch leaf.

    Raises ValueError if the collection or its launch leaf is not found, or if
    no launch disc is configured.
    """
    from backend.models.library import LibraryCollection, LibraryItem

    c = db.get(LibraryCollection, collection_id)
    if c is None:
        raise ValueError(f"LibraryCollection {collection_id} not found")
    if not c.launch_disk_id:
        raise ValueError(f"LibraryCollection {collection_id} has no launch disc configured")
    launch_leaf = db.get(LibraryItem, c.launch_disk_id)
    if launch_leaf is None:
        raise ValueError(
            f"LibraryCollection {collection_id}: launch disc leaf {c.launch_disk_id} not found"
        )
    all_leaves = (
        db.query(LibraryItem)
        .filter(LibraryItem.library_collection_id == c.id)
        .order_by(LibraryItem.disc_number)
        .all()
    )

    return LaunchableEntity(
        collection_id=c.id,
        profile_id=c.profile_id,
        era=c.era,
        slug=c.slug,
        media_path=launch_leaf.media_path,
        folder_path=launch_leaf.folder_path,
        executable_path=launch_leaf.executable_path,
        launch_commands=c.launch_commands,
        launch_review_flagged=bool(c.launch_review_flagged),
        installed=c.installed,
        requires_install=c.requires_install,
        media_type=str(launch_leaf.media_type) if launch_leaf.media_type is not None else None,
        drive=c.drive,
        disc_paths=[leaf.media_path for leaf in all_leaves],
        _db_collection=c,
    )
