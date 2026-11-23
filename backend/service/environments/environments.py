from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.models.environment import EnvironmentItem, EnvironmentItemCreate, EnvironmentItemUpdate
from backend.service.utils.confirmation_tokens import consume as _consume
from backend.constants import DOSBOX_PLATFORMS, PC_PLATFORMS
from backend.service.utils.platform_defaults import PROVISIONABLE_PLATFORMS
from backend.service.utils.slug_generator import unique_slug


def _validate_image_path(path_str: str) -> Path:
    from backend.service.utils.path_utils import normalise_path

    try:
        # allow_unc: Environment images may live on NAS shares (SECURITY.md,
        # "Environment image path traversal relies on the OS trust model").
        resolved = normalise_path(path_str, allow_unc=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not resolved.exists():
        raise HTTPException(status_code=400, detail="Path does not exist.")
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file.")
    return resolved


def _probe_image_integrity(path: Path) -> bool:
    """Cheap interrupted-write/corruption check for a working image.

    Not a format validator (working images may be raw .img, .vhd, or a
    pre-installed copy with varying internal layouts), just confirms the
    file is non-empty and its header and tail (where a VHD footer would
    live, per vm/vhd.py) are actually readable. A zero-byte or truncated
    file from an interrupted copy fails this; a legitimately fresh,
    not-yet-installed disk image does not.
    """
    try:
        size = path.stat().st_size
        if size == 0:
            return False
        with path.open("rb") as f:
            if not f.read(512):
                return False
            f.seek(max(0, size - 512))
            if not f.read(512):
                return False
    except OSError:
        return False
    return True


def _environment_files_present(platform: str, working: str | None, base: str | None) -> bool:
    if platform in DOSBOX_PLATFORMS:
        # DOS launches mount the per-item drive instead of working_image_path
        # (see provision_dosbox_drive). base_image_path is optional for DOS:
        # only a configured base image that is missing on disk fails here.
        return not base or Path(base).is_file()

    working_ok = bool(working and Path(working).is_file())
    base_ok = bool(base and Path(base).is_file())
    if not (working_ok and base_ok):
        return False
    return _probe_image_integrity(Path(working))


def compute_environment_presence(environment: EnvironmentItem) -> bool:
    """Uncached, boolean presence check for *environment*, safe to call on every
    read (list/detail/summary endpoints), nothing is persisted or cached, so
    this can never go stale the way the old persisted status column did.
    Same philosophy as check_bios_presence/validate_bios_from_descriptor:
    a live check of on-disk (or installed-binary) state, not a stored flag."""
    if environment.is_system or environment.platform in DOSBOX_PLATFORMS:
        from backend.service.utils.emulator_catalog import get_install_path as _get_install_path

        install_path = _get_install_path(environment.emulator_slug) if environment.emulator_slug else None
        if install_path is None:
            return False
        if environment.is_system:
            return True
    return _environment_files_present(environment.platform, environment.working_image_path, environment.base_image_path)


def create_environment_item(body: EnvironmentItemCreate, db: Session) -> EnvironmentItem:
    from backend.core.logger import get_logger

    logger = get_logger(__name__)

    if body.platform not in PC_PLATFORMS:
        raise HTTPException(
            status_code=422, detail=f"Only PC platforms are supported: {', '.join(sorted(PC_PLATFORMS))}."
        )

    environment_data = body.model_dump()
    if body.base_image_path:
        environment_data["base_image_path"] = str(_validate_image_path(body.base_image_path))
    if body.working_image_path:
        environment_data["working_image_path"] = str(_validate_image_path(body.working_image_path))
        # A working_image_path supplied directly in the create request is the
        # pre-installed-HDD-image path (SCOPE.md P2's primary media path): the
        # OS is already present the moment it's registered, launch-ready
        # immediately. Do not set this for the installer-media path below
        # (working_image_path absent here, auto-provisioned as an empty VHD/
        # drive), that one genuinely is not installed until the user runs the
        # installer inside the emulator.
        environment_data["installed_at"] = datetime.now(timezone.utc)

    environment = EnvironmentItem(**environment_data)
    if not environment.slug:
        environment.slug = unique_slug(
            environment.name,
            lambda s: db.query(EnvironmentItem).filter(EnvironmentItem.slug == s).first() is not None,
            fallback="environment",
        )
    db.add(environment)
    db.commit()
    db.refresh(environment)

    if not environment.working_image_path and environment.platform in PROVISIONABLE_PLATFORMS:
        try:
            from backend.service.utils.vm import provision_environment

            _iso, working_path, config_path, _install_path, _rom_path = provision_environment(environment)
            if _iso and not environment.base_image_path:
                environment.base_image_path = _iso
            if working_path:
                environment.working_image_path = working_path
            if config_path:
                environment.config_path = config_path
            db.commit()
            db.refresh(environment)
        except Exception as exc:
            logger.error(
                "Auto-provisioning failed for environment %d (%s/%s): %s",
                environment.id,
                environment.platform,
                environment.slug,
                exc,
            )
            # Provisioning failed after the row was already committed above,
            # so delete it rather than leave a half-provisioned environment
            # (no working_image_path, but a real id) that looks like a normal,
            # healthy row to both the DB and the caller.
            db.delete(environment)
            db.commit()
            raise HTTPException(
                status_code=500,
                detail=f"Environment provisioning failed: {exc}",
            ) from exc

    return environment


def delete_environment_item(environment_id: int, token: str, db: Session) -> None:
    from backend.core.logger import get_logger

    logger = get_logger(__name__)

    if not _consume(token, "environment_item", environment_id, "delete"):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    environment = db.get(EnvironmentItem, environment_id)
    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found.")

    # working_image_path is the app-managed working copy created at
    # registration/provisioning time (P2-4), safe to remove. base_image_path
    # is the user's original source image and is never modified or deleted by
    # the app (P2-4 "base is never modified"; 2026-07-05 DECISIONS.md notes
    # base/media images are "never mutated by the app, so they're never at
    # risk"), it is deliberately left untouched here.
    #
    # Path ownership is not just this row's problem: working_image_path has no
    # uniqueness constraint, so another Environment row could reference the same
    # file (e.g. a manually-set override via PATCH). Deleting the file out
    # from under a still-live Environment would be worse than leaving an orphan,
    # so the file is only removed if no other row still points at it.
    working_path = environment.working_image_path
    if working_path:
        still_referenced = (
            db.query(EnvironmentItem)
            .filter(EnvironmentItem.id != environment_id, EnvironmentItem.working_image_path == working_path)
            .first()
            is not None
        )
        if still_referenced:
            logger.info(
                "Environment %d deleted; working_image_path '%s' left on disk, "
                "still referenced by another environment.",
                environment_id,
                working_path,
            )
        else:
            try:
                img = Path(working_path)
                if img.exists():
                    img.unlink()
                    logger.info("Deleted working image for environment %d: %s", environment_id, img)
            except OSError as exc:
                logger.warning(
                    "Could not delete working image %s for environment %d: %s",
                    working_path,
                    environment_id,
                    exc,
                )

    db.delete(environment)
    db.commit()


def update_environment_item(environment_id: int, body: EnvironmentItemUpdate, db: Session) -> EnvironmentItem:
    environment = db.get(EnvironmentItem, environment_id)
    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found.")
    # exclude_unset (not exclude_none): a PATCH must distinguish "field absent
    # from the request" (leave untouched) from "field explicitly sent as null"
    # (clear it). exclude_none dropped every explicit-null field before
    # setattr ever ran, silently no-op'ing every clear-to-null PATCH for every
    # nullable field on this model (installed_at, working_image_path,
    # base_image_path, config_path, notes, ...), confirmed live in
    # EnvironmentDetail.tsx's edit form, which sends `... || null` for exactly
    # this purpose.
    updates = body.model_dump(exclude_unset=True)
    if "platform" in updates and updates["platform"] not in PC_PLATFORMS:
        raise HTTPException(
            status_code=422, detail=f"Only PC platforms are supported: {', '.join(sorted(PC_PLATFORMS))}."
        )
    # Validate-and-normalise only when a non-empty path was actually sent; an
    # explicit null/empty value is a real clear and must pass through as None,
    # not be handed to _validate_image_path (which requires a real path and
    # would reject/crash on None).
    if updates.get("base_image_path"):
        updates["base_image_path"] = str(_validate_image_path(updates["base_image_path"]))
    if updates.get("working_image_path"):
        updates["working_image_path"] = str(_validate_image_path(updates["working_image_path"]))
    for key, value in updates.items():
        setattr(environment, key, value)
    db.commit()
    db.refresh(environment)
    return environment


def check_environment_item_health(environment: EnvironmentItem, db: Session) -> dict:
    """Live recompute, nothing persisted (status/last_health_check no longer
    exist on the model), this is now a read, not a write, but the route stays
    for the frontend's per-Environment "Check now" action."""
    present = compute_environment_presence(environment)

    if environment.is_system:
        from backend.service.utils.emulator_catalog import get_install_path as _get_install_path

        install_path = _get_install_path(environment.emulator_slug) if environment.emulator_slug else None
        return {
            "is_present": present,
            "binary_exists": install_path is not None,
            "binary_path": str(install_path) if install_path else None,
        }

    return {
        "is_present": present,
        "working_image_exists": bool(environment.working_image_path and Path(environment.working_image_path).is_file()),
        "base_image_exists": bool(environment.base_image_path and Path(environment.base_image_path).is_file()),
    }


def batch_health_check(db: Session) -> dict:
    """Live recompute over all user Environments, nothing persisted."""
    environments = db.query(EnvironmentItem).filter(EnvironmentItem.is_system == False).all()  # noqa: E712
    results = [
        {"id": environment.id, "is_present": compute_environment_presence(environment)} for environment in environments
    ]
    return {"results": results, "checked": len(results)}


def get_health_summary(db: Session) -> dict:
    from sqlalchemy import func, distinct as sa_distinct
    from backend.models.game import GameItemBundle, GameItem
    from backend.service.utils.emulator_catalog import (
        check_bios_presence,
        get_install_path,
        load_bios_requirements,
        load_catalog,
    )

    user_environments = db.query(EnvironmentItem).filter(EnvironmentItem.is_system == False).all()  # noqa: E712
    # Computed live (nothing persisted) so this always matches what
    # list_environment_items shows on the same page load, see
    # compute_environment_presence.
    environments_present = sum(1 for p in user_environments if compute_environment_presence(p))

    # "library total" = number of games (collections); a multi-disc set counts once.
    library_count = db.query(GameItemBundle).count()
    # Count actual per-collection Drive rows (mirrors get_drive_images_bytes, which
    # sums those same rows' image files).
    from backend.models.drive import Drive

    drive_count = db.query(Drive).count()
    extension_count = (
        db.query(func.count(sa_distinct(GameItem.file_type))).filter(GameItem.file_type.isnot(None)).scalar() or 0
    )

    catalog = load_catalog()
    emulator_total = len(catalog)
    emulator_installed = sum(1 for e in catalog if get_install_path(e["slug"]) is not None)

    bios_reqs = load_bios_requirements()
    bios_total = len(bios_reqs)
    bios_present = sum(
        1
        for b in bios_reqs
        if b.get("bios_path")
        and check_bios_presence(
            b["bios_path"],
            required_files=b.get("required_files"),
            required_glob=b.get("required_glob"),
            required_glob_excludes=b.get("required_glob_excludes"),
        )
    )

    from backend.models.rom_pack import RomPackItem

    rom_entries = [e for e in catalog if e.get("install_type") == "rom_pack"]
    rom_total = len(rom_entries)
    rom_pack_slugs = {e["slug"] for e in rom_entries}
    rom_installed = (
        db.query(RomPackItem)
        .filter(RomPackItem.slug.in_(rom_pack_slugs), RomPackItem.is_present == True)  # noqa: E712
        .count()
        if rom_pack_slugs
        else 0
    )

    return {
        "environments": {
            "total": len(user_environments),
            "present": environments_present,
        },
        "library": {"total": library_count},
        "drives": {"total": drive_count},
        "extensions": {"total": extension_count},
        "emulators": {"total": emulator_total, "installed": emulator_installed},
        "bios": {"total": bios_total, "present": bios_present},
        "rom_packs": {"total": rom_total, "installed": rom_installed},
    }


def _safe_file_size(path: str | None) -> int:
    if not path:
        return 0
    try:
        return os.path.getsize(path) if os.path.isfile(path) else 0
    except OSError:
        return 0


def get_drive_images_bytes(db: Session) -> int:
    from backend.models.drive import Drive

    return sum(_safe_file_size(d.image_path) for d in db.query(Drive).all())


def get_storage_stats(db: Session) -> dict:
    from backend.models.game import GameItem
    from backend.service.utils import settings as _settings
    from backend.service.utils.emulator_catalog import (
        get_settings_key as _get_settings_key,
        load_catalog as _load_catalog,
    )

    drive_images_bytes = get_drive_images_bytes(db)
    source_media_bytes = sum(_safe_file_size(item.file_path) for item in db.query(GameItem).all())
    os_images_bytes = sum(
        _safe_file_size(p.base_image_path) + _safe_file_size(p.working_image_path)
        for p in db.query(EnvironmentItem).all()
    )
    emulator_binaries_bytes = sum(
        _safe_file_size(_settings.get(_get_settings_key(e["slug"])) or "")
        for e in _load_catalog()
        if e.get("install_type") != "rom_pack"
    )

    return {
        "drive_images_bytes": drive_images_bytes,
        "source_media_bytes": source_media_bytes,
        "os_images_bytes": os_images_bytes,
        "emulator_binaries_bytes": emulator_binaries_bytes,
    }
