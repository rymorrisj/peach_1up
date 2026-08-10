"""Route-level tests for Media CRUD (backend/api/routes/media.py), the
generic entity-link routes (backend/api/routes/entity_links.py), and the
MediaLink canonical-ordering / no-self-link invariant enforced by
make_entity_link() in backend/models/media.py.
"""

import pytest


def _owner_user():
    from backend.models.user import UserItem
    return UserItem(id=1, name="Owner", is_owner=True)


def _no_permission_user():
    from backend.models.user import UserItem
    return UserItem(id=2, name="Guest", is_owner=False, can_manage_media=False)


def _media_only_user():
    """can_manage_media but NOT can_manage_game, used to prove link creation
    needs authorization on BOTH entities, not just the one named in the URL."""
    from backend.models.user import UserItem
    return UserItem(id=3, name="Archivist", is_owner=False, can_manage_media=True, can_manage_game=False)


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
def client(mem_db_session, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import entity_links, media
    from backend.core.database import get_db
    from backend.core.dependencies import get_active_user

    # item_to_read/media_item_bundle_to_read compute cover_art_url/file_url
    # via _compute_media_url (backend/models/media.py), which reads
    # LIBRARY_PATH straight off backend.service.utils.settings, not through
    # the core.settings.get_settings() facade, so the usual get_settings
    # monkeypatch used elsewhere in this suite does not cover it. Patched
    # here the same way test_asset_fetch.py's tmp_lib fixture does.
    import backend.service.utils.settings as settings_mod

    def _fake_get(key, default=None):
        if key == "LIBRARY_PATH":
            return str(tmp_path)
        return default

    monkeypatch.setattr(settings_mod, "get", _fake_get)

    app = FastAPI()
    app.include_router(media.router)
    app.include_router(entity_links.router)
    app.dependency_overrides[get_active_user] = _owner_user
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session


def _make_software_collection(db, **overrides):
    from backend.models.game import GameItemBundle

    kwargs = dict(
        title="Doom",
        file_path="/library/games/dos/doom",
        era="dos",
        slug="doom",
    )
    kwargs.update(overrides)
    collection = GameItemBundle(**kwargs)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


# ---------------------------------------------------------------------------
# MediaItem CRUD
# ---------------------------------------------------------------------------


class TestMediaItemCrud:
    def test_create_read_update_delete(self, client):
        c, db = client

        create_resp = c.post(
            "/api/v1/media-items",
            json={
                "title": "Doom OST",
                "media_kind": "audio",
                "file_path": "/library/media/doom-ost.mp3",
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        item = create_resp.json()
        assert item["slug"] == "doom-ost"
        item_id = item["id"]

        get_resp = c.get(f"/api/v1/media-item/{item_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["title"] == "Doom OST"

        list_resp = c.get("/api/v1/media-items")
        assert list_resp.status_code == 200
        assert any(i["id"] == item_id for i in list_resp.json()["items"])

        patch_resp = c.patch(f"/api/v1/media-item/{item_id}", json={"title": "Doom OST (Remastered)"})
        assert patch_resp.status_code == 200
        assert patch_resp.json()["title"] == "Doom OST (Remastered)"

        del_resp = c.delete(f"/api/v1/media-item/{item_id}")
        assert del_resp.status_code == 204

        from backend.models.media import MediaItem
        assert db.get(MediaItem, item_id) is None

    def test_get_unknown_id_is_404(self, client):
        c, _ = client
        resp = c.get("/api/v1/media-item/999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# MediaItemBundle CRUD
# ---------------------------------------------------------------------------


class TestMediaItemBundleCrud:
    def test_create_read_update_delete(self, client):
        c, db = client

        create_resp = c.post(
            "/api/v1/media-item-bundles",
            json={"title": "Doom OST Collection", "media_kind": "audio"},
        )
        assert create_resp.status_code == 201, create_resp.text
        collection = create_resp.json()
        collection_id = collection["id"]

        get_resp = c.get(f"/api/v1/media-item-bundle/{collection_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["title"] == "Doom OST Collection"

        patch_resp = c.patch(
            f"/api/v1/media-item-bundle/{collection_id}",
            json={"title": "Renamed Collection"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["title"] == "Renamed Collection"

        del_resp = c.delete(f"/api/v1/media-item-bundle/{collection_id}")
        assert del_resp.status_code == 204

        from backend.models.media import MediaItemBundle
        assert db.get(MediaItemBundle, collection_id) is None

    def test_get_unknown_id_is_404(self, client):
        c, _ = client
        resp = c.get("/api/v1/media-item-bundle/999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cross-table slug uniqueness, MediaItem and MediaItemBundle share one slug
# namespace (see _unique_media_slug in backend/api/routes/media.py).
# ---------------------------------------------------------------------------


class TestCrossTableSlugUniqueness:
    def test_collection_title_colliding_with_item_slug_gets_suffixed(self, client):
        c, _ = client
        item_resp = c.post(
            "/api/v1/media-items",
            json={"title": "Shared Name", "media_kind": "audio", "file_path": "/library/media/a.mp3"},
        )
        assert item_resp.status_code == 201
        assert item_resp.json()["slug"] == "shared-name"

        collection_resp = c.post(
            "/api/v1/media-item-bundles",
            json={"title": "Shared Name", "media_kind": "audio"},
        )
        assert collection_resp.status_code == 201
        assert collection_resp.json()["slug"] == "shared-name-2"

    def test_item_title_colliding_with_collection_slug_gets_suffixed(self, client):
        c, _ = client
        collection_resp = c.post(
            "/api/v1/media-item-bundles",
            json={"title": "Shared Name", "media_kind": "audio"},
        )
        assert collection_resp.status_code == 201
        assert collection_resp.json()["slug"] == "shared-name"

        item_resp = c.post(
            "/api/v1/media-items",
            json={"title": "Shared Name", "media_kind": "audio", "file_path": "/library/media/a.mp3"},
        )
        assert item_resp.status_code == 201
        assert item_resp.json()["slug"] == "shared-name-2"


# ---------------------------------------------------------------------------
# Permission split, GET routes: any authenticated user. POST/PATCH/DELETE:
# require can_manage_media, 403 without it.
# ---------------------------------------------------------------------------


class TestPermissionSplit:
    def test_get_routes_succeed_without_can_manage_media(self, client):
        c, db = client
        from backend.models.media import MediaItem, MediaItemBundle

        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        collection = MediaItemBundle(title="Y", media_kind="audio", slug="y")
        db.add(item)
        db.add(collection)
        db.commit()
        db.refresh(item)
        db.refresh(collection)

        from backend.core.dependencies import get_active_user
        c.app.dependency_overrides[get_active_user] = _no_permission_user

        assert c.get("/api/v1/media-items").status_code == 200
        assert c.get(f"/api/v1/media-item/{item.id}").status_code == 200
        assert c.get(f"/api/v1/media-item-bundle/{collection.id}").status_code == 200

    @pytest.mark.parametrize(
        "method,path,json",
        [
            ("post", "/api/v1/media-items", {"title": "X", "media_kind": "audio", "file_path": "/x.mp3"}),
            ("post", "/api/v1/media-item-bundles", {"title": "X", "media_kind": "audio"}),
        ],
    )
    def test_create_routes_require_can_manage_media(self, client, method, path, json):
        c, _ = client
        from backend.core.dependencies import get_active_user
        c.app.dependency_overrides[get_active_user] = _no_permission_user

        resp = getattr(c, method)(path, json=json)
        assert resp.status_code == 403

    def test_update_and_delete_require_can_manage_media(self, client):
        c, db = client
        from backend.models.media import MediaItem

        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        db.add(item)
        db.commit()
        db.refresh(item)

        from backend.core.dependencies import get_active_user
        c.app.dependency_overrides[get_active_user] = _no_permission_user

        assert c.patch(f"/api/v1/media-item/{item.id}", json={"title": "Y"}).status_code == 403
        assert c.delete(f"/api/v1/media-item/{item.id}").status_code == 403


# ---------------------------------------------------------------------------
# Link / unlink, generic entity-link routes (backend/api/routes/entity_links.py).
# Canonical ordering sorts entity_a/entity_b ascending by (type, id): since
# "game_item_bundle" < "media_item" and "game_item_bundle" < "media_item_bundle"
# lexicographically, the game side always lands as entity_a regardless of
# which side the request names first. Tests assert on that fixed ordering.
# ---------------------------------------------------------------------------


class TestLinkUnlink:
    def test_link_and_unlink_media_item(self, client):
        c, db = client
        from backend.models.media import MediaItem

        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        db.add(item)
        db.commit()
        db.refresh(item)
        collection = _make_software_collection(db)

        link_resp = c.post(
            f"/api/v1/entity-links/media_item/{item.id}",
            json={
                "target_entity_type": "game_item_bundle",
                "target_entity_id": collection.id,
                "link_note": "Theme song",
            },
        )
        assert link_resp.status_code == 201, link_resp.text
        body = link_resp.json()
        assert body["entity_a_type"] == "game_item_bundle"
        assert body["entity_a_id"] == collection.id
        assert body["entity_b_type"] == "media_item"
        assert body["entity_b_id"] == item.id

        get_resp = c.get(f"/api/v1/media-item/{item.id}")
        assert get_resp.status_code == 200
        linked = get_resp.json()["linked_items"]
        assert len(linked) == 1
        assert linked[0]["entity_type"] == "game_item_bundle"
        assert linked[0]["entity_id"] == collection.id

        unlink_resp = c.delete(
            f"/api/v1/entity-links/media_item/{item.id}",
            params={"target_entity_type": "game_item_bundle", "target_entity_id": collection.id},
        )
        assert unlink_resp.status_code == 204

        get_resp2 = c.get(f"/api/v1/media-item/{item.id}")
        assert get_resp2.json()["linked_items"] == []

    def test_link_and_unlink_media_collection(self, client):
        c, db = client
        from backend.models.media import MediaItemBundle

        media_collection = MediaItemBundle(title="Y", media_kind="audio", slug="y")
        db.add(media_collection)
        db.commit()
        db.refresh(media_collection)
        sw_collection = _make_software_collection(db)

        link_resp = c.post(
            f"/api/v1/entity-links/media_item_bundle/{media_collection.id}",
            json={"target_entity_type": "game_item_bundle", "target_entity_id": sw_collection.id},
        )
        assert link_resp.status_code == 201, link_resp.text
        body = link_resp.json()
        assert body["entity_a_type"] == "game_item_bundle"
        assert body["entity_a_id"] == sw_collection.id
        assert body["entity_b_type"] == "media_item_bundle"
        assert body["entity_b_id"] == media_collection.id

        unlink_resp = c.delete(
            f"/api/v1/entity-links/media_item_bundle/{media_collection.id}",
            params={"target_entity_type": "game_item_bundle", "target_entity_id": sw_collection.id},
        )
        assert unlink_resp.status_code == 204

    def test_link_unknown_item_is_404(self, client):
        c, db = client
        collection = _make_software_collection(db)
        resp = c.post(
            "/api/v1/entity-links/media_item/999",
            json={"target_entity_type": "game_item_bundle", "target_entity_id": collection.id},
        )
        assert resp.status_code == 404

    def test_link_unknown_game_collection_is_404(self, client):
        c, db = client
        from backend.models.media import MediaItem

        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        db.add(item)
        db.commit()
        db.refresh(item)

        resp = c.post(
            f"/api/v1/entity-links/media_item/{item.id}",
            json={"target_entity_type": "game_item_bundle", "target_entity_id": 999},
        )
        assert resp.status_code == 404

    def test_link_unknown_entity_type_is_422(self, client):
        c, db = client
        from backend.models.media import MediaItem

        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        db.add(item)
        db.commit()
        db.refresh(item)

        resp = c.post(
            f"/api/v1/entity-links/media_item/{item.id}",
            json={"target_entity_type": "not_a_real_type", "target_entity_id": 1},
        )
        assert resp.status_code == 422

    def test_self_link_is_422(self, client):
        c, db = client
        from backend.models.media import MediaItem

        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        db.add(item)
        db.commit()
        db.refresh(item)

        resp = c.post(
            f"/api/v1/entity-links/media_item/{item.id}",
            json={"target_entity_type": "media_item", "target_entity_id": item.id},
        )
        assert resp.status_code == 422

    def test_unlink_missing_link_is_404(self, client):
        c, db = client
        from backend.models.media import MediaItem

        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        db.add(item)
        db.commit()
        db.refresh(item)
        collection = _make_software_collection(db)

        resp = c.delete(
            f"/api/v1/entity-links/media_item/{item.id}",
            params={"target_entity_type": "game_item_bundle", "target_entity_id": collection.id},
        )
        assert resp.status_code == 404

    def test_create_requires_authorization_on_both_entities(self, client):
        """A caller with can_manage_media but not can_manage_game must be
        rejected: creating a link touches two entities in two domains, and
        the two-sided check (backend/api/routes/entity_links.py's
        _resolve_link_entities) must not accept authorization on only one
        side, unlike tags.py's single-sided precedent."""
        c, db = client
        from backend.models.media import MediaItem

        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        db.add(item)
        db.commit()
        db.refresh(item)
        collection = _make_software_collection(db)

        from backend.core.dependencies import get_active_user
        c.app.dependency_overrides[get_active_user] = _media_only_user

        resp = c.post(
            f"/api/v1/entity-links/media_item/{item.id}",
            json={"target_entity_type": "game_item_bundle", "target_entity_id": collection.id},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# MediaLink canonical-ordering / no-self-link invariant, enforced by
# make_entity_link() (backend/models/media.py) rather than a model
# validator. Unlike the old exactly-one-of-two-nullable-FKs shape, every
# MediaLink column is now always required, so there is no construction-time
# ambiguity left for a model_post_init to guard.
# ---------------------------------------------------------------------------


class TestMakeEntityLink:
    def test_self_link_is_rejected(self):
        from backend.models.media import make_entity_link

        with pytest.raises(ValueError):
            make_entity_link("media_item", 5, "media_item", 5)

    def test_canonical_ordering_is_independent_of_argument_order(self):
        from backend.models.media import make_entity_link

        forward = make_entity_link("media_item", 5, "game_item_bundle", 2)
        backward = make_entity_link("game_item_bundle", 2, "media_item", 5)

        assert (forward.entity_a_type, forward.entity_a_id, forward.entity_b_type, forward.entity_b_id) == (
            backward.entity_a_type, backward.entity_a_id, backward.entity_b_type, backward.entity_b_id,
        )
        assert forward.entity_a_type == "game_item_bundle"
        assert forward.entity_a_id == 2
        assert forward.entity_b_type == "media_item"
        assert forward.entity_b_id == 5

    def test_self_referential_media_to_media_link_is_accepted(self, mem_db_session):
        from backend.models.media import MediaItem, make_entity_link

        db = mem_db_session
        a = MediaItem(title="A", media_kind="text", file_path="/a.pdf", slug="a")
        b = MediaItem(title="B", media_kind="text", file_path="/b.pdf", slug="b")
        db.add(a)
        db.add(b)
        db.commit()
        db.refresh(a)
        db.refresh(b)

        link = make_entity_link("media_item", a.id, "media_item", b.id)
        db.add(link)
        db.flush()
        assert link.id is not None

    def test_duplicate_pair_violates_unique_constraint(self, mem_db_session):
        from sqlalchemy.exc import IntegrityError
        from backend.models.media import MediaItem, make_entity_link

        db = mem_db_session
        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        db.add(item)
        db.commit()
        db.refresh(item)
        collection = _make_software_collection(db)

        db.add(make_entity_link("media_item", item.id, "game_item_bundle", collection.id))
        db.flush()

        db.add(make_entity_link("game_item_bundle", collection.id, "media_item", item.id))
        with pytest.raises(IntegrityError):
            db.flush()
