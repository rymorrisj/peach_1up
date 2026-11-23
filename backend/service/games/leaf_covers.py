"""Display-disc lookup, the cover library guard, and cleanup of app-owned
per-disc cover art (META-2).

Earlier versions wrote fetched disc covers to
MEDIA_PATH/_game_covers/game-item-{id}{ext}. Nothing writes there now (a game
cover comes from Accept All, see cover_from_media.py), but game delete still
removes those files so a reused leaf id never inherits one. Covers stored
anywhere else (user-set paths, linked media) are left untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional

from fastapi import HTTPException

from backend.core.logger import get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.models.game import GameItem, GameItemBundle

_log = get_logger(__name__)


def effective_display_leaf(bundle: "GameItemBundle") -> Optional["GameItem"]:
    """The disc whose cover the card shows: display_disk_id, else
    launch_disk_id, else the first disc by disc_number. None when the bundle
    has no discs. Mirrors resolveLeafCoverArt (frontend/src/pages/Software/types.ts)."""
    wanted = bundle.display_disk_id or bundle.launch_disk_id
    leaf = next((i for i in bundle.items if i.id == wanted), None)
    if leaf is None and bundle.items:
        return bundle.items[0]
    return leaf


def require_cover_in_library(resolved: Path, raw: str) -> None:
    """A cover renders from /media/<path relative to LIBRARY_PATH>, the same
    root GameItemRead resolves cover_art_url against, so a path outside it
    would save and then show a blank card. Checked before any existence test,
    so the 422 says nothing about whether the path exists."""
    from backend.service.utils import settings as _s

    library = _s.get("LIBRARY_PATH", "") or ""
    if library and resolved.is_relative_to(Path(library).resolve()):
        return
    _log.warning("Rejected game cover_art_path %r: outside LIBRARY_PATH", raw)
    raise HTTPException(
        status_code=422,
        detail="cover_art_path must be inside the library folder (its software or media folders).",
    )


def leaf_cover_stem(leaf_id: int) -> str:
    return f"game-item-{leaf_id}"


def app_owned_leaf_cover(raw: Optional[str], leaf_id: int) -> Optional[Path]:
    """*raw* resolved, when it is this leaf's own file directly inside
    _game_covers; None for anything else (including when MEDIA_PATH is not
    configured)."""
    from backend.service.media.file_cleanup import lexical_key
    from backend.service.utils.path_utils import game_covers_root, is_untrusted_remote_path

    if not raw or is_untrusted_remote_path(raw):
        return None
    try:
        root = game_covers_root()
        resolved = Path(raw).resolve()
    except OSError, ValueError:
        return None
    if lexical_key(str(resolved.parent)) != lexical_key(str(root)) or resolved.stem != leaf_cover_stem(leaf_id):
        return None
    return resolved


def _still_referenced(raw: str, db: "Session") -> bool:
    from backend.models.game import GameItem
    from backend.models.media import MediaItem, MediaItemBundle
    from backend.service.media.file_cleanup import matching_row_ids, path_keys

    targets = path_keys(raw)
    return any(
        matching_row_ids(db, model, columns, targets)
        for model, columns in (
            (GameItem, ("cover_art_path",)),
            (MediaItem, ("file_path", "cover_art_path")),
            (MediaItemBundle, ("cover_art_path",)),
        )
    )


def _all_covers_for(leaf_id: int) -> list[Path]:
    """Every game-item-{id}.* file directly inside _game_covers, so a leaf
    delete also sweeps covers left by an earlier format change."""
    from backend.service.utils.path_utils import game_covers_root

    try:
        root = game_covers_root()
    except ValueError:
        return []
    if not root.is_dir():
        return []
    stem = leaf_cover_stem(leaf_id)
    return [p for p in root.iterdir() if p.is_file() and p.stem == stem]


def remove_app_owned_leaf_covers(leaves: Iterable[tuple[int, Optional[str]]], db: "Session") -> None:
    """Unlink each (leaf id, cover_art_path) cover that app_owned_leaf_cover
    accepts and no remaining row references, plus every game-item-{id}.* file
    of those leaves. Run after the commit that dropped the leaves. Never
    raises."""
    for leaf_id, raw in leaves:
        candidates = [str(p) for p in _all_covers_for(leaf_id)]
        if raw and raw not in candidates:
            candidates.append(raw)
        for candidate in candidates:
            _remove_one(leaf_id, candidate, db)


def _remove_one(leaf_id: int, raw: str, db: "Session") -> None:
    path = app_owned_leaf_cover(raw, leaf_id)
    if path is None:
        return
    try:
        if _still_referenced(raw, db):
            return
    except Exception as exc:  # noqa: BLE001, never delete on a failed check
        _log.warning("Kept disc cover %s, reference check failed: %s", path, exc)
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        _log.warning("Could not delete disc cover %s: %s", path, exc)
