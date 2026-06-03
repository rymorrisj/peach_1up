from pathlib import Path
import struct

_CHD_MAGIC = b"MComprHD"
_META_CHTR = b"CHTR"
_META_CHT2 = b"CHT2"

# Byte offset of metaoffset field in CHD v5 header
_META_OFFSET_POS = 48


def detect_chd_platform(path: str | Path) -> str:
    """
    Returns one of: "ps2", "dreamcast", "unknown"
    Reads the CHD v5 metadata section to find sector size.
    2352 bytes/sector → "dreamcast" (raw GD-ROM sectors)
    2048 bytes/sector → "ps2" (standard DVD sectors)
    Returns "unknown" on any error or unrecognised sector size.
    Never raises.
    """
    try:
        p = Path(path)
        with p.open("rb") as fh:
            if fh.read(8) != _CHD_MAGIC:
                return "unknown"

            fh.seek(_META_OFFSET_POS)
            raw = fh.read(8)
            if len(raw) < 8:
                return "unknown"
            meta_offset = struct.unpack(">Q", raw)[0]

            while meta_offset != 0:
                fh.seek(meta_offset)
                entry_header = fh.read(16)  # tag(4) + flags(1) + length(3) + next(8)
                if len(entry_header) < 16:
                    break

                tag = entry_header[0:4]
                length = struct.unpack(">I", b"\x00" + entry_header[5:8])[0]
                next_offset = struct.unpack(">Q", entry_header[8:16])[0]

                if tag in (_META_CHTR, _META_CHT2) and length > 0:
                    data = fh.read(length)
                    sector_size = _parse_track_type(data.decode("ascii", errors="replace"))
                    if sector_size == 2352:
                        return "dreamcast"
                    if sector_size == 2048:
                        return "ps2"

                meta_offset = next_offset

        return "unknown"
    except Exception:
        return "unknown"


def _parse_track_type(track_meta: str) -> int | None:
    """Parse TYPE field from CHTR/CHT2 metadata string; return sector size or None."""
    for part in track_meta.split():
        if part.startswith("TYPE:"):
            t = part[5:].strip()
            if t in ("MODE1_RAW", "MODE2_RAW", "AUDIO"):
                return 2352
            if t in ("MODE1", "MODE2_FORM1"):
                return 2048
    return None
