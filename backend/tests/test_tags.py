"""Route-level tests for the generic tag-assignment endpoints
(backend/api/routes/tags.py). Covers dispatch order in
_resolve_assignment_entity, one create+delete pass per entity_type in
_ASSIGNMENT_TARGETS, and that controller_mapping assignments reuse
check_controller_edit_permission (backend/api/routes/controllers.py) rather
than duplicating it. test_controllers.py holds that permission matrix.

httpx's TestClient.delete() has no json/content parameter (DELETE-with-body is
non-standard), so every delete_tag_assignment call below uses
c.request("DELETE", url, json=...) instead of c.delete(url, json=...).
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
    from backend.api.routes import tags
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(tags.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session


def _override_user(c, user):
    from backend.core.dependencies import get_active_user
    c.app.dependency_overrides[get_active_user] = lambda: user


def _make_tag(db, **overrides):
    from backend.models.tag import Tag
    kwargs = dict(name="Favorite", color="slate")
    kwargs.update(overrides)
    tag = Tag(**kwargs)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


# ---------------------------------------------------------------------------
# One factory per _ASSIGNMENT_TARGETS entity_type.
# ---------------------------------------------------------------------------


def _make_software_collection(db, **overrides):
    from backend.models.game import GameItemBundle
    kwargs = dict(title="Doom", file_path="/library/games/dos/doom", era="dos", slug="doom")
    kwargs.update(overrides)
    row = GameItemBundle(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_software_item(db, **overrides):
    from backend.models.game import GameItem
    collection = overrides.pop("collection", None) or _make_software_collection(db)
    kwargs = dict(game_item_bundle_id=collection.id, file_path="/library/games/dos/doom/doom.iso")
    kwargs.update(overrides)
    row = GameItem(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_media_item(db, **overrides):
    from backend.models.media import MediaItem
    kwargs = dict(title="Doom OST", media_kind="audio", file_path="/library/media/doom-ost.mp3", slug="doom-ost")
    kwargs.update(overrides)
    row = MediaItem(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_media_collection(db, **overrides):
    from backend.models.media import MediaItemBundle
    kwargs = dict(title="Doom OST Collection", media_kind="audio", slug="doom-ost-collection")
    kwargs.update(overrides)
    row = MediaItemBundle(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_environment(db, **overrides):
    from backend.models.environment import EnvironmentItem
    kwargs = dict(name="Win98 Box", era="win98", emulator_slug="86box", slug="win98-box")
    kwargs.update(overrides)
    row = EnvironmentItem(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_rom_pack_item(db, **overrides):
    from backend.models.rom_pack import RomPackItem
    kwargs = dict(name="86Box ROM Pack", emulator_slug="86box", slug="86box-rom-pack", is_present=False)
    kwargs.update(overrides)
    row = RomPackItem(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_controller_mapping(db, **overrides):
    from backend.models.controller_mapping import ControllerMappingItem
    kwargs = dict(name="Xbox Pad", device_signature="030000005e0400008e02000010010000", slug="xbox-pad")
    kwargs.update(overrides)
    row = ControllerMappingItem(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


_ENTITY_FACTORIES = {
    "game_item_bundle": _make_software_collection,
    "game_item": _make_software_item,
    "media_item": _make_media_item,
    "media_item_bundle": _make_media_collection,
    "environment_item": _make_environment,
    "rom_pack_item": _make_rom_pack_item,
    "controller_mapping": _make_controller_mapping,
}

# entity_type -> a User authorized to write an assignment for it.
_ENTITY_AUTHORIZED_USER = {
    "game_item_bundle": lambda: _user(1, can_manage_game=True),
    "game_item": lambda: _user(1, can_manage_game=True),
    "media_item": lambda: _user(1, can_manage_media=True),
    "media_item_bundle": lambda: _user(1, can_manage_media=True),
    "environment_item": lambda: _user(1, can_manage_environment=True),
    "rom_pack_item": lambda: _user(1, can_manage_environment=True),
    "controller_mapping": lambda: _user(1, is_owner=True),
}


# ---------------------------------------------------------------------------
# Dispatch order in _resolve_assignment_entity:
#   unknown entity_type -> 422
#   plain-flag permission -> 403 (before ANY existence check, so an
#     unauthorized caller can't learn whether a tag/entity exists)
#   tag_id not found -> 404
#   entity_id not found -> 404
#   (controller_mapping's bespoke check runs last, needs the fetched row)
# ---------------------------------------------------------------------------


class TestDispatchOrder:
    def test_unknown_entity_type_is_422(self, client):
        c, db = client
        tag = _make_tag(db)
        _override_user(c, _user(1, is_owner=True))
        resp = c.post(
            f"/api/v1/tags/{tag.id}/assignments",
            json={"entity_type": "not_a_real_type", "entity_id": 1},
        )
        assert resp.status_code == 422

    def test_permission_check_precedes_existence_checks_no_leak(self, client):
        c, _ = client
        # Neither the tag nor the entity exist, and the user lacks can_manage_game.
        # If existence were checked first this would 404; it must 403 instead.
        _override_user(c, _user(2, can_manage_game=False))
        resp = c.post(
            "/api/v1/tags/999999/assignments",
            json={"entity_type": "game_item", "entity_id": 999999},
        )
        assert resp.status_code == 403

    def test_tag_not_found_is_404(self, client):
        c, db = client
        collection = _make_software_collection(db)
        _override_user(c, _user(1, can_manage_game=True))
        resp = c.post(
            "/api/v1/tags/999999/assignments",
            json={"entity_type": "game_item_bundle", "entity_id": collection.id},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Tag not found."

    def test_entity_not_found_is_404(self, client):
        c, db = client
        tag = _make_tag(db)
        _override_user(c, _user(1, can_manage_game=True))
        resp = c.post(
            f"/api/v1/tags/{tag.id}/assignments",
            json={"entity_type": "game_item_bundle", "entity_id": 999999},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "game_item_bundle not found."


# ---------------------------------------------------------------------------
# One create+delete assignment pass per entity_type in _ASSIGNMENT_TARGETS.
# ---------------------------------------------------------------------------


class TestPerEntityTypeCreateDeleteAssignment:
    @pytest.mark.parametrize("entity_type", sorted(_ENTITY_FACTORIES.keys()))
    def test_create_then_delete_assignment(self, client, entity_type):
        c, db = client
        tag = _make_tag(db)
        entity = _ENTITY_FACTORIES[entity_type](db)
        _override_user(c, _ENTITY_AUTHORIZED_USER[entity_type]())

        body = {"entity_type": entity_type, "entity_id": entity.id}

        create_resp = c.post(f"/api/v1/tags/{tag.id}/assignments", json=body)
        assert create_resp.status_code == 204, create_resp.text

        from backend.models.tag import EntityTag

        def _link():
            return (
                db.query(EntityTag)
                .filter(
                    EntityTag.tag_id == tag.id,
                    EntityTag.entity_type == entity_type,
                    EntityTag.entity_id == entity.id,
                )
                .first()
            )

        assert _link() is not None

        delete_resp = c.request("DELETE", f"/api/v1/tags/{tag.id}/assignments", json=body)
        assert delete_resp.status_code == 204, delete_resp.text

        db.expire_all()
        assert _link() is None


# ---------------------------------------------------------------------------
# controller_mapping assignments reuse check_controller_edit_permission
# verbatim, same matrix as test_controllers.py::TestEditPermissionMatrix,
# run here against POST /tags/{id}/assignments instead of PATCH/DELETE
# /controllers/{id}, to prove tags.py dispatches into the shared function
# rather than a separate/duplicated check.
# ---------------------------------------------------------------------------


class TestControllerMappingAssignmentReusesEditPermission:
    @staticmethod
    def _attempt(c, tag, mapping, user):
        _override_user(c, user)
        return c.post(
            f"/api/v1/tags/{tag.id}/assignments",
            json={"entity_type": "controller_mapping", "entity_id": mapping.id},
        )

    def test_owner_succeeds_regardless_of_other_flags(self, client):
        c, db = client
        tag = _make_tag(db)
        mapping = _make_controller_mapping(db, created_by=999)
        user = _user(1, is_owner=True, is_admin=False, can_manage_controllerMapping=False)
        resp = self._attempt(c, tag, mapping, user)
        assert resp.status_code == 204, resp.text

    def test_creator_succeeds_regardless_of_admin_or_flag(self, client):
        c, db = client
        tag = _make_tag(db)
        creator = _user(5, is_owner=False, is_admin=False, can_manage_controllerMapping=False)
        mapping = _make_controller_mapping(db, created_by=creator.id)
        resp = self._attempt(c, tag, mapping, creator)
        assert resp.status_code == 204, resp.text

    def test_admin_alone_without_flag_fails(self, client):
        c, db = client
        tag = _make_tag(db)
        mapping = _make_controller_mapping(db, created_by=999)
        user = _user(2, is_owner=False, is_admin=True, can_manage_controllerMapping=False)
        resp = self._attempt(c, tag, mapping, user)
        assert resp.status_code == 403

    def test_flag_alone_without_admin_fails(self, client):
        c, db = client
        tag = _make_tag(db)
        mapping = _make_controller_mapping(db, created_by=999)
        user = _user(3, is_owner=False, is_admin=False, can_manage_controllerMapping=True)
        resp = self._attempt(c, tag, mapping, user)
        assert resp.status_code == 403

    def test_admin_and_flag_together_on_someone_elses_mapping_succeeds(self, client):
        c, db = client
        tag = _make_tag(db)
        mapping = _make_controller_mapping(db, created_by=999)
        user = _user(4, is_owner=False, is_admin=True, can_manage_controllerMapping=True)
        resp = self._attempt(c, tag, mapping, user)
        assert resp.status_code == 204, resp.text

    def test_unrelated_user_fails(self, client):
        c, db = client
        tag = _make_tag(db)
        mapping = _make_controller_mapping(db, created_by=999)
        user = _user(6, is_owner=False, is_admin=False, can_manage_controllerMapping=False)
        resp = self._attempt(c, tag, mapping, user)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# create_tag_assignment idempotency
# ---------------------------------------------------------------------------


class TestCreateTagAssignmentIdempotency:
    def test_creating_same_assignment_twice_does_not_error_or_duplicate(self, client):
        c, db = client
        tag = _make_tag(db)
        collection = _make_software_collection(db)
        _override_user(c, _user(1, can_manage_game=True))

        body = {"entity_type": "game_item_bundle", "entity_id": collection.id}
        first = c.post(f"/api/v1/tags/{tag.id}/assignments", json=body)
        second = c.post(f"/api/v1/tags/{tag.id}/assignments", json=body)
        assert first.status_code == 204
        assert second.status_code == 204

        from backend.models.tag import EntityTag
        count = (
            db.query(EntityTag)
            .filter(
                EntityTag.tag_id == tag.id,
                EntityTag.entity_type == "game_item_bundle",
                EntityTag.entity_id == collection.id,
            )
            .count()
        )
        assert count == 1


# ---------------------------------------------------------------------------
# delete_tag_assignment: 404 if the link doesn't exist
# ---------------------------------------------------------------------------


class TestDeleteTagAssignment:
    def test_404_if_link_does_not_exist(self, client):
        c, db = client
        tag = _make_tag(db)
        collection = _make_software_collection(db)
        _override_user(c, _user(1, can_manage_game=True))

        resp = c.request(
            "DELETE",
            f"/api/v1/tags/{tag.id}/assignments",
            json={"entity_type": "game_item_bundle", "entity_id": collection.id},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Tag not assigned to this entity."
