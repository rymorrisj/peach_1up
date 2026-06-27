from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional

import httpx
from fastapi import HTTPException

from backend.models.library import LibraryItem
from backend.models.library_set import LibrarySet, LibrarySetItem

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_COVER_DOWNLOAD_MAX_BYTES = 20 * 1024 * 1024  # 20 MB

_MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _download_cover_art(url: str, dest_dir: Path) -> Path:
    if not url.startswith("https://"):
        raise HTTPException(status_code=422, detail="cover_art_url must use https")

    from backend.service.utils import settings as _s
    lib_root = Path(_s.get("LIBRARY_PATH")).resolve()
    dest_dir_resolved = dest_dir.resolve()
    try:
        dest_dir_resolved.relative_to(lib_root)
    except ValueError:
        raise HTTPException(status_code=422, detail="Resolved cover art destination is outside LIBRARY_PATH.")

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        resp = client.get(url)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"cover_art_url fetch failed: {e}")
        content_type = resp.headers.get("content-type", "").split(";")[0].strip()
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=422,
                detail=f"cover_art_url returned non-image content-type: {content_type}",
            )
        data = resp.content
        if len(data) > _COVER_DOWNLOAD_MAX_BYTES:
            raise HTTPException(status_code=422, detail="cover_art_url image exceeds 20 MB size limit")

    ext = _MIME_TO_EXT.get(content_type, ".jpg")
    dest_dir_resolved.mkdir(parents=True, exist_ok=True)
    dest = dest_dir_resolved / f"cover{ext}"
    dest.write_bytes(data)
    return dest


def enrich_entity(
    entity_type: Literal["library_item", "library_set", "library_set_item"],
    entity_id: int,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    publisher: Optional[str] = None,
    year: Optional[int] = None,
    content_rating: Optional[str] = None,
    metadata_source: Optional[str] = None,
    cover_art_url: Optional[str] = None,
    db: "Session",
) -> tuple:
    metadata_fields = {k: v for k, v in {
        "title": title,
        "description": description,
        "publisher": publisher,
        "year": year,
        "content_rating": content_rating,
        "metadata_source": metadata_source,
    }.items() if v is not None}

    if entity_type == "library_item":
        entity = db.get(LibraryItem, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Library item not found.")
        for key, value in metadata_fields.items():
            setattr(entity, key, value)
        if cover_art_url:
            dest_dir = Path(entity.folder_path) if entity.folder_path else Path(entity.media_path).parent
            entity.cover_art_path = str(_download_cover_art(cover_art_url, dest_dir))

    elif entity_type == "library_set":
        entity = db.get(LibrarySet, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Library set not found.")
        if cover_art_url:
            raise HTTPException(
                status_code=422,
                detail=(
                    "cover_art_url is not supported for library_set; "
                    "apply cover art to individual library_set_item discs instead."
                ),
            )
        for key, value in metadata_fields.items():
            setattr(entity, key, value)

    elif entity_type == "library_set_item":
        entity = db.get(LibrarySetItem, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Library set item not found.")
        if metadata_fields:
            raise HTTPException(
                status_code=422,
                detail=(
                    "library_set_item does not support metadata fields (title, description, etc.); "
                    "apply those to the parent library_set."
                ),
            )
        if cover_art_url:
            dest_dir = Path(entity.media_path).parent
            entity.cover_art_path = str(_download_cover_art(cover_art_url, dest_dir))

    else:
        raise HTTPException(status_code=422, detail=f"Invalid entity_type: {entity_type!r}")

    db.commit()
    db.refresh(entity)
    return entity, entity_type
