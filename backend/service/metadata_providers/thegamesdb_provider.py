"""TheGamesDB implementation of the MetadataProvider protocol.

Wraps backend/service/thegamesdb_client.py's raw HTTP functions and adds
genre/developer/publisher ID resolution on top, using the Genre/Developer/
Publisher cache tables (backend/models/metadata_lookup.py). TheGamesDB's
/Genres, /Developers, /Publishers endpoints each return their entire list in
one call (no by-ID lookup exists) — so the cache is warmed once, in full,
the first time any of these is needed, and every id lookup thereafter is
local. A genre/developer/publisher id introduced by TheGamesDB after that
one-time warm-up would not be picked up automatically; this is a deliberate
tradeoff for staying "never re-fetch a known list" rather than re-checking
the API on every call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from backend.models.metadata_lookup import (
    Developer, Genre, Publisher,
    get_or_create_developer, get_or_create_genre, get_or_create_publisher,
)
from backend.service.metadata_providers import GameDetails, MetadataAsset, SearchResult

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_PROVIDER = "thegamesdb"


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
        except (TypeError, ValueError):
            continue
    return ids


def _ensure_genres_cached(db: "Session") -> None:
    if db.query(Genre).filter(Genre.provider == _PROVIDER).first() is not None:
        return
    from backend.service.thegamesdb_client import get_genres as _fetch_genres

    raw = _fetch_genres()
    entries = raw.get("data", {}).get("genres", {})
    values = entries.values() if isinstance(entries, dict) else entries
    for entry in values:
        gid, gname = entry.get("id"), entry.get("name")
        if gid is None or not gname:
            continue
        get_or_create_genre(db, gname, provider=_PROVIDER, external_id=int(gid))
    db.commit()


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
        games = raw.get("data", {}).get("games", [])
        if not isinstance(games, list):
            games = list(games.values()) if isinstance(games, dict) else []
        return [
            SearchResult(
                game_id=g["id"],
                title=g.get("game_title"),
                release_date=g.get("release_date"),
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
            raw_platform = game.get("platform")
            if raw_platform is not None:
                try:
                    result.platform_id = int(raw_platform)
                except (ValueError, TypeError):
                    pass

            genre_ids = _ids_from_game_field(game, "genres")
            if genre_ids:
                _ensure_genres_cached(db)
                rows = db.query(Genre).filter(
                    Genre.provider == _PROVIDER, Genre.external_id.in_(genre_ids)
                ).all()
                result.genres = sorted(r.name for r in rows)

            developer_ids = _ids_from_game_field(game, "developers")
            if developer_ids:
                _ensure_developers_cached(db)
                # Single-valued in this app's schema — first id is treated as primary.
                row = db.query(Developer).filter(
                    Developer.provider == _PROVIDER, Developer.external_id == developer_ids[0]
                ).first()
                result.developer = row.name if row else None

            publisher_ids = _ids_from_game_field(game, "publishers")
            if publisher_ids:
                _ensure_publishers_cached(db)
                row = db.query(Publisher).filter(
                    Publisher.provider == _PROVIDER, Publisher.external_id == publisher_ids[0]
                ).first()
                result.publisher = row.name if row else None

        images_data = images_raw.get("data", {})
        base_url_obj = images_data.get("base_url", {})
        all_images = images_data.get("images", {}).get(str(game_id), [])

        # Full image set, every type (boxart front/back, screenshot, fanart,
        # banner, clearlogo, icon) and every image TheGamesDB returned for
        # this game, not just the one front-boxart cover — this is already
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
            result.assets.append(
                MetadataAsset(url=full_url, type=_asset_type_label(img), thumb_url=thumb_url)
            )

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
