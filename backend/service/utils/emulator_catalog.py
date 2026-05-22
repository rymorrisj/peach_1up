import glob as _glob
import os
import tomllib
from pathlib import Path

from backend.core.settings import get_base_path

_CATALOG_PATH = get_base_path() / "config" / "emulators.toml"
_BASE_DIR = get_base_path() / "emulators"
_PROFILES_PATH = get_base_path() / "config" / "86box-profiles.toml"
_PROFILES_DIR = get_base_path() / "config" / "86box-profiles"

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


def get_86box_profile(slug: str) -> dict:
    """Return the 86Box hardware profile dict for *slug*.

    Reads from config/86box-profiles.toml if present; falls back to reading
    individual files from config/86box-profiles/ for development use.

    Raises:
        ValueError: If the slug is not found in any profile file.
        FileNotFoundError: If neither the merged TOML nor the source directory exists.
    """
    if _PROFILES_PATH.exists():
        data = tomllib.loads(_PROFILES_PATH.read_text(encoding="utf-8"))
        profiles = data.get("profiles", [])
    elif _PROFILES_DIR.is_dir():
        profiles = [
            tomllib.loads(f.read_text(encoding="utf-8"))
            for f in sorted(_PROFILES_DIR.glob("*.toml"))
        ]
    else:
        raise FileNotFoundError(
            f"86Box profiles not found — expected {_PROFILES_PATH} or {_PROFILES_DIR}. "
            "Run scripts/merge_emulators.py to generate config/86box-profiles.toml."
        )
    for profile in profiles:
        if profile.get("slug") == slug:
            return profile
    raise ValueError(
        f"Unknown 86Box hardware profile: {slug!r}. "
        "Available profiles are defined in config/86box-profiles/."
    )


def load_catalog() -> list[dict]:
    data = tomllib.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    return data.get("emulators", [])


def get_emulator(slug: str) -> dict:
    for entry in load_catalog():
        if entry["slug"] == slug:
            return entry
    raise ValueError(f"Unknown emulator slug: {slug!r}")


def get_install_path(slug: str) -> Path | None:
    # Check settings.yaml user override first — user path always wins.
    settings_key = _SLUG_TO_SETTINGS_KEY.get(slug)
    if settings_key:
        try:
            from backend.service.utils import settings as _settings_mod
            val = _settings_mod.get(settings_key, "")
            if val:
                p = Path(str(val))
                if p.exists():
                    return p
        except Exception:
            pass

    entry = get_emulator(slug)
    install_type = entry.get("install_type", "zip")
    install_scope = entry.get("install_scope", "portable")
    binary = entry.get("binary", "")

    if install_type == "rom_pack":
        if binary:
            pack_dir = (get_base_path() / binary).resolve()
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

    if binary:
        path = _BASE_DIR / slug / binary
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
            saves_dir = get_base_path() / "library" / "saves" / "project64"
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
        # Never overwrite an existing user override.
        try:
            existing = _settings_mod.get(settings_key, "")
        except Exception:
            existing = ""
        if existing:
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


def get_skip_memory_limit(slug: str) -> bool:
    try:
        return bool(get_emulator(slug).get("skip_memory_limit", False))
    except ValueError:
        return False


def get_skip_cpu_limit(slug: str) -> bool:
    try:
        return bool(get_emulator(slug).get("skip_cpu_limit", False))
    except ValueError:
        return False


def get_container_enabled(slug: str) -> bool:
    try:
        return bool(get_emulator(slug).get("container_enabled", False))
    except ValueError:
        return False


def get_container_config(slug: str, exe_path: str) -> "SandboxConfig | None":
    """Return a SandboxConfig for *slug*, or None if container_enabled is false.

    Calls app_container.get_container_config() internally.  Returns None
    immediately (without importing app_container) when container_enabled is
    false so the common case has zero overhead.

    Raises:
        SandboxError: stage=CONFIG_VALIDATION if any DACL path_key cannot be
            resolved.  Propagated directly from app_container.
    """
    if not get_container_enabled(slug):
        return None
    from backend.service.utils.app_container import (
        get_container_config as _build_config,
    )
    return _build_config(slug, exe_path)


def load_bios_requirements() -> list[dict]:
    data = tomllib.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    return data.get("bios_requirements", [])


def check_bios_presence(bios_path: str) -> bool:
    path = (get_base_path() / bios_path).resolve()
    try:
        return path.exists() and path.is_dir() and any(path.iterdir())
    except PermissionError:
        return False
