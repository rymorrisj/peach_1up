import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.service.utils.xbox_image import detect_xbox_image_type, is_xiso

_XBOX_MAGIC = b"MICROSOFT*XBOX*MEDIA"
_ISO9660_MAGIC = b"CD001"


def _make_image(xbox_magic: bool, iso_magic: bool) -> bytes:
    """Build a minimal in-memory image buffer with magic bytes at real offsets."""
    size = 0x10000 + 20
    buf = bytearray(size)
    if iso_magic:
        buf[0x8001:0x8006] = _ISO9660_MAGIC
    if xbox_magic:
        buf[0x10000:0x10014] = _XBOX_MAGIC
    return bytes(buf)


def _patch_open(data: bytes, stat_size: int = 0):
    """Return a context-manager patch for Path.open that yields a BytesIO."""
    bio = io.BytesIO(data)

    mock_stat = MagicMock()
    mock_stat.st_size = stat_size

    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=bio)
    cm.__exit__ = MagicMock(return_value=False)

    open_mock = MagicMock(return_value=cm)
    stat_mock = MagicMock(return_value=mock_stat)

    return open_mock, stat_mock


class TestDetectXboxImageType:
    def test_xiso_detected(self):
        data = _make_image(xbox_magic=True, iso_magic=False)
        open_mock, stat_mock = _patch_open(data)
        with patch.object(Path, "open", open_mock), patch.object(Path, "stat", stat_mock):
            assert detect_xbox_image_type("game.iso") == "xiso"
            assert is_xiso("game.iso") is True

    def test_dvd_rip_detected(self):
        data = _make_image(xbox_magic=False, iso_magic=True)
        open_mock, stat_mock = _patch_open(data, stat_size=7_900_000_000)
        with patch.object(Path, "open", open_mock), patch.object(Path, "stat", stat_mock):
            assert detect_xbox_image_type("game.iso") == "dvd_rip"

    def test_iso9660_detected(self):
        data = _make_image(xbox_magic=False, iso_magic=True)
        open_mock, stat_mock = _patch_open(data, stat_size=700_000_000)
        with patch.object(Path, "open", open_mock), patch.object(Path, "stat", stat_mock):
            assert detect_xbox_image_type("game.iso") == "iso9660"

    def test_unknown_on_io_error(self):
        open_mock = MagicMock(side_effect=OSError("no such file"))
        with patch.object(Path, "open", open_mock):
            assert detect_xbox_image_type("missing.iso") == "unknown"
            assert is_xiso("missing.iso") is False

    def test_unknown_on_garbage_data(self):
        data = bytes(0x10000 + 20)
        open_mock, stat_mock = _patch_open(data)
        with patch.object(Path, "open", open_mock), patch.object(Path, "stat", stat_mock):
            assert detect_xbox_image_type("garbage.iso") == "unknown"
