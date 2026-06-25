"""Tests for the CHS geometry computed in _build_drive_mount_lines (dosbox.py).

Regression coverage: cyl was previously computed with floor division
(total_sectors // (spt * hpc)), which under-declares the IMGMOUNT -size
capacity relative to what the FAT16 BPB baked into the image actually
contains, truncating the visible drive. The fix rounds up (ceiling division)
so the CHS triple always covers at least total_sectors.
"""

import re

import pytest

from backend.service.backends.dosbox import _build_drive_mount_lines
from backend.service.utils.fat import format_fat16
from backend.service.utils.fat.geometry import FAT16_SIZE_MAX_MB, FAT16_SIZE_MIN_MB, _read_geometry


def _make_image(tmp_path, size_mb):
    img = tmp_path / "drive.img"
    format_fat16(img, size_mb)
    return img


def _cyl_from_mount_lines(lines):
    for line in lines:
        m = re.search(r"-size 512,(\d+),(\d+),(\d+)", line)
        if m:
            spt, hpc, cyl = (int(x) for x in m.groups())
            return spt, hpc, cyl
    raise AssertionError(f"No IMGMOUNT -size line found in {lines}")


@pytest.mark.parametrize("size_mb", [FAT16_SIZE_MIN_MB, 50, 128, 129, 256, 512, FAT16_SIZE_MAX_MB])
def test_chs_geometry_covers_actual_image_size(tmp_path, monkeypatch, size_mb):
    """The CHS triple's capacity must be >= the image's real total_sectors."""
    library_path = tmp_path / "library"
    library_path.mkdir()
    img = library_path / "drive.img"
    format_fat16(img, size_mb)

    monkeypatch.setattr(
        "backend.service.backends.dosbox.get_base_path",
        lambda: tmp_path,
    )

    drive_setup_lines, _mount_line, _drive_line, _media_drive = _build_drive_mount_lines(
        drive_image_path=img,
        drive_size_mb=size_mb,
        use_drive=True,
        media_path=library_path / "GAME.EXE",
    )

    spt, hpc, cyl = _cyl_from_mount_lines(drive_setup_lines)
    geo = _read_geometry(img)

    declared_capacity = cyl * spt * hpc
    assert declared_capacity >= geo["total_sectors"], (
        f"size_mb={size_mb}: CHS triple ({spt},{hpc},{cyl}) covers "
        f"{declared_capacity} sectors but image needs {geo['total_sectors']}"
    )


def test_chs_cylinder_count_stays_within_bios_limit(tmp_path, monkeypatch):
    """At the largest supported image size, cylinder count must stay well under
    the classic INT13 CHS cap of 1024 cylinders that DOSBox-X's -size expects."""
    library_path = tmp_path / "library"
    library_path.mkdir()
    img = library_path / "drive.img"
    format_fat16(img, FAT16_SIZE_MAX_MB)

    monkeypatch.setattr(
        "backend.service.backends.dosbox.get_base_path",
        lambda: tmp_path,
    )

    drive_setup_lines, _, _, _ = _build_drive_mount_lines(
        drive_image_path=img,
        drive_size_mb=FAT16_SIZE_MAX_MB,
        use_drive=True,
        media_path=library_path / "GAME.EXE",
    )

    _, _, cyl = _cyl_from_mount_lines(drive_setup_lines)
    assert cyl < 1024
