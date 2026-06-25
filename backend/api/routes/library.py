import shutil
import threading
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, get_filtered_item, get_filtered_library, require_permission
from backend.core.logger import get_logger
from backend.models.library import ImportResult, LibraryItem, LibraryItemCreate, LibraryItemRead, LibraryItemUpdate, ScanStatus
from backend.models.library_set import LibrarySet, LibrarySetItem, LibrarySetRead, LibrarySetUpdate, set_to_read
from backend.models.media_restriction import MediaRestriction
from backend.models.user import User
from backend.service.library import items as lib_svc
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL


class RestrictionsBody(BaseModel):
    user_ids: list[int]


class ScanImportBody(BaseModel):
    selected: list[str]


router = APIRouter(prefix="/api/v1/library", tags=["library"])
logger = get_logger(__name__)

_scan_lock = threading.Lock()
_scan_state: dict[str, Any] = {"running": False, "preview": [], "error": None}


@router.get("", response_model=list[LibraryItemRead])
def list_library(
    era: str | None = None,
    category: str | None = None,
    platform_id: int | None = None,
    tag: str | None = None,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    q = get_filtered_library(active_user, db)
    if era:
        q = q.filter(LibraryItem.era == era)
    if category:
        q = q.filter(LibraryItem.category == category)
    if platform_id is not None:
        q = q.filter(LibraryItem.platform_id == platform_id)
    if tag:
        from backend.models.tag import Tag
        q = q.join(LibraryItem.tags).filter(Tag.name == tag)
    return q.all()


@router.post("", response_model=LibraryItemRead, status_code=201)
def add_library_item(
    body: LibraryItemCreate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    try:
        return lib_svc._ingest_media_entry(
            body.media_path,
            body.title,
            db,
            override_profile_id=body.profile_id,
        )
    except lib_svc._ItemAlreadyExists:
        raise HTTPException(status_code=409, detail="This media path is already in the library.")
    except lib_svc._SlugCollision:
        raise HTTPException(status_code=409, detail="Import collided with a concurrent change, please retry.")


@router.post("/upload", response_model=LibraryItemRead, status_code=201)
async def upload_library_media(
    file: UploadFile,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    """Upload a game media file directly into the library.

    Browser uploads only ever provide bytes, never a real host path, so this
    writes straight into MEDIA_PATH and chains into the same ingest pipeline
    (_prepare_item) used by manual add and scan import — era detection,
    platform/profile auto-assignment, and dedup all apply identically.

    Before ingesting, the uploaded bytes are checked against existing files
    under MEDIA_PATH by content hash (find_existing_duplicate). If a match is
    found, the freshly-written copy is discarded and the existing file is
    reused instead of creating a second physical copy — surfaced to the
    caller via reused_existing_media in the response.
    """
    if not file.filename:
        raise HTTPException(status_code=422, detail="A filename is required.")

    from backend.core.settings import get_settings
    from backend.service.utils import media_dup_index
    from backend.service.utils.upload_utils import (
        DEFAULT_MAX_BYTES,
        begin_upload,
        find_existing_duplicate,
        stream_upload_to_disk,
    )

    svc = get_settings()
    max_bytes = int(svc.get("UPLOAD_MAX_BYTES", DEFAULT_MAX_BYTES) or DEFAULT_MAX_BYTES)
    media_root = Path(svc.get_env_var("MEDIA_PATH")).resolve()

    dest_dir, dest_path = begin_upload(media_root, file.filename)

    try:
        written = await stream_upload_to_disk(file, dest_path, max_bytes)
    except HTTPException:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    duplicate_path = find_existing_duplicate(media_root, dest_path, written)
    reused_existing = duplicate_path is not None
    ingest_path = duplicate_path if reused_existing else dest_path
    if reused_existing:
        shutil.rmtree(dest_dir, ignore_errors=True)

    title = ingest_path.stem.replace("-", " ").title()
    try:
        item = lib_svc._ingest_media_entry(str(ingest_path), title, db)
    except lib_svc._ItemAlreadyExists:
        shutil.rmtree(dest_dir, ignore_errors=True)
        media_dup_index.forget(dest_path)
        raise HTTPException(status_code=409, detail="This media path is already in the library.")
    except lib_svc._SlugCollision:
        shutil.rmtree(dest_dir, ignore_errors=True)
        media_dup_index.forget(dest_path)
        raise HTTPException(status_code=409, detail="Import collided with a concurrent change, please retry.")
    except HTTPException:
        shutil.rmtree(dest_dir, ignore_errors=True)
        media_dup_index.forget(dest_path)
        raise

    if reused_existing:
        from fastapi.responses import JSONResponse
        payload = LibraryItemRead.model_validate(item).model_dump(mode="json")
        payload["reused_existing_media"] = True
        return JSONResponse(status_code=201, content=payload)
    return item


@router.get("/scan/status", response_model=ScanStatus)
def scan_status():
    with _scan_lock:
        return dict(_scan_state)


def _resolve_scan_directory() -> Path:
    try:
        from backend.core.settings import get_settings
        media_path = get_settings().get("MEDIA_PATH", "") or ""
    except RuntimeError:
        media_path = ""
    if not media_path:
        raise HTTPException(
            status_code=400,
            detail="No media library path is configured. Set MEDIA_PATH in Settings before scanning.",
        )
    resolved = Path(media_path).resolve()
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Media library path does not exist or is not a directory.")
    return resolved


@router.post("/scan")
def trigger_scan(background_tasks: BackgroundTasks = BackgroundTasks()):
    with _scan_lock:
        if _scan_state["running"]:
            raise HTTPException(status_code=409, detail="A scan is already running.")
    resolved = _resolve_scan_directory()
    with _scan_lock:
        _scan_state["running"] = True
        _scan_state["preview"] = []
        _scan_state["error"] = None
    background_tasks.add_task(_run_scan, str(resolved))
    return {"started": True, "directory": str(resolved)}


def _run_scan(directory: str) -> None:
    """
    Phase 1: walk the media directory, dedup against the DB, run era detection,
    and store a preview list. Does NOT write to the DB.
    """
    from backend.core.database import get_engine
    from backend.service.library.items import best_detect_path
    from backend.service.utils.smart_media_detector import detect as _smart_detect
    from backend.service.utils.profile_builder import scan_media_folders
    from sqlalchemy.orm import Session

    base_path = Path(directory).resolve()
    preview: list[dict] = []
    error_msg: str | None = None

    try:
        entries = scan_media_folders(base_path)
        db = Session(get_engine())
        try:
            existing_folder_paths: set[str] = {
                str(Path(fp).resolve())
                for (fp,) in db.query(LibraryItem.folder_path)
                .filter(LibraryItem.folder_path.isnot(None))
                .all()
            }

            for entry in entries:
                is_loose = (
                    entry.executable_path is not None
                    and entry.executable_path.resolve().parent == base_path
                )
                is_zip = is_loose and entry.executable_path.suffix.lower() == ".zip"

                if is_loose:
                    # Dedup by the destination folder the file would be copied into
                    dest_folder = str((base_path / entry.executable_path.stem).resolve())
                    if dest_folder in existing_folder_paths:
                        continue
                    scan_path = entry.executable_path
                else:
                    folder = str(entry.folder_path.resolve())
                    if folder in existing_folder_paths:
                        continue
                    scan_path = entry.folder_path

                try:
                    if is_loose:
                        era_path = scan_path
                    else:
                        era_path = best_detect_path(
                            scan_path,
                            str(entry.executable_path) if entry.executable_path else None,
                        )
                    _scan = _smart_detect(era_path)
                    era_slug = _scan.era
                except Exception:
                    era_slug = None

                preview.append({
                    "title": entry.name,
                    "media_path": str(scan_path),
                    "detected_era": era_slug,
                    "is_loose": is_loose,
                    "is_zip": is_zip,
                })
        finally:
            db.close()

    except Exception as exc:
        logger.error("Scan failed: %s", exc, exc_info=True)
        error_msg = str(exc)
    finally:
        with _scan_lock:
            _scan_state["running"] = False
            _scan_state["preview"] = preview
            _scan_state["error"] = error_msg


@router.post("/scan/import", response_model=ImportResult)
def import_scan_results(
    body: ScanImportBody,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    """
    Phase 2: import the user-selected paths from the Phase 1 preview.
    Bulk-inserts item records in chunks of 500, then creates drives for PC-era items.
    """
    from backend.service.library.items import _DRIVE_ERAS, _ItemAlreadyExists, _prepare_item
    from backend.service.utils.drive_utils import create_drive_for_item

    with _scan_lock:
        preview_snapshot = list(_scan_state.get("preview", []))
    title_map: dict[str, str] = {p["media_path"]: p["title"] for p in preview_snapshot}

    used_slugs: set[str] = {
        s
        for (s,) in db.query(LibraryItem.slug).filter(LibraryItem.slug.isnot(None)).all()
    }

    prepared: list[dict] = []
    skipped = 0
    errors: list[dict] = []

    for path in body.selected:
        title = title_map.get(path) or Path(path).stem.replace("-", " ").title()
        try:
            row = _prepare_item(path, title, db, used_slugs=used_slugs)
            prepared.append(row)
        except _ItemAlreadyExists:
            skipped += 1
        except HTTPException as exc:
            errors.append({"path": path, "reason": exc.detail})
        except Exception as exc:
            logger.exception("Import: error preparing '%s'", path)
            errors.append({"path": path, "reason": str(exc)})

    if prepared:
        def _chunks(lst: list, n: int):
            for i in range(0, len(lst), n):
                yield lst[i: i + n]

        # Bulk-insert item records chunked at 500 to stay within SQLite variable limits.
        # used_slugs is seeded once above, so a concurrent import landing between
        # that seed and this commit can still collide on the unique slug index —
        # surface that as a clear retry signal instead of a raw 500.
        try:
            for chunk in _chunks(prepared, 500):
                db.bulk_insert_mappings(LibraryItem, chunk)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Import collided with a concurrent import, please retry.",
            )

        # Drive creation requires item IDs — query back PC-era items by their slugs
        drive_slugs = [r["slug"] for r in prepared if r["era"] in _DRIVE_ERAS]
        if drive_slugs:
            pc_items = db.query(LibraryItem).filter(LibraryItem.slug.in_(drive_slugs)).all()
            for pc_item in pc_items:
                try:
                    create_drive_for_item(pc_item, db)
                except Exception as exc:
                    logger.warning("Drive creation failed for '%s': %s", pc_item.title, exc)

    return {"imported": len(prepared), "skipped": skipped, "errors": errors}


@router.get("/by-slug/{slug}", response_model=LibraryItemRead)
def get_library_item_by_slug(
    slug: str,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    return get_filtered_item(slug, active_user, db)


@router.get("/{item_id}", response_model=LibraryItemRead)
def get_library_item(
    item_id: int,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    return get_filtered_item(item_id, active_user, db)


@router.patch("/{item_id}", response_model=LibraryItemRead)
def update_library_item(
    item_id: int,
    body: LibraryItemUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    return lib_svc.update_library_item(item_id, body, db)


@router.post("/{item_id}/flag-launch", response_model=LibraryItemRead)
def flag_launch(
    item_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_launch_media"),
):
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    item.launch_review_flagged = True
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/confirm-delete")
def issue_delete_token(
    item_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    token = confirmation_tokens.issue("library", item_id)
    return {"confirmation_token": token, "expires_in_seconds": TOKEN_TTL}


@router.delete("/{item_id}", status_code=204)
def delete_library_item(
    item_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    lib_svc.delete_library_item(item_id, confirmation_token, db)


@router.get("/{item_id}/restrictions")
def get_restrictions(
    item_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    if not db.get(LibraryItem, item_id):
        raise HTTPException(status_code=404, detail="Library item not found.")
    rows = db.query(MediaRestriction).filter(MediaRestriction.library_item_id == item_id).all()
    return {"restricted_user_ids": [r.user_id for r in rows]}


@router.put("/{item_id}/restrictions")
def set_restrictions(
    item_id: int,
    body: RestrictionsBody,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    if not db.get(LibraryItem, item_id):
        raise HTTPException(status_code=404, detail="Library item not found.")
    db.query(MediaRestriction).filter(MediaRestriction.library_item_id == item_id).delete()
    for user_id in body.user_ids:
        db.add(MediaRestriction(user_id=user_id, library_item_id=item_id))
    db.commit()
    return {"restricted_user_ids": body.user_ids}


# ---------------------------------------------------------------------------
# Library set routes
# ---------------------------------------------------------------------------

sets_router = APIRouter(prefix="/api/v1/library/sets", tags=["library-sets"])


@sets_router.get("", response_model=list[LibrarySetRead])
def list_library_sets(
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    sets = db.query(LibrarySet).order_by(LibrarySet.title).all()
    return [set_to_read(s, db) for s in sets]


@sets_router.post("", response_model=LibrarySetRead, status_code=201)
async def create_library_set(
    title: str = Form(...),
    era: str = Form("unknown"),
    profile_id: Optional[int] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    """Create a multi-disc set from N uploaded files.

    Files are stored under MEDIA_PATH using the same per-upload isolated
    subdirectory pattern as single-file uploads. Disc numbers are assigned
    by file submission order; launch_disk_id is set to disc 1's item.
    """
    from backend.core.settings import get_settings
    from backend.service.utils.upload_utils import (
        DEFAULT_MAX_BYTES,
        begin_upload,
        stream_upload_to_disk,
    )

    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required.")

    svc = get_settings()
    max_bytes = int(svc.get("UPLOAD_MAX_BYTES", DEFAULT_MAX_BYTES) or DEFAULT_MAX_BYTES)
    media_root = Path(svc.get_env_var("MEDIA_PATH")).resolve()

    uploaded_paths: list[tuple[Path, Path]] = []  # (dest_dir, dest_path)
    try:
        for f in files:
            if not f.filename:
                raise HTTPException(status_code=422, detail="Each file must have a filename.")
            dest_dir, dest_path = begin_upload(media_root, f.filename)
            try:
                await stream_upload_to_disk(f, dest_path, max_bytes)
            except HTTPException:
                shutil.rmtree(dest_dir, ignore_errors=True)
                raise
            except Exception as exc:
                shutil.rmtree(dest_dir, ignore_errors=True)
                raise HTTPException(status_code=500, detail=f"Upload failed for {f.filename}: {exc}") from exc
            uploaded_paths.append((dest_dir, dest_path))
    except HTTPException:
        # Clean up any already-written files before propagating.
        for dest_dir, _ in uploaded_paths:
            shutil.rmtree(dest_dir, ignore_errors=True)
        raise

    library_set = LibrarySet(title=title, era=era, profile_id=profile_id)
    db.add(library_set)
    db.flush()

    items: list[LibrarySetItem] = []
    for disc_number, (_, dest_path) in enumerate(uploaded_paths, start=1):
        item = LibrarySetItem(
            set_id=library_set.id,
            disc_number=disc_number,
            media_path=str(dest_path),
            file_size_bytes=dest_path.stat().st_size if dest_path.exists() else None,
        )
        db.add(item)
        items.append(item)
    db.flush()

    library_set.launch_disk_id = items[0].id
    db.add(library_set)
    db.commit()
    db.refresh(library_set)
    return set_to_read(library_set, db)


@sets_router.get("/{set_id}", response_model=LibrarySetRead)
def get_library_set(
    set_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    s = db.get(LibrarySet, set_id)
    if not s:
        raise HTTPException(status_code=404, detail="Library set not found.")
    return set_to_read(s, db)


@sets_router.patch("/{set_id}", response_model=LibrarySetRead)
def update_library_set(
    set_id: int,
    body: LibrarySetUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    from sqlalchemy import select as _select
    s = db.get(LibrarySet, set_id)
    if not s:
        raise HTTPException(status_code=404, detail="Library set not found.")
    if body.display_disk_id is not None:
        item_ids = set(
            db.execute(_select(LibrarySetItem.id).where(LibrarySetItem.set_id == set_id)).scalars().all()
        )
        if body.display_disk_id not in item_ids:
            raise HTTPException(status_code=422, detail="disc does not belong to this set.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return set_to_read(s, db)
