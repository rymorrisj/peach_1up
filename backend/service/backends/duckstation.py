"""DuckStation backend for Peach 1UP.

Handles PlayStation 1 launches. Validates the binary path, media file, and
PS1 BIOS directory, then launches DuckStation under Job Objects.

Network isolation: PS1 hardware has no network capability. DuckStation
exposes no network emulation. No enable_networking handling is needed for
this backend or any other console backend (PCSX2, xemu, Mesen, Project64).

BIOS files must be dumped from PlayStation hardware the user owns. Peach 1UP
does not provide, link to, or assist with acquiring BIOS files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from backend.service.utils.job_objects import launch_under_job_object, SandboxProcess, WindowsJobObject
from backend.service.utils.settings import get_env_var


SUPPORTED_MEDIA = {'.iso', '.bin', '.cue', '.chd'}
SUPPORTED_ERAS = {'ps1'}


def validate_media(media_path: Path) -> None:
    """Validate that the media file exists and has a supported extension.

    Args:
        media_path: Path to the media file.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is not supported.
    """
    if not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")
    if media_path.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(
            f"Unsupported media format '{media_path.suffix}'. "
            f"DuckStation supports: {', '.join(sorted(SUPPORTED_MEDIA))}"
        )


def validate_bios_path(bios_path: Path) -> None:
    """Validate that the PS1 BIOS directory exists.

    Args:
        bios_path: Path to the directory containing PS1 BIOS files.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the path is not a directory.
    """
    if not bios_path.exists():
        raise FileNotFoundError(
            f"PS1 BIOS path not found: {bios_path}. "
            "PS1 BIOS files must be dumped from PlayStation hardware you own. "
            "Configure PS1_BIOS_PATH in config/settings.yaml to the directory "
            "containing your dumped BIOS files, then configure DuckStation to "
            "use the same directory."
        )
    if not bios_path.is_dir():
        raise ValueError(
            f"PS1 BIOS path is not a directory: {bios_path}. "
            "PS1_BIOS_PATH must point to a directory containing your dumped BIOS files."
        )


def build_args(media_path: Path) -> list[str]:
    """Build DuckStation command line arguments for the given media file.

    Args:
        media_path: Path to the PS1 disc image.

    Returns:
        List of command line arguments (excludes the executable path).
    """
    return ["-nogui", str(media_path)]


def launch(media_path: Path, era: str, executable_path: str) -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch DuckStation with the given PS1 media under Job Object isolation.

    Args:
        media_path: Path to the PS1 disc image to mount.
        era: Era string — must be 'ps1'.
        executable_path: Full path to the DuckStation executable.

    Returns:
        Tuple of (subprocess.Popen process, WindowsJobObject instance).
        Caller is responsible for cleanup via job_object.terminate_all().

    Raises:
        FileNotFoundError: If the executable, media file, or BIOS path is missing.
        ValueError: If the media extension is unsupported.
        RuntimeError: If PS1_BIOS_PATH is not configured or process launch fails.
    """
    if not Path(executable_path).exists():
        raise FileNotFoundError(f"DuckStation executable not found: {executable_path}")

    validate_media(media_path)

    bios_path_str = get_env_var("PS1_BIOS_PATH")
    if not bios_path_str:
        raise RuntimeError(
            "PS1_BIOS_PATH is not configured. "
            "Set it in config/settings.yaml to the directory containing your PS1 BIOS files. "
            "PS1 BIOS files must be dumped from PlayStation hardware you own."
        )
    validate_bios_path(Path(bios_path_str))

    args = build_args(media_path)
    job_name = f"peach1up_duckstation_{media_path.stem}"

    return launch_under_job_object(
        executable_path=executable_path,
        args=args,
        media_paths=[str(media_path)],
        era=era,
        job_name=job_name,
    )
