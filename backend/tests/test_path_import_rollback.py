"""Tests for backend/service/games/path_import.py's rollback and ordering
guarantees.

Created as a separate file rather than extending
test_folder_ingest_failure_paths.py: that file's own docstring scopes it to
folder_ingest.ingest_folder and the _replay_undo/_ingest_transaction
undo-callable machinery in items.py, a different module with a different
rollback shape. stage_from_source's guarantee is a plain try/except plus a
single ordered "verify then delete" step, not the undo-callable-list
pattern, so it gets its own file.

Module docstring under test: "the source is never deleted before a copy is
verified... the source is never deleted before a copy is verified, so a
truncated/corrupted cross-device copy cannot destroy the only remaining
copy of the data." Each test below that locks in a piece of that guarantee
says so.
"""

import errno
from pathlib import Path
from types import SimpleNamespace

import pytest


class TestStageFromSourceCrossDeviceMoveOrdering:
    def test_source_removal_only_happens_after_dest_copy_is_verified(self, tmp_path, monkeypatch):
        """Locks in: the source is never deleted before a copy is verified.
        Intercepts Path.unlink (the actual deletion call site for a file-kind
        source) and asserts, at the moment it fires, that the destination
        copy already exists with the full expected byte count, proving the
        integrity check ran and passed strictly before removal."""
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
        """Locks in the other half of the same guarantee: when the post-copy
        byte-count check fails, the source must still be there afterward
        (never deleted) and the partial destination directory must be gone,
        not left as orphaned partial state."""
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


class TestRenameSameFilesystemErrorPropagation:
    def test_non_exdev_oserror_propagates_instead_of_falling_back(self, tmp_path, monkeypatch):
        """_rename_same_filesystem must re-raise any OSError that is not
        EXDEV/ERROR_NOT_SAME_DEVICE, a permissions failure must never be
        silently misread as 'needs the cross-device copy fallback.'"""
        from backend.service.games import path_import

        def _raise_permission(src, dst):
            raise OSError(errno.EACCES, "Permission denied")

        monkeypatch.setattr(path_import.os, "rename", _raise_permission)

        source = tmp_path / "source.iso"
        dest = tmp_path / "dest.iso"

        with pytest.raises(OSError) as exc_info:
            path_import._rename_same_filesystem(source, dest)

        assert exc_info.value.errno == errno.EACCES


class TestImportBackgroundInPlaceRouting:
    def test_source_under_domain_root_never_creates_a_staging_dir(self, tmp_path, monkeypatch):
        """A source already resolving under the domain root (e.g.
        SOFTWARE_PATH/games) must take _import_in_place, never
        stage_from_source, so no disposable staging directory is ever
        created for it. Asserted by making stage_from_source raise if
        called at all, not just by checking the result shape."""
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
