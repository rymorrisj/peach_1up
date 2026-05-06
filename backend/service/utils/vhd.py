"""
Virtual hard disk image builder for Peach 1UP.

DOSBox-X requires a pre-formatted FAT16 disk image to serve as the game's
persistent C: drive.  We build the image ourselves so the geometry and
filesystem are exactly what DOSBox-X expects — otherwise the emulator either
refuses to mount the drive or fails at boot.

Image layout (sectors are 512 bytes each):
  Sector  0       — MBR (partition table + boot signature)
  Sectors 1 to 62    — Gap between MBR and partition start (CHS alignment)
  Sector  63      — FAT16 boot sector (BPB) — partition starts here
  Sectors 64 to 66   — Reserved sectors (BPB_RsvdSecCnt = 4, after boot sector)
  Sectors 67…    — FAT copy 1
  …               — FAT copy 2
  …               — Root directory (512 entries X 32 bytes = 32 sectors)
  …               — Data region (sparse — only the last byte is written to
                    pre-allocate the full image without writing every zeroed sector)

Why FAT16?  DOSBox-X's HDD imager targets FAT16 for DOS-era compatibility.
FAT32 and NTFS are outside the scope of the eras we support (DOS, Win 3.1).
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

from backend.service.utils.constants import Era
from backend.service.utils.profile import Profile, save


_SECTOR = 512           # bytes per sector — fixed for all FAT16 images
_RESERVED_SECTORS = 4   # BPB_RsvdSecCnt: sectors reserved before FAT1 (includes boot sector)
_NUM_FATS = 2           # BPB_NumFATs: always 2 copies for FAT16 redundancy
_ROOT_DIR_ENTRIES = 512 # BPB_RootEntCnt: max files/dirs in the root directory
_ROOT_DIR_SECTORS = (_ROOT_DIR_ENTRIES * 32) // _SECTOR  # 32-byte dir entry → 32 sectors total
_PARTITION_OFFSET = 63  # LBA of partition start; standard MBR gap for CHS alignment


# Geometry constants per era.
#
# Each tuple is (total_sectors, sectors_per_cluster, fat_sectors) where:
#   total_sectors        — image size in sectors (MBR gap + entire partition)
#   sectors_per_cluster  — BPB_SecPerClus: larger clusters reduce FAT overhead on
#                          bigger images but waste space on small files
#   fat_sectors          — BPB_FATSz16: sectors required for one copy of the FAT
#
# Derivation (DOS example, 504 MiB image):
#   total_sectors     = 504 × 1024 × 1024 / 512 = 1,032,192
#   partition_sectors = 1,032,192 − 63           = 1,032,129
#   data_sectors      = 1,032,129 − 4 (reserved) − 2×252 (FATs) − 32 (root)
#                     = 1,031,589
#   cluster_count     = 1,031,589 / 16            = 64,474   (< 65,525 FAT16 limit ✓)
#   fat_entries       = cluster_count + 2         = 64,476   (FAT[0] and FAT[1] reserved)
#   fat_bytes         = 64,476 × 2                = 128,952
#   fat_sectors       = ceil(128,952 / 512)       = 252
#
# Win 3.1 uses a 1 GiB image with 32 spc to stay under the 65,525-cluster ceiling.
_ERA_PARAMS: dict[Era, tuple[int, int, int]] = {
    Era.DOS:   (504 * 1024 * 1024 // _SECTOR, 16, 252),  # 1,032,192 sectors, ~64,474 clusters
    Era.WIN31: (1024 * 1024 * 1024 // _SECTOR, 32, 256), # 2,097,152 sectors, ~65,518 clusters
}


def hdd_size_param(era: Era) -> str:
    """Return the DOSBox-X ``-size`` CLI argument for the HDD image geometry of the given era.

    DOSBox-X's ``imgmount -size`` flag takes the format
    ``-size bytes_per_sector,sectors_per_track,heads,cylinders``.  This
    function derives the cylinder count from ``total_sectors`` and returns
    the complete argument string so callers do not need to re-implement the
    geometry math.

    Args:
        era: The gaming era whose disk geometry to use.

    Returns:
        A string of the form ``"-size 512,63,255,<cylinders>"``.

    Raises:
        KeyError: If ``era`` has no entry in ``_ERA_PARAMS``.
    """
    total_sectors, _, _ = _ERA_PARAMS[era]
    cylinders = math.ceil(total_sectors / (63 * 255))
    return f"-size 512,63,255,{cylinders}"


def _chs(lba: int, heads: int = 255, spt: int = 63) -> bytes:
    """Convert an LBA address to a packed 3-byte CHS tuple for an MBR partition entry.

    The MBR partition table stores start/end addresses in CHS form.  Values
    are clamped to the CHS maximum (1023, 254, 63) for images larger than
    ~8 GiB — a standard BIOS compatibility convention.

    Args:
        lba: Logical block address to convert.
        heads: Heads per cylinder (default 255 — LBA-mode geometry).
        spt: Sectors per track (default 63 — LBA-mode geometry).

    Returns:
        3-byte sequence packed as ``(head, sector|cyl_hi, cyl_lo)`` per MBR spec.
    """
    cyl = lba // (heads * spt)
    head = (lba // spt) % heads
    sec = (lba % spt) + 1
    if cyl > 1023:
        cyl, head, sec = 1023, 254, 63
    return bytes([head, ((cyl >> 8) << 6) | sec, cyl & 0xFF])


def _mbr(total_sectors: int) -> bytes:
    """Build a 512-byte MBR with a single primary FAT16 partition covering the whole image.

    The MBR contains 446 bytes of blank bootstrap code, one 16-byte partition
    entry, 48 bytes of padding for the remaining three empty partition slots,
    and the 0x55AA boot signature.

    Partition entry ``struct`` format ``'<B3sB3sII'`` field mapping:
      B   — status: 0x80 = bootable
      3s  — CHS start address (3 bytes)
      B   — partition type: 0x06 = FAT16 ≥ 32 MB
      3s  — CHS end address (3 bytes)
      I   — LBA start sector (little-endian uint32)
      I   — partition size in sectors (little-endian uint32)

    Args:
        total_sectors: Total sector count of the image (MBR + all partitions).

    Returns:
        Exactly 512 bytes representing the MBR sector.
    """
    partition_sectors = total_sectors - _PARTITION_OFFSET
    entry = struct.pack(
        '<B3sB3sII',
        0x80,                       # status: bootable
        _chs(_PARTITION_OFFSET),    # CHS start of partition
        0x06,                       # type: FAT16 >= 32 MB
        _chs(total_sectors - 1),    # CHS end of partition
        _PARTITION_OFFSET,          # LBA start
        partition_sectors,          # partition size in sectors
    )
    return b'\x00' * 446 + entry + b'\x00' * 48 + b'\x55\xAA'


def _fat16_boot_sector(partition_sectors: int, spc: int, spf: int) -> bytes:
    """Build a 512-byte FAT16 BIOS Parameter Block (BPB) / boot sector.

    This is the first sector of the partition (LBA 63).  DOSBox-X reads the
    BPB to understand the filesystem geometry before mounting.

    ``struct`` format ``'<3s8sHBHBHHBHHHIIBBBI11s8s'`` field mapping:
      3s  — BS_JmpBoot:    jump instruction (EB 58 90)
      8s  — BS_OEMName:    OEM label (``"MSWIN4.1"`` for FAT16 compatibility)
      H   — BPB_BytsPerSec: bytes per sector (512)
      B   — BPB_SecPerClus: sectors per cluster (era-dependent)
      H   — BPB_RsvdSecCnt: reserved sectors before FAT1 (4)
      B   — BPB_NumFATs:   number of FAT copies (2)
      H   — BPB_RootEntCnt: max root directory entries (512)
      H   — BPB_TotSec16:  total sectors if ≤ 65535, else 0 (0 — we use TotSec32)
      B   — BPB_Media:     media descriptor byte (0xF8 = fixed disk)
      H   — BPB_FATSz16:   sectors per FAT copy (era-derived)
      H   — BPB_SecPerTrk: sectors per track (63)
      H   — BPB_NumHeads:  number of heads (255)
      I   — BPB_HiddSec:   hidden sectors before partition (``_PARTITION_OFFSET``)
      I   — BPB_TotSec32:  total sectors in partition (``partition_sectors``)
      B   — BS_DrvNum:     BIOS drive number (0x80 = first hard disk)
      B   — BS_Reserved1:  reserved (0)
      B   — BS_BootSig:    extended boot signature (0x29 = fields below are valid)
      I   — BS_VolID:      volume serial number (arbitrary)
      11s — BS_VolLab:     volume label (``"NO NAME    "``)
      8s  — BS_FilSysType: filesystem type string (``"FAT16   "``)

    Args:
        partition_sectors: Number of sectors in the partition.
        spc: Sectors per cluster (BPB_SecPerClus).
        spf: Sectors per FAT copy (BPB_FATSz16).

    Returns:
        Exactly 512 bytes with the BPB fields in the first ~90 bytes and
        0x55AA boot signature at bytes 510 to 511.
    """
    header = struct.pack(
        '<3s8sHBHBHHBHHHIIBBBI11s8s',
        b'\xeb\x58\x90',    # BS_JmpBoot
        b'MSWIN4.1',        # BS_OEMName
        _SECTOR,            # BPB_BytsPerSec
        spc,                # BPB_SecPerClus
        _RESERVED_SECTORS,  # BPB_RsvdSecCnt
        _NUM_FATS,          # BPB_NumFATs
        _ROOT_DIR_ENTRIES,  # BPB_RootEntCnt
        0,                  # BPB_TotSec16 (0 → use BPB_TotSec32 below)
        0xF8,               # BPB_Media: fixed disk
        spf,                # BPB_FATSz16
        63,                 # BPB_SecPerTrk
        255,                # BPB_NumHeads
        _PARTITION_OFFSET,  # BPB_HiddSec — sectors before partition
        partition_sectors,  # BPB_TotSec32 — sectors in partition only
        0x80,               # BS_DrvNum: first hard disk
        0,                  # BS_Reserved1
        0x29,               # BS_BootSig: extended signature present
        0x12345678,         # BS_VolID: arbitrary serial number
        b'NO NAME    ',     # BS_VolLab
        b'FAT16   ',        # BS_FilSysType
    )
    return header + b'\x00' * (510 - len(header)) + b'\x55\xAA'


def _fat16_table(spf: int) -> bytes:
    """Build one copy of the FAT16 allocation table with all clusters marked free.

    FAT[0] holds the media descriptor byte in its low byte (0xF8) with all
    remaining bits set to 1.  FAT[1] is the end-of-chain marker (0xFFFF).
    All other entries are 0x0000, indicating free clusters.

    Args:
        spf: Sectors per FAT (BPB_FATSz16); determines the table's byte length.

    Returns:
        Byte string of length ``spf * _SECTOR`` with FAT[0]/FAT[1] initialised
        and all other clusters free.
    """
    # FAT[0] = 0xFFF8 (media descriptor), FAT[1] = 0xFFFF (reserved EOF)
    # All remaining entries = 0x0000 (free cluster)
    return b'\xf8\xff\xff\xff' + b'\x00' * (spf * _SECTOR - 4)


def _create_raw_image(dest: Path, era: Era) -> None:
    """Write a complete FAT16-formatted disk image to ``dest``.

    Builds and writes every region of the image in order: MBR, MBR gap,
    partition boot sector, reserved sectors, two FAT copies, root directory,
    then seeks to the final byte to pre-allocate the full data region without
    writing every zeroed sector (sparse file).

    Args:
        dest: Destination path for the image file.
        era: Era whose geometry constants to use from ``_ERA_PARAMS``.

    Raises:
        RuntimeError: If the file cannot be created or written (wraps OSError).
    """
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
    """Return the path to the game's HDD image, creating it if it does not exist.

    Resolution order:
      1. Profile already has a valid ``hdd_image_path`` on disk — return it unchanged.
      2. Image exists at the expected location but is not recorded in the
         profile (e.g. profile was hand-edited) — adopt the file and update the profile.
      3. Neither — create a new FAT16 image, record the path in the profile, and save.

    The profile is saved to disk whenever ``hdd_image_path`` is updated so the
    path survives subsequent launches.

    Args:
        profile: The game profile requesting an HDD image.
        images_dir: Directory where ``.img`` files are stored.
        profiles_dir: Directory where profile ``.yaml`` files are saved.

    Returns:
        Absolute path to the ``.img`` file.

    Raises:
        ValueError: If the era is not supported for HDD image creation.
        RuntimeError: If the image file cannot be written.
    """
    if profile.era not in _ERA_PARAMS:
        raise ValueError(
            f"Era '{profile.era.value}' is not supported for HDD image creation. "
            f"Supported: {', '.join(e.value for e in _ERA_PARAMS)}"
        )

    # Reuse existing image — never overwrite
    if profile.hdd_image_path is not None and profile.hdd_image_path.exists():
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
