"""Path normalisation for Peach 1UP.

Every path arriving from external input (request bodies, query params, settings
forms) must pass through normalise_path before any allowlist check or filesystem
operation. This module is the single choke-point for that normalisation.
"""

import os
import re
from pathlib import Path

from backend.service.utils.slug_generator import slugify


def sanitize_filename(filename: str, *, fallback: str = "upload") -> str:
    """Reduce a user-supplied filename to a safe basename.

    Unifies separators and takes only the final path segment, then slugifies
    the stem and extension independently. The result can never contain a
    path separator or a ``..`` segment, so it is safe to join onto a
    destination directory without further escaping.

    Args:
        filename: Raw filename from a multipart upload (``UploadFile.filename``).
        fallback: Base name to use when the stem normalises to an empty string.

    Returns:
        A sanitized ``stem.ext`` (or bare ``stem`` if no extension survives).
    """
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    safe_stem = slugify(stem, fallback=fallback)
    safe_ext = re.sub(r"[^a-zA-Z0-9]", "", ext).lower()
    return f"{safe_stem}.{safe_ext}" if safe_ext else safe_stem


def resolve_under(base: Path, *parts: str) -> Path:
    """Join *parts* onto *base* and verify the resolved path stays within it.

    Defense-in-depth check for any path built from user-influenced segments,
    even ones already sanitized — mirrors the allowlist checks used elsewhere
    for media and drive paths.

    Raises:
        ValueError: If the resolved path is not *base* or a descendant of it.
    """
    candidate = base
    for part in parts:
        candidate = candidate / part
    resolved = candidate.resolve()
    base_resolved = base.resolve()
    if not (resolved == base_resolved or resolved.is_relative_to(base_resolved)):
        raise ValueError(f"Resolved path '{resolved}' escapes base directory '{base_resolved}'.")
    return resolved


def normalise_path(path: str) -> Path:
    """Normalise a user-supplied path to an absolute resolved Path.

    The result is a canonical absolute path native to the host the backend runs
    on, independent of the terminal it was launched from. ``os.name`` (the
    Python runtime OS, unaffected by whether the process was started from Git
    Bash, cmd, PowerShell, or a Linux shell) selects the path flavor:

    * On Windows, ``pathlib.Path`` is ``WindowsPath``, which already parses both
      ``C:/foo`` and ``C:\\foo`` as absolute — no separator munging is needed.
      Git Bash / MSYS2 virtual paths (``/c/Users`` -> ``C:/Users``) are the one
      form it does not understand, so those are translated first.
    * On POSIX, ``Path`` is ``PosixPath``. A backslash is a legal filename
      character and ``/c/...`` is a legitimate absolute path, so the string is
      left untouched — the Windows-only translation must never run here.

    Steps applied in order:
        1. Empty / whitespace-only rejection.
        2. Null-byte rejection (common injection vector).
        3. Git Bash / MSYS2 virtual path translation — Windows host only.
        4. Absolute resolution via ``Path.resolve()`` — eliminates ``..``
           segments and relative references.

    Raises:
        ValueError: If path is empty or contains a null byte.
    """
    if not path or not path.strip():
        raise ValueError("Path must not be empty.")

    if "\x00" in path:
        raise ValueError("Path contains a null byte.")

    # Git Bash / MSYS2 style virtual paths (/c/Users -> C:/Users). Windows host
    # only: on POSIX, /c/... is a real absolute path and must be left alone.
    if os.name == "nt" and re.match(r"^/[a-zA-Z]/", path):
        path = f"{path[1].upper()}:{path[2:]}"

    return Path(path).resolve()


def allowed_browse_roots() -> list[Path]:
    """Return every filesystem root the server-side file browser (and anything
    that consumes a path it returned) is permitted to touch: the configured
    library base directories, plus — on Windows — every drive letter, since
    the browser is also used to locate arbitrary source media (ROM packs,
    manual launch-target overrides) that legitimately live outside the library.

    Shared by the /filesystem/browse endpoint and any endpoint that accepts a
    path the browser produced, so the allowlist can never drift between the
    two call sites.
    """
    import string
    import sys

    from backend.core.settings import get_settings

    svc = get_settings()
    roots: list[Path] = []
    for key in ("LIBRARY_PATH", "SOFTWARE_PATH", "MEDIA_PATH", "OS_PATH", "ROMS_PATH", "PROFILES_PATH"):
        val = svc.get(key, "") or ""
        if val:
            try:
                roots.append(Path(val).resolve())
            except OSError:
                pass
    if sys.platform == "win32":
        for letter in string.ascii_uppercase:
            try:
                drive = Path(f"{letter}:\\")
                if drive.exists():
                    roots.append(drive.resolve())
            except OSError:
                pass
    return roots


def is_within_roots(resolved: Path, roots: list[Path]) -> bool:
    return any(resolved == r or resolved.is_relative_to(r) for r in roots)


# Matches the on-disk folder names exactly so a domain key can be joined onto
# SOFTWARE_PATH with no further translation. "media" is deliberately NOT a member: MediaItem/
# MediaItemBundle (backend/models/media.py) is the Software section's Media
# sub-tab AND the only Media domain that exists in this codebase, per doc
# dev_docs/v2/03_media_archive.md's "new archival Media domain" and the
# Software Media sub-tab were never two separate things, they shipped as one.
# That domain roots at MEDIA_PATH (library/media/), not SOFTWARE_PATH/media/,
# and is resolved directly in backend/service/uploads/software_media.py, it
# has no reason to ever go through this SOFTWARE_PATH-scoped resolver.
_LIBRARY_DOMAINS: frozenset[str] = frozenset({"games", "apps"})


def library_root() -> Path:
    """Return LIBRARY_PATH: the shared root one level above every domain
    subtree (software/, media/, system/...). Used for state that exists before
    a file's eventual destination domain is even known, e.g. chunked-upload
    staging, so that staging area is not nested inside any one domain's root.
    """
    from backend.core.settings import get_settings
    return Path(get_settings().get_env_var("LIBRARY_PATH")).resolve()


def library_domain_root(domain: str) -> Path:
    """Return the on-disk root for one Software-library domain: "games" or
    "apps". Each is a fixed subdirectory of SOFTWARE_PATH, library/software/games/,
    library/software/apps/, matching the real on-disk layout.

    Single place upload, scan, and any other consumer that used to read
    SOFTWARE_PATH directly and treat it as one flat root should resolve a
    domain-scoped destination from instead.

    Raises:
        ValueError: if domain is not one of "games", "apps".
    """
    if domain not in _LIBRARY_DOMAINS:
        raise ValueError(
            f"Unknown library domain '{domain}'. Valid domains: {', '.join(sorted(_LIBRARY_DOMAINS))}"
        )
    from backend.core.settings import get_settings
    software_path = get_settings().get_env_var("SOFTWARE_PATH")
    return Path(software_path).resolve() / domain
