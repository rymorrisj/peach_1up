"""Which Media files the app may remove from disk, and the cover references
to clear when it does (MED-17, and Accept All's Replace).

A file is removable only when all of these hold:

- it resolves strictly inside MEDIA_PATH (never the root itself), outside
  the app-internal _game_covers and _asset_staging directories
- it is a regular file
- no MediaItem row outside the set being removed has it as file_path, and
  no game or app leaf has it as file_path or executable_path (checked
  again just before the unlink)

Removal is unlink only. An emptied parent directory is removed with rmdir,
never rmtree, and only when it sits inside MEDIA_PATH.

Callers commit the DB change first and remove files afterwards, so a failed
commit never loses a file that rows still point at.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from backend.core.logger import get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_log = get_logger(__name__)


def path_variants(raw: str | None) -> set[str]:
    """The stored string plus its resolved form, so a reference written in
    a different but equivalent spelling still matches. A UNC or device path
    is never resolved."""
    if not raw:
        return set()
    from backend.service.utils.path_utils import is_untrusted_remote_path

    variants = {raw}
    if not is_untrusted_remote_path(raw):
        try:
            variants.add(str(Path(raw).resolve()))
        except (OSError, ValueError):
            pass
    return variants


def _owned_path(raw: str, root: Path) -> Path | None:
    from backend.service.utils.path_utils import APP_INTERNAL_MEDIA_DIRNAMES, is_untrusted_remote_path

    if is_untrusted_remote_path(raw):
        return None
    try:
        resolved = Path(raw).resolve()
    except (OSError, ValueError):
        return None
    if resolved == root or not resolved.is_relative_to(root):
        return None
    if resolved.relative_to(root).parts[0] in APP_INTERNAL_MEDIA_DIRNAMES:
        return None
    return resolved if resolved.is_file() else None


def _referenced_elsewhere(raw: str, excluded_item_ids: set[int], db: "Session") -> bool:
    """True when a MediaItem outside *excluded_item_ids*, or any game or app
    leaf, uses *raw* as its file (file_path or executable_path)."""
    from backend.models.app import AppItem
    from backend.models.game import GameItem
    from backend.models.media import MediaItem

    variants = path_variants(raw)
    q = db.query(MediaItem.id).filter(MediaItem.file_path.in_(variants))
    if excluded_item_ids:
        q = q.filter(MediaItem.id.notin_(excluded_item_ids))
    if q.first() is not None:
        return True
    for model in (GameItem, AppItem):
        hit = db.query(model.id).filter(
            model.file_path.in_(variants) | model.executable_path.in_(variants)
        ).first()
        if hit is not None:
            return True
    return False


def removable_media_files(
    file_paths: Iterable[str], excluded_item_ids: set[int], db: "Session",
) -> list[str]:
    """The subset of *file_paths* safe to unlink once the MediaItem rows in
    *excluded_item_ids* are gone. Returns the stored strings, deduplicated.
    Returns nothing when MEDIA_PATH is not configured."""
    from backend.service.utils.path_utils import media_root

    try:
        root = media_root()
    except ValueError:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for raw in file_paths:
        if not raw or raw in seen:
            continue
        seen.add(raw)
        if _owned_path(raw, root) is None or _referenced_elsewhere(raw, excluded_item_ids, db):
            continue
        result.append(raw)
    return result


def clear_cover_references(file_paths: Iterable[str], db: "Session") -> int:
    """Null every game disc, app leaf, media bundle and media item
    cover_art_path that points at one of *file_paths*. Flushes nothing; the
    caller commits."""
    from backend.models.app import AppItem
    from backend.models.game import GameItem
    from backend.models.media import MediaItem, MediaItemBundle

    variants: set[str] = set()
    for raw in file_paths:
        variants |= path_variants(raw)
    if not variants:
        return 0
    cleared = 0
    for model in (GameItem, AppItem, MediaItemBundle, MediaItem):
        cleared += (
            db.query(model)
            .filter(model.cover_art_path.in_(variants))
            .update({model.cover_art_path: None}, synchronize_session="fetch")
        )
    return cleared


def remove_files(file_paths: Iterable[str], db: "Session") -> list[str]:
    """Unlink each path that is still owned by location (see _owned_path)
    and, re-checked now that the caller's commit is done, still referenced
    by no row; then rmdir its parent if that left it empty. Never raises: a
    failure is logged and the file is left in place. Returns the paths
    actually removed."""
    from backend.service.utils.path_utils import media_root

    try:
        root = media_root()
    except ValueError:
        return []
    removed: list[str] = []
    for raw in file_paths:
        resolved = _owned_path(raw, root)
        if resolved is None:
            continue
        try:
            if _referenced_elsewhere(raw, set(), db):
                _log.info("Kept media file still in use: %s", resolved)
                continue
        except Exception as exc:  # noqa: BLE001, never delete on a failed check
            _log.warning("Kept media file %s, reference check failed: %s", resolved, exc)
            continue
        try:
            resolved.unlink()
            removed.append(raw)
            _log.info("Deleted media file: %s", resolved)
        except OSError as exc:
            _log.warning("Could not delete media file %s: %s", resolved, exc)
            continue
        parent = resolved.parent
        if parent != root and parent.is_relative_to(root):
            try:
                parent.rmdir()
            except OSError:
                pass
    return removed
