from backend.api.routes import (
    auth, bios, drives, emulators, environments, filesystem, health, jobs, launches,
    media, profiles, rom_packs, settings, software_collections, software_items, software_metadata,
    tags, uploads, users,
)

ROUTERS = [
    auth.router,
    users.router,
    health.router,
    settings.router,
    emulators.router,
    rom_packs.router,
    bios.router,
    profiles.router,
    drives.router,
    # software_metadata precedes the collection/item routers. The collection,
    # item, and /software list routers use distinct top-level path segments
    # (/softwarecollection, /softwareitem, /software) so no wildcard shadows another.
    software_metadata.router,
    software_collections.router,
    software_items.router,
    uploads.router,
    jobs.router,
    launches.router,
    environments.router,
    filesystem.router,
    media.router,
    tags.router,
]
