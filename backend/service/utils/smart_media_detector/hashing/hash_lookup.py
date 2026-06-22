import hashlib
import json
import zlib
from pathlib import Path

from ..result import ScanResult

_CHUNK = 65536

# Cached per index_path: (mtime, sha1_index, md5_index, crc32_index). Keyed by mtime
# so a rebuilt hash_index.json (via build_index.py) is picked up without a restart.
_index_cache: dict[Path, tuple[float, dict, dict, dict]] = {}


def hash_file(path: Path) -> dict:
    sha1 = hashlib.sha1()
    md5 = hashlib.md5()
    crc = 0

    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            sha1.update(chunk)
            md5.update(chunk)
            crc = zlib.crc32(chunk, crc)

    return {
        "sha1": sha1.hexdigest(),
        "md5": md5.hexdigest(),
        "crc32": format(crc & 0xFFFFFFFF, "08x"),
    }


def load_index(index_path: Path) -> dict:
    """Return the sha1-keyed index dict for index_path, loading and caching it on first use."""
    return _load_cached(index_path)[0]


def lookup(path: Path, index_path: Path) -> ScanResult | None:
    index, md5_index, crc32_index = _load_cached(index_path)
    if not index:
        return None

    hashes = hash_file(path)

    entry = index.get(hashes["sha1"])
    if entry is not None:
        return ScanResult(
            title=entry.get("title"),
            platform=entry.get("platform"),
            era=entry.get("era"),
            confidence=1.0,
            reason=f"sha1 match: {hashes['sha1']}",
        )

    entry = md5_index.get(hashes["md5"])
    if entry is not None:
        return ScanResult(
            title=entry.get("title"),
            platform=entry.get("platform"),
            era=entry.get("era"),
            confidence=0.85,
            reason=f"md5 match: {hashes['md5']}",
        )

    entry = crc32_index.get(hashes["crc32"])
    if entry is not None:
        return ScanResult(
            title=entry.get("title"),
            platform=entry.get("platform"),
            era=entry.get("era"),
            confidence=0.75,
            reason=f"crc32 match: {hashes['crc32']}",
        )

    return None


def _load_cached(index_path: Path) -> tuple[dict, dict, dict]:
    if not index_path.exists():
        raise FileNotFoundError(
            f"Hash index not found at {index_path}. "
            "Run build_index.py to generate it from your DAT files."
        )

    mtime = index_path.stat().st_mtime
    cached = _index_cache.get(index_path)
    if cached is not None and cached[0] == mtime:
        return cached[1], cached[2], cached[3]

    with index_path.open("r", encoding="utf-8") as fh:
        index = json.load(fh)

    md5_index: dict[str, dict] = {}
    crc32_index: dict[str, dict] = {}
    for entry in index.values():
        md5 = entry.get("md5")
        if md5 and md5 not in md5_index:
            md5_index[md5] = entry
        crc32 = entry.get("crc32")
        if crc32 and crc32 not in crc32_index:
            crc32_index[crc32] = entry

    _index_cache[index_path] = (mtime, index, md5_index, crc32_index)
    return index, md5_index, crc32_index
