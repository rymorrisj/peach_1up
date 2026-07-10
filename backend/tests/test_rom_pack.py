"""Route-level tests for ROM pack routes (backend/api/routes/rom_packs.py).

RomPackItem routes are catalog-driven rather than pure CRUD: entries come
from load_catalog() (TOML files cached in a module-level global), and
GET/verify synthesize an unpersisted RomPackItemRead when no rom_pack_items
row exists yet. record_rom_pack_item (backend/service/utils/emulator_installer.py)
opens its own DB session via sessionmaker(bind=get_engine()) rather than
using the request-injected session, so get_engine() must be monkeypatched
to the test's in-memory engine for verify-endpoint writes to land where the
test can see them.

rom_packs.py imports get_emulator/get_install_path/load_catalog by name
(`from backend.service.utils.emulator_catalog import ...`) rather than
referencing the emulator_catalog module, so monkeypatching
emulator_catalog.load_catalog (as other route tests do) would not affect
rom_packs.py's own bound names. Patches below target the names as bound
on the rom_packs module itself.
"""

import pytest


def _owner_user():
    from backend.models.user import User
    return User(id=1, name="Owner", is_owner=True)


def _no_permission_user():
    from backend.models.user import User
    return User(id=2, name="Guest", is_owner=False, is_admin=False)


@pytest.fixture
def mem_db_session():
    from sqlmodel import SQLModel, Session, create_engine
    from sqlalchemy.pool import StaticPool
    import backend.models  # noqa: F401 — registers all table models with SQLModel.metadata

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session, engine


@pytest.fixture
def client(mem_db_session, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import rom_packs
    from backend.core import database as database_module
    from backend.core.database import get_db
    from backend.core.dependencies import get_active_user

    db, engine = mem_db_session

    # record_rom_pack_item() builds its own session via
    # sessionmaker(bind=get_engine()) instead of reusing the request's
    # injected session, so get_engine must point at the same in-memory
    # engine or its writes land in a different (throwaway) database.
    monkeypatch.setattr(database_module, "get_engine", lambda: engine)

    app = FastAPI()
    app.include_router(rom_packs.router)
    app.dependency_overrides[get_active_user] = _owner_user
    app.dependency_overrides[get_db] = lambda: db

    with TestClient(app) as c:
        yield c, db


ROM_PACK_ENTRY = {
    "slug": "mame-roms",
    "name": "MAME ROM Set",
    "install_type": "rom_pack",
    "source_url": "https://example.com/mame-roms.git",
}

EMULATOR_ENTRY_WITH_DEP = {
    "slug": "mame",
    "name": "MAME",
    "install_type": "zip",
    "dependencies": [{"name": "mame-roms"}],
}

NON_ROM_PACK_ENTRY = {
    "slug": "duckstation",
    "name": "DuckStation",
    "install_type": "zip",
}


def _set_catalog(monkeypatch, entries):
    """Patch load_catalog/get_emulator everywhere the route (and the code
    it calls into) can reach them.

    rom_packs.py imported get_emulator/load_catalog by name, so patching
    only emulator_catalog's module attributes (as other route tests do)
    would not reach rom_packs.py's own already-bound references — those
    are patched directly on the rom_packs module. Separately,
    record_rom_pack_item (backend/service/utils/emulator_installer.py,
    invoked by the verify endpoint) does its own `from ...emulator_catalog
    import get_emulator`, which internally calls load_catalog() resolved
    through emulator_catalog's own globals — so emulator_catalog.load_catalog
    is patched too, keeping that path off the real on-disk TOML catalog.
    """
    from backend.api.routes import rom_packs
    from backend.service.utils import emulator_catalog

    def _get_emulator(slug):
        for entry in entries:
            if entry["slug"] == slug:
                return entry
        raise ValueError(f"Unknown emulator slug: {slug!r}")

    monkeypatch.setattr(rom_packs, "load_catalog", lambda: entries)
    monkeypatch.setattr(rom_packs, "get_emulator", _get_emulator)
    monkeypatch.setattr(emulator_catalog, "load_catalog", lambda: entries)


def _make_rom_pack_item(db, **overrides):
    from backend.models.rom_pack import RomPackItem

    kwargs = dict(
        slug="mame-roms",
        name="MAME ROM Set",
        emulator_slug="mame",
        install_path="/roms/mame",
        source_url="https://example.com/mame-roms.git",
        is_present=True,
    )
    kwargs.update(overrides)
    row = RomPackItem(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestListRomPacks:
    def test_synthesizes_unpersisted_entry_when_no_db_row(self, client, monkeypatch):
        c, db = client
        _set_catalog(monkeypatch, [EMULATOR_ENTRY_WITH_DEP, ROM_PACK_ENTRY])

        resp = c.get("/api/v1/emulators/rom-packs")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["slug"] == "mame-roms"
        assert body[0]["emulator_slug"] == "mame"
        assert body[0]["is_present"] is False
        assert body[0]["id"] is None

    def test_uses_existing_row_when_present(self, client, monkeypatch):
        c, db = client
        _set_catalog(monkeypatch, [EMULATOR_ENTRY_WITH_DEP, ROM_PACK_ENTRY])
        _make_rom_pack_item(db, is_present=True, install_path="/roms/mame")

        resp = c.get("/api/v1/emulators/rom-packs")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["is_present"] is True
        assert body[0]["install_path"] == "/roms/mame"

    def test_non_rom_pack_entries_excluded(self, client, monkeypatch):
        c, db = client
        _set_catalog(monkeypatch, [NON_ROM_PACK_ENTRY])

        resp = c.get("/api/v1/emulators/rom-packs")

        assert resp.status_code == 200
        assert resp.json() == []


class TestGetRomPack:
    def test_404_when_slug_not_in_catalog(self, client, monkeypatch):
        c, _ = client
        _set_catalog(monkeypatch, [])

        resp = c.get("/api/v1/emulators/rom-packs/unknown-slug")

        assert resp.status_code == 404

    def test_404_when_slug_is_not_rom_pack_type(self, client, monkeypatch):
        c, _ = client
        _set_catalog(monkeypatch, [NON_ROM_PACK_ENTRY])

        resp = c.get("/api/v1/emulators/rom-packs/duckstation")

        assert resp.status_code == 404

    def test_returns_synthesized_entry_when_no_db_row(self, client, monkeypatch):
        c, _ = client
        _set_catalog(monkeypatch, [EMULATOR_ENTRY_WITH_DEP, ROM_PACK_ENTRY])

        resp = c.get("/api/v1/emulators/rom-packs/mame-roms")

        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] == "mame-roms"
        assert body["is_present"] is False

    def test_returns_existing_row_when_present(self, client, monkeypatch):
        c, db = client
        _set_catalog(monkeypatch, [EMULATOR_ENTRY_WITH_DEP, ROM_PACK_ENTRY])
        _make_rom_pack_item(db, is_present=True)

        resp = c.get("/api/v1/emulators/rom-packs/mame-roms")

        assert resp.status_code == 200
        assert resp.json()["is_present"] is True


class TestVerifyRomPack:
    def test_requires_is_admin_permission(self, client, monkeypatch):
        c, _ = client
        from backend.core.dependencies import get_active_user
        _set_catalog(monkeypatch, [EMULATOR_ENTRY_WITH_DEP, ROM_PACK_ENTRY])
        c.app.dependency_overrides[get_active_user] = _no_permission_user

        resp = c.post("/api/v1/emulators/rom-packs/mame-roms/verify")

        assert resp.status_code == 403

    def test_404_when_slug_not_in_catalog(self, client, monkeypatch):
        c, _ = client
        _set_catalog(monkeypatch, [])

        resp = c.post("/api/v1/emulators/rom-packs/unknown-slug/verify")

        assert resp.status_code == 404

    def test_400_when_slug_is_not_rom_pack_type(self, client, monkeypatch):
        c, _ = client
        _set_catalog(monkeypatch, [NON_ROM_PACK_ENTRY])

        resp = c.post("/api/v1/emulators/rom-packs/duckstation/verify")

        assert resp.status_code == 400

    def test_success_writes_row_via_test_engine_and_resyncs_is_present(
        self, client, monkeypatch, tmp_path
    ):
        c, db = client
        rom_dir = tmp_path / "mame-roms"
        rom_dir.mkdir()
        _set_catalog(monkeypatch, [EMULATOR_ENTRY_WITH_DEP, ROM_PACK_ENTRY])

        from backend.api.routes import rom_packs
        monkeypatch.setattr(rom_packs, "get_install_path", lambda slug: rom_dir)

        resp = c.post("/api/v1/emulators/rom-packs/mame-roms/verify")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["is_present"] is True
        assert body["install_path"] == str(rom_dir)

        # record_rom_pack_item() opens its own session via get_engine(); confirm
        # its write actually landed in the test's in-memory DB rather than some
        # other engine, by reading it back through the fixture's own session.
        from backend.models.rom_pack import RomPackItem
        db.expire_all()
        row = db.query(RomPackItem).filter(RomPackItem.slug == "mame-roms").one_or_none()
        assert row is not None
        assert row.is_present is True
        assert row.install_path == str(rom_dir)
        assert row.emulator_slug == "mame"

    def test_resyncs_to_not_present_when_missing_on_disk(self, client, monkeypatch):
        c, db = client
        _set_catalog(monkeypatch, [EMULATOR_ENTRY_WITH_DEP, ROM_PACK_ENTRY])
        _make_rom_pack_item(db, is_present=True, install_path="/roms/mame")

        from backend.api.routes import rom_packs
        monkeypatch.setattr(rom_packs, "get_install_path", lambda slug: None)

        resp = c.post("/api/v1/emulators/rom-packs/mame-roms/verify")

        assert resp.status_code == 200, resp.text
        assert resp.json()["is_present"] is False
