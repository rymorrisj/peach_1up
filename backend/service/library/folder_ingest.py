"""Folder → library-item-or-set ingest logic.

Extracted from the upload-folder route so both the (removed) synchronous route
path and the chunked/background finalizer share one implementation. This is a
helper imported by upload_finalize (the orchestration entry point); it funnels
into the shared item/set ingester in service.library.items.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.service.library import items as lib_svc


def detect_disc_files(files: list[Path]) -> list[Path]:
    """Return a sorted list of .cue/.gdi files when 2+ exist (multi-disc signal),
    else []. Raises 422 when both .cue and .gdi are present (ambiguous format)."""
    cue_files = sorted(f for f in files if f.suffix.lower() == ".cue")
    gdi_files = sorted(f for f in files if f.suffix.lower() == ".gdi")

    if cue_files and gdi_files:
        raise HTTPException(
            status_code=422,
            detail=(
                "Folder contains both .cue and .gdi files. "
                "These formats imply different consoles and cannot be mixed in one multi-disc set. "
                "Upload only one format at a time."
            ),
        )

    disc_files = gdi_files or cue_files
    if len(disc_files) <= 1:
        return []
    return disc_files


def pick_folder_launch_file(files: list[Path]) -> Path:
    """Confirm at least one recognizable launch file exists; raise 422 otherwise."""
    for ext in (".gdi", ".cue", ".iso", ".chd", ".xiso", ".zip", ".exe"):
        hit = next((f for f in files if f.suffix.lower() == ext), None)
        if hit:
            return hit
    raise HTTPException(
        status_code=422,
        detail=(
            "No recognizable launch file found in the uploaded folder. "
            "Expected: .gdi, .cue, .iso, .chd, .xiso, .zip, or .exe."
        ),
    )


def ingest_folder(dest_dir: Path, written_paths: list[Path], title: str, db: Session):
    """Multi-disc set when 2+ disc files are present, else a single library item.

    Returns ``(result_type, entity)`` where result_type is ``"library_set"`` or
    ``"library_item"``. Raises the same 4xx HTTPExceptions as the ingester on a
    duplicate/collision — callers translate those (inline route) or mark the job
    failed (background finalizer).
    """
    disc_files = detect_disc_files(written_paths)
    if disc_files:
        library_set = lib_svc._create_multi_disc_set(disc_files, title.strip(), db)
        return "library_set", library_set

    pick_folder_launch_file(written_paths)
    item = lib_svc._ingest_media_entry(str(dest_dir), title.strip(), db)
    return "library_item", item
