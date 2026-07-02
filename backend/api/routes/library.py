import shutil
import threading
from pathlib import Path
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core import jobs, rate_limit
from backend.core.database import get_db
from backend.core.dependencies import get_active_user, get_filtered_item, get_filtered_library, require_permission
from backend.core.logger import get_logger
from backend.models.library import ImportResult, LibraryItem, LibraryItemCreate, LibraryItemRead, LibraryItemUpdate, ScanStatus, item_to_read, items_to_read_bulk
from backend.models.library_set import LibrarySet, LibrarySetItem, LibrarySetItemUpdate, LibrarySetRead, LibrarySetUpdate, set_to_read, sets_to_read_bulk
from backend.models.pagination import Page
from backend.models.media_restriction import MediaRestriction
from backend.models.user import User
from backend.service.library import items as lib_svc
from backend.service.library import enrich as enrich_svc
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL


class RestrictionsBody(BaseModel):
    user_ids: list[int]


class EnrichBody(BaseModel):
    entity_type: Literal["library_item", "library_set", "library_set_item"]
    entity_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    content_rating: Optional[str] = None
    metadata_source: Optional[str] = None
    cover_art_url: Optional[str] = None


class ScanImportBody(BaseModel):
    selected: list[str]


router = APIRouter(prefix="/api/v1/library", tags=["library"])
logger = get_logger(__name__)

_scan_lock = threading.Lock()
_scan_state: dict[str, Any] = {"running": False, "preview": [], "error": None, "job_id": None}

# Rate limits for endpoints that hit external services (TheGamesDB, cover-art
# fetch) or do expensive local work (filesystem scans, hash-dedup uploads).
# In-memory + per-IP, reusing backend.core.rate_limit exactly as auth.switch_user
# does — single-instance deployment, no shared store needed. Keyed on the
# immediate TCP peer, not X-Forwarded-For, for the same spoofing reason
# documented there.
_METADATA_RATE_LIMIT = 30
_METADATA_RATE_WINDOW_SECONDS = 60.0
_ENRICH_RATE_LIMIT = 30
_ENRICH_RATE_WINDOW_SECONDS = 60.0
_SCAN_RATE_LIMIT = 5
_SCAN_RATE_WINDOW_SECONDS = 60.0
_UPLOAD_RATE_LIMIT = 10
_UPLOAD_RATE_WINDOW_SECONDS = 60.0


def _enforce_rate_limit(bucket: str, request: Request, limit: int, window_seconds: float) -> None:
    """Raise 429 (with Retry-After) if the caller's IP has exceeded *limit* in
    *window_seconds* for *bucket*. No-op when allowed."""
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = rate_limit.check_and_record(f"{bucket}:{client_ip}", limit, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests, please slow down.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


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
    """Sum of file sizes under *root* using stat only (no hashing/detection).
    Fast even for large trees; used to classify a scan as inline vs nav-bell."""
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
    from sqlalchemy.orm import Session

    base_path = Path(directory).resolve()
    preview: list[dict] = []
    error_msg: str | None = None

    try:
        entries = scan_media_folders(base_path)
        total_entries = len(entries) or 1
        db = Session(get_engine())
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
    Bulk-inserts item records in chunks of 500. DOS/Win3.1 items no longer get a
    per-item drive here — they use the shared per-era environment C: image.
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


@router.get("/metadata-search")
def search_metadata(
    request: Request,
    name: str = Query(...),
    _: User = require_permission("is_owner"),
):
    _enforce_rate_limit("library-metadata", request, _METADATA_RATE_LIMIT, _METADATA_RATE_WINDOW_SECONDS)

    import httpx
    from backend.service.thegamesdb_client import search_games

    try:
        raw = search_games(name)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"TheGamesDB API error: {exc.response.status_code}",
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="TheGamesDB API request timed out.")

    games = raw.get("data", {}).get("games", [])
    if not isinstance(games, list):
        games = list(games.values()) if isinstance(games, dict) else []

    return {
        "results": [
            {
                "game_id": g.get("id"),
                "title": g.get("game_title"),
                "release_date": g.get("release_date"),
            }
            for g in games
            if g.get("id") is not None
        ]
    }


@router.get("/metadata-details")
def get_metadata_details(
    request: Request,
    game_id: int = Query(...),
    _: User = require_permission("is_owner"),
):
    _enforce_rate_limit("library-metadata", request, _METADATA_RATE_LIMIT, _METADATA_RATE_WINDOW_SECONDS)

    import httpx
    from backend.service.thegamesdb_client import get_game_details, get_game_images

    try:
        details_raw = get_game_details(game_id)
        images_raw = get_game_images(game_id)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"TheGamesDB API error: {exc.response.status_code}",
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="TheGamesDB API request timed out.")

    games_raw = details_raw.get("data", {}).get("games", {})
    if isinstance(games_raw, list):
        games_map = {str(g["id"]): g for g in games_raw if g.get("id") is not None}
    else:
        games_map = games_raw if isinstance(games_raw, dict) else {}
    game = games_map.get(str(game_id))
    if game is None and games_map:
        game = next(iter(games_map.values()), None)

    title: str | None = None
    release_date: str | None = None
    overview: str | None = None
    rating: str | None = None
    platform_id: int | None = None

    if game:
        title = game.get("game_title") or None
        release_date = game.get("release_date") or None
        overview = game.get("overview") or None
        rating = game.get("rating") or None
        raw_platform = game.get("platform")
        if raw_platform is not None:
            try:
                platform_id = int(raw_platform)
            except (ValueError, TypeError):
                pass

    images_data = images_raw.get("data", {})
    base_url_obj = images_data.get("base_url", {})
    all_images = images_data.get("images", {}).get(str(game_id), [])

    front_boxart = next(
        (img for img in all_images if img.get("type") == "boxart" and img.get("side") == "front"),
        None,
    )

    cover_art_url: str | None = None
    cover_art_thumb_url: str | None = None

    if front_boxart:
        filename = front_boxart.get("filename", "")
        original = (base_url_obj.get("original") or "").rstrip("/")
        thumb = (base_url_obj.get("thumb") or "").rstrip("/")
        clean_filename = filename.lstrip("/")
        if original and clean_filename:
            cover_art_url = f"{original}/{clean_filename}"
        if thumb and clean_filename:
            cover_art_thumb_url = f"{thumb}/{clean_filename}"

    return {
        "game_id": game_id,
        "title": title,
        "release_date": release_date,
        "overview": overview,
        "rating": rating,
        "platform_id": platform_id,
        "cover_art_url": cover_art_url,
        "cover_art_thumb_url": cover_art_thumb_url,
    }


@router.post("/enrich")
def enrich_library_entity(
    request: Request,
    body: EnrichBody,
    db: Session = Depends(get_db),
    _: User = require_permission("is_owner"),
):
    _enforce_rate_limit("library-enrich", request, _ENRICH_RATE_LIMIT, _ENRICH_RATE_WINDOW_SECONDS)

    entity, entity_type = enrich_svc.enrich_entity(
        body.entity_type,
        body.entity_id,
        title=body.title,
        description=body.description,
        publisher=body.publisher,
        year=body.year,
        content_rating=body.content_rating,
        metadata_source=body.metadata_source,
        cover_art_url=body.cover_art_url,
        db=db,
    )
    if entity_type == "library_item":
        return item_to_read(entity, db)
    if entity_type == "library_set":
        return set_to_read(entity, db)
    from backend.models.library_set import LibrarySetItemRead
    return LibrarySetItemRead.model_validate(entity)


@router.get("/sets", response_model=Page[LibrarySetRead])
def list_library_sets(
    era: str | None = None,
    profile_assigned: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    q = db.query(LibrarySet)
    if era:
        q = q.filter(LibrarySet.era == era)
    if profile_assigned is True:
        q = q.filter(LibrarySet.profile_id.isnot(None))
    elif profile_assigned is False:
        q = q.filter(LibrarySet.profile_id.is_(None))
    total = q.count()
    rows = q.order_by(LibrarySet.title).offset(offset).limit(limit).all()
    return Page(items=sets_to_read_bulk(rows, db), total=total, limit=limit, offset=offset)


@router.post("/sets", response_model=LibrarySetRead, status_code=201)
async def create_library_set(
    request: Request,
    title: str = Form(...),
    era: str = Form("unknown"),
    profile_id: Optional[int] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    """Create a multi-disc set from N uploaded files."""
    _enforce_rate_limit("library-upload", request, _UPLOAD_RATE_LIMIT, _UPLOAD_RATE_WINDOW_SECONDS)

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

    uploaded_paths: list[tuple[Path, Path]] = []
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
        for dest_dir, _ in uploaded_paths:
            shutil.rmtree(dest_dir, ignore_errors=True)
        raise

    from backend.service.utils.smart_media_detector import detect as _smart_detect
    from backend.service.utils.era_defaults import defaults_for_era, lookup_platform_and_profile

    launch_disc_path = uploaded_paths[0][1]
    _scan = _smart_detect(launch_disc_path)
    detected_era: str = _scan.era if _scan.era is not None else era

    detected_platform_id: int | None = None
    detected_profile_id: int | None = None
    if detected_era and detected_era != "unknown":
        _emulator_slug, _profile_era = defaults_for_era(detected_era)
        if _emulator_slug and _profile_era:
            detected_platform_id, detected_profile_id = lookup_platform_and_profile(
                _emulator_slug, _profile_era, db
            )

    resolved_profile_id = detected_profile_id if profile_id is None else profile_id

    library_set = LibrarySet(
        title=title,
        era=detected_era,
        platform_id=detected_platform_id,
        profile_id=resolved_profile_id,
    )
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


@router.get("/sets/{set_id}", response_model=LibrarySetRead)
def get_library_set(
    set_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_active_user),
):
    s = db.get(LibrarySet, set_id)
    if not s:
        raise HTTPException(status_code=404, detail="Library set not found.")
    return set_to_read(s, db)


@router.patch("/sets/{set_id}", response_model=LibrarySetRead)
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


@router.get("/sets/{set_id}/restrictions")
def get_set_restrictions(
    set_id: int,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    if not db.get(LibrarySet, set_id):
        raise HTTPException(status_code=404, detail="Library set not found.")
    rows = db.query(MediaRestriction).filter(MediaRestriction.library_set_id == set_id).all()
    return {"restricted_user_ids": [r.user_id for r in rows]}


@router.put("/sets/{set_id}/restrictions")
def set_set_restrictions(
    set_id: int,
    body: RestrictionsBody,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    if not db.get(LibrarySet, set_id):
        raise HTTPException(status_code=404, detail="Library set not found.")
    db.query(MediaRestriction).filter(MediaRestriction.library_set_id == set_id).delete()
    for user_id in body.user_ids:
        db.add(MediaRestriction(user_id=user_id, library_set_id=set_id))
    db.commit()
    return {"restricted_user_ids": body.user_ids}


@router.patch("/sets/{set_id}/items/{item_id}")
def update_library_set_item(
    set_id: int,
    item_id: int,
    body: LibrarySetItemUpdate,
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_library"),
):
    from backend.models.library_set import LibrarySetItemRead
    item = db.get(LibrarySetItem, item_id)
    if not item or item.set_id != set_id:
        raise HTTPException(status_code=404, detail="Item not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return LibrarySetItemRead.model_validate(item)


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

