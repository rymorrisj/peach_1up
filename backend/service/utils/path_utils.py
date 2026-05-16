"""Path normalisation for Peach 1UP.

Every path arriving from external input (request bodies, query params, settings
forms) must pass through normalise_path before any allowlist check or filesystem
operation. This module is the single choke-point for that normalisation.
"""

from pathlib import Path


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
