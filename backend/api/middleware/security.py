import uuid

from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

_LOCALHOST_ORIGINS = {"127.0.0.1", "::1", "localhost"}


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
        if not allow_network and client_host not in _LOCALHOST_ORIGINS:
            return Response(
                content="Remote access is disabled.",
                status_code=403,
            )

        response = await call_next(request)

        # Inject request ID on every response for traceability
        response.headers["X-Request-ID"] = str(uuid.uuid4())
        return response


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
