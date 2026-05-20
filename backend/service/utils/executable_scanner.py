from __future__ import annotations

import os
from pathlib import Path

_DEPRIORITIZED_STEMS = frozenset({"setup", "install", "uninst", "autorun", "unwise", "readme"})
_EXECUTABLE_EXTENSIONS = frozenset({".exe", ".bat", ".com"})
_ISO_DRIVE_LETTER = "D"


def scan_executable_candidates(media_path: Path) -> list[str]:
    suffix = media_path.suffix.lower()
    if suffix in {".iso", ".cue"}:
        return _scan_optical(media_path)
    if media_path.is_dir():
        return _scan_directory(media_path)
    raise ValueError(
        f"Unsupported media: '{media_path}'. Expected .iso, .cue, or a directory."
    )


def _rank_key(path: str, media_stem_lower: str) -> tuple[int, str]:
    fname = os.path.basename(path)
    if "." in fname:
        stem = fname.rsplit(".", 1)[0].lower()
        ext = "." + fname.rsplit(".", 1)[1].lower()
    else:
        stem = fname.lower()
        ext = ""

    if stem in _DEPRIORITIZED_STEMS:
        return (5, fname.lower())

    is_stem_match = stem == media_stem_lower

    if ext == ".exe":
        return (0 if is_stem_match else 1, fname.lower())
    if ext == ".bat":
        return (2 if is_stem_match else 3, fname.lower())
    if ext == ".com":
        return (4, fname.lower())
    return (6, fname.lower())


def _scan_optical(media_path: Path) -> list[str]:
    # Security: all returned paths are constructed from pycdlib walk results only.
    try:
        import pycdlib
        from pycdlib.pycdlibexception import PyCdlibException
    except ImportError as exc:
        raise RuntimeError(
            f"pycdlib is required to scan optical media but is not installed: {exc}"
        ) from exc

    iso = pycdlib.PyCdlib()
    try:
        iso.open(str(media_path))
    except PyCdlibException as exc:
        raise RuntimeError(
            f"Could not open optical media '{media_path}': {exc}"
        ) from exc

    try:
        candidates: list[str] = []
        use_joliet = iso.has_joliet()
        walk_kwargs: dict = {"joliet_path": "/"} if use_joliet else {"iso_path": "/"}

        for dirpath, _dirnames, filenames in iso.walk(**walk_kwargs):
            for raw_fname in filenames:
                fname = raw_fname if use_joliet else raw_fname.split(";")[0]
                if "." not in fname:
                    continue
                ext = "." + fname.rsplit(".", 1)[1].lower()
                if ext not in _EXECUTABLE_EXTENSIONS:
                    continue
                iso_rel = f"/{fname}" if dirpath == "/" else f"{dirpath}/{fname}"
                dos_path = f"{_ISO_DRIVE_LETTER}:" + iso_rel.replace("/", "\\")
                candidates.append(dos_path)

        media_stem_lower = media_path.stem.lower()
        candidates.sort(key=lambda p: _rank_key(p, media_stem_lower))
        return candidates

    finally:
        iso.close()


def _scan_directory(media_path: Path) -> list[str]:
    candidates: list[str] = []
    for root, _dirs, files in os.walk(media_path):
        for fname in files:
            if "." not in fname:
                continue
            ext = "." + fname.rsplit(".", 1)[1].lower()
            if ext in _EXECUTABLE_EXTENSIONS:
                candidates.append(str(Path(root) / fname))

    media_stem_lower = media_path.stem.lower()
    candidates.sort(key=lambda p: _rank_key(p, media_stem_lower))
    return candidates
