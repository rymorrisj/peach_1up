"""Tests for folder-upload ingest decision tree.

Covers three functions introduced in the folder-upload / multi-disc feature:

- _pick_folder_launch_file (library route): single-disc pre-flight launch file
  selection including GDI-first priority.
- _detect_disc_files (library route): multi-disc detection and 422 guard for
  ambiguous mixed .cue/.gdi uploads.
- the multi-disc ingest stages (library service): _prepare_multi_disc plus
  _persist_multi_disc_collection, creating a bundle + one leaf per disc.

.gdi leads _EXECUTABLE_PRIORITY in profile_builder.py deliberately. Without
it, _prepare_item stores executable_path=None for Dreamcast folders even when
_pick_folder_launch_file resolved the .gdi correctly.
"""

from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlmodel import select
from formatscout.result import Method, ScanResult

from backend.tests.scan_factory import make_scan


# ---------------------------------------------------------------------------
# _pick_folder_launch_file
# ---------------------------------------------------------------------------

class TestPickFolderLaunchFile:
    def _call(self, *names: str, base: Path | None = None) -> Path:
        from backend.service.games.folder_ingest import pick_folder_launch_file
        if base is None:
            paths = [Path(n) for n in names]
        else:
            paths = [base / n for n in names]
        return pick_folder_launch_file(paths)

    def test_gdi_returned_first_dreamcast_platform(self, tmp_path):
        (tmp_path / "track.gdi").write_bytes(b"")
        result = self._call("track.gdi", base=tmp_path)
        assert result.suffix.lower() == ".gdi"

    def test_cue_returned_when_no_gdi_present(self, tmp_path):
        (tmp_path / "game.cue").write_bytes(b"")
        result = self._call("game.cue", base=tmp_path)
        assert result.suffix.lower() == ".cue"

    def test_gdi_beats_cue_when_both_present(self, tmp_path):
        (tmp_path / "track.gdi").write_bytes(b"")
        (tmp_path / "game.cue").write_bytes(b"")
        result = self._call("track.gdi", "game.cue", base=tmp_path)
        assert result.suffix.lower() == ".gdi"

    def test_no_launch_file_raises_422(self):
        from backend.service.games.folder_ingest import pick_folder_launch_file
        with pytest.raises(HTTPException) as exc_info:
            pick_folder_launch_file([Path("readme.txt"), Path("cover.jpg")])
        assert exc_info.value.status_code == 422

    def test_iso_returned_when_no_gdi_or_cue(self, tmp_path):
        (tmp_path / "game.iso").write_bytes(b"")
        result = self._call("game.iso", base=tmp_path)
        assert result.suffix.lower() == ".iso"


# ---------------------------------------------------------------------------
# _detect_disc_files
# ---------------------------------------------------------------------------

class TestDetectDiscFiles:
    def _call(self, *names: str) -> list[Path]:
        from backend.service.games.folder_ingest import detect_disc_files
        return detect_disc_files([Path(n) for n in names])

    def test_zero_disc_files_returns_empty(self):
        result = self._call("game.iso", "cover.jpg")
        assert result == []

    def test_single_cue_returns_empty_single_disc_path(self):
        result = self._call("game.cue", "game.bin", "cover.jpg")
        assert result == []

    def test_single_gdi_returns_empty_single_disc_path(self):
        result = self._call("track.gdi", "track01.bin")
        assert result == []

    def test_two_cue_files_returns_sorted_pair(self):
        result = self._call("disc2.cue", "disc1.cue")
        assert len(result) == 2
        assert result[0].name == "disc1.cue"
        assert result[1].name == "disc2.cue"

    def test_two_gdi_files_returns_sorted_pair(self):
        result = self._call("disc2.gdi", "disc1.gdi")
        assert len(result) == 2
        assert result[0].name == "disc1.gdi"
        assert result[1].name == "disc2.gdi"

    def test_mixed_cue_and_gdi_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            self._call("disc1.cue", "disc2.gdi")
        assert exc_info.value.status_code == 422
        assert "ambiguous" in exc_info.value.detail.lower() or "mixed" in exc_info.value.detail.lower()

    def test_three_cue_files_returns_all_sorted(self):
        result = self._call("disc3.cue", "disc1.cue", "disc2.cue")
        assert len(result) == 3
        assert [p.name for p in result] == ["disc1.cue", "disc2.cue", "disc3.cue"]


# ---------------------------------------------------------------------------
# Multi-disc ingest stages: DB integration
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_session():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, Session, create_engine
    import backend.models  # noqa: F401, registers all ORM tables

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _create_multi_disc_collection(disc_files, title, db, *, staging_dir=None):
    """Test-local driver for the multi-disc ingest stages.

    _create_multi_disc_collection was split into _prepare_multi_disc (detect +
    stage_files, no DB writes) and _persist_multi_disc_collection (no commit),
    with the transaction owned by the caller. This runs the same
    prepare/persist/commit sequence folder_ingest.ingest_folder and
    software_games.finalize_reassembled now run, so these tests keep exercising
    the production sequence rather than a shortcut through it.
    """
    from backend.service.games.items import (
        _ingest_transaction,
        _persist_multi_disc_collection,
        _prepare_multi_disc,
    )

    undo_ops: list = []
    with _ingest_transaction(db, undo_ops):
        collection_fields, leaf_rows = _prepare_multi_disc(
            disc_files, title, db, staging_dir=staging_dir, undo_stack=undo_ops
        )
        collection = _persist_multi_disc_collection(collection_fields, leaf_rows, db)
        db.commit()
    db.refresh(collection)
    return collection


def _fake_scan_result() -> ScanResult:
    return make_scan("dreamcast", reason="gdi header", method=Method.MAGIC)


class TestCreateMultiDiscSet:
    @pytest.fixture(autouse=True)
    def _patch_detect(self, monkeypatch):
        import formatscout as smd
        monkeypatch.setattr(smd, "detect", lambda path: _fake_scan_result())

    @pytest.fixture(autouse=True)
    def _patch_platform_defaults(self, monkeypatch):
        import backend.service.utils.platform_defaults as ead
        # Return (None, None) to skip the profile lookup, not under test here.
        monkeypatch.setattr(ead, "defaults_for_platform", lambda platform: (None, None))

    def _make_disc_files(self, tmp_path: Path, names: list[str]) -> list[Path]:
        files = []
        for name in names:
            p = tmp_path / name
            p.write_bytes(b"\x00" * 16)
            files.append(p)
        return files

    def test_two_disc_set_creates_one_set_and_two_items(self, tmp_path, mem_session):
        from backend.models.game import GameItemBundle, GameItem

        disc_files = self._make_disc_files(tmp_path, ["disc1.gdi", "disc2.gdi"])
        _create_multi_disc_collection(disc_files, "Sonic Adventure", mem_session)

        sets = mem_session.exec(select(GameItemBundle)).all()
        assert len(sets) == 1
        assert sets[0].title == "Sonic Adventure"

        items = mem_session.exec(
            select(GameItem).where(GameItem.game_item_bundle_id == sets[0].id)
        ).all()
        assert len(items) == 2

    def test_launch_disk_id_points_to_first_disc(self, tmp_path, mem_session):
        from backend.models.game import GameItem

        disc_files = self._make_disc_files(tmp_path, ["disc1.gdi", "disc2.gdi"])
        library_set = _create_multi_disc_collection(disc_files, "Test Game", mem_session)

        items = mem_session.exec(
            select(GameItem)
            .where(GameItem.game_item_bundle_id == library_set.id)
            .order_by(GameItem.disc_number)
        ).all()
        assert library_set.launch_disk_id == items[0].id

    def test_each_item_has_gdi_as_executable_path(self, tmp_path, mem_session):
        from backend.models.game import GameItem

        disc_files = self._make_disc_files(tmp_path, ["disc1.gdi", "disc2.gdi"])
        library_set = _create_multi_disc_collection(disc_files, "Dreamcast Game", mem_session)

        items = mem_session.exec(
            select(GameItem)
            .where(GameItem.game_item_bundle_id == library_set.id)
            .order_by(GameItem.disc_number)
        ).all()
        for idx, item in enumerate(items):
            assert item.executable_path == str(disc_files[idx])
            assert item.file_path == str(disc_files[idx])
            assert Path(item.executable_path).suffix.lower() == ".gdi"

    def test_disc_numbers_are_sequential_from_one(self, tmp_path, mem_session):
        from backend.models.game import GameItem

        disc_files = self._make_disc_files(tmp_path, ["disc1.cue", "disc2.cue", "disc3.cue"])
        library_set = _create_multi_disc_collection(disc_files, "Triple-Disc Game", mem_session)

        items = mem_session.exec(
            select(GameItem)
            .where(GameItem.game_item_bundle_id == library_set.id)
            .order_by(GameItem.disc_number)
        ).all()
        assert [i.disc_number for i in items] == [1, 2, 3]

    def test_platform_from_detector_stored_on_set(self, tmp_path, mem_session):
        from backend.models.game import GameItemBundle

        disc_files = self._make_disc_files(tmp_path, ["d1.gdi", "d2.gdi"])
        library_set = _create_multi_disc_collection(disc_files, "Platform Test", mem_session)

        stored = mem_session.get(GameItemBundle, library_set.id)
        assert stored.platform == "dreamcast"

    def test_content_rating_detected_from_disc_one_filename(self, tmp_path, mem_session):
        """detect_rating is called with disc_files[0] only, a bracketed rating
        tag on disc 1's filename must land on the GameItemBundle, matching
        rating_detect's strict (bracket-guarded) filename-stem fallback."""
        from backend.models.game import GameItemBundle

        disc_files = self._make_disc_files(tmp_path, ["disc1 [M].gdi", "disc2.gdi"])
        library_set = _create_multi_disc_collection(disc_files, "Rated Game", mem_session)

        stored = mem_session.get(GameItemBundle, library_set.id)
        assert stored.content_rating == "M"

    def test_cover_art_found_next_to_disc_one_lands_on_first_disc_only(self, tmp_path, mem_session):
        """_find_cover is called on disc_files[0]'s parent, a cover image found
        there must land on disc 1's item only, never on later discs."""
        from backend.models.game import GameItem

        (tmp_path / "cover.jpg").write_bytes(b"\xff\xd8\xff")
        disc_files = self._make_disc_files(tmp_path, ["disc1.gdi", "disc2.gdi"])
        library_set = _create_multi_disc_collection(disc_files, "Cover Game", mem_session)

        items = mem_session.exec(
            select(GameItem)
            .where(GameItem.game_item_bundle_id == library_set.id)
            .order_by(GameItem.disc_number)
        ).all()
        assert items[0].cover_art_path == str(tmp_path / "cover.jpg")
        assert items[1].cover_art_path is None


# ---------------------------------------------------------------------------
# dedup_disc_anchor, content-hash dedup for multi-disc disc-1 anchors
# ---------------------------------------------------------------------------

class TestDedupDiscAnchor:
    @pytest.fixture(autouse=True)
    def _patch_detect(self, monkeypatch):
        import formatscout as smd
        monkeypatch.setattr(smd, "detect", lambda path: _fake_scan_result())

    @pytest.fixture(autouse=True)
    def _patch_platform_defaults(self, monkeypatch):
        import backend.service.utils.platform_defaults as ead
        monkeypatch.setattr(ead, "defaults_for_platform", lambda platform: (None, None))

    def test_does_not_repoint_to_a_match_in_an_untracked_folder(self, tmp_path, mem_session):
        """A byte-identical file in an untracked leftover folder is NOT reused by
        the anchor dedup: repointing disc 1 alone would split the set across two
        folders. Whole untracked leftover sets are adopted by leftover_folder
        instead (TestFolderUploadAdoptsLeftover). The upload copy is kept."""
        from backend.service.games.folder_ingest import dedup_disc_anchor

        media_root = tmp_path
        content = b"identical disc1 bytes for dedup anchor test"

        orphan_dir = media_root / "orphan"
        orphan_dir.mkdir()
        orphan_disc1 = orphan_dir / "disc1.gdi"
        orphan_disc1.write_bytes(content)

        incoming_dir = media_root / "incoming"
        incoming_dir.mkdir()
        new_disc1 = incoming_dir / "disc1.gdi"
        new_disc1.write_bytes(content)

        assert dedup_disc_anchor(media_root, new_disc1, mem_session) == new_disc1
        assert new_disc1.exists()
        assert orphan_disc1.read_bytes() == content

    def test_repoints_to_a_non_leaf_match_inside_a_db_tracked_folder(self, tmp_path, mem_session):
        """Unchanged DB-tracked behavior: the match is not itself a live leaf but
        its folder is tracked, so the anchor is repointed and the upload copy
        removed."""
        from backend.service.games.folder_ingest import dedup_disc_anchor
        from backend.models.game import GameItemBundle, GameItem

        media_root = tmp_path
        content = b"identical disc1 bytes inside a tracked folder"

        tracked_dir = media_root / "tracked"
        tracked_dir.mkdir()
        stray_disc1 = tracked_dir / "disc1.gdi"
        stray_disc1.write_bytes(content)
        collection = GameItemBundle(title="Tracked Game", platform="dreamcast", slug="tracked-game")
        mem_session.add(collection)
        mem_session.flush()
        mem_session.add(GameItem(
            game_item_bundle_id=collection.id,
            disc_number=1,
            file_path=str(tracked_dir / "main.gdi"),
            folder_path=str(tracked_dir.resolve()),
        ))
        mem_session.commit()

        incoming_dir = media_root / "incoming"
        incoming_dir.mkdir()
        new_disc1 = incoming_dir / "disc1.gdi"
        new_disc1.write_bytes(content)

        assert dedup_disc_anchor(media_root, new_disc1, mem_session) == stray_disc1.resolve()
        assert not new_disc1.exists()

    def test_raises_item_already_exists_when_duplicate_is_still_tracked(self, tmp_path, mem_session):
        """A byte-identical file that is still a live GameItem.file_path must
        not be silently repointed, that would create a second tracked row
        sharing one file_path with an existing collection. dedup_disc_anchor
        raises _ItemAlreadyExists instead, same as the file-kind upload path."""
        from backend.service.games.folder_ingest import dedup_disc_anchor
        from backend.service.games.items import _ItemAlreadyExists
        from backend.models.game import GameItemBundle, GameItem

        media_root = tmp_path
        content = b"identical disc1 bytes still tracked by a live item"

        tracked_dir = media_root / "tracked"
        tracked_dir.mkdir()
        tracked_disc1 = tracked_dir / "disc1.gdi"
        tracked_disc1.write_bytes(content)

        existing_collection = GameItemBundle(title="Existing Game", platform="dreamcast", slug="existing-game")
        mem_session.add(existing_collection)
        mem_session.flush()
        existing_leaf = GameItem(
            game_item_bundle_id=existing_collection.id,
            disc_number=1,
            file_path=str(tracked_disc1.resolve()),
            executable_path=str(tracked_disc1.resolve()),
        )
        mem_session.add(existing_leaf)
        mem_session.commit()

        incoming_dir = media_root / "incoming2"
        incoming_dir.mkdir()
        new_disc1 = incoming_dir / "disc1.gdi"
        new_disc1.write_bytes(content)

        with pytest.raises(_ItemAlreadyExists) as exc_info:
            dedup_disc_anchor(media_root, new_disc1, mem_session)

        assert exc_info.value.collection.id == existing_collection.id
        assert new_disc1.exists()  # rejection path must not delete the new upload


# ---------------------------------------------------------------------------
# Folder upload of a game whose folder already sits in the library untracked:
# index the leftover in place (DB rows only), never import a second copy.
# ---------------------------------------------------------------------------

_TITLE = "Armored Core USA"
_DISC1 = b"disc one bytes " * 8
_DISC2 = b"disc two bytes!! " * 7


class _FakeSettings:
    def __init__(self, media_path: str):
        self._media_path = media_path

    def get(self, key, default=None):
        return self._media_path if key == "SOFTWARE_PATH" else default

    def get_env_var(self, key):
        return self._media_path if key == "SOFTWARE_PATH" else ""


@pytest.fixture
def library(tmp_path, monkeypatch) -> Path:
    """Resolved games root under a patched SOFTWARE_PATH, a fresh dedup index,
    and stubbed detect/classify so only the adoption logic is under test."""
    from types import SimpleNamespace

    import backend.core.settings as settings_mod
    import backend.service.utils.platform_defaults as ead
    import formatscout as smd
    from backend.service.utils import media_dup_index

    media_root = (tmp_path / "media").resolve()
    games_root = media_root / "games"
    games_root.mkdir(parents=True)
    monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings(str(media_root)))
    monkeypatch.setattr(smd, "detect", lambda path: _fake_scan_result())
    monkeypatch.setattr(
        smd, "classify",
        lambda *a, **k: SimpleNamespace(status="unchecked", similarity=None, computed_sha1=None),
    )
    monkeypatch.setattr(ead, "defaults_for_platform", lambda platform: (None, None))
    media_dup_index._index.clear()
    monkeypatch.setattr(media_dup_index, "_built_for", None)
    return games_root


def _write_folder(parent: Path, name: str, files: dict[str, bytes]) -> Path:
    folder = parent / name
    folder.mkdir()
    for file_name, data in files.items():
        (folder / file_name).write_bytes(data)
    return folder


def _upload(games_root: Path, name: str, files: dict[str, bytes]) -> tuple[Path, list[Path]]:
    """A staged upload folder (what reassemble() leaves behind) and its files."""
    folder = _write_folder(games_root, name, files)
    return folder, [folder / n for n in files]


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir()) if p.is_file()}


def _bundle_count(db) -> int:
    from sqlmodel import func
    from backend.models.game import GameItemBundle

    return db.exec(select(func.count()).select_from(GameItemBundle)).one()


def _track(db, folder: Path, file_name: str) -> None:
    """A live bundle whose single leaf is *folder*/*file_name*, folder owned."""
    from backend.models.game import GameItemBundle, GameItem

    bundle = GameItemBundle(title="Tracked Game", platform="dreamcast", slug="tracked-game")
    db.add(bundle)
    db.flush()
    db.add(GameItem(
        game_item_bundle_id=bundle.id,
        disc_number=1,
        file_path=str(folder / file_name),
        folder_path=str(folder),
        folder_owned=True,
    ))
    db.commit()


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available in this environment")


def _leaves(collection) -> list:
    return sorted(collection.items, key=lambda leaf: leaf.disc_number)


class TestFolderUploadAdoptsLeftover:
    def _ingest(self, staged: Path, paths: list[Path], games_root: Path, db):
        from backend.service.games import folder_ingest

        return folder_ingest.ingest_folder(staged, paths, _TITLE, db, games_root)

    # (a) single disc, matching untracked leftover
    def test_single_disc_matching_leftover_is_adopted_in_place(self, library, mem_session):
        leftover = _write_folder(library, "armored-core-usa", {"game.chd": _DISC1, "cover.png": b"leftover cover"})
        before = _snapshot(leftover)
        staged, paths = _upload(library, "armored-core-usa-2", {"game.chd": _DISC1, "cover.png": b"upload cover"})

        _kind, collection, disc_count = self._ingest(staged, paths, library, mem_session)

        leaf = collection.items[0]
        assert disc_count == 1
        assert Path(leaf.folder_path) == leftover
        assert Path(leaf.file_path) == leftover / "game.chd"
        assert leaf.cover_art_path == str(leftover / "cover.png")
        assert collection.slug == "armored-core-usa"
        assert not staged.exists()
        assert [p.name for p in library.iterdir()] == ["armored-core-usa"]
        assert _snapshot(leftover) == before

    # (b) single disc, different content
    def test_single_disc_different_content_gets_suffixed_folder_and_original_is_untouched(self, library, mem_session):
        leftover = _write_folder(library, "armored-core-usa", {"game.chd": b"x" * len(_DISC1)})
        before = _snapshot(leftover)
        staged, paths = _upload(library, "armored-core-usa-2", {"game.chd": _DISC1})

        _kind, collection, _n = self._ingest(staged, paths, library, mem_session)

        assert Path(collection.items[0].folder_path) == staged
        assert staged.is_dir() and (staged / "game.chd").read_bytes() == _DISC1
        assert _snapshot(leftover) == before

    # (c) single disc, match in a DB-tracked folder: today's behavior
    def test_single_disc_match_in_tracked_folder_imports_as_new(self, library, mem_session):
        tracked = _write_folder(library, "tracked-game", {"game.chd": _DISC1})
        _track(mem_session, tracked, "game.chd")
        before = _snapshot(tracked)
        staged, paths = _upload(library, "armored-core-usa", {"game.chd": _DISC1})

        _kind, collection, _n = self._ingest(staged, paths, library, mem_session)

        assert Path(collection.items[0].folder_path) == staged
        assert staged.is_dir()
        assert _bundle_count(mem_session) == 2
        assert _snapshot(tracked) == before

    # (c) multi disc, match is a live leaf: _ItemAlreadyExists as before
    def test_multi_disc_match_that_is_a_live_leaf_still_raises_already_exists(self, library, mem_session):
        from backend.service.games.items import _ItemAlreadyExists

        tracked = _write_folder(library, "tracked-game", {"disc1.chd": _DISC1, "disc2.chd": _DISC2})
        _track(mem_session, tracked, "disc1.chd")
        staged, paths = _upload(library, "armored-core-usa", {"disc1.chd": _DISC1, "disc2.chd": _DISC2})

        with pytest.raises(_ItemAlreadyExists):
            self._ingest(staged, paths, library, mem_session)

        assert _bundle_count(mem_session) == 1
        assert staged.is_dir() and (staged / "disc1.chd").exists()

    # (d) multi disc, every disc in one untracked leftover
    def test_multi_disc_all_discs_in_one_leftover_adopts_it(self, library, mem_session):
        leftover = _write_folder(
            library, "armored-core-usa",
            {"disc1.chd": _DISC1, "disc2.chd": _DISC2, "cover.png": b"leftover cover"},
        )
        before = _snapshot(leftover)
        staged, paths = _upload(
            library, "armored-core-usa-2",
            {"disc1.chd": _DISC1, "disc2.chd": _DISC2, "cover.png": b"upload cover"},
        )

        _kind, collection, disc_count = self._ingest(staged, paths, library, mem_session)

        leaves = _leaves(collection)
        assert disc_count == 2
        assert [Path(leaf.file_path) for leaf in leaves] == [leftover / "disc1.chd", leftover / "disc2.chd"]
        assert {Path(leaf.folder_path) for leaf in leaves} == {leftover}
        assert leaves[0].cover_art_path == str(leftover / "cover.png")
        assert not staged.exists()
        assert [p.name for p in library.iterdir()] == ["armored-core-usa"]
        assert _snapshot(leftover) == before

    # (e) multi disc, partial match: nothing repointed
    def test_multi_disc_partial_match_repoints_nothing_and_imports_own_folder(self, library, mem_session):
        leftover = _write_folder(library, "armored-core-usa", {"disc1.chd": _DISC1, "disc2.chd": b"different disc two"})
        before = _snapshot(leftover)
        staged, paths = _upload(library, "armored-core-usa-2", {"disc1.chd": _DISC1, "disc2.chd": _DISC2})

        _kind, collection, disc_count = self._ingest(staged, paths, library, mem_session)

        leaves = _leaves(collection)
        assert disc_count == 2
        assert [Path(leaf.file_path) for leaf in leaves] == [staged / "disc1.chd", staged / "disc2.chd"]
        assert (staged / "disc1.chd").read_bytes() == _DISC1
        assert _snapshot(leftover) == before

    # (e) multi disc, discs matched in two different leftover folders
    def test_multi_disc_cross_folder_match_repoints_nothing(self, library, mem_session):
        first = _write_folder(library, "armored-core-usa", {"disc1.chd": _DISC1})
        second = _write_folder(library, "armored-core-usa-disc2", {"disc2.chd": _DISC2})
        before = (_snapshot(first), _snapshot(second))
        staged, paths = _upload(library, "armored-core-usa-2", {"disc1.chd": _DISC1, "disc2.chd": _DISC2})

        _kind, collection, _n = self._ingest(staged, paths, library, mem_session)

        assert {Path(leaf.folder_path) for leaf in _leaves(collection)} == {staged}
        assert (_snapshot(first), _snapshot(second)) == before

    # (f) leftover not a direct child of the games root
    def test_leftover_not_a_direct_child_is_imported_as_new(self, library, mem_session):
        nested_parent = library / "collections"
        nested_parent.mkdir()
        nested = _write_folder(nested_parent, "armored-core-usa", {"game.chd": _DISC1})
        before = _snapshot(nested)
        staged, paths = _upload(library, "armored-core-usa", {"game.chd": _DISC1})

        _kind, collection, _n = self._ingest(staged, paths, library, mem_session)

        assert Path(collection.items[0].folder_path) == staged
        assert staged.is_dir()
        assert _snapshot(nested) == before

    # (g) a symlink among the leftover's entries is refused with a 409
    def test_symlink_inside_leftover_is_refused(self, library, mem_session, tmp_path):
        leftover = _write_folder(library, "armored-core-usa", {"game.chd": _DISC1})
        outside = tmp_path / "outside.txt"
        outside.write_bytes(b"outside")
        _symlink_or_skip(leftover / "linked.txt", outside)
        staged, paths = _upload(library, "armored-core-usa-2", {"game.chd": _DISC1})

        with pytest.raises(HTTPException) as exc_info:
            self._ingest(staged, paths, library, mem_session)

        assert exc_info.value.status_code == 409
        assert "symlink" in exc_info.value.detail.lower()
        assert _bundle_count(mem_session) == 0
        assert staged.is_dir() and (leftover / "game.chd").read_bytes() == _DISC1
        assert outside.read_bytes() == b"outside"

    # (g) a symlinked leftover folder is never traversed by the index, so it
    # cannot match: imported as new, nothing is written through the link.
    def test_symlinked_leftover_folder_is_never_adopted(self, library, mem_session, tmp_path):
        real = _write_folder(tmp_path, "elsewhere", {"game.chd": _DISC1, "cover.png": b"real cover"})
        before = _snapshot(real)
        _symlink_or_skip(library / "armored-core-usa", real)
        staged, paths = _upload(library, "armored-core-usa-2", {"game.chd": _DISC1, "notes.nfo": b"nfo"})

        _kind, collection, _n = self._ingest(staged, paths, library, mem_session)

        assert Path(collection.items[0].folder_path) == staged
        assert _snapshot(real) == before

    # (g) a symlinked leftover file resolves outside the games root: imported as new
    def test_symlinked_leftover_file_is_never_adopted(self, library, mem_session, tmp_path):
        target = tmp_path / "real.chd"
        target.write_bytes(_DISC1)
        leftover = library / "armored-core-usa"
        leftover.mkdir()
        _symlink_or_skip(leftover / "game.chd", target)
        staged, paths = _upload(library, "armored-core-usa-2", {"game.chd": _DISC1})

        _kind, collection, _n = self._ingest(staged, paths, library, mem_session)

        assert Path(collection.items[0].folder_path) == staged
        assert target.read_bytes() == _DISC1
        assert (leftover / "game.chd").is_symlink()

    # (h) nothing from the upload is ever written into the adopted folder
    def test_single_disc_upload_cover_and_sidecars_never_reach_adopted_folder(self, library, mem_session):
        leftover = _write_folder(library, "armored-core-usa", {"game.chd": _DISC1, "cover.png": b"leftover cover"})
        before = _snapshot(leftover)
        staged, paths = _upload(
            library, "armored-core-usa-2",
            {"game.chd": _DISC1, "cover.png": b"UPLOAD COVER", "notes.nfo": b"nfo", "game.sav": b"sav"},
        )

        self._ingest(staged, paths, library, mem_session)

        assert sorted(p.name for p in leftover.iterdir()) == sorted(before)
        assert _snapshot(leftover) == before

    def test_multi_disc_upload_cover_and_sidecars_never_reach_adopted_folder(self, library, mem_session):
        leftover = _write_folder(library, "armored-core-usa", {"disc1.chd": _DISC1, "disc2.chd": _DISC2})
        before = _snapshot(leftover)
        staged, paths = _upload(
            library, "armored-core-usa-2",
            {"disc1.chd": _DISC1, "disc2.chd": _DISC2, "cover.png": b"UPLOAD COVER", "notes.nfo": b"nfo"},
        )

        _kind, collection, _n = self._ingest(staged, paths, library, mem_session)

        assert sorted(p.name for p in leftover.iterdir()) == sorted(before)
        assert _snapshot(leftover) == before
        assert _leaves(collection)[0].cover_art_path is None
