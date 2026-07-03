from backend.api.routes import (
    auth, bios, drives, emulators, filesystem, health, jobs, launches,
    library_collections, library_metadata, libraryitems,
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
    # library_metadata precedes the collection/item routers. The collection,
    # item, and /library list routers use distinct top-level path segments
    # (/librarycollection, /libraryitem, /library) so no wildcard shadows another.
    library_metadata.router,
    library_collections.router,
    libraryitems.router,
    uploads.router,
    jobs.router,
    launches.router,
    platforms.router,
    filesystem.router,
    media.router,
    tags.router,
]
