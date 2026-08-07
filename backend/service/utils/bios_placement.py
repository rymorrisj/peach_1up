"""Placement logic for POST /api/v1/bios/{slug}/place.

Lets a tester who already has BIOS/ROM files on disk point at them instead of
manually copying into the right folder. This module only adds the per-slug
filename/extension/hash rules and the copy step, path safety and chunked
upload streaming are reused as-is from path_utils / upload_utils, the same
primitives the media/library upload routes use.

Never fetches, downloads, or scrapes anything, source is always a path or
upload the caller already has.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import UploadFile

from backend.service.utils.path_utils import normalise_path, resolve_under, safe_basename
from smart_media_detector.hashing.hash_lookup import hash_file
from backend.service.utils.upload_utils import DEFAULT_MAX_BYTES, stream_upload_to_disk


class PlacementError(ValueError):
    """A placement request that must be rejected outright (-> HTTP 400)."""


@dataclass
class PlacementResult:
    copied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Known-good hash for the optional Famicom Disk System BIOS, taken verbatim
# from dev_docs/EMULATORS.md. The task brief that introduced this feature
# quoted a 39-character value (`e4e41472454f928e53eb10e0509bf7d1146ecc1`) —
# one character short for a SHA1, missing the "c" after "e4e41472". The value
# below matches EMULATORS.md and is the one actually checked against.
_MESEN_FDS_SHA1 = "e4e41472c454f928e53eb10e0509bf7d1146ecc1"
_MESEN_FDS_NAME = "FdsBios.bin"

_FLYCAST_NAMES = ("dc_boot.bin", "dc_flash.bin")

_BIN_PATTERN = re.compile(r"\.bin$", re.IGNORECASE)
_PS2_PATTERN = re.compile(r"(\.bin|\.rom\d*|\.erom)$", re.IGNORECASE)


def _iter_source_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    return [p for p in sorted(source.iterdir()) if p.is_file()]


async def _copy_or_stream(
    *, source: Path | None, upload: UploadFile | None, dest_path: Path,
    max_bytes: int, result: PlacementResult, name: str,
) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists():
        result.skipped.append(name)
        return
    if upload is not None:
        await stream_upload_to_disk(upload, dest_path, max_bytes)
    else:
        assert source is not None
        shutil.copy2(source, dest_path)
    result.copied.append(name)


async def _place_flat_pattern(
    *, pattern: re.Pattern, label: str, source: Path | None,
    uploads: list[UploadFile], dest_dir: Path, max_bytes: int,
) -> PlacementResult:
    result = PlacementResult()
    if source is not None:
        matched = [p for p in _iter_source_files(source) if pattern.search(p.name)]
        if not matched:
            raise PlacementError(f"No {label} files found in '{source}'.")
        for p in matched:
            dest_path = resolve_under(dest_dir, p.name)
            await _copy_or_stream(
                source=p, upload=None, dest_path=dest_path,
                max_bytes=max_bytes, result=result, name=p.name,
            )
    else:
        if not uploads:
            raise PlacementError("No file provided.")
        matched_any = False
        for up in uploads:
            if not up.filename:
                continue
            safe_name = safe_basename(up.filename)
            if not pattern.search(safe_name):
                result.warnings.append(
                    f"Skipped '{up.filename}', does not look like a {label} file."
                )
                continue
            matched_any = True
            dest_path = resolve_under(dest_dir, safe_name)
            await _copy_or_stream(
                source=None, upload=up, dest_path=dest_path,
                max_bytes=max_bytes, result=result, name=safe_name,
            )
        if not matched_any:
            raise PlacementError(f"None of the uploaded files look like {label} files.")
    return result


def _place_tree_merge(*, source: Path, dest_dir: Path) -> PlacementResult:
    if not source.is_dir():
        raise PlacementError("86Box ROM pack placement requires a folder, not a single file.")
    result = PlacementResult()
    dest_dir.mkdir(parents=True, exist_ok=True)
    for entry in source.rglob("*"):
        if entry.is_dir():
            continue
        rel = entry.relative_to(source)
        rel_str = str(rel).replace("\\", "/")
        dest_path = resolve_under(dest_dir, *rel.parts)
        if dest_path.exists():
            result.skipped.append(rel_str)
            continue
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry, dest_path)
        result.copied.append(rel_str)
    if not result.copied and not result.skipped:
        raise PlacementError(f"No files found in '{source}'.")
    return result


async def _place_named_pair(
    *, source: Path | None, uploads: list[UploadFile], dest_dir: Path, max_bytes: int,
) -> PlacementResult:
    result = PlacementResult()
    found: dict[str, Path | UploadFile] = {}

    if source is not None:
        for p in _iter_source_files(source):
            for canon in _FLYCAST_NAMES:
                if p.name.lower() == canon:
                    found[canon] = p
    else:
        for up in uploads:
            if not up.filename:
                continue
            for canon in _FLYCAST_NAMES:
                if up.filename.lower() == canon:
                    found[canon] = up

    if not found:
        where = "folder" if source is not None else "upload"
        raise PlacementError(
            f"Expected {' and '.join(_FLYCAST_NAMES)}, neither was found in the supplied {where}."
        )

    for canon, item in found.items():
        dest_path = resolve_under(dest_dir, canon)
        if isinstance(item, Path):
            await _copy_or_stream(
                source=item, upload=None, dest_path=dest_path,
                max_bytes=max_bytes, result=result, name=canon,
            )
        else:
            await _copy_or_stream(
                source=None, upload=item, dest_path=dest_path,
                max_bytes=max_bytes, result=result, name=canon,
            )

    for canon in _FLYCAST_NAMES:
        if canon not in found and not (dest_dir / canon).exists():
            result.warnings.append(
                f"'{canon}' is still missing, Flycast requires both files together."
            )
    return result


async def _place_mesen_fds(
    *, source: Path | None, uploads: list[UploadFile], dest_dir: Path, max_bytes: int,
) -> PlacementResult:
    result = PlacementResult()
    dest_path = resolve_under(dest_dir, _MESEN_FDS_NAME)

    if source is not None:
        match = next(
            (p for p in _iter_source_files(source) if p.name.lower() == _MESEN_FDS_NAME.lower()),
            None,
        )
        if match is None:
            raise PlacementError(f"Expected a file named '{_MESEN_FDS_NAME}', not found in '{source}'.")
        await _copy_or_stream(
            source=match, upload=None, dest_path=dest_path,
            max_bytes=max_bytes, result=result, name=_MESEN_FDS_NAME,
        )
    else:
        if len(uploads) != 1 or not uploads[0].filename:
            raise PlacementError(f"Upload exactly one file named '{_MESEN_FDS_NAME}'.")
        up = uploads[0]
        if up.filename.lower() != _MESEN_FDS_NAME.lower():
            raise PlacementError(f"Expected a file named '{_MESEN_FDS_NAME}', got '{up.filename}'.")
        await _copy_or_stream(
            source=None, upload=up, dest_path=dest_path,
            max_bytes=max_bytes, result=result, name=_MESEN_FDS_NAME,
        )

    if _MESEN_FDS_NAME in result.copied:
        digest = hash_file(dest_path).sha1
        if digest.lower() != _MESEN_FDS_SHA1.lower():
            result.warnings.append(
                f"SHA1 {digest} does not match the known-good FDS BIOS hash ({_MESEN_FDS_SHA1}). "
                "The file was placed, but double-check the dump, other revisions may not work correctly."
            )
    return result


async def place_bios_asset(
    *, slug: str, source_path: str | None, uploads: list[UploadFile],
    dest_dir: Path, max_bytes: int = DEFAULT_MAX_BYTES,
) -> PlacementResult:
    source: Path | None = None
    if source_path:
        source = normalise_path(source_path)
        if not source.exists():
            raise PlacementError(f"Path does not exist: {source}")

    if source is None and not uploads:
        raise PlacementError("Provide either source_path or at least one file upload.")

    if slug == "ps1-bios":
        return await _place_flat_pattern(
            pattern=_BIN_PATTERN, label="PS1 BIOS (.bin)",
            source=source, uploads=uploads, dest_dir=dest_dir, max_bytes=max_bytes,
        )

    if slug == "ps2-bios":
        result = await _place_flat_pattern(
            pattern=_PS2_PATTERN, label="PS2 BIOS",
            source=source, uploads=uploads, dest_dir=dest_dir, max_bytes=max_bytes,
        )
        try:
            total = sum(1 for p in dest_dir.iterdir() if p.is_file())
        except FileNotFoundError:
            total = 0
        if total < 2:
            result.warnings.append(
                f"Only {total} file(s) present in the PS2 BIOS directory, a full set "
                "(main BIOS + rom1/rom2/erom) usually has multiple files. The set may be incomplete."
            )
        return result

    if slug == "86box-roms":
        if source is None:
            raise PlacementError(
                "86Box ROM pack placement requires a server-side folder path, "
                "file upload isn't supported for ROM pack trees."
            )
        return _place_tree_merge(source=source, dest_dir=dest_dir)

    if slug == "dreamcast-bios":
        return await _place_named_pair(
            source=source, uploads=uploads, dest_dir=dest_dir, max_bytes=max_bytes,
        )

    if slug == "mesen-fds-bios":
        return await _place_mesen_fds(
            source=source, uploads=uploads, dest_dir=dest_dir, max_bytes=max_bytes,
        )

    if slug == "xbox-bios":
        raise PlacementError(
            "xemu uses its own configuration flow, not a copy-into-place flow, "
            "set bootrom/flashrom/hdd_image paths via PATCH /api/v1/emulator-items/xemu/asset-paths."
        )

    raise PlacementError(f"Unsupported BIOS slug for placement: '{slug}'.")
