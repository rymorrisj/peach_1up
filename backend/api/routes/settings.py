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
    "LIBRARY_PATH", "SOFTWARE_PATH", "MEDIA_PATH", "OS_PATH",
    "ROMS_PATH", "PROFILES_PATH",
}

_LIBRARY_KEY_MAP: dict[str, str] = {
    "library_path":  "LIBRARY_PATH",
    "software_path": "SOFTWARE_PATH",
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


class LibraryPathBody(BaseModel):
    key: Literal["library_path", "media_path", "os_path", "roms_path", "profiles_path"]
    path: str


def _check_traversal(path_str: str) -> Path:
    from backend.service.utils.path_utils import normalise_path
    return normalise_path(path_str)


# Still "sensitive" in the sense of being scrubbed from GET-all, even though
# none of the four live in app_settings any more — they're .env-backed (see
# env_secrets.py). Kept as a real filter (not dead code) as defense in depth
# in case a future source ever merges into `state`.
_SENSITIVE_KEYS = {
    "AI_API_KEY", "IGDB_ACCESS_TOKEN", "IGDB_CLIENT_ID", "IGDB_CLIENT_SECRET",
    "PIN_PEPPER", "THEGAMESDB_API_KEY",
}

# Of the sensitive keys, these four route through .env via the generic PATCH
# endpoint below. PIN_PEPPER is excluded — it has its own dedicated route
# because changing it requires re-hashing the owner PIN (see patch_pin_pepper).
_ENV_SECRET_KEYS = {"THEGAMESDB_API_KEY", "AI_API_KEY", "IGDB_CLIENT_ID", "IGDB_CLIENT_SECRET"}

# The only keys a can_edit_settings user may write through the generic PATCH
# endpoint. Anything not listed here is refused — notably ALLOW_NETWORK_ACCESS
# (relaxes the network security boundary), reset_db (destructive), and any
# rating_ordinals key (would silently reshape every user's content-rating cap).
# PIN_PEPPER is handled by its own dedicated route and is intentionally absent.
# Path keys and _ENV_SECRET_KEYS are each routed through their own dedicated
# write path below (set_path() / set_env_secret()) rather than written to
# app_settings state raw.
_USER_WRITABLE_KEYS = _ALL_PATH_KEYS | _ENV_SECRET_KEYS | {
    "suppress_confirmations",
    "delete_media_on_removal",
    "delete_original_on_upload",
    "metadata_provider",
}


@router.get("", response_model=dict)
def get_all_settings(_: User = require_permission("can_edit_settings")):
    svc = get_settings()
    state = svc._require_init()
    return {
        k: v for k, v in state.items()
        if not k.startswith("_") and k.upper() not in _SENSITIVE_KEYS
    }


class LibraryDefaultsResult(BaseModel):
    delete_media_on_removal: bool
    delete_original_on_upload: bool


@router.get("/library-defaults", response_model=LibraryDefaultsResult)
def get_library_defaults(_: User = require_permission("can_manage_software")):
    """Narrow, can_manage_software-gated read of the two boolean defaults that
    library-editing surfaces (Library list, collection detail, Add Media) need
    to seed their own per-action checkboxes. GET /api/v1/settings (the full
    payload) is can_edit_settings-gated — a sub-account can legitimately have
    can_manage_software without can_edit_settings, and calling the full endpoint
    from those surfaces 403s for that account shape. This endpoint exists so
    those surfaces never need the broader permission just to read two flags.
    """
    svc = get_settings()
    return {
        "delete_media_on_removal": bool(svc.get("delete_media_on_removal", False)),
        "delete_original_on_upload": bool(svc.get("delete_original_on_upload", False)),
    }


@router.patch("")
def patch_settings(body: SettingsPatch, _: User = require_permission("can_edit_settings")):
    if "PIN_PEPPER" in body.updates:
        raise HTTPException(
            status_code=400,
            detail="PIN_PEPPER must be set via PATCH /api/v1/settings/pin-pepper, "
            "not the generic settings endpoint — changing it requires re-hashing "
            "the owner PIN and invalidating sub-account PINs.",
        )
    disallowed = sorted(set(body.updates) - _USER_WRITABLE_KEYS)
    if disallowed:
        raise HTTPException(
            status_code=403,
            detail=f"These settings cannot be changed here: {', '.join(disallowed)}.",
        )
    svc = get_settings()
    for key, value in body.updates.items():
        if key in _ALL_PATH_KEYS:
            svc.set_path(key, value or "")
        elif key in _ENV_SECRET_KEYS:
            from backend.service.utils.env_secrets import set_env_secret
            set_env_secret(key, value or "")
        else:
            svc.set_flag(key, value)
    return {"updated": list(body.updates.keys())}


class PinPepperBody(BaseModel):
    pepper: str
    owner_pin: str | None = None


@router.get("/pin-pepper/status")
def get_pin_pepper_status(_: User = require_permission("is_owner")):
    """Whether a pepper is currently configured. Never returns the pepper value itself."""
    from backend.service.utils.env_secrets import get_env_secret
    return {"enabled": bool(get_env_secret("PIN_PEPPER"))}


@router.get("/thegamesdb-api-key/status")
def get_thegamesdb_api_key_status(_: User = require_permission("is_owner")):
    """Whether a TheGamesDB API key is currently configured. Never returns the key value itself."""
    from backend.service.utils.env_secrets import get_env_secret
    return {"enabled": bool(get_env_secret("THEGAMESDB_API_KEY"))}


@router.get("/igdb-status")
def get_igdb_status(_: User = require_permission("is_owner")):
    """Whether both IGDB credentials are configured. Never returns their values."""
    from backend.service.utils.env_secrets import get_env_secret
    return {"enabled": bool(get_env_secret("IGDB_CLIENT_ID")) and bool(get_env_secret("IGDB_CLIENT_SECRET"))}


@router.patch("/pin-pepper")
def patch_pin_pepper(
    body: PinPepperBody,
    db: Session = Depends(get_db),
    _: User = require_permission("is_owner"),
):
    """Enable, disable, or rotate the Argon2id PIN pepper.

    Owner-only: this changes how every PIN in the system is hashed. The
    pepper is mixed directly into the hashed secret (see pin_hashing.py),
    so any change automatically makes every existing hash fail to verify —
    that's the desired clean break, but it must be handled deliberately
    here rather than left to surface as silent wrong-PIN lockouts:

    - The owner's own PIN is re-hashed immediately under the new pepper,
      proven via `owner_pin` (the current, still-valid PIN) — otherwise the
      owner who just changed this setting would lock themselves out with
      no recovery path (reset-pin/unlock both explicitly refuse to touch
      the owner account).
    - Every other account's pin_hash is cleared and pin_required is kept
      set, so they fall through to the existing admin reset-pin flow
      instead of silently accumulating failed attempts against a hash
      that can never match again.
    """
    from backend.service.utils.env_secrets import get_env_secret, set_env_secret
    from backend.service.utils.pin_hashing import hash_pin, verify_pin

    current_pepper = get_env_secret("PIN_PEPPER")
    new_pepper = body.pepper or ""

    if new_pepper == current_pepper:
        return {"pepper_enabled": bool(new_pepper), "owner_rehashed": False, "sub_accounts_reset": []}

    owner = db.query(User).filter(User.is_owner.is_(True)).first()
    owner_rehashed = False
    if owner is not None and owner.pin_hash is not None:
        if not body.owner_pin or not verify_pin(body.owner_pin, owner.pin_hash, pepper=current_pepper):
            raise HTTPException(
                status_code=401,
                detail="Current owner PIN required to change the pepper.",
            )
        owner.pin_hash = hash_pin(body.owner_pin, pepper=new_pepper)
        owner_rehashed = True

    affected: list[str] = []
    others = db.query(User).filter(User.is_owner.is_(False), User.pin_hash.isnot(None)).all()
    for user in others:
        user.pin_hash = None
        user.pin_required = True
        user.failed_pin_attempts = 0
        user.is_locked = False
        affected.append(user.name)

    db.commit()
    set_env_secret("PIN_PEPPER", new_pepper)

    return {
        "pepper_enabled": bool(new_pepper),
        "owner_rehashed": owner_rehashed,
        "sub_accounts_reset": affected,
    }


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
            "software_path": svc.get("SOFTWARE_PATH") or None,
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
