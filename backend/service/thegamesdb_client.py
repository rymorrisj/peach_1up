"""Thin HTTP client for TheGamesDB REST API v1/v1.1.

Each function reads the API key fresh from .env at call time.
Raises ValueError if the key is not configured.
Raises httpx.HTTPStatusError on non-2xx responses.
Raises httpx.TimeoutException on timeout.
No caching, no retries, no rate-limit tracking.
"""

from __future__ import annotations

import httpx

_BASE_V1 = "https://api.thegamesdb.net/v1"
_BASE_V1_1 = "https://api.thegamesdb.net/v1.1"
_TIMEOUT = 15.0


def _api_key() -> str:
    from backend.service.utils.env_secrets import get_env_secret
    key = get_env_secret("THEGAMESDB_API_KEY")
    if not key:
        raise ValueError(
            "THEGAMESDB_API_KEY is not configured. "
            "Set it via Settings > Metadata before using TheGamesDB features."
        )
    return key


def search_games(name: str) -> dict:
    """Search games by name.

    Calls GET /v1.1/Games/ByGameName and returns the parsed JSON response body.

    Args:
        name: Game title to search for.

    Raises:
        ValueError: If THEGAMESDB_API_KEY is not configured.
        httpx.HTTPStatusError: On non-2xx response.
        httpx.TimeoutException: On request timeout.
    """
    key = _api_key()
    response = httpx.get(
        f"{_BASE_V1_1}/Games/ByGameName",
        params={"apikey": key, "name": name},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def get_game_images(game_id: int) -> dict:
    """Fetch images for a game by its TheGamesDB ID.

    Calls GET /v1/Games/Images and returns the parsed JSON response body.

    Args:
        game_id: The TheGamesDB numeric game identifier.

    Raises:
        ValueError: If THEGAMESDB_API_KEY is not configured.
        httpx.HTTPStatusError: On non-2xx response.
        httpx.TimeoutException: On request timeout.
    """
    key = _api_key()
    response = httpx.get(
        f"{_BASE_V1}/Games/Images",
        params={"apikey": key, "games_id": game_id},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def get_game_details(game_id: int) -> dict:
    """Fetch detailed metadata for a game by its TheGamesDB ID.

    Calls GET /v1/Games/ByGameID with overview, rating, genres, publishers,
    developers, and platform fields.

    Args:
        game_id: The TheGamesDB numeric game identifier.

    Raises:
        ValueError: If THEGAMESDB_API_KEY is not configured.
        httpx.HTTPStatusError: On non-2xx response.
        httpx.TimeoutException: On request timeout.
    """
    key = _api_key()
    response = httpx.get(
        f"{_BASE_V1}/Games/ByGameID",
        params={
            "apikey": key,
            "id": game_id,
            "fields": "overview,rating,genres,publishers,developers,platform",
        },
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()
