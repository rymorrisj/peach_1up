"""extract-xiso invocation for Peach 1UP.

extract-xiso is a vendored third-party tool (services/vendor/extract-xiso/),
not an emulator — it has no entry in config/emulators/*.toml and is never
surfaced as a launchable item. It exists solely to convert a raw Xbox DVD rip
into the xiso format xemu requires.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.service.utils.path_utils import allowed_browse_roots, is_within_roots

logger = get_logger(__name__)

_VENDOR_DIR = get_base_path() / "services" / "vendor" / "extract-xiso"
_BINARY_NAME = "extract-xiso.exe" if sys.platform == "win32" else "extract-xiso"

# Multi-GB rips take a while to rewrite; this is a ceiling against a hung
# or wedged process, not an expected duration.
_CONVERT_TIMEOUT_SECONDS = 1800

# A genuinely rewritten xiso is a multi-hundred-MB-to-multi-GB file. This is
# only a floor against a truncated/empty write, not a comparison against the
# original size — a real rewrite is usually *smaller* than the raw rip (it
# strips the video partition and padding), so shrinkage alone is expected.
_MIN_PLAUSIBLE_XISO_BYTES = 1_048_576


def get_extract_xiso_path() -> Path | None:
    """Return the resolved extract-xiso binary path, or None if not built."""
    path = _VENDOR_DIR / "build" / _BINARY_NAME
    return path if path.is_file() else None


def convert_dvd_rip_to_xiso(source_path: Path) -> Path:
    """Rewrite a raw Xbox DVD rip at *source_path* into a proper xiso, in place.

    Calls extract-xiso's own -r (rewrite) mode directly on source_path — no
    -D flag, so extract-xiso's automatic '<name>.old' backup of the
    pre-rewrite file is left on disk as the safety net; this wrapper never
    deletes it. If a '.old' backup already exists from a prior attempt,
    extract-xiso itself refuses to run and that surfaces below as a normal
    RuntimeError (its own stderr message names the conflicting path).

    extract-xiso can report success (exit 0) without having actually
    rewritten anything — its own err_iso_no_files case resets the exit code
    to 0 internally — so exit 0 is not trusted on its own. After the
    subprocess returns 0, the result is re-inspected: the file must still
    exist, be a plausible size, and no longer detect as dvd_rip. Any of
    those failing is treated as a conversion failure even though
    extract-xiso itself reported success.

    Args:
        source_path: Absolute path to the raw DVD rip. Must already resolve
            within a configured library root — this is enforced here as a
            second check, independent of any validation the caller performed.

    Returns:
        Path to the rewritten file — the same path as source_path, since the
        rewrite happens in place.

    Raises:
        FileNotFoundError: extract-xiso is not built, or source_path does
            not exist.
        ValueError: source_path resolves outside the configured library roots.
        RuntimeError: extract-xiso exited with a non-zero status, or exited
            0 without producing a valid, non-dvd_rip xiso.
    """
    from backend.service.utils.xbox_image import detect_xbox_image_type

    binary = get_extract_xiso_path()
    if binary is None:
        raise FileNotFoundError(
            "extract-xiso is not built. Run services/vendor/extract-xiso/build.sh "
            "(or the project build.bat) first."
        )

    resolved_source = source_path.resolve()
    if not resolved_source.is_file():
        raise FileNotFoundError(f"Source media not found: {resolved_source}")
    if not is_within_roots(resolved_source, allowed_browse_roots()):
        raise ValueError(f"Source path '{resolved_source}' is outside the configured library.")

    # Argument list, never a shell string — resolved_source is a resolved
    # Path built from the DB-sourced file_path (see the convert-xiso route),
    # not raw request input.
    #
    # cwd is pinned to the source's own directory because extract-xiso has no
    # -d/output-directory flag in this invocation, so its rewrite path falls
    # back to the process's cwd (see create_xiso() in extract-xiso.c) rather
    # than resolving relative to the argument path. Without this, the backend
    # process's own cwd (the project root) leaks in and the rewritten file
    # lands there instead of next to the original.
    result = subprocess.run(
        [str(binary), "-r", str(resolved_source)],
        cwd=resolved_source.parent,
        capture_output=True,
        text=True,
        timeout=_CONVERT_TIMEOUT_SECONDS,
    )

    # Logged unconditionally, not just on failure — extract-xiso's own
    # diagnostics (e.g. "contains no files") are the only signal that a
    # exit-0 response was actually a silent no-op.
    if result.stdout.strip():
        logger.info("extract-xiso stdout for %s:\n%s", resolved_source, result.stdout.strip())
    if result.stderr.strip():
        logger.info("extract-xiso stderr for %s:\n%s", resolved_source, result.stderr.strip())

    if result.returncode != 0:
        raise RuntimeError(
            f"extract-xiso failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )

    if not resolved_source.is_file():
        raise RuntimeError(
            f"extract-xiso reported success but {resolved_source} no longer exists."
        )
    rewritten_size = resolved_source.stat().st_size
    if rewritten_size < _MIN_PLAUSIBLE_XISO_BYTES:
        raise RuntimeError(
            f"extract-xiso reported success but the rewritten file at {resolved_source} "
            f"is implausibly small ({rewritten_size} bytes)."
        )
    if detect_xbox_image_type(resolved_source) == "dvd_rip":
        raise RuntimeError(
            f"extract-xiso reported success but {resolved_source} still detects as a "
            "raw Xbox DVD rip — the rewrite did not actually convert it."
        )

    return resolved_source
