"""Chunked-upload transport & storage.

Single responsibility: accept a file (or folder of files) as an ordered series
of chunks staged under ``MEDIA_PATH/tmp_chunks/<upload_id>/``, then reassemble
them into their permanent location under ``MEDIA_PATH``. Ingest (dedup, era
detection, DB persistence) is NOT done here — that is upload_finalize's job,
which funnels into the shared ingester. Cleanup of the staging area is owned
entirely by this module (success, abort, and orphan sweep).

Sessions are in-memory (matching _scan_state / install_registry). A crash loses
the session but leaves the tmp dir on disk; sweep_orphans() reaps those.
"""
from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from backend.core.logger import get_logger
from backend.service.utils.path_utils import resolve_under, sanitize_filename
from backend.service.utils.slug_generator import unique_slug
from backend.service.utils.upload_utils import (
    DEFAULT_MAX_BYTES,
    TMP_CHUNKS_DIRNAME,
    stream_upload_to_disk,
)

logger = get_logger(__name__)

_lock = threading.Lock()
_sessions: dict[str, dict] = {}


@dataclass
class ReassembledUpload:
    kind: str  # "file" | "folder"
    title: str
    dest_dir: Path
    paths: list[Path]
    total_bytes: int


def tmp_root(media_root: Path) -> Path:
    return media_root / TMP_CHUNKS_DIRNAME


def init_session(media_root: Path, kind: str, title: str, files: list[dict]) -> str:
    """Validate the declared manifest, create the staging dir, and return an
    unguessable upload_id. Raises ValueError on a malformed manifest."""
    import uuid

    if kind not in ("file", "folder", "set"):
        raise ValueError("kind must be 'file', 'folder', or 'set'.")
    if not files:
        raise ValueError("At least one file is required.")

    declared_total = 0
    slots: list[dict] = []
    for f in files:
        name = sanitize_filename(str(f.get("name") or ""))
        size = int(f.get("size") or 0)
        chunks = int(f.get("chunks") or 0)
        if not name:
            raise ValueError("Each file requires a name.")
        if size < 0 or chunks < 1:
            raise ValueError("Each file requires a positive chunk count and non-negative size.")
        declared_total += size
        slots.append({"name": name, "size": size, "chunks": chunks, "received": set()})
    if declared_total > DEFAULT_MAX_BYTES:
        raise ValueError("Upload exceeds the maximum allowed size.")

    upload_id = uuid.uuid4().hex
    root = tmp_root(media_root)
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
    # part on violation; the running per-file/total cap is enforced at reassembly.
    await stream_upload_to_disk(upload, part_path, chunk_max_bytes)

    with _lock:
        session = _sessions.get(upload_id)
        if session is None:
            raise KeyError(upload_id)
        slot = session["files"][file_index]
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


def reassemble(upload_id: str, media_root: Path) -> ReassembledUpload:
    """Concatenate every file's chunks in order into a permanent slug dir under
    MEDIA_PATH, then drop the staging dir and session. On any failure the
    partial destination and the staging dir are both removed before re-raising.
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
    slug = unique_slug(base_title, lambda s: (media_root / s).exists())
    media_root.mkdir(parents=True, exist_ok=True)
    dest_dir = resolve_under(media_root, slug)
    dest_dir.mkdir(parents=True, exist_ok=False)

    written_paths: list[Path] = []
    total_bytes = 0
    try:
        for file_index, slot in enumerate(files):
            dest_path = resolve_under(dest_dir, slot["name"])
            src_dir = resolve_under(session_dir, str(file_index))
            with dest_path.open("wb") as out:
                for chunk_index in range(slot["chunks"]):
                    part = resolve_under(src_dir, f"{chunk_index}.part")
                    if not part.exists():
                        raise ValueError(f"Missing chunk {chunk_index} for file {slot['name']}.")
                    data = part.read_bytes()
                    total_bytes += len(data)
                    if total_bytes > DEFAULT_MAX_BYTES:
                        raise ValueError("Upload exceeds the maximum allowed size.")
                    out.write(data)
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


def sweep_orphans(media_root: Path, ttl_seconds: float) -> int:
    """Remove staging dirs on disk older than ttl_seconds with no live session —
    reaps interrupted uploads (crash/restart lost the in-memory session). Returns
    the number of dirs removed."""
    root = tmp_root(media_root)
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
            continue
    return removed
