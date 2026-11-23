"""Media file cleanup path matching (backend/service/media/file_cleanup.py).

Paths are compared by a normalised key (normcase, normpath, resolved form),
never as raw strings: a referenced file spelled with a different case, slash
direction or trailing separator must not be removable, and a cover stored in
another spelling must still be cleared. Case and slash cases only differ on
Windows, so they are skipped elsewhere.
"""

import os
from pathlib import Path

import pytest

windows_only = pytest.mark.skipif(os.name != "nt", reason="case and slash spellings only differ on Windows")


@pytest.fixture
def db():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine
    import backend.models  # noqa: F401, registers all table models

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def media(tmp_path, monkeypatch) -> Path:
    import backend.core.settings as core_settings
    import backend.service.utils.settings as utils_settings

    lib = tmp_path / "library"
    root = lib / "software" / "media"
    root.mkdir(parents=True)

    class _S:
        def get_env_var(self, key):
            return str(root) if key == "MEDIA_PATH" else str(lib)

        def get(self, key, default=None):
            return default

    monkeypatch.setattr(core_settings, "get_settings", lambda: _S())
    monkeypatch.setattr(utils_settings, "get", lambda key, default=None: str(lib) if key == "LIBRARY_PATH" else default)
    return root


def _file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xd8\xffdata")
    return path


def _item(db, file_path, cover=None):
    from backend.models.media import MediaItem

    item = MediaItem(title="item", media_kind="image", file_path=str(file_path), cover_art_path=cover)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _leaf(db, file_path, executable_path=None, cover=None):
    from backend.models.game import GameItem, GameItemBundle

    game = GameItemBundle(title="Game", platform="dos", slug="game")
    db.add(game)
    db.commit()
    db.refresh(game)
    leaf = GameItem(
        game_item_bundle_id=game.id,
        file_path=str(file_path),
        executable_path=str(executable_path) if executable_path else None,
        cover_art_path=cover,
    )
    db.add(leaf)
    db.commit()
    db.refresh(leaf)
    return leaf


def _spellings(path: Path) -> list[str]:
    raw = str(path)
    return [raw + os.sep, raw.upper(), raw.lower(), raw.replace("\\", "/")]


class TestPathKeys:
    def test_trailing_separator_does_not_change_the_key(self, tmp_path):
        from backend.service.media.file_cleanup import path_keys

        raw = str(tmp_path / "a" / "x.jpg")

        assert path_keys(raw) == path_keys(raw + os.sep)

    @windows_only
    def test_case_and_slash_spellings_share_a_key(self, tmp_path):
        from backend.service.media.file_cleanup import path_keys

        raw = str(tmp_path / "a" / "x.jpg")

        for spelling in (raw.upper(), raw.lower(), raw.replace("\\", "/")):
            assert path_keys(raw) & path_keys(spelling)

    def test_unc_and_device_paths_are_never_resolved(self, monkeypatch):
        from backend.service.media.file_cleanup import path_keys

        def _boom(self, *args, **kwargs):
            raise AssertionError("resolve() called on an untrusted path")

        monkeypatch.setattr(Path, "resolve", _boom)

        assert len(path_keys("\\\\attacker\\share\\x.png")) == 1
        assert len(path_keys("\\\\?\\C:\\Windows\\x.png")) == 1


class TestRemovableMediaFiles:
    def test_unreferenced_owned_file_is_removable(self, db, media):
        from backend.service.media.file_cleanup import removable_media_files

        shot = _file(media / "doom" / "a.jpg")
        item = _item(db, shot)

        assert removable_media_files([str(shot)], {item.id}, db) == [str(shot)]

    def test_trailing_separator_reference_keeps_the_file(self, db, media):
        from backend.service.media.file_cleanup import removable_media_files

        shot = _file(media / "doom" / "a.jpg")
        mine = _item(db, shot)
        _item(db, str(shot) + os.sep)

        assert removable_media_files([str(shot)], {mine.id}, db) == []

    @windows_only
    @pytest.mark.parametrize("variant", [0, 1, 2, 3])
    def test_media_item_reference_in_another_spelling_keeps_the_file(self, db, media, variant):
        from backend.service.media.file_cleanup import removable_media_files

        shot = _file(media / "doom" / "a.jpg")
        mine = _item(db, shot)
        _item(db, _spellings(shot)[variant])

        assert removable_media_files([str(shot)], {mine.id}, db) == []

    @windows_only
    @pytest.mark.parametrize("variant", [0, 1, 2, 3])
    def test_game_leaf_reference_in_another_spelling_keeps_the_file(self, db, media, variant):
        from backend.service.media.file_cleanup import removable_media_files

        shot = _file(media / "doom" / "a.jpg")
        mine = _item(db, shot)
        _leaf(db, "/library/games/doom.img", executable_path=_spellings(shot)[variant])

        assert removable_media_files([str(shot)], {mine.id}, db) == []

    def test_app_leaf_reference_keeps_the_file(self, db, media):
        from backend.models.app import AppItem, AppItemBundle
        from backend.service.media.file_cleanup import removable_media_files

        shot = _file(media / "doom" / "a.jpg")
        mine = _item(db, shot)
        bundle = AppItemBundle(title="App", platform="ps1", slug="app")
        db.add(bundle)
        db.commit()
        db.refresh(bundle)
        db.add(AppItem(app_item_bundle_id=bundle.id, file_path=str(shot) + os.sep))
        db.commit()

        assert removable_media_files([str(shot)], {mine.id}, db) == []

    @windows_only
    def test_internal_directories_are_protected_in_any_case(self, db, media):
        from backend.service.media.file_cleanup import removable_media_files

        cover = _file(media / "_game_covers" / "game-item-1.jpg")
        staged = _file(media / "_asset_staging" / "x.part")
        item = _item(db, cover)

        spelled = [
            str(cover).replace("_game_covers", "_GAME_COVERS"),
            str(staged).replace("_asset_staging", "_Asset_Staging"),
        ]
        assert removable_media_files(spelled, {item.id}, db) == []

    @windows_only
    def test_root_spelled_in_another_case_still_counts_as_inside(self, db, media):
        from backend.service.media.file_cleanup import removable_media_files

        shot = _file(media / "doom" / "a.jpg")
        item = _item(db, shot)

        assert removable_media_files([str(shot).upper()], {item.id}, db) == [str(shot).upper()]

    def test_file_outside_media_path_is_not_removable(self, db, media, tmp_path):
        from backend.service.media.file_cleanup import removable_media_files

        outside = _file(tmp_path / "outside" / "a.jpg")
        item = _item(db, outside)

        assert removable_media_files([str(outside)], {item.id}, db) == []

    def test_media_root_itself_is_not_removable(self, db, media):
        from backend.service.media.file_cleanup import removable_media_files

        assert removable_media_files([str(media), str(media) + os.sep], set(), db) == []

    def test_two_spellings_of_one_file_are_deduplicated(self, db, media):
        from backend.service.media.file_cleanup import removable_media_files

        shot = _file(media / "doom" / "a.jpg")
        item = _item(db, shot)

        assert removable_media_files([str(shot), str(shot) + os.sep], {item.id}, db) == [str(shot)]


class TestRemoveFiles:
    def test_referenced_file_in_another_spelling_survives(self, db, media):
        from backend.service.media.file_cleanup import remove_files

        shot = _file(media / "doom" / "a.jpg")
        _item(db, str(shot) + os.sep)

        assert remove_files([str(shot)], db) == []
        assert shot.exists()

    @windows_only
    def test_referenced_file_in_another_case_survives(self, db, media):
        from backend.service.media.file_cleanup import remove_files

        shot = _file(media / "doom" / "a.jpg")
        _leaf(db, "/library/games/doom.img", executable_path=str(shot).upper())

        assert remove_files([str(shot)], db) == []
        assert shot.exists()

    def test_unreferenced_file_and_its_emptied_folder_are_removed(self, db, media):
        from backend.service.media.file_cleanup import remove_files

        shot = _file(media / "doom" / "a.jpg")

        assert remove_files([str(shot)], db) == [str(shot)]
        assert not shot.exists()
        assert not shot.parent.exists()
        assert media.exists()


class TestClearCoverReferences:
    def test_covers_in_another_spelling_are_cleared(self, db, media):
        from backend.service.media.file_cleanup import clear_cover_references

        shot = _file(media / "doom" / "a.jpg")
        leaf = _leaf(db, "/library/games/doom.img", cover=str(shot) + os.sep)
        other = _item(db, media / "doom" / "b.jpg", cover=str(shot) + os.sep)

        assert clear_cover_references([str(shot)], db) == 2
        db.commit()
        db.expire_all()
        assert leaf.cover_art_path is None
        assert other.cover_art_path is None

    @windows_only
    def test_covers_in_another_case_or_slash_are_cleared(self, db, media):
        from backend.service.media.file_cleanup import clear_cover_references

        shot = _file(media / "doom" / "a.jpg")
        first = _item(db, media / "doom" / "b.jpg", cover=str(shot).upper())
        second = _item(db, media / "doom" / "c.jpg", cover=str(shot).replace("\\", "/"))

        assert clear_cover_references([str(shot)], db) == 2
        db.commit()
        db.expire_all()
        assert first.cover_art_path is None
        assert second.cover_art_path is None

    def test_unrelated_covers_are_left_alone(self, db, media):
        from backend.service.media.file_cleanup import clear_cover_references

        shot = _file(media / "doom" / "a.jpg")
        keep = _item(db, media / "doom" / "b.jpg", cover=str(media / "doom" / "b.jpg"))

        assert clear_cover_references([str(shot)], db) == 0
        assert keep.cover_art_path == str(media / "doom" / "b.jpg")
