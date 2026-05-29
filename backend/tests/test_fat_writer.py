import pytest


def _make_image(tmp_path, size_mb=10):
    from backend.service.utils.fat import format_fat16
    img = tmp_path / "test.img"
    format_fat16(img, size_mb)
    return img


class TestFormatFat16:
    def test_creates_file_of_expected_size(self, tmp_path):
        from backend.service.utils.fat import format_fat16
        img = tmp_path / "disk.img"
        size_mb = 10
        format_fat16(img, size_mb)
        assert img.stat().st_size == size_mb * 1024 * 1024

    def test_larger_image_size(self, tmp_path):
        from backend.service.utils.fat import format_fat16
        img = tmp_path / "disk.img"
        size_mb = 32
        format_fat16(img, size_mb)
        assert img.stat().st_size == size_mb * 1024 * 1024

    def test_raises_if_path_already_exists(self, tmp_path):
        from backend.service.utils.fat import format_fat16
        img = tmp_path / "disk.img"
        img.write_bytes(b"\x00")
        with pytest.raises(RuntimeError, match="already exists"):
            format_fat16(img, 10)

    def test_raises_if_size_below_minimum(self, tmp_path):
        from backend.service.utils.fat import format_fat16
        img = tmp_path / "disk.img"
        with pytest.raises(RuntimeError):
            format_fat16(img, 9)

    def test_raises_if_size_above_maximum(self, tmp_path):
        from backend.service.utils.fat import format_fat16
        img = tmp_path / "disk.img"
        with pytest.raises(RuntimeError):
            format_fat16(img, 2049)


class TestWriteReadRoundTrip:
    def test_write_and_read_back_same_bytes(self, tmp_path):
        from backend.service.utils.fat import write_file_to_image, read_file_from_image
        img = _make_image(tmp_path)
        data = b"Hello, FAT16 world!"
        write_file_to_image(img, "HELLO.TXT", data)
        assert read_file_from_image(img, "HELLO.TXT") == data

    def test_write_and_read_binary_data(self, tmp_path):
        from backend.service.utils.fat import write_file_to_image, read_file_from_image
        img = _make_image(tmp_path)
        data = bytes(range(256)) * 64
        write_file_to_image(img, "BIN.DAT", data)
        assert read_file_from_image(img, "BIN.DAT") == data

    def test_write_empty_file(self, tmp_path):
        from backend.service.utils.fat import write_file_to_image, read_file_from_image
        img = _make_image(tmp_path)
        write_file_to_image(img, "EMPTY.TXT", b"")
        assert read_file_from_image(img, "EMPTY.TXT") == b""

    def test_multiple_files_round_trip(self, tmp_path):
        from backend.service.utils.fat import write_file_to_image, read_file_from_image
        img = _make_image(tmp_path)
        files = {
            "ALPHA.TXT": b"alpha data",
            "BETA.BIN":  b"\x00\x01\x02\x03" * 100,
            "GAMMA.DAT": b"gamma" * 200,
        }
        for name, data in files.items():
            write_file_to_image(img, name, data)
        for name, data in files.items():
            assert read_file_from_image(img, name) == data

    def test_files_in_subdirectory(self, tmp_path):
        from backend.service.utils.fat import write_file_to_image, read_file_from_image
        img = _make_image(tmp_path)
        data = b"nested file content"
        write_file_to_image(img, "GAMES/DOOM/DOOM.EXE", data)
        assert read_file_from_image(img, "GAMES/DOOM/DOOM.EXE") == data


class TestLongFilenames:
    def test_long_name_silently_truncated_on_write_and_read(self, tmp_path):
        from backend.service.utils.fat import write_file_to_image, read_file_from_image
        img = _make_image(tmp_path)
        data = b"data for a long-named file"
        # Name > 8 chars is truncated to 8.3 consistently on both write and read.
        write_file_to_image(img, "averylongfilename.txt", data)
        result = read_file_from_image(img, "averylongfilename.txt")
        assert result == data

    def test_truncated_names_collide(self, tmp_path):
        from backend.service.utils.fat import write_file_to_image
        img = _make_image(tmp_path)
        # Both names truncate to the same 8.3 entry "AVERYLONG.TXT".
        write_file_to_image(img, "averylongfilename.txt", b"first")
        with pytest.raises(RuntimeError, match="already exists"):
            write_file_to_image(img, "averylongfilename_other.txt", b"second")


class TestReadFileErrors:
    def test_missing_file_raises_runtime_error(self, tmp_path):
        from backend.service.utils.fat import read_file_from_image
        img = _make_image(tmp_path)
        with pytest.raises(RuntimeError, match="not found"):
            read_file_from_image(img, "NOEXIST.TXT")

    def test_missing_directory_raises_runtime_error(self, tmp_path):
        from backend.service.utils.fat import read_file_from_image
        img = _make_image(tmp_path)
        with pytest.raises(RuntimeError):
            read_file_from_image(img, "NODIR/FILE.TXT")

    def test_nonexistent_image_raises_runtime_error(self, tmp_path):
        from backend.service.utils.fat import read_file_from_image
        img = tmp_path / "ghost.img"
        with pytest.raises(RuntimeError, match="does not exist"):
            read_file_from_image(img, "FILE.TXT")

    def test_write_to_nonexistent_image_raises_runtime_error(self, tmp_path):
        from backend.service.utils.fat import write_file_to_image
        img = tmp_path / "ghost.img"
        with pytest.raises(RuntimeError, match="does not exist"):
            write_file_to_image(img, "FILE.TXT", b"data")
