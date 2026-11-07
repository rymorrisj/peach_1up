"""Route-level tests for GET /media/{file_path} in backend/main.py.

backend.main calls init_settings() at import, which would open the real
settings DB. The fixture pre-seeds settings state and marks it initialised so
that call is a no-op, and get_db is overridden with an in-memory session. The
lifespan never runs because TestClient is not used as a context manager.
"""

import pytest


def _with_client_ip(app, host: str):
    async def _wrapper(scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            scope = {**scope, "client": (host, 50000)}
        await app(scope, receive, send)

    return _wrapper


@pytest.fixture
def media_client(tmp_path, monkeypatch):
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine
    from fastapi.testclient import TestClient

    import backend.core.settings as core_settings
    import backend.service.utils.settings as settings_state
    import backend.models  # noqa: F401, registers all table models with SQLModel.metadata

    library_root = tmp_path / "library"
    library_root.mkdir()
    (library_root / "cover.png").write_bytes(b"png-bytes")
    (tmp_path / "outside.txt").write_text("secret")

    monkeypatch.setattr(core_settings, "_initialised", True)
    monkeypatch.setattr(
        settings_state,
        "_state",
        {"LIBRARY_PATH": str(library_root), "ALLOW_NETWORK_ACCESS": False, "_env": {}},
    )

    from backend.core.database import get_db
    from backend.main import app

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        app.dependency_overrides[get_db] = lambda: session
        try:
            yield TestClient(_with_client_ip(app, "127.0.0.1")), session
        finally:
            app.dependency_overrides.pop(get_db, None)


def _logged_in_cookie(db) -> str:
    from backend.core.identity import issue_session
    from backend.models.user import UserItem

    user = UserItem(name="Viewer", is_owner=False, is_admin=False)
    db.add(user)
    db.commit()
    db.refresh(user)
    token, _ = issue_session(db, user)
    return f"peach_token={user.id}.{token}"


class TestMediaRouteAuth:
    def test_no_session_is_401(self, media_client):
        client, _ = media_client

        resp = client.get("/media/cover.png")

        assert resp.status_code == 401, resp.text

    def test_malformed_cookie_is_401(self, media_client):
        client, _ = media_client

        resp = client.get("/media/cover.png", headers={"Cookie": "peach_token=not-a-session"})

        assert resp.status_code == 401, resp.text

    def test_stale_token_is_401(self, media_client):
        client, db = media_client
        cookie = _logged_in_cookie(db)
        user_id = cookie.split("=", 1)[1].split(".", 1)[0]

        resp = client.get("/media/cover.png", headers={"Cookie": f"peach_token={user_id}.wrong"})

        assert resp.status_code == 401, resp.text

    def test_valid_session_serves_file(self, media_client):
        client, db = media_client

        resp = client.get("/media/cover.png", headers={"Cookie": _logged_in_cookie(db)})

        assert resp.status_code == 200, resp.text
        assert resp.content == b"png-bytes"

    def test_valid_session_missing_file_is_404(self, media_client):
        client, db = media_client

        resp = client.get("/media/absent.png", headers={"Cookie": _logged_in_cookie(db)})

        assert resp.status_code == 404

    def test_valid_session_traversal_is_404(self, media_client):
        client, db = media_client

        resp = client.get("/media/..%2Foutside.txt", headers={"Cookie": _logged_in_cookie(db)})

        assert resp.status_code == 404
