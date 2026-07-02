from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from backend.models.drive import Drive
    from backend.models.library import LibraryItem


@dataclass
class LaunchableEntity:
    """Fully-resolved inputs for a single launch, independent of source type.

    One of item_id / set_id is set; the other is None.
    All fields are plain values — no ORM objects except drive (pre-resolved
    to avoid divergent lookup patterns between items and sets) and _db_item
    (back-ref for the installed=True write-back after loose-file hydration).
    """

    item_id: int | None
    set_id: int | None

    profile_id: int | None
    era: str
    media_path: str
    executable_path: str | None
    # None = never configured (media file may auto-run); [] = explicitly cleared
    # (no auto-run, drop to the DOS prompt); non-empty = run these commands.
    launch_commands: list[str] | None = None
    launch_review_flagged: bool = False

    # Drive hydration fields
    installed: bool = False
    requires_install: bool = False
    media_type: str | None = None
    # Source folder of loose files to copy onto the drive. media_path is
    # reassigned to a single resolved launch file at add time (items.py), so
    # folder_path is the authoritative directory for loose-file hydration.
    # None for set entities (disc images are never loose-file hydrated).
    folder_path: str | None = None

    # Pre-resolved Drive ORM object (None if no drive associated).
    drive: "Drive | None" = None

    # For set launches: all disc media_paths in disc_number order. Empty for item launches.
    disc_paths: list[str] = field(default_factory=list)

    # ORM back-reference for item.installed write-back after loose-file copy.
    # None for set entities — disc images never trigger loose-file hydration.
    _db_item: "LibraryItem | None" = None


def resolve_launchable(
    *,
    item_id: int | None = None,
    set_id: int | None = None,
    db: "Session",
) -> LaunchableEntity:
    """Resolve a LibraryItem or LibrarySet into a LaunchableEntity.

    Exactly one of item_id / set_id must be provided.
    Raises ValueError if the record or its launch disc is not found.
    """
    from backend.models.drive import Drive
    from backend.models.library import LibraryItem
    from backend.models.library_set import LibrarySet, LibrarySetItem

    if item_id is not None:
        item = db.get(LibraryItem, item_id)
        if item is None:
            raise ValueError(f"LibraryItem {item_id} not found")
        drive = db.query(Drive).filter(Drive.library_item_id == item.id).first()
        return LaunchableEntity(
            item_id=item.id,
            set_id=None,
            profile_id=item.profile_id,
            era=item.era,
            media_path=item.media_path,
            folder_path=item.folder_path,
            executable_path=item.executable_path,
            launch_commands=item.launch_commands,
            launch_review_flagged=bool(item.launch_review_flagged),
            installed=item.installed,
            requires_install=item.requires_install,
            media_type=str(item.media_type) if item.media_type is not None else None,
            drive=drive,
            _db_item=item,
        )

    if set_id is not None:
        s = db.get(LibrarySet, set_id)
        if s is None:
            raise ValueError(f"LibrarySet {set_id} not found")
        if not s.launch_disk_id:
            raise ValueError(f"LibrarySet {set_id} has no launch disc configured")
        launch_disc = db.get(LibrarySetItem, s.launch_disk_id)
        if launch_disc is None:
            raise ValueError(
                f"LibrarySet {set_id}: launch disc item {s.launch_disk_id} not found"
            )
        drive = db.get(Drive, s.drive_id) if s.drive_id else None
        all_items = (
            db.query(LibrarySetItem)
            .filter(LibrarySetItem.set_id == s.id)
            .order_by(LibrarySetItem.disc_number)
            .all()
        )
        return LaunchableEntity(
            item_id=None,
            set_id=s.id,
            profile_id=s.profile_id,
            era=s.era,
            media_path=launch_disc.media_path,
            executable_path=launch_disc.executable_path,
            launch_commands=[],
            launch_review_flagged=bool(s.launch_review_flagged),
            # Disc images are never loose-file hydrated; installed=True short-circuits
            # the hydration condition without needing a real installed state.
            installed=True,
            requires_install=s.requires_install,
            media_type=None,
            drive=drive,
            disc_paths=[item.media_path for item in all_items],
            _db_item=None,
        )

    raise ValueError("Must provide either item_id or set_id")
