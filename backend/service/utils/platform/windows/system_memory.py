"""Win32 system memory query.

Single purpose: get_total_physical_memory_mb() backs eras_config.py's
hardcoded memory_limit_mb sanity ceiling (75% of real system RAM). Mirrors
wincage's ctypes interop style (explicit Structure, declared argtypes and
restype) rather than an undeclared call, since the result feeds a resource
safety ceiling, not a display value.

Module import is safe on any platform, ctypes and ctypes.wintypes carry no
Windows-only attributes at import time. Only get_total_physical_memory_mb()
touches ctypes.windll, which exists on Windows only, so the failure is
deferred to call time, matching the rest of this project's Windows-only
launch path (wincage itself has the same shape).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes


class _MEMORYSTATUSEX(ctypes.Structure):
    """Maps to the Win32 MEMORYSTATUSEX structure."""

    _fields_ = [
        ("dwLength", ctypes.wintypes.DWORD),
        ("dwMemoryLoad", ctypes.wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def get_total_physical_memory_mb() -> int:
    """Return real total physical system RAM in MB via GlobalMemoryStatusEx.

    Raises RuntimeError if the Win32 call reports failure. There is no
    non-Windows fallback, this project's launch path only ever runs on
    Windows, the same assumption wincage's Job Object layer already makes.
    """
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    status = _MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)

    kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MEMORYSTATUSEX)]
    kernel32.GlobalMemoryStatusEx.restype = ctypes.wintypes.BOOL

    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise RuntimeError(
            f"GlobalMemoryStatusEx failed (GetLastError={ctypes.GetLastError()})."
        )

    return status.ullTotalPhys // (1024 * 1024)
