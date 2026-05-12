from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from backend.api.middleware.security import FirstRunGuardMiddleware, SecurityMiddleware, configure_cors
from backend.api.routes import auth, emulators, health, launches, library, platforms, profiles, settings
from backend.core.lifespan import lifespan
from backend.core.settings import init_settings
from backend.service.utils.settings import get_or_generate_session_secret

init_settings()
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
app.include_router(health.router)
app.include_router(settings.router)
app.include_router(emulators.router)
app.include_router(profiles.router)
app.include_router(library.router)
app.include_router(launches.router)
app.include_router(platforms.router)

# app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
