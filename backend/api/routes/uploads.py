"""Chunked upload endpoints, one router per upload domain.

Flow: init (create session + job) -> PUT chunks -> complete (reassemble +
ingest). init_upload creates the job.jobs entry immediately, before any bytes
have been transferred, so the nav bell can track an upload from the very
start; complete_upload always finalizes as a BackgroundTask and returns 202,
there is no separate inline-finalize path.

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

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.core import jobs, rate_limit
from backend.core.dependencies import require_permission
from backend.core.logger import get_logger
from backend.models.user import UserItem
from backend.service.uploads import core as cu
from backend.service.uploads import registry
from backend.service.utils.upload_utils import DEFAULT_CHUNK_MAX_BYTES

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

        # Created only after init_session succeeds, a malformed-manifest 422
        # never leaves an orphaned "processing" job with nothing left to ever
        # resolve it. Attached to the session (not returned for the client to
        # echo back at /complete) so /complete resolves it itself instead of
        # trusting a client-supplied job_id to identify which job to update.
        job_id = jobs.create("upload", message=f"Uploading \"{title or 'upload'}\"…")
        cu.set_job_id(upload_id, job_id)

        return {
            "upload_id": upload_id,
            "chunk_max_bytes": chunk_max_bytes,
            "job_id": job_id,
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
        _: UserItem = require_permission(permission_flag),
    ):
        session = cu.get_session(upload_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Unknown or expired upload session.")
        if not cu.all_received(upload_id):
            raise HTTPException(status_code=409, detail="Upload incomplete, some chunks are missing.")

        domain = registry.get_domain(domain_name)
        media_root: Path = domain.root_resolver()
        # job_id was created and attached to the session back at /init, not
        # here, so the nav bell tracks the upload from the start of byte
        # transfer, not just its server-side finalize tail. Every upload
        # finalizes as a BackgroundTask now, there is no inline/small-upload
        # branch, exceptions (including domain-specific ones like a duplicate
        # or slug collision) are reported into the job via jobs.fail() inside
        # finalize_background itself, not translated into an HTTP response
        # here, there is nothing left running synchronously in this request
        # to raise one from.
        job_id = session["job_id"]
        background_tasks.add_task(
            domain.finalize_background, upload_id, str(media_root), job_id
        )
        return JSONResponse(status_code=202, content={"job_id": job_id, "status": "processing"})

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
