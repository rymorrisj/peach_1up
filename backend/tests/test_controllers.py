"""Route-level tests for ControllerMapping CRUD (backend/api/routes/controllers.py).

list/get/create/duplicate are open to any authenticated user by design.
update/delete go through check_controller_edit_permission, which grants on:

    - owner, or
    - the row's creator, or
    - is_admin AND can_manage_controllerMapping (a real AND, neither flag
      is sufficient on its own)

backend/api/routes/tags.py reuses the same function for controller_mapping
tag assignments, see test_tags.py's
TestControllerMappingAssignmentReusesEditPermission.
"""

import pytest


def _user(id, **overrides):
    from backend.models.user import UserItem
    kwargs = dict(id=id, name=f"UserItem{id}")
    kwargs.update(overrides)
    return UserItem(**kwargs)


@pytest.fixture
def mem_db_session():
    from sqlmodel import SQLModel, Session, create_engine
    from sqlalchemy.pool import StaticPool
    import backend.models  # noqa: F401, registers all table models with SQLModel.metadata

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import controllers
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(controllers.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session


def _override_user(c, user):
    from backend.core.dependencies import get_active_user
    c.app.dependency_overrides[get_active_user] = lambda: user


def _make_mapping(db, **overrides):
    from backend.models.controller_mapping import ControllerMappingItem

    kwargs = dict(
        name="Xbox Pad",
        device_signature="030000005e0400008e02000010010000",
        slug="xbox-pad",
        mapping_json={"a": "a"},
    )
    kwargs.update(overrides)
    mapping = ControllerMappingItem(**kwargs)
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping


# ---------------------------------------------------------------------------
# list / get, any authenticated user
# ---------------------------------------------------------------------------


class TestListAndGet:
    def test_list_any_authenticated_user(self, client):
        c, db = client
        _make_mapping(db)
        _override_user(c, _user(1))
        resp = c.get("/api/v1/controllers")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_get_any_authenticated_user(self, client):
        c, db = client
        mapping = _make_mapping(db)
        _override_user(c, _user(1))
        resp = c.get(f"/api/v1/controllers/{mapping.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == mapping.id

    def test_get_unknown_id_is_404(self, client):
        c, _ = client
        _override_user(c, _user(1))
        resp = c.get("/api/v1/controllers/999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# create, any authenticated user; created_by set to the creator
# ---------------------------------------------------------------------------


class TestCreate:
    def test_any_authenticated_user_can_create_and_created_by_is_set(self, client):
        c, db = client
        _override_user(c, _user(7))

        resp = c.post(
            "/api/v1/controllers",
            json={
                "name": "New Pad",
                "device_signature": "030000005e0400008e02000010010001",
                "mapping_json": {"a": "a"},
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["created_by"] == 7

        from backend.models.controller_mapping import ControllerMappingItem
        row = db.get(ControllerMappingItem, body["id"])
        assert row.created_by == 7


# ---------------------------------------------------------------------------
# duplicate, any authenticated user; created_by is the duplicator, not the
# source's owner; name/device_signature/mapping_json copied; " (copy)" suffix
# ---------------------------------------------------------------------------


class TestDuplicate:
    def test_any_authenticated_user_can_duplicate(self, client):
        c, db = client
        source = _make_mapping(
            db,
            created_by=1,
            name="Original",
            slug="original",
            device_signature="sig-original",
            mapping_json={"a": "1"},
        )
        _override_user(c, _user(2))  # different user from source's creator

        resp = c.post(f"/api/v1/controllers/{source.id}/duplicate")
        assert resp.status_code == 201, resp.text
        body = resp.json()

        assert body["id"] != source.id
        assert body["name"] == "Original (copy)"
        assert body["device_signature"] == "sig-original"
        assert body["mapping_json"] == {"a": "1"}
        assert body["created_by"] == 2  # the duplicator, not source's created_by=1

    def test_duplicate_unknown_id_is_404(self, client):
        c, _ = client
        _override_user(c, _user(1))
        resp = c.post("/api/v1/controllers/999/duplicate")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# update/delete permission matrix, check_controller_edit_permission
# (a) owner bypasses everything
# (b) creator bypasses admin/flag entirely
# (c) is_admin alone, no can_manage_controllerMapping -> fails
# (d) can_manage_controllerMapping alone, no is_admin -> fails
# (e) is_admin AND can_manage_controllerMapping together, on someone else's mapping -> succeeds
# (f) unrelated user (not owner/creator, not admin+flag) -> 403
# ---------------------------------------------------------------------------


class TestEditPermissionMatrix:
    @staticmethod
    def _call(c, method, mapping_id):
        if method == "patch":
            return c.patch(f"/api/v1/controllers/{mapping_id}", json={"name": "Renamed"})
        return c.delete(f"/api/v1/controllers/{mapping_id}")

    @pytest.mark.parametrize("method", ["patch", "delete"])
    def test_owner_succeeds_regardless_of_other_flags(self, client, method):
        c, db = client
        mapping = _make_mapping(db, created_by=999)
        owner = _user(1, is_owner=True, is_admin=False, can_manage_controllerMapping=False)
        _override_user(c, owner)
        resp = self._call(c, method, mapping.id)
        assert resp.status_code in (200, 204), resp.text

    @pytest.mark.parametrize("method", ["patch", "delete"])
    def test_creator_succeeds_regardless_of_admin_or_flag(self, client, method):
        c, db = client
        creator = _user(5, is_owner=False, is_admin=False, can_manage_controllerMapping=False)
        mapping = _make_mapping(db, created_by=creator.id)
        _override_user(c, creator)
        resp = self._call(c, method, mapping.id)
        assert resp.status_code in (200, 204), resp.text

    @pytest.mark.parametrize("method", ["patch", "delete"])
    def test_admin_alone_without_flag_fails(self, client, method):
        c, db = client
        mapping = _make_mapping(db, created_by=999)
        user = _user(2, is_owner=False, is_admin=True, can_manage_controllerMapping=False)
        _override_user(c, user)
        resp = self._call(c, method, mapping.id)
        assert resp.status_code == 403

    @pytest.mark.parametrize("method", ["patch", "delete"])
    def test_flag_alone_without_admin_fails(self, client, method):
        c, db = client
        mapping = _make_mapping(db, created_by=999)
        user = _user(3, is_owner=False, is_admin=False, can_manage_controllerMapping=True)
        _override_user(c, user)
        resp = self._call(c, method, mapping.id)
        assert resp.status_code == 403

    @pytest.mark.parametrize("method", ["patch", "delete"])
    def test_admin_and_flag_together_on_someone_elses_mapping_succeeds(self, client, method):
        c, db = client
        mapping = _make_mapping(db, created_by=999)
        user = _user(4, is_owner=False, is_admin=True, can_manage_controllerMapping=True)
        _override_user(c, user)
        resp = self._call(c, method, mapping.id)
        assert resp.status_code in (200, 204), resp.text

    @pytest.mark.parametrize("method", ["patch", "delete"])
    def test_unrelated_user_fails(self, client, method):
        c, db = client
        mapping = _make_mapping(db, created_by=999)
        user = _user(6, is_owner=False, is_admin=False, can_manage_controllerMapping=False)
        _override_user(c, user)
        resp = self._call(c, method, mapping.id)
        assert resp.status_code == 403

    def test_unknown_id_is_404_for_owner(self, client):
        c, _ = client
        _override_user(c, _user(1, is_owner=True))
        resp = c.patch("/api/v1/controllers/999", json={"name": "X"})
        assert resp.status_code == 404

    def test_unknown_id_is_404_for_non_owner_non_creator(self, client):
        c, _ = client
        _override_user(c, _user(6))
        resp = c.patch("/api/v1/controllers/999", json={"name": "X"})
        assert resp.status_code == 404
