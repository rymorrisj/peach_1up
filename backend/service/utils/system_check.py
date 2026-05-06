from __future__ import annotations

import ctypes
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from backend.service.utils.settings import get_binary_path


def is_elevated() -> bool:
    """Return True if the current process has administrator privileges."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


@dataclass
class MissingBinary:
    name: str
    env_var: str
    download_url: str


def check_missing_binaries() -> list[MissingBinary]:
    """
    Check for missing emulator binaries defined in the environment.

    Returns a list of MissingBinary entries for every binary whose env var is
    unset or whose path does not exist on disk. Empty list means all present.
    """
    missing: list[MissingBinary] = []

    dosbox_path = get_binary_path("dosbox")
    if not dosbox_path or not Path(dosbox_path).exists():
        missing.append(
            MissingBinary("DOSBox-X", "DOSBOX_PATH", "https://dosbox-x.com")
        )

    box86_path = get_binary_path("box86")
    if not box86_path or not Path(box86_path).exists():
        missing.append(
            MissingBinary("86Box", "BOX86_PATH", "https://86box.net")
        )

    return missing


def compute_setup_status(platforms_path: Path) -> dict[str, str]:
    """Return a status dict for all first-run setup components.

    Each value is ``'ok'`` or ``'missing'``. Callable from FastAPI route
    handlers and the first-run wizard without any Textual context.

    Args:
        platforms_path: Path to ``platforms.yaml``.

    Returns:
        Dict with keys ``'dosbox'``, ``'virtualbox'``, ``'box86'``,
        ``'roms'``, and ``'platforms'``.
    """
    from backend.service.utils import settings as _settings
    from backend.service.utils.platform import load_all

    result: dict[str, str] = {}
    for key in ("dosbox", "virtualbox", "box86"):
        p = get_binary_path(key)
        result[key] = "ok" if (p and Path(p).is_file()) else "missing"

    rom = _settings.get_env_var("ROM_PATH")
    result["roms"] = "ok" if (rom and Path(rom).is_dir()) else "missing"

    try:
        result["platforms"] = "ok" if load_all(platforms_path) else "missing"
    except Exception:
        result["platforms"] = "missing"

    return result


def clone_rom_pack(rom_dir: Path) -> tuple[bool, str]:
    """Clone the 86Box ROM pack from GitHub into ``rom_dir``.

    Runs synchronously — callers that need non-blocking behaviour must run
    this in a thread. No user input reaches the subprocess; all arguments
    are hardcoded constants.

    Args:
        rom_dir: Destination directory for the ROM pack.

    Returns:
        ``(success, message)`` — ``True`` and a success string on success;
        ``False`` and a descriptive error string on failure.
    """
    rom_url = "https://github.com/86Box/roms"
    git_bin = shutil.which("git")

    if not git_bin:
        return False, "git is not installed or not on PATH."

    if rom_dir.exists():
        return False, f"ROM directory already exists: {rom_dir}"

    try:
        result = subprocess.run(
            [git_bin, "clone", rom_url, str(rom_dir)],
            capture_output=True,
            timeout=300,
        )
        if result.returncode == 0:
            return True, f"ROM pack cloned to {rom_dir}."
        err = result.stderr.decode(errors="replace").strip()[:120]
        return False, f"Clone failed: {err}"
    except Exception as exc:
        return False, f"Clone error: {exc}"
