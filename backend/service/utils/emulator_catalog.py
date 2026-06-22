import glob as _glob
import logging
import os
import tomllib
from pathlib import Path
from typing import Dict, Any

from backend.core.settings import get_base_path
from backend.service.utils import settings as _settings
from backend.service.utils.eras_config import get_eras as _get_eras

_logger = logging.getLogger(__name__)

_EMULATORS_DIR = get_base_path() / "config" / "emulators"
_BASE_DIR = get_base_path() / "emulators"
_PROFILES_PATH = get_base_path() / "library" / "system" / "templates" / "86box" / "86box-profiles.toml"
_PROFILES_DIR = get_base_path() / "library" / "system" / "templates" / "86box"

_catalog_cache: dict | None = None


def _load_raw_catalog() -> dict:
    global _catalog_cache
    if _catalog_cache is None:
        emulators = []
        bios_requirements = []
        for path in sorted(_EMULATORS_DIR.glob("*.toml")):
            entry = tomllib.loads(path.read_text(encoding="utf-8"))
            emulators.append(entry)
            for dep in entry.get("dependencies", []):
                bios_path = dep.get("bios_path", "")
                if not bios_path:
                    continue
                bios_requirements.append({
                    "slug": dep["name"],
                    "name": dep.get("display_name", dep["name"]),
                    "platform": dep.get("platform", ""),
                    "bios_path": bios_path,
                    "guidance_text": dep.get("guidance_text", ""),
                    "guidance_url": dep.get("guidance_url", ""),
                    "required": dep.get("required", True),
                    "required_files": dep.get("required_files"),
                    "required_glob": dep.get("required_glob"),
                    "required_glob_excludes": dep.get("required_glob_excludes"),
                })
        _catalog_cache = {
            "emulators": emulators,
            "bios_requirements": bios_requirements,
        }
    return _catalog_cache



def _get_eras_config() -> Dict[str, Any]:
    """Return the parsed eras.yaml config — delegates to eras_config.get_eras()."""
    return _get_eras()


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

    Reads from library/system/templates/86box/86box-profiles.toml if present;
    falls back to reading individual files from library/system/templates/86box/
    for development use.

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
            "Ensure library/system/templates/86box/ exists and contains .toml profile files."
        )
    for profile in profiles:
        if profile.get("slug") == slug:
            return profile
    raise ValueError(
        f"Unknown 86Box hardware profile: {slug!r}. "
        "Available profiles are defined in library/system/templates/86box/."
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

        if known_path_env and known_path_suffix and binary:
            env_val = os.environ.get(known_path_env, "")
            if env_val:
                candidate = Path(env_val) / Path(known_path_suffix).parent / binary
                if candidate.exists():
                    return candidate

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

    if slug == "xemu":
        # xemu needs a fully-populated config, not just an empty sentinel file —
        # touching xemu.toml would produce invalid TOML and break xemu startup.
        toml_path = exe_dir / "xemu.toml"
        configured = False
        if toml_path.exists():
            try:
                _cfg = tomllib.loads(toml_path.read_text(encoding="utf-8"))
                _files = _cfg.get("sys", {}).get("files", {})
                if _files.get("bootrom_path") and _files.get("flashrom_path") and _files.get("hdd_path"):
                    configured = True
            except Exception:
                pass
        if not configured:
            _logger.warning(
                "xemu global config at %s is missing or incomplete. "
                "bootrom_path, flashrom_path, and hdd_path must be set before launching Xbox titles.",
                toml_path,
            )
    else:
        ensure_portable_mode(slug, path)
        if slug == "pcsx2":
            (exe_dir / "memcards").mkdir(exist_ok=True)


def detect_and_sync_all() -> None:
    for entry in load_catalog():
        slug = entry["slug"]
        if entry.get("install_type") == "rom_pack":
            continue
        if get_install_path(slug) is not None:
            try:
                configure_emulator(slug)
            except Exception as exc:
                _logger.warning("detect_and_sync_all: configure_emulator failed for %s: %s", slug, exc)


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
    override = _settings.get(f"sandbox_{slug}_skip_memory_limit", None)
    if override is not None:
        return bool(override)
    try:
        return bool(get_emulator(slug).get("skip_memory_limit", False))
    except ValueError:
        return False


def get_skip_cpu_limit(slug: str) -> bool:
    override = _settings.get(f"sandbox_{slug}_skip_cpu_limit", None)
    if override is not None:
        return bool(override)
    try:
        return bool(get_emulator(slug).get("skip_cpu_limit", False))
    except ValueError:
        return False


def get_container_enabled(slug: str) -> bool:
    try:
        toml_val = get_emulator(slug).get("container_enabled", False)
    except ValueError:
        return False
    if toml_val is False:
        return False
    override = _settings.get(f"sandbox_{slug}_container_enabled", None)
    if override is not None:
        return bool(override)
    return bool(toml_val)


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
    from backend.service.utils.platform.windows.app_container import (
        get_container_config as _build_config,
    )
    return _build_config(slug, exe_path)


def load_bios_requirements() -> list[dict]:
    return _load_raw_catalog().get("bios_requirements", [])


def _missing_required_files(
    dir_path: Path,
    required_files: list[str] | None,
    required_glob: str | None,
    required_glob_excludes: list[str] | None,
) -> list[str]:
    """Return descriptions of required files absent from dir_path.

    Falls back to non-empty-directory semantics when neither required_files
    nor required_glob is specified — most BIOS dependencies (DuckStation,
    PCSX2) auto-detect flexibly-named files by hash and have no fixed
    filename to check.
    """
    if not required_files and not required_glob:
        try:
            return [] if any(dir_path.iterdir()) else ["<directory is empty>"]
        except PermissionError:
            return ["<directory not readable>"]

    missing = [name for name in required_files or [] if not (dir_path / name).exists()]
    if required_glob:
        excludes = {name.lower() for name in (required_glob_excludes or [])}
        matches = [f for f in dir_path.glob(required_glob) if f.name.lower() not in excludes]
        if not matches:
            missing.append(f"a file matching '{required_glob}' (excluding {sorted(excludes)})")
    return missing


def check_bios_presence(
    bios_path: str,
    required_files: list[str] | None = None,
    required_glob: str | None = None,
    required_glob_excludes: list[str] | None = None,
) -> bool:
    path = (get_base_path() / bios_path).resolve()
    try:
        if not path.exists() or not path.is_dir():
            return False
        return not _missing_required_files(path, required_files, required_glob, required_glob_excludes)
    except PermissionError:
        return False


def ensure_portable_mode(slug: str, exe_path: "Path") -> None:
    """Create the portable sentinel file declared in the emulator descriptor.

    Reads portable_sentinel from the descriptor for slug. If the value is
    non-empty, touches the sentinel file next to the binary when it does not
    already exist. Idempotent — safe to call on every configure pass.
    """
    try:
        entry = get_emulator(slug)
    except ValueError:
        return
    sentinel = entry.get("portable_sentinel", "")
    if not sentinel:
        return
    sentinel_path = exe_path.parent / sentinel
    if not sentinel_path.exists():
        sentinel_path.touch()


def validate_bios_from_descriptor(slug: str) -> None:
    """Validate that BIOS directories declared in the emulator descriptor exist.

    Reads each [[dependencies]] entry that has a bios_path field, resolves it
    relative to the project root, and raises FileNotFoundError if the directory
    is absent or empty.

    Security: bios_path values come from project-internal TOMLs. Each resolved
    path is confirmed to remain within the project root.

    Raises:
        FileNotFoundError: If a required bios_path directory is missing or empty.
        ValueError: If a bios_path resolves outside the project root (config error).
    """
    try:
        entry = get_emulator(slug)
    except ValueError:
        return
    base = get_base_path().resolve()
    for dep in entry.get("dependencies", []):
        bios_path_str = dep.get("bios_path", "")
        if not bios_path_str:
            continue
        resolved = (base / bios_path_str).resolve()
        if not resolved.is_relative_to(base):
            raise ValueError(
                f"bios_path '{bios_path_str}' for slug '{slug}' resolves outside "
                "the project root — this indicates a corrupted descriptor."
            )
        display_name = dep.get("display_name", "BIOS")
        required = dep.get("required", True)
        if not resolved.exists() or not resolved.is_dir():
            if required:
                raise FileNotFoundError(
                    f"{display_name} directory not found: {resolved}. "
                    "Place your BIOS files there before launching."
                )
            continue
        missing = _missing_required_files(
            resolved,
            dep.get("required_files"),
            dep.get("required_glob"),
            dep.get("required_glob_excludes"),
        )
        if missing and required:
            raise FileNotFoundError(
                f"{display_name} is missing required file(s) in {resolved}: {', '.join(missing)}. "
                "Place your BIOS files there before launching."
            )
