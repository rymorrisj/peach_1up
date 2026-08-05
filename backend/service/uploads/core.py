"""Chunked-upload transport & storage. Shared across every upload domain
(software_games, software_media, software_apps), this module has no
knowledge of any one domain, only bytes-on-disk.

Single responsibility: accept a file (or folder of files) as an ordered series
of chunks staged under ``library/tmp_chunks/<upload_id>/``, then reassemble
them into their permanent location under whichever domain root the caller
passes to ``reassemble``. Staging lives under the shared library root rather
than any one domain's root because at staging time the upload's eventual
destination domain is not yet known (the client can pick any registered
domain's route without this module caring), and reassembly is what resolves
it. Ingest (dedup, era detection, DB persistence) is NOT done here, that is
each domain's own finalize module's job (see backend.service.uploads.registry
and software_games.py / software_media.py / software_apps.py). Cleanup of the
staging area is owned entirely by this module (success, abort, and orphan
sweep).

Sessions are in-memory (matching _scan_state / install_registry). A crash loses
the session but leaves the tmp dir on disk; sweep_orphans() reaps those.
"""
from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile

from backend.core import jobs
from backend.core.logger import get_logger
from backend.service.utils.path_utils import resolve_under, safe_basename, sanitize_relative_path
from backend.service.utils.slug_generator import unique_slug
from backend.service.utils.upload_utils import (
    DEFAULT_MAX_BYTES,
    TMP_CHUNKS_DIRNAME,
    stream_upload_to_disk,
)

logger = get_logger(__name__)

_lock = threading.Lock()
_sessions: dict[str, dict] = {}

# Time-based throttle for reassemble()'s progress reporting, a simple local
# last-update timestamp rather than reading the job's own updated_at back from
# core.jobs (avoids a second lock round-trip per chunk just to throttle).
# Chosen over a fixed chunk-count stride because the nested files x chunks
# loop shape means a stride like "every 10 chunks" would fire far too often
# for many small files and not often enough for few huge ones; wall-clock
# time is shape-agnostic. 1s comfortably beats the frontend's 1500ms poll
# interval without adding meaningful lock contention.
_PROGRESS_INTERVAL_SECONDS = 1.0

# Smallest chunk size init_session will assume a real client might have picked,
# used only as the divisor for the upper bound on a declared chunk count. It is
# deliberately far below any plausible client value (the bundled frontend uses
# 8 MB, 128x larger) so that the bound rejects only counts that are absurd for
# the declared size, never counts that are merely finer-grained than expected.
# Not a transport parameter: nothing enforces a minimum on an actual chunk PUT,
# and a real final chunk is routinely smaller than this.
_MIN_CHUNK_BYTES = 64 * 1024

# Hard ceiling on .part files staged for a single file, independent of its
# declared size. Each chunk costs one file handle's worth of dir entry plus one
# set member regardless of how few bytes it carries, so this bounds that
# per-count overhead even for a maximal declared size. It only binds below a
# 256 KB implied chunk size on a 25 GB upload, well under _MIN_CHUNK_BYTES
# territory for anything smaller, so no realistic client ever meets it.
_MAX_CHUNKS_PER_FILE = 100_000


@dataclass
class ReassembledUpload:
    kind: str  # "file" | "folder" | "set"
    title: str
    dest_dir: Path
    paths: list[Path]
    total_bytes: int


def tmp_root() -> Path:
    """Shared pre-domain staging root, library/tmp_chunks/, a sibling of every
    domain root rather than nested inside one, since staging happens before
    the upload's eventual destination domain is known."""
    from backend.service.utils.path_utils import library_root
    return library_root() / TMP_CHUNKS_DIRNAME


def init_session(kind: str, title: str, files: list[dict], chunk_max_bytes: int) -> str:
    """Validate the declared manifest, create the staging dir, and return an
    unguessable upload_id. Raises ValueError on a malformed manifest."""
    import math
    import uuid

    if kind not in ("file", "folder", "set"):
        raise ValueError("kind must be 'file', 'folder', or 'set'.")
    if not files:
        raise ValueError("At least one file is required.")

    declared_total = 0
    slots: list[dict] = []
    for f in files:
        name = safe_basename(str(f.get("name") or ""))
        size = int(f.get("size") or 0)
        chunks = int(f.get("chunks") or 0)
        if not name:
            raise ValueError("Each file requires a name.")
        if size < 0 or chunks < 1:
            raise ValueError("Each file requires a positive chunk count and non-negative size.")
        # The client picks its own chunk size and never tells the server what it
        # is; chunk_max_bytes is only the ceiling the server will accept for any
        # single chunk. A legitimate chunk count therefore falls in a range, and
        # only counts outside that range indicate a lying manifest:
        #   floor  = ceil(size / chunk_max_bytes): fewer chunks than this cannot
        #            carry the declared size, because no one chunk may exceed the
        #            cap. Impossible declaration.
        #   ceiling = ceil(size / _MIN_CHUNK_BYTES): more chunks than this implies
        #            a chunk size below anything a real client would choose, i.e.
        #            a count inflated to exhaust staging entries rather than to
        #            move the declared bytes. Absurd declaration.
        # Dividing by chunk_max_bytes to get the UPPER bound (as the previous
        # revision did) conflates the server's per-chunk ceiling with the client's
        # actual chunk size, and so rejects every upload chunked finer than the
        # cap, which is every upload the bundled frontend produces over 8 MB.
        # Total bytes accepted are bounded separately and independently by the
        # cumulative check in store_chunk(), which is what actually caps disk use.
        # _MAX_CHUNKS_PER_FILE caps the absurdity ceiling so the per-count
        # overhead stays bounded even at the largest declared size, and the
        # ceiling applies whether or not a per-chunk cap is configured.
        min_required_chunks = max(1, math.ceil(size / chunk_max_bytes)) if chunk_max_bytes > 0 else 1
        max_allowed_chunks = min(
            max(1, math.ceil(size / _MIN_CHUNK_BYTES)), _MAX_CHUNKS_PER_FILE
        )
        if chunks < min_required_chunks:
            raise ValueError(
                f"Declared chunk count for '{name}' ({chunks}) is too low to carry its "
                f"declared size ({size} bytes) within the {chunk_max_bytes}-byte "
                f"per-chunk limit (at least {min_required_chunks} required)."
            )
        if chunks > max_allowed_chunks:
            raise ValueError(
                f"Declared chunk count for '{name}' ({chunks}) is implausible for its "
                f"declared size ({size} bytes) (max {max_allowed_chunks})."
            )
        declared_total += size
        # relative_path is sent by the frontend for every "folder"-kind upload
        # (see chunkedUpload.ts), so nested structure always survives the
        # transport; a "file"/"set" upload never sets it, so segments stays
        # None and reassemble() falls back to the flat basename in that case.
        raw_relative_path = f.get("relative_path")
        segments = sanitize_relative_path(str(raw_relative_path)) if raw_relative_path else None
        slots.append({
            "name": name, "size": size, "chunks": chunks, "received": set(),
            "received_bytes": 0, "segments": segments,
        })
    if declared_total > DEFAULT_MAX_BYTES:
        raise ValueError("Upload exceeds the maximum allowed size.")

    upload_id = uuid.uuid4().hex
    root = tmp_root()
    root.mkdir(parents=True, exist_ok=True)
    session_dir = resolve_under(root, upload_id)
    session_dir.mkdir(parents=True, exist_ok=False)

    with _lock:
        _sessions[upload_id] = {
            "id": upload_id,
            "kind": kind,
            "title": title,
            "dir": session_dir,
            "files": slots,
            "created_at": time.time(),
        }
    return upload_id


def get_session(upload_id: str) -> dict | None:
    with _lock:
        s = _sessions.get(upload_id)
        return dict(s) if s else None


async def store_chunk(
    upload_id: str, file_index: int, chunk_index: int, upload: UploadFile, chunk_max_bytes: int
) -> dict:
    """Persist one chunk to ``<dir>/<file_index>/<chunk_index>.part``.

    Raises KeyError for an unknown session and ValueError for an out-of-range
    index. Returns ``{"received": n, "total": m}`` for this file."""
    with _lock:
        session = _sessions.get(upload_id)
        if session is None:
            raise KeyError(upload_id)
        if not (0 <= file_index < len(session["files"])):
            raise ValueError("file_index out of range.")
        slot = session["files"][file_index]
        if not (0 <= chunk_index < slot["chunks"]):
            raise ValueError("chunk_index out of range.")
        session_dir: Path = session["dir"]

    file_dir = resolve_under(session_dir, str(file_index))
    file_dir.mkdir(parents=True, exist_ok=True)
    part_path = resolve_under(file_dir, f"{chunk_index}.part")
    # stream_upload_to_disk enforces the per-chunk cap and deletes the partial
    # part on violation; the running per-file total is enforced just below,
    # against the size declared at init (itself bounded against declared_total
    # in init_session).
    written_bytes = await stream_upload_to_disk(upload, part_path, chunk_max_bytes)

    with _lock:
        session = _sessions.get(upload_id)
        if session is None:
            raise KeyError(upload_id)
        slot = session["files"][file_index]
        if chunk_index not in slot["received"]:
            # Slack of one chunk_max_bytes accounts for the last chunk of a
            # file legitimately being smaller/larger than an even multiple —
            # this only rejects genuinely excess cumulative data, not a
            # normally-shaped final chunk.
            projected = slot["received_bytes"] + written_bytes
            if projected > slot["size"] + chunk_max_bytes:
                part_path.unlink(missing_ok=True)
                raise ValueError(
                    f"Cumulative bytes for file_index {file_index} exceed its declared size."
                )
            slot["received_bytes"] = projected
        slot["received"].add(chunk_index)
        return {"received": len(slot["received"]), "total": slot["chunks"]}


def all_received(upload_id: str) -> bool:
    with _lock:
        session = _sessions.get(upload_id)
        if session is None:
            return False
        return all(len(s["received"]) >= s["chunks"] for s in session["files"])


def total_size(upload_id: str) -> int:
    with _lock:
        session = _sessions.get(upload_id)
        if session is None:
            return 0
        return sum(int(s["size"]) for s in session["files"])


def reassemble(upload_id: str, domain_root: Path, job_id: str | None = None) -> ReassembledUpload:
    """Concatenate every file's chunks in order into a permanent slug dir under
    *domain_root* (the caller's resolved domain root), then drop the staging
    dir and session. On any failure the partial destination and the staging
    dir are both removed before re-raising.

    If *job_id* is given, periodically reports progress into core.jobs as
    bytes are written (throttled by elapsed time, see _PROGRESS_INTERVAL_SECONDS
    below), against the client-declared total from the manifest (same value
    total_size() returns). Declared size is untrusted client input, if it is
    0 (e.g. a malformed manifest), progress reporting is skipped entirely
    rather than dividing by zero; the caller still gets a normal complete/fail
    at the end regardless.
    """
    with _lock:
        session = _sessions.get(upload_id)
        if session is None:
            raise KeyError(upload_id)
        kind = session["kind"]
        title = session["title"]
        session_dir: Path = session["dir"]
        files = session["files"]

    base_title = (title or Path(files[0]["name"]).stem.replace("-", " ").title()).strip() or "upload"
    slug = unique_slug(base_title, lambda s: (domain_root / s).exists())
    domain_root.mkdir(parents=True, exist_ok=True)
    dest_dir = resolve_under(domain_root, slug)
    dest_dir.mkdir(parents=True, exist_ok=False)

    # Declared size drives progress percentage, same source of truth total_size()
    # uses. It's client-declared (untrusted) input, checked against actual
    # reassembled bytes per-file below, but 0 or bogus just means progress
    # reporting is skipped, it never affects correctness of the reassembly itself.
    declared_total_size = sum(int(s["size"]) for s in files)
    last_progress_at = time.time()

    written_paths: list[Path] = []
    total_bytes = 0
    try:
        for file_index, slot in enumerate(files):
            segments = slot.get("segments")
            dest_path = resolve_under(dest_dir, *segments) if segments else resolve_under(dest_dir, slot["name"])
            if dest_path.exists():
                raise HTTPException(
                    status_code=409,
                    detail=f"Two uploaded files are both named '{slot['name']}', rename one and retry.",
                )
            src_dir = resolve_under(session_dir, str(file_index))
            file_bytes = 0
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with dest_path.open("wb") as out:
                for chunk_index in range(slot["chunks"]):
                    part = resolve_under(src_dir, f"{chunk_index}.part")
                    if not part.exists():
                        raise ValueError(f"Missing chunk {chunk_index} for file {slot['name']}.")
                    data = part.read_bytes()
                    file_bytes += len(data)
                    total_bytes += len(data)
                    if total_bytes > DEFAULT_MAX_BYTES:
                        raise ValueError("Upload exceeds the maximum allowed size.")
                    out.write(data)
                    if job_id is not None and declared_total_size > 0:
                        now = time.time()
                        if now - last_progress_at >= _PROGRESS_INTERVAL_SECONDS:
                            last_progress_at = now
                            jobs.update(
                                job_id,
                                progress=total_bytes / declared_total_size,
                                message="Reassembling upload…",
                            )
            expected_size = int(slot["size"])
            if file_bytes == 0 or file_bytes != expected_size:
                raise ValueError(
                    f"Reassembled file '{slot['name']}' is {file_bytes} bytes, expected "
                    f"{expected_size} bytes as declared at upload start; the upload is "
                    "incomplete or one of its chunks was empty (e.g. a cloud-storage "
                    "placeholder with no local data)."
                )
            written_paths.append(dest_path)
    except Exception:
        shutil.rmtree(dest_dir, ignore_errors=True)
        _discard(upload_id, session_dir)
        raise

    _discard(upload_id, session_dir)
    return ReassembledUpload(
        kind=kind, title=base_title, dest_dir=dest_dir, paths=written_paths, total_bytes=total_bytes
    )


def abort(upload_id: str) -> None:
    """Client-initiated cancel: drop the staging dir and session."""
    with _lock:
        session = _sessions.pop(upload_id, None)
    if session is not None:
        shutil.rmtree(session["dir"], ignore_errors=True)


def _discard(upload_id: str, session_dir: Path) -> None:
    with _lock:
        _sessions.pop(upload_id, None)
    shutil.rmtree(session_dir, ignore_errors=True)


def sweep_orphans(ttl_seconds: float) -> int:
    """Remove staging dirs on disk older than ttl_seconds with no live session,
    reaping interrupted uploads (crash/restart lost the in-memory session). Returns
    the number of dirs removed."""
    root = tmp_root()
    if not root.is_dir():
        return 0
    with _lock:
        live_dirs = {str(s["dir"]) for s in _sessions.values()}
    now = time.time()
    removed = 0
    for child in root.iterdir():
        try:
            if str(child) in live_dirs:
                continue
            if not child.is_dir():
                continue
            if now - child.stat().st_mtime < ttl_seconds:
                continue
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
        except OSError:
            logger.warning("sweep_orphans: failed to inspect/remove %s", child)
            continue
    return removed
