"""In-memory (size, hash) index of media files under a library root.

Backs upload_utils.find_existing_duplicate. Replaces a fresh rglob+hash scan
of the whole tree on every upload (the same per-request-filesystem-walk
anti-pattern already fixed for GET /health/storage — see dev_docs/AUDIT.md's
storage-scanning investigation) with a build-once, reuse-after index.

Module-level dict + threading.Lock, mirroring backend/core/install_registry.py
and backend/core/process_registry.py: in-memory only, lost on restart. That's
the right tradeoff here, not a persisted table — the index never hashes a
whole library eagerly (build() only stat()s files; hashing is always lazy, on
first real comparison need), so even a cold rebuild after a restart costs one
directory walk plus stat() per candidate file, not a bulk file-content read.
Library size assumptions: there's no documented hard number, but
backend/api/routes/library.py's scan-import chunks DB inserts at 500 rows to
stay within SQLite variable limits, implying the realistic scale is hundreds
to low thousands of items — a stat-only walk at that size is sub-second.

Correctness under drift: every cached hash is re-validated against a live
stat() (size + mtime) before being trusted. Nothing outside this module needs
to proactively notify it of moves/renames/deletes — a file rewritten in place
(e.g. backend/service/launch/drive_hydration.py unlinking and reformatting a
drive image at the same path on every pre-install launch) or removed entirely
is simply re-stat()'d and, if changed or gone, dropped or rehashed before any
comparison happens. This is why the result can never be a false-positive
"duplicate found" pointing at stale content — worst case is a missed match
(falls through to a normal, correct re-upload), never a wrong one.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path

_HASH_CHUNK_SIZE = 1024 * 1024


@dataclass
class _Entry:
    size: int
    mtime: float
    sha256: str | None = None


_index: dict[Path, _Entry] = {}
_built_for: Path | None = None
_lock = threading.Lock()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_built(media_root: Path, candidate_exts: frozenset[str]) -> None:
    """Populate the index from disk if it hasn't been built for this root yet.

    Caller must hold _lock. Stat-only — never reads file contents, so this is
    cheap regardless of file size, only directory-entry count.
    """
    global _built_for
    if _built_for == media_root and _index:
        return
    fresh: dict[Path, _Entry] = {}
    for path in media_root.rglob("*"):
        try:
            if not path.is_file() or path.suffix.lower() not in candidate_exts:
                continue
            st = path.stat()
        except OSError:
            continue
        fresh[path.resolve()] = _Entry(size=st.st_size, mtime=st.st_mtime)
    _index.clear()
    _index.update(fresh)
    _built_for = media_root


def forget(path: Path) -> None:
    """Drop a path from the index, e.g. once its file is known to be gone."""
    with _lock:
        _index.pop(path.resolve(), None)


def find_duplicate(
    media_root: Path,
    candidate_exts: frozenset[str],
    uploaded_path: Path,
    uploaded_size: int,
) -> Path | None:
    """Return an existing path under media_root with content identical to
    uploaded_path, or None.

    Builds the index on first use (or after media_root changes), then filters
    cached entries by size and re-validates each same-size candidate against a
    live stat() before trusting (or reusing) its cached hash — so a file
    that's been moved, rewritten, or deleted since it was indexed is always
    caught instead of producing a stale match.

    If no duplicate is found, uploaded_path is registered in the index with
    whatever hash was already computed along the way (possibly none, if no
    same-size candidate ever existed to compare against) — so it's visible to
    the very next lookup with no lag, at no extra hashing cost beyond what
    this call already did.
    """
    with _lock:
        _ensure_built(media_root, candidate_exts)
        candidates = [p for p, e in _index.items() if e.size == uploaded_size]

    uploaded_resolved = uploaded_path.resolve()
    uploaded_hash: str | None = None

    for path in candidates:
        if path == uploaded_resolved:
            continue
        try:
            st = path.stat()
        except OSError:
            forget(path)
            continue

        with _lock:
            entry = _index.get(path)
        if entry is None:
            continue

        if st.st_size != entry.size or st.st_mtime != entry.mtime:
            # Changed on disk since last indexed (e.g. drive hydration
            # recreating a .img at the same path) — refresh before trusting
            # it, and only keep comparing if it still matches our target size.
            with _lock:
                if path in _index:
                    _index[path] = _Entry(size=st.st_size, mtime=st.st_mtime)
            if st.st_size != uploaded_size:
                continue
            entry = _Entry(size=st.st_size, mtime=st.st_mtime)

        if entry.sha256 is not None:
            candidate_hash = entry.sha256
        else:
            try:
                candidate_hash = _hash_file(path)
            except OSError:
                forget(path)
                continue
            with _lock:
                cached = _index.get(path)
                if cached is not None and cached.mtime == st.st_mtime:
                    cached.sha256 = candidate_hash

        if uploaded_hash is None:
            uploaded_hash = _hash_file(uploaded_path)

        if candidate_hash == uploaded_hash:
            return path

    with _lock:
        try:
            mtime = uploaded_resolved.stat().st_mtime
        except OSError:
            return None
        _index[uploaded_resolved] = _Entry(size=uploaded_size, mtime=mtime, sha256=uploaded_hash)
    return None
