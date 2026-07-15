import sys
from pathlib import Path

from backend.core.settings import init_settings
init_settings()

from backend.core.logger import get_logger

logger = get_logger(__name__)

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.requests import Request
from fastapi.staticfiles import StaticFiles


def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parent.parent / relative

from backend.api.middleware.security import CSRFMiddleware, FirstRunGuardMiddleware, SecurityMiddleware, _DOCS_HOST, _LOCALHOST_ORIGINS, configure_cors
from backend.api.middleware.request_logging import RequestLoggingMiddleware
from backend.api.routes import ROUTERS
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
# Execution order: RequestLogging → CORS → Security → CSRF → FirstRunGuard → router
app.add_middleware(FirstRunGuardMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityMiddleware)
configure_cors(app)
app.add_middleware(RequestLoggingMiddleware)

for _router in ROUTERS:
    app.include_router(_router)

from backend.service.utils.path_utils import normalise_path


@app.get("/media/{file_path:path}", include_in_schema=False)
async def serve_media(file_path: str, request: Request):
    from backend.core.settings import get_settings
    svc = get_settings()
    allow_network = svc.get("ALLOW_NETWORK_ACCESS", False)
    client_host = request.client.host if request.client else "unknown"
    if client_host not in _LOCALHOST_ORIGINS and not allow_network:
        return Response(status_code=403, content="Remote access is disabled.")
    # Read LIBRARY_PATH fresh on every request rather than caching it at import
    # time: it can change at runtime (e.g. the first-run wizard or Settings
    # page call POST /api/v1/settings/library-path with no server restart),
    # and a stale cached root here would 404 every request even though
    # cover_art_url (computed fresh per-read in models/game.py) points at the
    # new, correct location.
    library_root = Path(svc.get("LIBRARY_PATH")).resolve()
    try:
        resolved = normalise_path(str(library_root / file_path))
    except ValueError:
        return Response(status_code=404)
    if not resolved.is_relative_to(library_root) or not resolved.exists():
        return Response(status_code=404)
    return FileResponse(resolved)

frontend_dist = resource_path("frontend/dist")
logger.debug("[PEACH] frozen=%s", getattr(sys, 'frozen', False))
logger.debug("[PEACH] _MEIPASS=%s", getattr(sys, '_MEIPASS', 'N/A'))
logger.debug("[PEACH] frontend_dist=%s", frontend_dist)
logger.debug("[PEACH] exists=%s", frontend_dist.exists())

# Starlette's router dispatches to the first route whose .matches() returns a
# FULL match (see starlette.routing.Router.app), in registration order. Host
# routes match FULL on any path once the hostname matches, so this app.host()
# call must be registered before the "/{full_path:path}" catch-all below —
# otherwise the catch-all (registered first) would win and the docs sub-app
# would never be reached. Verified empirically with TestClient.
docs_dist = resource_path("docs/build")
app.host(_DOCS_HOST, app=StaticFiles(directory=str(docs_dist), html=True, check_dir=False))

@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    asset = frontend_dist / full_path
    if asset.exists() and asset.is_file():
        return FileResponse(str(asset))
    index = frontend_dist / "index.html"
    return FileResponse(str(index))