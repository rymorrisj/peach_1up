"""Tests for backend/core/dependencies.py — the parental-control enforcement
layer (max_content_rating + block_unrated_media + MediaRestriction).

Per dev_docs/v2/09_test_coverage.md item 1, this was the highest-risk
zero-coverage gap in the codebase: the server-side enforcement of content
rating ceilings on SoftwareCollection visibility. Functions under test:
get_filtered_collections, get_filtered_collection, validate_max_content_rating,
rating_change_requires_confirmation, normalize_content_rating,
_load_rating_ordinals / _derive_rating_ordinals.
"""

import pytest


# ---------------------------------------------------------------------------
# Ordinal math — single scheme
# ---------------------------------------------------------------------------


class TestRatingOrdinals:
    def test_esrb_ordering_is_severity_increasing(self):
        from backend.core.dependencies import _BASE_RATING_ORDINALS

        assert _BASE_RATING_ORDINALS["EC"] < _BASE_RATING_ORDINALS["E"]
        assert _BASE_RATING_ORDINALS["E"] < _BASE_RATING_ORDINALS["E10+"]
        assert _BASE_RATING_ORDINALS["E10+"] < _BASE_RATING_ORDINALS["T"]
        assert _BASE_RATING_ORDINALS["T"] < _BASE_RATING_ORDINALS["M"]
        assert _BASE_RATING_ORDINALS["M"] < _BASE_RATING_ORDINALS["AO"]

    def test_pegi_ordering_is_severity_increasing(self):
        from backend.core.dependencies import _BASE_RATING_ORDINALS

        assert _BASE_RATING_ORDINALS["PEGI 3"] < _BASE_RATING_ORDINALS["PEGI 7"]
        assert _BASE_RATING_ORDINALS["PEGI 7"] < _BASE_RATING_ORDINALS["PEGI 12"]
        assert _BASE_RATING_ORDINALS["PEGI 12"] < _BASE_RATING_ORDINALS["PEGI 16"]
        assert _BASE_RATING_ORDINALS["PEGI 16"] < _BASE_RATING_ORDINALS["PEGI 18"]

    def test_each_scheme_ordinal_ladder_restarts_at_zero(self):
        """ESRB and PEGI are independent ladders — PEGI's first value is not
        offset by ESRB's length. Confirms _derive_rating_ordinals groups by
        scheme rather than assigning one flat sequence across CONTENT_RATINGS."""
        from backend.core.dependencies import _BASE_RATING_ORDINALS

        assert _BASE_RATING_ORDINALS["EC"] == 0
        assert _BASE_RATING_ORDINALS["PEGI 3"] == 0

    def test_load_rating_ordinals_falls_back_to_base_when_settings_unavailable(self):
        """_load_rating_ordinals must fail closed to the restrictive default
        vocabulary, never raise, when app_settings isn't reachable yet."""
        from backend.core.dependencies import _BASE_RATING_ORDINALS, _load_rating_ordinals

        # No monkeypatch here: backend.core.settings.get_settings() raises
        # RuntimeError before app init in a bare unit-test process, exercising
        # the fallback path for real rather than simulating it.
        assert _load_rating_ordinals() == _BASE_RATING_ORDINALS

    def test_load_rating_ordinals_uses_app_settings_override_when_present(self, monkeypatch):
        import backend.core.settings as settings_mod

        class _Settings:
            def get(self, key, default=None):
                if key == "rating_ordinals":
                    return {"E": 0, "M": 1}
                return default

        monkeypatch.setattr(settings_mod, "get_settings", lambda: _Settings())

        from backend.core.dependencies import _load_rating_ordinals

        assert _load_rating_ordinals() == {"E": 0, "M": 1}

    def test_load_rating_ordinals_falls_back_on_malformed_override(self, monkeypatch):
        """A non-dict or otherwise malformed override must not widen access —
        fall back to the safe default rather than raising or passing through."""
        import backend.core.settings as settings_mod
        from backend.core.dependencies import _BASE_RATING_ORDINALS

        class _Settings:
            def get(self, key, default=None):
                return "not-a-dict"

        monkeypatch.setattr(settings_mod, "get_settings", lambda: _Settings())

        from backend.core.dependencies import _load_rating_ordinals

        assert _load_rating_ordinals() == _BASE_RATING_ORDINALS


# ---------------------------------------------------------------------------
# Cross-scheme comparison via rating_change_requires_confirmation
# ---------------------------------------------------------------------------


class TestRatingChangeRequiresConfirmation:
    def test_same_scheme_lowering_requires_confirmation(self):
        from backend.core.dependencies import rating_change_requires_confirmation

        assert rating_change_requires_confirmation("M", "T") is True

    def test_same_scheme_raising_does_not_require_confirmation(self):
        from backend.core.dependencies import rating_change_requires_confirmation

        assert rating_change_requires_confirmation("T", "M") is False

    def test_same_value_no_change_does_not_require_confirmation(self):
        from backend.core.dependencies import rating_change_requires_confirmation

        assert rating_change_requires_confirmation("M", "M") is False

    def test_old_none_never_requires_confirmation(self):
        """Nothing was set before, so there's nothing to protect from lowering."""
        from backend.core.dependencies import rating_change_requires_confirmation

        assert rating_change_requires_confirmation(None, "AO") is False

    def test_clearing_a_set_rating_requires_confirmation(self):
        from backend.core.dependencies import rating_change_requires_confirmation

        assert rating_change_requires_confirmation("M", None) is True

    def test_cross_scheme_change_requires_confirmation_even_if_nominally_lower_ordinal(self):
        """ESRB M (ordinal 4) -> PEGI 3 (ordinal 0) looks like a drop by ordinal
        value alone, but the schemes aren't comparable — must still require
        confirmation rather than being treated as a safe raise because the
        raw ordinal happens to be smaller."""
        from backend.core.dependencies import rating_change_requires_confirmation

        assert rating_change_requires_confirmation("M", "PEGI 3") is True

    def test_cross_scheme_change_requires_confirmation_even_when_ordinal_would_look_like_a_raise(self):
        from backend.core.dependencies import rating_change_requires_confirmation

        assert rating_change_requires_confirmation("PEGI 3", "M") is True

    def test_unknown_new_value_requires_confirmation(self):
        from backend.core.dependencies import rating_change_requires_confirmation

        assert rating_change_requires_confirmation("T", "NOT-A-REAL-RATING") is True

    def test_unknown_old_value_requires_confirmation(self):
        from backend.core.dependencies import rating_change_requires_confirmation

        assert rating_change_requires_confirmation("NOT-A-REAL-RATING", "T") is True


# ---------------------------------------------------------------------------
# normalize_content_rating — leading-token parsing
# ---------------------------------------------------------------------------


class TestNormalizeContentRating:
    def test_exact_known_value_passes_through(self):
        from backend.core.dependencies import normalize_content_rating

        assert normalize_content_rating("M") == "M"

    def test_leading_token_with_dash_and_label(self):
        from backend.core.dependencies import normalize_content_rating

        assert normalize_content_rating("M - Mature 17+") == "M"

    def test_leading_token_with_en_dash(self):
        from backend.core.dependencies import normalize_content_rating

        assert normalize_content_rating("E10+ – Everyone 10+") == "E10+"

    def test_leading_token_with_colon(self):
        from backend.core.dependencies import normalize_content_rating

        # "ESRB" is not itself a rating value, so this is expected to fail to
        # resolve, but exercises the colon-splitting branch specifically.
        assert normalize_content_rating("ESRB: T") is None

    def test_mixed_case_is_normalized(self):
        from backend.core.dependencies import normalize_content_rating

        assert normalize_content_rating("m") == "M"
        assert normalize_content_rating("pegi 18") == "PEGI 18"

    def test_extra_surrounding_whitespace_is_stripped(self):
        from backend.core.dependencies import normalize_content_rating

        assert normalize_content_rating("   T   ") == "T"

    def test_none_input_returns_none(self):
        from backend.core.dependencies import normalize_content_rating

        assert normalize_content_rating(None) is None

    def test_empty_or_whitespace_only_returns_none(self):
        from backend.core.dependencies import normalize_content_rating

        assert normalize_content_rating("") is None
        assert normalize_content_rating("   ") is None

    def test_malformed_unparseable_string_returns_none_not_a_guess(self):
        from backend.core.dependencies import normalize_content_rating

        assert normalize_content_rating("totally-not-a-rating") is None


# ---------------------------------------------------------------------------
# validate_max_content_rating
# ---------------------------------------------------------------------------


class TestValidateMaxContentRating:
    def test_known_value_is_returned_unchanged(self):
        from backend.core.dependencies import validate_max_content_rating

        assert validate_max_content_rating("T") == "T"

    def test_none_means_no_ceiling_and_passes(self):
        from backend.core.dependencies import validate_max_content_rating

        assert validate_max_content_rating(None) is None

    def test_unknown_value_raises_value_error(self):
        """Regression lock: an unrecognised max_content_rating must be rejected
        at write time. If it were allowed through, get_filtered_collections'
        ordinal lookup would return None for it and skip the rating filter
        entirely — silently uncapping the account."""
        from backend.core.dependencies import validate_max_content_rating

        with pytest.raises(ValueError):
            validate_max_content_rating("NOT-A-REAL-RATING")


# ---------------------------------------------------------------------------
# get_filtered_collections / get_filtered_collection — DB-backed unit tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mem_db_session():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, Session, create_engine
    import backend.models  # noqa: F401 — registers all table models with SQLModel.metadata

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_collection(db, **overrides):
    from backend.models.software import SoftwareCollection

    kwargs = dict(title="Doom", file_path="/library/games/dos/doom", era="dos", slug="doom")
    kwargs.update(overrides)
    collection = SoftwareCollection(**kwargs)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


def _make_user(db, **overrides):
    from backend.models.user import User

    kwargs = dict(name="Kid", is_owner=False, is_admin=False)
    kwargs.update(overrides)
    user = User(**kwargs)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestGetFilteredCollectionsOwnerBypass:
    def test_owner_sees_everything_including_unrated_and_restricted(self, mem_db_session):
        from backend.core.dependencies import get_filtered_collections
        from backend.models.media_restriction import MediaRestriction
        from backend.models.user import User

        owner = _make_user(mem_db_session, name="Owner", is_owner=True)
        unrated = _make_collection(mem_db_session, slug="unrated", content_rating=None)
        restricted = _make_collection(mem_db_session, slug="restricted", content_rating="E")
        mem_db_session.add(MediaRestriction(user_id=owner.id, software_collection_id=restricted.id))
        mem_db_session.commit()

        results = get_filtered_collections(owner, mem_db_session).all()
        ids = {c.id for c in results}
        assert unrated.id in ids
        assert restricted.id in ids


class TestGetFilteredCollectionsUnknownRatingDenies:
    def test_unrecognised_content_rating_is_denied_not_passed_through(self, mem_db_session):
        """Regression lock for the previously-fixed uncap bug: a collection
        whose content_rating string doesn't resolve to any known ordinal must
        be EXCLUDED for a capped account, not treated as unrestricted."""
        from backend.core.dependencies import get_filtered_collections

        capped = _make_user(mem_db_session, max_content_rating="T")
        unknown_rated = _make_collection(mem_db_session, slug="mystery", content_rating="TOTALLY-UNKNOWN-RATING")
        allowed = _make_collection(mem_db_session, slug="allowed", content_rating="E")

        results = get_filtered_collections(capped, mem_db_session).all()
        ids = {c.id for c in results}

        assert unknown_rated.id not in ids
        assert allowed.id in ids

    def test_rating_above_ceiling_is_denied(self, mem_db_session):
        from backend.core.dependencies import get_filtered_collections

        capped = _make_user(mem_db_session, max_content_rating="T")
        over_rated = _make_collection(mem_db_session, slug="over", content_rating="M")

        results = get_filtered_collections(capped, mem_db_session).all()
        assert over_rated.id not in {c.id for c in results}

    def test_rating_at_or_below_ceiling_is_allowed(self, mem_db_session):
        from backend.core.dependencies import get_filtered_collections

        capped = _make_user(mem_db_session, max_content_rating="T")
        at_ceiling = _make_collection(mem_db_session, slug="at-ceiling", content_rating="T")
        below_ceiling = _make_collection(mem_db_session, slug="below", content_rating="E")

        results = get_filtered_collections(capped, mem_db_session).all()
        ids = {c.id for c in results}
        assert at_ceiling.id in ids
        assert below_ceiling.id in ids

    def test_null_or_empty_rating_is_governed_by_block_unrated_media_not_the_ceiling(self, mem_db_session):
        """Null/empty content_rating bypasses the ceiling filter's OR clause by
        design — it is gated separately by block_unrated_media."""
        from backend.core.dependencies import get_filtered_collections

        capped_allows_unrated = _make_user(
            mem_db_session, max_content_rating="E", block_unrated_media=False,
        )
        unrated = _make_collection(mem_db_session, slug="unrated", content_rating=None)

        results = get_filtered_collections(capped_allows_unrated, mem_db_session).all()
        assert unrated.id in {c.id for c in results}

    def test_block_unrated_media_excludes_null_and_empty_ratings(self, mem_db_session):
        from backend.core.dependencies import get_filtered_collections

        capped = _make_user(mem_db_session, block_unrated_media=True)
        null_rated = _make_collection(mem_db_session, slug="null-rated", content_rating=None)
        empty_rated = _make_collection(mem_db_session, slug="empty-rated", content_rating="")
        rated = _make_collection(mem_db_session, slug="rated", content_rating="E")

        results = get_filtered_collections(capped, mem_db_session).all()
        ids = {c.id for c in results}
        assert null_rated.id not in ids
        assert empty_rated.id not in ids
        assert rated.id in ids

    def test_media_restriction_excludes_regardless_of_rating(self, mem_db_session):
        from backend.core.dependencies import get_filtered_collections
        from backend.models.media_restriction import MediaRestriction

        capped = _make_user(mem_db_session)
        restricted = _make_collection(mem_db_session, slug="restricted", content_rating="E")
        mem_db_session.add(MediaRestriction(user_id=capped.id, software_collection_id=restricted.id))
        mem_db_session.commit()

        results = get_filtered_collections(capped, mem_db_session).all()
        assert restricted.id not in {c.id for c in results}


class TestGetFilteredCollectionsUnresolvableOwnCeilingFailsClosed:
    def test_orphaned_own_max_content_rating_denies_all_rated_content(self, mem_db_session, monkeypatch):
        """Regression lock: if the CALLER's own max_content_rating can no longer
        be resolved to a known ordinal (e.g. a rating_ordinals settings change
        orphaned a value that was valid when it was set), the ceiling must fail
        closed — no rated content passes — rather than silently skipping the
        rating filter and uncapping the account (the previous fail-open bug)."""
        import backend.core.dependencies as deps

        # "AO" is valid against the base ordinal map, so user creation succeeds
        # normally (validate_max_content_rating resolves it at write time).
        capped = _make_user(mem_db_session, max_content_rating="AO")
        rated = _make_collection(mem_db_session, slug="rated", content_rating="E")
        unrated = _make_collection(mem_db_session, slug="unrated", content_rating=None)

        # Simulate a rating_ordinals settings change made after the ceiling was
        # set: the custom map no longer contains "AO" at all.
        monkeypatch.setattr(deps, "_load_rating_ordinals", lambda: {"E": 0, "T": 1})

        results = deps.get_filtered_collections(capped, mem_db_session).all()
        ids = {c.id for c in results}

        assert rated.id not in ids
        # Null/empty ratings remain governed separately by block_unrated_media,
        # unaffected by the ceiling being unresolvable.
        assert unrated.id in ids


class TestGetFilteredCollection:
    def test_visible_collection_returned_by_id(self, mem_db_session):
        from backend.core.dependencies import get_filtered_collection

        capped = _make_user(mem_db_session, max_content_rating="T")
        allowed = _make_collection(mem_db_session, slug="allowed", content_rating="E")

        result = get_filtered_collection(allowed.id, capped, mem_db_session)
        assert result.id == allowed.id

    def test_visible_collection_returned_by_slug(self, mem_db_session):
        from backend.core.dependencies import get_filtered_collection

        capped = _make_user(mem_db_session, max_content_rating="T")
        allowed = _make_collection(mem_db_session, slug="allowed", content_rating="E")

        result = get_filtered_collection("allowed", capped, mem_db_session)
        assert result.id == allowed.id

    def test_over_rated_collection_raises_404(self, mem_db_session):
        from fastapi import HTTPException
        from backend.core.dependencies import get_filtered_collection

        capped = _make_user(mem_db_session, max_content_rating="T")
        over_rated = _make_collection(mem_db_session, slug="over", content_rating="M")

        with pytest.raises(HTTPException) as exc_info:
            get_filtered_collection(over_rated.id, capped, mem_db_session)
        assert exc_info.value.status_code == 404

    def test_nonexistent_collection_also_raises_404_same_as_filtered(self, mem_db_session):
        """404 must be indistinguishable between 'does not exist' and 'exists
        but filtered out' — that's the whole point of not leaking existence."""
        from fastapi import HTTPException
        from backend.core.dependencies import get_filtered_collection

        capped = _make_user(mem_db_session, max_content_rating="T")

        with pytest.raises(HTTPException) as exc_info:
            get_filtered_collection(999999, capped, mem_db_session)
        assert exc_info.value.status_code == 404

    def test_unknown_rating_collection_raises_404_via_single_collection_lookup(self, mem_db_session):
        from fastapi import HTTPException
        from backend.core.dependencies import get_filtered_collection

        capped = _make_user(mem_db_session, max_content_rating="T")
        unknown_rated = _make_collection(mem_db_session, slug="mystery", content_rating="TOTALLY-UNKNOWN-RATING")

        with pytest.raises(HTTPException) as exc_info:
            get_filtered_collection(unknown_rated.id, capped, mem_db_session)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# HTTP route-level tests — list and detail endpoints, no-leak-via-404
# ---------------------------------------------------------------------------


@pytest.fixture
def http_client(mem_db_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes import software_collections
    from backend.core.database import get_db

    app = FastAPI()
    app.include_router(software_collections.router)
    app.dependency_overrides[get_db] = lambda: mem_db_session

    with TestClient(app) as c:
        yield c, mem_db_session, app


def _set_active_user(app, user):
    from backend.core.dependencies import get_active_user

    app.dependency_overrides[get_active_user] = lambda: user


class TestSoftwareListRouteFiltering:
    def test_over_rated_item_absent_from_list_payload_no_error_leak(self, http_client):
        """GET /api/v1/software for a capped sub-account: the over-rated item
        is simply missing from the page, not surfaced with a 403 or any
        other differentiated error — filtering, not denial-with-explanation."""
        c, db, app = http_client
        capped = _make_user(db, max_content_rating="T")
        allowed = _make_collection(db, slug="allowed", content_rating="E")
        over_rated = _make_collection(db, slug="over-rated", content_rating="M")
        _set_active_user(app, capped)

        resp = c.get("/api/v1/software")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = {item["id"] for item in body["items"]}
        assert allowed.id in ids
        assert over_rated.id not in ids

    def test_unknown_rated_item_absent_from_list_payload(self, http_client):
        c, db, app = http_client
        capped = _make_user(db, max_content_rating="T")
        unknown_rated = _make_collection(db, slug="mystery", content_rating="TOTALLY-UNKNOWN-RATING")
        _set_active_user(app, capped)

        resp = c.get("/api/v1/software")
        assert resp.status_code == 200, resp.text
        ids = {item["id"] for item in resp.json()["items"]}
        assert unknown_rated.id not in ids


class TestSoftwareCollectionDetailRouteNoLeak:
    def test_over_rated_collection_returns_404_not_403(self, http_client):
        c, db, app = http_client
        capped = _make_user(db, max_content_rating="T")
        over_rated = _make_collection(db, slug="over-rated", content_rating="M")
        _set_active_user(app, capped)

        resp = c.get(f"/api/v1/softwarecollection/{over_rated.id}")
        assert resp.status_code == 404
        assert resp.status_code != 403

    def test_over_rated_collection_404_matches_nonexistent_id_404(self, http_client):
        """No leak via error differentiation: a filtered-out real ID and a
        nonexistent ID must produce the same status and error shape."""
        c, db, app = http_client
        capped = _make_user(db, max_content_rating="T")
        over_rated = _make_collection(db, slug="over-rated", content_rating="M")
        _set_active_user(app, capped)

        filtered_resp = c.get(f"/api/v1/softwarecollection/{over_rated.id}")
        missing_resp = c.get("/api/v1/softwarecollection/999999")

        assert filtered_resp.status_code == missing_resp.status_code == 404
        assert filtered_resp.json() == missing_resp.json()

    def test_allowed_collection_returns_200(self, http_client):
        c, db, app = http_client
        capped = _make_user(db, max_content_rating="T")
        allowed = _make_collection(db, slug="allowed", content_rating="E")
        _set_active_user(app, capped)

        resp = c.get(f"/api/v1/softwarecollection/{allowed.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == allowed.id
