"""Tests for _prepare_item in backend/service/library/items.py:

- Folder rename-in-place: when a file's parent is a direct subfolder of
  games_root with a non-canonical name, the folder is renamed rather than a
  new folder being created and the file moved.
- Deduplication: re-importing the same folder or the same file path must
  raise _ItemAlreadyExists rather than creating a second DB record.
"""

from pathlib import Path

import pytest


class _FakeSettings:
    def __init__(self, media_path: str):
        self._media_path = media_path

    def get(self, key, default=None):
        return self._media_path if key == "MEDIA_PATH" else default

    def get_env_var(self, key):
        return self._media_path if key == "MEDIA_PATH" else ""


@pytest.fixture
def mem_session():
    from sqlmodel import SQLModel, Session, create_engine
    from sqlalchemy.pool import StaticPool
    import backend.models  # noqa: F401 — registers all table models

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _patch_settings(monkeypatch, media_path: Path):
    import backend.core.settings as settings_mod
    monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings(str(media_path)))


def _call_prepare(path: str, title: str, session) -> dict:
    from backend.service.library.items import _prepare_item
    return _prepare_item(path, title, session)


def _commit_row(row: dict, session):
    from backend.models.library import LibraryItem
    item = LibraryItem(**row)
    session.add(item)
    session.commit()
    return item


# ---------------------------------------------------------------------------
# Rename-in-place fix
# ---------------------------------------------------------------------------

class TestPrepareFolderRename:
    """File in a direct subfolder of games_root with a non-canonical name should
    cause that folder to be renamed in place, not create a new folder + move."""

    def test_renames_parent_folder_to_canonical_stem(self, tmp_path, mem_session, monkeypatch):
        """games_root/My Game (1993)/doom.exe → folder renamed to games_root/doom/."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        src_folder = media_root / "My Game (1993)"
        src_folder.mkdir()
        src_file = src_folder / "doom.exe"
        src_file.write_bytes(b"fake exe")

        _patch_settings(monkeypatch, media_root)
        row = _call_prepare(str(src_file), "Doom", mem_session)

        canonical = media_root / "doom"
        assert canonical.is_dir(), "Canonical folder must exist after rename"
        assert not src_folder.exists(), "Original folder must be gone after rename"
        assert (canonical / "doom.exe").is_file()
        assert row["folder_path"] == str(canonical)
        assert row["media_path"] == str(canonical / "doom.exe")

    def test_already_canonically_named_folder_no_rename(self, tmp_path, mem_session, monkeypatch):
        """File in games_root/doom/doom.exe — folder name already matches stem,
        no rename and no move should occur."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        src_folder = media_root / "doom"
        src_folder.mkdir()
        src_file = src_folder / "doom.exe"
        src_file.write_bytes(b"fake exe")

        _patch_settings(monkeypatch, media_root)
        row = _call_prepare(str(src_file), "Doom", mem_session)

        assert src_folder.is_dir(), "Correctly-named folder must still be there"
        assert src_file.is_file(), "File must not have moved"
        assert row["folder_path"] == str(src_folder)
        assert row["media_path"] == str(src_file)

    def test_canonical_target_exists_falls_back_to_move(self, tmp_path, mem_session, monkeypatch):
        """If games_root/doom/ already exists on disk, the rename branch is
        skipped and the file is moved there instead."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        existing_canonical = media_root / "doom"
        existing_canonical.mkdir()
        src_folder = media_root / "My Doom Game"
        src_folder.mkdir()
        src_file = src_folder / "doom.exe"
        src_file.write_bytes(b"fake exe")

        _patch_settings(monkeypatch, media_root)
        row = _call_prepare(str(src_file), "Doom", mem_session)

        assert (existing_canonical / "doom.exe").is_file()
        assert row["folder_path"] == str(existing_canonical)
        assert row["media_path"] == str(existing_canonical / "doom.exe")

    def test_loose_file_at_games_root_still_creates_canonical_folder(self, tmp_path, mem_session, monkeypatch):
        """A file placed directly inside games_root (loose, no parent subfolder)
        is not eligible for rename — a new folder is created and the file moved."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        src_file = media_root / "doom.exe"
        src_file.write_bytes(b"fake exe")

        _patch_settings(monkeypatch, media_root)
        row = _call_prepare(str(src_file), "Doom", mem_session)

        canonical = media_root / "doom"
        assert canonical.is_dir()
        assert (canonical / "doom.exe").is_file()
        assert not src_file.exists(), "Loose file must have been moved into the canonical folder"
        assert row["folder_path"] == str(canonical)

    def test_file_in_deeply_nested_subfolder_not_renamed(self, tmp_path, mem_session, monkeypatch):
        """A file two levels deep (games_root/a/b/file.exe) does not trigger the
        rename path — only direct subfolders of games_root qualify."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        deep_folder = media_root / "outer" / "inner"
        deep_folder.mkdir(parents=True)
        src_file = deep_folder / "doom.exe"
        src_file.write_bytes(b"fake exe")

        _patch_settings(monkeypatch, media_root)
        # _prepare_item will raise because outer/ is inside games_root but
        # inner/ is two levels deep — falls through to create+move; the
        # canonical dest_folder is games_root/doom which doesn't conflict.
        row = _call_prepare(str(src_file), "Doom", mem_session)

        canonical = media_root / "doom"
        assert canonical.is_dir()
        assert (canonical / "doom.exe").is_file()
        # The deeply-nested original folder's content was moved, not renamed.
        assert not (deep_folder / "doom.exe").exists()


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestPrepareDuplication:
    """Re-importing the same path must raise _ItemAlreadyExists."""

    def test_reimport_same_folder_raises(self, tmp_path, mem_session, monkeypatch):
        """Importing the same directory twice raises _ItemAlreadyExists."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        folder = media_root / "doom"
        folder.mkdir()
        (folder / "doom.exe").write_bytes(b"fake exe")

        from backend.service.library.items import _ItemAlreadyExists

        _patch_settings(monkeypatch, media_root)
        row = _call_prepare(str(folder), "Doom", mem_session)
        _commit_row(row, mem_session)

        with pytest.raises(_ItemAlreadyExists):
            _call_prepare(str(folder), "Doom", mem_session)

    def test_reimport_canonical_file_path_after_rename_raises(self, tmp_path, mem_session, monkeypatch):
        """After a file import renames the parent folder, re-importing via the
        canonical file path raises _ItemAlreadyExists."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        src_folder = media_root / "My Game"
        src_folder.mkdir()
        src_file = src_folder / "doom.exe"
        src_file.write_bytes(b"fake exe")

        from backend.service.library.items import _ItemAlreadyExists

        _patch_settings(monkeypatch, media_root)
        row = _call_prepare(str(src_file), "Doom", mem_session)
        _commit_row(row, mem_session)

        canonical_file = Path(row["media_path"])
        assert canonical_file.exists(), "canonical file must exist after rename"

        with pytest.raises(_ItemAlreadyExists):
            _call_prepare(str(canonical_file), "Doom Again", mem_session)

    def test_reimport_canonical_folder_path_after_rename_raises(self, tmp_path, mem_session, monkeypatch):
        """After a file import renames the parent folder, re-importing via the
        canonical folder path raises _ItemAlreadyExists."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        src_folder = media_root / "My Game"
        src_folder.mkdir()
        (src_folder / "doom.exe").write_bytes(b"fake exe")

        from backend.service.library.items import _ItemAlreadyExists

        _patch_settings(monkeypatch, media_root)
        row = _call_prepare(str(src_folder / "doom.exe"), "Doom", mem_session)
        _commit_row(row, mem_session)

        canonical_folder = Path(row["folder_path"])
        assert canonical_folder.is_dir()

        with pytest.raises(_ItemAlreadyExists):
            _call_prepare(str(canonical_folder), "Doom Again", mem_session)

    def test_reimport_same_file_via_dest_path_raises(self, tmp_path, mem_session, monkeypatch):
        """A loose file is moved into a canonical folder on first import;
        attempting to import the destination path again raises _ItemAlreadyExists."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        src_file = media_root / "doom.exe"
        src_file.write_bytes(b"fake exe")

        from backend.service.library.items import _ItemAlreadyExists

        _patch_settings(monkeypatch, media_root)
        row = _call_prepare(str(src_file), "Doom", mem_session)
        _commit_row(row, mem_session)

        # The file was moved to the canonical path; that path is now tracked.
        canonical_file = Path(row["media_path"])
        with pytest.raises(_ItemAlreadyExists):
            _call_prepare(str(canonical_file), "Doom Again", mem_session)
