"""FAT16 entry I/O and cluster allocation."""

import struct

from backend.service.utils.fat.geometry import (
    _CLUSTER_FIRST,
    _FAT_EOC,
    _FAT_FREE,
    _fat1_byte_offset,
    _fat2_byte_offset,
    _fat_entry_byte_offset,
)


def _read_fat_entry(f, geo: dict, entry: int) -> int:
    f.seek(_fat_entry_byte_offset(_fat1_byte_offset(geo), entry))
    return struct.unpack("<H", f.read(2))[0]


def _write_fat_entry(f, geo: dict, entry: int, value: int) -> None:
    packed = struct.pack("<H", value)
    f.seek(_fat_entry_byte_offset(_fat1_byte_offset(geo), entry))
    f.write(packed)
    f.seek(_fat_entry_byte_offset(_fat2_byte_offset(geo), entry))
    f.write(packed)


def _find_free_cluster(f, geo: dict) -> int:
    max_cluster = _CLUSTER_FIRST + geo["data_clusters"]
    for cluster in range(_CLUSTER_FIRST, max_cluster):
        if _read_fat_entry(f, geo, cluster) == _FAT_FREE:
            return cluster
    raise RuntimeError("FAT image is full — no free clusters available")


def _alloc_clusters(f, geo: dict, count: int) -> list:
    clusters: list = []
    for _ in range(count):
        c = _find_free_cluster(f, geo)
        _write_fat_entry(f, geo, c, _FAT_EOC)
        clusters.append(c)

    for i in range(len(clusters) - 1):
        _write_fat_entry(f, geo, clusters[i], clusters[i + 1])

    return clusters
