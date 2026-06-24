import shutil
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


def _heal_interrupted_rom_pack_clones() -> None:
    """Clean up a rom_pack target directory left half-populated by a git
    clone that was interrupted (e.g. backend restart mid-clone).

    install_registry's "cloning" state is in-memory only and resets to
    "idle" on restart, but the partial roms/ directory on disk survives —
    the next install attempt then fails with FileExistsError since
    clone_rom_pack() refuses to clone into a non-empty target. Detecting
    and clearing an interrupted clone here lets that retry succeed.
    """
    try:
        from backend.service.utils.emulator_catalog import load_catalog

        for entry in load_catalog():
            if entry.get("install_type") != "rom_pack":
                continue
            binary = entry.get("binary", "")
            if not binary:
                continue
            target = (get_base_path() / binary).resolve()
            if not target.is_dir():
                continue
            try:
                children = list(target.iterdir())
            except OSError:
                continue
            if not children:
                continue

            # An interrupted `git clone` leaves either a stale .git/index.lock
            # (killed during checkout) or a .git dir with nothing checked out
            # yet (killed during fetch). A completed clone has .git plus
            # checked-out ROM content and no lock file — leave that alone.
            git_dir = target / ".git"
            checked_out = any(c.name != ".git" for c in children)
            interrupted = (git_dir / "index.lock").exists() or (git_dir.is_dir() and not checked_out)
            if interrupted:
                shutil.rmtree(target, ignore_errors=True)
                logger.warning(
                    "Startup: removed half-populated rom pack directory for '%s' (%s) — "
                    "a previous clone was interrupted by a restart; ready to retry.",
                    entry.get("slug"), target,
                )
    except Exception as exc:
        logger.warning("Rom pack self-heal check failed: %s", exc)


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
