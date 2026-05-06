import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.core import install_registry
from backend.service.utils.emulator_catalog import get_all_statuses, get_emulator
from backend.service.utils.emulator_installer import download_emulator, remove_emulator

router = APIRouter(prefix="/api/v1/emulators", tags=["emulators"])
logger = logging.getLogger(__name__)


class DeleteRequest(BaseModel):
    confirmation_token: str


@router.get("")
def list_emulators():
    return get_all_statuses()


@router.post("/{slug}/install")
async def install_emulator(slug: str, background_tasks: BackgroundTasks):
    try:
        entry = get_emulator(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Emulator '{slug}' not found.")

    url = entry.get("linux_url", "")
    if not url or url.startswith("PLACEHOLDER"):
        raise HTTPException(
            status_code=501,
            detail=f"Download URL not yet configured for '{slug}' — update config/emulators.yaml",
        )

    current = install_registry.get_status(slug)
    if current["status"] == "downloading":
        raise HTTPException(status_code=409, detail=f"Install already in progress for '{slug}'.")

    install_registry.set_status(slug, "downloading")
    background_tasks.add_task(_run_install, slug)
    return {"status": "downloading", "slug": slug}


async def _run_install(slug: str) -> None:
    try:
        path = await download_emulator(slug)
        install_registry.set_status(slug, "complete", install_path=str(path))
    except NotImplementedError as exc:
        install_registry.set_status(slug, "error", error=str(exc))
        logger.error("Install %s failed (not implemented): %s", slug, exc)
    except Exception as exc:
        install_registry.set_status(slug, "error", error=str(exc))
        logger.error("Install %s failed: %s", slug, exc)


@router.get("/{slug}/install/status")
def get_install_status(slug: str):
    try:
        get_emulator(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Emulator '{slug}' not found.")
    return install_registry.get_status(slug)


@router.get("/{slug}/confirm-token")
def get_confirm_token(slug: str):
    try:
        get_emulator(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Emulator '{slug}' not found.")
    token = install_registry.generate_confirm_token(slug)
    return {"token": token}


@router.delete("/{slug}")
def delete_emulator(slug: str, body: DeleteRequest):
    try:
        get_emulator(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Emulator '{slug}' not found.")

    if not install_registry.consume_confirm_token(slug, body.confirmation_token):
        raise HTTPException(status_code=403, detail="Invalid or expired confirmation token.")

    try:
        remove_emulator(slug)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    install_registry.set_status(slug, "idle")
    return {"slug": slug, "status": "removed"}
