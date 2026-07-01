"""FAT16 public API: format_fat16, write_file_to_image, read_file_from_image."""

import math
import struct
from pathlib import Path

from backend.service.utils.fat.boot_sector import _build_boot_sector
from backend.service.utils.fat.directory import (
    _find_in_dir,
    _find_free_dir_slot,
    _iter_dir_entries,
    _make_dir_entry,
    _read_cluster_chain,
    _to_83,
    _walk_path,
)
from backend.service.utils.fat.fat_table import _alloc_clusters
from backend.service.utils.fat.geometry import (
    FAT16_SIZE_MAX_MB,
    FAT16_SIZE_MIN_MB,
    _ATTR_DIR,
    _ATTR_FILE,
    _BYTES_PER_SECTOR,
    _FAT_EOC,
    _FAT_RESERVED,
    _HEAD_COUNT,
    _SECTORS_PER_TRACK,
    _calc_geometry,
    _cluster_byte_offset,
    _cluster_size_bytes,
    _fat1_byte_offset,
    _fat2_byte_offset,
    _read_geometry,
)


def format_fat16(img_path: Path, size_mb: int) -> None:
    """Create a blank FAT16 image file at img_path with a capacity of size_mb MiB."""
    if img_path.exists():
        raise RuntimeError(
            f"format_fat16: {img_path} already exists — refusing to overwrite"
        )
    if not (FAT16_SIZE_MIN_MB <= size_mb <= FAT16_SIZE_MAX_MB):
        _reason = (
            f"below minimum of {FAT16_SIZE_MIN_MB} MB"
            if size_mb < FAT16_SIZE_MIN_MB
            else f"exceeds maximum of {FAT16_SIZE_MAX_MB} MB"
        )
        raise RuntimeError(
            f"format_fat16: size_mb={size_mb} is {_reason} "
            f"(supported range: {FAT16_SIZE_MIN_MB}–{FAT16_SIZE_MAX_MB})"
        )

    geo = _calc_geometry(size_mb)

    # Size the image up to a whole CHS cylinder (63 * 255 sectors) so the file's
    # byte length exactly matches the cylinder-aligned geometry that
    # dosbox._build_c_drive_mount_line declares via `IMGMOUNT ... -t hdd -size`.
    # That call rounds the cylinder count UP from the BPB's total_sectors using
    # the same 63/255 values baked into the boot sector below, and DOSBox-X
    # refuses to mount a -t hdd image whose backing file is smaller than its
    # declared geometry ("Cannot create drive from file"). The BPB total_sectors
    # is left unchanged, so the FAT volume and its FAT16 cluster count are
    # unaffected — the result is a valid FAT volume on a slightly larger,
    # cylinder-aligned disk. Rounding total_sectors itself up would instead push
    # boundary sizes (e.g. 512 MB) past the FAT16 65,524-cluster limit.
    cylinder_sectors = _SECTORS_PER_TRACK * _HEAD_COUNT
    aligned_sectors  = math.ceil(geo["total_sectors"] / cylinder_sectors) * cylinder_sectors
    total_bytes      = aligned_sectors * _BYTES_PER_SECTOR

    with img_path.open("wb") as f:
        f.seek(total_bytes - 1)
        f.write(b"\x00")

    with img_path.open("r+b") as f:
        f.seek(0)
        f.write(_build_boot_sector(geo))

        fat1 = _fat1_byte_offset(geo)
        f.seek(fat1)
        f.write(struct.pack("<H", _FAT_EOC))
        f.write(struct.pack("<H", _FAT_RESERVED))

        fat2 = _fat2_byte_offset(geo)
        f.seek(fat2)
        f.write(struct.pack("<H", _FAT_EOC))
        f.write(struct.pack("<H", _FAT_RESERVED))


def write_file_to_image(img_path: Path, dest_path: str, data: bytes) -> None:
    """Write bytes into a FAT16 image at the path given by dest_path."""
    if not img_path.exists():
        raise RuntimeError(f"write_file_to_image: {img_path} does not exist")

    parts = [p for p in dest_path.replace("\\", "/").split("/") if p and p != "."]
    if not parts:
        raise RuntimeError(
            f"write_file_to_image: {img_path}: dest_path '{dest_path}' resolves to empty"
        )

    filename  = parts[-1]
    dir_parts = parts[:-1]

    try:
        name83, ext83 = _to_83(filename)
    except Exception as exc:
        raise RuntimeError(
            f"write_file_to_image: {img_path}: cannot convert '{filename}' to 8.3 — {exc}"
        ) from exc

    geo = _read_geometry(img_path)
    csz = _cluster_size_bytes(geo)

    with img_path.open("r+b") as f:
        try:
            dir_cluster = _walk_path(f, geo, dir_parts, create=True)
        except RuntimeError as exc:
            raise RuntimeError(f"write_file_to_image: {img_path}: {exc}") from exc

        if _find_in_dir(f, geo, dir_cluster, name83, ext83) is not None:
            raise RuntimeError(
                f"write_file_to_image: {img_path}: '{dest_path}' already exists in the image"
            )

        clusters_needed = max(1, math.ceil(len(data) / csz))
        try:
            clusters = _alloc_clusters(f, geo, clusters_needed)
        except RuntimeError as exc:
            raise RuntimeError(f"write_file_to_image: {img_path}: {exc}") from exc

        for i, cluster in enumerate(clusters):
            chunk = data[i * csz : (i + 1) * csz]
            chunk = chunk.ljust(csz, b"\x00")
            f.seek(_cluster_byte_offset(geo, cluster))
            f.write(chunk)

        try:
            slot_off = _find_free_dir_slot(f, geo, dir_cluster)
        except RuntimeError as exc:
            raise RuntimeError(f"write_file_to_image: {img_path}: {exc}") from exc

        f.seek(slot_off)
        f.write(_make_dir_entry(name83, ext83, _ATTR_FILE, clusters[0], len(data)))


def list_files_in_image(img_path: Path) -> list[tuple[str, bytes]]:
    """Recursively collect every regular file stored in a FAT16 image.

    Returns (path, data) pairs using "/" separators relative to the image
    root, in a form directly usable as write_file_to_image(dest, data)
    arguments. Used to migrate file contents when rebuilding an image at a
    different size, since FAT16 has no in-place resize.
    """
    if not img_path.exists():
        raise RuntimeError(f"list_files_in_image: {img_path} does not exist")

    geo = _read_geometry(img_path)
    results: list[tuple[str, bytes]] = []

    def _walk(f, dir_cluster, prefix: str) -> None:
        for _, entry in _iter_dir_entries(f, geo, dir_cluster):
            name = entry["name83"].decode("ascii").rstrip()
            ext = entry["ext83"].decode("ascii").rstrip()
            if name in (".", ".."):
                continue
            filename = f"{name}.{ext}" if ext else name
            path = f"{prefix}{filename}"
            if entry["attr"] & _ATTR_DIR:
                child_cluster = entry["first_cluster"] if entry["first_cluster"] != 0 else None
                _walk(f, child_cluster, f"{path}/")
            else:
                data = (
                    _read_cluster_chain(f, geo, entry["first_cluster"])
                    if entry["first_cluster"] != 0
                    else b""
                )
                results.append((path, data[: entry["file_size"]]))

    with img_path.open("rb") as f:
        _walk(f, None, "")

    return results


def read_file_from_image(img_path: Path, dest_path: str) -> bytes:
    """Read and return the raw bytes of a file stored in a FAT16 image."""
    if not img_path.exists():
        raise RuntimeError(f"read_file_from_image: {img_path} does not exist")

    parts = [p for p in dest_path.replace("\\", "/").split("/") if p and p != "."]
    if not parts:
        raise RuntimeError(
            f"read_file_from_image: {img_path}: dest_path '{dest_path}' resolves to empty"
        )

    filename  = parts[-1]
    dir_parts = parts[:-1]
    name83, ext83 = _to_83(filename)

    geo = _read_geometry(img_path)

    with img_path.open("rb") as f:
        dir_cluster = _walk_path(f, geo, dir_parts, create=False)
        if dir_cluster is None and dir_parts:
            raise RuntimeError(
                f"read_file_from_image: {img_path}: directory not found: "
                f"'{'/'.join(dir_parts)}'"
            )

        entry = _find_in_dir(f, geo, dir_cluster, name83, ext83)
        if entry is None:
            raise RuntimeError(
                f"read_file_from_image: {img_path}: file not found: '{dest_path}'"
            )

        if entry["attr"] & _ATTR_DIR:
            raise RuntimeError(
                f"read_file_from_image: {img_path}: '{dest_path}' is a directory, not a file"
            )

        if entry["first_cluster"] == 0:
            return b""

        try:
            raw = _read_cluster_chain(f, geo, entry["first_cluster"])
        except RuntimeError as exc:
            raise RuntimeError(f"read_file_from_image: {img_path}: {exc}") from exc

    return raw[: entry["file_size"]]
