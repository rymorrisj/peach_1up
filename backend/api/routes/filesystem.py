import string
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.dependencies import require_library_or_platform_editor
from backend.models.filesystem import BrowseResult, DrivesResult
from backend.models.user import User

router = APIRouter(prefix="/api/v1/filesystem", tags=["filesystem"])


def _allowed_roots() -> list[Path]:
    """Return all filesystem roots the browser is permitted to access."""
    from backend.core.settings import get_settings
    svc = get_settings()
    roots: list[Path] = []
    for key in ("LIBRARY_PATH", "MEDIA_PATH", "OS_PATH", "ROMS_PATH", "PROFILES_PATH"):
        val = svc.get(key, "") or ""
        if val:
            try:
                roots.append(Path(val).resolve())
            except Exception:
                pass
    if sys.platform == "win32":
        for letter in string.ascii_uppercase:
            try:
                drive = Path(f"{letter}:\\")
                if drive.exists():
                    roots.append(drive.resolve())
            except Exception:
                pass
    return roots


def _within_allowed(resolved: Path, roots: list[Path]) -> bool:
    return any(resolved == r or resolved.is_relative_to(r) for r in roots)


def _get_drive_label(letter: str) -> str:
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(261)
        ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
            f"{letter}:\\", buf, 261, None, None, None, None, 0,
        )
        name = buf.value
        return f"{name} ({letter}:)" if name else f"Local Disk ({letter}:)"
    except Exception:
        return f"Drive {letter}:"


@router.get("/drives", response_model=DrivesResult)
def list_drives(_: User = Depends(require_library_or_platform_editor)):
    """Return available Windows drive letters. 404 on non-Windows."""
    if sys.platform != "win32":
        raise HTTPException(status_code=404, detail="Drive listing is only available on Windows.")
    drives = []
    for letter in string.ascii_uppercase:
        try:
            drive = Path(f"{letter}:\\")
            if drive.exists():
                drives.append({"letter": letter, "path": str(drive), "label": _get_drive_label(letter)})
        except Exception:
            pass
    return {"drives": drives}


@router.get("/browse", response_model=BrowseResult)
def browse(
    path: str | None = Query(default=None),
    show_files: bool = Query(default=True),
    extensions: str | None = Query(default=None),
    _: User = Depends(require_library_or_platform_editor),
):
    """Browse the filesystem within the configured allowed roots.

    When path is omitted, returns the configured base directories as the home
    listing. On Windows, callers should also fetch /drives to show a drive picker.
    """
    roots = _allowed_roots()

    if path is None:
        from backend.core.settings import get_settings
        svc = get_settings()
        _LABELS = {
            "LIBRARY_PATH": "Library",
            "MEDIA_PATH": "Media",
            "OS_PATH": "OS Images",
            "ROMS_PATH": "ROMs",
            "PROFILES_PATH": "Profiles",
        }
        dirs = []
        for key, label in _LABELS.items():
            val = svc.get(key, "") or ""
            if val:
                p = Path(val).resolve()
                if p.is_dir():
                    dirs.append({"name": label, "path": str(p)})
        return {"current_path": None, "parent_path": None, "dirs": dirs, "files": []}

    from backend.service.utils.path_utils import normalise_path
    try:
        resolved = normalise_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not _within_allowed(resolved, roots):
        raise HTTPException(status_code=400, detail="Path is outside the permitted directories.")

    if not resolved.exists():
        raise HTTPException(status_code=400, detail="Path does not exist.")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory.")

    ext_filter: set[str] | None = None
    if extensions:
        ext_filter = {e.lower().strip().lstrip(".") for e in extensions.split(",") if e.strip()}

    dirs_out: list[dict] = []
    files_out: list[dict] = []
    try:
        for entry in sorted(resolved.iterdir(), key=lambda e: (e.is_file(), e.name.lower())):
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if not entry.name.startswith("."):
                    dirs_out.append({"name": entry.name, "path": str(entry)})
            elif show_files and entry.is_file():
                ext = entry.suffix.lower().lstrip(".")
                if ext_filter is None or ext in ext_filter:
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        size = 0
                    files_out.append({"name": entry.name, "path": str(entry), "size_bytes": size})
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied reading directory.")

    parent_obj = resolved.parent
    parent_path: str | None = None
    if parent_obj != resolved:
        if _within_allowed(parent_obj, roots):
            parent_path = str(parent_obj)

    return {
        "current_path": str(resolved),
        "parent_path": parent_path,
        "dirs": dirs_out,
        "files": files_out,
    }
