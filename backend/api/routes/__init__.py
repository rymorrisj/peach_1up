from backend.api.routes import (
    auth, bios, drives, emulators, filesystem, health, jobs, launches,
    library, media, platforms, profiles, settings, tags, uploads, users,
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
    library.router,
    uploads.router,
    jobs.router,
    launches.router,
    platforms.router,
    filesystem.router,
    media.router,
    tags.router,
]
