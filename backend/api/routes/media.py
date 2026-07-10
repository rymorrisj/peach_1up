from fastapi import APIRouter

# The former POST /upload (OS-install-media) handler moved to
# POST /api/v1/environments/{slug}/install-media — see environments.py.
# This prefix is freed for the new Media domain (doc 03).
router = APIRouter(prefix="/api/v1/media", tags=["media"])
