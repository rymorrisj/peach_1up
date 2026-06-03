import json
import os
import uuid

from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

_LOCALHOST_ORIGINS = {"127.0.0.1", "::1", "localhost"}


def _apply_cors_headers(response: Response, request: Request) -> None:
    """Inject CORS headers into a bare middleware response.

    BaseHTTPMiddleware short-circuits (return without call_next) bypass the
    outer CORSMiddleware's send-wrapper in some Starlette versions, leaving
    preflight-passing origins without the required headers on the follow-up
    request. This helper guarantees headers are present regardless of version.
    setdefault is used so that if CORSMiddleware already injected them, we
    do not duplicate.
    """
    origin = request.headers.get("origin", "")
    if origin and origin in get_cors_origins():
        response.headers.setdefault("access-control-allow-origin", origin)
        response.headers.setdefault("access-control-allow-credentials", "true")
        response.headers.setdefault("vary", "Origin")

class SecurityMiddleware(BaseHTTPMiddleware):
    """Enforce localhost binding and inject request correlation IDs."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        # Bind address enforcement — reject non-localhost clients unless network access is enabled
        try:
            from backend.core.settings import get_settings
            svc = get_settings()
            allow_network = svc.get("ALLOW_NETWORK_ACCESS", False)
        except RuntimeError:
            allow_network = False

        client_host = request.client.host if request.client else "unknown"
        is_local = client_host in _LOCALHOST_ORIGINS
        if not allow_network and not is_local:
            resp = Response(content="Remote access is disabled.", status_code=403)
            _apply_cors_headers(resp, request)
            return resp

        response = await call_next(request)

        # Preserve client-supplied correlation ID; generate one if absent
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response.headers["X-Request-ID"] = request_id
        return response


_first_run_done_cache: bool = False

_FIRST_RUN_EXEMPT_PATHS: frozenset[str] = frozenset({
    "/api/v1/health",
    "/api/v1/settings/first-run-status",
    "/api/v1/settings/emulator-path",
    "/api/v1/settings/library-path",
    "/api/v1/settings/complete-first-run",
    "/api/v1/auth/me",
    "/api/v1/auth/switch",
    "/api/v1/auth/logout",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
})


def invalidate_first_run_cache() -> None:
    global _first_run_done_cache
    _first_run_done_cache = False


class FirstRunGuardMiddleware(BaseHTTPMiddleware):
    """Redirect non-wizard requests to /first-run when setup is incomplete."""

    async def dispatch(self, request: Request, call_next) -> Response:
        global _first_run_done_cache

        if request.method == "OPTIONS":
            return await call_next(request)

        if _first_run_done_cache:
            return await call_next(request)

        first_run_done = False
        try:
            from backend.core.settings import get_settings
            svc = get_settings()
            first_run_done = not svc.is_first_run()
        except RuntimeError:
            pass

        if first_run_done:
            _first_run_done_cache = True
            return await call_next(request)

        path = request.url.path
        excluded = path.startswith("/api/") or path.startswith("/assets/")
        is_first_run_page = path == "/first-run" or path.startswith("/first-run")
        has_extension = "." in path.rsplit("/", 1)[-1]

        if not excluded and not is_first_run_page and not has_extension:
            return RedirectResponse("/first-run")

        return await call_next(request)


def get_cors_origins() -> list[str]:
    # init_settings() in main.py calls load_dotenv() before configure_cors(),
    # so os.getenv reflects .env values at this point.
    # CORS_ORIGIN adds an explicit override; the localhost default is always included.
    origins = ["http://localhost:5173"]
    extra = os.getenv("CORS_ORIGIN", "")
    if extra:
        origins.append(extra)
    return origins


def configure_cors(app) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
