"""Path normalisation for Peach 1UP.

Every path arriving from external input (request bodies, query params, settings
forms) must pass through normalise_path before any allowlist check or filesystem
operation. This module is the single choke-point for that normalisation.
"""

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

    Steps applied in order:
    1. Null-byte rejection (common injection vector).
    2. Separator unification to os.sep.
    3. Absolute resolution via Path.resolve() — eliminates ``..`` segments
       and relative references, producing a canonical absolute path.

    Args:
        path: Raw path string from user input.

    Returns:
        Resolved absolute Path with OS-native separators.

    Raises:
        ValueError: If path is empty or contains a null byte.
    """
    if not path or not path.strip():
        raise ValueError("Path must not be empty.")
    if "\x00" in path:
        raise ValueError("Path contains a null byte.")
    unified = path.replace("\\", "/")
    return Path(unified).resolve()
