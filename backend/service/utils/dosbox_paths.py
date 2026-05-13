"""
Path utilities for DOSBox-X autoexec section generation.

Centralises the host-path -> DOSBox-X path translation so the autoexec
builder in dosbox.py is free of raw f-string interpolation and handles
paths with spaces correctly on both Windows and Linux.

On Windows, GetShortPathNameW resolves 8.3 names and the result is kept in
native backslash form. Forward slashes inside a Windows path are parsed by
the DOSBox-X autoexec tokenizer as DOS switch characters (``/X``), which
can truncate the imgmount file argument. Backslashes avoid this entirely,
and 8.3 short paths never contain spaces so quoting is often unnecessary.

On Linux, forward-slash POSIX paths are used directly.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path


def get_windows_short_path(path: Path) -> str:
    """Return the 8.3 short path for *path* on Windows if available.

    Falls back to the normal native Windows path if short-name resolution
    fails or 8.3 names are disabled on the volume.
    """
    try:
        buf = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf))
        if result:
            return buf.value
    except Exception:
        pass
    return str(path)


def dosbox_host_path(path: Path, prefer_short_windows_path: bool = False) -> str:
    """Return a host path string suitable for a DOSBox-X autoexec line.

    On Windows, preserves native backslash separators. When
    ``prefer_short_windows_path`` is true, returns the 8.3 short path if
    available.

    On non-Windows platforms, returns the POSIX path form.
    """
    if sys.platform == "win32":
        if prefer_short_windows_path:
            return get_windows_short_path(path)
        return str(path)

    return path.as_posix()


def quote_if_needed(host_path: str) -> str:
    """Wrap *host_path* in double quotes only when it contains whitespace.

    DOSBox-X's autoexec parser can be picky about quoting. The safest default
    is to leave paths unquoted unless the fallback long path actually contains
    spaces.
    """
    return f'"{host_path}"' if any(ch.isspace() for ch in host_path) else host_path


def build_imgmount_cdrom(
    path: Path,
    drive: str,
    prefer_short_windows_path: bool = False,
) -> str:
    """Return an ``imgmount`` command for optical-disc media.

    Generates: ``imgmount {DRIVE} {host_path} -t iso -ro``

    Args:
        path: Host path to the ISO or CUE file.
        drive: DOSBox drive letter to mount to.
        prefer_short_windows_path: When true on Windows, prefer the 8.3 path.

    Returns:
        DOSBox-X autoexec command line.
    """
    host_path = dosbox_host_path(path, prefer_short_windows_path)
    return f'imgmount {drive.upper()} {quote_if_needed(host_path)} -t iso -ro'


def build_imgmount_hdd(
    path: Path,
    drive: str,
    prefer_short_windows_path: bool = False,
) -> str:
    """Return an ``imgmount`` command for hard-disk images.

    Generates: ``imgmount {DRIVE} {host_path} -t hdd``

    Args:
        path: Host path to the IMG file.
        drive: DOSBox drive letter to mount to.
        prefer_short_windows_path: When true on Windows, prefer the 8.3 path.

    Returns:
        DOSBox-X autoexec command line.
    """
    host_path = dosbox_host_path(path, prefer_short_windows_path)
    return f'imgmount {drive.upper()} {quote_if_needed(host_path)} -t hdd'