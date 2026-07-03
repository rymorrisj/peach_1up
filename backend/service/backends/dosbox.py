"""
DOSBox-X backend for Peach 1UP.

Handles DOS and Windows 3.1 era games using DOSBox-X natively on the Windows
host. A per-launch conf file is written to a private temp directory, incorporating
the emulator's bundled dosbox-x.conf with Peach's [autoexec] and SDL overrides
appended. The temp directory is cleaned up after the process exits.
"""

import math
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import List, TYPE_CHECKING, Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.service.utils.fat.geometry import _is_bare_fat_superfloppy, _read_geometry
from backend.constants_generated import Era
from backend.service.utils.era_defaults import DOS_WIN_ERAS
from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.service.utils.emulator_catalog import get_container_enabled
from backend.service.utils.platform.windows.sandbox import BrokerFile
from backend.service.utils.platform.windows.process.launcher import launch_under_job_object
from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec

logger = get_logger(__name__)

SUPPORTED_ERAS = DOS_WIN_ERAS
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
        raise RuntimeError("launch_commands line must not contain newline characters")
    if "\x00" in line:
        raise RuntimeError("launch_commands line must not contain null bytes")
    if "#" in line:
        raise RuntimeError("launch_commands line must not contain '#' (DOSBox-X comment character)")


def _build_multi_iso_mount_line(disc_paths: list[Path]) -> str:
    """Build IMGMOUNT line for multiple ISO/CUE disc images (set launch).

    DOSBox-X supports listing multiple image paths on one IMGMOUNT command;
    the user cycles between them with Ctrl+F11 (Windows) / Ctrl+F12 (other)
    or via DOS menu → Swap CD.

    SECURITY: each path is validated against library/ before inclusion.
    """
    library_path = get_base_path() / "library"
    for dp in disc_paths:
        if not dp.resolve().is_relative_to(library_path.resolve()):
            raise ValueError(
                f"Disc path escaped library: {dp}. "
                "This indicates a data integrity problem."
            )
    all_hosts = " ".join(_dosbox_cmd_path(p) for p in disc_paths)
    return f"imgmount D {all_hosts} -t iso -ro"


def _build_drive_mount_lines(
    drive_image_path: Path | None,
    drive_size_mb: int | None,
    use_drive: bool,
    media_path: Path,
    disc_paths: list[Path] | None = None,
    run_from_c: bool = False,
) -> tuple[list[str], str | None, str, str]:
    """Return (drive_setup_lines, mount_line, drive_line, media_drive).

    mount_line is None when media_path is a directory on a persistent drive
    (files are already on C:, so no additional mount is needed).

    SECURITY: drive_image_path is validated against library/ to prevent path traversal.
    This check must not be removed or weakened.
    """
    suffix = media_path.suffix.lower()
    host = _dosbox_cmd_path(media_path)
    has_persistent_drive = drive_image_path is not None and use_drive

    drive_setup_lines: list[str] = []

    if has_persistent_drive:
        library_path = get_base_path() / "library"
        if not drive_image_path.resolve().is_relative_to(library_path.resolve()):
            raise ValueError(
                f"Drive image path escaped library: {drive_image_path}. "
                "This indicates a data integrity problem."
            )
        drive_cmd_path = _dosbox_cmd_path(drive_image_path)
        if not drive_image_path.exists():
            drive_setup_lines.append(f"IMGMAKE {drive_cmd_path} -t hd -size {drive_size_mb}")
            drive_setup_lines.append(f"IMGMOUNT C {drive_cmd_path} -t hdd")
        elif _is_bare_fat_superfloppy(drive_image_path):
            geo = _read_geometry(drive_image_path)
            spt = 63        # standard sectors per track for CHS geometry
            hpc = 255       # standard heads per cylinder
            # Round up so the CHS triple covers at least the BPB's total_sectors;
            # floor division under-declared capacity and truncated the mounted drive.
            cyl = math.ceil(geo["total_sectors"] / (spt * hpc))
            # sectoff=0 forces DOSBox-X to read the FAT BPB at sector 0 instead of
            # searching for an MBR/partition table. format_fat16 writes a bare
            # "superfloppy" (BPB at sector 0, no partition table); without this the
            # -t hdd path misclassifies it as MBR, finds no FAT partition, and fails
            # with "Cannot create drive from file".
            drive_setup_lines.append(f"IMGMOUNT C {drive_cmd_path} -t hdd -size 512,{spt},{hpc},{cyl} -o sectoff=0")
        else:
            # Partitioned image (e.g. created by the IMGMAKE branch above on an
            # earlier launch). DOSBox-X reads geometry from the MBR partition
            # table; sectoff=0 must NOT be used here — it would force reading a
            # BPB at sector 0, where the partition table actually lives, and
            # mismount the drive.
            drive_setup_lines.append(f"IMGMOUNT C {drive_cmd_path} -t hdd")


        if run_from_c:
            # Hydrated loose-file item: files already live on the writable C:
            # drive; run from there and skip the read-only D: source mount.
            mount_line = None
            drive_line = "C:"
            media_drive = "C:"
        elif media_path.is_dir():
            mount_line = None
            drive_line = "C:"
            media_drive = "C:"
        elif suffix == ".img":
            mount_line = f"imgmount D {host} -t hdd -ro"
            drive_line = "C:"
            media_drive = "D:"
        elif suffix in {".iso", ".cue"}:
            if disc_paths and len(disc_paths) > 1:
                mount_line = _build_multi_iso_mount_line(disc_paths)
            else:
                mount_line = f"imgmount D {host} -t iso -ro"
            drive_line = "C:"
            media_drive = "D:"
        elif suffix in {".exe", ".bat"}:
            parent_dir = _dosbox_cmd_path(media_path.parent)
            mount_line = f"MOUNT D {parent_dir} -ro -freesize 1024"
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
            mount_line = f"imgmount C {host} -t hdd -ro"
            drive_line = "C:"
            media_drive = "C:"
        elif suffix in {".iso", ".cue"}:
            if disc_paths and len(disc_paths) > 1:
                mount_line = _build_multi_iso_mount_line(disc_paths)
            else:
                mount_line = f"imgmount D {host} -t iso -ro"
            drive_line = "D:"
            media_drive = "D:"
        elif suffix in {".exe", ".bat"}:
            parent_dir = _dosbox_cmd_path(media_path.parent)
            mount_line = f"MOUNT D {parent_dir} -ro -freesize 1024"
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
    spec: "LaunchSpec",
    game_executable: str | None = None,
) -> Path:
    """Write the DOSBox-X launch conf to a private temp directory and return its path.

    Reads library/system/templates/dosbox-x/base.conf, strips any existing [autoexec]
    section, then appends a generated [autoexec] block. The result is written
    to a temporary directory as dosbox-x.conf and the path is returned; the
    caller passes it to DOSBox-X via the -conf flag.

    When ``spec.drive_image_path`` is set and ``spec.use_drive`` is True, a
    persistent HDD image is mounted as C: (created via IMGMAKE if absent).
    Media is then mounted as D:.

    Args:
        spec: LaunchSpec providing media_path, executable_path, era,
            use_drive, profile_launch_commands, launch_commands,
            drive_image_path, and drive_size_mb.
        game_executable: Optional single DOS executable command appended after
            item-level launch_commands.

    Returns:
        Path to the written dosbox-x.conf file inside the temp directory.

    Raises:
        FileNotFoundError: If base.conf does not exist.
        ValueError: If the media suffix is not handled or the drive path escapes
            the library directory.
    """
    media_path = spec.media_path
    executable_path = Path(spec.executable_path)

    drive_setup_lines, mount_line, drive_line, media_drive = _build_drive_mount_lines(
        spec.drive_image_path, spec.drive_size_mb, spec.use_drive, media_path,
        disc_paths=spec.disc_paths or [],
        run_from_c=spec.run_from_c,
    )

    # Layer 1: profile commands (base defaults, run first).
    profile_cmds: list[str] = list(spec.profile_launch_commands)
    # Layer 2: item commands (item-specific paths, appended after).
    # Scan candidates and executable_path are display-only — they must never
    # reach this list. Only the user's explicit launch_commands field feeds here.
    exe_cmds: list[str] = []
    if game_executable:
        _validate_game_executable(game_executable, media_drive)
        exe_cmds = [game_executable]
    item_cmds: list[str] = list(spec.launch_commands) + exe_cmds

    # Auto-run: when launch_commands was never configured (auto_run_media), run
    # the game automatically from its mounted drive. Drive-qualified so it runs
    # regardless of the landing drive. An explicitly-cleared command list
    # ([] -> auto_run_media False) intentionally drops the user at the prompt.
    #   * run_from_c: the files were copied to the writable C: drive, so run the
    #     copied executable (c_run_command) from C:.
    #   * otherwise: the resolved media is itself a runnable executable mounted
    #     on media_drive — run it by name.
    if spec.auto_run_media and not item_cmds:
        auto_run: str | None = None
        if spec.run_from_c:
            if spec.c_run_command:
                auto_run = f"{media_drive}\\{spec.c_run_command}"
                _validate_game_executable(auto_run, media_drive)
                if "\\" in spec.c_run_command:
                    dir_part = spec.c_run_command.rsplit("\\", 1)[0]
                    item_cmds = [f"cd \\{dir_part}", auto_run]
                else:
                    item_cmds = [auto_run]
        elif media_path.suffix.lower() in _EXEC_SUFFIXES:
            auto_run = f"{media_drive}\\{media_path.name}"
            _validate_game_executable(auto_run, media_drive)
            item_cmds = [auto_run]

    # Media-drive fallback: when nothing will run, land the shell on the media
    # drive so the installer/game is visible instead of an empty C: prompt.
    if not (profile_cmds + item_cmds):
        drive_line = media_drive

    autoexec = _build_autoexec(
        drive_setup_lines, mount_line, drive_line, media_drive, profile_cmds, item_cmds
    )

    base_conf = get_base_path() / "library" / "system" / "templates" / "dosbox-x" / "base.conf"
    if not base_conf.exists():
        raise FileNotFoundError(f"DOSBox-X base.conf not found: {base_conf}")
    base = _strip_autoexec(base_conf.read_text(encoding="utf-8", errors="replace"))

    tmpdir = Path(tempfile.mkdtemp(prefix="peach1up_dosbox_"))
    conf_path = tmpdir / "dosbox-x.conf"
    content = base.rstrip("\n") + "\n\n" + autoexec

    conf_path.write_text(content, encoding="utf-8")

    return conf_path


def _cleanup_temp_dir_on_exit(proc, tmpdir: Path) -> None:
    try:
        while proc.poll() is None:
            time.sleep(0.5)
    except Exception:
        pass
    try:
        shutil.rmtree(str(tmpdir), ignore_errors=False)
    except Exception as exc:
        logger.warning("Failed to remove DOSBox temp dir %s: %s", tmpdir, exc)


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
    args = ["-noconfig"]
    if not enable_networking:
        args += ["-set", "ne2000=false"]
    return args


def launch(spec: "LaunchSpec") -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch DOSBox-X with the given media file under Job Object isolation.

    Writes a per-launch conf to the DOSBox-X executable directory, passes
    it to DOSBox-X via auto-load, and registers a cleanup thread.

    Args:
        spec: LaunchSpec with media_path, era, executable_path,
            enable_networking, launch_commands, profile_launch_commands,
            use_drive, container_enabled, drive_image_path, drive_size_mb set.

    Returns:
        Tuple of ``(process, job_object)``. The caller is responsible for
        cleanup via ``job_object.teardown()``.

    Raises:
        FileNotFoundError: If ``executable_path`` or ``media_path`` does not exist.
        ValueError: If the era or media extension is unsupported.
        RuntimeError: If Job Object creation or process launch fails.
    """
    if not spec.executable_path or not os.path.exists(spec.executable_path):
        raise FileNotFoundError(f"DOSBox-X executable not found: {spec.executable_path}")

    validate_media(spec.media_path)

    conf_path = write_launch_conf(spec)
    tmpdir = conf_path.parent

    args = build_args(spec.media_path, spec.era, enable_networking=spec.enable_networking)
    args += ["-conf", str(conf_path)]
    job_name_prefix = f"Peach1UP_dosbox_{spec.era}_{spec.media_path.stem}"

    # Resolve container_enabled: profile field overrides the emulator catalog value.
    catalog_enabled = get_container_enabled("dosbox-x")
    container_enabled = spec.container_enabled if spec.container_enabled is not None else catalog_enabled

    if container_enabled:
        from backend.service.utils.platform.windows.app_container import get_container_config as _build_cfg
        sandbox_config = _build_cfg("dosbox-x", spec.executable_path, user_id=spec.user_id)
        sandbox_config.broker_files.append(
            BrokerFile(path=str(get_base_path() / "library"), access="r", mode="grant"))
        sandbox_config.broker_files.append(
            BrokerFile(path=str(tmpdir), access="r", mode="grant"))
        if spec.drive_image_path is not None and spec.use_drive:
            sandbox_config.broker_files.append(
                BrokerFile(
                    path=str(spec.drive_image_path.parent),
                    access="rw",
                    mode="grant",
                ))
            # A pre-existing .img does not inherit the parent-dir grant, so apply
            # an explicit ACE to the file itself or the AppContainer SID cannot
            # write it (drive changes would silently fail).
            sandbox_config.broker_files.append(
                BrokerFile(
                    path=str(spec.drive_image_path),
                    access="rw",
                    mode="secure",
                ))
    else:
        sandbox_config = None

    result = launch_under_job_object(
        cwd=str(Path(spec.executable_path).parent),
        executable_path=spec.executable_path,
        args=args,
        era=spec.era,
        job_name_prefix=job_name_prefix,
        slug="dosbox-x",
        container_enabled=container_enabled,
        sandbox_config=sandbox_config,
    )

    threading.Thread(
        target=_cleanup_temp_dir_on_exit,
        args=(result[0], tmpdir),
        daemon=True,
        name=f"dosbox_conf_cleanup_{result[0].pid}",
    ).start()

    return result
