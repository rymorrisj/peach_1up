"""Known titles database utilities for Peach 1UP.

Provides lookup functions against the community-curated known_titles.yaml.
requires_86box: true in that file is the authoritative signal for accuracy
mode routing — no automated heuristics are used.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml


_REQUIRED_FIELDS = frozenset({"name", "era", "requires_86box"})


def load_titles(titles_path: Path) -> list[dict]:
    """Load and validate all entries from known_titles.yaml.

    Args:
        titles_path: Path to ``known_titles.yaml``.

    Returns:
        List of validated title dicts, or an empty list if the file is missing
        or the ``titles`` key is absent or empty.

    Raises:
        ValueError: If any entry is missing a required field, has an invalid
            ``era`` value, or has a non-bool ``requires_86box`` value.
        yaml.YAMLError: If the file exists but is not valid YAML.
    """
    if not titles_path.exists():
        return []

    with titles_path.open("r", encoding="utf-8") as fh:
        raw: Any = yaml.safe_load(fh)

    if not isinstance(raw, dict) or not raw.get("titles"):
        return []

    validated: list[dict] = []
    for i, entry in enumerate(raw["titles"]):
        if not isinstance(entry, dict):
            raise ValueError(
                f"known_titles.yaml entry {i} is not a mapping"
            )

        missing = _REQUIRED_FIELDS - entry.keys()
        if missing:
            raise ValueError(
                f"known_titles.yaml entry {i} is missing required fields: "
                + ", ".join(sorted(missing))
            )

        era = str(entry["era"])
        if era not in {"win95", "win98"}:
            raise ValueError(
                f"known_titles.yaml entry {i} ('{entry['name']}') has invalid era "
                f"'{era}'. Valid values: {', '.join(sorted(_VALID_ERAS))}"
            )

        if not isinstance(entry["requires_86box"], bool):
            raise ValueError(
                f"known_titles.yaml entry {i} ('{entry['name']}') has non-bool "
                f"requires_86box value '{entry['requires_86box']}'"
            )

        validated.append(entry)

    return validated


def get_title(title_name: str, titles_path: Path) -> Optional[dict]:
    """Return the first database entry matching the title name, or None.

    Matching is case-insensitive with leading/trailing whitespace stripped.
    Returns None on no match, a missing database, or any load error.

    Args:
        title_name: Title name to look up.
        titles_path: Path to ``known_titles.yaml``.

    Returns:
        The matching entry dict, or None.
    """
    try:
        needle = title_name.strip().lower()
        for entry in load_titles(titles_path):
            if str(entry["name"]).strip().lower() == needle:
                return entry
    except Exception:
        pass
    return None
