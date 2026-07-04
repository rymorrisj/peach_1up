"""Folder → library-collection ingest logic.

Extracted from the upload-folder route so both the (removed) synchronous route
path and the chunked/background finalizer share one implementation. This is a
helper imported by upload_finalize (the orchestration entry point); it funnels
into the shared collection ingester in service.library.items. Every upload —
single disc or multi-disc — becomes a LibraryCollection (single-disc is a
collection-of-one).
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


def select_disc_pointer_files(files: list[Path]) -> list[Path]:
    """Order-preserving, companion-aware disc selection for explicit multi-disc
    "set" uploads, where a disc can be more than one file (e.g. .cue + .bin).

    Returns the .cue/.gdi pointer files in their original (client-declared)
    order when any are present — every other file rides along in the shared
    destination folder unregistered as a companion. Falls back to returning
    *files* unchanged when no .cue/.gdi is present (each file is already its
    own disc, e.g. .iso/.chd). Raises 422 for a mixed .cue/.gdi upload, same as
    detect_disc_files — unlike that function, this one does not sort, since the
    caller must preserve the client's declared disc order.
    """
    cue_files = [f for f in files if f.suffix.lower() == ".cue"]
    gdi_files = [f for f in files if f.suffix.lower() == ".gdi"]

    if cue_files and gdi_files:
        raise HTTPException(
            status_code=422,
            detail=(
                "Upload contains both .cue and .gdi files. "
                "These formats imply different consoles and cannot be mixed in one multi-disc set. "
                "Upload only one format at a time."
            ),
        )

    pointer_files = cue_files or gdi_files
    return pointer_files if pointer_files else files


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
    """Multi-disc collection when 2+ disc files are present, else a collection-of-one.

    Returns ``(result_type, collection)`` where result_type is always
    ``"library_collection"``. Raises the same 4xx HTTPExceptions as the ingester
    on a duplicate/collision — callers translate those (inline route) or mark the
    job failed (background finalizer).
    """
    disc_files = detect_disc_files(written_paths)
    if disc_files:
        collection = lib_svc._create_multi_disc_collection(disc_files, title.strip(), db)
        return "library_collection", collection

    pick_folder_launch_file(written_paths)
    collection = lib_svc._ingest_media_entry(str(dest_dir), title.strip(), db)
    return "library_collection", collection
