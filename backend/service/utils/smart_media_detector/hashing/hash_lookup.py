import hashlib
import json
import zlib
from pathlib import Path

from ..result import ScanResult

_CHUNK = 65536


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
    if not index_path.exists():
        raise FileNotFoundError(
            f"Hash index not found at {index_path}. "
            "Run build_index.py to generate it from your DAT files."
        )
    with index_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def lookup(path: Path, index: dict) -> ScanResult | None:
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
            executable_hints=[],
        )

    for entry in index.values():
        if entry.get("md5") == hashes["md5"]:
            return ScanResult(
                title=entry.get("title"),
                platform=entry.get("platform"),
                era=entry.get("era"),
                confidence=0.85,
                reason=f"md5 match: {hashes['md5']}",
                executable_hints=[],
            )

    for entry in index.values():
        if entry.get("crc32") == hashes["crc32"]:
            return ScanResult(
                title=entry.get("title"),
                platform=entry.get("platform"),
                era=entry.get("era"),
                confidence=0.75,
                reason=f"crc32 match: {hashes['crc32']}",
                executable_hints=[],
            )

    return None
