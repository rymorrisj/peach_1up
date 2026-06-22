"""Route-level tests for POST /api/v1/bios/{slug}/place.

bios_requirements.toml is loaded once at import time via a module-level cached
path, so route tests can't redirect it to a tmp_path by patching get_base_path
alone — instead load_bios_requirements is patched directly to return a single
fixed entry, and get_base_path is patched (in both bios.py and
emulator_catalog.py, since check_bios_presence calls it independently) so the
configured bios_path resolves under tmp_path.
"""

import pytest


def _owner_user():
    from backend.models.user import User
    return User(id=1, name="Owner", is_owner=True)


def _non_admin_user():
    from backend.models.user import User
    return User(id=2, name="Guest", is_owner=False, is_admin=False)


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import bios
    from backend.core.dependencies import get_active_user
    from backend.service.utils import emulator_catalog

    fake_entry = {
        "slug": "ps1-bios",
        "name": "PS1 BIOS",
        "platform": "ps1",
        "bios_path": "test-bios",
        "guidance_text": "Place your BIOS.",
        "guidance_url": "https://example.invalid",
        "required": True,
    }
    monkeypatch.setattr(bios, "load_bios_requirements", lambda: [fake_entry])
    monkeypatch.setattr(bios, "get_base_path", lambda: tmp_path)
    monkeypatch.setattr(emulator_catalog, "get_base_path", lambda: tmp_path)

    app = FastAPI()
    app.include_router(bios.router)
    app.dependency_overrides[get_active_user] = _owner_user

    with TestClient(app) as c:
        yield c, tmp_path


class TestPlaceRoute:
    def test_unknown_slug_is_404(self, client):
        c, _ = client
        resp = c.post("/api/v1/bios/not-a-slug/place", data={"source_path": "/tmp"})
        assert resp.status_code == 404

    def test_neither_source_nor_files_is_400(self, client):
        c, _ = client
        resp = c.post("/api/v1/bios/ps1-bios/place")
        assert resp.status_code == 400
        assert "Provide either" in resp.json()["detail"]

    def test_both_source_and_files_is_400(self, client):
        c, tmp_path = client
        src = tmp_path / "scph1001.bin"
        src.write_bytes(b"x")
        resp = c.post(
            "/api/v1/bios/ps1-bios/place",
            data={"source_path": str(src)},
            files={"files": ("scph1001.bin", b"x", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "not both" in resp.json()["detail"]

    def test_successful_placement_via_source_path_updates_presence(self, client):
        c, tmp_path = client
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "scph1001.bin").write_bytes(b"bios-bytes")

        resp = c.post("/api/v1/bios/ps1-bios/place", data={"source_path": str(src_dir)})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["slug"] == "ps1-bios"
        assert body["is_present"] is True
        assert body["copied"] == ["scph1001.bin"]
        assert (tmp_path / "test-bios" / "scph1001.bin").read_bytes() == b"bios-bytes"

    def test_successful_placement_via_file_upload(self, client):
        c, tmp_path = client
        resp = c.post(
            "/api/v1/bios/ps1-bios/place",
            files={"files": ("scph1001.bin", b"uploaded-bytes", "application/octet-stream")},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["copied"] == ["scph1001.bin"]
        assert (tmp_path / "test-bios" / "scph1001.bin").read_bytes() == b"uploaded-bytes"

    def test_rejected_placement_is_400_with_message(self, client):
        c, tmp_path = client
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "readme.txt").write_text("not a bios")

        resp = c.post("/api/v1/bios/ps1-bios/place", data={"source_path": str(src_dir)})

        assert resp.status_code == 400
        assert "No PS1 BIOS" in resp.json()["detail"]

    def test_nonexistent_source_path_is_400(self, client):
        c, tmp_path = client
        resp = c.post("/api/v1/bios/ps1-bios/place", data={"source_path": str(tmp_path / "missing")})
        assert resp.status_code == 400

    def test_requires_admin_permission(self, client):
        c, tmp_path = client
        from backend.core.dependencies import get_active_user
        c.app.dependency_overrides[get_active_user] = _non_admin_user
        src = tmp_path / "scph1001.bin"
        src.write_bytes(b"x")
        resp = c.post("/api/v1/bios/ps1-bios/place", data={"source_path": str(src)})
        assert resp.status_code == 403


class TestListRouteIncludesRequiredField:
    def test_get_bios_includes_required_flag(self, client):
        c, _ = client
        resp = c.get("/api/v1/bios")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["slug"] == "ps1-bios"
        assert body[0]["required"] is True
