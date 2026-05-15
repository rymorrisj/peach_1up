from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import require_permission
from backend.core.settings import get_settings
from backend.models.settings import SettingsPatch, SettingsRead
from backend.models.user import User

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

_KNOWN_BINARY_KEYS = {"DOSBOX_PATH", "BOX86_PATH", "VIRTUALBOX_PATH"}
_ALL_PATH_KEYS = {
    "DOSBOX_PATH", "BOX86_PATH", "VIRTUALBOX_PATH",
    "DUCKSTATION_PATH", "PCSX2_PATH", "XEMU_PATH", "MESEN_PATH", "PROJECT64_PATH",
    "LIBRARY_PATH", "GAMES_PATH", "OS_PATH", "ROM_PATH", "BIOS_PATH", "TOOLS_PATH",
    "PROFILES_PATH",
}

_EMULATOR_SLUG_TO_KEY: dict[str, str] = {
    "dosbox-x":    "DOSBOX_PATH",
    "86box":       "BOX86_PATH",
    "virtualbox":  "VIRTUALBOX_PATH",
    "duckstation": "DUCKSTATION_PATH",
    "pcsx2":       "PCSX2_PATH",
    "xemu":        "XEMU_PATH",
    "mesen":       "MESEN_PATH",
    "project64":   "PROJECT64_PATH",
}

_LIBRARY_KEY_MAP: dict[str, str] = {
    "library_path":  "LIBRARY_PATH",
    "games_path":    "GAMES_PATH",
    "os_path":       "OS_PATH",
    "rom_path":      "ROM_PATH",
    "bios_path":     "BIOS_PATH",
    "tools_path":    "TOOLS_PATH",
    "profiles_path": "PROFILES_PATH",
}


class PathValidationResult(BaseModel):
    key: str
    path: str
    exists: bool
    executable: bool


class ValidateResponse(BaseModel):
    results: list[PathValidationResult]


class EmulatorPathBody(BaseModel):
    slug: str
    path: str


class LibraryPathBody(BaseModel):
    key: Literal["library_path", "games_path", "os_path", "rom_path", "bios_path", "tools_path", "profiles_path"]
    path: str


def _check_traversal(path_str: str) -> Path:
    from backend.service.utils.path_utils import normalise_path
    return normalise_path(path_str)


@router.get("", response_model=dict)
def get_all_settings():
    svc = get_settings()
    state = svc._require_init()
    _SENSITIVE = {"SECRET", "PASSWORD", "TOKEN"}
    return {
        k: v for k, v in state.items()
        if not k.startswith("_") and not any(s in k.upper() for s in _SENSITIVE)
    }


@router.patch("")
def patch_settings(body: SettingsPatch, _: User = require_permission("can_edit_settings")):
    svc = get_settings()
    for key, value in body.updates.items():
        if key in _ALL_PATH_KEYS:
            svc.set_path(key, value or "")
        else:
            state = svc._require_init()
            state[key] = value
            svc._save()
    return {"updated": list(body.updates.keys())}


@router.post("/validate", response_model=ValidateResponse)
def validate_paths():
    svc = get_settings()
    results = []
    for key in _KNOWN_BINARY_KEYS:
        raw = svc.get(key, "") or ""
        p = Path(raw) if raw else None
        results.append(PathValidationResult(
            key=key,
            path=raw,
            exists=p.exists() if p else False,
            executable=p.is_file() if p else False,
        ))
    return ValidateResponse(results=results)


@router.get("/first-run-status")
def get_first_run_status():
    svc = get_settings()
    first_run_complete = not svc.is_first_run()

    return {
        "first_run_complete": first_run_complete,
        "emulators": svc.compute_setup_status(),
        "paths": {
            "library_path":  svc.get("LIBRARY_PATH") or None,
            "games_path":    svc.get("GAMES_PATH") or None,
            "os_path":       svc.get("OS_PATH") or None,
            "rom_path":      svc.get("ROM_PATH") or None,
            "bios_path":     svc.get("BIOS_PATH") or None,
            "tools_path":    svc.get("TOOLS_PATH") or None,
            "profiles_path": svc.get("PROFILES_PATH") or None,
        },
    }


@router.post("/emulator-path")
def set_emulator_path(body: EmulatorPathBody, _: User = require_permission("can_edit_settings")):
    if body.slug not in _EMULATOR_SLUG_TO_KEY:
        raise HTTPException(status_code=400, detail=f"Unknown emulator slug: {body.slug!r}")

    try:
        resolved = _check_traversal(body.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not resolved.exists():
        raise HTTPException(status_code=400, detail="Path does not exist.")
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file.")

    settings_key = _EMULATOR_SLUG_TO_KEY[body.slug]
    svc = get_settings()
    svc.set_path(settings_key, str(resolved))

    return {"slug": body.slug, "path": str(resolved), "available": True}


@router.post("/library-path")
def set_library_path(body: LibraryPathBody, _: User = require_permission("can_edit_settings")):
    try:
        resolved = _check_traversal(body.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not resolved.exists():
        raise HTTPException(status_code=400, detail="Path does not exist.")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory.")

    settings_key = _LIBRARY_KEY_MAP[body.key]
    svc = get_settings()
    svc.set_path(settings_key, str(resolved))

    return {"key": body.key, "path": str(resolved)}


@router.post("/complete-first-run")
def complete_first_run(db: Session = Depends(get_db), _: User = require_permission("can_edit_settings")):
    from backend.models.settings import Settings as SettingsModel
    row = db.get(SettingsModel, "first_run_complete")
    if row:
        row.value = "true"
    else:
        row = SettingsModel(key="first_run_complete", value="true")
        db.add(row)
    db.commit()

    svc = get_settings()
    try:
        svc.mark_first_run_complete()
    except OSError:
        # Config dir is read-only (e.g. read-only mount).
        # In-memory state was already updated before the file write failed.
        pass

    return {"success": True}
