from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional

import httpx
from fastapi import HTTPException

from backend.models.library import LibraryCollection, LibraryItem

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_COVER_DOWNLOAD_MAX_BYTES = 20 * 1024 * 1024  # 20 MB

_MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _is_forbidden_redirect_host(host: str) -> bool:
    """Return True if the host is a private/internal address that should not be reached."""
    if host.lower() == "localhost":
        return True
    # httpx.URL.host strips brackets from IPv6 literals, so ip_address() can parse directly
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
    except ValueError:
        return False


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
        with client.stream("GET", url) as resp:
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(status_code=502, detail=f"cover_art_url fetch failed: {e}")

            # Re-validate the final URL after redirects — scheme and host may differ from the original
            final_url = resp.url
            if final_url.scheme != "https" or _is_forbidden_redirect_host(final_url.host):
                raise HTTPException(
                    status_code=422,
                    detail="cover_art_url redirect target must be an https non-private host",
                )

            content_type = resp.headers.get("content-type", "").split(";")[0].strip()
            if not content_type.startswith("image/"):
                raise HTTPException(
                    status_code=422,
                    detail=f"cover_art_url returned non-image content-type: {content_type}",
                )

            # Stream body incrementally — abort before full download if limit is exceeded
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > _COVER_DOWNLOAD_MAX_BYTES:
                    raise HTTPException(status_code=422, detail="cover_art_url image exceeds 20 MB size limit")
                chunks.append(chunk)
            data = b"".join(chunks)

    ext = _MIME_TO_EXT.get(content_type, ".jpg")
    dest_dir_resolved.mkdir(parents=True, exist_ok=True)
    dest = dest_dir_resolved / f"cover{ext}"
    dest.write_bytes(data)
    return dest


def enrich_entity(
    entity_type: Literal["library_collection", "library_item"],
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
        "metadata_source": metadata_source,
    }.items() if v is not None}

    if content_rating is not None:
        # Normalise free-form ratings (e.g. TheGamesDB "M - Mature 17+") onto
        # the known vocabulary. An unrecognised value is written as null rather
        # than stored verbatim, so it can never slip past the content-rating
        # filter as an unknown string. content_rating=None means "leave as-is".
        from backend.core.dependencies import normalize_content_rating
        metadata_fields["content_rating"] = normalize_content_rating(content_rating)

    if entity_type == "library_collection":
        # Metadata lives on the collection; cover art belongs on the individual leaves.
        entity = db.get(LibraryCollection, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Library collection not found.")
        if cover_art_url:
            raise HTTPException(
                status_code=422,
                detail=(
                    "cover_art_url is not supported for library_collection; "
                    "apply cover art to individual library_item discs instead."
                ),
            )
        for key, value in metadata_fields.items():
            setattr(entity, key, value)

    elif entity_type == "library_item":
        # Leaf: per-disc cover art only — no metadata fields (those go on the collection).
        entity = db.get(LibraryItem, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Library item not found.")
        if metadata_fields:
            raise HTTPException(
                status_code=422,
                detail=(
                    "library_item does not support metadata fields (title, description, etc.); "
                    "apply those to the parent library_collection."
                ),
            )
        if cover_art_url:
            dest_dir = Path(entity.folder_path) if entity.folder_path else Path(entity.media_path).parent
            entity.cover_art_path = str(_download_cover_art(cover_art_url, dest_dir))

    else:
        raise HTTPException(status_code=422, detail=f"Invalid entity_type: {entity_type!r}")

    db.commit()
    db.refresh(entity)
    return entity, entity_type
