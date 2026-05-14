import asyncio
import logging
import subprocess
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.core import install_registry
from backend.service.utils.emulator_catalog import get_emulator, load_catalog
from backend.service.utils.emulator_installer import (
    clone_rom_pack,
    detect_binary,
    launch_installer,
    remove_emulator,
)
from backend.service.utils import settings as _settings

router = APIRouter(prefix="/api/v1/emulators", tags=["emulators"])
logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class DeleteRequest(BaseModel):
    confirmation_token: str


class ConfigureRequest(BaseModel):
    action: str


_CONFIGURE_ACTIONS: dict[str, list[str]] = {
    "virtualbox": ["set_expert_mode"],
}


@router.get("")
def list_emulators():
    import glob as _glob
    from backend.service.utils.emulator_installer import check_git

    result = []
    for entry in load_catalog():
        slug = entry["slug"]
        binary = detect_binary(slug)
        install_type = entry.get("install_type", "zip")

        installer_present = False
        if install_type == "installer":
            installer_glob = entry.get("windows_installer_glob", "")
            if installer_glob:
                slug_dir = _PROJECT_ROOT / "emulators" / slug
                installer_present = bool(_glob.glob(str(slug_dir / installer_glob)))

        item: dict = {
            "slug": slug,
            "name": entry.get("name", slug),
            "version": entry.get("version", ""),
            "description": entry.get("description", ""),
            "license": entry.get("license", ""),
            "copyright": entry.get("copyright", ""),
            "source_url": entry.get("source_url", ""),
            "install_type": install_type,
            "required": entry.get("required", False),
            "supported_formats": entry.get("supported_formats", []),
            "is_installed": binary is not None,
            "install_path": str(binary) if binary else None,
            "installer_present": installer_present,
            "git_available": check_git() if install_type == "rom_pack" else None,
            "guidance_text": entry.get("guidance_text"),
            "guidance_url": entry.get("guidance_url"),
        }
        if "install_note" in entry:
            item["install_note"] = entry["install_note"]
        if slug == "virtualbox":
            item["expert_mode_set"] = bool(_settings.get("virtualbox_expert_mode_set", False))
        result.append(item)
    return result


@router.post("/{slug}/install")
async def install_emulator(slug: str, background_tasks: BackgroundTasks):
    try:
        entry = get_emulator(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Emulator '{slug}' not found.")

    install_type = entry.get("install_type", "zip")

    if install_type == "zip":
        binary = detect_binary(slug)
        if binary is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Binary not found for '{slug}'. "
                    f"Extract the emulator archive into emulators/{slug}/."
                ),
            )
        install_registry.set_status(slug, "complete", install_path=str(binary))
        return {"status": "detected", "slug": slug, "install_path": str(binary)}

    if install_type == "installer":
        current = install_registry.get_status(slug)
        if current.get("status") == "installer_launched":
            raise HTTPException(
                status_code=409,
                detail=f"Installer already launched for '{slug}'.",
            )
        try:
            info = launch_installer(slug)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        install_registry.set_status(slug, "installer_launched")
        return {"status": "installer_launched", "slug": slug, **info}

    if install_type == "rom_pack":
        current = install_registry.get_status(slug)
        if current.get("status") == "cloning":
            raise HTTPException(
                status_code=409,
                detail=f"ROM pack clone already in progress for '{slug}'.",
            )
        windows_binary = entry.get("windows_binary", "library/roms/86box")
        target = (_PROJECT_ROOT / windows_binary).resolve()
        install_registry.set_status(slug, "cloning")
        background_tasks.add_task(_run_clone, slug, target)
        return {"status": "cloning", "slug": slug}

    raise HTTPException(
        status_code=400,
        detail=f"Unknown install_type '{install_type}' for '{slug}'.",
    )


async def _run_clone(slug: str, target: Path) -> None:
    try:
        await asyncio.to_thread(clone_rom_pack, target)
        install_registry.set_status(slug, "complete", install_path=str(target))
    except FileExistsError as exc:
        install_registry.set_status(slug, "error", error=str(exc))
        logger.error("ROM pack clone %s blocked: %s", slug, exc)
    except Exception as exc:
        install_registry.set_status(slug, "error", error=str(exc))
        logger.error("ROM pack clone %s failed: %s", slug, exc)


@router.get("/{slug}/status")
def get_emulator_status(slug: str):
    try:
        entry = get_emulator(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Emulator '{slug}' not found.")

    binary = detect_binary(slug)
    installer_glob = entry.get("windows_installer_glob", "")
    installer_present = False
    if installer_glob:
        import glob as _glob
        slug_dir = _PROJECT_ROOT / "emulators" / slug
        installer_present = bool(_glob.glob(str(slug_dir / installer_glob)))

    return {
        "slug": slug,
        "install_type": entry.get("install_type", "zip"),
        "binary_detected": binary is not None,
        "binary_path": str(binary) if binary else None,
        "installer_present": installer_present,
        **install_registry.get_status(slug),
    }


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


@router.post("/{slug}/configure")
def configure_emulator(slug: str, body: ConfigureRequest):
    allowed_actions = _CONFIGURE_ACTIONS.get(slug)
    if allowed_actions is None:
        raise HTTPException(status_code=404, detail=f"No configurable actions for '{slug}'.")
    if body.action not in allowed_actions:
        raise HTTPException(status_code=400, detail=f"Unknown action '{body.action}' for '{slug}'.")

    if slug == "virtualbox" and body.action == "set_expert_mode":
        binary = detect_binary("virtualbox")
        if binary is None:
            raise HTTPException(
                status_code=404,
                detail="VBoxManage not found. Install VirtualBox first.",
            )
        try:
            result = subprocess.run(
                [str(binary), "setextradata", "global", "GUI/ExperienceMode", "Expert"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=500, detail="VBoxManage timed out.")
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to run VBoxManage: {exc}")

        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            raise HTTPException(status_code=500, detail=f"VBoxManage failed: {detail}")

        _settings.set_flag("virtualbox_expert_mode_set", True)
        return {"slug": slug, "action": body.action, "status": "ok"}
