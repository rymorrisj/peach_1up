import sys
from pathlib import Path

from backend.core.settings import init_settings
init_settings()

from backend.core.logger import get_logger

logger = get_logger(__name__)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware


def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parent.parent / relative

from backend.api.middleware.security import FirstRunGuardMiddleware, SecurityMiddleware, configure_cors
from backend.api.routes import auth, bios, drives, emulators, filesystem, health, launches, library, media, platforms, profiles, settings, users
from backend.core.lifespan import lifespan
from backend.service.utils.settings import get_or_generate_session_secret
_session_secret = get_or_generate_session_secret()

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
# Execution order: CORS → Security → FirstRunGuard → Session → router
app.add_middleware(SessionMiddleware, secret_key=_session_secret, https_only=False)
app.add_middleware(FirstRunGuardMiddleware)
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

frontend_dist = resource_path("frontend/dist")
logger.debug("[PEACH] frozen=%s", getattr(sys, 'frozen', False))
logger.debug("[PEACH] _MEIPASS=%s", getattr(sys, '_MEIPASS', 'N/A'))
logger.debug("[PEACH] frontend_dist=%s", frontend_dist)
logger.debug("[PEACH] exists=%s", frontend_dist.exists())

from fastapi.responses import FileResponse

@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    asset = frontend_dist / full_path
    if asset.exists() and asset.is_file():
        return FileResponse(str(asset))
    index = frontend_dist / "index.html"
    return FileResponse(str(index))