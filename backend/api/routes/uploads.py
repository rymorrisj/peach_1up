"""Chunked upload endpoints.

Flow: init (create session) → PUT chunks → complete (reassemble + ingest). Small
uploads finalize inline and return 201; uploads over the background threshold
return 202 with a job_id and finalize in a BackgroundTask surfaced in the nav
bell. Cleanup of the staging area is owned by service.library.chunked_uploads.
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
from backend.models.user import User
from backend.service.library import chunked_uploads as cu
from backend.service.library import upload_finalize
from backend.service.library.items import _ItemAlreadyExists, _SlugCollision
from backend.service.utils.upload_utils import (
    DEFAULT_BACKGROUND_THRESHOLD_BYTES,
    DEFAULT_CHUNK_MAX_BYTES,
)

router = APIRouter(prefix="/api/v1/software/uploads", tags=["uploads"])
logger = get_logger(__name__)

# Session creation shares the library-upload bucket; the per-chunk PUTs are NOT
# rate-limited (a legitimate large upload is hundreds of chunk requests).
_INIT_RATE_LIMIT = 10
_INIT_RATE_WINDOW_SECONDS = 60.0


class InitFile(BaseModel):
    name: str
    size: int
    chunks: int


class InitBody(BaseModel):
    kind: Literal["file", "folder", "set"]
    title: Optional[str] = None
    files: list[InitFile]


def _software_root() -> Path:
    from backend.core.settings import get_settings
    return Path(get_settings().get_env_var("SOFTWARE_PATH")).resolve()


def _setting_int(key: str, default: int) -> int:
    from backend.core.settings import get_settings
    try:
        return int(get_settings().get(key, default) or default)
    except (TypeError, ValueError):
        return default


@router.post("/init")
def init_upload(
    body: InitBody,
    request: Request,
    _: User = require_permission("can_manage_software"),
):
    client_ip = request.client.host if request.client else "unknown"
    rate_limit.enforce("library-upload", client_ip, _INIT_RATE_LIMIT, _INIT_RATE_WINDOW_SECONDS)

    title = (body.title or "").strip()
    if body.kind in ("folder", "set") and not title:
        raise HTTPException(status_code=422, detail="A title is required for folder and set uploads.")
    try:
        upload_id = cu.init_session(
            _software_root(),
            body.kind,
            title,
            [{"name": f.name, "size": f.size, "chunks": f.chunks} for f in body.files],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "upload_id": upload_id,
        "chunk_max_bytes": _setting_int("UPLOAD_CHUNK_MAX_BYTES", DEFAULT_CHUNK_MAX_BYTES),
    }


@router.put("/{upload_id}/chunks/{file_index}/{chunk_index}")
async def put_chunk(
    upload_id: str,
    file_index: int,
    chunk_index: int,
    chunk: UploadFile,
    _: User = require_permission("can_manage_software"),
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
    _: User = require_permission("can_manage_software"),
):
    session = cu.get_session(upload_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown or expired upload session.")
    if not cu.all_received(upload_id):
        raise HTTPException(status_code=409, detail="Upload incomplete — some chunks are missing.")

    media_root = _software_root()
    threshold = _setting_int("UPLOAD_BACKGROUND_THRESHOLD_BYTES", DEFAULT_BACKGROUND_THRESHOLD_BYTES)

    if cu.total_size(upload_id) > threshold:
        job_id = jobs.create("upload", message=f"Finalizing \"{session['title'] or 'upload'}\"…")
        background_tasks.add_task(
            upload_finalize.finalize_background, upload_id, str(media_root), job_id
        )
        return JSONResponse(status_code=202, content={"job_id": job_id, "status": "processing"})

    try:
        result = upload_finalize.finalize_inline(upload_id, media_root, db)
    except _ItemAlreadyExists:
        raise HTTPException(status_code=409, detail="This upload's content is already in the library.")
    except _SlugCollision as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse(status_code=201, content=result)


@router.delete("/{upload_id}", status_code=204)
def abort_upload(
    upload_id: str,
    _: User = require_permission("can_manage_software"),
):
    cu.abort(upload_id)
