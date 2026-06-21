from fastapi import APIRouter, Depends

from backend.core.dependencies import get_active_user
from backend.core.logger import get_logger
from backend.models.bios import BiosRequirement
from backend.models.user import User
from backend.service.utils.emulator_catalog import check_bios_presence, load_bios_requirements

router = APIRouter(prefix="/api/v1/bios", tags=["bios"])
logger = get_logger(__name__)


@router.get("", response_model=list[BiosRequirement])
def list_bios_requirements(_: User = Depends(get_active_user)):
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
            "is_present": check_bios_presence(bios_path) if bios_path else False,
        })
    return result
