import os
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core import process_registry
from backend.core.database import get_db
from backend.core.dependencies import require_permission
from backend.models.user import User
from backend.service.environments.environments import get_drive_images_bytes

router = APIRouter(prefix="/api/v1", tags=["health"])

_ERA_LABELS: dict[str, str] = {
    "dos": "DOS",
    "win95": "Windows 95",
    "win98": "Windows 98",
    "winxp": "Windows XP",
    "ps1": "PlayStation 1",
    "ps2": "PlayStation 2",
    "xbox": "Xbox",
    "nes": "NES",
    "snes": "SNES",
    "n64": "Nintendo 64",
    "dreamcast": "Dreamcast",
}


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for fname in filenames:
            fp = Path(dirpath) / fname
            if not fp.is_symlink():
                try:
                    total += fp.stat().st_size
                except OSError:
                    pass
    return total


class HealthResponse(BaseModel):
    status: str
    settings_initialised: bool
    database_reachable: bool
    active_processes: int


@router.get("/health", response_model=HealthResponse)
def health_check():
    settings_ok = False
    try:
        from backend.core.settings import get_settings
        get_settings()
        settings_ok = True
    except RuntimeError:
        pass

    db_ok = False
    try:
        from backend.core.database import get_engine
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    return HealthResponse(
        status="ok" if (settings_ok and db_ok) else "degraded",
        settings_initialised=settings_ok,
        database_reachable=db_ok,
        active_processes=process_registry.count(),
    )


# storage_footprint() walks several directory trees unboundedly (see
# _dir_size), so re-running it on every health-page poll is what causes the
# slow/occasionally-timed-out responses this cache exists to fix. Storage
# usage only moves in bursts (upload/import/delete, snapshot, install,
# drive create/delete) rather than continuously, so a short TTL is enough —
# 60s matches the sweep cadence rate_limit.py already uses elsewhere in this
# codebase. No lock: like emulator_catalog.py's module-global cache, a rare
# concurrent recompute is just wasted (idempotent) work, not a correctness
# issue.
_STORAGE_CACHE_TTL_SECONDS = 60.0
_storage_cache: dict | None = None
_storage_cache_time: float = 0.0


def _compute_storage_footprint(db: Session) -> dict:
    from backend.core.settings import get_base_path
    base = get_base_path()

    emu_size = _dir_size(base / "emulators")
    sys_size = _dir_size(base / "library" / "system")
    env_size = _dir_size(base / "emulators" / "86box" / "vms")

    appdata = os.environ.get("APPDATA", "")
    ext_size = _dir_size(Path(appdata) / "xemu") if appdata else 0

    db_path = base / "database" / "data" / "peach1up.db"
    try:
        db_bytes = db_path.stat().st_size
    except OSError:
        db_bytes = 0

    log_size = _dir_size(base / "logs")
    drive_size = get_drive_images_bytes(db)

    # era lives on the collection; file sizes on the leaf — join to break down by era.
    sized_rows = db.execute(
        text(
            "SELECT c.era, i.file_size_bytes FROM software_items i "
            "JOIN software_collections c ON c.id = i.library_collection_id "
            "WHERE i.file_size_bytes IS NOT NULL"
        )
    ).fetchall()
    unsized_count = db.execute(
        text("SELECT COUNT(*) FROM software_items WHERE file_size_bytes IS NULL")
    ).scalar() or 0

    era_map: dict[str, dict] = {}
    for era, size in sized_rows:
        key = era or "unknown"
        if key not in era_map:
            era_map[key] = {
                "era": key,
                "label": _ERA_LABELS.get(key, key.upper()),
                "size_bytes": 0,
                "count": 0,
            }
        era_map[key]["size_bytes"] += size
        era_map[key]["count"] += 1

    media_size = sum(e["size_bytes"] for e in era_map.values())
    breakdown = sorted(era_map.values(), key=lambda x: x["size_bytes"], reverse=True)

    categories = [
        {"key": "emulators",      "label": "Emulator Binaries",        "size_bytes": emu_size,   "breakdown": []},
        {"key": "library_media",  "label": "Library / Media",           "size_bytes": media_size, "breakdown": breakdown, "unsized_count": unsized_count},
        {"key": "library_system", "label": "Library / System",          "size_bytes": sys_size,   "breakdown": []},
        {"key": "drive_images",   "label": "Drive Images",              "size_bytes": drive_size, "breakdown": []},
        {"key": "environments",   "label": "Environments (86Box VMs)",  "size_bytes": env_size,   "breakdown": []},
        {"key": "external",       "label": "External (AppData)",        "size_bytes": ext_size,   "breakdown": []},
        {"key": "database",       "label": "Database",                  "size_bytes": db_bytes,   "breakdown": []},
        {"key": "logs",           "label": "Logs",                      "size_bytes": log_size,   "breakdown": []},
    ]

    return {
        "categories": categories,
        "total_bytes": sum(c["size_bytes"] for c in categories),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def _get_storage_footprint(db: Session, force_refresh: bool = False) -> dict:
    global _storage_cache, _storage_cache_time
    now = time.monotonic()
    if force_refresh or _storage_cache is None or (now - _storage_cache_time) >= _STORAGE_CACHE_TTL_SECONDS:
        _storage_cache = _compute_storage_footprint(db)
        _storage_cache_time = now
    return _storage_cache


@router.get("/health/storage")
def storage_footprint(
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_environments"),
):
    return _get_storage_footprint(db)


@router.post("/health/storage/rescan")
def rescan_file_sizes(
    db: Session = Depends(get_db),
    _: User = require_permission("can_edit_environments"),
):
    rows = db.execute(
        text(
            "SELECT id, media_path FROM software_items "
            "WHERE file_size_bytes IS NULL AND media_path IS NOT NULL"
        )
    ).fetchall()
    updated = 0
    for item_id, media_path in rows:
        try:
            size = os.path.getsize(media_path)
            db.execute(
                text("UPDATE software_items SET file_size_bytes = :size WHERE id = :id"),
                {"size": size, "id": item_id},
            )
            updated += 1
        except (OSError, TypeError):
            pass
    db.commit()
    _get_storage_footprint(db, force_refresh=True)
    return {"updated": updated}
