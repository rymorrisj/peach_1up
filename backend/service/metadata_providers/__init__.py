"""Provider-agnostic metadata search/fetch abstraction.

software_metadata.py talks to this package only, never to a concrete provider
client, get_active_provider() reads the metadata_provider settings key
and returns the matching implementation. Adding a provider means adding a
module here plus one branch in get_active_provider(); no route or enrich.py
changes are needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional, Protocol, get_args

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# Every asset type label a provider can emit, and therefore the only values
# the Accept All route (backend/api/routes/game_metadata.py) accepts back
# from the client. The label becomes part of an on-disk filename stem
# (backend/service/games/media_link.py), so it is allowlisted at the API
# boundary rather than trusted.
#   IGDB:       "cover" (igdb_provider.py emits exactly one).
#   TheGamesDB: "{type}_{side}" when the image has a side, else "{type}"
#               (thegamesdb_provider._asset_type_label), over TheGamesDB's
#               documented image types. Labels outside this set are dropped
#               by the provider, never offered to the client.
AssetType = Literal[
    "cover",
    "boxart_front",
    "boxart_back",
    "screenshot",
    "fanart",
    "banner",
    "clearlogo",
    "icon",
]
ASSET_TYPES: frozenset[str] = frozenset(get_args(AssetType))

# The only hosts the server-side asset downloader
# (backend/service/utils/asset_fetch.py) will contact, on the first request
# and on every redirect hop. IGDB builds its image URLs against
# images.igdb.com (igdb_provider._cover_url); TheGamesDB returns
# base_url.original/thumb on cdn.thegamesdb.net. Adding a provider means
# adding its image CDN host here.
ASSET_CDN_HOSTS: frozenset[str] = frozenset({
    "images.igdb.com",
    "cdn.thegamesdb.net",
})


@dataclass
class SearchResult:
    game_id: int
    title: Optional[str]
    release_date: Optional[str]


@dataclass
class MetadataAsset:
    """One downloadable image a provider returned, offered to the Accept All
    flow (backend/service/games/media_link.py) for server-side download into
    a linked Media item. url is the best/original-resolution URL to actually
    download; thumb_url (when the provider has one) is only for the
    frontend's preview, never downloaded server-side."""

    url: str
    type: str
    thumb_url: Optional[str] = None


@dataclass
class GameDetails:
    game_id: int
    title: Optional[str] = None
    release_date: Optional[str] = None
    overview: Optional[str] = None
    rating: Optional[str] = None
    provider_platform_id: Optional[int] = None
    cover_art_url: Optional[str] = None
    cover_art_thumb_url: Optional[str] = None
    genres: list[str] = field(default_factory=list)
    developer: Optional[str] = None
    publisher: Optional[str] = None
    video_urls: list[str] = field(default_factory=list)
    assets: list[MetadataAsset] = field(default_factory=list)


class MetadataProvider(Protocol):
    """Every provider owns however many underlying API calls and local
    caching it needs, callers only ever see fully-resolved names."""

    def search_games(self, name: str) -> list[SearchResult]: ...

    def get_game_details(self, game_id: int, db: "Session") -> GameDetails: ...


def is_metadata_fetch_enabled() -> bool:
    """Return True only when the owner has turned on metadata_fetch_enabled.

    Fails closed: an unset key, a non-bool stored value, or settings not yet
    initialised (RuntimeError) all read as disabled.
    """
    from backend.service.utils import settings as _s

    try:
        return _s.get("metadata_fetch_enabled", False) is True
    except RuntimeError:
        return False


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
