from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path

from utils.settings import get_binary_path


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
