"""Path normalisation for Peach 1UP.

Every path arriving from external input (request bodies, query params, settings
forms) must pass through normalise_path before any allowlist check or filesystem
operation. This module is the single choke-point for that normalisation.
"""

import ntpath
import re
from pathlib import Path, PureWindowsPath


def safe_basename(filename: str, *, fallback: str = "upload") -> str:
    """Reduce a user-supplied filename to a safe basename, preserving case and underscores.

    Unifies separators and takes only the final path segment, then filters
    the stem and extension independently to a safe character class. Unlike
    the old sanitize_filename (which this replaces), it does not route
    through slugify(): slugify lowercases and drops underscores outright,
    which is fine for a generated slug/ID but silently corrupts a
    content-derived filename that is meant to be preserved verbatim, most
    concretely PS3 .rap license filenames (e.g.
    "UP0177-NPUB30724_00-00BAYONETTAHDDUS.rap"), which RPCS3 will not
    recognize once lowercased and stripped of their underscore. The result
    can still never contain a path separator or a ``..`` segment, so it
    remains safe to join onto a destination directory without further
    escaping.

    Args:
        filename: Raw filename from a multipart upload (``UploadFile.filename``).
        fallback: Base name to use when the stem normalises to an empty string.

    Returns:
        A sanitized ``stem.ext`` (or bare ``stem`` if no extension survives),
        case and underscores preserved.
    """
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    safe_stem = re.sub(r"[^a-zA-Z0-9_-]", "", stem) or fallback
    safe_ext = re.sub(r"[^a-zA-Z0-9]", "", ext)
    return f"{safe_stem}.{safe_ext}" if safe_ext else safe_stem


def sanitize_relative_path(path: str) -> list[str]:
    """Validate a caller-supplied relative path and return its safe segments.

    Unlike safe_basename, which deliberately collapses any input to a
    single flat basename, this preserves the full segment list for callers
    that have already gated on needing real nested-path handling (today:
    chunked-upload folders whose kind resolves to a directory-based media
    shape, see backend.service.uploads.core.init_session). It only validates
    path *shape*, rejecting an empty path and any segment that is empty, ".",
    "..", or looks like a drive letter or home-relative prefix. It does not
    itself check containment against any destination directory, callers must
    still pass the returned segments through resolve_under(base, *segments)
    before touching disk, the same defense-in-depth every other
    user-influenced path in this codebase already goes through.

    Raises:
        ValueError: if path is empty or any segment is unsafe.
    """
    segments = path.replace("\\", "/").split("/")
    if not any(segments):
        raise ValueError("Relative path must not be empty.")
    for segment in segments:
        if not segment:
            raise ValueError(f"Relative path '{path}' contains an empty segment.")
        if segment in (".", ".."):
            raise ValueError(f"Relative path '{path}' contains a disallowed '{segment}' segment.")
        if ":" in segment or segment.startswith("~"):
            raise ValueError(f"Relative path '{path}' contains an absolute-looking segment '{segment}'.")
    return segments


def resolve_under(base: Path, *parts: str) -> Path:
    """Join *parts* onto *base* and verify the resolved path stays within it.

    Defense-in-depth check for any path built from user-influenced segments,
    even ones already sanitized, mirrors the allowlist checks used elsewhere
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


# Win32 device and NT object-namespace prefixes, compared after unifying
# separators to "/": \\?\ (long-path / raw device), \\.\ (device namespace,
# e.g. \\.\PhysicalDrive0), \??\ (NT object manager). Never legitimate input.
_DEVICE_PREFIXES = ("//?/", "//./", "/??/")
# "C:foo" or bare "C:": relative to drive C's per-process current directory,
# so its meaning depends on hidden process state.
_DRIVE_RELATIVE_RE = re.compile(r"^[a-zA-Z]:(?![\\/])")
_ROOT_SETTING_KEYS = ("LIBRARY_PATH", "SOFTWARE_PATH", "MEDIA_PATH", "OS_PATH", "ROMS_PATH", "PROFILES_PATH")


def _configured_unc_roots() -> list[PureWindowsPath]:
    """Operator-configured library roots, lexically normalised, never touching
    disk. Empty when settings are not initialised (tests, early startup)."""
    try:
        from backend.service.utils import settings as _s
        values = [_s.get(key, "") or "" for key in _ROOT_SETTING_KEYS]
    except RuntimeError:
        return []
    return [PureWindowsPath(ntpath.normpath(v)) for v in values if v]


def _is_under_configured_root(path: str) -> bool:
    """True if UNC *path* is lexically inside an operator-configured library
    root. ``ntpath.normpath`` collapses ``..`` without resolving, and a UNC
    path's ``\\\\server\\share`` anchor cannot be climbed out of, so a
    ``..``-laden path cannot reach a different host this way. Deciding this
    must not touch the filesystem: resolving an attacker-chosen UNC path is
    itself the NTLM leak MED-10 describes."""
    candidate = PureWindowsPath(ntpath.normpath(path))
    return any(candidate == root or candidate.is_relative_to(root) for root in _configured_unc_roots())


def is_untrusted_remote_path(path: str) -> bool:
    """True if a stored *path* is a device path, or a UNC path that is not
    lexically under an operator-configured library root (MED-10 read side).

    Lexical only, never touches the filesystem: read builders call this
    before resolve() or exists(), because resolving an attacker-chosen UNC
    path is itself the outbound SMB/NTLM leak. Same acceptance rule as
    normalise_path without allow_unc, so a library on a mapped network
    drive (stored as UNC) still renders.
    """
    unified = path.replace("\\", "/")
    if unified.startswith(_DEVICE_PREFIXES):
        return True
    return unified.startswith("//") and not _is_under_configured_root(path)


def normalise_path(path: str, *, allow_unc: bool = False) -> Path:
    """Normalise a user-supplied path to an absolute resolved Path.

    The result is a canonical absolute path, independent of the terminal it was
    launched from. ``pathlib.Path`` is ``WindowsPath``, which already parses
    both ``C:/foo`` and ``C:\\foo`` as absolute, no separator munging is
    needed. Git Bash / MSYS2 virtual paths (``/c/Users`` -> ``C:/Users``) are
    the one form it does not understand, so those are translated first.

    Steps applied in order:
        1. Empty / whitespace-only rejection.
        2. Null-byte rejection (common injection vector).
        3. Device-path rejection (``\\\\?\\``, ``\\\\.\\``, ``\\??\\``), always.
        4. UNC rejection (``\\\\host\\share``) unless *allow_unc* is set or
           the path is lexically under an operator-configured library root
           (a library on a mapped network drive is stored as UNC, because
           ``Path.resolve()`` expands mapped drives). Checked before any
           filesystem access, since resolving a UNC path opens an SMB
           connection to that host.
        5. Drive-relative rejection (``C:foo``).
        6. Git Bash / MSYS2 virtual path translation.
        7. Absolute resolution via ``Path.resolve()``, eliminates ``..``
           segments and relative references.

    Args:
        path: The raw path string.
        allow_unc: Accept any UNC path. Only for Environment image paths,
            which SECURITY.md explicitly allows on NAS shares.

    Raises:
        ValueError: If path is empty, contains a null byte, or is a
            device, disallowed UNC, or drive-relative path.
    """
    if not path or not path.strip():
        raise ValueError("Path must not be empty.")

    if "\x00" in path:
        raise ValueError("Path contains a null byte.")

    unified = path.replace("\\", "/")
    if unified.startswith(_DEVICE_PREFIXES):
        raise ValueError("Device paths are not allowed.")
    if unified.startswith("//") and not allow_unc and not _is_under_configured_root(path):
        raise ValueError("UNC network paths are not allowed.")
    if _DRIVE_RELATIVE_RE.match(path):
        raise ValueError("Drive-relative paths (e.g. 'C:folder') are not allowed, use 'C:\\folder'.")

    # Git Bash / MSYS2 style virtual paths (/c/Users -> C:/Users).
    if re.match(r"^/[a-zA-Z]/", path):
        path = f"{path[1].upper()}:{path[2:]}"

    return Path(path).resolve()


def allowed_browse_roots() -> list[Path]:
    """Return every filesystem root the server-side file browser (and anything
    that consumes a path it returned) is permitted to touch: the configured
    library base directories, plus every drive letter, since the browser is
    also used to locate arbitrary source media (ROM packs, manual launch-target
    overrides) that legitimately live outside the library.

    Shared by the /filesystem/browse endpoint and any endpoint that accepts a
    path the browser produced, so the allowlist can never drift between the
    two call sites.
    """
    import string

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
# SOFTWARE_PATH with no further translation. "media" is deliberately excluded, that
# domain roots at MEDIA_PATH directly (see software_media.py) and never goes through
# this SOFTWARE_PATH-scoped resolver.
_LIBRARY_DOMAINS: frozenset[str] = frozenset({"games", "apps"})


def library_root() -> Path:
    """Return LIBRARY_PATH: the shared root one level above every domain
    subtree (software/, media/, system/...). Used for state that exists before
    a file's eventual destination domain is even known, e.g. chunked-upload
    staging, so that staging area is not nested inside any one domain's root.
    """
    from backend.core.settings import get_settings
    return Path(get_settings().get_env_var("LIBRARY_PATH")).resolve()


def media_root() -> Path:
    """Return MEDIA_PATH resolved, the root every Media upload lands under.

    An unset or blank value must never fall through to ``Path("").resolve()``,
    which is the process working directory.

    Raises:
        ValueError: If MEDIA_PATH is unset or blank.
    """
    from backend.core.settings import get_settings
    try:
        raw = get_settings().get_env_var("MEDIA_PATH")
    except KeyError:
        raw = ""
    if not raw or not raw.strip():
        raise ValueError("MEDIA_PATH is not configured.")
    return Path(raw).resolve()


# App-owned subdirectories of MEDIA_PATH. Slugs (slugify) never contain an
# underscore, so no upload or Accept All directory can take these names.
GAME_COVERS_DIRNAME = "_game_covers"
ASSET_STAGING_DIRNAME = "_asset_staging"
APP_INTERNAL_MEDIA_DIRNAMES: frozenset[str] = frozenset({GAME_COVERS_DIRNAME, ASSET_STAGING_DIRNAME})


def game_covers_root() -> Path:
    """MEDIA_PATH/_game_covers, where per-disc fetched cover art used to
    live (META-2). Nothing writes there now; it is kept so game delete can
    still sweep covers an earlier version left. Not created here.

    Raises:
        ValueError: If MEDIA_PATH is unset or blank.
    """
    return media_root() / GAME_COVERS_DIRNAME


def asset_staging_root() -> Path:
    """MEDIA_PATH/_asset_staging, the temp area downloads stream into before
    os.replace moves them to their final path (META-6, META-21). On the
    same volume as every download destination. Not created here.

    Raises:
        ValueError: If MEDIA_PATH is unset or blank.
    """
    return media_root() / ASSET_STAGING_DIRNAME


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
