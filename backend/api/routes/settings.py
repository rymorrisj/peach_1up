from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.settings import get_settings
from backend.schemas.settings import SettingsPatch, SettingsRead

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

_KNOWN_BINARY_KEYS = {"DOSBOX_PATH", "BOX86_PATH", "VIRTUALBOX_PATH"}
_ALL_PATH_KEYS = {"DOSBOX_PATH", "BOX86_PATH", "VIRTUALBOX_PATH", "ROM_PATH", "IMAGES_PATH", "PROFILES_PATH"}


class PathValidationResult(BaseModel):
    key: str
    path: str
    exists: bool
    executable: bool


class ValidateResponse(BaseModel):
    results: list[PathValidationResult]


@router.get("", response_model=dict)
def get_all_settings():
    svc = get_settings()
    state = svc._require_init()
    return {k: v for k, v in state.items() if not k.startswith("_")}


@router.patch("")
def patch_settings(body: SettingsPatch):
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
