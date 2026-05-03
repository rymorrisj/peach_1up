from __future__ import annotations

import math
import struct
from pathlib import Path

from utils.constants import Era
from utils.profile import Profile, save


_SECTOR = 512
_RESERVED_SECTORS = 4
_NUM_FATS = 2
_ROOT_DIR_ENTRIES = 512
_ROOT_DIR_SECTORS = (_ROOT_DIR_ENTRIES * 32) // _SECTOR  # 32
_PARTITION_OFFSET = 63  # MBR gap; FAT BPB starts at this LBA

# (total_sectors, sectors_per_cluster, fat_sectors)
# Values derived from FAT16 geometry constraints — see plan doc for working.
_ERA_PARAMS: dict[Era, tuple[int, int, int]] = {
    Era.DOS:   (504 * 1024 * 1024 // _SECTOR, 16, 252),  # 1,032,192 sectors, 64,478 clusters
    Era.WIN31: (1024 * 1024 * 1024 // _SECTOR, 32, 256), # 2,097,152 sectors, 65,518 clusters
}


def hdd_size_param(era: Era) -> str:
    """Return the DOSBox-X -size geometry string for the HDD image of the given era."""
    total_sectors, _, _ = _ERA_PARAMS[era]
    cylinders = math.ceil(total_sectors / (63 * 255))
    return f"-size 512,63,255,{cylinders}"


def _chs(lba: int, heads: int = 255, spt: int = 63) -> bytes:
    cyl = lba // (heads * spt)
    head = (lba // spt) % heads
    sec = (lba % spt) + 1
    if cyl > 1023:
        cyl, head, sec = 1023, 254, 63
    return bytes([head, ((cyl >> 8) << 6) | sec, cyl & 0xFF])


def _mbr(total_sectors: int) -> bytes:
    partition_sectors = total_sectors - _PARTITION_OFFSET
    entry = struct.pack(
        '<B3sB3sII',
        0x80,
        _chs(_PARTITION_OFFSET),
        0x06,                       # FAT16 >= 32 MB
        _chs(total_sectors - 1),
        _PARTITION_OFFSET,
        partition_sectors,
    )
    return b'\x00' * 446 + entry + b'\x00' * 48 + b'\x55\xAA'


def _fat16_boot_sector(partition_sectors: int, spc: int, spf: int) -> bytes:
    header = struct.pack(
        '<3s8sHBHBHHBHHHIIBBBI11s8s',
        b'\xeb\x58\x90',
        b'MSWIN4.1',
        _SECTOR,
        spc,
        _RESERVED_SECTORS,
        _NUM_FATS,
        _ROOT_DIR_ENTRIES,
        0,
        0xF8,
        spf,
        63,
        255,
        _PARTITION_OFFSET,   # BPB_HiddSec — sectors before partition
        partition_sectors,   # BPB_TotSec32 — sectors in partition only
        0x80,
        0,
        0x29,
        0x12345678,
        b'NO NAME    ',
        b'FAT16   ',
    )
    return header + b'\x00' * (510 - len(header)) + b'\x55\xAA'


def _fat16_table(spf: int) -> bytes:
    # FAT[0] = 0xFFF8 (media descriptor), FAT[1] = 0xFFFF (reserved EOF)
    # All remaining entries = 0x0000 (free cluster)
    return b'\xf8\xff\xff\xff' + b'\x00' * (spf * _SECTOR - 4)


def _create_raw_image(dest: Path, era: Era) -> None:
    total_sectors, spc, spf = _ERA_PARAMS[era]
    partition_sectors = total_sectors - _PARTITION_OFFSET

    mbr      = _mbr(total_sectors)
    gap      = b'\x00' * ((_PARTITION_OFFSET - 1) * _SECTOR)   # sectors 1–62
    boot     = _fat16_boot_sector(partition_sectors, spc, spf)
    fat      = _fat16_table(spf)
    root_dir = b'\x00' * (_ROOT_DIR_SECTORS * _SECTOR)

    try:
        with dest.open('wb') as fh:
            fh.write(mbr)                            # sector 0
            fh.write(gap)                            # sectors 1–62
            fh.write(boot)                           # sector 63 (partition start)
            fh.write(b'\x00' * (3 * _SECTOR))       # sectors 64–66: reserved
            fh.write(fat)                            # FAT copy 1
            fh.write(fat)                            # FAT copy 2
            fh.write(root_dir)                       # root directory (empty)
            fh.seek(total_sectors * _SECTOR - 1)    # leave data region sparse
            fh.write(b'\x00')
    except OSError as exc:
        raise RuntimeError(
            f"Failed to create HDD image at '{dest}': {exc}"
        ) from exc


def ensure_hdd(profile: Profile, images_dir: Path, profiles_dir: Path) -> Path:
    if profile.era not in _ERA_PARAMS:
        raise ValueError(
            f"Era '{profile.era.value}' is not supported for HDD image creation. "
            f"Supported: {', '.join(e.value for e in _ERA_PARAMS)}"
        )

    # Reuse existing image — never overwrite
    if profile.hdd_image_path != Path("") and profile.hdd_image_path.exists():
        return profile.hdd_image_path

    images_dir.mkdir(parents=True, exist_ok=True)
    dest = images_dir / f"{profile.name}.img"

    # Image already on disk but not recorded in profile — adopt it
    if dest.exists():
        profile.hdd_image_path = dest
        save(profile, profiles_dir)
        return dest

    _create_raw_image(dest, profile.era)

    profile.hdd_image_path = dest
    save(profile, profiles_dir)

    return dest
