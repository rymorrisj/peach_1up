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
import shutil
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Tuple

from backend.core.logger import get_logger
from backend.service.utils.detection import MediaTarget, resolve_ps3_target
from backend.service.utils.emulator_catalog import (
    get_emulator,
    get_install_path,
    resolve_container_enabled,
)
from backend.service.utils.file_types import supported_extensions_for_era
from backend.service.utils.ini_writer import set_ini_key
from backend.service.utils.path_utils import resolve_under
from backend.service.utils.platform.windows.process.launcher import launch_under_job_object
from wincage import SandboxProcess, WindowsJobObject

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


# PS3 folder-shape resolution (MediaTarget, resolve_ps3_target) now lives in
# backend.service.utils.detection, shared with backend.service.games.items'
# ingest-time detection instead of each carrying its own copy. Previously a
# private, underscore-prefixed transplant here from the formatscout vendor
# package (services/vendor/formatscout/smart_media_detector, as it existed
# at commit f3fde90 before its working-tree removal); restored to a shared
# module since this is Peach 1UP-specific launch-target logic, not format
# detection, and belongs outside formatscout regardless.

# RPCS3's fixed exdata location for PlayStation Network license (.rap) files.
# Confirmed against RPCS3's own quickstart/wiki guidance: the folder name is
# lowercase, and files placed there must retain their original filename
# verbatim, RPCS3 will not recognize a renamed .rap. This is exactly why the
# safe_basename fix (path_utils.py) matters here: a .rap sanitized through the
# old slugify-based sanitize_filename lost case and its underscore, which
# would have made a freshly-uploaded .rap unrecognizable even after being
# placed here under its (mangled) name.
_EXDATA_RELATIVE_PATH = Path("dev_hdd0") / "home" / "00000001" / "exdata"


def _find_license_files(pkg_path: Path) -> tuple[Path, ...]:
    """Return every sibling .rap file next to *pkg_path*, in glob order.

    Not all .pkg content ships a .rap, some needs no per-console license
    file, so an empty tuple is a normal result, not a failure.
    """
    return tuple(pkg_path.parent.glob("*.rap"))


def _place_license_files(license_files: tuple[Path, ...], install_dir: Path) -> None:
    """Copy *license_files* into RPCS3's exdata folder under their own names.

    RPCS3 scans dev_hdd0/home/00000001/exdata/ at launch and links whatever
    .rap files it finds there to their matching installed titles by content
    ID, itself parsed from the file's own bytes, not the filename, but RPCS3
    still requires the on-disk filename to be unchanged from how it was
    originally distributed (see _EXDATA_RELATIVE_PATH). Security note: the
    source paths here come from a filesystem glob against the library's own
    upload-managed folder, not from a raw request field, but the destination
    join still goes through resolve_under as defense-in-depth, matching the
    pattern every other path built from an upload-influenced segment in this
    codebase already follows, a Path.name can't itself contain a separator
    or traversal segment, but this keeps the guarantee structural rather than
    relying on that fact staying true.
    """
    if not license_files:
        return
    exdata_dir = install_dir / _EXDATA_RELATIVE_PATH
    exdata_dir.mkdir(parents=True, exist_ok=True)
    for rap in license_files:
        try:
            dest = resolve_under(exdata_dir, rap.name)
            shutil.copy2(str(rap), str(dest))
        except (OSError, ValueError) as exc:
            logger.error("rpcs3: failed to place license file '%s' into exdata: %s", rap, exc)


def _title_id_from_rap(pkg_path: Path) -> str | None:
    """Fast path: extract the title ID from a sibling .rap's filename.

    RAP filenames follow Sony's convention (e.g.
    "UP0177-NPUB30724_00-00BAYONETTAHDDUS.rap" -> "NPUB30724"). Not all pkgs
    ship a .rap, some content needs no per-console license file, so this
    returns None rather than raising when one isn't found. Filename-based, so
    a .rap whose case/underscores were stripped by upload sanitization prior
    to the safe_basename fix will silently miss here and fall through to the
    pkg-header fallback below, which reads the actual file bytes rather than
    the filename and is unaffected either way.
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


def _write_installed_state(spec: "LaunchSpec", installed: bool, *, reraise: bool = False) -> None:
    """Write pkg install completion back onto the matching GameItemBundle.

    era-gated to "ps3" and source_type "game", the install-completion signal
    only means something for a PS3 title bundle, and this is the one backend
    that ever calls it. Opens its own session rather than reusing any
    request-scoped one, this can run from the background install-poll thread
    in _wait_for_stable_and_terminate, long after the launch request that
    started the install has returned, mirrors monitor._flag_short_lived_item,
    the codebase's existing pattern for a DB write from outside a request.

    reraise defaults to False: the launch() call site writes this as
    best-effort bookkeeping and a failure there must not fail an otherwise
    successful launch. The background install-poll call site passes
    reraise=True, matching monitor._flag_short_lived_item, since that write
    failing is a genuine background job failure with no launch to protect.
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
        if reraise:
            raise


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
    try:
        proc.terminate()
        proc.wait(timeout_ms=10_000)
    except Exception as exc:
        logger.error("rpcs3: failed to terminate install process pid=%s: %s", proc.pid, exc)
    _write_installed_state(spec, True, reraise=True)


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
    # eras.yaml is the single enforced source for launch-time format
    # validation (matches dosbox.py/flycast.py/xemu.py's pattern), not the
    # TOML descriptor's own supported_formats field, which stays display-only
    # (surfaced by GET /emulators) and is now cross-checked against eras.yaml
    # at startup by EmulatorDescriptor's validator instead of trusted here.
    supported_formats = frozenset(supported_extensions_for_era("ps3"))

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
            # resolve_ps3_target validates both folder shapes identically now
            # (N3): a PS3_DISC.SFB-marked folder with no findable EBOOT.BIN
            # used to skip this check entirely and reach launch_under_job_object
            # anyway, only to fail inside RPCS3 itself instead of here.
            ps3_target = resolve_ps3_target(media_path)
            if ps3_target is None:
                raise FileNotFoundError(
                    f"No bootable PS3 title found in '{media_path}' "
                    "(expected USRDIR/EBOOT.BIN, optionally under PS3_GAME/)."
                )
            target_path = ps3_target.launch_path
        elif media_path.suffix.lower() == ".pkg":
            title_id = _title_id_from_rap(media_path) or _title_id_from_pkg_header(media_path)
            license_files = _find_license_files(media_path)
            pkg_target = MediaTarget(
                kind="file", detect_path=media_path, launch_path=media_path,
                era="ps3", requires_install=False, license_files=license_files,
            )
            # Placed before either branch below: RPCS3 scans exdata for
            # licenses at its own next launch, which for an uninstalled title
            # is the install-triggering launch started by _start_pkg_install
            # just below, and for an already-installed title is the boot
            # about to happen in the eboot.is_file() branch. Either way the
            # license must already be in place before RPCS3's process starts.
            _place_license_files(pkg_target.license_files, install_dir)
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
