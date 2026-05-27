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
from pathlib import Path
from typing import List, Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.service.utils.emulator_catalog import get_container_enabled
from backend.service.utils.sandbox import BrokerFile
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


def _build_drive_mount_lines(
    drive: object | None,
    use_drive: bool,
    media_path: Path,
) -> tuple[list[str], str | None, str, str]:
    """Return (drive_setup_lines, mount_line, drive_line, media_drive).

    mount_line is None when media_path is a directory on a persistent drive
    (files are already on C:, so no additional mount is needed).
    """
    suffix = media_path.suffix.lower()
    host = _dosbox_cmd_path(media_path)
    has_persistent_drive = drive is not None and use_drive

    drive_setup_lines: list[str] = []

    if has_persistent_drive:
        if not drive.image_path:
            raise ValueError(
                f"Drive id={drive.id!r} has no image_path configured. "
                "Re-add the library item to regenerate the drive record."
            )
        drive_path = Path(drive.image_path)
        lib_media = get_base_path() / "library" / "media"
        if not drive_path.resolve().is_relative_to(lib_media.resolve()):
            raise ValueError(
                f"Drive image path escaped library/media (id={drive.id!r}). "
                "This indicates a data integrity problem."
            )
        drive_cmd_path = _dosbox_cmd_path(drive_path)
        if not drive_path.exists():
            drive_setup_lines.append(f"IMGMAKE {drive_cmd_path} -t hd -size {drive.size_mb}")
        drive_setup_lines.append(f"IMGMOUNT C {drive_cmd_path} -t hdd")

        if media_path.is_dir():
            mount_line = None
            drive_line = "C:"
            media_drive = "C:"
        elif suffix == ".img":
            mount_line = f"imgmount D {host} -t hdd"
            drive_line = "C:"
            media_drive = "D:"
        elif suffix in {".iso", ".cue"}:
            mount_line = f"imgmount D {host} -t iso -ro"
            drive_line = "C:"
            media_drive = "D:"
        elif suffix in {".exe", ".bat"}:
            parent_dir = _dosbox_cmd_path(media_path.parent)
            mount_line = f"MOUNT D {parent_dir} -freesize 1024"
            drive_line = "C:"
            media_drive = "D:"
        else:
            raise ValueError(
                f"Unhandled media suffix '{suffix}'. This indicates a programming error."
            )
    else:
        if media_path.is_dir():
            raise ValueError(
                "Directory media requires a persistent drive. This indicates a misconfiguration."
            )
        elif suffix == ".img":
            mount_line = f"imgmount C {host} -t hdd"
            drive_line = "C:"
            media_drive = "C:"
        elif suffix in {".iso", ".cue"}:
            mount_line = f"imgmount D {host} -t iso -ro"
            drive_line = "D:"
            media_drive = "D:"
        elif suffix in {".exe", ".bat"}:
            parent_dir = _dosbox_cmd_path(media_path.parent)
            mount_line = f"MOUNT D {parent_dir} -freesize 1024"
            drive_line = "D:"
            media_drive = "D:"
        else:
            raise ValueError(
                f"Unhandled media suffix '{suffix}'. This indicates a programming error."
            )

    return drive_setup_lines, mount_line, drive_line, media_drive


def _build_autoexec(
    drive_setup_lines: list[str],
    mount_line: str | None,
    drive_line: str,
    media_drive: str,
    profile_cmds: list[str],
    item_cmds: list[str],
) -> str:
    """Return the full [autoexec] block as a string."""
    merged = profile_cmds + item_cmds
    autoexec = "[autoexec]\n"
    for setup_line in drive_setup_lines:
        autoexec += f"{setup_line}\n"
    if mount_line is not None:
        autoexec += f"{mount_line}\n"
    autoexec += f"{drive_line}\n"
    for line in merged:
        if any(line.rstrip().lower().endswith(ext) for ext in _EXEC_SUFFIXES):
            _validate_game_executable(line, media_drive)
        else:
            _validate_shell_line(line)
        autoexec += f"{line}\n"
    return autoexec


def write_launch_conf(
    media_path: Path,
    era: str,
    executable_path: Path,
    launch_commands: list[str] | None = None,
    profile: object | None = None,
    drive: object | None = None,
) -> Path:
    """Write the DOSBox-X launch conf and return its path.

    Reads config/templates/dosbox-x/base.conf, applies two in-place patches
    (output=surface, working directory option=program), then appends a
    generated [autoexec] block. Writes the result directly to
    emulators/dosbox-x/dosbox-x.conf so DOSBox-X auto-loads it from its
    working directory without a -conf flag.

    When ``drive`` is provided and ``profile.use_drive`` is True, a persistent
    HDD image is mounted as C: (created via IMGMAKE if absent). Media is then
    mounted as D:. Without a drive, the existing single-mount behaviour applies.

    Args:
        media_path: Path to the media file to mount.
        era: Era name (unused; retained for call-site symmetry).
        executable_path: Path to the DOSBox-X executable (unused; retained for
            call-site symmetry).
        launch_commands: Item-level command lines appended after profile
            commands.
        profile: Profile ORM object supplying launch_commands and use_drive.
        drive: Drive ORM object supplying slug and size_mb for the persistent
            HDD image. None means no persistent drive.

    Returns:
        Path to emulators/dosbox-x/dosbox-x.conf.

    Raises:
        FileNotFoundError: If base.conf does not exist.
        ValueError: If the media suffix is not handled or the drive path escapes
            the drives directory.
    """
    use_drive = bool(getattr(profile, 'use_drive', True)) if profile is not None else True

    drive_setup_lines, mount_line, drive_line, media_drive = _build_drive_mount_lines(
        drive, use_drive, media_path
    )

    # Layer 1: profile commands (base defaults, run first).
    profile_cmds: list[str] = getattr(profile, 'launch_commands', None) or []
    # Layer 2: item commands (item-specific paths, appended after).
    # Scan candidates and executable_path are display-only — they must never
    # reach this list. Only the user's explicit launch_commands field feeds here.
    item_cmds: list[str] = launch_commands or []

    autoexec = _build_autoexec(
        drive_setup_lines, mount_line, drive_line, media_drive, profile_cmds, item_cmds
    )

    base_conf = get_base_path() / "config" / "templates" / "dosbox-x" / "base.conf"
    if not base_conf.exists():
        raise FileNotFoundError(f"DOSBox-X base.conf not found: {base_conf}")
    base = _strip_autoexec(base_conf.read_text(encoding="utf-8", errors="replace"))

    conf_path = get_base_path() / "emulators" / "dosbox-x" / "dosbox-x.conf"
    content = base.rstrip("\n") + "\n\n" + autoexec

    conf_path.write_text(content, encoding="utf-8")

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
    launch_commands: list[str] | None = None,
    profile: object | None = None,
    drive: object | None = None,
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
        launch_commands: Item-level commands; merged after profile commands.
        profile: Profile ORM object supplying launch_commands, use_drive, and
            an optional container_enabled override.
        drive: Drive ORM object for the persistent HDD image, or None.

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

    conf_path = write_launch_conf(
        media_path, era, Path(executable_path),
        launch_commands=launch_commands,
        profile=profile,
        drive=drive,
    )
    atexit.register(lambda: conf_path.unlink(missing_ok=True))

    args = build_args(media_path, era, enable_networking=enable_networking)
    job_name = f"peach1up_dosbox_{era}_{media_path.stem}"

    # Resolve container_enabled: profile field overrides the emulator catalog value.
    catalog_enabled = get_container_enabled("dosbox-x")
    profile_override = getattr(profile, 'container_enabled', None)
    container_enabled = profile_override if profile_override is not None else catalog_enabled

    if container_enabled:
        from backend.service.utils.app_container import get_container_config as _build_cfg
        sandbox_config = _build_cfg("dosbox-x", executable_path)
        sandbox_config.broker_files.append(
            BrokerFile(path=str(get_base_path() / "library"), access="r", mode="grant"))
        use_drive = bool(getattr(profile, 'use_drive', True)) if profile is not None else True
        if drive is not None and use_drive and drive.image_path is not None:
            sandbox_config.broker_files.append(
                BrokerFile(
                    path=str(Path(drive.image_path).parent),
                    access="rw",
                    mode="grant",
                ))
    else:
        sandbox_config = None

    result = launch_under_job_object(
        cwd=str(Path(executable_path).parent),
        executable_path=executable_path,
        args=args,
        media_paths=[str(media_path)],
        era=era,
        job_name=job_name,
        slug="dosbox-x",
        container_enabled=container_enabled,
        sandbox_config=sandbox_config,
    )

    return result
