"""Accept All asset storage (backend/service/games/media_link.py):

- one apply is all or nothing on disk and in the DB (META-6)
- per-apply asset count and time limits (META-5)
- fetch-created items store asset_type and source_url, are deduplicated
  by URL, and a repeat apply needs a Replace or Keep choice (META-7)
- a null bundle cover is filled from the new images (MED-14)

Downloads are replaced by a fake that writes into the staging dir it is
handed, the same contract fetch_image_to_temp has.
"""

import tempfile
from pathlib import Path

import pytest

_BOX = "https://cdn.thegamesdb.net/images/original/boxart/front/1.jpg"


def _url(n: int) -> str:
    return f"https://cdn.thegamesdb.net/images/original/screenshots/{n}.jpg"


@pytest.fixture
def db():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine
    import backend.models  # noqa: F401, registers all table models

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class _Env:
    def __init__(self, lib: Path, media: Path):
        self.lib = lib
        self.media = media
        self.fetched: list[str] = []
        self.fail_on: str | None = None
        self.before_fetch = None

    def files(self) -> list[Path]:
        """Every file under MEDIA_PATH outside the staging area."""
        return sorted(
            p for p in self.media.rglob("*")
            if p.is_file() and "_asset_staging" not in p.relative_to(self.media).parts
        )

    def staging_leftovers(self) -> list[Path]:
        staging = self.media / "_asset_staging"
        return list(staging.rglob("*")) if staging.exists() else []


@pytest.fixture
def env(tmp_path, monkeypatch):
    import backend.core.settings as core_settings
    import backend.service.utils.asset_fetch as asset_fetch_mod
    import backend.service.utils.settings as utils_settings

    lib = tmp_path / "library"
    media = lib / "software" / "media"
    media.mkdir(parents=True)
    state = _Env(lib, media)

    class _S:
        def get_env_var(self, key):
            return str(media) if key == "MEDIA_PATH" else str(lib)

        def get(self, key, default=None):
            return default

    monkeypatch.setattr(core_settings, "get_settings", lambda: _S())
    monkeypatch.setattr(utils_settings, "get", lambda key, default=None: str(lib) if key == "LIBRARY_PATH" else default)

    def _fake_fetch(url, staging_dir, **kwargs):
        from fastapi import HTTPException

        if state.before_fetch is not None:
            state.before_fetch(url, kwargs)
        if url == state.fail_on:
            raise HTTPException(status_code=502, detail="Asset fetch failed: boom")
        state.fetched.append(url)
        fd, raw = tempfile.mkstemp(suffix=".part", dir=staging_dir)
        with open(fd, "wb") as fh:
            fh.write(b"\xff\xd8\xff" + url.encode())
        return Path(raw), ".jpg"

    monkeypatch.setattr(asset_fetch_mod, "fetch_image_to_temp", _fake_fetch)
    return state


def _game(db, title="Doom"):
    from backend.models.game import GameItemBundle

    game = GameItemBundle(title=title, platform="dos", slug=title.lower())
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def _assets(*urls, types=None):
    from backend.service.metadata_providers import MetadataAsset

    types = types or ["screenshot"] * len(urls)
    return [MetadataAsset(url=u, type=t) for u, t in zip(urls, types)]


def _apply(db, game, assets, **kwargs):
    from backend.service.games.media_link import prepare_apply, run_apply

    return run_apply(prepare_apply(game.id, assets, db, **kwargs), db)


def _counts(db):
    from backend.models.media import MediaItem, MediaItemBundle, MediaLink

    return db.query(MediaItem).count(), db.query(MediaItemBundle).count(), db.query(MediaLink).count()


# META-6: all or nothing


class TestAtomicApply:
    def test_failure_midway_leaves_no_files_or_rows(self, db, env):
        from fastapi import HTTPException

        game = _game(db)
        env.fail_on = _url(2)

        with pytest.raises(HTTPException) as exc_info:
            _apply(db, game, _assets(_url(0), _url(1), _url(2)))

        assert exc_info.value.status_code == 502
        assert env.files() == []
        assert env.staging_leftovers() == []
        assert _counts(db) == (0, 0, 0)

    def test_commit_failure_removes_moved_files_and_rows(self, db, env, monkeypatch):
        game = _game(db)
        real_commit = db.commit

        def _fail_commit():
            raise RuntimeError("database is locked")

        monkeypatch.setattr(db, "commit", _fail_commit)
        with pytest.raises(RuntimeError):
            _apply(db, game, _assets(_url(0), _url(1)))
        monkeypatch.setattr(db, "commit", real_commit)

        assert env.files() == []
        assert [p for p in env.media.iterdir() if p.name != "_asset_staging"] == []
        assert env.staging_leftovers() == []
        assert _counts(db) == (0, 0, 0)

    def test_failed_keep_leaves_the_earlier_set_untouched(self, db, env):
        from fastapi import HTTPException

        game = _game(db)
        _apply(db, game, _assets(_url(0)))
        before_files = env.files()
        env.fail_on = _url(2)

        with pytest.raises(HTTPException):
            _apply(db, game, _assets(_url(1), _url(2)), previous_assets="keep")

        assert env.files() == before_files
        assert _counts(db) == (1, 1, 1)

    def test_failed_replace_keeps_the_old_set(self, db, env):
        from fastapi import HTTPException
        from backend.models.media import MediaItem

        game = _game(db)
        _apply(db, game, _assets(_url(0)))
        before_files = env.files()
        env.fail_on = _url(1)

        with pytest.raises(HTTPException):
            _apply(db, game, _assets(_url(1)), previous_assets="replace")

        assert env.files() == before_files
        assert [i.source_url for i in db.query(MediaItem).all()] == [_url(0)]

    def test_success_leaves_staging_empty(self, db, env):
        _apply(db, _game(db), _assets(_url(0), _url(1)))

        assert env.staging_leftovers() == []
        assert len(env.files()) == 2


# META-5: limits


class TestLimits:
    def test_too_many_assets_is_413_before_any_download(self, db, env):
        from fastapi import HTTPException
        from backend.service.games.media_link import ACCEPT_ALL_MAX_ASSETS

        game = _game(db)
        assets = _assets(*[_url(n) for n in range(ACCEPT_ALL_MAX_ASSETS + 1)])

        with pytest.raises(HTTPException) as exc_info:
            _apply(db, game, assets)

        assert exc_info.value.status_code == 413
        detail = exc_info.value.detail
        assert f"{ACCEPT_ALL_MAX_ASSETS + 1} images" in detail
        assert f"at most {ACCEPT_ALL_MAX_ASSETS} per apply" in detail
        assert env.fetched == []
        assert _counts(db) == (0, 0, 0)

    def test_exactly_the_cap_is_allowed(self, db, env):
        from backend.service.games.media_link import ACCEPT_ALL_MAX_ASSETS

        bundle = _apply(db, _game(db), _assets(*[_url(n) for n in range(ACCEPT_ALL_MAX_ASSETS)]))

        assert len(bundle.items) == ACCEPT_ALL_MAX_ASSETS

    def test_every_download_gets_the_same_deadline(self, db, env):
        import time

        from backend.service.games.media_link import ACCEPT_ALL_TIME_BUDGET_SECONDS

        deadlines: list[float] = []
        env.before_fetch = lambda url, kwargs: deadlines.append(kwargs["deadline"])
        start = time.monotonic()

        _apply(db, _game(db), _assets(_url(0), _url(1)))

        assert len(set(deadlines)) == 1
        assert start < deadlines[0] <= time.monotonic() + ACCEPT_ALL_TIME_BUDGET_SECONDS

    def test_budget_exhausted_is_422_and_leaves_nothing(self, db, env, monkeypatch):
        from fastapi import HTTPException

        import backend.service.games.media_link as media_link_mod
        from backend.service.utils.asset_fetch import _check_deadline

        monkeypatch.setattr(media_link_mod, "ACCEPT_ALL_TIME_BUDGET_SECONDS", -1.0)
        env.before_fetch = lambda url, kwargs: _check_deadline(kwargs["deadline"])

        with pytest.raises(HTTPException) as exc_info:
            _apply(db, _game(db), _assets(_url(0)))

        assert exc_info.value.status_code == 422
        assert "time budget" in exc_info.value.detail
        assert env.files() == []
        assert _counts(db) == (0, 0, 0)

    def test_concurrent_apply_for_the_same_game_is_409(self, db, env, monkeypatch):
        from fastapi import HTTPException

        import backend.service.games.media_link as media_link_mod

        game = _game(db)
        monkeypatch.setattr(media_link_mod, "_running_applies", {("game", game.id)})

        with pytest.raises(HTTPException) as exc_info:
            _apply(db, game, _assets(_url(0)))

        assert exc_info.value.status_code == 409
        assert "already running" in exc_info.value.detail
        assert env.fetched == []

    def test_concurrent_apply_into_a_shared_media_bundle_is_409(self, db, env, monkeypatch):
        """Two games linked to one media bundle cannot apply into it at once."""
        from fastapi import HTTPException

        import backend.service.games.media_link as media_link_mod
        from backend.models.media import make_entity_link

        first = _game(db, "Doom")
        bundle = _apply(db, first, _assets(_url(0)))
        second = _game(db, "Doom II")
        db.add(make_entity_link("game_item_bundle", second.id, "media_item_bundle", bundle.id))
        db.commit()
        env.fetched.clear()
        monkeypatch.setattr(media_link_mod, "_running_applies", {("media_bundle", bundle.id)})

        with pytest.raises(HTTPException) as exc_info:
            _apply(db, second, _assets(_url(1)), previous_assets="keep")

        assert exc_info.value.status_code == 409
        assert env.fetched == []

    def test_lock_is_released_after_a_failure(self, db, env):
        from fastapi import HTTPException

        import backend.service.games.media_link as media_link_mod

        game = _game(db)
        env.fail_on = _url(0)
        with pytest.raises(HTTPException):
            _apply(db, game, _assets(_url(0)))

        assert media_link_mod._running_applies == set()


# META-7: source_url, dedupe, Replace / Keep


class TestFetchCreatedItems:
    def test_items_store_asset_type_and_source_url(self, db, env):
        bundle = _apply(db, _game(db), _assets(_BOX, _url(0), types=["boxart_front", "screenshot"]))

        assert sorted((i.asset_type, i.source_url) for i in bundle.items) == [
            ("boxart_front", _BOX), ("screenshot", _url(0)),
        ]

    def test_repeated_url_in_one_request_is_downloaded_once(self, db, env):
        bundle = _apply(db, _game(db), _assets(_url(0), _url(0), _url(1)))

        assert len(bundle.items) == 2
        assert env.fetched == [_url(0), _url(1)]

    def test_repeat_apply_without_a_choice_is_409_with_the_count(self, db, env):
        from fastapi import HTTPException
        from backend.service.games.media_link import PREVIOUS_ASSETS_ERROR_TYPE

        game = _game(db)
        _apply(db, game, _assets(_url(0), _url(1)))
        env.fetched.clear()

        with pytest.raises(HTTPException) as exc_info:
            _apply(db, game, _assets(_url(0), _url(2)))

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error_type"] == PREVIOUS_ASSETS_ERROR_TYPE
        assert exc_info.value.detail["existing_count"] == 2
        assert env.fetched == []

    def test_manual_items_alone_need_no_choice(self, db, env):
        """Rows with a null source_url (uploads, pre-migration rows) do not
        count as fetch-created."""
        from backend.models.media import MediaItem

        game = _game(db)
        bundle = _apply(db, game, _assets(_url(0)))
        for item in bundle.items:
            item.source_url = None
        db.commit()

        again = _apply(db, game, _assets(_url(0)))

        assert db.query(MediaItem).filter(MediaItem.media_item_bundle_id == again.id).count() == 2

    def test_keep_adds_only_new_urls(self, db, env):
        game = _game(db)
        _apply(db, game, _assets(_url(0), _url(1)))
        env.fetched.clear()

        bundle = _apply(db, game, _assets(_url(1), _url(2)), previous_assets="keep")

        assert env.fetched == [_url(2)]
        assert sorted(i.source_url for i in bundle.items) == [_url(0), _url(1), _url(2)]
        assert len(env.files()) == 3

    def test_keep_with_nothing_new_changes_nothing(self, db, env):
        game = _game(db)
        _apply(db, game, _assets(_url(0)))
        before = env.files()
        env.fetched.clear()

        bundle = _apply(db, game, _assets(_url(0)), previous_assets="keep")

        assert env.fetched == []
        assert env.files() == before
        assert len(bundle.items) == 1

    def test_replace_swaps_fetched_items_and_never_touches_manual_ones(self, db, env):
        from backend.models.media import MediaItem

        game = _game(db)
        bundle = _apply(db, game, _assets(_url(0), _url(1)))
        old_files = {Path(i.file_path) for i in bundle.items}
        manual_file = env.media / "manual" / "scan.jpg"
        manual_file.parent.mkdir()
        manual_file.write_bytes(b"\xff\xd8\xffmanual")
        db.add(MediaItem(
            title="Scan", media_kind="image", file_path=str(manual_file), media_item_bundle_id=bundle.id,
        ))
        db.commit()

        bundle = _apply(db, game, _assets(_url(2)), previous_assets="replace")

        sources = sorted((i.source_url or "manual") for i in bundle.items)
        assert sources == [_url(2), "manual"]
        assert manual_file.exists()
        assert all(not p.exists() for p in old_files)

    def test_replace_keeps_a_file_another_row_still_uses(self, db, env):
        from backend.models.media import MediaItem

        game = _game(db)
        bundle = _apply(db, game, _assets(_url(0)))
        shared = bundle.items[0].file_path
        db.add(MediaItem(title="Same file", media_kind="image", file_path=shared, media_item_bundle_id=bundle.id))
        db.commit()

        _apply(db, game, _assets(_url(1)), previous_assets="replace")

        assert Path(shared).exists()

    def test_replace_keeps_covers_on_a_file_that_stays(self, db, env):
        """A disc cover on a file another row still uses keeps working; the
        media bundle's own cover still moves to the new set."""
        from backend.models.game import GameItem
        from backend.models.media import MediaItem

        game = _game(db)
        bundle = _apply(db, game, _assets(_BOX, types=["boxart_front"]))
        shared = bundle.items[0].file_path
        db.add(MediaItem(title="Same file", media_kind="image", file_path=shared, media_item_bundle_id=bundle.id))
        disc = GameItem(game_item_bundle_id=game.id, file_path="/library/games/doom.img", cover_art_path=shared)
        db.add(disc)
        db.commit()

        bundle = _apply(db, game, _assets(_url(7)), previous_assets="replace")
        db.refresh(disc)

        assert disc.cover_art_path == shared
        assert bundle.cover_art_path == next(i for i in bundle.items if i.source_url == _url(7)).file_path

    def test_file_used_by_a_game_leaf_is_never_removed(self, db, env):
        from backend.models.game import GameItem

        game = _game(db)
        bundle = _apply(db, game, _assets(_url(0)))
        used = bundle.items[0].file_path
        db.add(GameItem(game_item_bundle_id=game.id, file_path=used))
        db.commit()

        _apply(db, game, _assets(_url(1)), previous_assets="replace")

        assert Path(used).exists()

    def test_replace_clears_game_disc_and_bundle_covers_that_pointed_at_old_items(self, db, env):
        from backend.models.game import GameItem

        game = _game(db)
        bundle = _apply(db, game, _assets(_BOX, types=["boxart_front"]))
        old_cover = bundle.cover_art_path
        disc = GameItem(game_item_bundle_id=game.id, file_path="/library/games/doom.img", cover_art_path=old_cover)
        db.add(disc)
        db.commit()

        bundle = _apply(db, game, _assets(_url(5)), previous_assets="replace")
        db.refresh(disc)

        assert disc.cover_art_path is None
        assert bundle.cover_art_path != old_cover
        assert bundle.cover_art_path == bundle.items[0].file_path


# MED-14: bundle cover


class TestBundleCover:
    def test_new_bundle_cover_prefers_box_art_over_list_order(self, db, env):
        bundle = _apply(
            db, _game(db), _assets(_url(0), _BOX, types=["screenshot", "boxart_front"]),
        )

        cover_item = next(i for i in bundle.items if i.asset_type == "boxart_front")
        assert bundle.cover_art_path == cover_item.file_path

    def test_cover_type_is_preferred_too(self, db, env):
        bundle = _apply(db, _game(db), _assets(_url(0), _url(1), types=["fanart", "cover"]))

        assert bundle.cover_art_path == next(i for i in bundle.items if i.asset_type == "cover").file_path

    def test_without_box_art_the_first_image_is_used(self, db, env):
        bundle = _apply(db, _game(db), _assets(_url(0), _url(1)))

        assert bundle.cover_art_path == next(i for i in bundle.items if i.source_url == _url(0)).file_path

    def test_existing_bundle_with_null_cover_gets_one(self, db, env):
        game = _game(db)
        bundle = _apply(db, game, _assets(_url(0)))
        bundle.cover_art_path = None
        db.commit()

        bundle = _apply(db, game, _assets(_BOX, types=["boxart_front"]), previous_assets="keep")

        assert bundle.cover_art_path == next(i for i in bundle.items if i.source_url == _BOX).file_path

    def test_existing_cover_is_never_overwritten(self, db, env):
        game = _game(db)
        bundle = _apply(db, game, _assets(_url(0)))
        chosen = bundle.cover_art_path

        bundle = _apply(db, game, _assets(_BOX, types=["boxart_front"]), previous_assets="keep")

        assert bundle.cover_art_path == chosen


# Game cover (cover_asset_url)


def _game_with_discs(db, count=1, display=None):
    from backend.models.game import GameItem

    game = _game(db)
    leaves = []
    for number in range(1, count + 1):
        leaf = GameItem(game_item_bundle_id=game.id, file_path=f"/library/games/doom/disc{number}.iso", disc_number=number)
        db.add(leaf)
        db.commit()
        db.refresh(leaf)
        leaves.append(leaf)
    if display is not None:
        game.display_disk_id = leaves[display].id
        db.commit()
    return game, leaves


class TestGameCover:
    def test_cover_is_set_on_the_display_disc_from_the_chosen_asset(self, db, env):
        game, leaves = _game_with_discs(db, count=2, display=1)

        bundle = _apply(
            db, game, _assets(_url(0), _BOX, types=["screenshot", "boxart_front"]), cover_asset_url=_BOX,
        )

        chosen = next(i for i in bundle.items if i.source_url == _BOX)
        db.refresh(leaves[0]), db.refresh(leaves[1])
        assert leaves[1].cover_art_path == str(Path(chosen.file_path).resolve())
        assert leaves[0].cover_art_path is None

    def test_without_cover_asset_url_the_game_cover_is_unchanged(self, db, env):
        game, leaves = _game_with_discs(db)
        leaves[0].cover_art_path = "/library/games/doom/own.jpg"
        db.commit()

        _apply(db, game, _assets(_BOX, types=["boxart_front"]))

        db.refresh(leaves[0])
        assert leaves[0].cover_art_path == "/library/games/doom/own.jpg"

    def test_asset_not_among_the_submitted_ones_is_422_before_anything_runs(self, db, env):
        from fastapi import HTTPException

        game, _ = _game_with_discs(db)

        with pytest.raises(HTTPException) as exc_info:
            _apply(db, game, _assets(_url(0)), cover_asset_url=_BOX)

        assert exc_info.value.status_code == 422
        assert "cover_asset_url" in exc_info.value.detail
        assert env.fetched == []
        assert _counts(db) == (0, 0, 0)

    def test_keep_can_choose_an_image_saved_by_an_earlier_apply(self, db, env):
        game, leaves = _game_with_discs(db)
        box_path = _apply(db, game, _assets(_BOX, types=["boxart_front"])).items[0].file_path
        env.fetched.clear()

        _apply(db, game, _assets(_BOX, _url(0), types=["boxart_front", "screenshot"]),
               previous_assets="keep", cover_asset_url=_BOX)

        db.refresh(leaves[0])
        assert leaves[0].cover_art_path == str(Path(box_path).resolve())
        assert env.fetched == [_url(0)]

    def test_cover_outside_the_library_fails_and_rolls_the_whole_apply_back(self, db, env, monkeypatch):
        from fastapi import HTTPException

        import backend.service.games.cover_from_media as cover_mod
        from backend.service.games.media_link import ApplyFailure

        def _outside(resolved, raw):
            raise HTTPException(status_code=422, detail="cover_art_path must be inside the library folder")

        monkeypatch.setattr(cover_mod, "require_cover_in_library", _outside)
        game, leaves = _game_with_discs(db)

        with pytest.raises(ApplyFailure) as exc_info:
            _apply(db, game, _assets(_BOX, types=["boxart_front"]), cover_asset_url=_BOX)

        assert exc_info.value.code == "cover_rejected"
        assert _counts(db) == (0, 0, 0)
        assert env.files() == []
        db.refresh(leaves[0])
        assert leaves[0].cover_art_path is None

    def test_game_without_discs_fails_and_leaves_nothing(self, db, env):
        from backend.service.games.media_link import ApplyFailure

        game = _game(db)

        with pytest.raises(ApplyFailure) as exc_info:
            _apply(db, game, _assets(_BOX, types=["boxart_front"]), cover_asset_url=_BOX)

        assert exc_info.value.code == "cover_rejected"
        assert "no discs" in exc_info.value.message
        assert _counts(db) == (0, 0, 0)
        assert env.files() == []
