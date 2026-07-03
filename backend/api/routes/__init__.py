from backend.api.routes import (
    auth, bios, drives, emulators, filesystem, health, jobs, launches,
    library_items, library_metadata, library_sets,
    media, platforms, profiles, settings, tags, uploads, users,
)

ROUTERS = [
    auth.router,
    users.router,
    health.router,
    settings.router,
    emulators.router,
    bios.router,
    profiles.router,
    drives.router,
    # library_metadata and library_sets must precede library_items — Starlette
    # uses first-match-wins and library_items registers a /{item_id} wildcard
    # that would otherwise shadow static paths like /metadata-search and /sets.
    library_metadata.router,
    library_sets.router,
    library_items.router,
    uploads.router,
    jobs.router,
    launches.router,
    platforms.router,
    filesystem.router,
    media.router,
    tags.router,
]
