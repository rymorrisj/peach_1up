import threading
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.constants_generated import PlatformValue
from backend.core import install_registry, jobs, rate_limit
from backend.core.database import get_db
from backend.core.dependencies import (
    get_active_user,
    get_filtered_game_item_bundle,
    get_filtered_game_item_bundles,
    reject_old_era_query_param,
    require_permission,
)
from backend.core.logger import get_logger
from backend.models.game import (
    GameCoverCandidate,
    GameCoverFromMedia,
    ImportResult,
    GameItemBundle,
    GameItemBundleCreate,
    GameItemBundleRead,
    GameItemBundleUpdate,
    GameItem,
    GameItemRead,
    GameItemReorder,
    GameItemUpdate,
    ScanStatus,
    game_item_bundle_to_read,
    game_item_bundles_to_read_bulk,
)
from backend.models.pagination import Page
from backend.models.user import UserItem
from backend.service.games import cover_from_media
from backend.service.games import items as lib_svc
from backend.service.games import path_import
from backend.service.media.rating_change_guard import (
    game_removal_effects,
    require_rating_change_confirmation,
)
from backend.service.utils import confirmation_tokens
from backend.service.utils.confirmation_tokens import TOKEN_TTL
from backend.service.utils.path_utils import allowed_browse_roots, is_within_roots, normalise_path
from backend.service.utils.sort_utils import apply_bundle_sort
from backend.service.utils.upload_utils import DEFAULT_MAX_BYTES

router = APIRouter(prefix="/api/v1", tags=["games"])
logger = get_logger(__name__)

# Guards re-entry ("one scan running at a time") only. Scan state itself
# (running/error/job_id) lives entirely in core.jobs now, not in a parallel
# set of module globals, this lock's scope is narrowed to just the
# check-then-create race in trigger_scan below, not a running/error mirror.
_scan_lock = threading.Lock()

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


class ScanImportItem(BaseModel):
    path: str
    title: str
    platform: PlatformValue | None = None


class ScanImportBody(BaseModel):
    selected: list[ScanImportItem]


# ---------------------------------------------------------------------------
# List + create
# ---------------------------------------------------------------------------


@router.get("/game-items", response_model=Page[GameItemBundleRead], dependencies=[Depends(reject_old_era_query_param)])
def list_game_items(
    platform: str | None = None,
    category: str | None = None,
    environment_item_id: int | None = None,
    tag: str | None = None,
    profile_assigned: bool | None = None,
    sort: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    q = get_filtered_game_item_bundles(active_user, db)
    if platform:
        q = q.filter(GameItemBundle.platform == platform)
    if category:
        q = q.filter(GameItemBundle.category == category)
    if environment_item_id is not None:
        q = q.filter(GameItemBundle.environment_item_id == environment_item_id)
    if profile_assigned is True:
        q = q.filter(GameItemBundle.profile_item_id.isnot(None))
    elif profile_assigned is False:
        q = q.filter(GameItemBundle.profile_item_id.is_(None))
    if tag:
        from backend.models.tag import Tag, EntityTag

        subq = (
            db.query(EntityTag.entity_id)
            .join(Tag, EntityTag.tag_id == Tag.id)
            .filter(EntityTag.entity_type == "game_item_bundle", Tag.name == tag)
            .subquery()
        )
        q = q.filter(GameItemBundle.id.in_(subq))
    total = q.count()
    rows = apply_bundle_sort(q, GameItemBundle, sort).offset(offset).limit(limit).all()
    return Page(
        items=game_item_bundles_to_read_bulk(rows, db, viewer=active_user), total=total, limit=limit, offset=offset
    )


@router.post("/game-items", response_model=GameItemBundleRead, status_code=201)
def create_game_item_bundle(
    body: GameItemBundleCreate,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_game"),
):
    """Create a collection-of-one from a single media path."""
    try:
        collection = lib_svc._ingest_media_entry(
            body.file_path,
            body.title,
            db,
            override_profile_item_id=body.profile_item_id,
        )
        return game_item_bundle_to_read(collection, db, viewer=active_user)
    except lib_svc._ItemAlreadyExists:
        raise HTTPException(status_code=409, detail="This media path is already in the library.")
    except lib_svc._SlugCollision as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class ImportFromPathBody(BaseModel):
    source_path: str
    title: str
    delete_original: bool = False


@router.post("/game-items/import-from-path")
def import_from_path(
    body: ImportFromPathBody,
    request: Request,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_game"),
):
    """Import a file or folder already on the server's filesystem, the same
    kind of real, absolute path GET /api/v1/filesystem/browse resolves, into
    the library. This is a second transport alongside chunked browser upload,
    for when the source is already local to the server: no chunked transfer,
    and (opt-in, per delete_original) the source can be deleted afterward,
    which a browser upload can never do since the browser never exposes the
    source's real path. See service.games.path_import for the copy-then-
    optionally-delete implementation.
    """
    _enforce_rate_limit("library-path-import", request, _PATH_IMPORT_RATE_LIMIT, _PATH_IMPORT_RATE_WINDOW_SECONDS)

    try:
        resolved = normalise_path(body.source_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Re-validated here even though the frontend only ever offers paths the
    # file browser itself returned, the backend must not trust that a path
    # in a request body actually came from that browser call.
    if not is_within_roots(resolved, allowed_browse_roots()):
        raise HTTPException(status_code=400, detail="Path is outside the permitted directories.")
    if resolved.is_symlink():
        raise HTTPException(status_code=400, detail="Symlinked paths cannot be imported directly.")
    if not resolved.exists():
        raise HTTPException(status_code=400, detail="Path does not exist.")

    # _prepare_item carries this same guard, but it only ever sees the
    # already-copied path under SOFTWARE_PATH, by then the (potentially huge)
    # copy has already happened and would silently duplicate an OS image into
    # the library. Check the original source here, before staging starts.
    from backend.models.environment import EnvironmentItem

    incoming_norm = resolved.as_posix()
    for base_path, working_path in db.query(EnvironmentItem.base_image_path, EnvironmentItem.working_image_path).all():
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
            detail=f"Import exceeds the maximum allowed size ({DEFAULT_MAX_BYTES // 1024**3} GB).",
        )

    from backend.service.utils.path_utils import library_domain_root

    # Games-only route today, so the destination domain is always "games".
    domain_root = library_domain_root("games")

    # Always a background job, same "one job lifecycle" decision as chunked
    # upload, no inline/background size split. _ItemAlreadyExists/_SlugCollision
    # are reported into the job via jobs.fail() inside import_background
    # itself, not translated into an HTTP response here.
    job_id = jobs.create("upload", message=f'Importing "{title}"…')
    background_tasks.add_task(
        path_import.import_background,
        str(resolved),
        title,
        str(domain_root),
        job_id,
        body.delete_original,
    )
    return JSONResponse(status_code=202, content={"job_id": job_id, "status": "processing"})


# ---------------------------------------------------------------------------
# Scan / import (ingest, every import creates a collection-of-one + leaf)
# ---------------------------------------------------------------------------


def _latest_scan_job() -> dict | None:
    """Most recent "scan"-kind job, if any have ever run this process
    lifetime. jobs.list_recent() returns oldest-first, so the last match is
    the most recent."""
    scans = [j for j in jobs.list_recent() if j["kind"] == "scan"]
    return scans[-1] if scans else None


@router.get("/game-items/scan/status", response_model=ScanStatus)
def scan_status(_: UserItem = require_permission("can_manage_game")):
    job = _latest_scan_job()
    if job is None:
        return {"running": False, "job_id": None, "error": None}
    return {
        "running": job["status"] in ("processing", "cancelling"),
        "job_id": job["id"],
        "error": job["error"],
    }


@router.post("/game-items/scan/{job_id}/cancel")
def cancel_scan(job_id: str, _: UserItem = require_permission("can_manage_game")):
    """Cooperative cancellation for an in-flight scan job. Flags the job so
    _run_scan's loop exits at its next check, then returns the updated job
    status immediately, the job itself only reaches the terminal 'cancelled'
    status once the background task actually notices and stops (poll
    /api/v1/jobs/{job_id} to observe that transition)."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["kind"] != "scan":
        raise HTTPException(status_code=400, detail="Job is not a library scan.")
    updated = jobs.request_cancel(job_id)
    if updated is None:
        raise HTTPException(status_code=409, detail="Scan is not currently running.")
    return updated


def _resolve_scan_directory(domain: str) -> Path:
    """Resolve the scan root for one library domain ("games" or "apps"). Only
    "games" is reachable today (this route is games-only), but the resolver
    itself is domain-aware so a future Apps scan endpoint can call it
    correctly without any change here."""
    try:
        from backend.core.settings import get_settings

        software_path = get_settings().get("SOFTWARE_PATH", "") or ""
    except RuntimeError:
        software_path = ""
    if not software_path:
        raise HTTPException(
            status_code=400,
            detail="No software library path is configured. Set SOFTWARE_PATH in Settings before scanning.",
        )
    from backend.service.utils.path_utils import library_domain_root

    resolved = library_domain_root(domain)
    if not resolved.is_dir():
        logger.warning("Scan root for domain %r is not a directory: %s", domain, resolved)
        raise HTTPException(status_code=400, detail=f"The '{domain}' library directory is not available.")
    return resolved


def _check_known_items_findable(db: Session) -> None:
    """Fail loud if a DB-known item's file has vanished from disk (moved or
    renamed outside Peach 1UP) instead of letting scan silently work around it.
    Scan is stateless now, it re-walks disk every call and relies on
    original_name/file_path to reconcile against existing rows, so a
    known item that can no longer be found on disk is surfaced immediately
    rather than dropped without explanation.

    Runs inside _run_scan's background task, not the trigger_scan route
    itself: for a large, long-lived library this is a full DB-row scan plus
    one Path.exists() per row, exactly the kind of pre-flight work that used
    to make the route synchronously block before returning job_id. Raising
    HTTPException here still produces a clean message, _run_scan's own
    generic except Exception clause reads str(exc), which for an HTTPException
    is just its detail (Starlette's HTTPException stores detail as the
    exception's own message)."""
    rows = db.query(GameItem.file_path, GameItem.original_name).filter(GameItem.file_path.isnot(None)).all()
    for file_path, original_name in rows:
        if not Path(file_path).exists():
            name = original_name or Path(file_path).name
            raise HTTPException(
                status_code=400,
                detail=f"Cannot find {name}, did you move or rename it?",
            )


@router.post("/game-items/scan")
def trigger_scan(
    request: Request,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    _: UserItem = require_permission("can_manage_game"),
):
    _enforce_rate_limit("library-scan", request, _SCAN_RATE_LIMIT, _SCAN_RATE_WINDOW_SECONDS)
    # Single lock scope covers the whole check-then-create sequence, so two
    # concurrent trigger_scan calls can't both observe "no active scan" and
    # both start one. _resolve_scan_directory is cheap (a settings lookup
    # plus an is_dir() check, not a directory walk) so it stays synchronous
    # here too, its 400s (unconfigured/missing SOFTWARE_PATH) are still an
    # immediate response, not a job that fails. The expensive pre-flight
    # check (_check_known_items_findable) is NOT run here, see _run_scan.
    with _scan_lock:
        active = _latest_scan_job()
        if active is not None and active["status"] in ("processing", "cancelling"):
            raise HTTPException(status_code=409, detail="A scan is already running.")
        # This route is games-only today (mounted at /api/v1/game-items/scan).
        resolved = _resolve_scan_directory("games")
        job_id = jobs.create("scan", message="Scanning media library…")
    background_tasks.add_task(_run_scan, str(resolved), job_id)
    return {"started": True, "directory": str(resolved), "job_id": job_id}


def _run_scan(directory: str, job_id: str | None = None) -> None:
    """
    Phase 1: walk the media directory, dedup against the DB, run platform detection,
    and store a preview list. Does NOT write to the DB. Reports progress into the
    core.jobs registry so a large scan can surface in the nav-bell notification
    centre.
    """
    from backend.core.database import get_engine
    from backend.service.games.items import best_detect_path
    from backend.service.utils.detection import resolve_ps3_target
    from backend.service.utils.detection.formatscout_adapter import detect_media
    from backend.service.utils.profile_builder import scan_media_folders
    from sqlalchemy.orm import Session as _Session

    base_path = Path(directory).resolve()
    preview: list[dict] = []
    error_msg: str | None = None
    cancelled = False

    try:
        db = _Session(get_engine())
        try:
            # Moved here from the trigger_scan route (see _check_known_items_findable's
            # docstring): this is the pre-flight validation that used to block
            # the route's response until it finished walking every known
            # item's file_path.
            _check_known_items_findable(db)
            entries = scan_media_folders(base_path)
            total_entries = len(entries) or 1
            existing_folder_paths: set[str] = {
                str(Path(fp).resolve())
                for (fp,) in db.query(GameItem.folder_path).filter(GameItem.folder_path.isnot(None)).all()
            }
            existing_media_dirs: set[str] = {
                str(Path(mp).resolve().parent) for (mp,) in db.query(GameItem.file_path).all()
            }

            dir_cache: dict[Path, list[Path]] = {}
            for _idx, entry in enumerate(entries):
                # Checked every iteration (an Event.is_set() check is
                # effectively free) so cancellation is noticed between any two
                # folders, not just every 10th, the progress update itself
                # stays throttled below since that one does real work (a job
                # dict mutation under a lock).
                if job_id is not None and jobs.cancel_requested(job_id):
                    cancelled = True
                    break
                if job_id is not None and _idx % 10 == 0:
                    jobs.update(
                        job_id, progress=_idx / total_entries, message=f"Scanned {_idx} of {total_entries} folders…"
                    )
                is_loose = entry.executable_path is not None and entry.executable_path.resolve().parent == base_path
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
                        platform_slug = detect_media(scan_path, dir_cache).platform
                    else:
                        # best_detect_path() resolves a PS3 folder structurally
                        # and hands back the folder itself; formatscout has no
                        # PS3 structural check of its own anymore (see
                        # ps3.py's module docstring), so detect_media() on
                        # that folder always reports platform=None. Trust the
                        # structural resolver directly, same as the ingest
                        # detect stage in items.py._detect_directory_source.
                        ps3_target = resolve_ps3_target(scan_path)
                        if ps3_target is not None:
                            platform_slug = ps3_target.platform
                        else:
                            platform_path = best_detect_path(
                                scan_path,
                                str(entry.executable_path) if entry.executable_path else None,
                            )
                            platform_slug = detect_media(platform_path, dir_cache).platform
                except Exception as exc:
                    logger.warning("Scan: platform detection failed for '%s': %s", scan_path, exc, exc_info=True)
                    platform_slug = None

                preview.append(
                    {
                        "title": entry.name,
                        "file_path": str(scan_path),
                        "detected_platform": platform_slug,
                        "is_loose": is_loose,
                        "is_zip": is_zip,
                    }
                )
        finally:
            db.close()

    except Exception as exc:
        logger.error("Scan failed: %s", exc, exc_info=True)
        error_msg = str(exc)
    finally:
        # Running/error state lives in the job itself now (core.jobs), there
        # is no separate module-global mirror left to update.
        if job_id is not None:
            if cancelled:
                jobs.cancel(job_id, message="Scan cancelled.")
            elif error_msg is not None:
                jobs.fail(job_id, error_msg)
            else:
                jobs.complete(
                    job_id,
                    result={"preview": preview},
                    message=f"Scan complete, {len(preview)} item(s) ready to import.",
                )


@router.post("/game-items/scan/import", response_model=ImportResult)
def import_scan_results(
    body: ScanImportBody,
    db: Session = Depends(get_db),
    _: UserItem = require_permission("can_manage_game"),
):
    """
    Phase 2: import the user-selected paths from the Phase 1 preview. Each import
    creates a collection-of-one + leaf. DOS collections are not given a
    drive here, the drive is created lazily on first launch
    (drive_hydration.hydrate_drive_for_entity).
    """
    from backend.service.games.items import (
        _ingest_transaction,
        _ItemAlreadyExists,
        _persist_multi_disc_collection,
        _prepare_item,
        _SlugCollision,
    )

    used_slugs: set[str] = {s for (s,) in db.query(GameItemBundle.slug).filter(GameItemBundle.slug.isnot(None)).all()}

    imported = 0
    skipped = 0
    errors: list[dict] = []

    for item in body.selected:
        path = item.path
        title = item.title or Path(path).stem.replace("-", " ").title()
        # Each item gets its own _ingest_transaction (undo_ops is per-item, not
        # shared across the batch): a staging failure on item N must roll back
        # and replay only item N's filesystem moves, not abort or undo the items
        # already committed before it. This route already treats the batch as
        # independent per-item units (skip/continue on failure), not all-or-
        # nothing, so per-item transaction scope matches existing semantics.
        undo_ops: list = []
        collection_fields: dict | None = None
        try:
            with _ingest_transaction(db, undo_ops):
                # item.platform is the platform the scan preview auto-detected, echoed
                # back by the client from an earlier request. _prepare_item no
                # longer trusts it for the persisted platform or detection_reason
                # (it always re-detects against the file on disk at import
                # time instead), it is passed through only as a directory-
                # file-selection hint for multi-format folders. See
                # _prepare_item's docstring for why the client echo is not
                # trusted.
                collection_fields, leaf_rows = _prepare_item(
                    path,
                    title,
                    db,
                    used_slugs=used_slugs,
                    detected_platform=item.platform,
                    _undo_stack=undo_ops,
                )
                _persist_multi_disc_collection(collection_fields, leaf_rows, db)
                db.commit()
            imported += 1
        except _ItemAlreadyExists:
            skipped += 1
        except _SlugCollision as exc:
            if collection_fields is not None:
                used_slugs.discard(collection_fields.get("slug"))
            errors.append({"path": path, "reason": str(exc)})
        except HTTPException as exc:
            errors.append({"path": path, "reason": exc.detail})
        except Exception as exc:
            # A single item's failure must never abort the rest of the batch or
            # leave a poisoned session for the next iteration.
            if collection_fields is not None:
                used_slugs.discard(collection_fields.get("slug"))
            logger.exception(
                "Import: error %s '%s'",
                "persisting" if collection_fields is not None else "preparing",
                path,
            )
            errors.append({"path": path, "reason": str(exc)})

    return {"imported": imported, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Single-collection read / update / delete
# ---------------------------------------------------------------------------


@router.get("/game-item-bundle/by-slug/{slug}", response_model=GameItemBundleRead)
def get_game_item_bundle_by_slug(
    slug: str,
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    return game_item_bundle_to_read(get_filtered_game_item_bundle(slug, active_user, db), db, viewer=active_user)


@router.get("/game-item-bundle/{collection_id}", response_model=GameItemBundleRead)
def get_game_item_bundle(
    collection_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = Depends(get_active_user),
):
    return game_item_bundle_to_read(
        get_filtered_game_item_bundle(collection_id, active_user, db),
        db,
        viewer=active_user,
    )


@router.patch("/game-item-bundle/{collection_id}", response_model=GameItemBundleRead)
def update_game_item_bundle(
    collection_id: int,
    body: GameItemBundleUpdate,
    confirm_rating_change: bool = Query(False),
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_game"),
):
    # Same 404 as a missing bundle, so a hidden item is neither patchable nor confirmed to exist.
    get_filtered_game_item_bundle(collection_id, active_user, db)
    return game_item_bundle_to_read(
        lib_svc.update_library_collection(
            collection_id,
            body,
            db,
            confirm_rating_change=confirm_rating_change,
        ),
        db,
        viewer=active_user,
    )


@router.post("/game-item-bundle/{collection_id}/verify", response_model=GameItemBundleRead)
def verify_game_item_bundle(
    collection_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_game"),
):
    """Re-verify every disc in this collection, distinct from
    POST /api/v1/game-item/{leaf_id}/verify (single disc only). Per-disc
    verification means only this endpoint reflects the whole game's true
    state for a multi-disc collection."""
    get_filtered_game_item_bundle(collection_id, active_user, db)
    return game_item_bundle_to_read(
        lib_svc.reverify_library_collection(collection_id, db),
        db,
        viewer=active_user,
    )


@router.post("/game-item-bundle/{collection_id}/flag-launch", response_model=GameItemBundleRead)
def flag_launch(
    collection_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_launch_media"),
):
    # can_launch_media is on by default, so this must not hand a capped
    # account the full read of a hidden game: same 404 as a missing one.
    collection = get_filtered_game_item_bundle(collection_id, active_user, db)
    collection.launch_review_flagged = True
    db.commit()
    db.refresh(collection)
    return game_item_bundle_to_read(collection, db, viewer=active_user)


def _xiso_convert_key(collection_id: int) -> str:
    return f"xiso-convert-{collection_id}"


def _run_xiso_conversion(key: str, media_path: str) -> None:
    from backend.service.utils.extract_xiso import convert_dvd_rip_to_xiso

    try:
        output = convert_dvd_rip_to_xiso(Path(media_path))
        install_registry.set_status(key, "complete", install_path=str(output))
    except Exception as exc:
        install_registry.set_status(key, "error", error=str(exc))
        logger.error("extract-xiso conversion failed for %s: %s", media_path, exc)


@router.post("/game-item-bundle/{collection_id}/convert-xiso")
def start_xiso_conversion(
    collection_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_launch_media"),
):
    """Convert the collection's current launch disc from a raw Xbox DVD rip to xiso.

    User-triggered only, never runs automatically. extract-xiso rewrites the
    file in place under its original filename; its own automatic '<name>.old'
    backup of the pre-rewrite file is left on disk as the safety net (never
    deleted here). No launch-target update is needed since the filename
    doesn't change. Runs in the background because multi-GB rips take a
    while; poll the status endpoint below for completion.
    """
    from backend.service.launch.launchable_resolver import resolve_launchable

    collection = get_filtered_game_item_bundle(collection_id, active_user, db)
    if collection.platform != "xbox":
        raise HTTPException(status_code=400, detail="extract-xiso conversion only applies to Xbox media.")

    key = _xiso_convert_key(collection_id)
    if install_registry.get_status(key).get("status") == "converting":
        raise HTTPException(status_code=409, detail="Conversion already in progress for this item.")

    try:
        entity = resolve_launchable(collection_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    install_registry.set_status(key, "converting")
    background_tasks.add_task(_run_xiso_conversion, key, entity.media_path)
    return {"status": "converting"}


@router.get("/game-item-bundle/{collection_id}/convert-xiso/status")
def get_xiso_conversion_status(
    collection_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_launch_media"),
):
    # output_path names the game's media file, so a hidden bundle 404s.
    get_filtered_game_item_bundle(collection_id, active_user, db)
    status = install_registry.get_status(_xiso_convert_key(collection_id))
    return {
        "status": status["status"],
        "error": status.get("error"),
        "output_path": status.get("install_path"),
    }


@router.post("/game-item-bundle/{collection_id}/confirm-delete")
def issue_delete_token(
    collection_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_game"),
):
    # Same 404 as a missing bundle, so a hidden bundle is neither deletable
    # nor confirmed to exist.
    get_filtered_game_item_bundle(collection_id, active_user, db)
    token = confirmation_tokens.issue("game", collection_id)
    return {"confirmation_token": token, "expires_in_seconds": TOKEN_TTL}


@router.delete("/game-item-bundle/{collection_id}", status_code=204)
def delete_game_item_bundle(
    collection_id: int,
    confirmation_token: str = Query(...),
    confirm_rating_change: bool = Query(False),
    delete_media: bool | None = Query(None),
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_game"),
):
    """*delete_media*, when given, is the delete-confirm checkbox's choice
    for this delete only. It travels with the confirmed DELETE so nothing is
    persisted when the user cancels the rating-change prompt; omitted, the
    bundle's delete_media_override (else the global setting) applies."""
    get_filtered_game_item_bundle(collection_id, active_user, db)
    # Deleting the game drops every link it has, which can loosen the
    # effective rating of linked media. Checked before the service consumes
    # the single-use token, so a 409 leaves the token valid for the retry.
    require_rating_change_confirmation(
        game_removal_effects(collection_id, db),
        confirm_rating_change=confirm_rating_change,
        action="game delete",
    )
    lib_svc.delete_library_collection(collection_id, confirmation_token, db, delete_media=delete_media)


@router.patch("/game-item-bundle/{collection_id}/items/reorder", response_model=GameItemBundleRead)
def reorder_game_item_bundle_items(
    collection_id: int,
    body: GameItemReorder,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_game"),
):
    # Registered before the "/items/{leaf_id}" route below: {leaf_id} has no
    # type constraint in the path itself, so a literal "reorder" segment
    # would otherwise match that route first and 422 on int conversion.
    get_filtered_game_item_bundle(collection_id, active_user, db)
    collection = lib_svc.reorder_library_items(collection_id, body, db)
    return game_item_bundle_to_read(collection, db, viewer=active_user)


@router.patch("/game-item-bundle/{collection_id}/items/{leaf_id}", response_model=GameItemRead)
def update_game_item(
    collection_id: int,
    leaf_id: int,
    body: GameItemUpdate,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_game"),
):
    get_filtered_game_item_bundle(collection_id, active_user, db)
    return GameItemRead.model_validate(lib_svc.update_library_leaf(collection_id, leaf_id, body, db))


@router.get("/game-item-bundle/{collection_id}/cover-candidates", response_model=list[GameCoverCandidate])
def list_cover_candidates(
    collection_id: int,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_game"),
):
    """Image files from the media linked to this game that the caller may
    see, for the cover picker."""
    game = get_filtered_game_item_bundle(collection_id, active_user, db)
    return [
        GameCoverCandidate(
            media_item_id=item.id,
            title=item.title,
            asset_type=item.asset_type,
            file_url=item.file_url,
            media_item_bundle_id=item.media_item_bundle_id,
            is_current=cover_from_media.current_cover_matches(game, item),
        )
        for item in cover_from_media.linked_image_items(game.id, active_user, db)
    ]


@router.put("/game-item-bundle/{collection_id}/cover-art", response_model=GameItemRead)
def set_cover_from_media(
    collection_id: int,
    body: GameCoverFromMedia,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("can_manage_game"),
):
    """Use a linked media image as the cover of the disc the card shows.
    Clearing a cover is PATCH .../items/{leaf_id} with an explicit null."""
    game = get_filtered_game_item_bundle(collection_id, active_user, db)
    return GameItemRead.model_validate(
        cover_from_media.set_cover_from_media_item(game, body.media_item_id, active_user, db)
    )
