from fastapi import FastAPI

from backend.api.middleware.security import SecurityMiddleware, configure_cors
from backend.api.routes import emulators, health, launches, library, platforms, profiles, settings, user_profiles
from backend.core.lifespan import lifespan

app = FastAPI(
    title="Peach 1UP",
    description="Preservation automation — REST API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

configure_cors(app)
app.add_middleware(SecurityMiddleware)

app.include_router(health.router)
app.include_router(settings.router)
app.include_router(emulators.router)
app.include_router(profiles.router)
app.include_router(library.router)
app.include_router(launches.router)
app.include_router(platforms.router)
app.include_router(user_profiles.router)

# app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
