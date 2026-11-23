import json
from typing import Callable, Literal, Optional, TypeVar

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core import jobs, rate_limit
from backend.core.database import get_db
from backend.core.dependencies import get_filtered_game_item_bundle, normalize_content_rating, require_permission
from backend.models.game import game_item_bundle_to_read
from backend.models.user import UserItem
from backend.service.games import accept_all_job, media_link
from backend.service.games import enrich as enrich_svc
from backend.service.metadata_providers import AssetType, MetadataProvider
from backend.service.metadata_providers.links import clean_provider_links, trailer_links

_T = TypeVar("_T")

router = APIRouter(prefix="/api/v1/game-items", tags=["games"])

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


METADATA_FETCH_DISABLED_DETAIL = "Metadata fetching is disabled in Settings"


def _require_metadata_fetch_enabled() -> None:
    """Refuse with 403 unless the owner has enabled metadata fetching.

    Called first in each route body, so the require_permission dependency has
    already run (a non-owner still gets the permission 403, not this one) and
    a refused call never consumes rate-limit budget or reaches a provider.
    403 matches the other setting-gated refusal in this app, the
    ALLOW_NETWORK_ACCESS check in backend/api/middleware/security.py.
    """
    from backend.service.metadata_providers import is_metadata_fetch_enabled

    if not is_metadata_fetch_enabled():
        raise HTTPException(status_code=403, detail=METADATA_FETCH_DISABLED_DETAIL)


class EnrichBody(BaseModel):
    """Only the fields present in the request are applied (exclude_unset);
    to apply the rest without a rating that needs confirmation, leave
    content_rating out."""

    # Only bundles carry metadata. A leaf (game_item) id must be rejected,
    # never read as a bundle id.
    entity_type: Literal["game_item_bundle"] = "game_item_bundle"
    entity_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    developer: Optional[str] = None
    genre: Optional[list[str]] = None
    year: Optional[int] = None
    content_rating: Optional[str] = None
    metadata_source: Optional[str] = None
    external_links: Optional[list[dict]] = None
    external_game_id: Optional[int] = None
    confirm_rating_change: bool = False


class MetadataAssetBody(BaseModel):
    url: str
    # Allowlisted, not free text: the type becomes part of the on-disk
    # filename stem in media_link.py (META-3).
    type: AssetType
    thumb_url: Optional[str] = None


class AcceptMetadataAssetsBody(BaseModel):
    assets: list[MetadataAssetBody]
    # Required once the linked media already holds fetched images (409
    # otherwise). replace swaps them for this set, keep adds new URLs only.
    previous_assets: Optional[Literal["replace", "keep"]] = None
    # Optional game cover, one of the submitted assets' urls. Absent leaves
    # the game's cover alone.
    cover_asset_url: Optional[str] = None


def _call_provider(call: Callable[[MetadataProvider], _T]) -> _T:
    """Run *call* against the active provider, mapping its failures to
    specific responses that name the provider and the cause but never carry
    a key, a URL or raw exception text. Missing credentials keep their
    own clear 503."""
    import httpx2
    from backend.service.metadata_providers import active_provider_label, get_active_provider

    label = active_provider_label()
    try:
        return call(get_active_provider())
    except httpx2.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"{label} returned {exc.response.status_code}.")
    except httpx2.TimeoutException:
        raise HTTPException(status_code=504, detail=f"{label} did not respond in time.")
    except httpx2.RequestError:
        raise HTTPException(status_code=502, detail=f"Could not reach {label}.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail=f"{label} returned an unreadable response.")
    except (NotImplementedError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/metadata-search")
def search_metadata(
    request: Request,
    name: str = Query(...),
    _: UserItem = require_permission("is_owner"),
):
    _require_metadata_fetch_enabled()
    _enforce_rate_limit("library-metadata", request, _METADATA_RATE_LIMIT, _METADATA_RATE_WINDOW_SECONDS)

    results = _call_provider(lambda provider: provider.search_games(name))

    return {
        "results": [
            {"game_id": r.game_id, "title": r.title, "release_date": r.release_date, "platform": r.platform}
            for r in results
        ]
    }


@router.get("/metadata-details")
def get_metadata_details(
    request: Request,
    game_id: int = Query(...),
    db: Session = Depends(get_db),
    _: UserItem = require_permission("is_owner"),
):
    _require_metadata_fetch_enabled()
    _enforce_rate_limit("library-metadata", request, _METADATA_RATE_LIMIT, _METADATA_RATE_WINDOW_SECONDS)

    details = _call_provider(lambda provider: provider.get_game_details(game_id, db))

    return {
        "game_id": details.game_id,
        "title": details.title,
        "release_date": details.release_date,
        "overview": details.overview,
        "rating": details.rating,
        "normalized_rating": normalize_content_rating(details.rating),
        "provider_platform_id": details.provider_platform_id,
        "cover_art_url": details.cover_art_url,
        "cover_art_thumb_url": details.cover_art_thumb_url,
        "genres": details.genres,
        "unresolved_genre_ids": details.unresolved_genre_ids,
        "developer": details.developer,
        "publisher": details.publisher,
        "video_urls": details.video_urls,
        "external_links": clean_provider_links([*details.external_links, *trailer_links(details.video_urls)]),
        "assets": [{"url": a.url, "type": a.type, "thumb_url": a.thumb_url} for a in details.assets],
    }


@router.post("/enrich")
def enrich_library_entity(
    request: Request,
    body: EnrichBody,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("is_owner"),
):
    _require_metadata_fetch_enabled()
    _enforce_rate_limit("library-enrich", request, _ENRICH_RATE_LIMIT, _ENRICH_RATE_WINDOW_SECONDS)

    bundle = get_filtered_game_item_bundle(body.entity_id, active_user, db)
    fields = body.model_dump(exclude_unset=True, exclude={"entity_type", "entity_id", "confirm_rating_change"})
    entity = enrich_svc.enrich_game_bundle(
        bundle.id,
        fields,
        confirm_rating_change=body.confirm_rating_change,
        db=db,
    )
    return game_item_bundle_to_read(entity, db, viewer=active_user)


@router.post("/{id}/accept-metadata-assets", status_code=202)
def accept_metadata_assets(
    id: int,
    request: Request,
    body: AcceptMetadataAssetsBody,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    active_user: UserItem = require_permission("is_owner"),
):
    """Accept All step of the Fetch Metadata flow: starts a background job
    that downloads every asset the frontend already fetched via
    /metadata-details (no second round trip to the provider here) and
    attaches them to a linked Media item bundle for the GameItemBundle named
    by *id*. Same permission level as the rest of this flow and the same
    rate-limit bucket as /enrich, since both are write operations against
    this game.

    Every pre-check (setting, visibility, asset cap, Replace/Keep decision,
    running apply) answers here; once they pass the response is 202 with a
    job id to poll at /metadata-jobs/{job_id}.
    """
    _require_metadata_fetch_enabled()
    _enforce_rate_limit("library-enrich", request, _ENRICH_RATE_LIMIT, _ENRICH_RATE_WINDOW_SECONDS)

    from backend.service.metadata_providers import MetadataAsset

    game = get_filtered_game_item_bundle(id, active_user, db)
    assets = [MetadataAsset(url=a.url, type=a.type, thumb_url=a.thumb_url) for a in body.assets]
    plan = media_link.prepare_apply(
        game.id,
        assets,
        db,
        previous_assets=body.previous_assets,
        cover_asset_url=body.cover_asset_url,
    )
    return {"job_id": accept_all_job.start(plan, background_tasks), "state": "queued"}


@router.get("/metadata-jobs/{job_id}")
def get_metadata_job(job_id: str, _: UserItem = require_permission("is_owner")):
    """Status of an Accept All job: state (queued, running, done, failed,
    cancelled), done/total asset counts, the current asset label and, on
    failure, {code, message}."""
    job = accept_all_job.status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.post("/metadata-jobs/{job_id}/cancel")
def cancel_metadata_job(job_id: str, _: UserItem = require_permission("is_owner")):
    """Cooperative cancel through core.jobs, same as the scan cancel: the job
    stops before its next download or before its commit, removes everything
    it created and reaches 'cancelled'. Poll the status route to see it."""
    if accept_all_job.status(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if jobs.request_cancel(job_id) is None:
        raise HTTPException(status_code=409, detail="This job is not running.")
    return accept_all_job.status(job_id)
