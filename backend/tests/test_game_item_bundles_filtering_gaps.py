"""Route-level (TestClient/HTTP) tests closing the remaining gaps in the
parental-control filtering surface of backend/api/routes/game_item_bundles.py.

test_dependencies_content_rating.py already covers HTTP-level max_content_rating
and MediaRestriction filtering for GET /game-items (list) and
GET /game-item-bundle/{id} (detail), plus owner bypass on the detail route.
This file does not repeat that coverage. It closes what was still missing
after reading both existing suites:

    - block_unrated_media exclusion, exercised over TestClient (only
      unit-tested directly against get_filtered_game_item_bundles before)
    - the list route's own query filters (era, tag, profile_assigned) chained
      on top of the parental-control base query, confirming a restricted or
      over-rated item stays excluded even when it would otherwise match an
      additional filter, not just that the unfiltered list works
    - owner bypass on the LIST route specifically (only detail route was
      HTTP-tested for this)
    - GET .../by-slug/{slug} combined with the manual MediaRestriction
      blocklist (only content_rating was covered for by-slug)
    - Page.total reflecting the post-filter, post-restriction count under
      pagination, not the raw table count

Uses the same in-memory SQLModel SQLite DB + StaticPool +
get_active_user/get_db dependency-override pattern as the other
game_item_bundles route test files.
"""

import pytest


@pytest.fixture
def mem_db_session():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, Session, create_engine
    import backend.models  # noqa: F401, registers all table models with SQLModel.metadata

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_user(db, **overrides):
    from backend.models.user import UserItem

    kwargs = dict(name="UserItem", is_owner=False, is_admin=False)
    kwargs.update(overrides)
    user = UserItem(**kwargs)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_collection(db, **overrides):
    from backend.models.game import GameItemBundle

    kwargs = dict(title="Doom", file_path="/library/games/dos/doom", era="dos", slug="doom")
    kwargs.update(overrides)
    collection = GameItemBundle(**kwargs)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


def _restrict(db, user, collection):
    from backend.models.media_restriction import MediaRestriction

    restriction = MediaRestriction(user_item_id=user.id, game_item_bundle_id=collection.id)
    db.add(restriction)
    db.commit()


def _tag(db, collection, name):
    from backend.models.tag import Tag, EntityTag

    # Reuse an existing tag by name instead of always creating one, same
    # name lookup tags.py's create_tag does, tag names are unique so two
    # collections tagged with the same name must share one Tag row.
    tag = db.query(Tag).filter(Tag.name == name).first()
    if tag is None:
        tag = Tag(name=name)
        db.add(tag)
        db.commit()
        db.refresh(tag)
    db.add(EntityTag(tag_id=tag.id, entity_type="game_item_bundle", entity_id=collection.id))
    db.commit()


@pytest.fixture
def http_client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import game_item_bundles
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(game_item_bundles.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session, app


def _set_active_user(app, user):
    from backend.core.dependencies import get_active_user

    app.dependency_overrides[get_active_user] = lambda: user


# ---------------------------------------------------------------------------
# block_unrated_media, HTTP level (only unit-tested against
# get_filtered_game_item_bundles directly before this)
# ---------------------------------------------------------------------------


class TestBlockUnratedMediaHttpLevel:
    def test_unrated_item_absent_from_list_payload_when_blocked(self, http_client):
        c, db, app = http_client
        blocking = _make_user(db, block_unrated_media=True)
        unrated = _make_collection(db, slug="unrated", content_rating=None)
        rated = _make_collection(db, slug="rated", content_rating="E")
        _set_active_user(app, blocking)

        resp = c.get("/api/v1/game-items")

        assert resp.status_code == 200, resp.text
        ids = {item["id"] for item in resp.json()["items"]}
        assert unrated.id not in ids
        assert rated.id in ids

    def test_empty_string_rating_also_excluded_when_blocked(self, http_client):
        c, db, app = http_client
        blocking = _make_user(db, block_unrated_media=True)
        empty_rated = _make_collection(db, slug="empty-rated", content_rating="")
        _set_active_user(app, blocking)

        resp = c.get("/api/v1/game-items")

        assert resp.status_code == 200, resp.text
        ids = {item["id"] for item in resp.json()["items"]}
        assert empty_rated.id not in ids

    def test_unrated_item_visible_when_not_blocked(self, http_client):
        c, db, app = http_client
        non_blocking = _make_user(db, block_unrated_media=False)
        unrated = _make_collection(db, slug="unrated", content_rating=None)
        _set_active_user(app, non_blocking)

        resp = c.get("/api/v1/game-items")

        assert resp.status_code == 200, resp.text
        ids = {item["id"] for item in resp.json()["items"]}
        assert unrated.id in ids

    def test_unrated_item_404s_on_detail_route_when_blocked(self, http_client):
        c, db, app = http_client
        blocking = _make_user(db, block_unrated_media=True)
        unrated = _make_collection(db, slug="unrated", content_rating=None)
        _set_active_user(app, blocking)

        resp = c.get(f"/api/v1/game-item-bundle/{unrated.id}")

        assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# List route's own filters (era, tag, profile_assigned) chained on top of
# the parental-control base query: a restricted/over-rated item must stay
# excluded even when it would otherwise match the additional filter.
# ---------------------------------------------------------------------------


class TestListFiltersStayScopedToParentalControlBaseQuery:
    def test_era_filter_does_not_leak_a_restricted_item_matching_that_era(self, http_client):
        c, db, app = http_client
        user = _make_user(db)
        allowed = _make_collection(db, slug="allowed", era="dos", content_rating="E")
        restricted = _make_collection(db, slug="restricted", era="dos", content_rating="E")
        _restrict(db, user, restricted)
        _set_active_user(app, user)

        resp = c.get("/api/v1/game-items", params={"era": "dos"})

        assert resp.status_code == 200, resp.text
        ids = {item["id"] for item in resp.json()["items"]}
        assert allowed.id in ids
        assert restricted.id not in ids

    def test_tag_filter_does_not_leak_an_over_rated_item_carrying_that_tag(self, http_client):
        c, db, app = http_client
        capped = _make_user(db, max_content_rating="E")
        allowed = _make_collection(db, slug="allowed", content_rating="E")
        over_rated = _make_collection(db, slug="over-rated", content_rating="M")
        _tag(db, allowed, "favorites")
        _tag(db, over_rated, "favorites")
        _set_active_user(app, capped)

        resp = c.get("/api/v1/game-items", params={"tag": "favorites"})

        assert resp.status_code == 200, resp.text
        ids = {item["id"] for item in resp.json()["items"]}
        assert allowed.id in ids
        assert over_rated.id not in ids

    def test_profile_assigned_filter_does_not_leak_a_restricted_item(self, http_client):
        c, db, app = http_client
        user = _make_user(db)
        allowed = _make_collection(db, slug="allowed", content_rating="E", profile_item_id=None)
        restricted = _make_collection(db, slug="restricted", content_rating="E", profile_item_id=None)
        _restrict(db, user, restricted)
        _set_active_user(app, user)

        resp = c.get("/api/v1/game-items", params={"profile_assigned": "false"})

        assert resp.status_code == 200, resp.text
        ids = {item["id"] for item in resp.json()["items"]}
        assert allowed.id in ids
        assert restricted.id not in ids


# ---------------------------------------------------------------------------
# Owner bypass on the LIST route specifically (detail route's owner bypass
# is already covered by test_dependencies_content_rating.py)
# ---------------------------------------------------------------------------


class TestOwnerBypassOnListRoute:
    def test_owner_sees_restricted_and_unrated_items_in_list(self, http_client):
        c, db, app = http_client
        owner = _make_user(db, is_owner=True)
        other = _make_user(db, name="other")
        restricted = _make_collection(db, slug="restricted", content_rating="E")
        unrated = _make_collection(db, slug="unrated", content_rating=None)
        _restrict(db, other, restricted)
        _set_active_user(app, owner)

        resp = c.get("/api/v1/game-items")

        assert resp.status_code == 200, resp.text
        ids = {item["id"] for item in resp.json()["items"]}
        assert restricted.id in ids
        assert unrated.id in ids


# ---------------------------------------------------------------------------
# by-slug + manual MediaRestriction blocklist (only content_rating was
# covered for by-slug in test_game_item_bundles_gaps_routes.py)
# ---------------------------------------------------------------------------


class TestGetBySlugRestrictionFiltering:
    def test_restricted_bundle_404s_by_slug_same_as_by_id(self, http_client):
        c, db, app = http_client
        user = _make_user(db)
        restricted = _make_collection(db, slug="restricted", content_rating="E")
        _restrict(db, user, restricted)
        _set_active_user(app, user)

        resp = c.get(f"/api/v1/game-item-bundle/by-slug/{restricted.slug}")

        assert resp.status_code == 404, resp.text

    def test_owner_bypasses_restriction_by_slug(self, http_client):
        c, db, app = http_client
        owner = _make_user(db, is_owner=True)
        other = _make_user(db, name="other")
        restricted = _make_collection(db, slug="restricted", content_rating="E")
        _restrict(db, other, restricted)
        _set_active_user(app, owner)

        resp = c.get(f"/api/v1/game-item-bundle/by-slug/{restricted.slug}")

        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == restricted.id


# ---------------------------------------------------------------------------
# Page.total reflects the post-filter, post-restriction count under
# pagination, not the raw table count (list_game_items builds `total` from
# the same query object the filters are chained onto, before offset/limit
# are applied; a regression that computed total from an unfiltered query, or
# from a query built before the parental-control filters were chained on,
# would leak the true item count to a restricted account even though the
# items themselves stay hidden).
# ---------------------------------------------------------------------------


class TestPageTotalReflectsFilteredCountUnderPagination:
    def test_total_excludes_restricted_items_even_when_page_is_truncated_by_limit(self, http_client):
        c, db, app = http_client
        user = _make_user(db)
        first = _make_collection(db, slug="first", content_rating="E")
        second = _make_collection(db, slug="second", content_rating="E")
        restricted = _make_collection(db, slug="restricted", content_rating="E")
        _restrict(db, user, restricted)
        _set_active_user(app, user)

        resp = c.get("/api/v1/game-items", params={"limit": 1})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["items"]) == 1
        # Two visible collections (first, second) exist for this user, the
        # restricted third must never be counted in total.
        assert body["total"] == 2

    def test_total_excludes_over_rated_items(self, http_client):
        c, db, app = http_client
        capped = _make_user(db, max_content_rating="E")
        allowed = _make_collection(db, slug="allowed", content_rating="E")
        over_rated = _make_collection(db, slug="over-rated", content_rating="M")
        _set_active_user(app, capped)

        resp = c.get("/api/v1/game-items")

        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 1
