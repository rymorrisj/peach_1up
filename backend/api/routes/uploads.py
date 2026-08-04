"""Chunked upload endpoints, one router per upload domain.

Flow: init (create session) -> PUT chunks -> complete (reassemble + ingest).
Small uploads finalize inline and return 201; uploads over the background
threshold return 202 with a job_id and finalize in a BackgroundTask surfaced
in the nav bell.

Route-per-domain replaces the earlier single-endpoint-plus-target_type shape:
each domain (software_games, software_media, software_apps) gets its own URL
prefix and its own permission Depends(), decided statically below at router-
build time. The route *bodies* are identical across domains (chunk transport
never varies), so one factory builds all three instead of copy-pasting the
handlers, but each call site still bakes in a concrete permission dependency,
not a runtime-parametrized one. What DOES vary per domain (root directory,
allowed upload kinds, finalize logic) is resolved per-request through the
registry in backend.service.uploads.registry, populated by each domain
module's explicit register() call from backend.core.lifespan at startup, so
by the time any request reaches these routes, lifespan has already run.
"""
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core import jobs, rate_limit
from backend.core.database import get_db
from backend.core.dependencies import require_permission
from backend.core.logger import get_logger
from backend.models.user import UserItem
from backend.service.uploads import core as cu
from backend.service.uploads import registry
from backend.service.utils.upload_utils import (
    DEFAULT_BACKGROUND_THRESHOLD_BYTES,
    DEFAULT_CHUNK_MAX_BYTES,
)

logger = get_logger(__name__)

# Session creation shares one bucket across every domain; the per-chunk PUTs
# are NOT rate-limited (a legitimate large upload is hundreds of chunk requests).
_INIT_RATE_LIMIT = 10
_INIT_RATE_WINDOW_SECONDS = 60.0


class InitFile(BaseModel):
    name: str
    size: int
    chunks: int
    # Only ever sent for a folder upload the frontend already detected as
    # PS3_DISC.SFB-marked (see chunkedUpload.ts); absent for every other
    # upload, which keeps the existing flat-basename behavior unchanged.
    relative_path: Optional[str] = None


class InitBody(BaseModel):
    kind: Literal["file", "folder", "set"]
    title: Optional[str] = None
    files: list[InitFile]


def _setting_int(key: str, default: int) -> int:
    from backend.core.settings import get_settings
    try:
        return int(get_settings().get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _build_domain_router(domain_name: str, permission_flag: str) -> APIRouter:
    router = APIRouter(
        prefix=f"/api/v1/uploads/{domain_name.replace('_', '-')}",
        tags=["uploads"],
    )

    @router.post("/init")
    def init_upload(
        body: InitBody,
        request: Request,
        _: UserItem = require_permission(permission_flag),
    ):
        domain = registry.get_domain(domain_name)
        if body.kind not in domain.allowed_kinds:
            raise HTTPException(
                status_code=422,
                detail=f"Upload kind '{body.kind}' is not supported for this domain.",
            )
        client_ip = request.client.host if request.client else "unknown"
        rate_limit.enforce("library-upload", client_ip, _INIT_RATE_LIMIT, _INIT_RATE_WINDOW_SECONDS)

        title = (body.title or "").strip()
        if body.kind in ("folder", "set") and not title:
            raise HTTPException(status_code=422, detail="A title is required for folder and set uploads.")
        chunk_max_bytes = _setting_int("UPLOAD_CHUNK_MAX_BYTES", DEFAULT_CHUNK_MAX_BYTES)
        try:
            upload_id = cu.init_session(
                body.kind,
                title,
                [
                    {"name": f.name, "size": f.size, "chunks": f.chunks, "relative_path": f.relative_path}
                    for f in body.files
                ],
                chunk_max_bytes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return {
            "upload_id": upload_id,
            "chunk_max_bytes": chunk_max_bytes,
        }

    @router.put("/{upload_id}/chunks/{file_index}/{chunk_index}")
    async def put_chunk(
        upload_id: str,
        file_index: int,
        chunk_index: int,
        chunk: UploadFile,
        _: UserItem = require_permission(permission_flag),
    ):
        chunk_max = _setting_int("UPLOAD_CHUNK_MAX_BYTES", DEFAULT_CHUNK_MAX_BYTES)
        try:
            return await cu.store_chunk(upload_id, file_index, chunk_index, chunk, chunk_max)
        except KeyError:
            raise HTTPException(status_code=404, detail="Unknown or expired upload session.")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/{upload_id}/complete")
    def complete_upload(
        upload_id: str,
        background_tasks: BackgroundTasks = BackgroundTasks(),
        db: Session = Depends(get_db),
        _: UserItem = require_permission(permission_flag),
    ):
        session = cu.get_session(upload_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Unknown or expired upload session.")
        if not cu.all_received(upload_id):
            raise HTTPException(status_code=409, detail="Upload incomplete, some chunks are missing.")

        domain = registry.get_domain(domain_name)
        media_root: Path = domain.root_resolver()
        threshold = _setting_int("UPLOAD_BACKGROUND_THRESHOLD_BYTES", DEFAULT_BACKGROUND_THRESHOLD_BYTES)

        if cu.total_size(upload_id) > threshold:
            job_id = jobs.create("upload", message=f"Finalizing \"{session['title'] or 'upload'}\"…")
            background_tasks.add_task(
                domain.finalize_background, upload_id, str(media_root), job_id
            )
            return JSONResponse(status_code=202, content={"job_id": job_id, "status": "processing"})

        try:
            result = domain.finalize_inline(upload_id, media_root, db)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001, surfaced as a clean 409 rather than a bare 500
            # _ItemAlreadyExists/_SlugCollision (software_games) are the two
            # expected domain-specific exceptions here; every other domain
            # either can't raise them or has no equivalent, so they are
            # imported lazily to avoid a hard dependency from this generic
            # route module onto software_games internals.
            from backend.service.games.items import _ItemAlreadyExists, _SlugCollision

            if isinstance(exc, _ItemAlreadyExists):
                raise HTTPException(status_code=409, detail="This upload's content is already in the library.")
            if isinstance(exc, _SlugCollision):
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            if isinstance(exc, ValueError):
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            raise
        return JSONResponse(status_code=201, content=result)

    @router.delete("/{upload_id}", status_code=204)
    def abort_upload(
        upload_id: str,
        _: UserItem = require_permission(permission_flag),
    ):
        cu.abort(upload_id)

    return router


software_games_router = _build_domain_router("software_games", "can_manage_game")
software_media_router = _build_domain_router("software_media", "can_manage_media")
software_apps_router = _build_domain_router("software_apps", "can_manage_app")
