import shutil
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select as _select
from sqlalchemy.orm import Session

from backend.models.app import (
    AppItemBundle, AppItemBundleCreate, AppItemBundleUpdate, AppItem, AppItemUpdate, derive_is_pc,
)
from backend.models.environment import EnvironmentItem
from backend.service.utils.confirmation_tokens import consume as _consume
from backend.service.utils.file_types import file_type_from_path
from backend.service.utils.path_utils import allowed_browse_roots, is_within_roots, normalise_path
from backend.service.utils.slug_generator import unique_slug

# Apps have no dedicated APPS_PATH setting (see dev_docs) — they share the
# same allowlisted source roots as everything else the file browser can
# point at (SOFTWARE_PATH plus the other configured library roots).
_PATH_FIELDS = {"executable_path", "cover_art_path"}
_EXISTENCE_FIELDS = {"executable_path"}
# Mirrors backend/service/games/items.py's _CONTAINMENT_FIELDS: executable_path
# is what coordinator.py prefers over media_path when building a LaunchSpec,
# so it is the one field that can steer a launch outside the permitted
# directories. Uses the same allowed_browse_roots() check create_app_item_bundle
# already applies at ingest (~line 62), not games' library_domain_root("games"),
# apps have no dedicated APPS_PATH and are intentionally allowed to point at
# any of the configured library roots or local drives, see this module's
# top-of-file comment.
_CONTAINMENT_FIELDS = {"executable_path"}


def _generate_app_slug(name: str, db: Session) -> str:
    return unique_slug(
        name,
        lambda s: db.query(AppItemBundle).filter(AppItemBundle.slug == s).first() is not None,
    )


def _enforce_environment_binding(collection: AppItemBundle) -> None:
    """Environment is strictly PC (doc 02 A5): console apps may never carry an
    environment_item_id. Mirrors backend/service/games/items.py's
    _enforce_environment_binding exactly.

    PC apps may have a null environment_item_id at this point (backfilled
    later / pre-launch-gated, same as PC Games); only the
    console+non-null combination is rejected here.
    """
    if not collection.is_pc and collection.environment_item_id is not None:
        raise HTTPException(
            status_code=422,
            detail="Console apps cannot have an environment_item_id; Environment is strictly PC.",
        )


def create_app_item_bundle(body: AppItemBundleCreate, db: Session) -> AppItemBundle:
    """Create an App collection-of-one from a single file or folder path.

    No smart-media era detection runs here (unlike Software ingest) — the
    caller supplies era explicitly. environment_item_id is validated for
    existence only when provided (required for PC apps, forbidden for
    console apps — see _enforce_environment_binding).
    """
    if body.environment_item_id is not None and not db.get(EnvironmentItem, body.environment_item_id):
        raise HTTPException(status_code=404, detail="Environment not found.")

    try:
        resolved = normalise_path(body.file_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not is_within_roots(resolved, allowed_browse_roots()):
        raise HTTPException(status_code=400, detail="Path is outside the permitted directories.")
    if not resolved.exists():
        raise HTTPException(status_code=400, detail="Path does not exist.")

    title = body.title.strip() or resolved.stem.replace("-", " ").title()
    slug = _generate_app_slug(title, db)

    is_file = resolved.is_file()
    collection = AppItemBundle(
        title=title,
        slug=slug,
        era=body.era,
        environment_item_id=body.environment_item_id,
        profile_item_id=body.profile_item_id,
    )
    _enforce_environment_binding(collection)
    db.add(collection)
    db.flush()

    leaf = AppItem(
        app_item_bundle_id=collection.id,
        file_path=str(resolved),
        executable_path=str(resolved) if is_file else None,
        folder_path=str(resolved.parent) if is_file else str(resolved),
        file_type=file_type_from_path(resolved),
        file_size_bytes=resolved.stat().st_size if is_file else None,
        original_name=resolved.name,
        # Never owned: create_app_item_bundle points at an existing path rather
        # than creating/renaming a directory for the item, so delete must
        # never rmtree it — mirrors SoftwareItem's folder_owned=False default
        # for the same "pre-existing, not ours" case.
        folder_owned=False,
    )
    db.add(leaf)
    db.flush()

    collection.launch_disk_id = leaf.id
    collection.display_disk_id = leaf.id
    db.commit()
    db.refresh(collection)
    return collection


def update_app_item_bundle(collection_id: int, body: AppItemBundleUpdate, db: Session) -> AppItemBundle:
    collection = db.get(AppItemBundle, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="App collection not found.")

    fields = body.model_dump(exclude_unset=True)
    if fields.get("environment_item_id") is not None and not db.get(EnvironmentItem, fields["environment_item_id"]):
        raise HTTPException(status_code=404, detail="Environment not found.")
    for disk_field in ("display_disk_id", "launch_disk_id"):
        if fields.get(disk_field) is not None:
            leaf_ids = set(
                db.execute(
                    _select(AppItem.id).where(AppItem.app_item_bundle_id == collection_id)
                ).scalars().all()
            )
            if fields[disk_field] not in leaf_ids:
                raise HTTPException(status_code=422, detail="Item does not belong to this collection.")
    for key, value in fields.items():
        setattr(collection, key, value)
    if "era" in fields:
        # setattr bypasses AppItemBundle._validate_is_pc (no validate_assignment)
        # — re-derive explicitly whenever era changes, mirrors
        # update_library_collection's identical re-derivation for GameItemBundle.
        collection.is_pc = derive_is_pc(collection.era)
    _enforce_environment_binding(collection)
    db.commit()
    db.refresh(collection)
    return collection


def update_app_leaf(collection_id: int, leaf_id: int, body: AppItemUpdate, db: Session) -> AppItem:
    leaf = db.get(AppItem, leaf_id)
    if not leaf or leaf.app_item_bundle_id != collection_id:
        raise HTTPException(status_code=404, detail="App item not found.")
    fields = body.model_dump(exclude_none=True)
    for key in _PATH_FIELDS & fields.keys():
        try:
            resolved = normalise_path(fields[key])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"{key}: {e}")
        if key in _EXISTENCE_FIELDS and not resolved.exists():
            raise HTTPException(status_code=400, detail=f"{key} does not exist: {resolved}")
        if key in _CONTAINMENT_FIELDS and not is_within_roots(resolved, allowed_browse_roots()):
            raise HTTPException(
                status_code=422,
                detail=f"{key} is outside the permitted directories.",
            )
        fields[key] = str(resolved)
    for key, value in fields.items():
        setattr(leaf, key, value)
    db.commit()
    db.refresh(leaf)
    return leaf


def _should_delete_media(collection: AppItemBundle) -> bool:
    if collection.delete_media_override is not None:
        return collection.delete_media_override
    from backend.core.settings import get_settings
    return bool(get_settings().get("delete_media_on_removal", False))


def _delete_leaf_media_folders(collection: AppItemBundle) -> None:
    """Delete each leaf's on-disk media. Same containment and ownership rules
    as backend/service/library/items.py's _delete_leaf_media_folders: only
    rmtree a folder_path the app itself owns (folder_owned=True); otherwise
    unlink just the tracked file. Apps have no dedicated APPS_PATH, so
    SOFTWARE_PATH is reused as the containment root here too."""
    from backend.core.logger import get_logger
    from backend.core.settings import get_settings

    log = get_logger(__name__)
    svc = get_settings()
    media_root_str = svc.get("SOFTWARE_PATH", "") or ""
    if not media_root_str:
        log.error(
            "Media deletion is enabled for app collection %s but SOFTWARE_PATH is unset; "
            "refusing to delete media folders.",
            collection.id,
        )
        return
    media_root = Path(media_root_str).resolve()

    def _under_root(path: Path) -> bool:
        return path == media_root or path.is_relative_to(media_root)

    seen_folders: set[str] = set()
    seen_files: set[str] = set()
    for leaf in collection.items:
        if leaf.folder_owned and leaf.folder_path:
            if leaf.folder_path in seen_folders:
                continue
            seen_folders.add(leaf.folder_path)
            folder = Path(leaf.folder_path).resolve()
            if not _under_root(folder):
                log.error(
                    "Refusing to delete media folder '%s' for app item %s: "
                    "it does not resolve under SOFTWARE_PATH ('%s').",
                    folder, leaf.id, media_root,
                )
                continue
            try:
                if folder.exists():
                    shutil.rmtree(folder)
                    log.info("Deleted media folder: %s", folder)
            except OSError as exc:
                log.warning("Could not delete media folder %s: %s", folder, exc)
        elif leaf.file_path:
            if leaf.file_path in seen_files:
                continue
            seen_files.add(leaf.file_path)
            file_path = Path(leaf.file_path).resolve()
            if not _under_root(file_path):
                log.error(
                    "Refusing to delete media file '%s' for app item %s: "
                    "it does not resolve under SOFTWARE_PATH ('%s').",
                    file_path, leaf.id, media_root,
                )
                continue
            try:
                if file_path.is_file():
                    file_path.unlink()
                    log.info("Deleted media file: %s", file_path)
            except OSError as exc:
                log.warning("Could not delete media file %s: %s", file_path, exc)


def delete_app_item_bundle(collection_id: int, token: str, db: Session) -> None:
    if not _consume(token, "app_item_bundle", collection_id):
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")
    collection = db.get(AppItemBundle, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="App collection not found.")

    # Remove the collection-owned drive row and its on-disk FAT16 image before
    # deleting the collection, so the image file is never orphaned (the FK
    # cascade only drops the DB row, not the file). Mirrors
    # library/items.py::delete_library_collection. No-op for collections
    # without a drive (the common case pre-DOS-era Apps).
    from backend.service.utils.drive_utils import delete_drive_for_collection
    delete_drive_for_collection(collection, db)

    if _should_delete_media(collection):
        _delete_leaf_media_folders(collection)

    # MediaLink carries no DB-level FK to app_item_bundles (a polymorphic
    # entity_id cannot FK to multiple target tables), so there is no
    # ON DELETE CASCADE for it, unlike the leaf rows below. Clean it up
    # explicitly, mirrors library/items.py::delete_library_collection.
    from backend.models.media import delete_links_for
    delete_links_for("app_item_bundle", collection_id, db)

    db.delete(collection)  # ON DELETE CASCADE removes the leaf rows
    db.commit()
