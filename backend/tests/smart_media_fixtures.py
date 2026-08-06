"""Shared synthetic fixtures for backend.service.utils.smart_media_detector tests.

Not a test module itself (no test_ prefix, nothing here is collected by pytest).
Plain helper functions/constants, imported directly by test_classify.py and
test_magic_detect.py, following this package's existing convention (see
test_iso_detect.py) of local per-test-file imports over a shared conftest.py.

hash_index.json in production is ~88MB — real DAT-derived data, never to be
loaded directly in a test. Every hash-index-shaped fixture here is a small,
in-memory/tmp_path-only synthetic index built from scratch.
"""

import hashlib
import json
import struct
import zlib
from pathlib import Path

# ---------------------------------------------------------------------------
# Generic hash helpers — mirror hash_lookup.hash_file()'s algorithm exactly
# (sha1/md5 over the full buffer, crc32 masked to unsigned 32-bit hex) so a
# fixture file's real computed hash always matches what's baked into the
# synthetic index below.
# ---------------------------------------------------------------------------


def hashes_for(content: bytes) -> dict[str, str]:
    return {
        "sha1": hashlib.sha1(content).hexdigest(),
        "md5": hashlib.md5(content).hexdigest(),
        "crc32": format(zlib.crc32(content) & 0xFFFFFFFF, "08x"),
    }


def _synthetic_sha1(label: str) -> str:
    """Deterministic 40-hex key for an index entry that represents 'a record
    already in the index under some other file's hash' — not derived from
    any fixture file's real content, since that's the point of these entries.
    """
    return hashlib.sha1(f"peach1up-synthetic-fixture:{label}".encode()).hexdigest()


def patch_classify_index(monkeypatch, index_path: Path) -> None:
    """Points classify.py's module-level _INDEX_PATH constant at *index_path*
    for the duration of one test.

    classify() has no index-path parameter of its own — unlike
    fuzzy_title_match()/hash_lookup.lookup(), which both take index_path
    directly, classify() always reads its own private _INDEX_PATH module
    constant (pointing at the real hash_index.json). Monkeypatching that
    constant is the only way to run classify() against a synthetic index
    without touching the real 88MB file.
    """
    from backend.service.utils.smart_media_detector import classify as classify_module

    monkeypatch.setattr(classify_module, "_INDEX_PATH", index_path)


def patch_verify_index(monkeypatch, index_path: Path) -> None:
    """Points verify.py's own module-level _INDEX_PATH constant at *index_path*,
    same rationale and pattern as patch_classify_index(). verify.py declares its
    own private _INDEX_PATH separate from classify.py's, so it needs its own patch.
    """
    from backend.service.utils.smart_media_detector import verify as verify_module

    monkeypatch.setattr(verify_module, "_INDEX_PATH", index_path)


# ---------------------------------------------------------------------------
# Part 1.1 — synthetic hash_index.json (5 entries)
# ---------------------------------------------------------------------------

VERIFIED_CONTENT = b"PEACH1UP_SYNTHETIC_VERIFIED_PS1_DISC"
CAUTION_MD5_CONTENT = b"PEACH1UP_SYNTHETIC_CAUTION_MD5_SOURCE"
CAUTION_CRC32_CONTENT = b"PEACH1UP_SYNTHETIC_CAUTION_CRC32_SOURCE"
UNINDEXED_CONTENT = b"PEACH1UP_SYNTHETIC_UNINDEXED_FILE_NO_HASH_MATCH"

CHD_EMBEDDED_SHA1 = _synthetic_sha1("chd-embedded-rawsha1")
CAUTION_ENTRY_SHA1 = _synthetic_sha1("caution-entry-own-sha1")
TITLE_MATCH_ENTRY_SHA1 = _synthetic_sha1("title-match-entry-own-sha1")
ERA_NONE_TRAP_SHA1 = _synthetic_sha1("era-none-trap-entry-own-sha1")

TITLE_MATCH_INDEXED_TITLE = "Final Fantasy VII (USA)"
# ratio (SequenceMatcher, normalized) vs TITLE_MATCH_INDEXED_TITLE == 0.8750 — above 0.80.
TITLE_QUERY_ABOVE_THRESHOLD = "Final Fantasy 7"
# ratio vs TITLE_MATCH_INDEXED_TITLE == 0.6471 — below 0.80.
TITLE_QUERY_BELOW_THRESHOLD = "Fantasy Final VII"

ERA_NONE_TRAP_TITLE = "Untracked PC Game (USA)"


def build_synthetic_index() -> dict[str, dict]:
    """Raw dict matching hash_index.json's real schema (verified against
    hash_lookup.py/classify.py and a handful of real entries):
    {sha1_hex: {title, platform, era, source, md5?, crc32?}}.

    Exactly 5 entries:
      1. sha1-only — no md5/crc32 keys at all (mirrors a real record sourced
         from a DAT that only supplied sha1). Drives the "verified" tests.
      2. md5+crc32 populated, own sha1 unrelated to any fixture file's real
         hash. Drives both caution sub-tiers (md5-hit, crc32-hit) via two
         different source files that each collide on exactly one field.
      3. CHD-style, keyed by embedded rawsha1 rather than any file's real
         on-disk hash (chdman wraps/compresses, so a .chd's raw file hash
         never equals the original dump's hash — see chd_validator.py).
      4. title-match entry (era=ps1) — used by both the above- and
         below-threshold fuzzy_title_match tests.
      5. era=None trap — a title that fuzzy-matches trivially (it's the
         exact indexed string) but carries no era. Used to prove classify()
         never turns this into a false "mismatch": fuzzy_title_match()
         fails closed on era=None rather than searching every era=None
         record — a real, large bucket in production (e.g. the unmapped
         "IBM - PC compatible" DAT, see README's Current coverage state).
         If that guard were ever removed, this exact shape (matching title,
         no era) is what would start producing a false "mismatch".
    """
    verified_hashes = hashes_for(VERIFIED_CONTENT)
    caution_md5_hashes = hashes_for(CAUTION_MD5_CONTENT)
    caution_crc32_hashes = hashes_for(CAUTION_CRC32_CONTENT)

    return {
        verified_hashes["sha1"]: {
            "title": "Synthetic Verified Game (USA)",
            "platform": "Sony PlayStation",
            "era": "ps1",
            "source": "synthetic-fixture",
        },
        CAUTION_ENTRY_SHA1: {
            "title": "Synthetic Caution Game (USA)",
            "platform": "Sony PlayStation",
            "era": "ps1",
            "source": "synthetic-fixture",
            "md5": caution_md5_hashes["md5"],
            "crc32": caution_crc32_hashes["crc32"],
        },
        CHD_EMBEDDED_SHA1: {
            "title": "Synthetic CHD Disc (USA)",
            "platform": "Sega Dreamcast",
            "era": "dreamcast",
            "source": "synthetic-fixture",
        },
        TITLE_MATCH_ENTRY_SHA1: {
            "title": TITLE_MATCH_INDEXED_TITLE,
            "platform": "Sony PlayStation",
            "era": "ps1",
            "source": "synthetic-fixture",
        },
        ERA_NONE_TRAP_SHA1: {
            "title": ERA_NONE_TRAP_TITLE,
            "platform": None,
            "era": None,
            "source": "synthetic-fixture",
        },
    }


def write_synthetic_index(tmp_path: Path) -> Path:
    index_path = tmp_path / "hash_index.json"
    index_path.write_text(json.dumps(build_synthetic_index()), encoding="utf-8")
    return index_path


def build_synthetic_chd(embedded_sha1_hex: str) -> bytes:
    """Minimal CHD v5 header: real magic + real rawsha1 offset/length, no
    hunk data (extract_embedded_sha1() only reads header bytes).
    """
    raw = bytes.fromhex(embedded_sha1_hex)
    assert len(raw) == 20
    buf = bytearray(100)
    buf[0:8] = b"MComprHD"
    buf[64:84] = raw
    return bytes(buf)


# ---------------------------------------------------------------------------
# Part 1.1b, CHD header and metadata-chain builder, for chd_validator.detect()
# ---------------------------------------------------------------------------
#
# CHD v5 fixed-header field offsets (chd.h, mirrored from chd_validator.py):
#   magic        @0,  8 bytes literal "MComprHD"
#   logicalbytes @32, 8 bytes big-endian uint64 (uncompressed image size)
#   meta_offset  @48, 8 bytes big-endian uint64 (offset of first metadata entry, 0 = none)
#   rawsha1      @64, 20 bytes (all-zero = unset)
#
# A metadata entry is a 16-byte header at its own offset in the file:
#   tag(4) + flags(1)+length(3) packed as one big-endian uint32 + next_offset(8, big-endian uint64)
# chd_validator.detect() only reads the tag and next_offset fields, flags/length
# content is never inspected, so build_chd_metadata_entry() leaves them zeroed.

CHD_HEADER_SIZE = 124  # real CHD v5 header size; only matters as a safe minimum buffer length
CHD_META_ENTRY_LEN = 16
_CHD_MAGIC_FOR_FIXTURES = b"MComprHD"


def build_chd_header(
    *, rawsha1: bytes | None = None, logical_bytes: int = 0, meta_offset: int = 0, size: int = CHD_HEADER_SIZE,
) -> bytearray:
    """Base CHD v5-shaped header buffer, no metadata entries placed yet.

    rawsha1=None leaves the field all-zero (the "unset" case extract_embedded_sha1()
    must treat distinctly from a real hash). size may be extended by the caller to
    make room for metadata entries appended after the header.
    """
    buf = bytearray(max(size, 84))
    buf[0:8] = _CHD_MAGIC_FOR_FIXTURES
    struct.pack_into(">Q", buf, 32, logical_bytes)
    struct.pack_into(">Q", buf, 48, meta_offset)
    if rawsha1 is not None:
        assert len(rawsha1) == 20
        buf[64:84] = rawsha1
    return buf


def build_chd_metadata_entry(tag: bytes, next_offset: int) -> bytes:
    """16-byte metadata entry header: tag(4) + flags/length(4, left zero) + next_offset(8, big-endian).

    tag must be exactly 4 bytes (e.g. b"CHGD", b"CHTR", b"CHT2", or any other
    4-byte value to build an unrecognised-tag entry for chain-termination tests).
    """
    assert len(tag) == 4
    entry = bytearray(CHD_META_ENTRY_LEN)
    entry[0:4] = tag
    struct.pack_into(">Q", entry, 8, next_offset)
    return bytes(entry)


def place_chd_metadata_entry(buf: bytearray, offset: int, tag: bytes, next_offset: int) -> None:
    """Writes a metadata entry into buf at offset. buf must already be long
    enough (extend it via build_chd_header(size=...) or bytearray padding
    before calling this).
    """
    entry = build_chd_metadata_entry(tag, next_offset)
    buf[offset:offset + len(entry)] = entry


# ---------------------------------------------------------------------------
# Part 1.2 — synthetic 2352-byte Mode-2 CD sector builder, for
# magic_detect._resolve_ps_generation() / resolve_ps_generation_from_file()
# ---------------------------------------------------------------------------

SECTOR = 2352
DATA_OFF = 24
_ROOT_LBA = 20
_CNF_LBA = 21


def _dir_record(name: bytes, lba: int, size: int) -> bytes:
    """Minimal ISO9660 directory record — only the fields
    magic_detect._resolve_ps_generation() actually reads: record length
    (offset 0), LBA (offset 2, LE), data length (offset 10, LE), file
    identifier length (offset 32), file identifier (offset 33+).
    """
    name_len = len(name)
    rec = bytearray(33 + name_len)
    rec[0] = len(rec)
    struct.pack_into("<I", rec, 2, lba)
    struct.pack_into("<I", rec, 10, size)
    rec[32] = name_len
    rec[33:33 + name_len] = name
    return bytes(rec)


def build_ps_disc_bin(
    *, boot_line: str | None, include_pvd: bool = True, include_system_cnf: bool = True,
) -> bytes:
    """Raw Mode-2/2352 BIN image covering sectors 0..21, with a valid ISO9660
    PVD at sector 16 (root dir at sector 20) and, when requested, a
    SYSTEM.CNF entry at sector 21 containing *boot_line*.

    include_pvd=False — no PVD at all (sector 16 left zeroed, byte 0 != 1).
    include_system_cnf=False — PVD present, but root dir has no SYSTEM.CNF
        entry (root dir sector left zeroed).
    """
    buf = bytearray((_CNF_LBA + 1) * SECTOR)
    if not include_pvd:
        return bytes(buf)

    pvd_start = 16 * SECTOR + DATA_OFF
    buf[pvd_start] = 1  # ISO9660 PVD type code
    root_size = 2048
    buf[pvd_start + 158:pvd_start + 162] = struct.pack("<I", _ROOT_LBA)
    buf[pvd_start + 166:pvd_start + 170] = struct.pack("<I", root_size)

    if include_system_cnf:
        cnf_bytes = (boot_line or "").encode("ascii")
        rec = _dir_record(b"SYSTEM.CNF", _CNF_LBA, len(cnf_bytes))
        root_start = _ROOT_LBA * SECTOR + DATA_OFF
        buf[root_start:root_start + len(rec)] = rec

        cnf_start = _CNF_LBA * SECTOR + DATA_OFF
        buf[cnf_start:cnf_start + len(cnf_bytes)] = cnf_bytes

    return bytes(buf)


# ---------------------------------------------------------------------------
# Part 1.3 — per-signature fixtures for magic_detect.detect_from_magic(),
# magic bytes transcribed directly from magic_signatures.toml
# ---------------------------------------------------------------------------


def _magic_blob(magic_hex: str, offset: int, total_len: int = 64) -> bytes:
    magic = bytes(int(b, 16) for b in magic_hex.split())
    buf = bytearray(max(total_len, offset + len(magic)))
    buf[offset:offset + len(magic)] = magic
    return bytes(buf)


CDROM_SYNC_AMBIGUOUS_BLOB = _magic_blob("00 FF FF FF FF FF FF FF FF FF FF 00", 0x00)
DREAMCAST_IP_BIN_BLOB = _magic_blob("53 45 47 41 20 53 45 47 41 4B 41 54 41 4E 41", 0x10)
N64_BIG_ENDIAN_BLOB = _magic_blob("80 37 12 40", 0x00)
N64_BYTESWAPPED_BLOB = _magic_blob("37 80 40 12", 0x00)
N64_LITTLE_ENDIAN_BLOB = _magic_blob("40 12 37 80", 0x00)
NES_HEADER_BLOB = _magic_blob("4E 45 53 1A", 0x00)


# ---------------------------------------------------------------------------
# Part 1.4, minimal PE/MZ header builder, for exe_detect.detect_exe()
# ---------------------------------------------------------------------------
#
# Field offsets mirrored from exe_detect.py's own reading code:
#   e_lfanew (PE offset pointer) @0x3C in the MZ header, 4 bytes little-endian
#   PE signature "PE\0\0"        @pe_offset, 4 bytes
#   MajorOperatingSystemVersion  @pe_offset+64, 2 bytes little-endian (IMAGE_OPTIONAL_HEADER)
#   Subsystem                    @pe_offset+92, 2 bytes little-endian
# exe_detect.py requires pe_offset + 96 <= len(header) before reading either
# field, so a too-large pe_offset with no room left is its own branch
# ("garbage PE offset"), distinct from a too-short MZ-only header.


def build_pe_header(
    *,
    mz: bool = True,
    total_len: int = 512,
    pe_offset: int | None = 0x80,
    pe_signature: bytes = b"PE\x00\x00",
    major_os_version: int = 4,
    subsystem: int = 2,
) -> bytes:
    """pe_offset=None builds an MZ-only header (no e_lfanew written at all).
    Use this for the too-short-for-a-PE-offset case by also passing a small
    total_len (< 0x40). Passing a pe_offset that leaves no room for the
    Subsystem/MajorOperatingSystemVersion fields (pe_offset + 96 > total_len)
    builds the "garbage PE offset" case; the PE signature and version fields
    are silently not written in that case since exe_detect.py never reads
    that far.
    """
    buf = bytearray(total_len)
    if mz:
        buf[0:2] = b"MZ"
    if pe_offset is None:
        return bytes(buf)

    struct.pack_into("<I", buf, 0x3C, pe_offset)
    if pe_offset + 96 > total_len:
        return bytes(buf)

    buf[pe_offset:pe_offset + 4] = pe_signature
    struct.pack_into("<H", buf, pe_offset + 64, major_os_version)
    struct.pack_into("<H", buf, pe_offset + 92, subsystem)
    return bytes(buf)
