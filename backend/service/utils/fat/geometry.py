"""
FAT16 geometry helpers and all module-level constants.
"""

import math
import struct
from pathlib import Path

FAT16_SIZE_MIN_MB  = 10
FAT16_SIZE_MAX_MB  = 1024

_BYTES_PER_SECTOR  = 512
_RESERVED_SECTORS  = 4
_FAT_COUNT         = 2
_ROOT_ENTRY_COUNT  = 512
_ROOT_DIR_SECTORS  = _ROOT_ENTRY_COUNT * 32 // _BYTES_PER_SECTOR  # always 32
_SECTORS_PER_TRACK = 63
_HEAD_COUNT        = 255

_FAT_FREE     = 0x0000
_FAT_EOC      = 0xFFF8
_FAT_RESERVED = 0xFFFF

_ATTR_FILE = 0x20
_ATTR_DIR  = 0x10

_DIR_ENTRY_SIZE = 32
_CLUSTER_FIRST  = 2


def _sectors_per_cluster(size_mb: int) -> int:
    """Choose the cluster size that keeps the FAT16 cluster count below 65524."""
    if size_mb <= 128:
        return 4
    if size_mb <= 256:
        return 8
    if size_mb <= 512:
        return 16
    return 32  # supports up to 2 GB


def _calc_geometry(size_mb: int) -> dict:
    """Derive all FAT16 layout parameters from the image size in megabytes.

    sectors_per_fat is computed iteratively because it depends on data_clusters
    and data_clusters depends on it.  Convergence always happens in ≤ 3 passes.
    """
    total_sectors = (size_mb * 1024 * 1024) // _BYTES_PER_SECTOR
    spc = _sectors_per_cluster(size_mb)

    spf = 1
    data_start = data_clusters = 0
    for _ in range(10):
        data_start    = _RESERVED_SECTORS + _FAT_COUNT * spf + _ROOT_DIR_SECTORS
        data_clusters = (total_sectors - data_start) // spc
        new_spf       = math.ceil((data_clusters + _CLUSTER_FIRST) * 2 / _BYTES_PER_SECTOR)
        if new_spf == spf:
            break
        spf = new_spf

    return {
        "total_sectors":       total_sectors,
        "sectors_per_cluster": spc,
        "sectors_per_fat":     spf,
        "data_start":          data_start,
        "data_clusters":       data_clusters,
    }


def _read_geometry(img_path: Path) -> dict:
    """Parse the BPB from an existing FAT16 image and return the same dict shape
    as _calc_geometry so the rest of the module can work with either.
    """
    with img_path.open("rb") as f:
        bpb = f.read(512)

    if bpb[510:512] != b"\x55\xAA":
        raise RuntimeError(f"{img_path}: missing FAT boot signature at offset 510")

    bytes_per_sector = struct.unpack_from("<H", bpb, 11)[0]
    spc              = bpb[13]
    reserved         = struct.unpack_from("<H", bpb, 14)[0]
    fat_count        = bpb[16]
    root_entry_count = struct.unpack_from("<H", bpb, 17)[0]
    total_sec_16     = struct.unpack_from("<H", bpb, 19)[0]
    spf              = struct.unpack_from("<H", bpb, 22)[0]
    total_sec_32     = struct.unpack_from("<I", bpb, 32)[0]

    total_sectors    = total_sec_16 if total_sec_16 else total_sec_32
    root_dir_sectors = root_entry_count * 32 // bytes_per_sector
    data_start       = reserved + fat_count * spf + root_dir_sectors
    data_clusters    = (total_sectors - data_start) // spc

    return {
        "total_sectors":       total_sectors,
        "sectors_per_cluster": spc,
        "sectors_per_fat":     spf,
        "data_start":          data_start,
        "data_clusters":       data_clusters,
    }


def _fat1_byte_offset(geo: dict) -> int:
    return _RESERVED_SECTORS * _BYTES_PER_SECTOR


def _fat2_byte_offset(geo: dict) -> int:
    return (_RESERVED_SECTORS + geo["sectors_per_fat"]) * _BYTES_PER_SECTOR


def _fat_entry_byte_offset(fat_base: int, entry: int) -> int:
    return fat_base + entry * 2


def _root_dir_byte_offset(geo: dict) -> int:
    return (_RESERVED_SECTORS + _FAT_COUNT * geo["sectors_per_fat"]) * _BYTES_PER_SECTOR


def _cluster_byte_offset(geo: dict, cluster: int) -> int:
    sector = geo["data_start"] + (cluster - _CLUSTER_FIRST) * geo["sectors_per_cluster"]
    return sector * _BYTES_PER_SECTOR


def _cluster_size_bytes(geo: dict) -> int:
    return geo["sectors_per_cluster"] * _BYTES_PER_SECTOR
