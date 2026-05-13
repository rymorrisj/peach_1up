"""
Path utilities for DOSBox-X autoexec section generation.

Centralises the host-path → DOSBox-X path translation so the autoexec
builder in dosbox.py is free of raw f-string interpolation and handles
paths with spaces correctly on both Windows and Linux.

On Windows, GetShortPathNameW resolves 8.3 names so the path can be passed
unquoted inside a DOSBox-X autoexec line — quoted long paths with spaces are
not reliably accepted there.  On Linux, forward-slash POSIX paths are used
directly (DOSBox-X accepts them on both platforms).
"""

import ctypes
from pathlib import Path


def windows_quote_arg(s: str) -> str:
    """Wrap *s* in double quotes for use in a DOSBox-X autoexec line."""
    return f'"{s}"'


def get_windows_short_path(path: Path) -> str:
    """Return the 8.3 short path for *path* via GetShortPathNameW.

    Falls back to the POSIX representation of *path* if the API call fails
    (path does not exist yet, or 8.3 name generation is disabled on the volume).

    Only meaningful on Windows — callers guard this with
    ``prefer_short_windows_path=True`` only when ``sys.platform == 'win32'``.
    """
    try:
        buf = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf))
        if result:
            return Path(buf.value).as_posix()
    except Exception:
        pass
    return path.as_posix()


def dosbox_host_path(path: Path, prefer_short_windows_path: bool = False) -> str:
    """Return a path string suitable for embedding in a DOSBox-X autoexec line.

    Uses forward slashes on all platforms.  When *prefer_short_windows_path*
    is ``True``, attempts to resolve the Windows 8.3 short path first so paths
    with spaces don't require quoting workarounds inside the autoexec section.
    """
    if prefer_short_windows_path:
        return get_windows_short_path(path)
    return path.as_posix()


def build_imgmount_cdrom(
    path: Path,
    drive: str,
    prefer_short_windows_path: bool = False,
) -> str:
    """Return an ``imgmount`` command line for an optical-disc image (.iso or .cue).

    Generates: ``imgmount {DRIVE} "{host_path}" -t iso -ro``
    """
    host_path = dosbox_host_path(path, prefer_short_windows_path)
    return f'imgmount {drive.upper()} {windows_quote_arg(host_path)} -t iso -ro'


def build_mount_dir(
    path: Path,
    drive: str,
    prefer_short_windows_path: bool = False,
) -> str:
    """Return a ``mount`` command line for a hard-disk image (.img).

    Generates: ``imgmount {DRIVE} "{host_path}" -t hdd``

    Named ``build_mount_dir`` because the result makes a drive letter available
    as a navigable directory inside DOSBox-X, regardless of the underlying
    imgmount mechanism.
    """
    host_path = dosbox_host_path(path, prefer_short_windows_path)
    return f'imgmount {drive.upper()} {windows_quote_arg(host_path)} -t hdd'
