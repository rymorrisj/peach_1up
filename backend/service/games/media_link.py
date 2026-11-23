"""Server-side creation of a linked Media item from a metadata provider's
fetched image assets (the Fetch Metadata flow's Accept All step,
backend/api/routes/game_metadata.py's accept_metadata_assets route).

Downloadable images only. Trailer/video links never reach this module: per
the locked design they are stored directly on GameItemBundle.external_links
(see backend/service/games/enrich.py), never downloaded, never become a
Media item.

One apply is all or nothing (META-6): every asset streams into a per-apply
temp directory under MEDIA_PATH/_asset_staging first, files are moved to
their final names only once every download succeeded, and any failure
before the commit removes every file this apply created and rolls the
session back.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Literal, Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from backend.service.utils.path_utils import asset_staging_root, media_root, safe_basename

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.models.media import MediaItemBundle
    from backend.service.metadata_providers import MetadataAsset

# Per-apply limits (META-5), Accept All only: no upload path reads these.
# 30 assets at the 20 MB per-image cap bounds one
# apply at 600 MB on disk; 90 s stays inside the frontend's 120 s Accept All
# timeout so the server answers before the client gives up.
ACCEPT_ALL_MAX_ASSETS = 30
ACCEPT_ALL_TIME_BUDGET_SECONDS = 90.0

PreviousAssets = Literal["replace", "keep"]
# error_type of the structured 409 asking the client to choose Replace or Keep.
PREVIOUS_ASSETS_ERROR_TYPE = "previous_assets_choice_required"

# Asset types preferred for the bundle cover (MED-14), in order.
_COVER_ASSET_TYPES = ("cover", "boxart_front")

_running_applies: set[tuple[str, int]] = set()
_running_guard = threading.Lock()


def asset_filename_stem(asset_type: str, index: int) -> str:
    """On-disk filename stem for the *index*-th asset of one Accept All call.

    The type is reduced to a safe basename (no separators, no ``..``) even
    though the route already allowlists it, and the per-call index makes
    every stem unique, so ten screenshots land as ten files instead of
    overwriting one ``screenshot.jpg`` (META-1, META-3). commit_temp_image
    additionally claims the final name exclusively, so a collision fails
    loudly.
    """
    return f"{safe_basename(asset_type or '', fallback='asset')}-{index}"


@contextmanager
def single_apply(
    key: tuple[str, int],
    detail: str = "An Accept All for this game's media is already running. Wait for it to finish.",
) -> Iterator[None]:
    """One apply per *key* at a time in this process (409 with *detail*
    otherwise). Accept All keys per game and per media bundle (several games
    can share one), so two concurrent applies cannot both pass the dedupe
    check or replace the same rows; the per-disc cover enrich keys per disc."""
    with _running_guard:
        if key in _running_applies:
            raise HTTPException(status_code=409, detail=detail)
        _running_applies.add(key)
    try:
        yield
    finally:
        with _running_guard:
            _running_applies.discard(key)


def _linked_bundle(game_item_bundle_id: int, db: "Session") -> Optional["MediaItemBundle"]:
    """The media bundle this game's Accept All joins: the earliest linked
    one (lowest link_id), per the locked "later additions join the same
    bundle" decision."""
    from backend.models.media import MediaItemBundle, _linked_items_for

    refs = [
        ref for ref in _linked_items_for("game_item_bundle", game_item_bundle_id, db)
        if ref.entity_type == "media_item_bundle"
    ]
    if not refs:
        return None
    return db.get(MediaItemBundle, min(refs, key=lambda r: r.link_id).entity_id)


def _cover_candidate(items: list) -> Optional[str]:
    for wanted in _COVER_ASSET_TYPES:
        hit = next((i for i in items if i.asset_type == wanted), None)
        if hit is not None:
            return hit.file_path
    return items[0].file_path if items else None


def create_linked_media_from_metadata(
    game_item_bundle_id: int,
    assets: list["MetadataAsset"],
    db: "Session",
    *,
    previous_assets: Optional[PreviousAssets] = None,
) -> "MediaItemBundle":
    """Download *assets* into MEDIA_PATH and attach them to the Media item
    bundle linked to this game, creating and linking one if none exists.

    Items created here store asset_type and source_url; source_url marks an
    item as fetch-created. Assets are deduplicated by URL within the
    request. When the bundle already holds fetch-created items the caller
    must choose *previous_assets*:

    - "replace": remove those items (files only when app-owned and no other
      row references them, after the commit), clear every cover that
      pointed at them, then add the new set
    - "keep": leave them and add only assets whose URL is new

    Items with a null source_url (added by hand) are never touched. A null
    bundle cover is set to the first new image, preferring cover/box art
    (MED-14); an existing cover is never overwritten.

    Raises:
        HTTPException: 404 if the game doesn't exist, 422 if assets is
            empty or the time budget runs out, 413 above
            ACCEPT_ALL_MAX_ASSETS, 409 when a Replace/Keep choice is needed
            (structured detail) or another apply for this game is running,
            503 if MEDIA_PATH is not configured.
    """
    from backend.models.game import GameItemBundle

    game = db.get(GameItemBundle, game_item_bundle_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found.")
    if not assets:
        raise HTTPException(status_code=422, detail="No downloadable assets to accept.")
    if len(assets) > ACCEPT_ALL_MAX_ASSETS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"This metadata offers {len(assets)} images, but Accept All can apply at most "
                f"{ACCEPT_ALL_MAX_ASSETS} per apply (limit {ACCEPT_ALL_MAX_ASSETS}). "
                "Nothing was downloaded."
            ),
        )
    # Resolved before any lookup, download or write: an unset or blank
    # MEDIA_PATH is a 503, never Path("").resolve() (the working directory),
    # matching the media upload routes.
    try:
        root = media_root()
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail="MEDIA_PATH is not configured.") from exc

    with single_apply(("game", game_item_bundle_id)):
        bundle = _linked_bundle(game_item_bundle_id, db)
        if bundle is None:
            return _apply(game, bundle, assets, root, previous_assets, db)
        with single_apply(("media_bundle", bundle.id)):
            return _apply(game, bundle, assets, root, previous_assets, db)


def _apply(
    game,
    bundle: Optional["MediaItemBundle"],
    assets: list["MetadataAsset"],
    root: Path,
    previous_assets: Optional[PreviousAssets],
    db: "Session",
) -> "MediaItemBundle":
    from backend.models.media import MediaItem, MediaItemBundle, delete_links_for, make_entity_link, unique_media_slug
    from backend.service.media.file_cleanup import (
        clear_cover_references, path_keys, remove_files, removable_media_files,
    )
    from backend.service.utils.asset_fetch import commit_temp_image, fetch_image_to_temp, final_image_path
    from backend.service.utils.upload_utils import begin_upload

    deadline = time.monotonic() + ACCEPT_ALL_TIME_BUDGET_SECONDS
    fetched_before = [i for i in bundle.items if i.source_url] if bundle is not None else []
    if fetched_before and previous_assets is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": PREVIOUS_ASSETS_ERROR_TYPE,
                "message": (
                    f"This game's media already has {len(fetched_before)} fetched image(s). "
                    "Re-submit with previous_assets set to replace or keep."
                ),
                "existing_count": len(fetched_before),
            },
        )
    replaced = fetched_before if previous_assets == "replace" else []
    seen_urls = {i.source_url for i in fetched_before} if previous_assets == "keep" else set()
    to_fetch: list["MetadataAsset"] = []
    for asset in assets:
        if asset.url in seen_urls:
            continue
        seen_urls.add(asset.url)
        to_fetch.append(asset)
    if not to_fetch and not replaced:
        return bundle

    staging_root = asset_staging_root()
    staging_root.mkdir(parents=True, exist_ok=True)
    apply_dir = Path(tempfile.mkdtemp(prefix="apply-", dir=staging_root))
    created_files: list[Path] = []
    created_dir: Optional[Path] = None
    old_files: list[str] = []
    try:
        fetched = [
            (asset, *fetch_image_to_temp(asset.url, apply_dir, deadline=deadline))
            for asset in to_fetch
        ]

        if replaced:
            replaced_ids = {i.id for i in replaced}
            replaced_paths = [i.file_path for i in replaced]
            old_files = removable_media_files(replaced_paths, replaced_ids, db)
            # Covers on files that stay (another row uses them) keep working;
            # only this bundle's own cover moves to the new set.
            clear_cover_references(old_files, db)
            if path_keys(bundle.cover_art_path) & {k for raw in replaced_paths for k in path_keys(raw)}:
                bundle.cover_art_path = None
            for item in replaced:
                delete_links_for("media_item", item.id, db)
                db.delete(item)

        is_new_bundle = bundle is None
        if is_new_bundle:
            bundle = MediaItemBundle(
                title=game.title,
                media_kind="image",
                slug=unique_media_slug(game.title, db),
            )
            db.add(bundle)
            try:
                db.flush()
            except IntegrityError:
                # unique_media_slug's check-then-insert isn't atomic. Join the
                # bundle another request created and linked for this game, or
                # fail when the collision is with an unrelated bundle.
                db.rollback()
                bundle = _linked_bundle(game.id, db)
                if bundle is None:
                    raise HTTPException(
                        status_code=409,
                        detail="A conflicting media item was created at the same time. Please try again.",
                    )
                is_new_bundle = False

        new_items: list = []
        if fetched:
            created_dir, _ = begin_upload(root, game.title)
            for index, (asset, tmp, ext) in enumerate(fetched):
                dest = final_image_path(created_dir, asset_filename_stem(asset.type, index), ext)
                commit_temp_image(tmp, dest, overwrite=False)
                created_files.append(dest)
                item = MediaItem(
                    title=f"{game.title} - {asset.type}",
                    media_kind="image",
                    file_path=str(dest),
                    media_item_bundle_id=bundle.id,
                    asset_type=asset.type,
                    source_url=asset.url,
                )
                db.add(item)
                new_items.append(item)

        if not bundle.cover_art_path:
            bundle.cover_art_path = _cover_candidate(new_items)

        db.flush()
        if is_new_bundle:
            db.add(make_entity_link("game_item_bundle", game.id, "media_item_bundle", bundle.id))
        db.commit()
    except BaseException:
        db.rollback()
        for path in created_files:
            path.unlink(missing_ok=True)
        if created_dir is not None:
            try:
                created_dir.rmdir()
            except OSError:
                pass
        raise
    finally:
        shutil.rmtree(apply_dir, ignore_errors=True)

    remove_files(old_files, db)
    db.refresh(bundle)
    return bundle
