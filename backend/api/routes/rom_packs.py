from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.dependencies import get_active_user, require_permission
from backend.models.pagination import Page
from backend.models.rom_pack import RomPackItem, RomPackItemRead
from backend.models.user import UserItem
from backend.service.utils.emulator_catalog import get_emulator, get_install_path, load_catalog
from backend.service.utils.emulator_installer import record_rom_pack_item

router = APIRouter(prefix="/api/v1/emulator-items/rom-packs", tags=["rom-packs"])


def _rom_pack_catalog_entries() -> list[dict]:
    return [e for e in load_catalog() if e.get("install_type") == "rom_pack"]


def _emulator_slug_for(pack_slug: str) -> str:
    """Find the emulator catalog entry that lists *pack_slug* as a dependency."""
    for entry in load_catalog():
        for dep in entry.get("dependencies", []):
            if dep.get("name") == pack_slug:
                return entry["slug"]
    return ""


def _to_read(entry: dict, row: Optional[RomPackItem]) -> RomPackItemRead:
    if row is not None:
        return RomPackItemRead.model_validate(row, from_attributes=True)
    # No rom_pack_items row yet — the pack is known to the catalog but has
    # never been cloned or verified. Synthesize an unpersisted response.
    return RomPackItemRead(
        slug=entry["slug"],
        name=entry.get("name", entry["slug"]),
        emulator_slug=_emulator_slug_for(entry["slug"]),
        source_url=entry.get("source_url"),
        is_present=False,
    )


@router.get("", response_model=Page[RomPackItemRead])
def list_rom_packs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: UserItem = Depends(get_active_user),
):
    entries = _rom_pack_catalog_entries()
    rows_by_slug = {r.slug: r for r in db.query(RomPackItem).all()}
    items = [_to_read(entry, rows_by_slug.get(entry["slug"])) for entry in entries]
    total = len(items)
    return Page(items=items[offset:offset + limit], total=total, limit=limit, offset=offset)


@router.get("/{slug}", response_model=RomPackItemRead)
def get_rom_pack(slug: str, db: Session = Depends(get_db), _: UserItem = Depends(get_active_user)):
    try:
        entry = get_emulator(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"ROM pack '{slug}' not found.")
    if entry.get("install_type") != "rom_pack":
        raise HTTPException(status_code=404, detail=f"'{slug}' is not a ROM pack.")
    row = db.query(RomPackItem).filter(RomPackItem.slug == slug).one_or_none()
    return _to_read(entry, row)


@router.post("/{slug}/verify", response_model=RomPackItemRead)
def verify_rom_pack(slug: str, db: Session = Depends(get_db), _: UserItem = require_permission("is_admin")):
    """Re-check on-disk presence and sync the owned rom_pack_items row.

    Does not perform the clone itself — that remains
    POST /api/v1/emulator-items/{slug}/install (clone_rom_pack, unchanged). This
    covers the case where a ROM pack was placed manually rather than cloned.
    """
    try:
        entry = get_emulator(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"ROM pack '{slug}' not found.")
    if entry.get("install_type") != "rom_pack":
        raise HTTPException(status_code=400, detail=f"'{slug}' is not a ROM pack.")

    install_path = get_install_path(slug)
    record_rom_pack_item(slug, _emulator_slug_for(slug), install_path, is_present=install_path is not None)

    row = db.query(RomPackItem).filter(RomPackItem.slug == slug).one_or_none()
    return _to_read(entry, row)
