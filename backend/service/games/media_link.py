"""Server-side creation of a linked Media item from a metadata provider's
fetched image assets (the Fetch Metadata flow's Accept All step,
backend/api/routes/game_metadata.py's accept_metadata_assets route).

Downloadable images only. Trailer/video links never reach this module: per
the locked design they are stored directly on GameItemBundle.external_links
(see backend/service/games/enrich.py), never downloaded, never become a
Media item.

An apply has two phases. prepare_apply runs the synchronous pre-checks and
takes the per-game and per-media-bundle locks; run_apply (called from the
background job, backend/service/games/accept_all_job.py) does the work and
always releases them.

One apply is all or nothing (META-6): every asset streams into a per-apply
temp directory under MEDIA_PATH/_asset_staging first, files are moved to
their final names only once every download succeeded, and any failure
or cancellation before the commit removes every file this apply created and
rolls the session back.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal, Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from backend.service.utils.path_utils import asset_staging_root, media_root, safe_basename

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.models.media import MediaItem, MediaItemBundle
    from backend.service.metadata_providers import MetadataAsset

# Per-apply limits (META-5), Accept All only: no upload path reads these.
# 30 assets at the 20 MB per-image cap bounds one apply at 600 MB on disk.
# The apply runs as a background job, so no client request waits on it: the
# budget only has to cover 30 sequential downloads (each also capped by the
# 15 s per-download timeout) on a slow link, and 10 minutes is about 1 MB/s
# for a full 600 MB set.
ACCEPT_ALL_MAX_ASSETS = 30
ACCEPT_ALL_TIME_BUDGET_SECONDS = 600.0

PreviousAssets = Literal["replace", "keep"]
# error_type of the structured 409 asking the client to choose Replace or Keep.
PREVIOUS_ASSETS_ERROR_TYPE = "previous_assets_choice_required"

CANCELLED_CODE = "cancelled"

# Asset types preferred for the bundle cover (MED-14), in order.
_COVER_ASSET_TYPES = ("cover", "boxart_front")

# (asset_done, asset_total, label of the asset being downloaded or None)
ProgressFn = Callable[[int, int, Optional[str]], None]
LockKey = tuple[str, int]

_running_applies: set[LockKey] = set()
_running_guard = threading.Lock()


class ApplyFailure(Exception):
    """A failure with a stable machine-readable *code* (CANCELLED_CODE or
    "cover_rejected"), reported to the client as {code, message}."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ApplyPlan:
    """A validated apply holding its locks. run_apply, or the caller if it
    never gets that far, must call release()."""

    game_id: int
    assets: list["MetadataAsset"]
    previous_assets: Optional[PreviousAssets]
    cover_asset_url: Optional[str]
    root: Path
    lock_keys: list[LockKey] = field(default_factory=list)
    _released: bool = False

    def release(self) -> None:
        """Release the locks once; later calls do nothing, so a key another
        apply has since taken is never released from under it."""
        with _running_guard:
            if self._released:
                return
            self._released = True
            for key in self.lock_keys:
                _running_applies.discard(key)


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


def _acquire(key: LockKey, held: list[LockKey]) -> None:
    """Take *key* (409 if another apply holds it) and append it to *held*."""
    with _running_guard:
        if key in _running_applies:
            raise HTTPException(
                status_code=409,
                detail="An Accept All for this game's media is already running. Wait for it to finish.",
            )
        _running_applies.add(key)
        held.append(key)


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


def _fetched_items(bundle: Optional["MediaItemBundle"]) -> list["MediaItem"]:
    return [i for i in bundle.items if i.source_url] if bundle is not None else []


def _cover_candidate(items: list) -> Optional[str]:
    for wanted in _COVER_ASSET_TYPES:
        hit = next((i for i in items if i.asset_type == wanted), None)
        if hit is not None:
            return hit.file_path
    return items[0].file_path if items else None


def prepare_apply(
    game_item_bundle_id: int,
    assets: list["MetadataAsset"],
    db: "Session",
    *,
    previous_assets: Optional[PreviousAssets] = None,
    cover_asset_url: Optional[str] = None,
) -> ApplyPlan:
    """Run every synchronous pre-check of an Accept All and take its locks.

    On success the returned plan holds the per-game lock (and the linked
    media bundle's, when one exists) until run_apply or release() frees it.
    Nothing is downloaded or written here.

    Items created by an apply store asset_type and source_url; source_url
    marks an item as fetch-created. When the bundle already holds
    fetch-created items the caller must choose *previous_assets*.

    Raises:
        HTTPException: 404 if the game doesn't exist, 422 if assets is empty
            or *cover_asset_url* is not one of them, 413 above
            ACCEPT_ALL_MAX_ASSETS, 409 when a Replace/Keep choice is needed
            (structured detail) or another apply for this game is running,
            503 if MEDIA_PATH is not configured.
    """
    from backend.models.game import GameItemBundle

    if not db.get(GameItemBundle, game_item_bundle_id):
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
    if cover_asset_url is not None and cover_asset_url not in {a.url for a in assets}:
        raise HTTPException(status_code=422, detail="cover_asset_url must be one of the submitted assets.")
    # Resolved before any lookup, download or write: an unset or blank
    # MEDIA_PATH is a 503, never Path("").resolve() (the working directory),
    # matching the media upload routes.
    try:
        root = media_root()
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail="MEDIA_PATH is not configured.") from exc

    held: list[LockKey] = []
    try:
        _acquire(("game", game_item_bundle_id), held)
        bundle = _linked_bundle(game_item_bundle_id, db)
        if bundle is not None:
            _acquire(("media_bundle", bundle.id), held)
        fetched_before = _fetched_items(bundle)
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
    except BaseException:
        with _running_guard:
            for key in held:
                _running_applies.discard(key)
        raise
    return ApplyPlan(
        game_id=game_item_bundle_id, assets=assets, previous_assets=previous_assets,
        cover_asset_url=cover_asset_url, root=root, lock_keys=held,
    )


def run_apply(
    plan: ApplyPlan,
    db: "Session",
    *,
    progress: Optional[ProgressFn] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Optional["MediaItemBundle"]:
    """Download the plan's assets into MEDIA_PATH and attach them to the
    Media item bundle linked to this game, creating and linking one if none
    exists. Always releases the plan's locks.

    Assets are deduplicated by URL within the request. *previous_assets*:

    - "replace": remove the fetch-created items (files only when app-owned
      and no other row references them, after the commit), clear every cover
      that pointed at them, then add the new set
    - "keep": leave them and add only assets whose URL is new

    Items with a null source_url (added by hand) are never touched. A null
    bundle cover is set to the first new image, preferring cover/box art
    (MED-14); an existing cover is never overwritten. When the plan names a
    cover_asset_url, the game's effective display disc is pointed at that
    image in the same commit; otherwise the game cover is left alone.

    *progress* and *should_cancel* are polled between downloads and once
    more before the commit; nothing is cancellable after it.

    Raises:
        ApplyFailure: cancelled, or the chosen cover cannot be used.
        HTTPException: 404 if the game vanished, 422/502 from a download or
            path check, 409 on a conflicting concurrent write.
    """
    from backend.models.game import GameItemBundle

    try:
        game = db.get(GameItemBundle, plan.game_id)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found.")
        return _apply(game, _linked_bundle(game.id, db), plan, db, progress, should_cancel)
    finally:
        plan.release()


def _check_cancel(should_cancel: Optional[Callable[[], bool]]) -> None:
    if should_cancel is not None and should_cancel():
        raise ApplyFailure(CANCELLED_CODE, "Cancelled. Nothing was added.")


def _apply(
    game,
    bundle: Optional["MediaItemBundle"],
    plan: ApplyPlan,
    db: "Session",
    progress: Optional[ProgressFn],
    should_cancel: Optional[Callable[[], bool]],
) -> Optional["MediaItemBundle"]:
    from backend.models.media import MediaItem, MediaItemBundle, delete_links_for, make_entity_link, unique_media_slug
    from backend.service.games.cover_from_media import assign_cover_path
    from backend.service.media.file_cleanup import (
        clear_cover_references, path_keys, remove_files, removable_media_files,
    )
    from backend.service.utils.asset_fetch import commit_temp_image, fetch_image_to_temp, final_image_path
    from backend.service.utils.upload_utils import begin_upload

    deadline = time.monotonic() + ACCEPT_ALL_TIME_BUDGET_SECONDS
    fetched_before = _fetched_items(bundle)
    replaced = fetched_before if plan.previous_assets == "replace" else []
    seen_urls = {i.source_url for i in fetched_before} if plan.previous_assets == "keep" else set()
    to_fetch: list["MetadataAsset"] = []
    for asset in plan.assets:
        if asset.url in seen_urls:
            continue
        seen_urls.add(asset.url)
        to_fetch.append(asset)
    if not to_fetch and not replaced and not plan.cover_asset_url:
        return bundle

    total = len(to_fetch)
    if progress:
        progress(0, total, None)
    staging_root = asset_staging_root()
    staging_root.mkdir(parents=True, exist_ok=True)
    apply_dir = Path(tempfile.mkdtemp(prefix="apply-", dir=staging_root))
    created_files: list[Path] = []
    created_dir: Optional[Path] = None
    old_files: list[str] = []
    try:
        fetched = []
        for index, asset in enumerate(to_fetch):
            _check_cancel(should_cancel)
            if progress:
                progress(index, total, f"{asset.type} ({index + 1} of {total})")
            fetched.append((asset, *fetch_image_to_temp(asset.url, apply_dir, deadline=deadline)))
        if progress:
            progress(total, total, None)

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
            created_dir, _ = begin_upload(plan.root, game.title)
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

        if plan.cover_asset_url:
            replaced_ids = {i.id for i in replaced}
            kept = [i for i in fetched_before if i.id not in replaced_ids]
            chosen = next((i for i in [*new_items, *kept] if i.source_url == plan.cover_asset_url), None)
            if chosen is None:
                raise ApplyFailure("cover_rejected", "The chosen cover image was not part of this apply.")
            try:
                assign_cover_path(game, chosen.file_path)
            except HTTPException as exc:
                raise ApplyFailure("cover_rejected", str(exc.detail)) from None

        db.flush()
        if is_new_bundle:
            db.add(make_entity_link("game_item_bundle", game.id, "media_item_bundle", bundle.id))
        _check_cancel(should_cancel)
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
