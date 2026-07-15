"""Provider-agnostic metadata search/fetch abstraction.

software_metadata.py talks to this package only, never to a concrete provider
client — get_active_provider() reads the metadata_provider settings key
and returns the matching implementation. Adding a provider means adding a
module here plus one branch in get_active_provider(); no route or enrich.py
changes are needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Protocol

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass
class SearchResult:
    game_id: int
    title: Optional[str]
    release_date: Optional[str]


@dataclass
class GameDetails:
    game_id: int
    title: Optional[str] = None
    release_date: Optional[str] = None
    overview: Optional[str] = None
    rating: Optional[str] = None
    platform_id: Optional[int] = None
    cover_art_url: Optional[str] = None
    cover_art_thumb_url: Optional[str] = None
    genres: list[str] = field(default_factory=list)
    developer: Optional[str] = None
    publisher: Optional[str] = None


class MetadataProvider(Protocol):
    """Every provider owns however many underlying API calls and local
    caching it needs — callers only ever see fully-resolved names."""

    def search_games(self, name: str) -> list[SearchResult]: ...

    def get_game_details(self, game_id: int, db: "Session") -> GameDetails: ...


def get_active_provider() -> MetadataProvider:
    """Return the MetadataProvider selected by the metadata_provider settings key.

    Raises:
        ValueError: If the stored value is not a recognised provider name.
    """
    from backend.service.utils import settings as _s

    provider = _s.get("metadata_provider", "thegamesdb")
    if provider == "thegamesdb":
        from backend.service.metadata_providers.thegamesdb_provider import TheGamesDBProvider
        return TheGamesDBProvider()
    if provider == "igdb":
        from backend.service.metadata_providers.igdb_provider import IGDBProvider
        return IGDBProvider()
    raise ValueError(f"Unknown metadata_provider {provider!r}; expected 'thegamesdb' or 'igdb'.")
