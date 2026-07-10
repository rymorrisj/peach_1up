from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core import rate_limit
from backend.core.database import get_db
from backend.core.dependencies import require_permission
from backend.models.software import SoftwareItemRead, collection_to_read
from backend.models.user import User
from backend.service.library import enrich as enrich_svc

router = APIRouter(prefix="/api/v1/software", tags=["library"])

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
    entity_type: Literal["library_collection", "library_item"]
    entity_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    developer: Optional[str] = None
    genre: Optional[list[str]] = None
    year: Optional[int] = None
    content_rating: Optional[str] = None
    metadata_source: Optional[str] = None
    cover_art_url: Optional[str] = None
    confirm_rating_change: bool = False


@router.get("/metadata-search")
def search_metadata(
    request: Request,
    name: str = Query(...),
    _: User = require_permission("is_owner"),
):
    _enforce_rate_limit("library-metadata", request, _METADATA_RATE_LIMIT, _METADATA_RATE_WINDOW_SECONDS)

    import httpx
    from backend.service.metadata_providers import get_active_provider

    try:
        provider = get_active_provider()
        results = provider.search_games(name)
    except NotImplementedError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Metadata provider API error: {exc.response.status_code}",
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Metadata provider API request timed out.")

    return {
        "results": [
            {"game_id": r.game_id, "title": r.title, "release_date": r.release_date}
            for r in results
        ]
    }


@router.get("/metadata-details")
def get_metadata_details(
    request: Request,
    game_id: int = Query(...),
    db: Session = Depends(get_db),
    _: User = require_permission("is_owner"),
):
    _enforce_rate_limit("library-metadata", request, _METADATA_RATE_LIMIT, _METADATA_RATE_WINDOW_SECONDS)

    import httpx
    from backend.service.metadata_providers import get_active_provider

    try:
        provider = get_active_provider()
        details = provider.get_game_details(game_id, db)
    except NotImplementedError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Metadata provider API error: {exc.response.status_code}",
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Metadata provider API request timed out.")

    return {
        "game_id": details.game_id,
        "title": details.title,
        "release_date": details.release_date,
        "overview": details.overview,
        "rating": details.rating,
        "platform_id": details.platform_id,
        "cover_art_url": details.cover_art_url,
        "cover_art_thumb_url": details.cover_art_thumb_url,
        "genres": details.genres,
        "developer": details.developer,
        "publisher": details.publisher,
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
        developer=body.developer,
        genre=body.genre,
        year=body.year,
        content_rating=body.content_rating,
        metadata_source=body.metadata_source,
        cover_art_url=body.cover_art_url,
        confirm_rating_change=body.confirm_rating_change,
        db=db,
    )
    if entity_type == "library_collection":
        return collection_to_read(entity, db)
    return SoftwareItemRead.model_validate(entity)
