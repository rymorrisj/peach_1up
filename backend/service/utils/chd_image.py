from pathlib import Path
import struct

_CHD_MAGIC = b"MComprHD"
_META_CHTR = b"CHTR"
_META_CHT2 = b"CHT2"
_META_CHGD = b"CHGD"  # GD-ROM track — Dreamcast only

# Byte offset of metaoffset field in CHD v5 header
_META_OFFSET_POS = 48


def detect_chd_platform(path: str | Path) -> str:
    """
    Returns one of: "ps2", "dreamcast", "unknown"
    CHGD tag → "dreamcast" (GD-ROM, Dreamcast only)
    CHTR/CHT2 tag → "ps2" (standard CD/DVD track)
    Returns "unknown" on any error or unrecognised metadata.
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
                next_offset = struct.unpack(">Q", entry_header[8:16])[0]

                if tag == _META_CHGD:
                    return "dreamcast"

                if tag in (_META_CHTR, _META_CHT2):
                    return "ps2"

                meta_offset = next_offset

        return "unknown"
    except Exception:
        return "unknown"
