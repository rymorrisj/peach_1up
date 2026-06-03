import io
import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.service.utils.chd_image import detect_chd_platform

_CHD_MAGIC = b"MComprHD"
_META_OFFSET_POS = 48
_HEADER_SIZE = 124


def _build_chd(track_type: str) -> bytes:
    """Build a minimal CHD v5 buffer with a single CHTR track metadata entry."""
    meta_offset = _HEADER_SIZE
    track_data = f"TRACK:1 TYPE:{track_type} SUBTYPE:NONE FRAMES:100".encode("ascii")
    length = len(track_data)

    header = bytearray(_HEADER_SIZE)
    header[0:8] = _CHD_MAGIC
    struct.pack_into(">Q", header, _META_OFFSET_POS, meta_offset)

    # Metadata entry: tag(4) + flags(1) + length(3 big-endian) + next(8) + data
    length_bytes = struct.pack(">I", length)[1:]  # 24-bit
    entry = b"CHTR" + b"\x00" + length_bytes + struct.pack(">Q", 0) + track_data

    return bytes(header) + entry


def _patch_open(data: bytes):
    bio = io.BytesIO(data)
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=bio)
    cm.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=cm)


class TestDetectChdPlatform:
    def test_ps2_detected(self):
        data = _build_chd("MODE1")
        with patch.object(Path, "open", _patch_open(data)):
            assert detect_chd_platform("game.chd") == "ps2"

    def test_dreamcast_detected(self):
        data = _build_chd("MODE1_RAW")
        with patch.object(Path, "open", _patch_open(data)):
            assert detect_chd_platform("game.chd") == "dreamcast"

    def test_bad_magic_returns_unknown(self):
        data = b"BADMAGIC" + bytes(200)
        with patch.object(Path, "open", _patch_open(data)):
            assert detect_chd_platform("game.chd") == "unknown"

    def test_io_error_returns_unknown(self):
        open_mock = MagicMock(side_effect=OSError("no such file"))
        with patch.object(Path, "open", open_mock):
            assert detect_chd_platform("missing.chd") == "unknown"

    def test_audio_track_returns_dreamcast(self):
        data = _build_chd("AUDIO")
        with patch.object(Path, "open", _patch_open(data)):
            assert detect_chd_platform("game.chd") == "dreamcast"
