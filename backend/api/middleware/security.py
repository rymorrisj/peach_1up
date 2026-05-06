import ipaddress
import json
import uuid

from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

_LOCALHOST_ORIGINS = {"127.0.0.1", "::1", "localhost"}

# RFC-1918 private ranges used by Docker bridge networks (172.16.0.0/12 covers 172.16–172.31)
_DOCKER_BRIDGE_NETWORKS = [
    ipaddress.ip_network("172.16.0.0/12"),
]


def _is_docker_bridge(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _DOCKER_BRIDGE_NETWORKS)
    except ValueError:
        return False


class SecurityMiddleware(BaseHTTPMiddleware):
    """Strip Authorization headers from logs and enforce localhost binding."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Bind address enforcement — reject non-localhost clients unless network access is enabled
        try:
            from backend.core.settings import get_settings
            svc = get_settings()
            allow_network = svc.get("ALLOW_NETWORK_ACCESS", False)
        except RuntimeError:
            allow_network = False

        client_host = request.client.host if request.client else "unknown"
        is_local = client_host in _LOCALHOST_ORIGINS or _is_docker_bridge(client_host)
        if not allow_network and not is_local:
            return Response(
                content="Remote access is disabled.",
                status_code=403,
            )

        response = await call_next(request)

        # Inject request ID on every response for traceability
        response.headers["X-Request-ID"] = str(uuid.uuid4())
        return response


_first_run_done_cache: bool = False

_FIRST_RUN_EXEMPT_PATHS: frozenset[str] = frozenset({
    "/api/v1/health",
    "/api/v1/settings/first-run-status",
    "/api/v1/settings/emulator-path",
    "/api/v1/settings/library-path",
    "/api/v1/settings/complete-first-run",
    "/api/v1/profiles/users/owner",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
})


class FirstRunGuardMiddleware(BaseHTTPMiddleware):
    """Redirect non-wizard requests to /first-run when setup is incomplete."""

    async def dispatch(self, request: Request, call_next) -> Response:
        global _first_run_done_cache

        if _first_run_done_cache or request.url.path in _FIRST_RUN_EXEMPT_PATHS:
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

        return Response(
            content=json.dumps({"redirect": "/first-run"}),
            status_code=302,
            media_type="application/json",
            headers={"Location": "/first-run"},
        )


def get_cors_origins() -> list[str]:
    try:
        from backend.core.settings import get_settings
        svc = get_settings()
        origin = svc.get("CORS_ORIGIN", "http://localhost:5173")
        return [origin] if origin else ["http://localhost:5173"]
    except RuntimeError:
        return ["http://localhost:5173"]


def configure_cors(app) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
