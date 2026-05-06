from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.settings import get_settings

router = APIRouter(prefix="/api/v1/emulators", tags=["emulators"])

_EMULATOR_REGISTRY = {
    "dosbox-x":   {"name": "DOSBox-X",   "settings_key": "DOSBOX_PATH",      "eras": ["dos", "win31"]},
    "86box":      {"name": "86Box",       "settings_key": "BOX86_PATH",        "eras": ["win95", "win98"]},
    "virtualbox": {"name": "VirtualBox",  "settings_key": "VIRTUALBOX_PATH",   "eras": ["win95", "win98", "winxp"]},
    "duckstation":{"name": "DuckStation", "settings_key": "DUCKSTATION_PATH",  "eras": ["ps1"]},
    "pcsx2":      {"name": "PCSX2",       "settings_key": "PCSX2_PATH",        "eras": ["ps2"]},
    "xemu":       {"name": "xemu",        "settings_key": "XEMU_PATH",         "eras": ["xbox"]},
    "mesen":      {"name": "Mesen",       "settings_key": "MESEN_PATH",        "eras": ["nes"]},
    "project64":  {"name": "Project64",   "settings_key": "PROJECT64_PATH",    "eras": ["n64"]},
}


class EmulatorDetail(BaseModel):
    slug: str
    name: str
    eras: list[str]
    binary_path: str
    available: bool


def _resolve(slug: str) -> EmulatorDetail:
    info = _EMULATOR_REGISTRY[slug]
    svc = get_settings()
    path = svc.get(info["settings_key"], "") or ""
    available = bool(path) and Path(path).is_file()
    return EmulatorDetail(slug=slug, name=info["name"], eras=info["eras"], binary_path=path, available=available)


@router.get("", response_model=list[EmulatorDetail])
def list_emulators():
    return [_resolve(slug) for slug in _EMULATOR_REGISTRY]


@router.get("/{slug}", response_model=EmulatorDetail)
def get_emulator(slug: str):
    if slug not in _EMULATOR_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Emulator '{slug}' not found.")
    return _resolve(slug)


@router.post("/{slug}/check", response_model=EmulatorDetail)
def check_emulator(slug: str):
    if slug not in _EMULATOR_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Emulator '{slug}' not found.")
    return _resolve(slug)
