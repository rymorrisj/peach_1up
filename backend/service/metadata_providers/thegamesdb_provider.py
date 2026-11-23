"""TheGamesDB implementation of the MetadataProvider protocol.

Wraps backend/service/thegamesdb_client.py's raw HTTP functions and adds
genre/developer/publisher ID resolution on top, using the Genre/Developer/
Publisher cache tables (backend/models/metadata_lookup.py). TheGamesDB's
/Genres, /Developers, /Publishers endpoints each return their entire list in
one call (no by-ID lookup exists), so the cache is warmed once, in full,
the first time any of these is needed, and every id lookup thereafter is
local. A genre id missing from the cache triggers one re-warm of the genre
list per fetch; ids still unknown after that are reported back, never
dropped silently. Developer and publisher ids are not re-warmed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import httpx2

from backend.core.logger import get_logger
from backend.models.metadata_lookup import (
    Developer,
    Genre,
    Publisher,
    get_or_create_developer,
    get_or_create_genre,
    get_or_create_publisher,
)
from backend.service.metadata_providers import ASSET_TYPES, GameDetails, MetadataAsset, SearchResult

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_PROVIDER = "thegamesdb"
_log = get_logger(__name__)


def _youtube_url(value: object) -> Optional[str]:
    """TheGamesDB's youtube field convention is not fully confirmed live
    (see this session's earlier discovery: api.thegamesdb.net was blocked by
    sandbox network policy). Community scraper implementations treat it as a
    bare video id needing the watch-url prefix, so that's the default
    assumption here, but a value that already looks like a full URL is
    passed through unchanged rather than double-prefixed, so either shape
    resolves correctly regardless of which one TheGamesDB actually returns."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://www.youtube.com/watch?v={value}"


def _asset_type_label(img: dict) -> str:
    img_type = img.get("type") or "image"
    side = img.get("side")
    return f"{img_type}_{side}" if side else img_type


def _asset_urls(base_url_obj: dict, filename: str) -> tuple[Optional[str], Optional[str]]:
    """Build (full_url, thumb_url) for one image filename, using the same
    original/thumb base_url keys the existing cover-art construction already
    relies on (the only two keys this codebase has confirmed TheGamesDB
    returns)."""
    original = (base_url_obj.get("original") or "").rstrip("/")
    thumb = (base_url_obj.get("thumb") or "").rstrip("/")
    clean_filename = filename.lstrip("/")
    if not clean_filename:
        return None, None
    full_url = f"{original}/{clean_filename}" if original else None
    thumb_url = f"{thumb}/{clean_filename}" if thumb else None
    return full_url, thumb_url


def _ids_from_game_field(game: dict, field: str) -> list[int]:
    raw = game.get(field)
    if not isinstance(raw, list):
        return []
    ids: list[int] = []
    for value in raw:
        try:
            ids.append(int(value))
        except TypeError, ValueError:
            continue
    return ids


def _platform_names(raw: dict) -> dict[int, str]:
    """Platform id -> name from a search response's include.platform table."""
    data = ((raw.get("include") or {}).get("platform") or {}).get("data") or {}
    entries = data.values() if isinstance(data, dict) else data
    names: dict[int, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        try:
            names[int(entry.get("id"))] = entry["name"]
        except TypeError, ValueError:
            continue
    return names


def _platform_label(game: dict, names: dict[int, str]) -> Optional[str]:
    try:
        return names.get(int(game.get("platform")))
    except TypeError, ValueError:
        return None


def _warm_genres(db: "Session") -> dict[int, str]:
    """Fetch TheGamesDB's full genre list into the cache and return it as
    id -> name. The returned names cover ids whose name was already cached
    under another provider, which the (provider, id) cache lookup cannot see."""
    from backend.service.thegamesdb_client import get_genres as _fetch_genres

    raw = _fetch_genres()
    entries = raw.get("data", {}).get("genres", {})
    values = entries.values() if isinstance(entries, dict) else entries
    names: dict[int, str] = {}
    for entry in values:
        gid, gname = entry.get("id"), entry.get("name")
        if gid is None or not gname:
            continue
        get_or_create_genre(db, gname, provider=_PROVIDER, external_id=int(gid))
        names[int(gid)] = gname
    db.commit()
    return names


def _cached_genre_names(db: "Session", ids: list[int]) -> dict[int, str]:
    rows = db.query(Genre).filter(Genre.provider == _PROVIDER, Genre.external_id.in_(ids)).all()
    return {r.external_id: r.name for r in rows}


def _resolve_genres(db: "Session", ids: list[int]) -> tuple[list[str], list[int]]:
    """Return (sorted genre names, sorted ids that could not be resolved).

    On a cache miss the genre list is re-warmed once and the lookup retried. A
    failed re-warm is logged and leaves the misses unresolved rather than
    failing the fetch."""
    if db.query(Genre).filter(Genre.provider == _PROVIDER).first() is None:
        _warm_genres(db)
    found = _cached_genre_names(db, ids)
    missing = [i for i in ids if i not in found]
    if missing:
        try:
            fresh = _warm_genres(db)
        except httpx2.HTTPError as exc:
            _log.warning("TheGamesDB genre re-warm failed: %s", exc)
            fresh = {}
        found.update(_cached_genre_names(db, missing))
        found.update({i: fresh[i] for i in missing if i not in found and i in fresh})
    unresolved = sorted({i for i in ids if i not in found})
    if unresolved:
        _log.info("TheGamesDB genre ids not resolved: %s", unresolved)
    return sorted({found[i] for i in ids if i in found}), unresolved


def _ensure_developers_cached(db: "Session") -> None:
    if db.query(Developer).filter(Developer.provider == _PROVIDER).first() is not None:
        return
    from backend.service.thegamesdb_client import get_developers as _fetch_developers

    raw = _fetch_developers()
    entries = raw.get("data", {}).get("developers", {})
    values = entries.values() if isinstance(entries, dict) else entries
    for entry in values:
        did, dname = entry.get("id"), entry.get("name")
        if did is None or not dname:
            continue
        get_or_create_developer(db, _PROVIDER, int(did), dname)
    db.commit()


def _ensure_publishers_cached(db: "Session") -> None:
    if db.query(Publisher).filter(Publisher.provider == _PROVIDER).first() is not None:
        return
    from backend.service.thegamesdb_client import get_publishers as _fetch_publishers

    raw = _fetch_publishers()
    entries = raw.get("data", {}).get("publishers", {})
    values = entries.values() if isinstance(entries, dict) else entries
    for entry in values:
        pid, pname = entry.get("id"), entry.get("name")
        if pid is None or not pname:
            continue
        get_or_create_publisher(db, _PROVIDER, int(pid), pname)
    db.commit()


class TheGamesDBProvider:
    def search_games(self, name: str) -> list[SearchResult]:
        from backend.service.thegamesdb_client import search_games as _search

        raw = _search(name)
        platform_names = _platform_names(raw)
        games = raw.get("data", {}).get("games", [])
        if not isinstance(games, list):
            games = list(games.values()) if isinstance(games, dict) else []
        return [
            SearchResult(
                game_id=g["id"],
                title=g.get("game_title"),
                release_date=g.get("release_date"),
                platform=_platform_label(g, platform_names),
            )
            for g in games
            if g.get("id") is not None
        ]

    def get_game_details(self, game_id: int, db: "Session") -> GameDetails:
        from backend.service.thegamesdb_client import get_game_details as _details
        from backend.service.thegamesdb_client import get_game_images as _images

        details_raw = _details(game_id)
        images_raw = _images(game_id)

        games_raw = details_raw.get("data", {}).get("games", {})
        games_map = (
            {str(g["id"]): g for g in games_raw if g.get("id") is not None}
            if isinstance(games_raw, list)
            else (games_raw if isinstance(games_raw, dict) else {})
        )
        game = games_map.get(str(game_id)) or (next(iter(games_map.values()), None) if games_map else None)

        result = GameDetails(game_id=game_id)

        if game:
            result.title = game.get("game_title") or None
            result.release_date = game.get("release_date") or None
            result.overview = game.get("overview") or None
            result.rating = game.get("rating") or None
            youtube_url = _youtube_url(game.get("youtube"))
            if youtube_url:
                result.video_urls = [youtube_url]
            raw_provider_platform = game.get("platform")
            if raw_provider_platform is not None:
                try:
                    result.provider_platform_id = int(raw_provider_platform)
                except ValueError, TypeError:
                    pass

            genre_ids = _ids_from_game_field(game, "genres")
            if genre_ids:
                result.genres, result.unresolved_genre_ids = _resolve_genres(db, genre_ids)

            developer_ids = _ids_from_game_field(game, "developers")
            if developer_ids:
                _ensure_developers_cached(db)
                # Single-valued in this app's schema, first id is treated as primary.
                row = (
                    db.query(Developer)
                    .filter(Developer.provider == _PROVIDER, Developer.external_id == developer_ids[0])
                    .first()
                )
                result.developer = row.name if row else None

            publisher_ids = _ids_from_game_field(game, "publishers")
            if publisher_ids:
                _ensure_publishers_cached(db)
                row = (
                    db.query(Publisher)
                    .filter(Publisher.provider == _PROVIDER, Publisher.external_id == publisher_ids[0])
                    .first()
                )
                result.publisher = row.name if row else None

        images_data = images_raw.get("data", {})
        base_url_obj = images_data.get("base_url", {})
        all_images = images_data.get("images", {}).get(str(game_id), [])

        # Full image set, every type (boxart front/back, screenshot, fanart,
        # banner, clearlogo, icon) and every image TheGamesDB returned for
        # this game, not just the one front-boxart cover, this is already
        # the full payload get_game_images() fetched, previously discarded
        # down to a single image here. cover_art_url/cover_art_thumb_url
        # below are left pointing at the front boxart specifically and
        # unchanged in behavior, existing consumers (the Keep flow's applied
        # cover art) depend on that.
        for img in all_images:
            filename = img.get("filename", "")
            full_url, thumb_url = _asset_urls(base_url_obj, filename)
            if not full_url:
                continue
            label = _asset_type_label(img)
            if label not in ASSET_TYPES:
                # Accept All rejects any type outside ASSET_TYPES, so an
                # unrecognised label is not offered to the client at all.
                continue
            result.assets.append(MetadataAsset(url=full_url, type=label, thumb_url=thumb_url))

        front_boxart = next(
            (img for img in all_images if img.get("type") == "boxart" and img.get("side") == "front"),
            None,
        )
        if front_boxart:
            filename = front_boxart.get("filename", "")
            full_url, thumb_url = _asset_urls(base_url_obj, filename)
            if full_url:
                result.cover_art_url = full_url
            if thumb_url:
                result.cover_art_thumb_url = thumb_url

        return result
