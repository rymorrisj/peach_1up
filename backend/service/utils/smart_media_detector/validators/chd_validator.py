import struct
from pathlib import Path

from ..result import ScanResult

_CHD_MAGIC = b"MComprHD"
_META_CHTR = b"CHTR"
_META_CHT2 = b"CHT2"
_META_CHGD = b"CHGD"  # GD-ROM track — Dreamcast only

_META_OFFSET_POS = 48


def detect(path: Path) -> ScanResult:
    """
    Inspect CHD v5 metadata chain to determine platform.

    CHGD tag  → Dreamcast (GD-ROM)
    CHTR/CHT2 → PS2 (standard CD/DVD track)
    Returns a zero-confidence result on any error or unrecognised metadata.
    Never raises.
    """
    try:
        with path.open("rb") as fh:
            if fh.read(8) != _CHD_MAGIC:
                return ScanResult(
                    title=None, platform=None, era=None, confidence=0.0,
                    reason="CHD magic bytes not found — not a valid CHD file",
                )

            fh.seek(_META_OFFSET_POS)
            raw = fh.read(8)
            if len(raw) < 8:
                return ScanResult(
                    title=None, platform=None, era=None, confidence=0.0,
                    reason="CHD header truncated — could not read metadata offset",
                )
            meta_offset = struct.unpack(">Q", raw)[0]

            while meta_offset != 0:
                fh.seek(meta_offset)
                entry_header = fh.read(16)  # tag(4) + flags(1) + length(3) + next(8)
                if len(entry_header) < 16:
                    break

                tag = entry_header[0:4]
                next_offset = struct.unpack(">Q", entry_header[8:16])[0]

                if tag == _META_CHGD:
                    return ScanResult(
                        title=None, platform=None, era="dreamcast", confidence=0.85,
                        reason="CHD metadata CHGD tag indicates GD-ROM (Dreamcast)",
                    )

                if tag in (_META_CHTR, _META_CHT2):
                    return ScanResult(
                        title=None, platform=None, era="ps2", confidence=0.85,
                        reason="CHD metadata CHTR/CHT2 tag indicates standard CD/DVD track (PS2)",
                    )

                meta_offset = next_offset

        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason="CHD container detected but no recognised platform metadata tag found",
            warnings=["no CHGD/CHTR/CHT2 tag in metadata chain"],
        )
    except Exception as exc:
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason=f"CHD read error: {exc}",
        )
