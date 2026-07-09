import struct
from pathlib import Path

from .result import ScanResult


def detect_exe(exe_path: Path) -> ScanResult:
    try:
        with exe_path.open("rb") as fh:
            header = fh.read(4096)

        if len(header) < 2 or header[:2] != b"MZ":
            return ScanResult(
                title=None, platform=None, era="dos", confidence=0.6,
                reason="no MZ header — likely DOS COM-style executable",
            )
        if len(header) < 0x40:
            return ScanResult(
                title=None, platform=None, era="dos", confidence=0.7,
                reason="MZ header present, no PE signature — DOS executable",
            )

        pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
        try:
            file_size = exe_path.stat().st_size
        except OSError:
            file_size = len(header)

        if pe_offset >= file_size or pe_offset + 96 > len(header):
            return ScanResult(
                title=None, platform=None, era="dos", confidence=0.7,
                reason="MZ header present, no PE signature — DOS executable",
            )
        if header[pe_offset: pe_offset + 4] != b"PE\x00\x00":
            return ScanResult(
                title=None, platform=None, era="dos", confidence=0.7,
                reason="MZ header present, no PE signature — DOS executable",
            )

        # Optional header offset 40 = MajorOperatingSystemVersion; pe_offset + 24 + 40 = pe_offset + 64
        major_os = struct.unpack_from("<H", header, pe_offset + 64)[0]
        if major_os >= 5:
            return ScanResult(
                title=None, platform=None, era="winxp", confidence=0.75,
                reason=f"PE MajorOSVersion={major_os} — Windows XP era executable",
            )
        if major_os == 4:
            return ScanResult(
                title=None, platform=None, era="win98", confidence=0.75,
                reason=f"PE MajorOSVersion={major_os} — Windows 9x era executable",
            )
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason=f"PE MajorOSVersion={major_os} not mapped to a known era",
        )
    except Exception as exc:
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason=f"detection error reading PE header: {exc}",
        )
