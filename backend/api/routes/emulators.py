import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.core import install_registry
from backend.core.database import get_db
from backend.core.dependencies import require_permission
from backend.core.logger import get_logger
from backend.models.user import User
from backend.service.utils.emulator_catalog import (
    get_emulator,
    get_install_path,
    installer_present as _installer_present,
    load_catalog,
)
from backend.service.utils.emulator_installer import (
    clone_rom_pack,
    detect_binary,
    launch_installer,
    remove_emulator,
)
from backend.service.utils import settings as _settings

router = APIRouter(prefix="/api/v1/emulators", tags=["emulators"])
logger = get_logger(__name__)


class CatalogEntryResponse(BaseModel):
    slug: str
    name: str
    version: str
    description: str
    license: str
    install_type: str
    required: bool
    is_installed: bool
    install_path: Optional[str] = None
    supported_formats: list[str] = []
    install_note: Optional[str] = None
    source_url: Optional[str] = None
    copyright: Optional[str] = None
    guidance_text: Optional[str] = None
    guidance_url: Optional[str] = None
    install_scope: Optional[str] = None
    installer_present: Optional[bool] = None
    git_available: Optional[bool] = None
    expert_mode_set: Optional[bool] = None
    container_enabled: bool = False
    container_hardcap_disabled: bool = False
    skip_cpu_limit: bool = False
    skip_memory_limit: bool = False
    known_limitations: list[dict] = []
    rom_pack_slug: Optional[str] = None


class SandboxPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    container_enabled: Optional[bool] = None
    skip_cpu_limit: Optional[bool] = None
    skip_memory_limit: Optional[bool] = None


class DeleteRequest(BaseModel):
    confirmation_token: str


class SandboxResetRequest(BaseModel):
    confirmation_token: str


class EmulatorStatusData(BaseModel):
    slug: str
    install_type: str
    binary_detected: bool
    binary_path: Optional[str] = None
    installer_present: Optional[bool] = None
    status: install_registry.InstallStatus
    error: Optional[str] = None
    install_path: Optional[str] = None


class XemuAssetPathsResponse(BaseModel):
    bootrom: str
    flashrom: str
    hdd_image: str
    eeprom_image: str = ""


class XemuAssetPathsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bootrom: Optional[str] = None
    flashrom: Optional[str] = None
    hdd_image: Optional[str] = None
    eeprom_image: Optional[str] = None


def _xemu_toml_path() -> Path:
    from backend.core.settings import get_base_path
    return get_base_path() / "emulators" / "xemu" / "xemu.toml"


def _write_xemu_toml(toml_path: Path, sections: dict) -> None:
    lines: list[str] = []
    for section, keys in sections.items():
        lines.append(f"[{section}]")
        for k, v in keys.items():
            if isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k} = {v}")
            else:
                safe = str(v).replace("\\", "/")
                lines.append(f'{k} = "{safe}"')
        lines.append("")
    tmp = toml_path.parent / (toml_path.name + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(toml_path)


@router.get("", response_model=list[CatalogEntryResponse])
def list_emulators():
    from backend.service.utils.emulator_installer import check_git

    all_entries = load_catalog()
    rom_pack_slugs = {e["slug"] for e in all_entries if e.get("install_type") == "rom_pack"}
    result = []
    for entry in all_entries:
        slug = entry["slug"]
        binary = get_install_path(slug)
        install_type = entry.get("install_type", "zip")
        installer_present = _installer_present(slug)

        item: dict = {
            "slug": slug,
            "name": entry.get("name", slug),
            "version": entry.get("version", ""),
            "description": entry.get("description", ""),
            "license": entry.get("license", ""),
            "copyright": entry.get("copyright", ""),
            "source_url": entry.get("source_url", ""),
            "install_type": install_type,
            "install_scope": entry.get("install_scope", "portable"),
            "required": entry.get("required", False),
            "supported_formats": entry.get("supported_formats", []),
            "is_installed": binary is not None,
            "install_path": str(binary) if binary else None,
            "installer_present": installer_present,
            "git_available": check_git() if install_type == "rom_pack" else None,
            "guidance_text": entry.get("guidance_text"),
            "guidance_url": entry.get("guidance_url"),
        }
        for _sf in ("container_enabled", "skip_cpu_limit", "skip_memory_limit"):
            _toml_val = bool(entry.get(_sf, False))
            _override = _settings.get(f"sandbox_{slug}_{_sf}", None)
            item[_sf] = bool(_override) if _override is not None else _toml_val
        item["container_hardcap_disabled"] = bool(entry.get("container_hardcap_disabled", False))
        item["rom_pack_slug"] = next(
            (dep["name"] for dep in entry.get("dependencies", []) if dep.get("name") in rom_pack_slugs),
            None,
        )
        if "install_note" in entry:
            item["install_note"] = entry["install_note"]
        item["known_limitations"] = entry.get("known_limitations", [])
        result.append(item)
    return result


@router.get("/sandbox-state/confirm-token")
def get_sandbox_reset_token(_: User = require_permission("is_admin")):
    token = install_registry.generate_confirm_token("sandbox-state")
    return {"token": token}


@router.delete("/sandbox-state")
def reset_sandbox_state(
    body: SandboxResetRequest,
    db: Session = Depends(get_db),
    _: User = require_permission("is_admin"),
):
    if not install_registry.consume_confirm_token("sandbox-state", body.confirmation_token):
        raise HTTPException(status_code=403, detail="Invalid or expired confirmation token.")

    from backend.models.profile import Profile
    from backend.service.utils.platform.windows.app_container import reset_container as _reset_container

    catalog = load_catalog()
    reset_count = 0
    errors: list[str] = []
    for entry in catalog:
        if entry.get("container_enabled", False):
            slug = entry["slug"]
            # Monikers are now scoped per profile.user_id — sweep every user
            # scope on record for this emulator, plus the "shared" scope used
            # by profiles with no user_id, to match the old per-slug sweep.
            user_ids: set[int | None] = {
                row[0] for row in db.query(Profile.user_id).filter(Profile.emulator_slug == slug).distinct()
            }
            user_ids.add(None)
            for user_id in user_ids:
                scope_label = str(user_id) if user_id is not None else "shared"
                try:
                    _reset_container(slug, user_id)
                    reset_count += 1
                except Exception as exc:
                    logger.warning(
                        "Failed to reset AppContainer for %s (user=%s): %s", slug, scope_label, exc
                    )
                    errors.append(f"{slug}:{scope_label}")

    return {"reset": reset_count, "errors": errors}


@router.get("/xemu/asset-paths", response_model=XemuAssetPathsResponse)
def get_xemu_asset_paths(_: User = require_permission("is_admin")):
    import tomllib

    xemu_toml = _xemu_toml_path()
    if not xemu_toml.exists():
        raise HTTPException(
            status_code=404,
            detail="xemu config not found at emulators/xemu/xemu.toml. Use PATCH to create it with the required asset paths.",
        )
    with xemu_toml.open("rb") as fh:
        config = tomllib.load(fh)
    files = config.get("sys", {}).get("files", {})
    return XemuAssetPathsResponse(
        bootrom=files.get("bootrom", ""),
        flashrom=files.get("flashrom", ""),
        hdd_image=files.get("hdd_image", ""),
        eeprom_image=files.get("eeprom_image", ""),
    )


@router.patch("/xemu/asset-paths", response_model=XemuAssetPathsResponse)
def patch_xemu_asset_paths(body: XemuAssetPathsPatch, _: User = require_permission("is_admin")):
    import tomllib
    from backend.service.utils.path_utils import normalise_path

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="At least one field must be provided.")

    validated: dict[str, str] = {}
    for key, raw in updates.items():
        try:
            validated[key] = str(normalise_path(raw)).replace("\\", "/")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid path for '{key}': {exc}") from exc

    xemu_toml = _xemu_toml_path()
    if xemu_toml.exists():
        with xemu_toml.open("rb") as fh:
            config = tomllib.load(fh)
    else:
        xemu_toml.parent.mkdir(parents=True, exist_ok=True)
        config = {}

    files = dict(config.get("sys", {}).get("files", {}))
    for key in ("bootrom", "flashrom", "hdd_image", "eeprom_image"):
        if key in validated:
            files[key] = validated[key]

    sections: dict = {}
    for section_name, section_data in config.items():
        if section_name != "sys":
            sections[section_name] = dict(section_data)
    sections["sys.files"] = files

    _write_xemu_toml(xemu_toml, sections)

    return XemuAssetPathsResponse(
        bootrom=files.get("bootrom", ""),
        flashrom=files.get("flashrom", ""),
        hdd_image=files.get("hdd_image", ""),
        eeprom_image=files.get("eeprom_image", ""),
    )


@router.post("/{slug}/install")
async def install_emulator(slug: str, background_tasks: BackgroundTasks, _: User = require_permission("is_admin")):
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
        install_registry.set_status(slug, "cloning")
        background_tasks.add_task(_run_clone, slug)
        return {"status": "cloning", "slug": slug}

    raise HTTPException(
        status_code=400,
        detail=f"Unknown install_type '{install_type}' for '{slug}'.",
    )


async def _run_clone(slug: str) -> None:
    try:
        target = await asyncio.to_thread(clone_rom_pack)
        install_registry.set_status(slug, "complete", install_path=str(target))
    except FileExistsError as exc:
        install_registry.set_status(slug, "error", error=str(exc))
        logger.error("ROM pack clone %s blocked: %s", slug, exc)
    except Exception as exc:
        install_registry.set_status(slug, "error", error=str(exc))
        logger.error("ROM pack clone %s failed: %s", slug, exc)


@router.get("/{slug}/status", response_model=EmulatorStatusData)
def get_emulator_status(slug: str, _: User = require_permission("is_admin")):
    try:
        entry = get_emulator(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Emulator '{slug}' not found.")

    binary = get_install_path(slug)
    installer_present = _installer_present(slug)

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


@router.patch("/{slug}/sandbox")
def patch_sandbox(slug: str, body: SandboxPatchRequest, _: User = require_permission("is_admin")):
    try:
        entry = get_emulator(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Emulator '{slug}' not found.")

    if body.container_enabled is True and entry.get("container_enabled") is False:
        raise HTTPException(
            status_code=400,
            detail="AppContainer is permanently disabled for this emulator. See known limitations for details.",
        )

    updates = body.model_dump(exclude_none=True)
    for field, value in updates.items():
        _settings.set_flag(f"sandbox_{slug}_{field}", value)

    return {"slug": slug, "updated": list(updates.keys())}


@router.delete("/{slug}")
def delete_emulator(slug: str, body: DeleteRequest, _: User = require_permission("is_admin")):
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
