"""Slug generation for library items.

Produces lowercase hyphenated slugs with ascending integer suffixes on
collision: doom → doom-2 → doom-3. Uniqueness is checked globally across
all library items, not per-era.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session


def generate_item_slug(name: str, era: str, db: Session) -> str:  # noqa: ARG001 — era reserved for future per-era folders
    """Return a unique slug for a library item.

    Args:
        name: Human-readable title of the item.
        era:  Era string (reserved; uniqueness is checked globally).
        db:   Active database session used for collision detection.

    Returns:
        A globally unique slug string suitable for use as a folder name.
    """
    from backend.models.library import LibraryItem

    base = re.sub(r"[^a-z0-9-]", "", re.sub(r"\s+", "-", name.lower())).strip("-") or "item"
    candidate = base
    n = 2
    while True:
        if not db.query(LibraryItem).filter(LibraryItem.slug == candidate).first():
            return candidate
        candidate = f"{base}-{n}"
        n += 1
