"""Visibility sweep: every game, app, profile, launch and drive route that
takes an id answers a hidden id exactly like a missing one.

For each route fixed in this sweep:
- a capped user gets the same 404 (status and body) for a hidden id as for a
  missing id, and the hidden row is left untouched;
- the owner still succeeds on the same hidden id (owner bypass);
- a non-owner who can see the item still succeeds.

List routes (profile items, launch history, drives) must leave hidden rows
out entirely, so a hidden id reads exactly like a missing one.
"""

import pytest

_MISSING_ID = 9999


@pytest.fixture
def mem_db_session():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine
    import backend.models  # noqa: F401, registers all table models

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def viewer(mem_db_session):
    """A non-owner holding every management and launch flag, capped at T.
    Holding the flags proves a 404 comes from visibility, not permissions."""
    from backend.models.user import UserItem

    user = UserItem(
        id=2,
        name="Teen",
        is_owner=False,
        max_content_rating="T",
        can_launch_media=True,
        can_manage_game=True,
        can_manage_media=True,
        can_manage_app=True,
    )
    mem_db_session.add(user)
    mem_db_session.commit()
    return user


@pytest.fixture
def owner():
    from backend.models.user import UserItem

    return UserItem(id=1, name="Owner", is_owner=True)


@pytest.fixture
def active_user_box(viewer):
    return {"user": viewer}


@pytest.fixture
def client(mem_db_session, tmp_path, monkeypatch, active_user_box):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import backend.api.routes.launches as launches_routes
    import backend.service.utils.settings as settings_mod
    from backend.api.routes import apps, drives, game_item_bundles, game_items, launches, profiles
    from backend.core.database import get_db
    from backend.core.dependencies import get_active_user

    monkeypatch.setattr(
        settings_mod,
        "get",
        lambda key, default=None: str(tmp_path) if key == "LIBRARY_PATH" else default,
    )
    # GET /launches/{id} resolves container_enabled from the emulator
    # catalog; irrelevant to visibility, so pin it.
    monkeypatch.setattr(launches_routes, "resolve_container_enabled", lambda slug, override: False)

    app = FastAPI()
    for module in (apps, drives, game_item_bundles, game_items, launches, profiles):
        app.include_router(module.router)
    app.dependency_overrides[get_active_user] = lambda: active_user_box["user"]
    app.dependency_overrides[get_db] = lambda: mem_db_session
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Fixtures-as-functions
# ---------------------------------------------------------------------------


def _game(db, slug, rating, **extra):
    from backend.models.game import GameItemBundle

    extra.setdefault("platform", "ps1")
    game = GameItemBundle(title=f"Game {slug}", slug=slug, content_rating=rating, **extra)
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def _game_leaf(db, game, disc_number=1):
    from backend.models.game import GameItem

    leaf = GameItem(
        game_item_bundle_id=game.id,
        disc_number=disc_number,
        file_path=f"/library/games/ps1/{game.slug}/disc{disc_number}.bin",
    )
    db.add(leaf)
    db.commit()
    db.refresh(leaf)
    return leaf


def _app(db, slug):
    from backend.models.app import AppItemBundle

    app = AppItemBundle(title=f"App {slug}", platform="ps1", slug=slug)
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def _app_leaf(db, app):
    from backend.models.app import AppItem

    leaf = AppItem(app_item_bundle_id=app.id, file_path=f"/library/apps/{app.slug}/setup.exe")
    db.add(leaf)
    db.commit()
    db.refresh(leaf)
    return leaf


def _restrict_app(db, user, app):
    from backend.models.media_restriction import MediaRestriction

    db.add(MediaRestriction(user_item_id=user.id, app_item_bundle_id=app.id))
    db.commit()


def _profile(db, slug="ps1-default"):
    from backend.models.profile import ProfileItem

    profile = ProfileItem(name=f"Profile {slug}", slug=slug, emulator_slug="duckstation", platform="ps1")
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _launch(db, **target):
    from backend.models.launch_history import LaunchHistory

    row = LaunchHistory(emulator_slug="duckstation", **target)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _drive(db, name, **owner_fk):
    from backend.models.drive import Drive

    drive = Drive(name=name, image_path=f"/library/games/dos/{name}/{name}.img", **owner_fk)
    db.add(drive)
    db.commit()
    db.refresh(drive)
    return drive


def _same_404(hidden_resp, missing_resp):
    assert hidden_resp.status_code == 404, hidden_resp.text
    assert missing_resp.status_code == 404, missing_resp.text
    assert hidden_resp.json() == missing_resp.json()


def _as(box, user):
    box["user"] = user


# ---------------------------------------------------------------------------
# Game bundle routes
# ---------------------------------------------------------------------------


class TestFlagLaunch:
    """High: can_launch_media is on by default, and this route returns the
    full bundle read."""

    def test_hidden_matches_missing_and_leaks_nothing(self, client, mem_db_session):
        from backend.models.game import GameItemBundle

        db = mem_db_session
        hidden = _game(db, "m", "M")

        hidden_resp = client.post(f"/api/v1/game-item-bundle/{hidden.id}/flag-launch")
        _same_404(hidden_resp, client.post(f"/api/v1/game-item-bundle/{_MISSING_ID}/flag-launch"))
        assert hidden.title not in hidden_resp.text
        db.expire_all()
        assert db.get(GameItemBundle, hidden.id).launch_review_flagged is False

    def test_owner_flags_a_game_hidden_from_others(self, client, mem_db_session, owner, active_user_box):
        hidden = _game(mem_db_session, "m", "M")
        _as(active_user_box, owner)

        resp = client.post(f"/api/v1/game-item-bundle/{hidden.id}/flag-launch")
        assert resp.status_code == 200, resp.text
        assert resp.json()["launch_review_flagged"] is True

    def test_visible_game_still_flags(self, client, mem_db_session):
        visible = _game(mem_db_session, "t", "T")

        resp = client.post(f"/api/v1/game-item-bundle/{visible.id}/flag-launch")
        assert resp.status_code == 200, resp.text
        assert resp.json()["launch_review_flagged"] is True


class TestVerifyBundle:
    def test_hidden_matches_missing(self, client, mem_db_session):
        hidden = _game(mem_db_session, "m", "M")
        _same_404(
            client.post(f"/api/v1/game-item-bundle/{hidden.id}/verify"),
            client.post(f"/api/v1/game-item-bundle/{_MISSING_ID}/verify"),
        )

    @pytest.mark.parametrize("who", ["owner", "visible"])
    def test_allowed_callers_succeed(self, client, mem_db_session, owner, active_user_box, who):
        # No leaves, so re-verify is a no-op loop and touches no file.
        game = _game(mem_db_session, "m", "M") if who == "owner" else _game(mem_db_session, "t", "T")
        if who == "owner":
            _as(active_user_box, owner)
        assert client.post(f"/api/v1/game-item-bundle/{game.id}/verify").status_code == 200


class TestReorder:
    def test_hidden_matches_missing_and_order_is_unchanged(self, client, mem_db_session):
        from backend.models.game import GameItem

        db = mem_db_session
        hidden = _game(db, "m", "M")
        first, second = _game_leaf(db, hidden, 1), _game_leaf(db, hidden, 2)
        body = {"disc_order": [second.id, first.id]}

        _same_404(
            client.patch(f"/api/v1/game-item-bundle/{hidden.id}/items/reorder", json=body),
            client.patch(f"/api/v1/game-item-bundle/{_MISSING_ID}/items/reorder", json=body),
        )
        db.expire_all()
        assert db.get(GameItem, first.id).disc_number == 1

    @pytest.mark.parametrize("who", ["owner", "visible"])
    def test_allowed_callers_succeed(self, client, mem_db_session, owner, active_user_box, who):
        db = mem_db_session
        game = _game(db, "m", "M") if who == "owner" else _game(db, "t", "T")
        first, second = _game_leaf(db, game, 1), _game_leaf(db, game, 2)
        if who == "owner":
            _as(active_user_box, owner)

        resp = client.patch(
            f"/api/v1/game-item-bundle/{game.id}/items/reorder", json={"disc_order": [second.id, first.id]}
        )
        assert resp.status_code == 200, resp.text


class TestBundleScopedLeafPatch:
    def test_hidden_matches_missing(self, client, mem_db_session):
        db = mem_db_session
        hidden = _game(db, "m", "M")
        leaf = _game_leaf(db, hidden)

        _same_404(
            client.patch(f"/api/v1/game-item-bundle/{hidden.id}/items/{leaf.id}", json={}),
            client.patch(f"/api/v1/game-item-bundle/{_MISSING_ID}/items/{leaf.id}", json={}),
        )

    @pytest.mark.parametrize("who", ["owner", "visible"])
    def test_allowed_callers_succeed(self, client, mem_db_session, owner, active_user_box, who):
        db = mem_db_session
        game = _game(db, "m", "M") if who == "owner" else _game(db, "t", "T")
        leaf = _game_leaf(db, game)
        if who == "owner":
            _as(active_user_box, owner)
        assert client.patch(f"/api/v1/game-item-bundle/{game.id}/items/{leaf.id}", json={}).status_code == 200


class TestLeafPatch:
    """PATCH /game-item/{leaf_id}. The hidden leaf must answer with the leaf's
    own missing detail, not the parent collection's."""

    def test_hidden_matches_missing(self, client, mem_db_session):
        leaf = _game_leaf(mem_db_session, _game(mem_db_session, "m", "M"))
        hidden_resp = client.patch(f"/api/v1/game-item/{leaf.id}", json={})
        _same_404(hidden_resp, client.patch(f"/api/v1/game-item/{_MISSING_ID}", json={}))
        assert hidden_resp.json()["detail"] == "Software item not found."

    def test_get_leaf_detail_no_longer_reveals_a_hidden_parent(self, client, mem_db_session):
        leaf = _game_leaf(mem_db_session, _game(mem_db_session, "m", "M"))
        _same_404(client.get(f"/api/v1/game-item/{leaf.id}"), client.get(f"/api/v1/game-item/{_MISSING_ID}"))

    @pytest.mark.parametrize("who", ["owner", "visible"])
    def test_allowed_callers_succeed(self, client, mem_db_session, owner, active_user_box, who):
        db = mem_db_session
        leaf = _game_leaf(db, _game(db, "m", "M") if who == "owner" else _game(db, "t", "T"))
        if who == "owner":
            _as(active_user_box, owner)
        assert client.patch(f"/api/v1/game-item/{leaf.id}", json={}).status_code == 200


class TestXisoStatus:
    def test_hidden_matches_missing_and_hides_output_path(self, client, mem_db_session):
        from backend.core import install_registry

        hidden = _game(mem_db_session, "m", "M", platform="xbox")
        install_registry.set_status(f"xiso-convert-{hidden.id}", "complete", install_path="/library/secret.iso")
        try:
            hidden_resp = client.get(f"/api/v1/game-item-bundle/{hidden.id}/convert-xiso/status")
            _same_404(hidden_resp, client.get(f"/api/v1/game-item-bundle/{_MISSING_ID}/convert-xiso/status"))
            assert "secret" not in hidden_resp.text
        finally:
            install_registry.set_status(f"xiso-convert-{hidden.id}", "idle")

    @pytest.mark.parametrize("who", ["owner", "visible"])
    def test_allowed_callers_succeed(self, client, mem_db_session, owner, active_user_box, who):
        game = _game(mem_db_session, "m", "M") if who == "owner" else _game(mem_db_session, "t", "T")
        if who == "owner":
            _as(active_user_box, owner)
        resp = client.get(f"/api/v1/game-item-bundle/{game.id}/convert-xiso/status")
        assert resp.status_code == 200, resp.text
        assert set(resp.json()) == {"status", "error", "output_path"}


# ---------------------------------------------------------------------------
# App routes (manual blocklist only)
# ---------------------------------------------------------------------------


class TestAppBundleRoutes:
    def test_patch_hidden_matches_missing(self, client, mem_db_session, viewer):
        from backend.models.app import AppItemBundle

        db = mem_db_session
        hidden = _app(db, "tool")
        _restrict_app(db, viewer, hidden)

        _same_404(
            client.patch(f"/api/v1/app-item-bundle/{hidden.id}", json={"description": "x"}),
            client.patch(f"/api/v1/app-item-bundle/{_MISSING_ID}", json={"description": "x"}),
        )
        db.expire_all()
        assert db.get(AppItemBundle, hidden.id).description is None

    def test_confirm_delete_hidden_matches_missing(self, client, mem_db_session, viewer):
        db = mem_db_session
        hidden = _app(db, "tool")
        _restrict_app(db, viewer, hidden)

        _same_404(
            client.post(f"/api/v1/app-item-bundle/{hidden.id}/confirm-delete"),
            client.post(f"/api/v1/app-item-bundle/{_MISSING_ID}/confirm-delete"),
        )

    def test_delete_hidden_matches_missing_even_with_a_valid_token(self, client, mem_db_session, viewer):
        from backend.models.app import AppItemBundle
        from backend.service.utils import confirmation_tokens

        db = mem_db_session
        hidden = _app(db, "tool")
        _restrict_app(db, viewer, hidden)
        hidden_token = confirmation_tokens.issue("app_item_bundle", hidden.id)
        missing_token = confirmation_tokens.issue("app_item_bundle", _MISSING_ID)

        _same_404(
            client.delete(f"/api/v1/app-item-bundle/{hidden.id}", params={"confirmation_token": hidden_token}),
            client.delete(f"/api/v1/app-item-bundle/{_MISSING_ID}", params={"confirmation_token": missing_token}),
        )
        assert db.get(AppItemBundle, hidden.id) is not None

    @pytest.mark.parametrize("who", ["owner", "visible"])
    def test_allowed_callers_patch_and_delete(self, client, mem_db_session, viewer, owner, active_user_box, who):
        from backend.models.app import AppItemBundle

        db = mem_db_session
        app = _app(db, "tool")
        if who == "owner":
            _restrict_app(db, viewer, app)  # hidden from the viewer, not from the owner
            _as(active_user_box, owner)

        assert client.patch(f"/api/v1/app-item-bundle/{app.id}", json={"description": "x"}).status_code == 200
        token = client.post(f"/api/v1/app-item-bundle/{app.id}/confirm-delete").json()["confirmation_token"]
        resp = client.delete(
            f"/api/v1/app-item-bundle/{app.id}",
            params={"confirmation_token": token, "delete_media": "false"},
        )
        assert resp.status_code == 204, resp.text
        assert db.get(AppItemBundle, app.id) is None


class TestAppLeafRoutes:
    @pytest.mark.parametrize("method", ["PATCH", "DELETE"])
    def test_hidden_matches_missing(self, client, mem_db_session, viewer, method):
        from backend.models.app import AppItem

        db = mem_db_session
        app = _app(db, "tool")
        leaf = _app_leaf(db, app)
        _restrict_app(db, viewer, app)
        kwargs = {"json": {}} if method == "PATCH" else {}

        hidden_resp = client.request(method, f"/api/v1/app-item/{leaf.id}", **kwargs)
        _same_404(hidden_resp, client.request(method, f"/api/v1/app-item/{_MISSING_ID}", **kwargs))
        assert hidden_resp.json()["detail"] == "App item not found."
        assert db.get(AppItem, leaf.id) is not None

    @pytest.mark.parametrize("who", ["owner", "visible"])
    def test_allowed_callers_patch_and_delete(self, client, mem_db_session, viewer, owner, active_user_box, who):
        from backend.models.app import AppItem

        db = mem_db_session
        app = _app(db, "tool")
        leaf = _app_leaf(db, app)
        if who == "owner":
            _restrict_app(db, viewer, app)
            _as(active_user_box, owner)

        assert client.patch(f"/api/v1/app-item/{leaf.id}", json={}).status_code == 200
        assert client.delete(f"/api/v1/app-item/{leaf.id}").status_code == 204
        assert db.get(AppItem, leaf.id) is None


# ---------------------------------------------------------------------------
# Profiles: listing and item_count show only games the viewer can see
# ---------------------------------------------------------------------------


class TestProfileItems:
    def _seed(self, db):
        profile = _profile(db)
        visible = _game(db, "t", "T", profile_item_id=profile.id)
        hidden = _game(db, "m", "M", profile_item_id=profile.id)
        return profile, visible, hidden

    def test_capped_user_lists_only_visible_games(self, client, mem_db_session):
        profile, visible, hidden = self._seed(mem_db_session)

        resp = client.get(f"/api/v1/profile-items/{profile.slug}/items")
        assert resp.status_code == 200, resp.text
        page = resp.json()
        assert [row["id"] for row in page["items"]] == [visible.id]
        assert page["total"] == 1
        assert hidden.title not in resp.text

    def test_item_count_matches_the_listing(self, client, mem_db_session):
        profile, _, _ = self._seed(mem_db_session)

        assert client.get(f"/api/v1/profile-items/{profile.slug}").json()["item_count"] == 1
        listed = client.get("/api/v1/profile-items").json()["items"]
        assert [p["item_count"] for p in listed if p["id"] == profile.id] == [1]

    def test_owner_lists_every_game(self, client, mem_db_session, owner, active_user_box):
        profile, visible, hidden = self._seed(mem_db_session)
        _as(active_user_box, owner)

        page = client.get(f"/api/v1/profile-items/{profile.slug}/items").json()
        assert {row["id"] for row in page["items"]} == {visible.id, hidden.id}
        assert page["total"] == 2
        assert client.get(f"/api/v1/profile-items/{profile.slug}").json()["item_count"] == 2

    def test_missing_profile_is_still_404(self, client):
        assert client.get("/api/v1/profile-items/no-such-profile/items").status_code == 404


# ---------------------------------------------------------------------------
# Launch history, single read and stop
# ---------------------------------------------------------------------------


class TestLaunchHistory:
    def _seed(self, db, viewer):
        visible_game, hidden_game = _game(db, "t", "T"), _game(db, "m", "M")
        hidden_app = _app(db, "tool")
        _restrict_app(db, viewer, hidden_app)
        rows = {
            "visible": _launch(db, game_item_bundle_id=visible_game.id),
            "hidden_game": _launch(db, game_item_bundle_id=hidden_game.id),
            "hidden_app": _launch(db, app_item_bundle_id=hidden_app.id),
        }
        return visible_game, hidden_game, rows

    def test_list_drops_hidden_targets(self, client, mem_db_session, viewer):
        _, _, rows = self._seed(mem_db_session, viewer)

        ids = {row["id"] for row in client.get("/api/v1/launches").json()}
        assert ids == {rows["visible"].id}

    def test_per_game_history_of_a_hidden_game_reads_like_a_missing_game(self, client, mem_db_session, viewer):
        visible_game, hidden_game, rows = self._seed(mem_db_session, viewer)

        hidden_resp = client.get(f"/api/v1/game-item-bundle/{hidden_game.id}/launches")
        missing_resp = client.get(f"/api/v1/game-item-bundle/{_MISSING_ID}/launches")
        assert hidden_resp.status_code == missing_resp.status_code == 200
        assert hidden_resp.json() == missing_resp.json() == []
        visible_ids = [r["id"] for r in client.get(f"/api/v1/game-item-bundle/{visible_game.id}/launches").json()]
        assert visible_ids == [rows["visible"].id]

    def test_filtered_by_target_query_on_a_hidden_target_is_empty(self, client, mem_db_session, viewer):
        _, hidden_game, _ = self._seed(mem_db_session, viewer)

        resp = client.get("/api/v1/launches", params={"target_type": "game_item_bundle", "target_id": hidden_game.id})
        assert resp.json() == []

    @pytest.mark.parametrize("key", ["hidden_game", "hidden_app"])
    def test_single_read_and_stop_hidden_matches_missing(self, client, mem_db_session, viewer, key):
        _, _, rows = self._seed(mem_db_session, viewer)
        hidden_id = rows[key].id

        _same_404(client.get(f"/api/v1/launches/{hidden_id}"), client.get(f"/api/v1/launches/{_MISSING_ID}"))
        _same_404(
            client.post(f"/api/v1/launches/{hidden_id}/stop"), client.post(f"/api/v1/launches/{_MISSING_ID}/stop")
        )

    def test_owner_sees_and_can_stop_everything(self, client, mem_db_session, viewer, owner, active_user_box):
        _, _, rows = self._seed(mem_db_session, viewer)
        _as(active_user_box, owner)

        assert {r["id"] for r in client.get("/api/v1/launches").json()} == {r.id for r in rows.values()}
        assert client.get(f"/api/v1/launches/{rows['hidden_game'].id}").status_code == 200
        resp = client.post(f"/api/v1/launches/{rows['hidden_game'].id}/stop")
        assert resp.status_code == 200
        assert resp.json() == {"stopped": False}  # nothing running in the test registry

    def test_visible_launch_still_reads_and_stops(self, client, mem_db_session, viewer):
        _, _, rows = self._seed(mem_db_session, viewer)

        assert client.get(f"/api/v1/launches/{rows['visible'].id}").status_code == 200
        assert client.post(f"/api/v1/launches/{rows['visible'].id}/stop").status_code == 200

    def test_environment_launches_are_unaffected(self, client, mem_db_session):
        from backend.models.environment import EnvironmentItem

        db = mem_db_session
        env = EnvironmentItem(name="Win98", slug="win98", platform="win98", emulator_slug="86box")
        db.add(env)
        db.commit()
        row = _launch(db, environment_item_id=env.id)

        assert row.id in {r["id"] for r in client.get("/api/v1/launches").json()}


# ---------------------------------------------------------------------------
# Drives: visible exactly when the owning game/app is
# ---------------------------------------------------------------------------


class TestDrives:
    def _seed(self, db, viewer):
        visible_game, hidden_game = _game(db, "t", "T", platform="dos"), _game(db, "m", "M", platform="dos")
        hidden_app = _app(db, "tool")
        _restrict_app(db, viewer, hidden_app)
        return {
            "visible": _drive(db, "visible", game_item_bundle_id=visible_game.id),
            "hidden_game": _drive(db, "secretgame", game_item_bundle_id=hidden_game.id),
            "hidden_app": _drive(db, "secretapp", app_item_bundle_id=hidden_app.id),
        }

    def test_list_drops_drives_of_hidden_owners(self, client, mem_db_session, viewer):
        drives = self._seed(mem_db_session, viewer)

        resp = client.get("/api/v1/drives")
        assert {d["id"] for d in resp.json()} == {drives["visible"].id}
        assert "secret" not in resp.text

    @pytest.mark.parametrize("key", ["hidden_game", "hidden_app"])
    def test_single_routes_hidden_match_missing(self, client, mem_db_session, viewer, key):
        from backend.models.drive import Drive
        from backend.service.utils import confirmation_tokens

        db = mem_db_session
        hidden_id = self._seed(db, viewer)[key].id

        _same_404(client.get(f"/api/v1/drives/{hidden_id}"), client.get(f"/api/v1/drives/{_MISSING_ID}"))
        _same_404(
            client.get(f"/api/v1/drives/{hidden_id}/confirm-token"),
            client.get(f"/api/v1/drives/{_MISSING_ID}/confirm-token"),
        )
        hidden_token = confirmation_tokens.issue("drive", hidden_id)
        missing_token = confirmation_tokens.issue("drive", _MISSING_ID)
        _same_404(
            client.delete(f"/api/v1/drives/{hidden_id}", params={"confirmation_token": hidden_token}),
            client.delete(f"/api/v1/drives/{_MISSING_ID}", params={"confirmation_token": missing_token}),
        )
        assert db.get(Drive, hidden_id) is not None

    def test_owner_sees_every_drive(self, client, mem_db_session, viewer, owner, active_user_box):
        drives = self._seed(mem_db_session, viewer)
        _as(active_user_box, owner)

        assert {d["id"] for d in client.get("/api/v1/drives").json()} == {d.id for d in drives.values()}
        assert client.get(f"/api/v1/drives/{drives['hidden_game'].id}").status_code == 200

    def test_visible_drive_still_reads_and_issues_a_token(self, client, mem_db_session, viewer):
        drives = self._seed(mem_db_session, viewer)

        assert client.get(f"/api/v1/drives/{drives['visible'].id}").status_code == 200
        assert client.get(f"/api/v1/drives/{drives['visible'].id}/confirm-token").status_code == 200
