"""
DOSBox-X backend for Peach 1UP.

Handles DOS and Windows 3.1 era games using DOSBox-X natively on the Windows
host. A per-launch conf file is written to a temp directory, incorporating the
emulator's bundled dosbox-x.conf with Peach's [autoexec] and SDL overrides
appended. The temp file is cleaned up via atexit when the service exits.
"""

import atexit
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import List, Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
from backend.core.logger import get_logger
from backend.service.utils.launcher import launch_under_job_object
from backend.service.utils.sandbox_process import SandboxProcess
from backend.service.utils.job_objects import WindowsJobObject

logger = get_logger(__name__)

_DOSBOX_ERAS = {Era.DOS, Era.WIN31}
SUPPORTED_ERAS = {e.value for e in _DOSBOX_ERAS}
SUPPORTED_MEDIA = ERA_MEDIA_TYPES[Era.DOS] | ERA_MEDIA_TYPES[Era.WIN31]


def validate_media(media_path: Path) -> None:
    """Validate media file for the DOSBox-X backend.

    Checks that the file exists and has a supported extension for the DOSBox-X
    backend.

    Args:
        media_path: Path to the media file.

    Raises:
        FileNotFoundError: If the media file does not exist.
        ValueError: If the media file extension is not supported.
    """
    if not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")

    if media_path.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(
            f"Unsupported media format '{media_path.suffix}'. "
            f"DOSBox-X backend supports: {', '.join(sorted(SUPPORTED_MEDIA))}"
        )


def _dosbox_cmd_path(path: Path) -> str:
    """Return a path string safe for a DOSBox-X autoexec line.

    Returns the raw absolute Windows path, double-quoted if it contains
    whitespace. Forward slashes are never used — the DOSBox-X autoexec
    tokeniser treats them as DOS switch characters, which truncates the
    imgmount file argument.

    On non-Windows platforms, returns the POSIX path form.
    """
    if sys.platform != "win32":
        return path.as_posix()
    p = str(path)
    return f'"{p}"' if any(c.isspace() for c in p) else p


def _strip_autoexec(conf_text: str) -> str:
    """Remove any existing [autoexec] section from DOSBox-X config text.

    DOSBox-X applies the last [autoexec] section it sees. Peach generates its
    own [autoexec] block, so any pre-existing one in the bundled dosbox-x.conf
    is stripped to avoid duplicate mount commands and conflicting startup
    behaviour. Also normalises lastdrive to z so DOSBox-X has room for mounts.

    Args:
        conf_text: Full text of a DOSBox-X config file.

    Returns:
        Config text with any [autoexec] section removed and lastdrive
        normalised.
    """
    lines = conf_text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        if lines[i].strip().lower() == "[autoexec]":
            end = i + 1
            while end < len(lines):
                stripped = lines[end].strip()
                if (
                    stripped.startswith("[")
                    and stripped.endswith("]")
                    and stripped.lower() != "[autoexec]"
                ):
                    break
                end += 1
            lines = lines[:i] + lines[end:]
            continue
        i += 1
    result = "".join(lines)
    result = re.sub(r"lastdrive\s*=\s*\w", "lastdrive = z", result, flags=re.IGNORECASE)
    return result


def _validate_game_executable(game_executable: str, expected_drive: str) -> None:
    """Validate game_executable before inserting into a DOSBox-X autoexec section.

    Raises:
        ValueError: If the value is empty, contains unsafe characters, starts
                    with a DOSBox-X meta-character, or references the wrong drive.
    """
    if not game_executable:
        raise ValueError("game_executable must be a non-empty string")

    if "\n" in game_executable or "\r" in game_executable:
        raise ValueError("game_executable must not contain newline characters")

    if "\x00" in game_executable:
        raise ValueError("game_executable must not contain null bytes")

    if "#" in game_executable:
        raise ValueError("game_executable must not contain '#' (DOSBox-X comment character)")

    if game_executable[0] in ("[", "@"):
        raise ValueError(
            f"game_executable must not start with '[' or '@' (DOSBox-X meta-characters); "
            f"got '{game_executable[0]}'"
        )

    # If game_executable specifies an absolute drive path (e.g. C:\GAME.EXE),
    # the drive letter must match the mounted drive to prevent cross-drive references.
    if len(game_executable) >= 2 and game_executable[1] == ":":
        specified = game_executable[0].upper() + ":"
        if specified != expected_drive.upper():
            raise ValueError(
                f"game_executable references drive '{specified}' but media is mounted at '{expected_drive}'"
            )


_EXEC_SUFFIXES = frozenset({".exe", ".bat", ".com"})


def _validate_shell_line(line: str) -> None:
    if "\n" in line or "\r" in line:
        raise ValueError("launch_commands line must not contain newline characters")
    if "\x00" in line:
        raise ValueError("launch_commands line must not contain null bytes")
    if "#" in line:
        raise ValueError("launch_commands line must not contain '#' (DOSBox-X comment character)")


def write_launch_conf(
    media_path: Path,
    era: str,
    executable_path: Path,
    game_executable: str | None = None,
    launch_commands: list[str] | None = None,
) -> Path:
    """Write a per-launch DOSBox-X conf to a temp directory and return its path.

    Reads the emulator's bundled dosbox-x.conf if present, strips its
    [autoexec] section, then appends an [sdl] override block (output=surface
    to suppress TTF mode), a [dos] suppression block, and Peach's [autoexec]
    mount commands. If the bundled conf is absent, a minimal conf is generated
    with just the [sdl] and [dos] blocks.

    The returned path is inside a mkdtemp directory. Callers are responsible
    for registering cleanup; launch() does this via atexit.

    Args:
        media_path: Path to the media file to mount.
        era: Era name (unused; retained for call-site symmetry).
        executable_path: Path to the DOSBox-X executable.

    Returns:
        Path to the written launch.conf file.

    Raises:
        ValueError: If the media suffix is not handled by this backend.
    """
    suffix = media_path.suffix.lower()
    host = _dosbox_cmd_path(media_path)

    if suffix == ".img":
        mount_line = f"imgmount C {host} -t hdd"
        drive_line = "C:"
    elif suffix in {".iso", ".cue"}:
        mount_line = f"imgmount D {host} -t iso -ro"
        drive_line = "D:"
    else:
        raise ValueError(
            f"Unhandled media suffix '{suffix}'. This indicates a programming error."
        )

    emulator_conf = executable_path.parent / "dosbox-x.conf"
    if emulator_conf.exists():
        base = _strip_autoexec(
            emulator_conf.read_text(encoding="utf-8", errors="replace")
        )
    else:
        base = ""

    tmpdir = Path(tempfile.mkdtemp(prefix="peach1up_dosbox_"))
    conf_path = tmpdir / "launch.conf"

    content = base.rstrip("\n")
    if content:
        content += "\n\n"
    # Appending [sdl] after the bundled conf ensures output=surface takes
    # precedence over TTF mode; DOSBox-X uses the last value it reads per key.
    content += "[sdl]\noutput=surface\n\n"
    content += "[dos]\nautomount=false\nmountwarning=false\n\n"
    autoexec = f"[autoexec]\n{mount_line}\n{drive_line}\n"
    if launch_commands:
        for line in launch_commands:
            if any(line.rstrip().lower().endswith(ext) for ext in _EXEC_SUFFIXES):
                _validate_game_executable(line, drive_line)
            else:
                _validate_shell_line(line)
            autoexec += f"{line}\n"
    elif game_executable:
        _validate_game_executable(game_executable, drive_line)
        autoexec += f"{game_executable}\n"
    content += autoexec

    try:
        conf_path.write_text(content, encoding="utf-8")
    except Exception:
        shutil.rmtree(str(tmpdir), ignore_errors=True)
        raise

    return conf_path


def _cleanup_temp_conf(tmpdir: Path) -> None:
    try:
        shutil.rmtree(str(tmpdir), ignore_errors=False)
    except Exception as exc:
        logger.warning("Failed to remove DOSBox temp conf %s: %s", tmpdir, exc)


def build_args(media_path: Path, era: str, enable_networking: bool = False) -> List[str]:
    """Build DOSBox-X command-line arguments for the given media and era.

    Mount commands, sound settings, and SDL/CPU overrides are handled by the
    generated conf file. This function returns only the networking guard, which
    is a security default that must be set explicitly at launch time.

    Args:
        media_path: Path to the media file (validated here for early failure).
        era: Era name (``'dos'`` or ``'win31'``).
        enable_networking: When ``False`` (default), the NE2000 adapter is
            disabled via ``-set ne2000=false``. When ``True``, the adapter
            config is left at the emulator default.

    Returns:
        List of command-line arguments, excluding the executable path and
        the ``-conf`` flag (added by ``launch()``).

    Raises:
        ValueError: If the era is unsupported.
        ValueError: If the media suffix is unsupported.
    """
    if era not in SUPPORTED_ERAS:
        raise ValueError(
            f"Era '{era}' not supported by DOSBox-X backend. "
            f"Supported: {', '.join(sorted(SUPPORTED_ERAS))}"
        )

    suffix = media_path.suffix.lower()
    if suffix not in SUPPORTED_MEDIA:
        raise ValueError(
            f"Media suffix '{suffix}' not supported by DOSBox-X backend. "
            f"Supported: {', '.join(sorted(SUPPORTED_MEDIA))}"
        )

    # Disable NE2000 adapter unless the profile explicitly enables networking.
    return [] if enable_networking else ["-set", "ne2000=false"]


def launch(
    media_path: Path,
    era: str,
    executable_path: str,
    enable_networking: bool = False,
    game_executable: str | None = None,
    launch_commands: list[str] | None = None,
) -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch DOSBox-X with the given media file under Job Object isolation.

    Writes a per-launch conf to a user-private temp directory, passes it to
    DOSBox-X via -conf, and registers an atexit handler to clean up the temp
    directory when the service exits.

    Args:
        media_path: Path to the media file to mount.
        era: Era name (``'dos'`` or ``'win31'``).
        executable_path: Full path to the DOSBox-X executable.
        enable_networking: When ``False`` (default), the NE2000 adapter is
            disabled. Set to ``True`` only for software that requires a
            network connection.

    Returns:
        Tuple of ``(process, job_object)``. The caller is responsible for
        cleanup via ``job_object.terminate_all()``.

    Raises:
        FileNotFoundError: If ``executable_path`` or ``media_path`` does not exist.
        ValueError: If the era or media extension is unsupported.
        RuntimeError: If Job Object creation or process launch fails.
    """
    if not os.path.exists(executable_path):
        raise FileNotFoundError(f"DOSBox-X executable not found: {executable_path}")

    validate_media(media_path)

    conf_path = write_launch_conf(media_path, era, Path(executable_path), game_executable=game_executable, launch_commands=launch_commands)
    conf_tmpdir = conf_path.parent
    atexit.register(shutil.rmtree, str(conf_tmpdir), True)

    args = ["-conf", str(conf_path)] + build_args(media_path, era, enable_networking=enable_networking)
    job_name = f"peach1up_dosbox_{era}_{media_path.stem}"

    result = launch_under_job_object(
        executable_path=executable_path,
        args=args,
        media_paths=[str(media_path)],
        era=era,
        job_name=job_name,
        slug="dosbox-x",
    )

    proc = result[0] if isinstance(result, tuple) else result

    def _deferred_cleanup() -> None:
        while proc is not None and proc.poll() is None:
            time.sleep(2)
        _cleanup_temp_conf(conf_tmpdir)

    threading.Thread(target=_deferred_cleanup, daemon=True, name="dosbox_conf_cleanup").start()

    return result
