import sys
from pathlib import Path

from backend.core.settings import init_settings
init_settings()

from backend.core.logger import get_logger

logger = get_logger(__name__)

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.requests import Request


def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parent.parent / relative

from backend.api.middleware.security import CSRFMiddleware, FirstRunGuardMiddleware, SecurityMiddleware, _LOCALHOST_ORIGINS, configure_cors
from backend.api.routes import auth, bios, drives, emulators, filesystem, health, launches, library, media, platforms, profiles, settings, tags, users
from backend.core.lifespan import lifespan

app = FastAPI(
    title="Peach 1UP",
    description="Preservation automation — REST API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    redirect_slashes=False,
)

# Middleware is applied in LIFO order (last-added = outermost = first to run).
# Execution order: CORS → Security → CSRF → FirstRunGuard → router
app.add_middleware(FirstRunGuardMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityMiddleware)
configure_cors(app)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(drives.router)
app.include_router(health.router)
app.include_router(settings.router)
app.include_router(emulators.router)
app.include_router(bios.router)
app.include_router(profiles.router)
app.include_router(library.router)
app.include_router(launches.router)
app.include_router(platforms.router)
app.include_router(filesystem.router)
app.include_router(media.router)
app.include_router(tags.router)

from backend.service.utils import settings as _peach_settings
from backend.service.utils.path_utils import normalise_path

_library_root = Path(_peach_settings.get("LIBRARY_PATH")).resolve()


@app.get("/media/{file_path:path}", include_in_schema=False)
async def serve_media(file_path: str, request: Request):
    from backend.core.settings import get_settings
    svc = get_settings()
    allow_network = svc.get("ALLOW_NETWORK_ACCESS", False)
    client_host = request.client.host if request.client else "unknown"
    if client_host not in _LOCALHOST_ORIGINS and not allow_network:
        return Response(status_code=403, content="Remote access is disabled.")
    try:
        resolved = normalise_path(str(_library_root / file_path))
    except ValueError:
        return Response(status_code=404)
    if not resolved.is_relative_to(_library_root) or not resolved.exists():
        return Response(status_code=404)
    return FileResponse(resolved)

frontend_dist = resource_path("frontend/dist")
logger.debug("[PEACH] frozen=%s", getattr(sys, 'frozen', False))
logger.debug("[PEACH] _MEIPASS=%s", getattr(sys, '_MEIPASS', 'N/A'))
logger.debug("[PEACH] frontend_dist=%s", frontend_dist)
logger.debug("[PEACH] exists=%s", frontend_dist.exists())

@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    asset = frontend_dist / full_path
    if asset.exists() and asset.is_file():
        return FileResponse(str(asset))
    index = frontend_dist / "index.html"
    return FileResponse(str(index))