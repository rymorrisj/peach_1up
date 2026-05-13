"""Profile builder utilities for Peach 1UP.

Library scan pipeline. Pure business logic with no Textual dependencies,
callable from FastAPI route handlers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.constants_generated import Era


_SCAN_EXTENSIONS: frozenset[str] = frozenset({".iso", ".img", ".cue"})


def sanitize_name(stem: str) -> str:
    """Produce a safe profile name from a filename stem.

    Strips characters invalid in a YAML filename stem, collapses runs of
    whitespace and hyphens to underscores, and truncates to 50 characters.

    Args:
        stem: The filename stem to sanitise (no extension).

    Returns:
        A non-empty safe profile name string.
    """
    name = re.sub(r"[^\w\s\-]", "", stem).strip()
    name = re.sub(r"[\s\-]+", "_", name)
    return name[:50] or "unnamed"


@dataclass
class ScanEntry:
    """A single media file found during a library scan.

    Attributes:
        path: Absolute path to the media file.
        era: Detected era, or ``None`` if detection was uncertain.
        name: Sanitised profile name derived from the filename stem.
        selected: Whether this entry is marked for import. Defaults to True.
    """
    path: Path
    era: Optional[Era]
    name: str
    selected: bool = True


def scan_directory(base: Path) -> list[ScanEntry]:
    """Walk ``base`` recursively and return a ``ScanEntry`` for each media file.

    Skips files and directories that raise ``OSError`` or ``PermissionError``
    rather than aborting the scan. Returns results sorted by path.

    Args:
        base: Directory to scan recursively.

    Returns:
        Sorted list of ``ScanEntry`` objects for every ``.iso``, ``.img``,
        and ``.cue`` file found. Empty if none are found or ``base`` is
        unreadable.
    """
    from backend.service.utils.media_detect import detect_era

    found: list[Path] = []
    try:
        for p in base.rglob("*"):
            try:
                if p.is_file() and p.suffix.lower() in _SCAN_EXTENSIONS:
                    found.append(p)
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        pass
    found.sort()
    return [ScanEntry(path=p, era=detect_era(p), name=sanitize_name(p.stem)) for p in found]


