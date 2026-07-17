"""IGDB implementation of the MetadataProvider protocol.

Auth: IGDB requires a Twitch Developer app. Client ID/secret live in .env
(env_secrets.py, same pattern as THEGAMESDB_API_KEY). The resulting app
access token is a short-lived, silently re-mintable derivative of the client
secret — not a root secret — so it's cached in settings
(igdb_access_token / igdb_access_token_expires_at) instead, and losing it on
reset_db is harmless (the next call just mints a new one).

No background refresh worker. Refresh is entirely lazy and inline on the
request path that needs a token: proactive refresh once the cached token is
within _REFRESH_MARGIN_SECONDS of expiring, plus a one-shot forced refresh
and retry if a call still comes back 401 (covers clock skew / a token
revoked out from under us).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import httpx

from backend.models.metadata_lookup import get_or_create_developer, get_or_create_genre, get_or_create_publisher
from backend.service.metadata_providers import GameDetails, MetadataAsset, SearchResult

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_IGDB_BASE_URL = "https://api.igdb.com/v4"
_TIMEOUT = 15.0
_PROVIDER = "igdb"

# Refresh proactively once less than this much time remains, rather than
# waiting for the token to actually expire mid-request.
_REFRESH_MARGIN_SECONDS = 24 * 60 * 60  # 1 day


def _client_credentials() -> tuple[str, str]:
    from backend.service.utils.env_secrets import get_env_secret

    client_id = get_env_secret("IGDB_CLIENT_ID")
    client_secret = get_env_secret("IGDB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ValueError(
            "IGDB_CLIENT_ID / IGDB_CLIENT_SECRET are not configured. "
            "Set them via Settings > Metadata before using IGDB features."
        )
    return client_id, client_secret


def _fetch_new_token() -> tuple[str, float]:
    """POST to Twitch's client-credentials endpoint. Returns (access_token, expires_at_epoch)."""
    client_id, client_secret = _client_credentials()
    response = httpx.post(
        _TWITCH_TOKEN_URL,
        params={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    body = response.json()
    return body["access_token"], time.time() + float(body["expires_in"])


def _get_valid_token(*, force_refresh: bool = False) -> str:
    """Return a usable access token, refreshing lazily/on-demand only."""
    from backend.service.utils import settings as _s

    if not force_refresh:
        cached_token = _s.get("igdb_access_token")
        cached_expires_at = _s.get("igdb_access_token_expires_at")
        if cached_token and cached_expires_at and (
            float(cached_expires_at) - time.time() > _REFRESH_MARGIN_SECONDS
        ):
            return cached_token

    token, expires_at = _fetch_new_token()
    _s.set_flag("igdb_access_token", token)
    _s.set_flag("igdb_access_token_expires_at", expires_at)
    return token


def _escape_apicalypse_string(value: str) -> str:
    """Escape a value for safe interpolation into an Apicalypse string literal.

    search_games() puts user-supplied text directly into a query body — the
    same injection concern as building raw SQL from user input. Apicalypse
    string literals are double-quoted; escaping backslashes and quotes closes
    the same "value breaks out of its quotes" class of bug SQL parameterization
    exists to prevent.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _post(path: str, body: str) -> list[dict]:
    """POST an Apicalypse query to IGDB, retrying once on 401 with a forced token refresh."""
    client_id, _ = _client_credentials()
    headers = {"Client-ID": client_id, "Authorization": f"Bearer {_get_valid_token()}"}
    response = httpx.post(f"{_IGDB_BASE_URL}/{path}", headers=headers, content=body, timeout=_TIMEOUT)
    if response.status_code == 401:
        headers["Authorization"] = f"Bearer {_get_valid_token(force_refresh=True)}"
        response = httpx.post(f"{_IGDB_BASE_URL}/{path}", headers=headers, content=body, timeout=_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _cover_url(cover: dict | None, size: str) -> str | None:
    """Build a full https:// IGDB CDN URL from a cover object.

    IGDB's own image_id field is not itself a URL — the CDN path convention
    (images.igdb.com/igdb/image/upload/{size}/{image_id}.jpg) is documented
    but the API never returns a scheme, so this must always produce a full
    https:// URL. enrich.py's _download_cover_art() rejects anything that
    doesn't start with "https://" outright.
    """
    if not cover or not cover.get("image_id"):
        return None
    return f"https://images.igdb.com/igdb/image/upload/{size}/{cover['image_id']}.jpg"


def _unix_to_date_string(epoch: int | None) -> str | None:
    if epoch is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


# Maps IGDB's age_ratings.organization.name + age_ratings.rating_category.rating
# onto this app's exact content_ratings vocabulary (config/constants.yaml) — the
# same vocabulary normalize_content_rating() (backend/core/dependencies.py)
# enforces. Only ESRB and PEGI are covered because those are the only two
# schemes that vocabulary defines; IGDB's other organizations (CERO, USK,
# GRAC, ACB) have no equivalent entry to map onto and are deliberately absent
# — an age rating from one of those always resolves to None, not a guess.
#
# IGDB migrated this endpoint from a flat numeric category/rating enum to a
# relational organization/rating_category schema (confirmed via IGDB's public
# schema docs and community-maintained type definitions — api-docs.igdb.com
# itself blocked automated fetches during this investigation, so this couldn't
# be cross-checked against a live query or IGDB's own rendered docs page).
# Both the short ESRB codes and both word-form and numeral-form PEGI labels
# are included below since the exact current string IGDB returns for
# rating_category.rating could not be confirmed with full certainty from
# secondary sources alone — deliberately over-covering matches, on the
# principle that a spurious lookup miss (-> None, unrated) is always safe
# here, while a wrong or over-broad match would not be.
_IGDB_RATING_MAP: dict[str, dict[str, str]] = {
    "ESRB": {
        "EC": "EC",
        "E": "E",
        "E10": "E10+",
        "E10+": "E10+",
        "EVERYONE 10+": "E10+",
        "T": "T",
        "TEEN": "T",
        "M": "M",
        "MATURE": "M",
        "MATURE 17+": "M",
        "AO": "AO",
        "ADULTS ONLY": "AO",
        # RP (Rating Pending) has no equivalent in this app's vocabulary and is
        # intentionally omitted — falls through to None (unrated), not guessed.
    },
    "PEGI": {
        "3": "PEGI 3", "THREE": "PEGI 3",
        "7": "PEGI 7", "SEVEN": "PEGI 7",
        "12": "PEGI 12", "TWELVE": "PEGI 12",
        "16": "PEGI 16", "SIXTEEN": "PEGI 16",
        "18": "PEGI 18", "EIGHTEEN": "PEGI 18",
    },
}


def _resolve_igdb_content_rating(age_ratings: list[dict] | None) -> str | None:
    """Resolve IGDB's age_ratings list to this app's content_rating vocabulary.

    Priority order: ESRB first, then PEGI, matching the convention this app
    already established via TheGamesDB (whose own `rating` field is itself
    ESRB-shaped, e.g. "M - Mature 17+"). A title with only a PEGI rating still
    resolves via PEGI; a title with neither recognised, or with only
    unsupported schemes (CERO/USK/GRAC/ACB), resolves to None — same safe-null
    behavior as an unrecognised TheGamesDB rating string today.
    """
    by_org: dict[str, str] = {}
    for entry in age_ratings or []:
        org_name = (entry.get("organization") or {}).get("name")
        rating_label = (entry.get("rating_category") or {}).get("rating")
        if not org_name or not rating_label:
            continue
        org_key = org_name.strip().upper()
        mapped = _IGDB_RATING_MAP.get(org_key, {}).get(rating_label.strip().upper())
        if mapped and org_key not in by_org:
            by_org[org_key] = mapped
    return by_org.get("ESRB") or by_org.get("PEGI")


class IGDBProvider:
    def search_games(self, name: str) -> list[SearchResult]:
        query = f'fields name,first_release_date; search "{_escape_apicalypse_string(name)}"; limit 20;'
        games = _post("games", query)
        return [
            SearchResult(
                game_id=g["id"],
                title=g.get("name"),
                release_date=_unix_to_date_string(g.get("first_release_date")),
            )
            for g in games
            if g.get("id") is not None
        ]

    def get_game_details(self, game_id: int, db: "Session") -> GameDetails:
        query = (
            "fields name,first_release_date,summary,"
            "genres.name,involved_companies.company.name,involved_companies.developer,"
            "involved_companies.publisher,cover.image_id,platforms,videos.video_id,"
            "age_ratings.organization.name,age_ratings.rating_category.rating; "
            f"where id = {int(game_id)}; limit 1;"
        )
        games = _post("games", query)
        game = games[0] if games else None

        result = GameDetails(game_id=game_id)
        if not game:
            return result

        result.title = game.get("name") or None
        result.release_date = _unix_to_date_string(game.get("first_release_date"))
        result.overview = game.get("summary") or None
        # Note: IGDB's `rating` field (a 0-100 aggregate user-rating score) is
        # never used here — it is not an ESRB/PEGI-style content rating and
        # would corrupt enrich.py's normalize_content_rating(), which drives
        # this app's parental content-rating filter. The real content rating
        # comes from the separate age_ratings field, resolved below.
        result.rating = _resolve_igdb_content_rating(game.get("age_ratings"))
        platforms = game.get("platforms") or []
        if platforms and isinstance(platforms[0], int):
            result.platform_id = platforms[0]

        genre_names: list[str] = []
        for genre in game.get("genres") or []:
            gid, gname = genre.get("id"), genre.get("name")
            if gid is None or not gname:
                continue
            get_or_create_genre(db, gname, provider=_PROVIDER, external_id=int(gid))
            genre_names.append(gname)
        result.genres = sorted(genre_names)

        for involved in game.get("involved_companies") or []:
            company = involved.get("company") or {}
            cid, cname = company.get("id"), company.get("name")
            if cid is None or not cname:
                continue
            if involved.get("developer") and result.developer is None:
                get_or_create_developer(db, _PROVIDER, int(cid), cname)
                result.developer = cname
            if involved.get("publisher") and result.publisher is None:
                get_or_create_publisher(db, _PROVIDER, int(cid), cname)
                result.publisher = cname

        db.commit()

        result.cover_art_url = _cover_url(game.get("cover"), "t_cover_big")
        result.cover_art_thumb_url = _cover_url(game.get("cover"), "t_thumb")

        # IGDB's own screenshots/artworks fields are deliberately not fetched
        # here (out of scope for this pass, TheGamesDB was the one audited
        # for image completeness this session) — assets only carries IGDB's
        # existing single cover image today, wrapped in the same shape
        # TheGamesDB's multi-image assets list uses, so the Accept All flow
        # never needs to special-case which provider produced a given asset.
        if result.cover_art_url:
            result.assets.append(
                MetadataAsset(url=result.cover_art_url, type="cover", thumb_url=result.cover_art_thumb_url)
            )

        for video in game.get("videos") or []:
            video_id = video.get("video_id")
            if video_id:
                result.video_urls.append(f"https://www.youtube.com/watch?v={video_id}")

        return result
