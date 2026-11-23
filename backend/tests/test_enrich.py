"""Tests for backend.service.games.enrich.enrich_entity: error branches for
not-found entities and unsupported operations.

_is_forbidden_redirect_host and download_remote_image, which the
cover_art_url path calls into, live in backend/service/utils/asset_fetch.py
and are tested in test_asset_fetch.py.
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


class TestEnrichEntity:
    def test_library_collection_not_found_raises_404(self, mem_session):
        from fastapi import HTTPException
        from backend.service.games.enrich import enrich_entity

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity("game_item_bundle", 9999, title="New Title", db=mem_session)
        assert exc_info.value.status_code == 404

    def test_library_item_not_found_raises_404(self, mem_session):
        from fastapi import HTTPException
        from backend.service.games.enrich import enrich_entity

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity("game_item", 9999, cover_art_url="https://cdn.example.com/a.jpg", db=mem_session)
        assert exc_info.value.status_code == 404

    def test_second_cover_refetch_of_the_same_disc_is_409(self, mem_session, monkeypatch):
        from fastapi import HTTPException
        import backend.service.games.media_link as media_link_mod
        from backend.service.games.enrich import enrich_entity

        monkeypatch.setattr(media_link_mod, "_running_applies", {("game_item_cover", 7)})

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity("game_item", 7, cover_art_url="https://cdn.example.com/a.jpg", db=mem_session)

        assert exc_info.value.status_code == 409
        assert "already running" in exc_info.value.detail

    def test_cover_refetch_of_another_disc_is_not_blocked(self, mem_session, monkeypatch):
        from fastapi import HTTPException
        import backend.service.games.media_link as media_link_mod
        from backend.service.games.enrich import enrich_entity

        monkeypatch.setattr(media_link_mod, "_running_applies", {("game_item_cover", 7)})

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity("game_item", 8, cover_art_url="https://cdn.example.com/a.jpg", db=mem_session)

        assert exc_info.value.status_code == 404

    def test_cover_refetch_lock_is_released_afterwards(self, mem_session):
        from fastapi import HTTPException
        import backend.service.games.media_link as media_link_mod
        from backend.service.games.enrich import enrich_entity

        with pytest.raises(HTTPException):
            enrich_entity("game_item", 9999, cover_art_url="https://cdn.example.com/a.jpg", db=mem_session)

        assert ("game_item_cover", 9999) not in media_link_mod._running_applies

    def test_library_collection_with_cover_art_url_raises_422(self, mem_session):
        """Collections don't support direct cover art, must be applied to individual discs."""
        from fastapi import HTTPException
        from backend.models.game import GameItemBundle
        from backend.service.games.enrich import enrich_entity

        c = GameItemBundle(title="My Set", platform="ps1", slug="my-set")
        mem_session.add(c)
        mem_session.commit()
        mem_session.refresh(c)

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity(
                "game_item_bundle",
                c.id,
                cover_art_url="https://cdn.example.com/art.jpg",
                db=mem_session,
            )
        assert exc_info.value.status_code == 422
        assert "cover_art_url" in exc_info.value.detail

    def test_library_item_with_metadata_fields_raises_422(self, mem_session):
        """Disc-level leaves (library_item) do not accept metadata fields."""
        from fastapi import HTTPException
        from backend.models.game import GameItemBundle, GameItem
        from backend.service.games.enrich import enrich_entity

        c = GameItemBundle(title="My Set", platform="ps1", slug="my-set")
        mem_session.add(c)
        mem_session.commit()
        mem_session.refresh(c)

        leaf = GameItem(game_item_bundle_id=c.id, file_path="/tmp/disc1.bin", disc_number=1)
        mem_session.add(leaf)
        mem_session.commit()
        mem_session.refresh(leaf)

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity(
                "game_item",
                leaf.id,
                title="Should Not Work",
                db=mem_session,
            )
        assert exc_info.value.status_code == 422
        assert "metadata" in exc_info.value.detail.lower()

    def test_invalid_entity_type_raises_422(self, mem_session):
        from fastapi import HTTPException
        from backend.service.games.enrich import enrich_entity

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity("unknown_type", 1, db=mem_session)
        assert exc_info.value.status_code == 422
        assert "entity_type" in exc_info.value.detail

    def test_metadata_fetched_at_set_on_bundle_keep(self, mem_session):
        """A Keep that actually applies bundle-level metadata stamps
        metadata_fetched_at; an empty payload does not."""
        from backend.models.game import GameItemBundle
        from backend.service.games.enrich import enrich_entity

        c = GameItemBundle(title="My Set", platform="ps1", slug="my-set")
        mem_session.add(c)
        mem_session.commit()
        mem_session.refresh(c)
        assert c.metadata_fetched_at is None

        entity, _ = enrich_entity(
            "game_item_bundle", c.id, metadata_source="TheGamesDB", db=mem_session,
        )
        assert entity.metadata_fetched_at is not None

    def test_metadata_fetched_at_set_on_leaf_cover_art_keep(self, mem_session, media_lib):
        """A leaf-level Keep that actually applies cover art stamps
        metadata_fetched_at too, the only leaf-level fetch path that exists."""
        leaf = _leaf(mem_session, media_lib.lib / "games" / "set")
        assert leaf.metadata_fetched_at is None
        media_lib.serve(_JPEG)

        entity, _ = media_lib.enrich.enrich_entity(
            "game_item", leaf.id, cover_art_url=_URL, db=mem_session,
        )
        assert entity.metadata_fetched_at is not None


# META-2: per-disc covers live in MEDIA_PATH/_game_covers, one file per leaf

_URL = "https://cdn.thegamesdb.net/images/original/boxart/front/1.jpg"
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class _MediaLib:
    def __init__(self, lib, media, enrich, monkeypatch):
        self.lib = lib
        self.media = media
        self.enrich = enrich
        self._monkeypatch = monkeypatch

    @property
    def covers(self):
        return self.media / "_game_covers"

    def serve(self, body: bytes, ext: str | None = None):
        """Replace the network fetch with one that writes *body* to a temp
        file in the staging dir it is given."""
        import tempfile
        from pathlib import Path

        from backend.service.utils.asset_fetch import _sniff_image_ext

        def _fake_fetch(url, staging_dir, **kwargs):
            staging_dir.mkdir(parents=True, exist_ok=True)
            fd, raw = tempfile.mkstemp(suffix=".part", dir=staging_dir)
            with open(fd, "wb") as fh:
                fh.write(body)
            return Path(raw), ext or _sniff_image_ext(body)

        self._monkeypatch.setattr(self.enrich, "fetch_image_to_temp", _fake_fetch)


@pytest.fixture
def media_lib(tmp_path, monkeypatch):
    import backend.core.settings as core_settings
    import backend.service.utils.settings as utils_settings
    from backend.service.games import enrich as enrich_mod

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
    return _MediaLib(lib, media, enrich_mod, monkeypatch)


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


class TestPerLeafCover:
    def test_cover_is_named_by_leaf_id_inside_game_covers(self, mem_session, media_lib):
        folder = media_lib.lib / "games" / "set"
        folder.mkdir(parents=True)
        leaf = _leaf(mem_session, folder)
        media_lib.serve(_JPEG)

        entity, _ = media_lib.enrich.enrich_entity("game_item", leaf.id, cover_art_url=_URL, db=mem_session)

        expected = (media_lib.covers / f"game-item-{leaf.id}.jpg").resolve()
        assert entity.cover_art_path == str(expected)
        assert expected.read_bytes() == _JPEG
        assert not (folder / "cover.jpg").exists()
        assert list(folder.iterdir()) == []

    def test_two_discs_of_one_set_get_two_files(self, mem_session, media_lib):
        from backend.models.game import GameItemBundle

        folder = media_lib.lib / "games" / "set"
        folder.mkdir(parents=True)
        bundle = GameItemBundle(title="Two Disc", platform="ps1", slug="two-disc")
        mem_session.add(bundle)
        mem_session.commit()
        disc1 = _leaf(mem_session, folder, disc_number=1, bundle=bundle)
        disc2 = _leaf(mem_session, folder, disc_number=2, bundle=bundle)

        media_lib.serve(_JPEG)
        media_lib.enrich.enrich_entity("game_item", disc1.id, cover_art_url=_URL, db=mem_session)
        media_lib.serve(_PNG)
        media_lib.enrich.enrich_entity("game_item", disc2.id, cover_art_url=_URL, db=mem_session)

        assert (media_lib.covers / f"game-item-{disc1.id}.jpg").read_bytes() == _JPEG
        assert (media_lib.covers / f"game-item-{disc2.id}.png").read_bytes() == _PNG

    def test_users_own_cover_is_never_touched(self, mem_session, media_lib):
        folder = media_lib.lib / "games" / "loose"
        folder.mkdir(parents=True)
        user_cover = folder / "cover.jpg"
        user_cover.write_bytes(b"user art")
        leaf = _leaf(mem_session, folder, cover_art_path=str(user_cover))
        media_lib.serve(_JPEG)

        entity, _ = media_lib.enrich.enrich_entity("game_item", leaf.id, cover_art_url=_URL, db=mem_session)

        assert user_cover.read_bytes() == b"user art"
        assert entity.cover_art_path != str(user_cover)
        assert sorted(p.name for p in folder.iterdir()) == ["cover.jpg"]

    def test_refetch_with_new_format_removes_only_the_old_app_file(self, mem_session, media_lib):
        leaf = _leaf(mem_session, media_lib.lib / "games" / "set")
        media_lib.serve(_JPEG)
        media_lib.enrich.enrich_entity("game_item", leaf.id, cover_art_url=_URL, db=mem_session)
        media_lib.serve(_PNG)

        entity, _ = media_lib.enrich.enrich_entity("game_item", leaf.id, cover_art_url=_URL, db=mem_session)

        assert entity.cover_art_path.endswith(f"game-item-{leaf.id}.png")
        assert sorted(p.name for p in media_lib.covers.iterdir()) == [f"game-item-{leaf.id}.png"]

    def test_staging_is_empty_after_a_fetch(self, mem_session, media_lib):
        leaf = _leaf(mem_session, media_lib.lib / "games" / "set")
        media_lib.serve(_JPEG)

        media_lib.enrich.enrich_entity("game_item", leaf.id, cover_art_url=_URL, db=mem_session)

        staging = media_lib.media / "_asset_staging"
        assert not staging.exists() or list(staging.iterdir()) == []

    def test_unset_media_path_is_503(self, mem_session, media_lib, monkeypatch):
        from fastapi import HTTPException

        import backend.core.settings as core_settings

        class _Unset:
            def get_env_var(self, key):
                return ""

            def get(self, key, default=None):
                return default

        monkeypatch.setattr(core_settings, "get_settings", lambda: _Unset())
        leaf = _leaf(mem_session, media_lib.lib / "games" / "set")
        media_lib.serve(_JPEG)

        with pytest.raises(HTTPException) as exc_info:
            media_lib.enrich.enrich_entity("game_item", leaf.id, cover_art_url=_URL, db=mem_session)
        assert exc_info.value.status_code == 503


# META-23: metadata_fetched_at only on a real change


class TestFetchedAtOnlyOnChange:
    def _bundle(self, db, **fields):
        from backend.models.game import GameItemBundle

        bundle = GameItemBundle(title="Doom", platform="dos", slug="doom", **fields)
        db.add(bundle)
        db.commit()
        db.refresh(bundle)
        return bundle

    def test_identical_values_do_not_stamp(self, mem_session):
        from backend.service.games.enrich import enrich_entity

        bundle = self._bundle(mem_session, description="Demons.", developer="id", year=1993)

        entity, _ = enrich_entity(
            "game_item_bundle", bundle.id,
            title="Doom", description="Demons.", developer="id", year=1993, db=mem_session,
        )
        assert entity.metadata_fetched_at is None

    def test_one_changed_value_stamps(self, mem_session):
        from backend.service.games.enrich import enrich_entity

        bundle = self._bundle(mem_session, description="Demons.")

        entity, _ = enrich_entity("game_item_bundle", bundle.id, description="Hell.", db=mem_session)
        assert entity.metadata_fetched_at is not None
        assert entity.description == "Hell."

    def test_same_genres_in_another_order_do_not_stamp(self, mem_session):
        from backend.models.metadata_lookup import set_genres_for_game_item_bundle
        from backend.service.games.enrich import enrich_entity

        bundle = self._bundle(mem_session)
        set_genres_for_game_item_bundle(mem_session, bundle.id, ["Action", "Shooter"])
        mem_session.commit()

        entity, _ = enrich_entity("game_item_bundle", bundle.id, genre=["Shooter", "Action"], db=mem_session)
        assert entity.metadata_fetched_at is None

    def test_new_genre_stamps(self, mem_session):
        from backend.service.games.enrich import enrich_entity

        bundle = self._bundle(mem_session)

        entity, _ = enrich_entity("game_item_bundle", bundle.id, genre=["Shooter"], db=mem_session)
        assert entity.metadata_fetched_at is not None

    def test_identical_leaf_cover_does_not_stamp_again(self, mem_session, media_lib):
        leaf = _leaf(mem_session, media_lib.lib / "games" / "set")
        media_lib.serve(_JPEG)
        first, _ = media_lib.enrich.enrich_entity("game_item", leaf.id, cover_art_url=_URL, db=mem_session)
        stamped = first.metadata_fetched_at
        assert stamped is not None

        again, _ = media_lib.enrich.enrich_entity("game_item", leaf.id, cover_art_url=_URL, db=mem_session)
        assert again.metadata_fetched_at == stamped


class TestGameDeleteRemovesAppOwnedDiscCovers:
    def test_only_the_app_owned_disc_cover_is_removed(self, mem_session, media_lib):
        from backend.service.games.items import delete_library_collection
        from backend.service.utils import confirmation_tokens

        folder = media_lib.lib / "games" / "set"
        folder.mkdir(parents=True)
        leaf = _leaf(mem_session, folder)
        media_lib.serve(_JPEG)
        media_lib.enrich.enrich_entity("game_item", leaf.id, cover_art_url=_URL, db=mem_session)
        app_cover = media_lib.covers / f"game-item-{leaf.id}.jpg"
        assert app_cover.exists()
        bundle_id = leaf.game_item_bundle_id

        token = confirmation_tokens.issue("game", bundle_id)
        delete_library_collection(bundle_id, token, mem_session, delete_media=False)

        assert not app_cover.exists()

    def test_a_cover_another_row_still_uses_is_kept(self, mem_session, media_lib):
        from backend.service.games.items import delete_library_collection
        from backend.service.utils import confirmation_tokens

        leaf = _leaf(mem_session, media_lib.lib / "games" / "a")
        media_lib.serve(_JPEG)
        media_lib.enrich.enrich_entity("game_item", leaf.id, cover_art_url=_URL, db=mem_session)
        app_cover = media_lib.covers / f"game-item-{leaf.id}.jpg"
        _leaf(mem_session, media_lib.lib / "games" / "b", disc_number=2, cover_art_path=str(app_cover.resolve()))

        token = confirmation_tokens.issue("game", leaf.game_item_bundle_id)
        delete_library_collection(leaf.game_item_bundle_id, token, mem_session, delete_media=False)

        assert app_cover.exists()

    def test_stale_covers_from_a_format_change_are_swept(self, mem_session, media_lib):
        from backend.service.games.items import delete_library_collection
        from backend.service.utils import confirmation_tokens

        leaf = _leaf(mem_session, media_lib.lib / "games" / "c")
        media_lib.serve(_JPEG)
        media_lib.enrich.enrich_entity("game_item", leaf.id, cover_art_url=_URL, db=mem_session)
        stale = media_lib.covers / f"game-item-{leaf.id}.gif"
        stale.write_bytes(b"GIF89a")
        unrelated = media_lib.covers / f"game-item-{leaf.id + 1000}.jpg"
        unrelated.write_bytes(_JPEG)

        token = confirmation_tokens.issue("game", leaf.game_item_bundle_id)
        delete_library_collection(leaf.game_item_bundle_id, token, mem_session, delete_media=False)

        assert not stale.exists()
        assert not (media_lib.covers / f"game-item-{leaf.id}.jpg").exists()
        assert unrelated.exists()
