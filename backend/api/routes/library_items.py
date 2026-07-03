import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core import jobs, rate_limit
from backend.core.database import get_db
from backend.core.dependencies import get_active_user, get_filtered_item, get_filtered_library, require_permission
from backend.core.logger import get_logger
from backend.models.library import (
    ImportResult, LibraryItem, LibraryItemCreate, LibraryItemRead, LibraryItemUpdate,
    ScanStatus, item_to_read, items_to_read_bulk,
)
from backend.models.library_set import LibrarySetItem
from backend.models.media_restriction import MediaRestriction
from backend.models.pagination import Page
from backend.models.user import User
from backend.service.library import items as lib_svc
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL

router = APIRouter(prefix="/api/v1/library", tags=["library"])
logger = get_logger(__name__)

_scan_lock = threading.Lock()
_scan_state: dict[str, Any] = {"running": False, "preview": [], "error": None, "job_id": None}

_SCAN_RATE_LIMIT = 5
_SCAN_RATE_WINDOW_SECONDS = 60.0


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


class ScanImportBody(BaseModel):
    selected: list[str]


@router.get("", response_model=Page[LibraryItemRead])
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
    q = get_filtered_library(active_user, db)
    if era:
        q = q.filter(LibraryItem.era == era)
    if category:
        q = q.filter(LibraryItem.category == category)
    if platform_id is not None:
        q = q.filter(LibraryItem.platform_id == platform_id)
    if profile_assigned is True:
        q = q.filter(LibraryItem.profile_id.isnot(None))
    elif profile_assigned is False:
        q = q.filter(LibraryItem.profile_id.is_(None))
    if tag:
        from backend.models.tag import Tag, EntityTag
        subq = (
            db.query(EntityTag.entity_id)
            .join(Tag, EntityTag.tag_id == Tag.id)
            .filter(EntityTag.entity_type == "library_item", Tag.name == tag)
            .subquery()
        )
        q = q.filter(LibraryItem.id.in_(subq))
    total = q.count()
    rows = q.order_by(LibraryItem.id).offset(offset).limit(limit).all()
    return Page(items=items_to_read_bulk(rows, db), total=total, limit=limit, offset=offset)


@router.post("", response_model=LibraryItemRead, status_code=201)
def add_library_item(
    body: LibraryItemCreate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    try:
        item = lib_svc._ingest_media_entry(
            body.media_path,
            body.title,
            db,
            override_profile_id=body.profile_id,
        )
        return item_to_read(item, db)
    except lib_svc._ItemAlreadyExists:
        raise HTTPException(status_code=409, detail="This media path is already in the library.")
    except lib_svc._SlugCollision:
        raise HTTPException(status_code=409, detail="Import collided with a concurrent change, please retry.")


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


@router.post("/scan")
def trigger_scan(request: Request, background_tasks: BackgroundTasks = BackgroundTasks()):
    _enforce_rate_limit("library-scan", request, _SCAN_RATE_LIMIT, _SCAN_RATE_WINDOW_SECONDS)
    with _scan_lock:
        if _scan_state["running"]:
            raise HTTPException(status_code=409, detail="A scan is already running.")
    resolved = _resolve_scan_directory()
    # Fast stat-only pre-pass classifies the scan so the UI knows immediately
    # whether to keep the inline modal (small) or drop to the nav bell (large).
    background = _dir_size_fast(resolved) > _scan_nav_threshold()
    job_id = jobs.create("scan", message="Scanning media library…")
    with _scan_lock:
        _scan_state["running"] = True
        _scan_state["preview"] = []
        _scan_state["error"] = None
        _scan_state["job_id"] = job_id
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

            _set_resolved = [
                str(Path(mp).resolve())
                for (mp,) in db.query(LibrarySetItem.media_path).all()
            ]
            existing_set_media_dirs: set[str] = {
                str(Path(p).parent) for p in _set_resolved
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
                    if dest_folder in existing_folder_paths or dest_folder in existing_set_media_dirs:
                        continue
                    scan_path = entry.executable_path
                else:
                    folder = str(entry.folder_path.resolve())
                    if folder in existing_folder_paths or folder in existing_set_media_dirs:
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
        if job_id is not None:
            if error_msg is not None:
                jobs.fail(job_id, error_msg)
            else:
                jobs.complete(
                    job_id,
                    result={"preview_count": len(preview)},
                    message=f"Scan complete — {len(preview)} item(s) ready to import.",
                )


@router.post("/scan/import", response_model=ImportResult)
def import_scan_results(
    body: ScanImportBody,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    """
    Phase 2: import the user-selected paths from the Phase 1 preview.
    Bulk-inserts item records in chunks of 500. DOS/Win3.1 items are not given a
    per-item drive here — the drive is created lazily on first launch
    (drive_hydration.hydrate_drive_for_entity).
    """
    from backend.service.library.items import _ItemAlreadyExists, _prepare_item

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

    return {"imported": len(prepared), "skipped": skipped, "errors": errors}


@router.get("/by-slug/{slug}", response_model=LibraryItemRead)
def get_library_item_by_slug(
    slug: str,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    return item_to_read(get_filtered_item(slug, active_user, db), db)


@router.get("/{item_id}", response_model=LibraryItemRead)
def get_library_item(
    item_id: int,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_active_user),
):
    return item_to_read(get_filtered_item(item_id, active_user, db), db)


@router.patch("/{item_id}", response_model=LibraryItemRead)
def update_library_item(
    item_id: int,
    body: LibraryItemUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    return item_to_read(lib_svc.update_library_item(item_id, body, db), db)


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
    return item_to_read(item, db)


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
