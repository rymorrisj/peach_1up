"""RPCS3 backend for Peach 1UP.

Handles PS3 launches. Three media shapes resolve to the same underlying
launch: a raw .iso, an extracted disc folder (top-level dir containing
PS3_GAME/USRDIR/EBOOT.BIN or USRDIR/EBOOT.BIN directly), or a digital .pkg.

.pkg installs are two-phase, not one-shot, because of a hard architectural
constraint: coordinator.launch() wraps the whole backend dispatch in a 30s
asyncio.wait_for (see coordinator.py), and a multi-gigabyte pkg install can
take many minutes. RPCS3 also refuses to install headlessly, its own binary
contains the string "Cannot perform installation in no-gui mode!", and it
never exits on its own once an unattended install finishes, so process exit
is not a usable completion signal either. So: the first launch() call for an
uninstalled .pkg starts the install and returns that RPCS3 process as this
launch's tracked process (spawn is near-instant, well inside the 30s window);
a background thread polls dev_hdd0/game/<TITLE_ID>/ for stabilization and
terminates the installer once it's done. The *next* launch() call for the
same item finds the folder already populated and boots it directly, same as
any other folder-based launch. process_registry's existing per-profile guard
key naturally prevents a second concurrent launch attempt while install is
running, and its existing cleanup_exited() path picks up the terminated
installer on the next launch attempt, with no coordinator changes needed.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Tuple

from backend.core.logger import get_logger
from backend.service.utils.emulator_catalog import (
    get_emulator,
    get_install_path,
    resolve_container_enabled,
)
from backend.service.utils.ini_writer import set_ini_key
from backend.service.utils.platform.windows.process.launcher import launch_under_job_object
from backend.service.utils.platform.windows.sandbox_process import SandboxProcess
from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject

logger = get_logger(__name__)

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec

# dev_flash/vsh/etc/version.txt is written by RPCS3's own firmware installer
# and contains a build manifest (e.g. "release:04.9300:..."). Its presence is
# a reliable, simple marker that --installfw has been run; there is no single
# canonical "is firmware installed" API, so this is the same file the RPCS3
# UI itself reads to display the firmware version.
_FIRMWARE_MARKER = Path("dev_flash") / "vsh" / "etc" / "version.txt"

# PS3 package header: 4-byte magic, content_id (e.g.
# "UP0177-NPUB30724_00-00BAYONETTAHDDUS") null-padded at offset 0x30.
# Verified against a real .pkg on disk during this pass, not just the spec.
_PKG_MAGIC = b"\x7fPKG"
_PKG_CONTENT_ID_OFFSET = 0x30
_PKG_CONTENT_ID_FIELD_SIZE = 0x30
_TITLE_ID_RE = re.compile(r"-([A-Z]{4}\d{5})_")

# Install-completion polling: dev_hdd0/game/<TITLE_ID>/ must stop growing for
# this many consecutive checks (with EBOOT.BIN present) before the installer
# process is considered done and is terminated.
_INSTALL_POLL_INTERVAL = 2.0
_INSTALL_STABLE_CHECKS = 3
_INSTALL_MAX_WAIT = 3600.0


def _check_firmware_installed(install_dir: Path) -> None:
    marker = install_dir / _FIRMWARE_MARKER
    if not marker.is_file() or marker.stat().st_size == 0:
        raise FileNotFoundError(
            "PS3 firmware is not installed. Install PS3UPDAT.PUP from within RPCS3 "
            "(File > Install Firmware) or via `rpcs3.exe --installfw <path-to-PS3UPDAT.PUP>`, "
            "then try launching again."
        )


# PS3_DISC.SFB at a folder's root (alongside PS3_GAME/, optionally PS3_UPDATE/)
# marks the folder as a disc-format dump. RPCS3's own "Boot Game" targets the
# folder itself in this case and does its own internal walk, so the folder is
# the launch unit, not a resolved EBOOT.BIN, this is a distinct shape from the
# dev_hdd0/game/<TITLE_ID>/ and loose extracted folders find_eboot resolves.
_DISC_MARKER_FILENAME = "PS3_DISC.SFB"


def is_disc_format_folder(folder: Path) -> bool:
    """Return True if *folder* is a disc-format dump (has PS3_DISC.SFB at its root)."""
    return (folder / _DISC_MARKER_FILENAME).is_file()


def find_eboot(folder: Path) -> Path | None:
    """Return the EBOOT.BIN path for *folder*, checking both known layouts.

    dev_hdd0/game/<TITLE_ID>/ folders (installed pkgs) hold USRDIR directly;
    extracted disc folders hold it one level down, under PS3_GAME/.

    Public (not module-private): also imported by the detection/ingest layer
    (backend.service.games.items.best_detect_path) via a deferred, function-local
    import, the same "one sanctioned import site" pattern emulator_catalog.py
    uses for box86.resolve_rom_path, to resolve an extracted PS3 disc folder to
    its actual hashable file without detection code depending on this launch
    backend module at import time.
    """
    for candidate in (folder / "USRDIR" / "EBOOT.BIN", folder / "PS3_GAME" / "USRDIR" / "EBOOT.BIN"):
        if candidate.is_file():
            return candidate
    return None


def _title_id_from_rap(pkg_path: Path) -> str | None:
    """Fast path: extract the title ID from a sibling .rap's filename.

    RAP filenames follow Sony's convention (e.g.
    "UP0177-NPUB30724_00-00BAYONETTAHDDUS.rap" -> "NPUB30724"). Not all pkgs
    ship a .rap, some content needs no per-console license file, so this
    returns None rather than raising when one isn't found.
    """
    for rap in pkg_path.parent.glob("*.rap"):
        match = _TITLE_ID_RE.search(rap.name)
        if match:
            return match.group(1)
    return None


def _title_id_from_pkg_header(pkg_path: Path) -> str:
    """Parse the PS3 package header directly to extract the title ID.

    General-case fallback for when no .rap sibling exists.
    """
    with pkg_path.open("rb") as f:
        magic = f.read(4)
        if magic != _PKG_MAGIC:
            raise ValueError(f"'{pkg_path}' is not a valid PS3 package (bad magic: {magic!r}).")
        f.seek(_PKG_CONTENT_ID_OFFSET)
        raw = f.read(_PKG_CONTENT_ID_FIELD_SIZE)
    content_id = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")
    match = _TITLE_ID_RE.search(content_id)
    if not match:
        raise ValueError(
            f"Could not determine the title ID from '{pkg_path}' (content_id={content_id!r})."
        )
    return match.group(1)


def _write_installed_state(spec: "LaunchSpec", installed: bool) -> None:
    """Write pkg install completion back onto the matching GameItemBundle.

    era-gated to "ps3" and source_type "game", the install-completion signal
    only means something for a PS3 title bundle, and this is the one backend
    that ever calls it. Opens its own session rather than reusing any
    request-scoped one, this can run from the background install-poll thread
    in _wait_for_stable_and_terminate, long after the launch request that
    started the install has returned, mirrors monitor._flag_short_lived_item,
    the codebase's existing pattern for a DB write from outside a request.
    """
    if spec.era != "ps3" or spec.source_type != "game" or spec.collection_id is None:
        return
    from backend.core.database import get_engine
    from backend.models import GameItemBundle
    from sqlalchemy.orm import Session

    try:
        with Session(get_engine()) as db:
            collection = db.get(GameItemBundle, spec.collection_id)
            if collection is not None and collection.installed != installed:
                collection.installed = installed
                db.commit()
    except Exception as exc:
        logger.error(
            "rpcs3: failed to write installed=%s for collection_id=%s: %s",
            installed, spec.collection_id, exc, exc_info=True,
        )


def _snapshot_dir(path: Path) -> tuple[int, int]:
    try:
        files = [f for f in path.rglob("*") if f.is_file()]
        return len(files), sum(f.stat().st_size for f in files)
    except OSError:
        return (0, 0)


def _wait_for_stable_and_terminate(proc: SandboxProcess, game_dir: Path, eboot: Path, spec: "LaunchSpec") -> None:
    """Background poll: end the installer once *game_dir* stops growing.

    Runs in a daemon thread so launch() can return well within the
    coordinator's 30s dispatch window, see the module docstring for why
    this can't be a synchronous wait. RPCS3 refuses to install headlessly and
    won't exit on its own once an unattended install finishes, so filesystem
    stabilization is the only usable completion signal.
    """
    deadline = time.monotonic() + _INSTALL_MAX_WAIT
    last_snapshot: tuple[int, int] | None = None
    stable_count = 0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return
        snapshot = _snapshot_dir(game_dir)
        if snapshot == last_snapshot and snapshot != (0, 0):
            stable_count += 1
            if stable_count >= _INSTALL_STABLE_CHECKS and eboot.is_file():
                break
        else:
            stable_count = 0
        last_snapshot = snapshot
        time.sleep(_INSTALL_POLL_INTERVAL)
    else:
        logger.warning(
            "rpcs3: pkg install for %s did not stabilize within %.0fs; leaving the "
            "installer process running rather than terminating a possibly-still-active install.",
            game_dir, _INSTALL_MAX_WAIT,
        )
        return

    logger.info("rpcs3: pkg install for %s appears complete, terminating installer process", game_dir)
    _write_installed_state(spec, True)
    try:
        proc.terminate()
        proc.wait(timeout_ms=10_000)
    except Exception as exc:
        logger.error("rpcs3: failed to terminate install process pid=%s: %s", proc.pid, exc)


def _start_pkg_install(
    spec: "LaunchSpec",
    install_path: Path,
    install_dir: Path,
    pkg_path: Path,
    game_dir: Path,
    eboot: Path,
) -> Tuple[SandboxProcess, WindowsJobObject]:
    # Suppress the post-install completion popup (infoBoxEnabledInstallPKG) --
    # confirmed via the RPCS3 binary and GuiConfigs/CurrentSettings.ini that
    # this key exists and defaults to on. The background poll thread below is
    # a second, independent backstop: it terminates the process once the
    # install folder stabilizes regardless of whether the popup was suppressed.
    ini_path = install_dir / "GuiConfigs" / "CurrentSettings.ini"
    set_ini_key(ini_path, "main_window", "infoBoxEnabledInstallPKG", "false")

    job_name_prefix = f"Peach1UP_rpcs3_install_{game_dir.name}"
    logger.info("rpcs3: '%s' not yet installed, starting install -> %s", game_dir.name, game_dir)
    result = launch_under_job_object(
        executable_path=str(install_path),
        args=["--installpkg", str(pkg_path)],
        era=spec.era,
        job_name_prefix=job_name_prefix,
        slug="rpcs3",
        cwd=str(install_dir),
        container_enabled=False,
        sandbox_config=None,
    )
    proc = result[0]
    threading.Thread(
        target=_wait_for_stable_and_terminate,
        args=(proc, game_dir, eboot, spec),
        daemon=True,
        name=f"rpcs3_pkg_install_wait_{proc.pid}",
    ).start()
    return result


def launch(spec: "LaunchSpec") -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch RPCS3 under Job Object isolation.

    Args:
        spec: LaunchSpec with era="ps3" and media_path set to one of: a .iso
            file, a directory (extracted disc, or an already-installed
            dev_hdd0/game/<TITLE_ID>/ folder), or a .pkg file.

    Returns:
        Tuple of (SandboxProcess, WindowsJobObject). For a .pkg whose title
        is not yet installed, this is the *installer* process, not the game
       , see the module docstring for the two-phase design. Call launch()
        again once install finishes to boot the actual game.

    Raises:
        FileNotFoundError: If the executable, firmware, or media is missing,
            or a directory has no bootable EBOOT.BIN.
        ValueError: If the media extension is unsupported, or a .pkg's title
            ID cannot be determined.
        RuntimeError: If process launch fails.
    """
    entry = get_emulator("rpcs3")
    display_name = entry.get("display_name", "rpcs3")
    supported_formats = set(entry.get("supported_formats", []))

    install_path = get_install_path("rpcs3")
    if install_path is None or not install_path.is_file():
        raise FileNotFoundError(
            f"{display_name} executable not found. Install it via the Emulators page."
        )
    install_dir = install_path.parent

    _check_firmware_installed(install_dir)

    target_path: Path | None = None
    if spec.media_path is not None:
        media_path = spec.media_path
        if not media_path.exists():
            raise FileNotFoundError(f"Media file not found: {media_path}")

        if media_path.is_dir():
            if not is_disc_format_folder(media_path):
                eboot = find_eboot(media_path)
                if eboot is None:
                    raise FileNotFoundError(
                        f"No bootable PS3 title found in '{media_path}' "
                        "(expected USRDIR/EBOOT.BIN, optionally under PS3_GAME/)."
                    )
            target_path = media_path
        elif media_path.suffix.lower() == ".pkg":
            title_id = _title_id_from_rap(media_path) or _title_id_from_pkg_header(media_path)
            game_dir = install_dir / "dev_hdd0" / "game" / title_id
            eboot = game_dir / "USRDIR" / "EBOOT.BIN"
            if eboot.is_file():
                target_path = game_dir
                _write_installed_state(spec, True)
            else:
                return _start_pkg_install(spec, install_path, install_dir, media_path, game_dir, eboot)
        else:
            if media_path.suffix.lower() not in supported_formats:
                raise ValueError(
                    f"Unsupported media format '{media_path.suffix}'. "
                    f"{display_name} supports: {', '.join(sorted(supported_formats))}"
                )
            target_path = media_path

    args = [str(target_path)] if target_path is not None else []
    job_name_prefix = f"Peach1UP_rpcs3_{target_path.stem if target_path else 'noboot'}"

    container_enabled = resolve_container_enabled("rpcs3", spec.container_enabled)

    logger.debug("rpcs3.launch: args=%s", args)
    return launch_under_job_object(
        executable_path=str(install_path),
        args=args,
        era=spec.era,
        job_name_prefix=job_name_prefix,
        slug="rpcs3",
        cwd=str(install_dir),
        container_enabled=container_enabled,
        sandbox_config=None,
    )
