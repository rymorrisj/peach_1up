"""
Minimal FAT16 raw image writer — no third-party dependencies.

Image layout
------------
  Sector 0               Boot Sector (BPB, 512 bytes)
  Sectors 1 .. R-1       Reserved padding  (R = 4)
  Sectors R .. R+S-1     FAT copy 1        (S = sectors_per_fat)
  Sectors R+S .. R+2S-1  FAT copy 2        (identical to copy 1)
  Sectors R+2S .. +31    Root directory    (512 entries × 32 bytes = 32 sectors)
  Sectors R+2S+32 ..     Data area         (clusters 2, 3, …)

All multi-byte integers are little-endian throughout (x86 native byte order).
"""

import math
import struct
from pathlib import Path

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

FAT16_SIZE_MIN_MB  = 10
FAT16_SIZE_MAX_MB  = 1024

_BYTES_PER_SECTOR  = 512
_RESERVED_SECTORS  = 4
_FAT_COUNT         = 2
_ROOT_ENTRY_COUNT  = 512
_ROOT_DIR_SECTORS  = _ROOT_ENTRY_COUNT * 32 // _BYTES_PER_SECTOR  # always 32
_SECTORS_PER_TRACK = 63
_HEAD_COUNT        = 255

# Special FAT16 entry values.
_FAT_FREE     = 0x0000  # cluster is available for allocation
_FAT_EOC      = 0xFFF8  # end-of-chain marker (last cluster of a file)
_FAT_RESERVED = 0xFFFF  # entries 0 and 1 are permanently reserved

# FAT16 directory entry attributes.
_ATTR_FILE = 0x20
_ATTR_DIR  = 0x10

_DIR_ENTRY_SIZE = 32   # bytes per directory entry (fixed by FAT spec)
_CLUSTER_FIRST  = 2    # FAT16 data clusters are numbered starting from 2

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

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

    # Bootstrap with a minimal estimate and iterate to a fixed point.
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
        "data_start":          data_start,    # first sector of the data area
        "data_clusters":       data_clusters,
    }


def _read_geometry(img_path: Path) -> dict:
    """Parse the BPB from an existing FAT16 image and return the same dict shape
    as _calc_geometry so the rest of the module can work with either.
    """
    with img_path.open("rb") as f:
        bpb = f.read(512)

    # Offset 510–511: mandatory FAT/MBR boot signature.
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


# ---------------------------------------------------------------------------
# Byte-offset calculators
# ---------------------------------------------------------------------------

def _fat1_byte_offset(geo: dict) -> int:
    """FAT copy 1 begins immediately after the reserved sectors."""
    return _RESERVED_SECTORS * _BYTES_PER_SECTOR


def _fat2_byte_offset(geo: dict) -> int:
    """FAT copy 2 begins immediately after FAT copy 1."""
    return (_RESERVED_SECTORS + geo["sectors_per_fat"]) * _BYTES_PER_SECTOR


def _fat_entry_byte_offset(fat_base: int, entry: int) -> int:
    """Byte offset of a single FAT16 entry within the image.

    Each FAT16 entry is exactly 2 bytes, so entry N lives at fat_base + N*2.
    fat_base is the absolute byte offset of the FAT copy (FAT1 or FAT2).
    """
    return fat_base + entry * 2


def _root_dir_byte_offset(geo: dict) -> int:
    """Root directory begins immediately after both FAT copies.

    Byte offset = (reserved + fat_count * sectors_per_fat) * bytes_per_sector.
    """
    return (_RESERVED_SECTORS + _FAT_COUNT * geo["sectors_per_fat"]) * _BYTES_PER_SECTOR


def _cluster_byte_offset(geo: dict, cluster: int) -> int:
    """Absolute byte offset of the first byte of a data cluster.

    Clusters are numbered from 2 (clusters 0 and 1 are reserved entries in
    the FAT, not real storage).  The mapping is:
        sector = data_start + (cluster - 2) * sectors_per_cluster
        byte   = sector * 512
    """
    sector = geo["data_start"] + (cluster - _CLUSTER_FIRST) * geo["sectors_per_cluster"]
    return sector * _BYTES_PER_SECTOR


def _cluster_size_bytes(geo: dict) -> int:
    return geo["sectors_per_cluster"] * _BYTES_PER_SECTOR


# ---------------------------------------------------------------------------
# FAT entry I/O
# ---------------------------------------------------------------------------

def _read_fat_entry(f, geo: dict, entry: int) -> int:
    """Read a 16-bit FAT entry from FAT copy 1 (the authoritative copy)."""
    f.seek(_fat_entry_byte_offset(_fat1_byte_offset(geo), entry))
    return struct.unpack("<H", f.read(2))[0]


def _write_fat_entry(f, geo: dict, entry: int, value: int) -> None:
    """Write a 16-bit FAT entry to both FAT copies atomically (within the OS write).

    FAT16 mandates two identical copies so that one can be recovered if the
    other is corrupted by a crash mid-write.
    """
    packed = struct.pack("<H", value)
    f.seek(_fat_entry_byte_offset(_fat1_byte_offset(geo), entry))
    f.write(packed)
    f.seek(_fat_entry_byte_offset(_fat2_byte_offset(geo), entry))
    f.write(packed)


# ---------------------------------------------------------------------------
# Cluster allocation
# ---------------------------------------------------------------------------

def _find_free_cluster(f, geo: dict) -> int:
    """Scan FAT1 linearly for the lowest-numbered free cluster (entry == 0x0000).

    The scan starts at cluster 2 because 0 and 1 are permanently reserved.
    Raises RuntimeError if the image is completely full.
    """
    max_cluster = _CLUSTER_FIRST + geo["data_clusters"]
    for cluster in range(_CLUSTER_FIRST, max_cluster):
        if _read_fat_entry(f, geo, cluster) == _FAT_FREE:
            return cluster
    raise RuntimeError("FAT image is full — no free clusters available")


def _alloc_clusters(f, geo: dict, count: int) -> list:
    """Allocate exactly `count` free clusters and link them as a FAT chain.

    Each cluster is immediately marked 0xFFF8 (end-of-chain) after discovery
    so that the next _find_free_cluster call skips over it.  After all clusters
    are found the chain is rewritten: cluster[i] → cluster[i+1], with the last
    one keeping its end-of-chain marker.  Both FAT copies are updated for every
    write.

    Returns the ordered list of allocated cluster numbers.
    """
    clusters: list = []
    for _ in range(count):
        c = _find_free_cluster(f, geo)
        _write_fat_entry(f, geo, c, _FAT_EOC)  # reserve immediately
        clusters.append(c)

    # Rewrite interior links (last entry already holds EOC from the loop above).
    for i in range(len(clusters) - 1):
        _write_fat_entry(f, geo, clusters[i], clusters[i + 1])

    return clusters


# ---------------------------------------------------------------------------
# Directory entry encoding / decoding
# ---------------------------------------------------------------------------

def _to_83(name: str) -> tuple:
    """Convert a filename string to FAT 8.3 components (name_bytes, ext_bytes).

    Both components are uppercased, ASCII-encoded, and space-padded to exactly
    8 and 3 bytes respectively.  The extension is everything after the last dot;
    if there is no dot the extension is empty.
    """
    name = name.upper()
    if "." in name:
        base, _, ext = name.rpartition(".")
    else:
        base, ext = name, ""
    name_bytes = base[:8].encode("ascii").ljust(8, b" ")
    ext_bytes  = ext[:3].encode("ascii").ljust(3, b" ")
    return name_bytes, ext_bytes


def _make_dir_entry(name83: bytes, ext83: bytes, attr: int, first_cluster: int, file_size: int) -> bytes:
    """Pack a 32-byte FAT directory entry.

    Directory entry layout (offsets relative to start of the 32-byte record):
      0– 7   filename, 8 bytes, space-padded, uppercase
      8–10   extension, 3 bytes, space-padded, uppercase
      11     attribute byte  (0x20 = normal file, 0x10 = directory)
     12–21   reserved / NT flags / creation timestamps — all zeroed
     22–23   last-modified time (zeroed; 00:00:00 is valid)
     24–25   last-modified date (zeroed; 1980-01-01 is valid)
     26–27   first cluster number, low 16-bit word (FAT16 uses only this word)
     28–31   file size in bytes (must be 0 for directories)
    """
    entry = bytearray(32)
    entry[0:8]  = name83
    entry[8:11] = ext83
    entry[11]   = attr
    # bytes 12–25: reserved and timestamp fields — leave as zero
    struct.pack_into("<H", entry, 26, first_cluster)
    struct.pack_into("<I", entry, 28, file_size)
    return bytes(entry)


def _parse_dir_entry(raw: bytes) -> dict | None:
    """Parse a 32-byte directory record.

    Returns None when the slot is free (first byte 0x00 = never used,
    0xE5 = deleted) or when it holds a long-filename (LFN) continuation
    entry (attr == 0x0F).  We write only 8.3 entries so LFN slots are skipped.
    """
    if raw[0] in (0x00, 0xE5):
        return None
    if raw[11] == 0x0F:  # LFN attribute combination — skip
        return None
    return {
        "name83":        raw[0:8],
        "ext83":         raw[8:11],
        "attr":          raw[11],
        "first_cluster": struct.unpack_from("<H", raw, 26)[0],
        "file_size":     struct.unpack_from("<I", raw, 28)[0],
    }


# ---------------------------------------------------------------------------
# Directory traversal
# ---------------------------------------------------------------------------

def _iter_dir_entries(f, geo: dict, dir_cluster):
    """Yield (byte_offset, entry_dict) for every non-free entry in a directory.

    dir_cluster=None means the root directory, which occupies a fixed region
    (_ROOT_ENTRY_COUNT entries) rather than cluster-based storage.
    For subdirectories, the FAT cluster chain is followed until end-of-chain.
    """
    if dir_cluster is None:
        # Root directory: fixed-size region, not stored in the data area.
        base = _root_dir_byte_offset(geo)
        for i in range(_ROOT_ENTRY_COUNT):
            off = base + i * _DIR_ENTRY_SIZE
            f.seek(off)
            entry = _parse_dir_entry(f.read(_DIR_ENTRY_SIZE))
            if entry is not None:
                yield off, entry
    else:
        cluster   = dir_cluster
        csz       = _cluster_size_bytes(geo)
        epc       = csz // _DIR_ENTRY_SIZE  # entries per cluster
        while cluster < 0xFFF8:
            base = _cluster_byte_offset(geo, cluster)
            for i in range(epc):
                off = base + i * _DIR_ENTRY_SIZE
                f.seek(off)
                entry = _parse_dir_entry(f.read(_DIR_ENTRY_SIZE))
                if entry is not None:
                    yield off, entry
            cluster = _read_fat_entry(f, geo, cluster)


def _find_in_dir(f, geo: dict, dir_cluster, name83: bytes, ext83: bytes) -> dict | None:
    """Search a directory for a matching 8.3 name+extension pair.

    Returns the parsed entry dict, or None if not found.
    """
    for _, entry in _iter_dir_entries(f, geo, dir_cluster):
        if entry["name83"] == name83 and entry["ext83"] == ext83:
            return entry
    return None


def _find_free_dir_slot(f, geo: dict, dir_cluster) -> int:
    """Return the byte offset of the first free directory slot (first byte 0x00 or 0xE5).

    Raises RuntimeError if the directory has no available slots.
    """
    if dir_cluster is None:
        base = _root_dir_byte_offset(geo)
        for i in range(_ROOT_ENTRY_COUNT):
            off = base + i * _DIR_ENTRY_SIZE
            f.seek(off)
            if f.read(1)[0] in (0x00, 0xE5):
                return off
        raise RuntimeError("root directory is full (512 entries used)")
    else:
        cluster = dir_cluster
        csz     = _cluster_size_bytes(geo)
        epc     = csz // _DIR_ENTRY_SIZE
        while cluster < 0xFFF8:
            base = _cluster_byte_offset(geo, cluster)
            for i in range(epc):
                off = base + i * _DIR_ENTRY_SIZE
                f.seek(off)
                if f.read(1)[0] in (0x00, 0xE5):
                    return off
            cluster = _read_fat_entry(f, geo, cluster)
        raise RuntimeError("subdirectory is full — cluster chain exhausted")


def _create_subdir(f, geo: dict, parent_cluster, name83: bytes, ext83: bytes) -> int:
    """Create a new subdirectory inside parent_cluster (None = root).

    Allocates one cluster, zero-fills it, writes '.' and '..' entries, then
    writes the directory entry in the parent.  Returns the new directory's
    first cluster.
    """
    clusters    = _alloc_clusters(f, geo, 1)
    new_cluster = clusters[0]

    # Zero-fill the cluster so stale data does not appear as valid entries.
    f.seek(_cluster_byte_offset(geo, new_cluster))
    f.write(b"\x00" * _cluster_size_bytes(geo))

    # '.' points to this directory itself.
    dot_entry = _make_dir_entry(b".       ", b"   ", _ATTR_DIR, new_cluster, 0)

    # '..' points to the parent; cluster 0 is the conventional encoding for root.
    dotdot_cluster = parent_cluster if parent_cluster is not None else 0
    dotdot_entry   = _make_dir_entry(b"..      ", b"   ", _ATTR_DIR, dotdot_cluster, 0)

    f.seek(_cluster_byte_offset(geo, new_cluster))
    f.write(dot_entry)
    f.write(dotdot_entry)

    # Add the entry for this directory in the parent.
    slot_off = _find_free_dir_slot(f, geo, parent_cluster)
    f.seek(slot_off)
    f.write(_make_dir_entry(name83, ext83, _ATTR_DIR, new_cluster, 0))

    return new_cluster


def _walk_path(f, geo: dict, parts: list, create: bool = False):
    """Walk a list of directory name components starting from the root.

    Returns the first cluster of the deepest directory reached (None = root).
    When create=True, missing intermediate directories are created on the fly.
    When create=False, returns None immediately if any component is missing.
    """
    cluster = None  # None is the sentinel for "root directory"
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
            # Cluster 0 in a '..' entry means root; normalise to None.
            cluster = entry["first_cluster"] if entry["first_cluster"] != 0 else None
    return cluster


def _read_cluster_chain(f, geo: dict, first_cluster: int) -> bytes:
    """Follow the FAT chain from first_cluster and concatenate all cluster data.

    Halts when the FAT entry is >= 0xFFF8 (any end-of-chain value).
    Raises RuntimeError if the chain loops or references an out-of-range cluster.
    """
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


# ---------------------------------------------------------------------------
# Boot sector builder
# ---------------------------------------------------------------------------

def _build_boot_sector(geo: dict) -> bytes:
    """Assemble the 512-byte BIOS Parameter Block / boot sector.

    All multi-byte fields are little-endian.  Field-by-field offset map:

      Offset  Size  Content
      ------  ----  -------
       0       3    EB 58 90 — x86 short-jump + NOP.  Required by many BPB
                              parsers (they jump over the BPB to the boot code).
       3       8    OEM identifier string.
      11       2    Bytes per sector (always 512 for FAT16).
      13       1    Sectors per cluster (power of 2, 4–32 for our images).
      14       2    Reserved sector count (4 — sector 0 is BPB + 3 padding).
      16       1    FAT copy count (always 2).
      17       2    Root directory entry count (512).
      19       2    Total sector count, 16-bit.  Set to 0 when > 65535.
      21       1    Media descriptor: 0xF8 = fixed (non-removable) disk.
      22       2    Sectors per FAT copy (computed iteratively).
      24       2    Sectors per track — CHS geometry hint for legacy BIOSes.
      26       2    Head count       — CHS geometry hint.
      28       4    Hidden sectors before this partition (0 = whole-disk image).
      32       4    Total sector count, 32-bit.  Non-zero only when 16-bit is 0.
      36       1    BIOS drive number: 0x80 = first hard disk.
      37       1    Reserved byte (must be 0x00).
      38       1    Extended boot signature 0x29 — signals that volume ID,
                              volume label, and filesystem type fields are valid.
      39       4    Volume serial number (arbitrary; we use ASCII "PEAC").
      43      11    Volume label, space-padded.
      54       8    Filesystem type string (informational only, not enforced).
     510       2    Boot sector signature 0x55 0xAA — required by all FAT
                              implementations to confirm a valid BPB/MBR sector.
    """
    sector = bytearray(512)
    ts     = geo["total_sectors"]

    sector[0:3]  = b"\xEB\x58\x90"   # offset 0: x86 short jump + NOP
    sector[3:11] = b"PEACH1UP"       # offset 3: OEM name

    struct.pack_into("<H", sector, 11, _BYTES_PER_SECTOR)           # offset 11
    sector[13] = geo["sectors_per_cluster"]                          # offset 13
    struct.pack_into("<H", sector, 14, _RESERVED_SECTORS)           # offset 14
    sector[16] = _FAT_COUNT                                          # offset 16
    struct.pack_into("<H", sector, 17, _ROOT_ENTRY_COUNT)           # offset 17

    # Offset 19: total sectors 16-bit; 0 when the image is larger than 32 MB.
    struct.pack_into("<H", sector, 19, ts if ts <= 0xFFFF else 0)   # offset 19

    sector[21] = 0xF8  # offset 21: media descriptor — fixed disk              # offset 21

    struct.pack_into("<H", sector, 22, geo["sectors_per_fat"])      # offset 22
    struct.pack_into("<H", sector, 24, _SECTORS_PER_TRACK)          # offset 24
    struct.pack_into("<H", sector, 26, _HEAD_COUNT)                 # offset 26
    struct.pack_into("<I", sector, 28, 0)                           # offset 28: hidden sectors

    # Offset 32: total sectors 32-bit; non-zero only when the 16-bit field is 0.
    struct.pack_into("<I", sector, 32, ts if ts > 0xFFFF else 0)    # offset 32

    sector[36] = 0x80  # BIOS drive number: 0x80 = first fixed disk            # offset 36
    sector[37] = 0x00  # reserved                                               # offset 37
    sector[38] = 0x29  # extended boot signature — volume ID / label valid      # offset 38

    # Offset 39: volume serial number — arbitrary 4-byte tag.
    struct.pack_into("<I", sector, 39, 0x50454143)                  # offset 39: "PEAC"

    sector[43:54] = b"PEACH1UP   "   # offset 43: volume label (11 bytes)
    sector[54:62] = b"FAT16   "      # offset 54: filesystem type (8 bytes)

    # Offset 510–511: mandatory signature that marks this as a valid boot sector.
    sector[510] = 0x55                                               # offset 510
    sector[511] = 0xAA                                               # offset 511

    return bytes(sector)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def format_fat16(img_path: Path, size_mb: int) -> None:
    """Create a blank FAT16 image file at img_path with a capacity of size_mb MiB.

    The file is created as a sparse file (seek to end, write one null byte) so
    that the full image size is not allocated in heap. The boot sector and both
    FAT copies are then written into the sparse file. All unwritten regions read
    back as zeros, which FAT16 interprets as free clusters and end-of-directory
    markers.

    Raises:
        RuntimeError: If img_path already exists or size_mb is outside the supported range 10–1024.
    """
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

    geo         = _calc_geometry(size_mb)
    total_bytes = size_mb * 1024 * 1024

    # Create a sparse file: seek to the last byte and write one null byte.
    # Unwritten regions read back as zeros — free clusters and end-of-directory
    # markers — without allocating the full image in heap.
    with img_path.open("wb") as f:
        f.seek(total_bytes - 1)
        f.write(b"\x00")

    with img_path.open("r+b") as f:
        # Boot sector at byte 0 (sector 0).
        f.seek(0)
        f.write(_build_boot_sector(geo))

        # FAT copy 1: entries 0 and 1 are always reserved.
        # Entry 0 conventionally mirrors the media descriptor in the high byte
        # (0xFFF8 for a fixed disk).  Entry 1 is end-of-chain for the reserved slot.
        fat1 = _fat1_byte_offset(geo)
        f.seek(fat1)
        f.write(struct.pack("<H", _FAT_EOC))       # entry 0: media descriptor marker
        f.write(struct.pack("<H", _FAT_RESERVED))  # entry 1: reserved

        # FAT copy 2: bit-for-bit identical to copy 1.
        fat2 = _fat2_byte_offset(geo)
        f.seek(fat2)
        f.write(struct.pack("<H", _FAT_EOC))
        f.write(struct.pack("<H", _FAT_RESERVED))


def write_file_to_image(img_path: Path, dest_path: str, data: bytes) -> None:
    """Write bytes into a FAT16 image at the path given by dest_path.

    dest_path is a POSIX-style path relative to the image root, e.g.
    "GAMES/DOOM/DOOM.EXE".  All path components are uppercased and silently
    truncated to 8.3 format.  Missing parent directories are created
    automatically.  The file must not already exist (no overwrite).

    The FAT chain and both FAT copies are updated on every cluster write.

    Raises:
        RuntimeError: If img_path does not exist, dest_path is invalid,
                      the file already exists, or the image is full — with
                      a message that includes img_path and the reason.
    """
    if not img_path.exists():
        raise RuntimeError(f"write_file_to_image: {img_path} does not exist")

    # Normalise path: strip empty components and lone dots.
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
        # Walk to (or create) the parent directory.
        try:
            dir_cluster = _walk_path(f, geo, dir_parts, create=True)
        except RuntimeError as exc:
            raise RuntimeError(f"write_file_to_image: {img_path}: {exc}") from exc

        if _find_in_dir(f, geo, dir_cluster, name83, ext83) is not None:
            raise RuntimeError(
                f"write_file_to_image: {img_path}: '{dest_path}' already exists in the image"
            )

        # Allocate clusters — at least one, even for an empty file, so the
        # directory entry's first_cluster field is always non-zero for files.
        clusters_needed = max(1, math.ceil(len(data) / csz))
        try:
            clusters = _alloc_clusters(f, geo, clusters_needed)
        except RuntimeError as exc:
            raise RuntimeError(f"write_file_to_image: {img_path}: {exc}") from exc

        # Write data cluster by cluster, zero-padding the final cluster so
        # slack space within the last cluster is clean.
        for i, cluster in enumerate(clusters):
            chunk = data[i * csz : (i + 1) * csz]
            chunk = chunk.ljust(csz, b"\x00")
            f.seek(_cluster_byte_offset(geo, cluster))
            f.write(chunk)

        # Add the directory entry pointing to the first allocated cluster.
        try:
            slot_off = _find_free_dir_slot(f, geo, dir_cluster)
        except RuntimeError as exc:
            raise RuntimeError(f"write_file_to_image: {img_path}: {exc}") from exc

        f.seek(slot_off)
        f.write(_make_dir_entry(name83, ext83, _ATTR_FILE, clusters[0], len(data)))


def read_file_from_image(img_path: Path, dest_path: str) -> bytes:
    """Read and return the raw bytes of a file stored in a FAT16 image.

    dest_path is a POSIX-style path relative to the image root, e.g.
    "GAMES/DOOM/DOOM.EXE".  Path components are uppercased before lookup
    (FAT16 is case-insensitive by spec).  The cluster chain is followed and
    the result is trimmed to the file's recorded byte count before returning.

    Raises:
        RuntimeError: If img_path does not exist, the path is not found,
                      dest_path resolves to a directory, or the cluster chain
                      is corrupt — with a message that includes img_path.
    """
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

        # A recorded file_size of 0 with first_cluster == 0 is a valid empty file.
        if entry["first_cluster"] == 0:
            return b""

        try:
            raw = _read_cluster_chain(f, geo, entry["first_cluster"])
        except RuntimeError as exc:
            raise RuntimeError(f"read_file_from_image: {img_path}: {exc}") from exc

    # Trim cluster-boundary padding back to the exact recorded file size.
    return raw[: entry["file_size"]]
