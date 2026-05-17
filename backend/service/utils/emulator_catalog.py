import glob as _glob
import os
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CATALOG_PATH = _PROJECT_ROOT / "config" / "emulators.yaml"
_BASE_DIR = Path(os.getcwd()) / "emulators"

_SLUG_TO_SETTINGS_KEY: dict[str, str] = {
    "dosbox-x":    "DOSBOX_PATH",
    "86box":       "BOX86_PATH",
    "virtualbox":  "VIRTUALBOX_PATH",
    "duckstation": "DUCKSTATION_PATH",
    "pcsx2":       "PCSX2_PATH",
    "xemu":        "XEMU_PATH",
    "mesen":       "MESEN_PATH",
    "project64":   "PROJECT64_PATH",
}


def load_catalog() -> list[dict]:
    with _CATALOG_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("emulators", [])


def get_emulator(slug: str) -> dict:
    for entry in load_catalog():
        if entry["slug"] == slug:
            return entry
    raise ValueError(f"Unknown emulator slug: {slug!r}")


def get_install_path(slug: str) -> Path | None:
    entry = get_emulator(slug)
    install_type = entry.get("install_type", "zip")
    windows_binary = entry.get("windows_binary", "")

    if install_type == "rom_pack":
        if windows_binary:
            pack_dir = (_PROJECT_ROOT / windows_binary).resolve()
            try:
                if pack_dir.exists() and pack_dir.is_dir() and any(pack_dir.iterdir()):
                    return pack_dir
            except PermissionError:
                pass
        return None

    if windows_binary:
        # Glob pattern (covers both relative and absolute glob paths like Program Files\Project64*\...)
        if "*" in windows_binary:
            matches = _glob.glob(windows_binary)
            if matches:
                return Path(matches[0])
        # Absolute path (system-installed emulators with known paths)
        elif Path(windows_binary).is_absolute():
            path = Path(windows_binary)
            if path.exists():
                return path
        else:
            # Relative name — portable install under emulators/<slug>/
            path = _BASE_DIR / slug / windows_binary
            if path.exists():
                return path

    # system_paths — common system install locations from catalog
    for sp in entry.get("system_paths", []):
        p = Path(sp)
        if p.exists():
            return p

    return None


def is_installed(slug: str) -> bool:
    entry = get_emulator(slug)
    install_type = entry.get("install_type", "zip")
    path = get_install_path(slug)
    if path is None:
        return False
    if install_type == "rom_pack":
        return path.is_dir()
    return path.is_file() and os.access(str(path), os.X_OK)


def detect_and_sync_all() -> None:
    from backend.service.utils import settings as _settings_mod
    for entry in load_catalog():
        slug = entry["slug"]
        settings_key = _SLUG_TO_SETTINGS_KEY.get(slug)
        if not settings_key:
            continue
        path = get_install_path(slug)
        if path is not None:
            try:
                _settings_mod.set_path(settings_key, str(path))
            except Exception:
                pass


def load_bios_requirements() -> list[dict]:
    with _CATALOG_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("bios_requirements", [])


def check_bios_presence(bios_path: str) -> bool:
    path = (_PROJECT_ROOT / bios_path).resolve()
    try:
        return path.exists() and path.is_dir() and any(path.iterdir())
    except PermissionError:
        return False
