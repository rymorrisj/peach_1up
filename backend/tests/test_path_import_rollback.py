"""Tests for backend/service/games/path_import.py's rollback and ordering
guarantees.

The main one: the source is never deleted before a copy is verified, so a
truncated or corrupted cross-device copy cannot destroy the only remaining
copy of the data.

The separate undo-callable rollback in items.py is in
test_folder_ingest_failure_paths.py.
"""

import errno
from pathlib import Path
from types import SimpleNamespace

import pytest


class TestStageFromSourceCrossDeviceMoveOrdering:
    def test_source_removal_only_happens_after_dest_copy_is_verified(self, tmp_path, monkeypatch):
        """Intercepts Path.unlink, the deletion call site for a file-kind
        source, and asserts at the moment it fires that the destination copy
        is already complete. Checking after the call would not distinguish
        verify-then-delete from delete-then-verify."""
        from backend.service.games import path_import

        monkeypatch.setattr(path_import, "_rename_same_filesystem", lambda source, dest: False)

        domain_root = tmp_path / "domain"
        source = tmp_path / "incoming" / "game.iso"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"\x00" * 4096)
        source_size_before = source.stat().st_size

        unlink_calls: list[Path] = []
        real_unlink = Path.unlink

        def _tracking_unlink(self, *a, **kw):
            unlink_calls.append(self)
            dest_files = [p for p in domain_root.rglob("*") if p.is_file()]
            assert len(dest_files) == 1
            assert dest_files[0].stat().st_size == source_size_before
            return real_unlink(self, *a, **kw)

        monkeypatch.setattr(Path, "unlink", _tracking_unlink)

        result = path_import.stage_from_source(source, "Game", domain_root, move=True)

        assert unlink_calls == [source]
        assert not source.exists()
        assert result.paths[0].exists()
        assert result.paths[0].stat().st_size == source_size_before

    def test_size_mismatch_never_deletes_source_and_cleans_up_partial_dest(self, tmp_path, monkeypatch):
        """The other half: a failed byte-count check must leave the source
        intact and the partial destination removed, not orphaned."""
        from backend.service.games import path_import

        monkeypatch.setattr(path_import, "_rename_same_filesystem", lambda source, dest: False)

        domain_root = tmp_path / "domain"
        source = tmp_path / "incoming" / "game.iso"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"\x00" * 4096)

        def _truncated_copy(src, dst, *a, **kw):
            Path(dst).write_bytes(b"\x00" * 10)
            return dst

        monkeypatch.setattr(path_import.shutil, "copy2", _truncated_copy)

        with pytest.raises(ValueError, match="expected 4096 bytes"):
            path_import.stage_from_source(source, "Game", domain_root, move=True)

        assert source.exists()
        assert source.stat().st_size == 4096
        assert list(domain_root.rglob("*")) == []


class TestStageFromSourceCopyMode:
    def test_move_false_leaves_the_source_in_place(self, tmp_path, monkeypatch):
        """The delete_original=False contract: copy only, never a deletion,
        and never even an attempted rename."""
        from backend.service.games import path_import

        def _rename_should_not_be_called(source, dest):
            raise AssertionError("_rename_same_filesystem must not run when move=False")
        monkeypatch.setattr(path_import, "_rename_same_filesystem", _rename_should_not_be_called)

        domain_root = tmp_path / "domain"
        source = tmp_path / "incoming" / "game.iso"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"\x00" * 4096)

        result = path_import.stage_from_source(source, "Game", domain_root, move=False)

        assert source.exists()
        assert source.stat().st_size == 4096
        assert result.paths[0].read_bytes() == source.read_bytes()
        assert result.kind == "file"


class TestStageFromSourceSameFilesystemMove:
    def test_successful_rename_skips_both_the_copy_and_the_delete(self, tmp_path, monkeypatch):
        """A same-filesystem move is atomic, so there is no copy to verify and
        no separate source deletion. copy2 firing would mean a transient
        double-disk-usage window the rename path is supposed to avoid."""
        from backend.service.games import path_import

        def _copy_should_not_be_called(src, dst, *a, **kw):
            raise AssertionError("copy2 must not run after a successful rename")
        monkeypatch.setattr(path_import.shutil, "copy2", _copy_should_not_be_called)

        domain_root = tmp_path / "domain"
        source = tmp_path / "incoming" / "game.iso"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"\x00" * 4096)

        unlink_calls: list[Path] = []
        real_unlink = Path.unlink

        def _tracking_unlink(self, *a, **kw):
            unlink_calls.append(self)
            return real_unlink(self, *a, **kw)

        monkeypatch.setattr(Path, "unlink", _tracking_unlink)

        result = path_import.stage_from_source(source, "Game", domain_root, move=True)

        assert unlink_calls == []
        assert not source.exists()
        assert result.paths[0].stat().st_size == 4096


class TestRenameSameFilesystemErrorPropagation:
    def test_non_exdev_oserror_propagates_instead_of_falling_back(self, tmp_path, monkeypatch):
        """Only EXDEV/ERROR_NOT_SAME_DEVICE means "fall back to copy". A
        permissions failure misread as that would copy, then delete the
        source, on a move the OS just refused."""
        from backend.service.games import path_import

        def _raise_permission(src, dst):
            raise OSError(errno.EACCES, "Permission denied")

        monkeypatch.setattr(path_import.os, "rename", _raise_permission)

        source = tmp_path / "source.iso"
        dest = tmp_path / "dest.iso"

        with pytest.raises(OSError) as exc_info:
            path_import._rename_same_filesystem(source, dest)

        assert exc_info.value.errno == errno.EACCES


# INTEGRATION TEST NEEDED: the cross-device fallback is forced here by
# stubbing _rename_same_filesystem, so the branch that selects it is never
# exercised. Needs a real move between two real volumes to confirm os.rename
# raises EXDEV/ERROR_NOT_SAME_DEVICE (not something else), that copytree
# handles the tree, and that the source is removed only afterwards.


class TestImportBackgroundInPlaceRouting:
    def test_source_under_domain_root_never_creates_a_staging_dir(self, tmp_path, monkeypatch):
        """A source already under the domain root must take _import_in_place.
        stage_from_source's dest_dir would be the source itself, so
        finalize_reassembled's failure cleanup would delete the user's data.
        stage_from_source is patched to raise rather than checked after."""
        from sqlalchemy.pool import StaticPool
        from sqlmodel import create_engine
        from backend.service.games import path_import
        from backend.core import database as database_mod
        from backend.core import jobs as jobs_mod

        engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        monkeypatch.setattr(database_mod, "get_engine", lambda: engine)

        root = tmp_path / "software"
        games_root = root / "games"
        games_root.mkdir(parents=True)
        src_dir = games_root / "doom"
        src_dir.mkdir()
        (src_dir / "doom.exe").write_bytes(b"fake exe")

        fake_collection = SimpleNamespace(id=1, title="Doom")
        monkeypatch.setattr(path_import.lib_svc, "_ingest_media_entry", lambda source, title, db: fake_collection)

        def _stage_should_not_be_called(*a, **kw):
            raise AssertionError("stage_from_source must not be called for an in-place source")
        monkeypatch.setattr(path_import, "stage_from_source", _stage_should_not_be_called)

        job_id = jobs_mod.create("upload")

        path_import.import_background(str(src_dir), "Doom", str(root), job_id, delete_original=False)

        job = jobs_mod.get(job_id)
        assert job["status"] == "done"
        assert list(games_root.iterdir()) == [src_dir]

    def test_duplicate_import_fails_the_job_with_a_named_message(self, tmp_path, monkeypatch):
        """_ItemAlreadyExists carries no message of its own, so str(exc) is
        empty and jobs.fail() used to write a blank one, leaving the Activity
        panel showing a bare status word. The title must appear instead."""
        from sqlalchemy.pool import StaticPool
        from sqlmodel import create_engine
        from backend.service.games import path_import
        from backend.core import database as database_mod
        from backend.core import jobs as jobs_mod

        engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        monkeypatch.setattr(database_mod, "get_engine", lambda: engine)

        root = tmp_path / "software"
        games_root = root / "games"
        games_root.mkdir(parents=True)
        src_dir = games_root / "doom"
        src_dir.mkdir()

        existing = SimpleNamespace(id=1, title="Doom")

        def _raise_already_exists(source, title, db):
            raise path_import.lib_svc._ItemAlreadyExists(existing)
        monkeypatch.setattr(path_import.lib_svc, "_ingest_media_entry", _raise_already_exists)

        job_id = jobs_mod.create("upload")

        path_import.import_background(str(src_dir), "Doom", str(root), job_id, delete_original=False)

        job = jobs_mod.get(job_id)
        assert job["status"] == "error"
        assert job["error"] == '"Doom" is already in the library.'
