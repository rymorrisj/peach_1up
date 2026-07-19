"""Server-side creation of a linked Media item from a metadata provider's
fetched image assets (the Fetch Metadata flow's Accept All step,
backend/api/routes/game_metadata.py's accept_metadata_assets route).

Downloadable images only. Trailer/video links never reach this module: per
the locked design they are stored directly on GameItemBundle.external_links
(see backend/service/games/enrich.py), never downloaded, never become a
Media item.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.models.media import MediaItemBundle
    from backend.service.metadata_providers import MetadataAsset


def create_linked_media_from_metadata(
    game_item_bundle_id: int,
    assets: list["MetadataAsset"],
    db: "Session",
) -> "MediaItemBundle":
    """Download every asset in *assets* into MEDIA_PATH and attach it to a
    Media item bundle linked to this game.

    If this game already has a linked media_item_bundle (found via the
    generalized entity-link table, not a bespoke lookup), the new items join
    that existing bundle instead of a new one being created, per the locked
    "later additions join the same bundle" decision. If more than one
    media_item_bundle happens to already be linked (e.g. a user separately,
    manually linked an unrelated one), the earliest link (lowest link_id)
    wins, deterministically, this is a real edge case the locked design
    doesn't explicitly resolve, flagged in this session's report.

    Images always live at the bundle level on both sides of the link (never
    leaf-to-leaf, never leaf-to-bundle), matching how GameItemBundle links
    are scoped everywhere else in this codebase.

    Raises:
        HTTPException: 404 if the game doesn't exist, 422 if assets is empty.
    """
    from backend.core.settings import get_settings
    from backend.models.game import GameItemBundle
    from backend.models.media import (
        MediaItem, MediaItemBundle, _linked_items_for, make_entity_link, unique_media_slug,
    )
    from backend.service.utils.asset_fetch import download_remote_image
    from backend.service.utils.upload_utils import begin_upload

    game = db.get(GameItemBundle, game_item_bundle_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found.")
    if not assets:
        raise HTTPException(status_code=422, detail="No downloadable assets to accept.")

    existing_refs = [
        ref for ref in _linked_items_for("game_item_bundle", game_item_bundle_id, db)
        if ref.entity_type == "media_item_bundle"
    ]
    bundle = None
    if existing_refs:
        earliest = min(existing_refs, key=lambda r: r.link_id)
        bundle = db.get(MediaItemBundle, earliest.entity_id)

    media_root = Path(get_settings().get_env_var("MEDIA_PATH")).resolve()
    dest_dir, _ = begin_upload(media_root, game.title)

    # "First/boxart": the front-boxart asset if present, else whichever
    # asset happens to be first in the list (IGDB's single "cover" asset,
    # for instance, has no "boxart_front" type at all).
    boxart = next((a for a in assets if a.type == "boxart_front"), assets[0])

    downloaded: list[tuple["MetadataAsset", Path]] = []
    for i, asset in enumerate(assets):
        stem = asset.type or f"asset-{i}"
        path = download_remote_image(asset.url, dest_dir, filename_stem=stem)
        downloaded.append((asset, path))

    is_new_bundle = bundle is None
    if is_new_bundle:
        bundle = MediaItemBundle(
            title=game.title,
            media_kind="image",
            slug=unique_media_slug(game.title, db),
        )
        db.add(bundle)
        db.flush()
        boxart_path = next((p for a, p in downloaded if a is boxart), downloaded[0][1])
        bundle.cover_art_path = str(boxart_path)

    for asset, path in downloaded:
        db.add(MediaItem(
            title=f"{game.title} - {asset.type}",
            media_kind="image",
            file_path=str(path),
            media_item_bundle_id=bundle.id,
        ))

    db.flush()

    if is_new_bundle:
        # Reuses the same canonical-ordering helper the generic entity-link
        # route uses (backend/api/routes/entity_links.py), no bespoke
        # MediaLink construction here.
        db.add(make_entity_link("game_item_bundle", game_item_bundle_id, "media_item_bundle", bundle.id))

    db.commit()
    db.refresh(bundle)
    return bundle
