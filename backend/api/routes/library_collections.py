import threading
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.constants_generated import EraValue
from backend.core import jobs, rate_limit
from backend.core.database import get_db
from backend.core.dependencies import (
    get_active_user, get_filtered_collection, get_filtered_collections, require_permission,
)
from backend.core.logger import get_logger
from backend.models.library import (
    ImportResult, LibraryCollection, LibraryCollectionCreate, LibraryCollectionRead,
    LibraryCollectionUpdate, LibraryItem, LibraryItemRead, LibraryItemReorder, LibraryItemUpdate,
    ScanStatus, collection_to_read, collections_to_read_bulk,
)
from backend.models.media_restriction import MediaRestriction
from backend.models.pagination import Page
from backend.models.user import User
from backend.service.library import items as lib_svc
from backend.service.library import path_import
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL
from backend.service.utils.path_utils import allowed_browse_roots, is_within_roots, normalise_path
from backend.service.utils.upload_utils import DEFAULT_BACKGROUND_THRESHOLD_BYTES, DEFAULT_MAX_BYTES

router = APIRouter(prefix="/api/v1", tags=["library"])
logger = get_logger(__name__)

# Guards re-entry ("one scan running at a time") only — no preview or other
# scan output is cached here. A finished scan's results live solely in the
# core.jobs result payload; this state is purely a running/error/job_id flag.
_scan_lock = threading.Lock()
_scan_running = False
_scan_error: str | None = None
_scan_job_id: str | None = None

_SCAN_RATE_LIMIT = 5
_SCAN_RATE_WINDOW_SECONDS = 60.0

_PATH_IMPORT_RATE_LIMIT = 10
_PATH_IMPORT_RATE_WINDOW_SECONDS = 60.0


def _enforce_rate_limit(bucket: str, request: Request, limit: int, window_seconds: float) -> None:
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = rate_limit.check_and_record(f"{bucket}:{client_ip}", limit, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests, please slow down.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


class RestrictionsBody(BaseModel):
    user_ids: list[int]


class ScanImportItem(BaseModel):
    path: str
    title: str
    era: EraValue | None = None


class ScanImportBody(BaseModel):
    selected: list[ScanImportItem]


# ---------------------------------------------------------------------------
# List + create
# ---------------------------------------------------------------------------


@router.get("/library", response_model=Page[LibraryCollectionRead])
def list_library(
    era: str | None = None,
    category: str | None = None,
    platform_id: int | None = None,
    tag: str | None = None,
    profile_assigned: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    q = get_filtered_collections(active_user, db)
    if era:
        q = q.filter(LibraryCollection.era == era)
    if category:
        q = q.filter(LibraryCollection.category == category)
    if platform_id is not None:
        q = q.filter(LibraryCollection.platform_id == platform_id)
    if profile_assigned is True:
        q = q.filter(LibraryCollection.profile_id.isnot(None))
    elif profile_assigned is False:
        q = q.filter(LibraryCollection.profile_id.is_(None))
    if tag:
        from backend.models.tag import Tag, EntityTag
        subq = (
            db.query(EntityTag.entity_id)
            .join(Tag, EntityTag.tag_id == Tag.id)
            .filter(EntityTag.entity_type == "library_collection", Tag.name == tag)
            .subquery()
        )
        q = q.filter(LibraryCollection.id.in_(subq))
    total = q.count()
    rows = q.order_by(LibraryCollection.id).offset(offset).limit(limit).all()
    return Page(items=collections_to_read_bulk(rows, db), total=total, limit=limit, offset=offset)


@router.post("/library", response_model=LibraryCollectionRead, status_code=201)
def add_library_collection(
    body: LibraryCollectionCreate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    """Create a collection-of-one from a single media path."""
    try:
        collection = lib_svc._ingest_media_entry(
            body.media_path,
            body.title,
            db,
            override_profile_id=body.profile_id,
        )
        return collection_to_read(collection, db)
    except lib_svc._ItemAlreadyExists:
        raise HTTPException(status_code=409, detail="This media path is already in the library.")
    except lib_svc._SlugCollision as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class ImportFromPathBody(BaseModel):
    source_path: str
    title: str
    delete_original: bool = False


@router.post("/library/import-from-path")
def import_from_path(
    body: ImportFromPathBody,
    request: Request,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    """Import a file or folder already on the server's filesystem — the same
    kind of real, absolute path GET /api/v1/filesystem/browse resolves — into
    the library. This is a second transport alongside chunked browser upload,
    for when the source is already local to the server: no chunked transfer,
    and (opt-in, per delete_original) the source can be deleted afterward,
    which a browser upload can never do since the browser never exposes the
    source's real path. See service.library.path_import for the copy-then-
    optionally-delete implementation.
    """
    _enforce_rate_limit("library-path-import", request, _PATH_IMPORT_RATE_LIMIT, _PATH_IMPORT_RATE_WINDOW_SECONDS)

    try:
        resolved = normalise_path(body.source_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Re-validated here even though the frontend only ever offers paths the
    # file browser itself returned — the backend must not trust that a path
    # in a request body actually came from that browser call.
    if not is_within_roots(resolved, allowed_browse_roots()):
        raise HTTPException(status_code=400, detail="Path is outside the permitted directories.")
    if resolved.is_symlink():
        raise HTTPException(status_code=400, detail="Symlinked paths cannot be imported directly.")
    if not resolved.exists():
        raise HTTPException(status_code=400, detail="Path does not exist.")

    # _prepare_item carries this same guard, but it only ever sees the
    # already-copied path under MEDIA_PATH — by then the (potentially huge)
    # copy has already happened and would silently duplicate an OS image into
    # the library. Check the original source here, before staging starts.
    from backend.models.platform import Platform
    incoming_norm = resolved.as_posix()
    for base_path, working_path in db.query(Platform.base_image_path, Platform.working_image_path).all():
        if (base_path and Path(base_path).resolve().as_posix() == incoming_norm) or (
            working_path and Path(working_path).resolve().as_posix() == incoming_norm
        ):
            raise HTTPException(
                status_code=409,
                detail="Path is an OS environment image and cannot be added as a library item.",
            )

    title = body.title.strip() or resolved.stem.replace("-", " ").title()

    size = path_import.source_size(resolved)
    if size > DEFAULT_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Import exceeds the maximum allowed size ({DEFAULT_MAX_BYTES // 1024 ** 3} GB).",
        )

    from backend.core.settings import get_settings
    svc = get_settings()
    media_root = Path(svc.get_env_var("MEDIA_PATH")).resolve()
    try:
        threshold = int(svc.get("UPLOAD_BACKGROUND_THRESHOLD_BYTES", DEFAULT_BACKGROUND_THRESHOLD_BYTES)
                         or DEFAULT_BACKGROUND_THRESHOLD_BYTES)
    except (TypeError, ValueError):
        threshold = DEFAULT_BACKGROUND_THRESHOLD_BYTES

    if size > threshold:
        job_id = jobs.create("upload", message=f"Importing \"{title}\"…")
        background_tasks.add_task(
            path_import.import_background,
            str(resolved), title, str(media_root), job_id, body.delete_original,
        )
        return JSONResponse(status_code=202, content={"job_id": job_id, "status": "processing"})

    try:
        result = path_import.import_inline(resolved, title, media_root, db, body.delete_original)
    except lib_svc._ItemAlreadyExists:
        raise HTTPException(status_code=409, detail="This item is already in the library.")
    except lib_svc._SlugCollision as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse(status_code=201, content=result)


# ---------------------------------------------------------------------------
# Scan / import (ingest — every import creates a collection-of-one + leaf)
# ---------------------------------------------------------------------------


@router.get("/library/scan/status", response_model=ScanStatus)
def scan_status():
    with _scan_lock:
        return {"running": _scan_running, "job_id": _scan_job_id, "error": _scan_error}


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


def _dir_size_fast(root: Path) -> int:
    """Sum of file sizes under *root* using stat only (no hashing/detection)."""
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _scan_nav_threshold() -> int:
    from backend.core.settings import get_settings
    from backend.service.utils.upload_utils import DEFAULT_SCAN_NAV_THRESHOLD_BYTES
    try:
        return int(get_settings().get("SCAN_NAV_THRESHOLD_BYTES", DEFAULT_SCAN_NAV_THRESHOLD_BYTES)
                   or DEFAULT_SCAN_NAV_THRESHOLD_BYTES)
    except (TypeError, ValueError):
        return DEFAULT_SCAN_NAV_THRESHOLD_BYTES


def _check_known_items_findable(db: Session) -> None:
    """Fail loud if a DB-known item's file has vanished from disk (moved or
    renamed outside Peach 1UP) instead of letting scan silently work around it.
    Scan is stateless now — it re-walks disk every call and relies on
    original_name/media_path to reconcile against existing rows, so a
    known item that can no longer be found on disk is surfaced immediately
    rather than dropped without explanation."""
    rows = db.query(LibraryItem.media_path, LibraryItem.original_name).filter(
        LibraryItem.media_path.isnot(None)
    ).all()
    for media_path, original_name in rows:
        if not Path(media_path).exists():
            name = original_name or Path(media_path).name
            raise HTTPException(
                status_code=400,
                detail=f"Cannot find {name} — did you move or rename it?",
            )


@router.post("/library/scan")
def trigger_scan(
    request: Request,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    global _scan_running, _scan_error, _scan_job_id
    _enforce_rate_limit("library-scan", request, _SCAN_RATE_LIMIT, _SCAN_RATE_WINDOW_SECONDS)
    with _scan_lock:
        if _scan_running:
            raise HTTPException(status_code=409, detail="A scan is already running.")
    resolved = _resolve_scan_directory()
    _check_known_items_findable(db)
    # Fast stat-only pre-pass classifies the scan so the UI knows immediately
    # whether to keep the inline modal (small) or drop to the nav bell (large).
    background = _dir_size_fast(resolved) > _scan_nav_threshold()
    job_id = jobs.create("scan", message="Scanning media library…")
    with _scan_lock:
        _scan_running = True
        _scan_error = None
        _scan_job_id = job_id
    background_tasks.add_task(_run_scan, str(resolved), job_id)
    return {"started": True, "directory": str(resolved), "job_id": job_id, "background": background}


def _run_scan(directory: str, job_id: str | None = None) -> None:
    """
    Phase 1: walk the media directory, dedup against the DB, run era detection,
    and store a preview list. Does NOT write to the DB. Reports progress into the
    core.jobs registry so a large scan can surface in the nav-bell notification
    centre.
    """
    from backend.core.database import get_engine
    from backend.service.library.items import best_detect_path
    from backend.service.utils.smart_media_detector import detect as _smart_detect
    from backend.service.utils.profile_builder import scan_media_folders
    from sqlalchemy.orm import Session as _Session

    global _scan_running, _scan_error

    base_path = Path(directory).resolve()
    preview: list[dict] = []
    error_msg: str | None = None

    try:
        entries = scan_media_folders(base_path)
        total_entries = len(entries) or 1
        db = _Session(get_engine())
        try:
            existing_folder_paths: set[str] = {
                str(Path(fp).resolve())
                for (fp,) in db.query(LibraryItem.folder_path)
                .filter(LibraryItem.folder_path.isnot(None))
                .all()
            }
            existing_media_dirs: set[str] = {
                str(Path(mp).resolve().parent)
                for (mp,) in db.query(LibraryItem.media_path).all()
            }

            for _idx, entry in enumerate(entries):
                if job_id is not None and _idx % 10 == 0:
                    jobs.update(job_id, progress=_idx / total_entries,
                                message=f"Scanned {_idx} of {total_entries} folders…")
                is_loose = (
                    entry.executable_path is not None
                    and entry.executable_path.resolve().parent == base_path
                )
                is_zip = is_loose and entry.executable_path.suffix.lower() == ".zip"

                if is_loose:
                    # Dedup by the destination folder the file would be copied into
                    dest_folder = str((base_path / entry.executable_path.stem).resolve())
                    if dest_folder in existing_folder_paths or dest_folder in existing_media_dirs:
                        continue
                    scan_path = entry.executable_path
                else:
                    folder = str(entry.folder_path.resolve())
                    if folder in existing_folder_paths or folder in existing_media_dirs:
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
                except Exception as exc:
                    logger.warning("Scan: era detection failed for '%s': %s", scan_path, exc, exc_info=True)
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
            _scan_running = False
            _scan_error = error_msg
        if job_id is not None:
            if error_msg is not None:
                jobs.fail(job_id, error_msg)
            else:
                jobs.complete(
                    job_id,
                    result={"preview": preview},
                    message=f"Scan complete — {len(preview)} item(s) ready to import.",
                )


@router.post("/library/scan/import", response_model=ImportResult)
def import_scan_results(
    body: ScanImportBody,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    """
    Phase 2: import the user-selected paths from the Phase 1 preview. Each import
    creates a collection-of-one + leaf. DOS/Win3.1 collections are not given a
    drive here — the drive is created lazily on first launch
    (drive_hydration.hydrate_drive_for_entity).
    """
    from backend.service.library.items import _ItemAlreadyExists, _persist_collection_of_one, _prepare_item

    used_slugs: set[str] = {
        s
        for (s,) in db.query(LibraryCollection.slug).filter(LibraryCollection.slug.isnot(None)).all()
    }

    imported = 0
    skipped = 0
    errors: list[dict] = []

    for item in body.selected:
        path = item.path
        title = item.title or Path(path).stem.replace("-", " ").title()
        try:
            # item.era is the era the scan preview auto-detected (echoed back by
            # the client), not a user selection — pass it as detected_era so the
            # per-item detection_reason is preserved instead of being overwritten
            # with a fixed "Selected by user during import" string.
            row = _prepare_item(path, title, db, used_slugs=used_slugs, detected_era=item.era)
        except _ItemAlreadyExists:
            skipped += 1
            continue
        except HTTPException as exc:
            errors.append({"path": path, "reason": exc.detail})
            continue
        except Exception as exc:
            logger.exception("Import: error preparing '%s'", path)
            errors.append({"path": path, "reason": str(exc)})
            continue
        try:
            _persist_collection_of_one(row, db)
            db.commit()
            imported += 1
        except IntegrityError:
            db.rollback()
            used_slugs.discard(row.get("slug"))
            errors.append({"path": path, "reason": "Import collided with a concurrent import, please retry."})
        except Exception as exc:
            # A single item's persist failure must never abort the rest of the
            # batch or leave a poisoned session for the next iteration — same
            # per-item containment as the _prepare_item exception handling above.
            db.rollback()
            used_slugs.discard(row.get("slug"))
            logger.exception("Import: error persisting '%s'", path)
            errors.append({"path": path, "reason": str(exc)})

    return {"imported": imported, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Single-collection read / update / delete
# ---------------------------------------------------------------------------


@router.get("/librarycollection/by-slug/{slug}", response_model=LibraryCollectionRead)
def get_collection_by_slug(
    slug: str,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    return collection_to_read(get_filtered_collection(slug, active_user, db), db)


@router.get("/librarycollection/{collection_id}", response_model=LibraryCollectionRead)
def get_collection(
    collection_id: int,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    return collection_to_read(get_filtered_collection(collection_id, active_user, db), db)


@router.patch("/librarycollection/{collection_id}", response_model=LibraryCollectionRead)
def update_collection(
    collection_id: int,
    body: LibraryCollectionUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    return collection_to_read(lib_svc.update_library_collection(collection_id, body, db), db)


@router.post("/librarycollection/{collection_id}/flag-launch", response_model=LibraryCollectionRead)
def flag_launch(
    collection_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_launch_media"),
):
    collection = db.get(LibraryCollection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Library collection not found.")
    collection.launch_review_flagged = True
    db.commit()
    db.refresh(collection)
    return collection_to_read(collection, db)


@router.post("/librarycollection/{collection_id}/confirm-delete")
def issue_delete_token(
    collection_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    collection = db.get(LibraryCollection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Library collection not found.")
    token = confirmation_tokens.issue("library", collection_id)
    return {"confirmation_token": token, "expires_in_seconds": TOKEN_TTL}


@router.delete("/librarycollection/{collection_id}", status_code=204)
def delete_collection(
    collection_id: int,
    confirmation_token: str = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    lib_svc.delete_library_collection(collection_id, confirmation_token, db)


@router.get("/librarycollection/{collection_id}/restrictions")
def get_restrictions(
    collection_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    if not db.get(LibraryCollection, collection_id):
        raise HTTPException(status_code=404, detail="Library collection not found.")
    rows = db.query(MediaRestriction).filter(MediaRestriction.library_collection_id == collection_id).all()
    return {"restricted_user_ids": [r.user_id for r in rows]}


@router.put("/librarycollection/{collection_id}/restrictions")
def set_restrictions(
    collection_id: int,
    body: RestrictionsBody,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    if not db.get(LibraryCollection, collection_id):
        raise HTTPException(status_code=404, detail="Library collection not found.")
    db.query(MediaRestriction).filter(MediaRestriction.library_collection_id == collection_id).delete()
    for user_id in body.user_ids:
        db.add(MediaRestriction(user_id=user_id, library_collection_id=collection_id))
    db.commit()
    return {"restricted_user_ids": body.user_ids}


@router.patch("/librarycollection/{collection_id}/items/reorder", response_model=LibraryCollectionRead)
def reorder_collection_items(
    collection_id: int,
    body: LibraryItemReorder,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    # Registered before the "/items/{leaf_id}" route below: {leaf_id} has no
    # type constraint in the path itself, so a literal "reorder" segment
    # would otherwise match that route first and 422 on int conversion.
    collection = lib_svc.reorder_library_items(collection_id, body, db)
    return collection_to_read(collection, db)


@router.patch("/librarycollection/{collection_id}/items/{leaf_id}", response_model=LibraryItemRead)
def update_collection_leaf(
    collection_id: int,
    leaf_id: int,
    body: LibraryItemUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    return LibraryItemRead.model_validate(
        lib_svc.update_library_leaf(collection_id, leaf_id, body, db)
    )
