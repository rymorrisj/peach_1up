"""
DOSBox-X backend for Peach 1UP.

Handles DOS and Windows 3.1 era games using DOSBox-X natively on the Windows
host. Launch-time configuration is written to the shared DOSBox-X conf
directory so the low-privilege ``peach_sandbox`` account can read it.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
from backend.service.utils import dosbox_paths
from backend.service.utils.dosbox_config import get_shared_dosbox_conf_dir
from backend.service.utils.job_objects import (
    SandboxProcess,
    WindowsJobObject,
    launch_under_job_object,
)

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


def _strip_autoexec(conf_text: str) -> str:
    """Remove any existing ``[autoexec]`` section from DOSBox-X config text.

    DOSBox-X applies the last ``[autoexec]`` section it sees. Peach 1UP
    generates its own launch-time ``[autoexec]`` block, so any pre-existing
    one in the emulator's bundled ``dosbox-x.conf`` is stripped to avoid
    duplicate mount commands and conflicting startup behavior. The helper also
    normalises ``lastdrive`` to ``z`` so DOSBox-X has room for mounted drives.

    Args:
        conf_text: Full text of a DOSBox-X config file.

    Returns:
        Config text with any ``[autoexec]`` section removed and ``lastdrive``
        normalised.
    """
    lines = conf_text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        if lines[i].strip().lower() == "[autoexec]":
            end = i + 1
            while end < len(lines):
                stripped = lines[end].strip()
                if stripped.startswith("[") and stripped.endswith("]") and stripped != "[autoexec]":
                    break
                end += 1
            lines = lines[:i] + lines[end:]
            continue
        i += 1

    base = "".join(lines)
    base = re.sub(r"lastdrive\s*=\s*\w", "lastdrive = z", base, flags=re.IGNORECASE)
    return base


def write_launch_conf(media_path: Path, era: str, executable_path: Path) -> Path:
    """Write the launch-specific DOSBox-X conf used for this emulator run.

    The generated file starts from the emulator's bundled ``dosbox-x.conf`` if
    present, removes any existing ``[autoexec]`` section, and appends Peach
    1UP's mount commands as the sole ``[autoexec]`` block.

    Unlike the earlier repo-local temp implementation, this conf is written to
    the shared DOSBox-X conf directory so the low-privilege ``peach_sandbox``
    account can read it during ``CreateProcessWithLogonW`` launches.

    On Windows, mount commands use native Windows paths and may prefer 8.3
    short paths where requested by the DOSBox path helper.

    Args:
        media_path: Path to the media file to mount.
        era: Era name (unused here; retained for call-site symmetry).
        executable_path: Path to the DOSBox-X executable.

    Returns:
        Path to the written launch ``.conf`` file.

    Raises:
        ValueError: If the media suffix is not handled by this backend.
    """
    suffix = media_path.suffix.lower()
    prefer_short = sys.platform == "win32"

    if suffix == ".img":
        mount_line = dosbox_paths.build_mount_dir(
            media_path,
            "C",
            prefer_short_windows_path=prefer_short,
        )
        drive_line = "C:"
    elif suffix in {".iso", ".cue"}:
        mount_line = dosbox_paths.build_imgmount_cdrom(
            media_path,
            "D",
            prefer_short_windows_path=prefer_short,
        )
        drive_line = "D:"
    else:
        raise ValueError(f"Unhandled media suffix '{suffix}'. This indicates a programming error.")

    emulator_conf = executable_path.parent / "dosbox-x.conf"
    if emulator_conf.exists():
        base = _strip_autoexec(emulator_conf.read_text(encoding="utf-8", errors="replace"))
    else:
        base = ""

    conf_dir = get_shared_dosbox_conf_dir()
    conf_dir.mkdir(parents=True, exist_ok=True)

    conf_path = conf_dir / "launch.conf"

    content = base.rstrip("\n")
    if content:
        content += "\n"
    content += f"[autoexec]\n{mount_line}\n{drive_line}\n"

    conf_path.write_text(content, encoding="utf-8")
    return conf_path


def build_args(media_path: Path, era: str, enable_networking: bool = False) -> List[str]:
    """Build DOSBox-X command-line arguments for the given media and era.

    This is a pure function with no I/O operations.

    Args:
        media_path: Path to the media file.
        era: Era name (``'dos'`` or ``'win31'``).
        enable_networking: When ``False`` (default), the NE2000 adapter is
            disabled via ``-set ne2000=false``. When ``True``, the adapter
            config is left at the emulator default.

    Returns:
        List of command-line arguments, excluding the executable path.

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

    suppress = ["-set", "dos:automount=false", "-set", "dos:mountwarning=false"]

    # Disable NE2000 adapter unless the profile explicitly enables networking.
    net_args = [] if enable_networking else ["-set", "ne2000=false"]

    # Explicit SoundBlaster 16 settings override any user-level dosbox-x.conf
    # that might have sound disabled or misconfigured. Values match the SB16
    # hardware defaults that the majority of DOS games expect without extra setup.
    sound_args = [
        "-set",
        "sblaster:sbtype=sb16",
        "-set",
        "sblaster:sbbase=220",
        "-set",
        "sblaster:irq=7",
        "-set",
        "sblaster:dma=1",
        "-set",
        "sblaster:hdma=5",
        "-set",
        "sblaster:oplmode=auto",
        "-set",
        "mixer:rate=44100",
        "-set",
        "mixer:nosound=false",
    ]

    return suppress + sound_args + net_args


def launch(
    media_path: Path,
    era: str,
    executable_path: str,
    enable_networking: bool = False,
) -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch DOSBox-X with the given media file under Job Object isolation.

    This is the single entry point for the DOSBox-X backend. It validates the
    media, builds the command-line arguments, writes a launch-specific conf to
    the shared DOSBox-X conf directory, and launches the process under the
    ``peach_sandbox`` account with Windows Job Object limits applied.

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

    args = build_args(media_path, era, enable_networking=enable_networking)
    conf_path = write_launch_conf(media_path, era, Path(executable_path))

    print(f"DEBUG conf:\n{conf_path.read_text(encoding='utf-8', errors='replace')}", flush=True)

    args = ["-conf", str(conf_path)] + args
    job_name = f"peach1up_dosbox_{era}_{media_path.stem}"

    return launch_under_job_object(
        executable_path=executable_path,
        args=args,
        media_paths=[str(media_path)],
        era=era,
        job_name=job_name,
    )