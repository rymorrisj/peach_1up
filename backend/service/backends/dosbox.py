"""
DOSBox-X backend for Peach 1UP
Handles DOS and Windows 3.1 era games using DOSBox-X natively on Windows host.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
from backend.service.utils import dosbox_paths
from backend.service.utils.job_objects import launch_under_job_object, SandboxProcess, WindowsJobObject

_DOSBOX_ERAS = {Era.DOS, Era.WIN31}
SUPPORTED_ERAS = {e.value for e in _DOSBOX_ERAS}
SUPPORTED_MEDIA = ERA_MEDIA_TYPES[Era.DOS] | ERA_MEDIA_TYPES[Era.WIN31]


def validate_media(media_path: Path) -> None:
    """
    Validate media file for DOSBox-X backend.

    Checks that file exists and has supported extension.

    Args:
        media_path: Path to media file

    Raises:
        FileNotFoundError: If media file does not exist
        ValueError: If media file extension is not supported
    """
    if not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")

    if media_path.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(f"Unsupported media format '{media_path.suffix}'. "
                        f"DOSBox-X backend supports: {', '.join(sorted(SUPPORTED_MEDIA))}")


def write_launch_conf(media_path: Path, era: str) -> Path:
    """Write a minimal DOSBox-X .conf containing only an [autoexec] section.

    On Windows, uses the 8.3 short path so that DOSBox-X autoexec lines are
    not broken by spaces â€” quoted long paths are not reliably accepted there.
    On Linux, uses the POSIX path directly.

    Args:
        media_path: Path to the media file to mount.
        era: Era name (unused here; kept for call-site symmetry).

    Returns:
        Path to the written .conf file inside a fresh temp directory.
    """
    suffix = media_path.suffix.lower()
    prefer_short = sys.platform == 'win32'

    if suffix == '.img':
        mount_line = dosbox_paths.build_mount_dir(media_path, 'C', prefer_short_windows_path=prefer_short)
        drive_line = 'C:'
    elif suffix in {'.iso', '.cue'}:
        mount_line = dosbox_paths.build_imgmount_cdrom(media_path, 'D', prefer_short_windows_path=prefer_short)
        drive_line = 'D:'
    else:
        raise ValueError(f"Unhandled media suffix '{suffix}'. This indicates a programming error.")

    # TODO(PX): clean up temp conf on process exit
    conf_dir = Path(tempfile.mkdtemp())
    conf_path = conf_dir / 'launch.conf'
    conf_path.write_text(f'[autoexec]\n{mount_line}\n{drive_line}\n', encoding='utf-8')
    return conf_path


def build_args(media_path: Path, era: str, enable_networking: bool = False) -> List[str]:
    """
    Build DOSBox-X command line arguments for given media and era.

    Pure function with no I/O operations.

    Args:
        media_path: Path to media file
        era: Era name ('dos' or 'win31')
        enable_networking: When False (default), the NE2000 adapter is
            disabled via -set ne2000=false. When True, the adapter config
            is left at the emulator default.

    Returns:
        List of command line arguments (excludes executable path)

    Raises:
        ValueError: If era is not in supported set {'dos', 'win31'}
        ValueError: If media suffix is not in supported set {'.iso', '.img', '.cue'}
    """
    if era not in SUPPORTED_ERAS:
        raise ValueError(f"Era '{era}' not supported by DOSBox-X backend. "
                        f"Supported: {', '.join(sorted(SUPPORTED_ERAS))}")

    suffix = media_path.suffix.lower()
    if suffix not in SUPPORTED_MEDIA:
        raise ValueError(f"Media suffix '{suffix}' not supported by DOSBox-X backend. "
                        f"Supported: {', '.join(sorted(SUPPORTED_MEDIA))}")

    suppress = ['-set', 'dos:automount=false', '-set', 'dos:mountwarning=false']

    # Disable NE2000 adapter unless the profile explicitly enables networking.
    net_args = [] if enable_networking else ['-set', 'ne2000=false']

    # Explicit SoundBlaster 16 settings override any user-level dosbox-x.conf
    # that might have sound disabled or misconfigured. Values match the SB16
    # hardware defaults that the majority of DOS games expect without extra setup.
    sound_args = [
        '-set', 'sblaster:sbtype=sb16',
        '-set', 'sblaster:sbbase=220',
        '-set', 'sblaster:irq=7',
        '-set', 'sblaster:dma=1',
        '-set', 'sblaster:hdma=5',
        '-set', 'sblaster:oplmode=auto',
        '-set', 'mixer:rate=44100',
        '-set', 'mixer:nosound=false',
    ]

    return suppress + sound_args + net_args


def launch(
    media_path: Path,
    era: str,
    executable_path: str,
    enable_networking: bool = False,
) -> Tuple[SandboxProcess, WindowsJobObject]:
    """
    Launch DOSBox-X with given media file under Job Object isolation.

    Single entry point for DOSBox-X backend. Validates media, builds arguments,
    and launches process under Job Object with memory limits applied.

    Args:
        media_path: Path to media file to mount
        era: Era name ('dos' or 'win31')
        executable_path: Full path to DOSBox-X executable
        enable_networking: When False (default), the NE2000 adapter is
            disabled. Set True only for software that requires a network
            connection.

    Returns:
        Tuple of (subprocess.Popen process, WindowsJobObject instance)
        Caller is responsible for cleanup via job_object.terminate_all()

    Raises:
        FileNotFoundError: If executable_path or media_path does not exist
        ValueError: If era or media extension not supported
        RuntimeError: If Job Object creation or process launch fails
    """
    if not os.path.exists(executable_path):
        raise FileNotFoundError(f"DOSBox-X executable not found: {executable_path}")

    validate_media(media_path)

    args = build_args(media_path, era, enable_networking=enable_networking)
    conf_path = write_launch_conf(media_path, era)
    args = args + ['-defaultconf', '-conf', str(conf_path)]

    job_name = f"peach1up_dosbox_{era}_{media_path.stem}"

    return launch_under_job_object(
        executable_path=executable_path,
        args=args,
        media_paths=[str(media_path)],
        era=era,
        job_name=job_name,
    )



