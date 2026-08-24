"""Tests for backend.api.middleware.security: SecurityMiddleware and CSRFMiddleware.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# ASGI wrapper that overrides scope["client"] so tests can simulate arbitrary
# client IPs without forking a real socket. Must wrap the fully-built app
# (after middleware is added) so the injected host is visible to SecurityMiddleware.
# ---------------------------------------------------------------------------

def _with_client_ip(app, host: str):
    """Return a lightweight ASGI wrapper that spoofs the client host."""

    async def _wrapper(scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            scope = {**scope, "client": (host, 50000)}
        await app(scope, receive, send)

    return _wrapper


def _make_app():
    """Minimal FastAPI app with both security middlewares registered."""
    from backend.api.middleware.security import SecurityMiddleware, CSRFMiddleware

    app = FastAPI()

    @app.get("/api/v1/ping")
    def ping():
        return {"ok": True}

    @app.post("/api/v1/library/items")
    def create_item():
        return {"created": True}

    @app.post("/api/v1/auth/login")
    def login():
        return {"token": "xyz"}

    app.add_middleware(SecurityMiddleware)
    app.add_middleware(CSRFMiddleware)
    return app


# ---------------------------------------------------------------------------
# SecurityMiddleware, localhost gate
# ---------------------------------------------------------------------------


class TestSecurityMiddlewareLocalhostGate:
    def test_localhost_127_is_allowed(self):
        app = _make_app()
        client = TestClient(_with_client_ip(app, "127.0.0.1"), raise_server_exceptions=False)
        resp = client.get("/api/v1/ping")
        assert resp.status_code == 200

    def test_localhost_ipv6_loopback_is_allowed(self):
        app = _make_app()
        client = TestClient(_with_client_ip(app, "::1"), raise_server_exceptions=False)
        resp = client.get("/api/v1/ping")
        assert resp.status_code == 200

    def test_localhost_hostname_is_allowed(self):
        app = _make_app()
        client = TestClient(_with_client_ip(app, "localhost"), raise_server_exceptions=False)
        resp = client.get("/api/v1/ping")
        assert resp.status_code == 200

    def test_remote_ip_is_blocked_when_network_access_disabled(self, monkeypatch):
        import backend.core.settings as settings_mod

        class _FakeSettings:
            def get(self, key, default=None):
                if key == "ALLOW_NETWORK_ACCESS":
                    return False
                return default

        monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings())

        app = _make_app()
        client = TestClient(_with_client_ip(app, "192.168.1.100"), raise_server_exceptions=False)
        resp = client.get("/api/v1/ping")
        assert resp.status_code == 403

    def test_remote_ip_allowed_when_network_access_enabled(self, monkeypatch):
        import backend.core.settings as settings_mod

        class _FakeSettings:
            def get(self, key, default=None):
                if key == "ALLOW_NETWORK_ACCESS":
                    return True
                return default

        monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings())

        app = _make_app()
        client = TestClient(_with_client_ip(app, "10.0.0.5"), raise_server_exceptions=False)
        resp = client.get("/api/v1/ping")
        assert resp.status_code == 200

    def test_options_request_skips_gate(self):
        app = _make_app()
        # "testclient" is not a localhost origin; OPTIONS must still pass.
        client = TestClient(_with_client_ip(app, "10.0.0.5"), raise_server_exceptions=False)
        resp = client.options("/api/v1/ping")
        assert resp.status_code != 403

    def test_x_request_id_is_echoed_when_supplied(self):
        app = _make_app()
        client = TestClient(_with_client_ip(app, "127.0.0.1"), raise_server_exceptions=False)
        resp = client.get("/api/v1/ping", headers={"X-Request-ID": "test-id-123"})
        assert resp.headers.get("x-request-id") == "test-id-123"

    def test_x_request_id_is_generated_when_absent(self):
        app = _make_app()
        client = TestClient(_with_client_ip(app, "127.0.0.1"), raise_server_exceptions=False)
        resp = client.get("/api/v1/ping")
        assert "x-request-id" in resp.headers
        assert resp.headers["x-request-id"]  # non-empty UUID


# ---------------------------------------------------------------------------
# CSRFMiddleware, double-submit cookie protection
# ---------------------------------------------------------------------------


class TestCSRFMiddleware:
    """All tests use a localhost client so SecurityMiddleware passes through."""

    def _client(self):
        app = _make_app()
        return TestClient(_with_client_ip(app, "127.0.0.1"), raise_server_exceptions=False)

    def test_get_request_skips_csrf_check(self):
        resp = self._client().get("/api/v1/ping")
        assert resp.status_code == 200

    def test_auth_endpoint_is_exempt(self):
        # No session cookie, no CSRF token, auth path must pass through.
        resp = self._client().post("/api/v1/auth/login")
        assert resp.status_code == 200

    def test_state_mutating_without_session_cookie_passes_to_auth(self):
        # No peach_token → CSRFMiddleware skips the check so the auth
        # dependency (or the endpoint itself) returns the canonical response.
        resp = self._client().post("/api/v1/library/items")
        # The endpoint itself would return 200 if CSRF check was skipped.
        assert resp.status_code != 403

    def test_csrf_cookie_matches_header_is_allowed(self):
        resp = self._client().post(
            "/api/v1/library/items",
            cookies={"peach_token": "1.sometoken", "peach_csrf": "abc123"},
            headers={"X-CSRF-Token": "abc123"},
        )
        assert resp.status_code != 403

    def test_csrf_cookie_mismatch_header_is_rejected(self):
        resp = self._client().post(
            "/api/v1/library/items",
            cookies={"peach_token": "1.sometoken", "peach_csrf": "abc123"},
            headers={"X-CSRF-Token": "WRONG"},
        )
        assert resp.status_code == 403

    def test_csrf_cookie_present_but_header_absent_is_rejected(self):
        resp = self._client().post(
            "/api/v1/library/items",
            cookies={"peach_token": "1.sometoken", "peach_csrf": "abc123"},
        )
        assert resp.status_code == 403

    def test_empty_csrf_cookie_with_session_is_rejected(self):
        resp = self._client().post(
            "/api/v1/library/items",
            cookies={"peach_token": "1.sometoken", "peach_csrf": ""},
            headers={"X-CSRF-Token": ""},
        )
        assert resp.status_code == 403

    def test_options_request_skips_csrf_check(self):
        # OPTIONS must never be blocked by CSRF.
        resp = self._client().options("/api/v1/library/items")
        assert resp.status_code != 403
