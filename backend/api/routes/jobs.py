"""Background-job status endpoints for the nav-bell notification centre.

Read-only view over core.jobs (upload finalization + large scans). Any
authenticated user may poll — jobs carry no sensitive payload, only progress and
a title/summary.
"""
from fastapi import APIRouter, Depends, HTTPException

from backend.core import jobs
from backend.core.dependencies import get_active_user
from backend.models.user import UserItem

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("")
def list_jobs(_: UserItem = Depends(get_active_user)):
    return jobs.list_recent()


@router.get("/{job_id}")
def get_job(job_id: str, _: UserItem = Depends(get_active_user)):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job
