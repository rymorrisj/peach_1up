import os
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CATALOG_PATH = _PROJECT_ROOT / "config" / "emulators.yaml"
_BASE_DIR = _PROJECT_ROOT / "emulators"


def load_catalog() -> list[dict]:
    with _CATALOG_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("emulators", [])


def get_emulator(slug: str) -> dict:
    for entry in load_catalog():
        if entry["slug"] == slug:
            return entry
    raise ValueError(f"Unknown emulator slug: {slug!r}")


def get_install_path(slug: str) -> Path:
    entry = get_emulator(slug)
    return _BASE_DIR / slug / entry["binary_name"]


def is_installed(slug: str) -> bool:
    path = get_install_path(slug)
    return path.exists() and path.is_file() and os.access(str(path), os.X_OK)


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


def get_all_statuses() -> list[dict]:
    result = []
    for entry in load_catalog():
        slug = entry["slug"]
        installed = is_installed(slug)
        install_path = get_install_path(slug)
        item: dict = {
            "slug": slug,
            "name": entry["name"],
            "version": entry["version"],
            "description": entry["description"],
            "license": entry["license"],
            "required": entry.get("required", False),
            "is_installed": installed,
            "install_path": str(install_path) if installed else None,
            "is_placeholder": entry.get("linux_url", "").startswith("PLACEHOLDER"),
            "supported_formats": entry.get("supported_formats", []),
        }
        if "install_note" in entry:
            item["install_note"] = entry["install_note"]
        result.append(item)
    return result
