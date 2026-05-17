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
    install_scope = entry.get("install_scope", "portable")
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

    if install_scope == "system":
        known_path_env = entry.get("known_path_env", "")
        known_path_suffix = entry.get("known_path_suffix", "")
        if known_path_env and known_path_suffix:
            env_val = os.environ.get(known_path_env, "")
            if env_val:
                candidate = Path(env_val) / known_path_suffix
                if candidate.exists():
                    return candidate

        known_path = entry.get("known_path", "")
        if known_path:
            p = Path(known_path)
            if p.exists():
                return p

        if known_path_env and known_path_suffix:
            env_val = os.environ.get(known_path_env, "")
            if env_val:
                parent = Path(env_val) / Path(known_path_suffix).parent
                matches = _glob.glob(str(parent / "duckstation-qt*.exe"))
                if matches:
                    return Path(matches[0])

        return None

    if windows_binary:
        path = _BASE_DIR / slug / windows_binary
        if path.exists():
            return path

    return None


def is_installed(slug: str) -> bool:
    entry = get_emulator(slug)
    install_type = entry.get("install_type", "zip")
    path = get_install_path(slug)
    if path is None:
        return False
    if install_type == "rom_pack":
        try:
            return path.is_dir() and any(path.iterdir())
        except PermissionError:
            return False
    return path.is_file()


def installer_present(slug: str) -> bool:
    entry = get_emulator(slug)
    install_scope = entry.get("install_scope", "portable")
    install_type = entry.get("install_type", "zip")

    if install_scope == "system" and install_type == "installer" and is_installed(slug):
        return True

    installer_glob = entry.get("windows_installer_glob", "")
    if installer_glob:
        slug_dir = _BASE_DIR / slug
        return bool(_glob.glob(str(slug_dir / installer_glob)))

    return False


def configure_emulator(slug: str) -> None:
    path = get_install_path(slug)
    if path is None:
        return

    exe_dir = path.parent

    if slug == "pcsx2":
        (exe_dir / "portable.txt").touch()
        (exe_dir / "memcards").mkdir(exist_ok=True)

    elif slug == "duckstation":
        (exe_dir / "portable.txt").touch()
        (exe_dir / "saves").mkdir(exist_ok=True)

    elif slug == "xemu":
        toml_path = exe_dir / "xemu.toml"
        if not toml_path.exists():
            toml_path.write_text(
                "[general]\n"
                "show_welcome = false\n"
                "[system]\n"
                'flash_path = "emulators/xemu/mcpx_1.0.bin"\n'
                'bios_path = "emulators/xemu/Complex_4627v1.03.bin"\n'
                "[storage]\n"
                'hdd_path = "emulators/xemu/xbox_hdd.qcow2"\n',
                encoding="utf-8",
            )

    elif slug == "project64":
        cfg_path = exe_dir / "Project64.cfg"
        if not cfg_path.exists():
            saves_dir = _PROJECT_ROOT / "library" / "saves" / "project64"
            screenshots_dir = saves_dir / "screenshots"
            cfg_path.write_text(
                "[Directory]\n"
                f"Saves={saves_dir}/\n"
                f"Screenshots={screenshots_dir}/\n",
                encoding="utf-8",
            )


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
            try:
                configure_emulator(slug)
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
