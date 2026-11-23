"""Which Media files the app may remove from disk, and the cover references
to clear when it does (MED-17, and Accept All's Replace).

A file is removable only when all of these hold:

- it resolves strictly inside MEDIA_PATH (never the root itself), outside
  the app-internal _game_covers and _asset_staging directories
- it is a regular file
- no MediaItem row outside the set being removed has it as file_path, and
  no game or app leaf has it as file_path or executable_path (checked
  again just before the unlink)

Every path comparison here goes through a normalised key (normcase and
normpath of the path, plus of its resolved form when it is safe to
resolve), never a raw string match, so case, slash direction and a trailing
separator cannot hide a reference. UNC and device paths are never resolved.

Removal is unlink only. An emptied parent directory is removed with rmdir,
never rmtree, and only when it sits inside MEDIA_PATH.

Callers commit the DB change first and remove files afterwards, so a failed
commit never loses a file that rows still point at.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from sqlalchemy import or_

from backend.core.logger import get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_log = get_logger(__name__)

_CHUNK = 500


def lexical_key(raw: str) -> str:
    """Case-insensitive (on Windows), slash-insensitive comparison key with
    no trailing separator. Never touches the filesystem."""
    return os.path.normcase(os.path.normpath(raw))


def path_keys(raw: str | None) -> set[str]:
    """Every comparison key for *raw*: its lexical key, plus the key of its
    resolved form so a junction, mapped drive or short name still matches.
    A UNC or device path is never resolved."""
    if not raw:
        return set()
    from backend.service.utils.path_utils import is_untrusted_remote_path

    keys = {lexical_key(raw)}
    if not is_untrusted_remote_path(raw):
        try:
            keys.add(lexical_key(str(Path(raw).resolve())))
        except (OSError, ValueError):
            pass
    return keys


def _keys_of(paths: Iterable[str | None]) -> set[str]:
    keys: set[str] = set()
    for raw in paths:
        keys |= path_keys(raw)
    return keys


def matching_row_ids(db: "Session", model, columns: tuple[str, ...], targets: set[str]) -> set[int]:
    """Ids of *model* rows where any of *columns* is a path matching one of
    the *targets* keys."""
    if not targets:
        return set()
    cols = [getattr(model, name) for name in columns]
    rows = db.query(model.id, *cols).filter(or_(*[c.isnot(None) for c in cols]))
    return {row[0] for row in rows if any(path_keys(value) & targets for value in row[1:])}


def _owned_path(raw: str, root: Path) -> Path | None:
    from backend.service.utils.path_utils import APP_INTERNAL_MEDIA_DIRNAMES, is_untrusted_remote_path

    if is_untrusted_remote_path(raw):
        return None
    try:
        resolved = Path(raw).resolve()
    except (OSError, ValueError):
        return None
    prefix = lexical_key(str(root)).rstrip(os.sep) + os.sep
    key = lexical_key(str(resolved))
    if not key.startswith(prefix) or len(key) == len(prefix):
        return None
    internal = {os.path.normcase(name) for name in APP_INTERNAL_MEDIA_DIRNAMES}
    if key[len(prefix):].split(os.sep, 1)[0] in internal:
        return None
    return resolved if resolved.is_file() else None


def _referenced_keys(excluded_item_ids: set[int], db: "Session") -> set[str]:
    """Keys of every file a MediaItem outside *excluded_item_ids*, or any
    game or app leaf, uses (file_path or executable_path)."""
    from backend.models.app import AppItem
    from backend.models.game import GameItem
    from backend.models.media import MediaItem

    keys: set[str] = set()
    for item_id, file_path in db.query(MediaItem.id, MediaItem.file_path).filter(MediaItem.file_path.isnot(None)):
        if item_id not in excluded_item_ids:
            keys |= path_keys(file_path)
    for model in (GameItem, AppItem):
        for file_path, executable_path in db.query(model.file_path, model.executable_path):
            keys |= path_keys(file_path)
            keys |= path_keys(executable_path)
    return keys


def removable_media_files(
    file_paths: Iterable[str], excluded_item_ids: set[int], db: "Session",
) -> list[str]:
    """The subset of *file_paths* safe to unlink once the MediaItem rows in
    *excluded_item_ids* are gone. Returns the stored strings, deduplicated
    by resolved file. Returns nothing when MEDIA_PATH is not configured."""
    from backend.service.utils.path_utils import media_root

    try:
        root = media_root()
    except ValueError:
        return []
    referenced: set[str] | None = None
    result: list[str] = []
    seen: set[str] = set()
    for raw in file_paths:
        if not raw:
            continue
        resolved = _owned_path(raw, root)
        if resolved is None:
            continue
        key = lexical_key(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        if referenced is None:
            referenced = _referenced_keys(excluded_item_ids, db)
        if path_keys(raw) & referenced:
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

    targets = _keys_of(file_paths)
    if not targets:
        return 0
    cleared = 0
    for model in (GameItem, AppItem, MediaItemBundle, MediaItem):
        ids = sorted(matching_row_ids(db, model, ("cover_art_path",), targets))
        for start in range(0, len(ids), _CHUNK):
            cleared += (
                db.query(model)
                .filter(model.id.in_(ids[start:start + _CHUNK]))
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
    root_key = lexical_key(str(root))
    removed: list[str] = []
    referenced: set[str] | None = None
    for raw in file_paths:
        resolved = _owned_path(raw, root)
        if resolved is None:
            continue
        try:
            if referenced is None:
                referenced = _referenced_keys(set(), db)
            if path_keys(raw) & referenced:
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
        parent_key = lexical_key(str(parent))
        if parent_key != root_key and parent_key.startswith(root_key.rstrip(os.sep) + os.sep):
            try:
                parent.rmdir()
            except OSError:
                pass
    return removed
