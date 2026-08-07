"""FAT16 directory entry encoding/decoding and traversal."""

import struct

from backend.service.utils.fat.geometry import (
    _ATTR_DIR,
    _CLUSTER_FIRST,
    _DIR_ENTRY_SIZE,
    _ROOT_ENTRY_COUNT,
    _cluster_byte_offset,
    _cluster_size_bytes,
    _root_dir_byte_offset,
)
from backend.service.utils.fat.fat_table import _alloc_clusters, _read_fat_entry


def _to_83(name: str) -> tuple:
    name = name.upper()
    if "." in name:
        base, _, ext = name.rpartition(".")
    else:
        base, ext = name, ""
    name_bytes = base[:8].encode("ascii").ljust(8, b" ")
    ext_bytes  = ext[:3].encode("ascii").ljust(3, b" ")
    return name_bytes, ext_bytes


def _to_83_str(component: str) -> str:
    """Return the 8.3 on-image name for a single filename component (uppercase).

    Raises ValueError if the component cannot be represented losslessly:
    base name > 8 chars, extension > 3 chars, or non-ASCII characters.
    """
    upper = component.upper()
    if "." in upper:
        base, _, ext = upper.rpartition(".")
    else:
        base, ext = upper, ""
    try:
        base.encode("ascii")
        ext.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"'{component}' contains non-ASCII characters") from exc
    if len(base) > 8:
        raise ValueError(f"'{component}': base name '{base}' exceeds 8 characters")
    if len(ext) > 3:
        raise ValueError(f"'{component}': extension '{ext}' exceeds 3 characters")
    return f"{base}.{ext}" if ext else base


def _make_dir_entry(name83: bytes, ext83: bytes, attr: int, first_cluster: int, file_size: int) -> bytes:
    entry = bytearray(32)
    entry[0:8]  = name83
    entry[8:11] = ext83
    entry[11]   = attr
    struct.pack_into("<H", entry, 26, first_cluster)
    struct.pack_into("<I", entry, 28, file_size)
    return bytes(entry)


def _parse_dir_entry(raw: bytes) -> dict | None:
    if raw[0] in (0x00, 0xE5):
        return None
    if raw[11] == 0x0F:
        return None
    return {
        "name83":        raw[0:8],
        "ext83":         raw[8:11],
        "attr":          raw[11],
        "first_cluster": struct.unpack_from("<H", raw, 26)[0],
        "file_size":     struct.unpack_from("<I", raw, 28)[0],
    }


def _iter_dir_entries(f, geo: dict, dir_cluster):
    if dir_cluster is None:
        base = _root_dir_byte_offset(geo)
        for i in range(_ROOT_ENTRY_COUNT):
            off = base + i * _DIR_ENTRY_SIZE
            f.seek(off)
            entry = _parse_dir_entry(f.read(_DIR_ENTRY_SIZE))
            if entry is not None:
                yield off, entry
    else:
        cluster     = dir_cluster
        csz         = _cluster_size_bytes(geo)
        epc         = csz // _DIR_ENTRY_SIZE
        max_cluster = _CLUSTER_FIRST + geo["data_clusters"]
        seen: set   = set()
        while cluster < 0xFFF8:
            if cluster in seen:
                raise RuntimeError(f"corrupt FAT: cluster chain loops at cluster {cluster}")
            if cluster < _CLUSTER_FIRST or cluster >= max_cluster:
                raise RuntimeError(f"corrupt FAT: cluster {cluster} is out of valid range")
            seen.add(cluster)
            base = _cluster_byte_offset(geo, cluster)
            for i in range(epc):
                off = base + i * _DIR_ENTRY_SIZE
                f.seek(off)
                entry = _parse_dir_entry(f.read(_DIR_ENTRY_SIZE))
                if entry is not None:
                    yield off, entry
            cluster = _read_fat_entry(f, geo, cluster)


def _find_in_dir(f, geo: dict, dir_cluster, name83: bytes, ext83: bytes) -> dict | None:
    for _, entry in _iter_dir_entries(f, geo, dir_cluster):
        if entry["name83"] == name83 and entry["ext83"] == ext83:
            return entry
    return None


def _find_free_dir_slot(f, geo: dict, dir_cluster) -> int:
    if dir_cluster is None:
        base = _root_dir_byte_offset(geo)
        for i in range(_ROOT_ENTRY_COUNT):
            off = base + i * _DIR_ENTRY_SIZE
            f.seek(off)
            if f.read(1)[0] in (0x00, 0xE5):
                return off
        raise RuntimeError("root directory is full (512 entries used)")
    else:
        cluster     = dir_cluster
        csz         = _cluster_size_bytes(geo)
        epc         = csz // _DIR_ENTRY_SIZE
        max_cluster = _CLUSTER_FIRST + geo["data_clusters"]
        seen: set   = set()
        while cluster < 0xFFF8:
            if cluster in seen:
                raise RuntimeError(f"corrupt FAT: cluster chain loops at cluster {cluster}")
            if cluster < _CLUSTER_FIRST or cluster >= max_cluster:
                raise RuntimeError(f"corrupt FAT: cluster {cluster} is out of valid range")
            seen.add(cluster)
            base = _cluster_byte_offset(geo, cluster)
            for i in range(epc):
                off = base + i * _DIR_ENTRY_SIZE
                f.seek(off)
                if f.read(1)[0] in (0x00, 0xE5):
                    return off
            cluster = _read_fat_entry(f, geo, cluster)
        raise RuntimeError("subdirectory is full, cluster chain exhausted")


def _create_subdir(f, geo: dict, parent_cluster, name83: bytes, ext83: bytes) -> int:
    clusters    = _alloc_clusters(f, geo, 1)
    new_cluster = clusters[0]

    f.seek(_cluster_byte_offset(geo, new_cluster))
    f.write(b"\x00" * _cluster_size_bytes(geo))

    dot_entry    = _make_dir_entry(b".       ", b"   ", _ATTR_DIR, new_cluster, 0)
    dotdot_cluster = parent_cluster if parent_cluster is not None else 0
    dotdot_entry   = _make_dir_entry(b"..      ", b"   ", _ATTR_DIR, dotdot_cluster, 0)

    f.seek(_cluster_byte_offset(geo, new_cluster))
    f.write(dot_entry)
    f.write(dotdot_entry)

    slot_off = _find_free_dir_slot(f, geo, parent_cluster)
    f.seek(slot_off)
    f.write(_make_dir_entry(name83, ext83, _ATTR_DIR, new_cluster, 0))

    return new_cluster


def _walk_path(f, geo: dict, parts: list, create: bool = False):
    cluster = None
    for part in parts:
        name83, ext83 = _to_83(part)
        entry = _find_in_dir(f, geo, cluster, name83, ext83)
        if entry is None:
            if not create:
                return None
            cluster = _create_subdir(f, geo, cluster, name83, ext83)
        else:
            if entry["attr"] & _ATTR_DIR == 0:
                raise RuntimeError(f"path component '{part}' exists but is not a directory")
            cluster = entry["first_cluster"] if entry["first_cluster"] != 0 else None
    return cluster


def _read_cluster_chain(f, geo: dict, first_cluster: int) -> bytes:
    csz         = _cluster_size_bytes(geo)
    max_cluster = _CLUSTER_FIRST + geo["data_clusters"]
    chunks: list = []
    cluster      = first_cluster
    seen: set    = set()

    while cluster < 0xFFF8:
        if cluster in seen:
            raise RuntimeError(f"corrupt FAT: cluster chain loops at cluster {cluster}")
        if cluster < _CLUSTER_FIRST or cluster >= max_cluster:
            raise RuntimeError(f"corrupt FAT: cluster {cluster} is out of valid range")
        seen.add(cluster)
        f.seek(_cluster_byte_offset(geo, cluster))
        chunks.append(f.read(csz))
        cluster = _read_fat_entry(f, geo, cluster)

    return b"".join(chunks)
