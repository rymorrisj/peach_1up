import pytest


class TestHasValidMbr:
    def test_valid_mbr_returns_true(self, tmp_path):
        from backend.service.utils.disk_utils import has_valid_mbr
        img = tmp_path / "disk.vhd"
        data = bytearray(512)
        data[510] = 0x55
        data[511] = 0xAA
        img.write_bytes(bytes(data))
        assert has_valid_mbr(img) is True

    def test_blank_disk_returns_false(self, tmp_path):
        from backend.service.utils.disk_utils import has_valid_mbr
        img = tmp_path / "blank.vhd"
        img.write_bytes(b"\x00" * 512)
        assert has_valid_mbr(img) is False

    def test_short_file_returns_false(self, tmp_path):
        from backend.service.utils.disk_utils import has_valid_mbr
        img = tmp_path / "short.vhd"
        img.write_bytes(b"\x55\xaa")  # signature bytes present but at offset 0, not 510
        assert has_valid_mbr(img) is False

    def test_empty_file_returns_false(self, tmp_path):
        from backend.service.utils.disk_utils import has_valid_mbr
        img = tmp_path / "empty.vhd"
        img.write_bytes(b"")
        assert has_valid_mbr(img) is False

    def test_nonexistent_path_raises_value_error(self, tmp_path):
        from backend.service.utils.disk_utils import has_valid_mbr
        with pytest.raises(ValueError):
            has_valid_mbr(tmp_path / "missing.vhd")
