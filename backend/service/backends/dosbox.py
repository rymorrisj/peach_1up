"""
DOSBox-X backend for Peach 1UP.

Handles DOS and Windows 3.1 era games using DOSBox-X natively on the Windows
host. Mount commands are passed as -c autoexec args so no temporary conf file
is required. DOSBox-X loads its own bundled dosbox-x.conf automatically from
the emulator directory; -set args override specific settings on top of that.
"""

import ctypes
import os
import sys
from pathlib import Path
from typing import List, Tuple

from backend.constants import ERA_MEDIA_TYPES
from backend.constants_generated import Era
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


def _dosbox_cmd_path(path: Path) -> str:
    """Return a path string safe for a DOSBox-X -c argument.

    On Windows, returns the 8.3 short path if available (avoids quoting for
    most paths and eliminates spaces from the autoexec token boundary). Falls
    back to the native long path, quoted if it contains whitespace. Forward
    slashes are never used — the DOSBox-X autoexec tokeniser treats them as
    DOS switch characters, which truncates the imgmount file argument.

    On non-Windows platforms, returns the POSIX path form.
    """
    if sys.platform != "win32":
        return path.as_posix()
    try:
        buf = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf)):
            return buf.value
    except Exception:
        pass
    p = str(path)
    return f'"{p}"' if any(c.isspace() for c in p) else p


def build_args(media_path: Path, era: str, enable_networking: bool = False) -> List[str]:
    """Build DOSBox-X command-line arguments for the given media and era.

    Returns -c autoexec mount commands followed by -set hardware overrides.
    No temporary conf file is required.

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

    host = _dosbox_cmd_path(media_path)
    if suffix == ".img":
        mount_args = ["-c", f"imgmount C {host} -t hdd", "-c", "C:"]
    else:  # .iso or .cue
        mount_args = ["-c", f"imgmount D {host} -t iso -ro", "-c", "D:"]

    suppress = ["-set", "dos:automount=false", "-set", "dos:mountwarning=false"]

    # Disable NE2000 adapter unless the profile explicitly enables networking.
    net_args = [] if enable_networking else ["-set", "ne2000=false"]

    # Explicit SoundBlaster 16 settings override any user-level dosbox-x.conf
    # that might have sound disabled or misconfigured.
    sound_args = [
        "-set", "sblaster:sbtype=sb16",
        "-set", "sblaster:sbbase=220",
        "-set", "sblaster:irq=7",
        "-set", "sblaster:dma=1",
        "-set", "sblaster:hdma=5",
        "-set", "sblaster:oplmode=auto",
        "-set", "mixer:rate=44100",
        "-set", "mixer:nosound=false",
    ]

    # core=normal avoids dynamic recompiler cache allocation spikes under the
    # Job Object memory cap, which cause crashes on some DOS titles.
    cpu_args = ["-set", "cpu:core=normal"] if era == Era.DOS.value else []

    return mount_args + suppress + sound_args + net_args + cpu_args


def launch(
    media_path: Path,
    era: str,
    executable_path: str,
    enable_networking: bool = False,
) -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch DOSBox-X with the given media file under Job Object isolation.

    This is the single entry point for the DOSBox-X backend. It validates the
    media, builds the command-line arguments, and launches the process under
    the ``peach_sandbox`` account with Windows Job Object limits applied.

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
    job_name = f"peach1up_dosbox_{era}_{media_path.stem}"

    return launch_under_job_object(
        executable_path=executable_path,
        args=args,
        media_paths=[str(media_path)],
        era=era,
        job_name=job_name,
    )
