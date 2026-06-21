from datetime import datetime, timezone

from backend.core import install_registry
from backend.core.logger import get_logger
from backend.core.settings import get_base_path

logger = get_logger(__name__)


def _sync_first_run_from_db(db) -> None:
    from backend.api.middleware.security import set_first_run_complete
    from backend.models.settings import Settings as SettingsModel
    row = db.get(SettingsModel, "first_run_complete")
    if row and row.value == "true":
        set_first_run_complete()


def _cleanup_stale_sessions(db) -> None:
    try:
        from backend.models import LaunchHistory
        stale = db.query(LaunchHistory).filter(LaunchHistory.ended_at.is_(None)).all()
        for session in stale:
            session.ended_at = datetime.now(timezone.utc)
            session.exit_code = -1
        db.flush()
        if stale:
            logger.info("Startup: closed %d stale launch session(s)", len(stale))
    except Exception as exc:
        db.rollback()
        logger.warning("Startup session cleanup failed: %s", exc)


def _flag_corrupt_platform_working_paths(db) -> None:
    try:
        from backend.models import Platform
        corrupt = (
            db.query(Platform)
            .filter(Platform.working_image_path.like("%.cfg"))
            .all()
        )
        for p in corrupt:
            logger.warning(
                "Platform %s (%s) has a .cfg file as working_image_path — "
                "this record was created by the broken provisioner and must be re-registered",
                p.id,
                p.name,
            )
            if p.status != "degraded":
                p.status = "degraded"
        db.flush()
    except Exception as exc:
        db.rollback()
        logger.warning("Corrupt working_image_path check failed: %s", exc)


def _ensure_owner_user() -> None:
    """Log a warning if no owner account exists; first-run web flow handles creation."""
    from backend.core.database import get_engine
    from backend.models.user import User
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=get_engine())
    with session_factory() as db:
        has_owner = db.query(User).filter(User.is_owner.is_(True)).count() > 0

    if not has_owner:
        logger.warning(
            "No owner account found. Complete the first-run setup in the web interface."
        )


def _ensure_default_paths() -> None:
    base = get_base_path()
    lib = base / "library"
    for d in [
        lib / "media",
        lib / "system",
        lib / "system" / "bios",
        lib / "system" / "roms",
        lib / "system" / "os",
        lib / "system" / "roms" / "86box",
        lib / "system" / "profiles",
    ]:
        d.mkdir(parents=True, exist_ok=True)


def _sync_detected_emulator_paths() -> None:
    try:
        from backend.service.utils.emulator_catalog import detect_and_sync_all
        detect_and_sync_all()
        logger.info("Startup: emulator configure pass complete")
    except Exception as exc:
        logger.warning("Startup emulator path sync failed: %s", exc)


def _scan_installed_emulators() -> None:
    try:
        from backend.service.utils.emulator_catalog import load_catalog
        from backend.service.utils.emulator_installer import detect_binary
        catalog = load_catalog()
        detected = 0
        for entry in catalog:
            slug = entry["slug"]
            path = detect_binary(slug)
            if path is not None:
                install_registry.set_status(slug, "complete", install_path=str(path))
                logger.info("Startup: %s detected at %s", slug, path)
                detected += 1
            else:
                logger.info("Startup: %s not detected", slug)
        logger.info("Startup: %d/%d emulators detected", detected, len(catalog))
    except Exception as exc:
        logger.warning("Startup emulator scan failed: %s", exc)
