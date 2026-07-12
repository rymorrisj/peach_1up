from backend.api.routes import (
    apps, auth, bios, controllers, drives, emulators, environments, filesystem, health, jobs, launches,
    media, profiles, rom_packs, settings, game_item_bundles, game_items, game_metadata,
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
    controllers.router,
    # game_metadata precedes the bundle/item routers. The bundle, item, and
    # /game-items list routers use distinct top-level path segments
    # (/game-item-bundle, /game-item, /game-items) so no wildcard shadows another.
    game_metadata.router,
    game_item_bundles.router,
    game_items.router,
    apps.router,
    uploads.router,
    jobs.router,
    launches.router,
    environments.router,
    filesystem.router,
    media.router,
    tags.router,
]
