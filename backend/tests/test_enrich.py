"""Tests for backend.service.games.enrich.enrich_game_bundle: selective
field application, the rating confirmation guard, provider-sourced link
replacement, metadata_fetched_at stamping, and that the per-disc cover fetch
is gone while game delete still sweeps old app-owned disc covers.

Route-level wiring (403 gates, the 409 over HTTP) is in
test_game_metadata_routes.py.
"""
import pytest


@pytest.fixture
def mem_session():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, Session, create_engine
    import backend.models  # noqa: F401, registers all table models

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _bundle(db, **fields):
    from backend.models.game import GameItemBundle

    bundle = GameItemBundle(title="Doom", platform="dos", slug="doom", **fields)
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    return bundle


def _enrich(db, bundle, fields, **kwargs):
    from backend.service.games.enrich import enrich_game_bundle

    return enrich_game_bundle(bundle.id, fields, db=db, **kwargs)


class TestEnrichGameBundle:
    def test_missing_bundle_is_404(self, mem_session):
        from fastapi import HTTPException
        from backend.service.games.enrich import enrich_game_bundle

        with pytest.raises(HTTPException) as exc_info:
            enrich_game_bundle(9999, {"title": "New Title"}, db=mem_session)
        assert exc_info.value.status_code == 404

    @pytest.mark.parametrize("title", [None, "", "   "])
    def test_title_cannot_be_cleared(self, mem_session, title):
        from fastapi import HTTPException

        bundle = _bundle(mem_session)

        with pytest.raises(HTTPException) as exc_info:
            _enrich(mem_session, bundle, {"title": title})
        assert exc_info.value.status_code == 422
        assert bundle.title == "Doom"

    def test_per_disc_cover_flow_is_gone(self):
        import inspect

        from backend.api.routes.game_metadata import EnrichBody
        from backend.service.games import enrich as enrich_mod

        assert "cover_art_url" not in inspect.signature(enrich_mod.enrich_game_bundle).parameters
        assert "cover_art_url" not in EnrichBody.model_fields
        assert not hasattr(enrich_mod, "_fetch_leaf_cover")
        assert not hasattr(enrich_mod, "enrich_entity")


class TestSelectiveFields:
    def test_omitted_fields_stay_unchanged(self, mem_session):
        from backend.models.metadata_lookup import get_genres_for_game_item_bundle, set_genres_for_game_item_bundle

        bundle = _bundle(
            mem_session, description="Demons.", publisher="id", developer="id Software", year=1993,
            content_rating="M", external_game_id=55, metadata_source="IGDB",
            external_links=[{"type": "trailer", "url": "https://example.com/t"}],
        )
        set_genres_for_game_item_bundle(mem_session, bundle.id, ["Shooter"])
        mem_session.commit()

        entity = _enrich(mem_session, bundle, {"title": "Doom (1993)"})

        assert entity.title == "Doom (1993)"
        assert (entity.description, entity.publisher, entity.developer, entity.year) == (
            "Demons.", "id", "id Software", 1993,
        )
        assert (entity.content_rating, entity.external_game_id, entity.metadata_source) == ("M", 55, "IGDB")
        assert entity.external_links == [{"type": "trailer", "url": "https://example.com/t"}]
        assert get_genres_for_game_item_bundle(bundle.id, mem_session) == ["Shooter"]

    def test_a_field_sent_as_null_is_cleared(self, mem_session):
        bundle = _bundle(mem_session, description="Demons.", year=1993)

        entity = _enrich(mem_session, bundle, {"description": None})

        assert entity.description is None
        assert entity.year == 1993

    def test_genre_list_replaces_and_empty_list_clears(self, mem_session):
        from backend.models.metadata_lookup import get_genres_for_game_item_bundle

        bundle = _bundle(mem_session)
        _enrich(mem_session, bundle, {"genre": ["Shooter", "Action"]})
        assert sorted(get_genres_for_game_item_bundle(bundle.id, mem_session)) == ["Action", "Shooter"]

        _enrich(mem_session, bundle, {"genre": []})
        assert get_genres_for_game_item_bundle(bundle.id, mem_session) == []

    def test_provider_name_is_stored_canonically(self, mem_session):
        bundle = _bundle(mem_session)

        assert _enrich(mem_session, bundle, {"metadata_source": "thegamesdb"}).metadata_source == "TheGamesDB"
        assert _enrich(mem_session, bundle, {"metadata_source": "My notes"}).metadata_source == "My notes"


class TestRatingGuard:
    def test_lowering_without_confirm_is_a_structured_409_and_applies_nothing(self, mem_session):
        from fastapi import HTTPException

        bundle = _bundle(mem_session, content_rating="M", description="old")

        with pytest.raises(HTTPException) as exc_info:
            _enrich(mem_session, bundle, {"description": "new", "content_rating": "E"})

        assert exc_info.value.status_code == 409
        detail = exc_info.value.detail
        assert detail["error_type"] == "rating_change_requires_confirmation"
        assert (detail["reason"], detail["current_rating"], detail["new_rating"]) == ("lowered", "M", "E")
        mem_session.refresh(bundle)
        assert (bundle.content_rating, bundle.description) == ("M", "old")

    def test_confirmed_change_applies_with_the_other_fields(self, mem_session):
        bundle = _bundle(mem_session, content_rating="M", description="old")

        entity = _enrich(mem_session, bundle, {"description": "new", "content_rating": "E"}, confirm_rating_change=True)

        assert (entity.content_rating, entity.description) == ("E", "new")

    def test_leaving_the_rating_out_applies_the_rest(self, mem_session):
        bundle = _bundle(mem_session, content_rating="M", description="old")

        entity = _enrich(mem_session, bundle, {"description": "new"})

        assert (entity.content_rating, entity.description) == ("M", "new")

    @pytest.mark.parametrize("sent,reason", [
        (None, "cleared"),
        ("not a rating", "cleared"),
        ("PEGI 3", "scheme_changed"),
        ("E", "lowered"),
    ])
    def test_each_loosening_reports_a_machine_readable_reason(self, mem_session, sent, reason):
        from fastapi import HTTPException

        bundle = _bundle(mem_session, content_rating="M")

        with pytest.raises(HTTPException) as exc_info:
            _enrich(mem_session, bundle, {"content_rating": sent})
        assert exc_info.value.detail["reason"] == reason

    @pytest.mark.parametrize("old,new", [("T", "M"), ("M", "M"), (None, "M")])
    def test_raising_keeping_or_setting_from_unrated_needs_no_confirmation(self, mem_session, old, new):
        bundle = _bundle(mem_session, content_rating=old)

        assert _enrich(mem_session, bundle, {"content_rating": new}).content_rating == new


class TestProviderLinks:
    def test_only_provider_sourced_links_are_replaced(self, mem_session):
        manual = {"type": "other", "url": "https://me.example/notes"}
        legacy = {"type": "trailer", "url": "https://www.youtube.com/watch?v=old"}
        bundle = _bundle(mem_session, external_links=[
            manual, legacy,
            {"type": "official", "url": "https://old.example/site", "source": "provider"},
        ])

        entity = _enrich(mem_session, bundle, {"external_links": [
            {"type": "official", "url": "https://new.example/site"},
        ]})

        assert entity.external_links == [
            manual, legacy, {"type": "official", "url": "https://new.example/site", "source": "provider"},
        ]

    def test_a_fetched_url_replaces_the_same_unmarked_entry(self, mem_session):
        legacy = {"type": "trailer", "url": "https://www.youtube.com/watch?v=abc"}
        bundle = _bundle(mem_session, external_links=[legacy])

        entity = _enrich(mem_session, bundle, {"external_links": [
            {"type": "trailer", "url": "https://www.youtube.com/watch?v=abc"},
        ]})

        assert entity.external_links == [{**legacy, "source": "provider"}]

    def test_non_http_urls_are_dropped_and_duplicates_collapse(self, mem_session):
        bundle = _bundle(mem_session)

        entity = _enrich(mem_session, bundle, {"external_links": [
            {"type": "official", "url": "javascript:alert(1)"},
            {"type": "official", "url": "file:///etc/passwd"},
            {"type": "official", "url": "ftp://example.com/x"},
            {"type": "official", "url": "https://user:pw@example.com/"},
            {"type": "official", "url": "//example.com/x"},
            {"type": "official", "url": "https://example.com/a b"},
            {"type": "bogus", "url": "https://example.com/ok"},
            {"type": "store", "url": "https://example.com/ok"},
            {"url": "http://example.com/plain"},
            "https://example.com/not-a-dict",
        ]})

        assert entity.external_links == [
            {"type": "other", "url": "https://example.com/ok", "source": "provider"},
            {"type": "other", "url": "http://example.com/plain", "source": "provider"},
        ]

    def test_count_is_capped(self, mem_session):
        from backend.service.metadata_providers.links import PROVIDER_LINK_CAP

        bundle = _bundle(mem_session)

        entity = _enrich(mem_session, bundle, {"external_links": [
            {"type": "other", "url": f"https://example.com/{n}"} for n in range(PROVIDER_LINK_CAP + 10)
        ]})

        assert len(entity.external_links) == PROVIDER_LINK_CAP

    def test_an_empty_list_removes_provider_links_and_keeps_the_rest(self, mem_session):
        manual = {"type": "other", "url": "https://me.example/notes"}
        bundle = _bundle(mem_session, external_links=[
            manual, {"type": "official", "url": "https://old.example/site", "source": "provider"},
        ])

        assert _enrich(mem_session, bundle, {"external_links": []}).external_links == [manual]

    def test_no_links_left_stores_null(self, mem_session):
        bundle = _bundle(mem_session, external_links=[
            {"type": "official", "url": "https://old.example/site", "source": "provider"},
        ])

        assert _enrich(mem_session, bundle, {"external_links": []}).external_links is None


class TestFetchedAtOnlyOnChange:
    def test_empty_payload_does_not_stamp(self, mem_session):
        assert _enrich(mem_session, _bundle(mem_session), {}).metadata_fetched_at is None

    def test_a_real_change_stamps(self, mem_session):
        bundle = _bundle(mem_session)

        assert _enrich(mem_session, bundle, {"metadata_source": "TheGamesDB"}).metadata_fetched_at is not None

    def test_identical_values_do_not_stamp(self, mem_session):
        bundle = _bundle(mem_session, description="Demons.", developer="id", year=1993)

        entity = _enrich(
            mem_session, bundle, {"title": "Doom", "description": "Demons.", "developer": "id", "year": 1993},
        )
        assert entity.metadata_fetched_at is None

    def test_one_changed_value_stamps(self, mem_session):
        bundle = _bundle(mem_session, description="Demons.")

        entity = _enrich(mem_session, bundle, {"description": "Hell."})
        assert entity.metadata_fetched_at is not None
        assert entity.description == "Hell."

    def test_same_genres_in_another_order_do_not_stamp(self, mem_session):
        from backend.models.metadata_lookup import set_genres_for_game_item_bundle

        bundle = _bundle(mem_session)
        set_genres_for_game_item_bundle(mem_session, bundle.id, ["Action", "Shooter"])
        mem_session.commit()

        assert _enrich(mem_session, bundle, {"genre": ["Shooter", "Action"]}).metadata_fetched_at is None

    def test_new_genre_stamps(self, mem_session):
        bundle = _bundle(mem_session)

        assert _enrich(mem_session, bundle, {"genre": ["Shooter"]}).metadata_fetched_at is not None

    def test_identical_links_do_not_stamp(self, mem_session):
        bundle = _bundle(mem_session, external_links=[
            {"type": "official", "url": "https://example.com/", "source": "provider"},
        ])

        entity = _enrich(mem_session, bundle, {"external_links": [{"type": "official", "url": "https://example.com/"}]})
        assert entity.metadata_fetched_at is None


# Game delete still sweeps app-owned disc covers that earlier versions wrote
# to MEDIA_PATH/_game_covers (META-2), though nothing writes there any more.

_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


class _MediaLib:
    def __init__(self, lib, media):
        self.lib = lib
        self.media = media

    @property
    def covers(self):
        return self.media / "_game_covers"

    def old_cover(self, leaf_id, ext=".jpg"):
        self.covers.mkdir(parents=True, exist_ok=True)
        path = self.covers / f"game-item-{leaf_id}{ext}"
        path.write_bytes(_JPEG)
        return path


@pytest.fixture
def media_lib(tmp_path, monkeypatch):
    import backend.core.settings as core_settings
    import backend.service.utils.settings as utils_settings

    lib = tmp_path / "library"
    media = lib / "software" / "media"
    media.mkdir(parents=True)

    class _S:
        def get_env_var(self, key):
            return str(media) if key == "MEDIA_PATH" else str(lib)

        def get(self, key, default=None):
            return default

    monkeypatch.setattr(core_settings, "get_settings", lambda: _S())
    monkeypatch.setattr(utils_settings, "get", lambda key, default=None: str(lib) if key == "LIBRARY_PATH" else default)
    return _MediaLib(lib, media)


def _leaf(db, folder, *, disc_number=1, bundle=None, cover_art_path=None):
    from backend.models.game import GameItem, GameItemBundle

    if bundle is None:
        bundle = GameItemBundle(title="My Set", platform="ps1", slug=f"my-set-{disc_number}")
        db.add(bundle)
        db.commit()
        db.refresh(bundle)
    leaf = GameItem(
        game_item_bundle_id=bundle.id,
        file_path=str(folder / f"disc{disc_number}.bin"),
        folder_path=str(folder),
        disc_number=disc_number,
        cover_art_path=cover_art_path,
    )
    db.add(leaf)
    db.commit()
    db.refresh(leaf)
    return leaf


class TestGameDeleteRemovesAppOwnedDiscCovers:
    def test_only_the_app_owned_disc_cover_is_removed(self, mem_session, media_lib):
        from backend.service.games.items import delete_library_collection
        from backend.service.utils import confirmation_tokens

        folder = media_lib.lib / "games" / "set"
        folder.mkdir(parents=True)
        leaf = _leaf(mem_session, folder)
        app_cover = media_lib.old_cover(leaf.id)
        leaf.cover_art_path = str(app_cover.resolve())
        mem_session.commit()
        bundle_id = leaf.game_item_bundle_id

        token = confirmation_tokens.issue("game", bundle_id)
        delete_library_collection(bundle_id, token, mem_session, delete_media=False)

        assert not app_cover.exists()

    def test_a_cover_another_row_still_uses_is_kept(self, mem_session, media_lib):
        from backend.service.games.items import delete_library_collection
        from backend.service.utils import confirmation_tokens

        leaf = _leaf(mem_session, media_lib.lib / "games" / "a")
        app_cover = media_lib.old_cover(leaf.id)
        leaf.cover_art_path = str(app_cover.resolve())
        mem_session.commit()
        _leaf(mem_session, media_lib.lib / "games" / "b", disc_number=2, cover_art_path=str(app_cover.resolve()))

        token = confirmation_tokens.issue("game", leaf.game_item_bundle_id)
        delete_library_collection(leaf.game_item_bundle_id, token, mem_session, delete_media=False)

        assert app_cover.exists()

    def test_stale_covers_from_a_format_change_are_swept(self, mem_session, media_lib):
        from backend.service.games.items import delete_library_collection
        from backend.service.utils import confirmation_tokens

        leaf = _leaf(mem_session, media_lib.lib / "games" / "c")
        current = media_lib.old_cover(leaf.id)
        leaf.cover_art_path = str(current.resolve())
        mem_session.commit()
        stale = media_lib.old_cover(leaf.id, ".gif")
        unrelated = media_lib.old_cover(leaf.id + 1000)

        token = confirmation_tokens.issue("game", leaf.game_item_bundle_id)
        delete_library_collection(leaf.game_item_bundle_id, token, mem_session, delete_media=False)

        assert not stale.exists()
        assert not current.exists()
        assert unrelated.exists()

    def test_a_users_own_cover_is_never_removed(self, mem_session, media_lib):
        from backend.service.games.items import delete_library_collection
        from backend.service.utils import confirmation_tokens

        folder = media_lib.lib / "games" / "loose"
        folder.mkdir(parents=True)
        user_cover = folder / "cover.jpg"
        user_cover.write_bytes(b"user art")
        leaf = _leaf(mem_session, folder, cover_art_path=str(user_cover))

        token = confirmation_tokens.issue("game", leaf.game_item_bundle_id)
        delete_library_collection(leaf.game_item_bundle_id, token, mem_session, delete_media=False)

        assert user_cover.read_bytes() == b"user art"
