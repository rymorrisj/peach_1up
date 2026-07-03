"""Slug generation utilities.

Produces lowercase hyphenated slugs with ascending integer suffixes on
collision: doom → doom-2 → doom-3.

Public API:
    slugify       — normalise a name to a base slug string.
    unique_slug   — produce a collision-free slug using a caller-supplied check.
    generate_collection_slug — convenience wrapper for LibraryCollection slugs.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from sqlalchemy.orm import Session


def slugify(name: str, *, fallback: str = "item") -> str:
    """Return a normalised base slug for *name*.

    Lowercases, collapses whitespace to hyphens, strips non-alphanumeric
    characters (except hyphens), and trims leading/trailing hyphens.
    Falls back to *fallback* when the result would be empty.
    """
    return re.sub(r"[^a-z0-9-]", "", re.sub(r"\s+", "-", name.lower())).strip("-") or fallback


def unique_slug(name: str, query_fn: Callable[[str], bool], *, fallback: str = "item") -> str:
    """Return a collision-free slug for *name*.

    Args:
        name:     Human-readable title to slugify.
        query_fn: Returns True if the candidate slug is already taken.
        fallback: Base slug to use when *name* normalises to an empty string.

    Returns:
        The first candidate (base, base-2, base-3, …) for which
        *query_fn* returns False.
    """
    base = slugify(name, fallback=fallback)
    candidate = base
    n = 2
    while query_fn(candidate):
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def generate_collection_slug(name: str, db: Session) -> str:
    """Return a unique slug for a LibraryCollection.

    Args:
        name: Human-readable title of the collection.
        db:   Active database session used for collision detection.

    Returns:
        A globally unique slug string suitable for use as a folder name.
    """
    from backend.models.library import LibraryCollection

    return unique_slug(
        name,
        lambda s: db.query(LibraryCollection).filter(LibraryCollection.slug == s).first() is not None,
    )
