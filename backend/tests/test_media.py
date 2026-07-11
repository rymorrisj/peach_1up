"""Route-level tests for Media CRUD (backend/api/routes/media.py) and the
MediaLink exactly-one-of(media_item_id, media_collection_id) invariant on
backend/models/media.py — the regression test for the @validates fix that
replaced a model_validator(mode="after") which never fired on direct
construction (same bug class as SoftwareCollection.item_type).
"""

import pytest


def _owner_user():
    from backend.models.user import User
    return User(id=1, name="Owner", is_owner=True)


def _no_permission_user():
    from backend.models.user import User
    return User(id=2, name="Guest", is_owner=False, can_edit_media=False)


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
        yield session


@pytest.fixture
def client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import media
    from backend.core.database import get_db
    from backend.core.dependencies import get_active_user

    app = FastAPI()
    app.include_router(media.router)
    app.dependency_overrides[get_active_user] = _owner_user
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session


def _make_software_collection(db, **overrides):
    from backend.models.software import SoftwareCollection

    kwargs = dict(
        title="Doom",
        file_path="/library/games/dos/doom",
        era="dos",
        slug="doom",
    )
    kwargs.update(overrides)
    collection = SoftwareCollection(**kwargs)
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
            "/api/v1/media",
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

        get_resp = c.get(f"/api/v1/media/{item_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["title"] == "Doom OST"

        list_resp = c.get("/api/v1/media")
        assert list_resp.status_code == 200
        assert any(i["id"] == item_id for i in list_resp.json()["items"])

        patch_resp = c.patch(f"/api/v1/media/{item_id}", json={"title": "Doom OST (Remastered)"})
        assert patch_resp.status_code == 200
        assert patch_resp.json()["title"] == "Doom OST (Remastered)"

        del_resp = c.delete(f"/api/v1/media/{item_id}")
        assert del_resp.status_code == 204

        from backend.models.media import MediaItem
        assert db.get(MediaItem, item_id) is None

    def test_get_unknown_id_is_404(self, client):
        c, _ = client
        resp = c.get("/api/v1/media/999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# MediaCollection CRUD
# ---------------------------------------------------------------------------


class TestMediaCollectionCrud:
    def test_create_read_update_delete(self, client):
        c, db = client

        create_resp = c.post(
            "/api/v1/media/collections",
            json={"title": "Doom OST Collection", "media_kind": "audio"},
        )
        assert create_resp.status_code == 201, create_resp.text
        collection = create_resp.json()
        collection_id = collection["id"]

        get_resp = c.get(f"/api/v1/media/collections/{collection_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["title"] == "Doom OST Collection"

        patch_resp = c.patch(
            f"/api/v1/media/collections/{collection_id}",
            json={"title": "Renamed Collection"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["title"] == "Renamed Collection"

        del_resp = c.delete(f"/api/v1/media/collections/{collection_id}")
        assert del_resp.status_code == 204

        from backend.models.media import MediaCollection
        assert db.get(MediaCollection, collection_id) is None

    def test_get_unknown_id_is_404(self, client):
        c, _ = client
        resp = c.get("/api/v1/media/collections/999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cross-table slug uniqueness — MediaItem and MediaCollection share one slug
# namespace (see _unique_media_slug in backend/api/routes/media.py).
# ---------------------------------------------------------------------------


class TestCrossTableSlugUniqueness:
    def test_collection_title_colliding_with_item_slug_gets_suffixed(self, client):
        c, _ = client
        item_resp = c.post(
            "/api/v1/media",
            json={"title": "Shared Name", "media_kind": "audio", "file_path": "/library/media/a.mp3"},
        )
        assert item_resp.status_code == 201
        assert item_resp.json()["slug"] == "shared-name"

        collection_resp = c.post(
            "/api/v1/media/collections",
            json={"title": "Shared Name", "media_kind": "audio"},
        )
        assert collection_resp.status_code == 201
        assert collection_resp.json()["slug"] == "shared-name-2"

    def test_item_title_colliding_with_collection_slug_gets_suffixed(self, client):
        c, _ = client
        collection_resp = c.post(
            "/api/v1/media/collections",
            json={"title": "Shared Name", "media_kind": "audio"},
        )
        assert collection_resp.status_code == 201
        assert collection_resp.json()["slug"] == "shared-name"

        item_resp = c.post(
            "/api/v1/media",
            json={"title": "Shared Name", "media_kind": "audio", "file_path": "/library/media/a.mp3"},
        )
        assert item_resp.status_code == 201
        assert item_resp.json()["slug"] == "shared-name-2"


# ---------------------------------------------------------------------------
# Permission split — GET routes: any authenticated user. POST/PATCH/DELETE:
# require can_edit_media, 403 without it.
# ---------------------------------------------------------------------------


class TestPermissionSplit:
    def test_get_routes_succeed_without_can_edit_media(self, client):
        c, db = client
        from backend.models.media import MediaItem, MediaCollection

        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        collection = MediaCollection(title="Y", media_kind="audio", slug="y")
        db.add(item)
        db.add(collection)
        db.commit()
        db.refresh(item)
        db.refresh(collection)

        from backend.core.dependencies import get_active_user
        c.app.dependency_overrides[get_active_user] = _no_permission_user

        assert c.get("/api/v1/media").status_code == 200
        assert c.get(f"/api/v1/media/{item.id}").status_code == 200
        assert c.get(f"/api/v1/media/collections/{collection.id}").status_code == 200

    @pytest.mark.parametrize(
        "method,path,json",
        [
            ("post", "/api/v1/media", {"title": "X", "media_kind": "audio", "file_path": "/x.mp3"}),
            ("post", "/api/v1/media/collections", {"title": "X", "media_kind": "audio"}),
        ],
    )
    def test_create_routes_require_can_edit_media(self, client, method, path, json):
        c, _ = client
        from backend.core.dependencies import get_active_user
        c.app.dependency_overrides[get_active_user] = _no_permission_user

        resp = getattr(c, method)(path, json=json)
        assert resp.status_code == 403

    def test_update_and_delete_require_can_edit_media(self, client):
        c, db = client
        from backend.models.media import MediaItem

        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        db.add(item)
        db.commit()
        db.refresh(item)

        from backend.core.dependencies import get_active_user
        c.app.dependency_overrides[get_active_user] = _no_permission_user

        assert c.patch(f"/api/v1/media/{item.id}", json={"title": "Y"}).status_code == 403
        assert c.delete(f"/api/v1/media/{item.id}").status_code == 403


# ---------------------------------------------------------------------------
# Link / unlink
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
            f"/api/v1/media/{item.id}/link",
            json={"software_collection_id": collection.id, "link_note": "Theme song"},
        )
        assert link_resp.status_code == 201, link_resp.text
        assert link_resp.json()["media_item_id"] == item.id

        get_resp = c.get(f"/api/v1/media/{item.id}")
        assert get_resp.status_code == 200
        assert len(get_resp.json()["linked_software"]) == 1

        unlink_resp = c.delete(
            f"/api/v1/media/{item.id}/link",
            params={"software_collection_id": collection.id},
        )
        assert unlink_resp.status_code == 204

        get_resp2 = c.get(f"/api/v1/media/{item.id}")
        assert get_resp2.json()["linked_software"] == []

    def test_link_and_unlink_media_collection(self, client):
        c, db = client
        from backend.models.media import MediaCollection

        media_collection = MediaCollection(title="Y", media_kind="audio", slug="y")
        db.add(media_collection)
        db.commit()
        db.refresh(media_collection)
        sw_collection = _make_software_collection(db)

        link_resp = c.post(
            f"/api/v1/media/collections/{media_collection.id}/link",
            json={"software_collection_id": sw_collection.id},
        )
        assert link_resp.status_code == 201, link_resp.text
        assert link_resp.json()["media_collection_id"] == media_collection.id

        unlink_resp = c.delete(
            f"/api/v1/media/collections/{media_collection.id}/link",
            params={"software_collection_id": sw_collection.id},
        )
        assert unlink_resp.status_code == 204

    def test_link_unknown_item_is_404(self, client):
        c, db = client
        collection = _make_software_collection(db)
        resp = c.post(
            "/api/v1/media/999/link",
            json={"software_collection_id": collection.id},
        )
        assert resp.status_code == 404

    def test_link_unknown_software_collection_is_404(self, client):
        c, db = client
        from backend.models.media import MediaItem

        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        db.add(item)
        db.commit()
        db.refresh(item)

        resp = c.post(f"/api/v1/media/{item.id}/link", json={"software_collection_id": 999})
        assert resp.status_code == 404

    def test_unlink_missing_link_is_404(self, client):
        c, db = client
        from backend.models.media import MediaItem

        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        db.add(item)
        db.commit()
        db.refresh(item)
        collection = _make_software_collection(db)

        resp = c.delete(
            f"/api/v1/media/{item.id}/link",
            params={"software_collection_id": collection.id},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# MediaLink XOR invariant — regression test for the @validates fix.
# Constructed directly (MediaLink(...) + db.add() + db.flush()), NOT via
# .model_validate(), since that is exactly the construction path a
# model_validator(mode="after") does not fire on for a SQLModel table=True
# class (see backend/models/media.py's comment on MediaLink).
# ---------------------------------------------------------------------------


class TestMediaLinkExactlyOneTarget:
    def test_both_set_is_rejected(self, mem_db_session):
        from backend.models.media import MediaLink, MediaItem, MediaCollection

        db = mem_db_session
        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        collection = MediaCollection(title="Y", media_kind="audio", slug="y")
        db.add(item)
        db.add(collection)
        db.commit()
        db.refresh(item)
        db.refresh(collection)
        sw_collection = _make_software_collection(db)

        with pytest.raises(ValueError):
            MediaLink(
                media_item_id=item.id,
                media_collection_id=collection.id,
                software_collection_id=sw_collection.id,
            )

    def test_neither_set_is_rejected(self, mem_db_session):
        from backend.models.media import MediaLink

        db = mem_db_session
        sw_collection = _make_software_collection(db)

        with pytest.raises(ValueError):
            MediaLink(software_collection_id=sw_collection.id)

    def test_exactly_one_item_set_is_accepted(self, mem_db_session):
        from backend.models.media import MediaLink, MediaItem

        db = mem_db_session
        item = MediaItem(title="X", media_kind="audio", file_path="/x.mp3", slug="x")
        db.add(item)
        db.commit()
        db.refresh(item)
        sw_collection = _make_software_collection(db)

        link = MediaLink(media_item_id=item.id, software_collection_id=sw_collection.id)
        db.add(link)
        db.flush()
        assert link.id is not None

    def test_exactly_one_collection_set_is_accepted(self, mem_db_session):
        from backend.models.media import MediaLink, MediaCollection

        db = mem_db_session
        collection = MediaCollection(title="Y", media_kind="audio", slug="y")
        db.add(collection)
        db.commit()
        db.refresh(collection)
        sw_collection = _make_software_collection(db)

        link = MediaLink(media_collection_id=collection.id, software_collection_id=sw_collection.id)
        db.add(link)
        db.flush()
        assert link.id is not None
