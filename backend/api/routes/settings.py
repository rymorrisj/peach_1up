from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import require_permission
from backend.core.settings import get_settings
from backend.models.settings import SettingsPatch
from backend.models.user import User

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

_ALL_PATH_KEYS = {
    "LIBRARY_PATH", "MEDIA_PATH", "OS_PATH",
    "ROMS_PATH", "PROFILES_PATH",
}

_LIBRARY_KEY_MAP: dict[str, str] = {
    "library_path":  "LIBRARY_PATH",
    "media_path":    "MEDIA_PATH",
    "os_path":       "OS_PATH",
    "roms_path":     "ROMS_PATH",
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
    key: Literal["library_path", "media_path", "os_path", "roms_path", "profiles_path"]
    path: str


def _check_traversal(path_str: str) -> Path:
    from backend.service.utils.path_utils import normalise_path
    return normalise_path(path_str)


_SENSITIVE_KEYS = {"AI_API_KEY", "IGDB_API_KEY"}


@router.get("", response_model=dict)
def get_all_settings():
    svc = get_settings()
    state = svc._require_init()
    return {
        k: v for k, v in state.items()
        if not k.startswith("_") and k.upper() not in _SENSITIVE_KEYS
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
    return ValidateResponse(results=[])


@router.get("/first-run-status")
def get_first_run_status(request: Request, db: Session = Depends(get_db)):
    from backend.models.settings import Settings as SettingsModel
    svc = get_settings()
    row = db.get(SettingsModel, "first_run_complete")
    first_run_complete = row is not None and row.value == "true"
    owner_exists = db.query(User).filter(User.is_owner.is_(True)).count() > 0

    return {
        "first_run_complete": first_run_complete,
        "owner_exists": owner_exists,
        "emulators": svc.compute_setup_status(),
        "paths": {
            "library_path":  svc.get("LIBRARY_PATH") or None,
            "media_path":    svc.get("MEDIA_PATH") or None,
            "os_path":       svc.get("OS_PATH") or None,
            "roms_path":     svc.get("ROMS_PATH") or None,
            "profiles_path": svc.get("PROFILES_PATH") or None,
        },
        "path_warnings": getattr(request.app.state, "path_warnings", []),
    }


@router.get("/owner-status")
def get_owner_status(db: Session = Depends(get_db)):
    """Unauthenticated — checked once at app load so the frontend can detect
    a missing/locked owner row and render the recovery fallback page."""
    owner = db.query(User).filter(User.is_owner.is_(True)).first()
    return {"owner_broken": owner is None or owner.is_locked}


@router.post("/emulator-path")
def set_emulator_path(body: EmulatorPathBody, _: User = require_permission("can_edit_settings")):
    from backend.service.utils.emulator_catalog import get_settings_key as _get_settings_key, get_emulator as _get_emulator
    try:
        _get_emulator(body.slug)
        settings_key = _get_settings_key(body.slug)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown emulator slug: {body.slug!r}")
    if settings_key not in _ALL_PATH_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown emulator slug: {body.slug!r}")

    try:
        resolved = _check_traversal(body.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not resolved.exists():
        raise HTTPException(status_code=400, detail="Path does not exist.")
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file.")

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
    from backend.api.middleware.security import set_first_run_complete
    from backend.models.settings import Settings as SettingsModel
    row = db.get(SettingsModel, "first_run_complete")
    if row:
        row.value = "true"
    else:
        row = SettingsModel(key="first_run_complete", value="true")
        db.add(row)
    db.commit()

    set_first_run_complete()

    return {"success": True}
