from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core import rate_limit
from backend.core.database import get_db
from backend.core.dependencies import require_permission
from backend.models.library import item_to_read
from backend.models.library_set import LibrarySetItemRead, set_to_read
from backend.models.user import User
from backend.service.library import enrich as enrich_svc

router = APIRouter(prefix="/api/v1/library", tags=["library"])

_METADATA_RATE_LIMIT = 30
_METADATA_RATE_WINDOW_SECONDS = 60.0
_ENRICH_RATE_LIMIT = 30
_ENRICH_RATE_WINDOW_SECONDS = 60.0


def _enforce_rate_limit(bucket: str, request: Request, limit: int, window_seconds: float) -> None:
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = rate_limit.check_and_record(f"{bucket}:{client_ip}", limit, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests, please slow down.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


class EnrichBody(BaseModel):
    entity_type: Literal["library_item", "library_set", "library_set_item"]
    entity_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    content_rating: Optional[str] = None
    metadata_source: Optional[str] = None
    cover_art_url: Optional[str] = None


@router.get("/metadata-search")
def search_metadata(
    request: Request,
    name: str = Query(...),
    _: User = require_permission("is_owner"),
):
    _enforce_rate_limit("library-metadata", request, _METADATA_RATE_LIMIT, _METADATA_RATE_WINDOW_SECONDS)

    import httpx
    from backend.service.thegamesdb_client import search_games

    try:
        raw = search_games(name)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"TheGamesDB API error: {exc.response.status_code}",
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="TheGamesDB API request timed out.")

    games = raw.get("data", {}).get("games", [])
    if not isinstance(games, list):
        games = list(games.values()) if isinstance(games, dict) else []

    return {
        "results": [
            {
                "game_id": g.get("id"),
                "title": g.get("game_title"),
                "release_date": g.get("release_date"),
            }
            for g in games
            if g.get("id") is not None
        ]
    }


@router.get("/metadata-details")
def get_metadata_details(
    request: Request,
    game_id: int = Query(...),
    _: User = require_permission("is_owner"),
):
    _enforce_rate_limit("library-metadata", request, _METADATA_RATE_LIMIT, _METADATA_RATE_WINDOW_SECONDS)

    import httpx
    from backend.service.thegamesdb_client import get_game_details, get_game_images

    try:
        details_raw = get_game_details(game_id)
        images_raw = get_game_images(game_id)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"TheGamesDB API error: {exc.response.status_code}",
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="TheGamesDB API request timed out.")

    games_raw = details_raw.get("data", {}).get("games", {})
    if isinstance(games_raw, list):
        games_map = {str(g["id"]): g for g in games_raw if g.get("id") is not None}
    else:
        games_map = games_raw if isinstance(games_raw, dict) else {}
    game = games_map.get(str(game_id))
    if game is None and games_map:
        game = next(iter(games_map.values()), None)

    title: str | None = None
    release_date: str | None = None
    overview: str | None = None
    rating: str | None = None
    platform_id: int | None = None

    if game:
        title = game.get("game_title") or None
        release_date = game.get("release_date") or None
        overview = game.get("overview") or None
        rating = game.get("rating") or None
        raw_platform = game.get("platform")
        if raw_platform is not None:
            try:
                platform_id = int(raw_platform)
            except (ValueError, TypeError):
                pass

    images_data = images_raw.get("data", {})
    base_url_obj = images_data.get("base_url", {})
    all_images = images_data.get("images", {}).get(str(game_id), [])

    front_boxart = next(
        (img for img in all_images if img.get("type") == "boxart" and img.get("side") == "front"),
        None,
    )

    cover_art_url: str | None = None
    cover_art_thumb_url: str | None = None

    if front_boxart:
        filename = front_boxart.get("filename", "")
        original = (base_url_obj.get("original") or "").rstrip("/")
        thumb = (base_url_obj.get("thumb") or "").rstrip("/")
        clean_filename = filename.lstrip("/")
        if original and clean_filename:
            cover_art_url = f"{original}/{clean_filename}"
        if thumb and clean_filename:
            cover_art_thumb_url = f"{thumb}/{clean_filename}"

    return {
        "game_id": game_id,
        "title": title,
        "release_date": release_date,
        "overview": overview,
        "rating": rating,
        "platform_id": platform_id,
        "cover_art_url": cover_art_url,
        "cover_art_thumb_url": cover_art_thumb_url,
    }


@router.post("/enrich")
def enrich_library_entity(
    request: Request,
    body: EnrichBody,
    db: Session = Depends(get_db),
    _: User = require_permission("is_owner"),
):
    _enforce_rate_limit("library-enrich", request, _ENRICH_RATE_LIMIT, _ENRICH_RATE_WINDOW_SECONDS)

    entity, entity_type = enrich_svc.enrich_entity(
        body.entity_type,
        body.entity_id,
        title=body.title,
        description=body.description,
        publisher=body.publisher,
        year=body.year,
        content_rating=body.content_rating,
        metadata_source=body.metadata_source,
        cover_art_url=body.cover_art_url,
        db=db,
    )
    if entity_type == "library_item":
        return item_to_read(entity, db)
    if entity_type == "library_set":
        return set_to_read(entity, db)
    return LibrarySetItemRead.model_validate(entity)
