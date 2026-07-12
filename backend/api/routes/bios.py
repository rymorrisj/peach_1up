from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from backend.core.dependencies import get_active_user, require_permission
from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.models.bios import BiosItem
from backend.models.pagination import Page
from backend.models.user import User
from backend.service.utils.bios_placement import PlacementError, place_bios_asset
from backend.service.utils.emulator_catalog import check_bios_presence, load_bios_requirements

router = APIRouter(prefix="/api/v1/bios", tags=["bios"])
logger = get_logger(__name__)


class BiosPlaceResult(BaseModel):
    slug: str
    is_present: bool
    copied: list[str]
    skipped: list[str]
    warnings: list[str]


@router.get("", response_model=Page[BiosItem])
def list_bios_requirements(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(get_active_user),
):
    result = []
    for entry in load_bios_requirements():
        bios_path = entry.get("bios_path", "")
        result.append({
            "slug": entry["slug"],
            "name": entry["name"],
            "platform": entry.get("platform", ""),
            "bios_path": bios_path,
            "guidance_text": entry.get("guidance_text", ""),
            "guidance_url": entry.get("guidance_url", ""),
            "is_present": check_bios_presence(
                bios_path,
                required_files=entry.get("required_files"),
                required_glob=entry.get("required_glob"),
                required_glob_excludes=entry.get("required_glob_excludes"),
            ) if bios_path else False,
            "required": entry.get("required", True),
        })
    total = len(result)
    return Page(items=result[offset:offset + limit], total=total, limit=limit, offset=offset)


@router.post("/{slug}/place", response_model=BiosPlaceResult)
async def place_bios(
    slug: str,
    source_path: Optional[str] = Form(None),
    files: list[UploadFile] = File(default=[]),
    _: User = require_permission("is_admin"),
):
    """Copy a BIOS/ROM asset the user already has into its required location.

    Accepts either a server-side source_path (file or folder) or one or more
    file uploads — never both. Never fetches or downloads anything; the
    caller must already have the bytes somewhere on disk.
    """
    entry = next((e for e in load_bios_requirements() if e["slug"] == slug), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown BIOS slug: '{slug}'.")

    bios_path_str = entry.get("bios_path", "")
    if not bios_path_str:
        raise HTTPException(status_code=400, detail=f"'{slug}' has no configured destination path.")

    base = get_base_path().resolve()
    dest_dir = (base / bios_path_str).resolve()
    if not dest_dir.is_relative_to(base):
        raise HTTPException(
            status_code=500,
            detail=f"bios_path for '{slug}' resolves outside the project root — corrupted config.",
        )

    uploads = [f for f in files if f.filename]
    if source_path and uploads:
        raise HTTPException(status_code=400, detail="Provide source_path or file uploads, not both.")
    if not source_path and not uploads:
        raise HTTPException(status_code=400, detail="Provide either source_path or at least one file upload.")

    try:
        result = await place_bios_asset(
            slug=slug, source_path=source_path, uploads=uploads, dest_dir=dest_dir,
        )
    except PlacementError as exc:
        logger.warning("bios place rejected for '%s': %s", slug, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info(
        "bios place '%s': %d copied, %d skipped, %d warning(s)",
        slug, len(result.copied), len(result.skipped), len(result.warnings),
    )

    return BiosPlaceResult(
        slug=slug,
        is_present=check_bios_presence(
            bios_path_str,
            required_files=entry.get("required_files"),
            required_glob=entry.get("required_glob"),
            required_glob_excludes=entry.get("required_glob_excludes"),
        ),
        copied=result.copied,
        skipped=result.skipped,
        warnings=result.warnings,
    )
