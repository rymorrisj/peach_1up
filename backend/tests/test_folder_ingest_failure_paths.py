"""Failure-path tests for backend/service/games/folder_ingest.py's ingest_folder,
the shared entry point every upload (chunked-browser finalize, path-import,
scan-import) funnels through, and for _ingest_transaction /
_replay_undo (backend/service/games/items.py), the rollback-and-undo machinery
every ingest shape shares.

test_folder_ingest.py already covers ingest_folder's constituent pieces
(detect_disc_files, pick_folder_launch_file, dedup_disc_anchor,
_prepare_multi_disc/_persist_multi_disc_collection happy paths) but never
calls ingest_folder() itself, and nothing exercises what happens when a
failure occurs after filesystem staging has already happened, only the
happy path was covered anywhere for this pipeline. This file closes that:
every test here confirms both "fails loud" (the exception actually
propagates, is never silently swallowed) and "cleans up" (the DB rollback
and the staged filesystem rename-undo both actually ran, no orphaned
partial state left behind).
"""

from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError


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


class _FakeScanResult:
    era = "dreamcast"
    reason = "gdi header"
    requires_install = False


@pytest.fixture(autouse=True)
def _patch_detect(monkeypatch):
    import formatscout as smd
    monkeypatch.setattr(smd, "detect", lambda path: _FakeScanResult())


@pytest.fixture(autouse=True)
def _patch_era_defaults(monkeypatch):
    import backend.service.utils.era_defaults as ead
    monkeypatch.setattr(ead, "defaults_for_era", lambda era: (None, None))


def _make_disc_files(dest_dir: Path, names: list[str]) -> list[Path]:
    files = []
    for name in names:
        p = dest_dir / name
        p.write_bytes(b"\x00" * 16)
        files.append(p)
    return files


class _FakeSettings:
    def __init__(self, media_path: str):
        self._media_path = media_path

    def get(self, key, default=None):
        return self._media_path if key == "SOFTWARE_PATH" else default

    def get_env_var(self, key):
        return self._media_path if key == "SOFTWARE_PATH" else ""


def _patch_settings(monkeypatch, media_root: Path):
    import backend.core.settings as settings_mod
    monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings(str(media_root)))


# ---------------------------------------------------------------------------
# Multi-disc branch: partial-write cleanup on a generic failure after
# filesystem staging (the folder-to-slug rename) has already happened.
# ---------------------------------------------------------------------------


class TestMultiDiscGenericFailureCleansUpPartialState:
    def test_persist_failure_rolls_back_db_and_undoes_the_staging_rename(self, tmp_path, mem_session, monkeypatch):
        """_persist_multi_disc_collection raising after _prepare_multi_disc has
        already renamed the staging dir to match its slug (registering an undo
        callable) must: (1) let the exception propagate, not swallow it,
        (2) roll back the DB session, no orphaned collection/leaf rows,
        (3) replay the rename-undo, the staged directory must be found back
        under its ORIGINAL (pre-slug) name afterward, not left renamed with no
        matching DB row."""
        from backend.service.games import folder_ingest
        from backend.service.games import items as lib_svc
        from backend.models.game import GameItemBundle

        media_root = tmp_path / "media"
        media_root.mkdir()
        original_dir = media_root / "incoming_upload_xyz"
        original_dir.mkdir()
        disc_files = _make_disc_files(original_dir, ["disc1.gdi", "disc2.gdi"])

        def _boom(collection_fields, leaf_rows, db):
            raise RuntimeError("simulated disk error during persist")

        monkeypatch.setattr(lib_svc, "_persist_multi_disc_collection", _boom)

        with pytest.raises(RuntimeError, match="simulated disk error during persist"):
            folder_ingest.ingest_folder(original_dir, disc_files, "Sonic Adventure", mem_session, media_root)

        # (1)/(3) staged directory was renamed to the "sonic-adventure" slug by
        # _prepare_multi_disc before the forced failure; the undo must have
        # renamed it back to its original name, not left it stranded under the
        # slug name with no DB row to justify it.
        assert original_dir.is_dir()
        assert not (media_root / "sonic-adventure").exists()

        # (2) no DB row survives the rollback.
        assert mem_session.query(GameItemBundle).count() == 0

    def test_slug_collision_on_commit_rolls_back_and_undoes_rename(self, tmp_path, mem_session, monkeypatch):
        """A slug unique-violation IntegrityError at commit time (the
        concurrent-insert race _ingest_transaction's docstring calls out)
        must translate to _SlugCollision, not a raw driver error, and still
        run the exact same rollback + undo-replay as any other failure."""
        from backend.service.games import folder_ingest
        from backend.service.games.items import _SlugCollision
        from backend.models.game import GameItemBundle
        from sqlalchemy.orm import Session as _Session

        media_root = tmp_path / "media"
        media_root.mkdir()
        original_dir = media_root / "incoming_upload_xyz"
        original_dir.mkdir()
        disc_files = _make_disc_files(original_dir, ["disc1.gdi", "disc2.gdi"])

        def _commit_boom(self):
            raise IntegrityError(
                "INSERT INTO game_item_bundles ...",
                {},
                Exception("UNIQUE constraint failed: game_item_bundles.slug"),
            )

        monkeypatch.setattr(_Session, "commit", _commit_boom)

        with pytest.raises(_SlugCollision):
            folder_ingest.ingest_folder(original_dir, disc_files, "Sonic Adventure", mem_session, media_root)

        assert original_dir.is_dir()
        assert not (media_root / "sonic-adventure").exists()
        assert mem_session.query(GameItemBundle).count() == 0


# ---------------------------------------------------------------------------
# Collection-of-one branch: validation failure must never reach the DB or
# touch the filesystem at all, it runs before staging starts.
# ---------------------------------------------------------------------------


class TestCollectionOfOneValidationFailureLeavesNoPartialState:
    def test_no_recognizable_launch_file_raises_422_before_any_db_write(self, tmp_path, mem_session):
        from backend.service.games import folder_ingest
        from backend.models.game import GameItemBundle

        media_root = tmp_path / "media"
        media_root.mkdir()
        dest_dir = media_root / "unrecognized_upload"
        dest_dir.mkdir()
        junk = dest_dir / "readme.txt"
        junk.write_text("no launchable content here")

        with pytest.raises(HTTPException) as exc_info:
            folder_ingest.ingest_folder(dest_dir, [junk], "Mystery Upload", mem_session, media_root)

        assert exc_info.value.status_code == 422
        assert mem_session.query(GameItemBundle).count() == 0
        # Nothing was staged or moved, this fails before any filesystem write.
        assert junk.exists()
        assert dest_dir.is_dir()

    def test_duplicate_media_path_raises_item_already_exists_no_second_row(self, tmp_path, mem_session, monkeypatch):
        """The collection-of-one path's duplicate guard
        (_guard_directory_source, run during _prepare_item's validate_source
        stage) must reject a folder that's already tracked, from a prior real
        ingest_folder call, before staging starts, leaving exactly the
        original row in place, not a second row or a half-written one.
        Builds the "already tracked" state through a real first ingest_folder
        call (as production would produce it) rather than a hand-typed
        GameItem row, so the folder_path/file_path strings are guaranteed to
        match however _prepare_item actually normalises them."""
        from backend.service.games import folder_ingest
        from backend.service.games.items import _ItemAlreadyExists
        from backend.models.game import GameItemBundle

        media_root = tmp_path / "media"
        media_root.mkdir()
        games_root = media_root / "games"
        games_root.mkdir()
        src_dir = games_root / "doom"
        src_dir.mkdir()
        exe = src_dir / "doom.exe"
        exe.write_bytes(b"fake exe")

        _patch_settings(monkeypatch, media_root)
        # The class-wide _patch_detect fixture always reports "dreamcast",
        # which cannot resolve a .exe inside this DOS folder, so the first
        # ingest's file_path lands on the folder itself instead of doom.exe,
        # and the second call's written_paths then holds a directory, not a
        # file, tripping pick_folder_launch_file's 422 before the duplicate
        # guard is ever reached. Override to a DOS-era result so the first
        # ingest resolves file_path to doom.exe the way a real DOS folder does.
        import formatscout as smd

        class _DosScanResult:
            era = "dos"
            reason = "exe header"
            requires_install = False

        monkeypatch.setattr(smd, "detect", lambda path: _DosScanResult())

        result_type, collection, disc_count = folder_ingest.ingest_folder(
            src_dir, [exe], "Doom", mem_session, media_root,
        )
        assert mem_session.query(GameItemBundle).count() == 1
        canonical_folder = Path(collection.items[0].folder_path)
        canonical_exe = Path(collection.items[0].file_path)
        assert canonical_folder.is_dir()

        with pytest.raises(_ItemAlreadyExists):
            folder_ingest.ingest_folder(canonical_folder, [canonical_exe], "Doom Again", mem_session, media_root)

        assert mem_session.query(GameItemBundle).count() == 1


# ---------------------------------------------------------------------------
# _replay_undo: best-effort by construction, a failing undo callable must
# never mask the original triggering exception, and must not stop the
# remaining undo callables from still running.
# ---------------------------------------------------------------------------


class TestReplayUndoIsBestEffort:
    def test_oserror_from_one_undo_callable_does_not_stop_the_rest(self):
        from backend.service.games.items import _replay_undo

        ran: list[str] = []

        def _first():
            ran.append("first")

        def _second_raises():
            ran.append("second")
            raise OSError("simulated: file locked, rename-back failed")

        def _third():
            ran.append("third")

        # Replayed in reverse order: third, second (raises), first.
        _replay_undo([_first, _second_raises, _third])

        assert ran == ["third", "second", "first"]

    def test_replay_undo_itself_never_raises(self):
        """The whole point of swallowing OSError per-callable: the caller in
        _ingest_transaction is already inside an except block re-raising the
        real triggering exception, _replay_undo raising over that would
        replace it with an unrelated cleanup failure."""
        from backend.service.games.items import _replay_undo

        def _raises():
            raise OSError("disk full during undo")

        _replay_undo([_raises])  # must not raise
