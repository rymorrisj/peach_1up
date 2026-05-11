import asyncio
import json
import logging
import os
import platform
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI

from backend.core import install_registry, process_registry
from backend.core.database import create_tables, init_db
from backend.core.settings import init_settings

logger = logging.getLogger(__name__)

_SYSTEM_PLATFORMS = [
    {
        "name": "DOSBox-X",
        "slug": "dosbox-x",
        "era": "dos",
        "emulator_slug": "dosbox-x",
        "is_system": True,
        "supported_eras": json.dumps(["dos", "win31"]),
        "download_url": "https://dosbox-x.com",
        "status": "unknown",
    },
    {
        "name": "86Box",
        "slug": "86box",
        "era": "win95",
        "emulator_slug": "86box",
        "is_system": True,
        "supported_eras": json.dumps(["win95", "win98"]),
        "download_url": "https://86box.net",
        "status": "unknown",
    },
    {
        "name": "VirtualBox",
        "slug": "virtualbox",
        "era": "win95",
        "emulator_slug": "virtualbox",
        "is_system": True,
        "supported_eras": json.dumps(["win95", "win98", "winxp"]),
        "download_url": "https://www.virtualbox.org",
        "status": "unknown",
    },
    {
        "name": "DuckStation",
        "slug": "duckstation",
        "era": "ps1",
        "emulator_slug": "duckstation",
        "is_system": True,
        "supported_eras": json.dumps(["ps1"]),
        "download_url": "https://www.duckstation.org",
        "status": "unknown",
    },
    {
        "name": "PCSX2",
        "slug": "pcsx2",
        "era": "ps2",
        "emulator_slug": "pcsx2",
        "is_system": True,
        "supported_eras": json.dumps(["ps2"]),
        "download_url": "https://pcsx2.net",
        "status": "unknown",
    },
    {
        "name": "xemu",
        "slug": "xemu",
        "era": "xbox",
        "emulator_slug": "xemu",
        "is_system": True,
        "supported_eras": json.dumps(["xbox"]),
        "download_url": "https://xemu.app",
        "status": "unknown",
    },
    {
        "name": "Mesen",
        "slug": "mesen",
        "era": "nes",
        "emulator_slug": "mesen",
        "is_system": True,
        "supported_eras": json.dumps(["nes"]),
        "download_url": "https://www.mesen.ca",
        "status": "unknown",
    },
    {
        "name": "Project64",
        "slug": "project64",
        "era": "n64",
        "emulator_slug": "project64",
        "is_system": True,
        "supported_eras": json.dumps(["n64"]),
        "download_url": "https://www.pj64-emu.com",
        "status": "unknown",
    },
]

_DEFAULT_PROFILES = [
    {"name": "DOS Default",      "slug": "dos-default",    "era": "dos",   "emulator_slug": "dosbox-x",   "is_bundled": True, "is_accuracy_mode": False},
    {"name": "Win 3.1 Default",  "slug": "win31-default",  "era": "win31", "emulator_slug": "dosbox-x",   "is_bundled": True, "is_accuracy_mode": False},
    {"name": "Win 95 Compat",    "slug": "win95-compat",   "era": "win95", "emulator_slug": "virtualbox",  "is_bundled": True, "is_accuracy_mode": False},
    {"name": "Win 95 Accuracy",  "slug": "win95-accuracy", "era": "win95", "emulator_slug": "86box",       "is_bundled": True, "is_accuracy_mode": True},
    {"name": "Win 98 Compat",    "slug": "win98-compat",   "era": "win98", "emulator_slug": "virtualbox",  "is_bundled": True, "is_accuracy_mode": False},
    {"name": "Win 98 Accuracy",  "slug": "win98-accuracy", "era": "win98", "emulator_slug": "86box",       "is_bundled": True, "is_accuracy_mode": True},
    {"name": "Win XP Default",   "slug": "winxp-default",  "era": "winxp", "emulator_slug": "virtualbox",  "is_bundled": True, "is_accuracy_mode": False},
    {"name": "PS1 Default",      "slug": "ps1-default",    "era": "ps1",   "emulator_slug": "duckstation", "is_bundled": True, "is_accuracy_mode": False},
    {"name": "PS2 Default",      "slug": "ps2-default",    "era": "ps2",   "emulator_slug": "pcsx2",       "is_bundled": True, "is_accuracy_mode": False},
    {"name": "Xbox OG Default",  "slug": "xbox-default",   "era": "xbox",  "emulator_slug": "xemu",        "is_bundled": True, "is_accuracy_mode": False},
    {"name": "NES Default",      "slug": "nes-default",    "era": "nes",   "emulator_slug": "mesen",       "is_bundled": True, "is_accuracy_mode": False},
    {"name": "N64 Default",      "slug": "n64-default",    "era": "n64",   "emulator_slug": "project64",   "is_bundled": True, "is_accuracy_mode": False},
]


def _sync_first_run_from_db(db) -> None:
    from backend.models.settings import Settings as SettingsModel
    from backend.service.utils import settings as _settings_mod
    row = db.get(SettingsModel, "first_run_complete")
    if row and row.value == "true":
        state = _settings_mod._require_init()
        state["first_run_complete"] = True


def _seed_system_platforms(db) -> None:
    try:
        from backend.models import Platform
        if db.query(Platform).filter(Platform.is_system.is_(True)).count() > 0:
            return
        for data in _SYSTEM_PLATFORMS:
            db.add(Platform(**data))
        db.flush()
        logger.info("Seeded %d system platforms", len(_SYSTEM_PLATFORMS))
    except Exception as exc:
        db.rollback()
        logger.warning("System platform seeding skipped: %s", exc)


def _seed_default_profiles(db) -> None:
    try:
        from backend.models import Profile
        if db.query(Profile).filter(Profile.is_bundled.is_(True)).count() > 0:
            return
        for data in _DEFAULT_PROFILES:
            db.add(Profile(**data))
        db.flush()
        logger.info("Seeded %d default profiles", len(_DEFAULT_PROFILES))
    except Exception as exc:
        db.rollback()
        logger.warning("Default profile seeding skipped: %s", exc)


def _cleanup_stale_sessions(db) -> None:
    try:
        from backend.models import LaunchHistory
        stale = db.query(LaunchHistory).filter(LaunchHistory.ended_at.is_(None)).all()
        for session in stale:
            session.ended_at = datetime.utcnow()
            session.exit_code = -1
        db.flush()
        if stale:
            logger.info("Startup: closed %d stale launch session(s)", len(stale))
    except Exception as exc:
        db.rollback()
        logger.warning("Startup session cleanup failed: %s", exc)


def _write_session_ends(exited: list, exit_code_override: int | None = None) -> None:
    if not exited:
        return
    from backend.core.database import get_engine
    from backend.models import LaunchHistory
    from sqlalchemy.orm import sessionmaker
    session_factory = sessionmaker(bind=get_engine())
    with session_factory() as db:
        for _pid, entry in exited:
            if entry.launch_history_id is None:
                continue
            history = db.get(LaunchHistory, entry.launch_history_id)
            if history and history.ended_at is None:
                history.ended_at = datetime.utcnow()
                if exit_code_override is not None:
                    history.exit_code = exit_code_override
                else:
                    rc = getattr(entry.process_handle, "returncode", None) if entry.process_handle else None
                    history.exit_code = rc if rc is not None else -1
        db.commit()


async def _process_monitor_loop() -> None:
    while True:
        try:
            await asyncio.sleep(5)
            exited = process_registry.cleanup_exited()
            if exited:
                await asyncio.to_thread(_write_session_ends, exited)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Process monitor iteration failed (will retry): %s", exc)


_SANDBOX_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent / "scripts" / "create_sandbox_user.ps1"
)


def _verify_sandbox_user() -> None:
    """Ensure the peach_sandbox local account exists and is correctly configured.

    No-op on non-Windows hosts. Calls create_sandbox_user.ps1 via a subprocess
    PowerShell call. Aborts startup (raises RuntimeError) if the script fails
    or exits non-zero.
    """
    if platform.system() != "Windows":
        return

    if not _SANDBOX_SCRIPT.exists():
        raise RuntimeError(
            f"Sandbox setup script not found: {_SANDBOX_SCRIPT}\n"
            "Re-clone the repository or restore scripts/create_sandbox_user.ps1."
        )

    from backend.service.utils import settings as _settings_mod
    password = _settings_mod.get_or_generate_sandbox_password()

    env = os.environ.copy()
    env["PEACH_SANDBOX_PASSWORD"] = password

    result = subprocess.run(
        [
            "powershell.exe",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-File", str(_SANDBOX_SCRIPT),
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    # Surface stdout at INFO so operators see what the script did.
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            logger.info("Sandbox setup: %s", line)

    if result.returncode != 0:
        error_output = (result.stdout + "\n" + result.stderr).strip()
        raise RuntimeError(
            f"Sandbox user setup failed (exit {result.returncode}):\n{error_output}"
        )


def _scan_installed_emulators() -> None:
    try:
        from backend.service.utils.emulator_catalog import get_all_statuses
        statuses = get_all_statuses()
        installed_count = 0
        for s in statuses:
            if s["is_installed"]:
                install_registry.set_status(s["slug"], "complete", install_path=s["install_path"])
                installed_count += 1
        logger.info("Startup: detected %d/%d emulators installed", installed_count, len(statuses))
    except Exception as exc:
        logger.warning("Startup emulator scan failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_settings()
    _verify_sandbox_user()
    init_db()
    create_tables()

    from backend.core.database import get_engine
    from sqlalchemy.orm import sessionmaker
    session_factory = sessionmaker(bind=get_engine())
    with session_factory() as db:
        _sync_first_run_from_db(db)
        _seed_system_platforms(db)
        _seed_default_profiles(db)
        _cleanup_stale_sessions(db)
        db.commit()

    _scan_installed_emulators()

    monitor_task = asyncio.create_task(_process_monitor_loop())

    yield

    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

    # Finalize any sessions that exited while the monitor was between poll intervals.
    exited = process_registry.cleanup_exited()
    if exited:
        _write_session_ends(exited)

    # Mark still-running sessions as killed by backend shutdown before terminating.
    still_running = list(process_registry.get_all().items())
    if still_running:
        _write_session_ends(still_running, exit_code_override=-15)

    for pid in list(process_registry.get_all().keys()):
        process_registry.terminate(pid)
