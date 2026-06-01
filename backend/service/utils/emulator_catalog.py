import glob as _glob
import logging
import os
import tomllib
from pathlib import Path
from typing import Dict, Any

import yaml as _yaml

from backend.core.settings import get_base_path

_logger = logging.getLogger(__name__)

_EMULATORS_DIR = get_base_path() / "config" / "emulators"
_BIOS_REQUIREMENTS_PATH = get_base_path() / "config" / "bios_requirements.toml"
_BASE_DIR = get_base_path() / "emulators"
_PROFILES_PATH = get_base_path() / "config" / "86box-profiles.toml"
_PROFILES_DIR = get_base_path() / "config" / "86box-profiles"

_catalog_cache: dict | None = None
_ERAS_CONFIG_CACHE: Dict[str, Any] | None = None


def _load_raw_catalog() -> dict:
    global _catalog_cache
    if _catalog_cache is None:
        emulators = []
        for path in sorted(_EMULATORS_DIR.glob("*.toml")):
            emulators.append(tomllib.loads(path.read_text(encoding="utf-8")))
        bios_data = tomllib.loads(_BIOS_REQUIREMENTS_PATH.read_text(encoding="utf-8"))
        _catalog_cache = {
            "emulators": emulators,
            "bios_requirements": bios_data.get("bios_requirements", []),
        }
    return _catalog_cache


def reset_catalog_cache() -> None:
    global _catalog_cache
    _catalog_cache = None


def _get_eras_config() -> Dict[str, Any]:
    global _ERAS_CONFIG_CACHE
    if _ERAS_CONFIG_CACHE is None:
        config_path = get_base_path() / "config" / "eras.yaml"
        with config_path.open("r", encoding="utf-8") as f:
            _ERAS_CONFIG_CACHE = _yaml.safe_load(f) or {}
    return _ERAS_CONFIG_CACHE


def get_settings_key(slug: str) -> str:
    """Return the settings key for a given emulator slug.

    Reads the ``settings_key`` field from emulators.toml if present;
    otherwise derives it as ``slug.upper().replace("-", "") + "_PATH"``.
    Falls back to the derived key for slugs not present in the catalog
    (e.g. emulators managed outside the TOML registry).
    """
    try:
        entry = get_emulator(slug)
        if "settings_key" in entry:
            return entry["settings_key"]
    except ValueError:
        pass
    return slug.upper().replace("-", "") + "_PATH"


def get_backend_for_era(era: str) -> str:
    """Return the backend slug for a given era from eras.yaml.

    Reads the ``backend`` field from the era's config block.

    Raises:
        ValueError: If the era is not in eras.yaml or has no ``backend`` key.
    """
    config = _get_eras_config()
    era_config = config.get(era)
    if not era_config or not isinstance(era_config, dict):
        raise ValueError(f"Era '{era}' not found in eras.yaml")
    backend = era_config.get("backend")
    if not backend:
        raise ValueError(f"Era '{era}' has no 'backend' key in eras.yaml")
    return str(backend)


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
            "Ensure config/86box-profiles/ exists and contains .toml profile files."
        )
    for profile in profiles:
        if profile.get("slug") == slug:
            return profile
    raise ValueError(
        f"Unknown 86Box hardware profile: {slug!r}. "
        "Available profiles are defined in config/86box-profiles/."
    )


def load_catalog() -> list[dict]:
    return _load_raw_catalog().get("emulators", [])


def get_emulator(slug: str) -> dict:
    for entry in load_catalog():
        if entry["slug"] == slug:
            return entry
    raise ValueError(f"Unknown emulator slug: {slug!r}")


def get_install_path(slug: str) -> Path | None:
    entry = get_emulator(slug)
    install_type = entry.get("install_type", "zip")
    install_scope = entry.get("install_scope", "portable")
    binary = entry.get("binary", "")

    # Check settings.yaml user override first — user path always wins.
    if install_type != "rom_pack":
        settings_key = get_settings_key(slug)
        try:
            from backend.service.utils import settings as _settings_mod
            val = _settings_mod.get(settings_key, "")
            if val:
                p = Path(str(val))
                if p.exists():
                    return p
        except Exception:
            pass

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

    elif slug == "flycast":
        cfg_path = exe_dir / "emu.cfg"
        if not cfg_path.exists():
            cfg_path.touch()

    elif slug == "xemu":
        toml_path = exe_dir / "xemu.toml"
        configured = False
        if toml_path.exists():
            try:
                _cfg = tomllib.loads(toml_path.read_text(encoding="utf-8"))
                _sys = _cfg.get("system", {})
                _sto = _cfg.get("storage", {})
                if _sys.get("flash_path") and _sys.get("bios_path") and _sto.get("hdd_path"):
                    configured = True
            except Exception:
                pass
        if not configured:
            _logger.warning(
                "xemu global config at %s is missing or incomplete. "
                "flash_path, bios_path, and hdd_path must be set before launching Xbox titles.",
                toml_path,
            )


def detect_and_sync_all() -> None:
    from backend.service.utils import settings as _settings_mod
    for entry in load_catalog():
        slug = entry["slug"]
        if entry.get("install_type") == "rom_pack":
            continue
        settings_key = get_settings_key(slug)
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


def get_emulator_era(slug: str) -> str:
    """Return the era key for a given emulator slug from emulators.toml.

    The era is used to look up CPU and memory limits in eras.yaml.  For
    emulators that span multiple eras (e.g. 86box), the most-demanding era
    is recorded so AppContainer limits are never under-resourced.

    Raises:
        ValueError: If the slug is not found or has no ``era`` field.
    """
    entry = get_emulator(slug)
    era = entry.get("era")
    if not era:
        raise ValueError(f"Emulator '{slug}' has no 'era' field in config/emulators/{slug}.toml")
    return str(era)


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
    return _load_raw_catalog().get("bios_requirements", [])


def check_bios_presence(bios_path: str) -> bool:
    path = (get_base_path() / bios_path).resolve()
    try:
        return path.exists() and path.is_dir() and any(path.iterdir())
    except PermissionError:
        return False
