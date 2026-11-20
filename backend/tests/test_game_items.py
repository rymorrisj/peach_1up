"""Tests for _prepare_item in backend/service/games/items.py:

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
        return self._media_path if key == "SOFTWARE_PATH" else default

    def get_env_var(self, key):
        return self._media_path if key == "SOFTWARE_PATH" else ""


@pytest.fixture
def mem_session():
    from sqlmodel import SQLModel, Session, create_engine
    from sqlalchemy.pool import StaticPool
    import backend.models  # noqa: F401, registers all table models

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


def _call_prepare(path: str, title: str, session) -> tuple[dict, dict]:
    from backend.service.games.items import _prepare_item
    collection_fields, leaf_rows = _prepare_item(path, title, session)
    return collection_fields, leaf_rows[0]


def _commit_row(collection_fields: dict, leaf_fields: dict, session):
    # Persist a collection-of-one (parent + leaf) so dedup queries against the
    # leaf's folder_path/media_path find it on re-import.
    from backend.service.games.items import _persist_multi_disc_collection
    collection = _persist_multi_disc_collection(collection_fields, [leaf_fields], session)
    session.commit()
    return collection


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
        # SOFTWARE_PATH is media_root; games_root_str-derived paths resolve to
        # library_domain_root("games") = media_root/games, see path_utils.py.
        games_root = media_root / "games"
        games_root.mkdir()
        src_folder = games_root / "My Game (1993)"
        src_folder.mkdir()
        src_file = src_folder / "doom.exe"
        src_file.write_bytes(b"fake exe")

        _patch_settings(monkeypatch, media_root)
        collection_fields, leaf_fields = _call_prepare(str(src_file), "Doom", mem_session)

        canonical = games_root / "doom"
        assert canonical.is_dir(), "Canonical folder must exist after rename"
        assert not src_folder.exists(), "Original folder must be gone after rename"
        assert (canonical / "doom.exe").is_file()
        assert leaf_fields["folder_path"] == str(canonical)
        assert leaf_fields["file_path"] == str(canonical / "doom.exe")

    def test_already_canonically_named_folder_no_rename(self, tmp_path, mem_session, monkeypatch):
        """File in games_root/doom/doom.exe, folder name already matches stem,
        no rename and no move should occur."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        games_root = media_root / "games"
        games_root.mkdir()
        src_folder = games_root / "doom"
        src_folder.mkdir()
        src_file = src_folder / "doom.exe"
        src_file.write_bytes(b"fake exe")

        _patch_settings(monkeypatch, media_root)
        collection_fields, leaf_fields = _call_prepare(str(src_file), "Doom", mem_session)

        assert src_folder.is_dir(), "Correctly-named folder must still be there"
        assert src_file.is_file(), "File must not have moved"
        assert leaf_fields["folder_path"] == str(src_folder)
        assert leaf_fields["file_path"] == str(src_file)

    def test_canonical_target_exists_falls_back_to_move(self, tmp_path, mem_session, monkeypatch):
        """If games_root/doom/ already exists on disk, the rename branch is
        skipped and the file is moved there instead."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        games_root = media_root / "games"
        games_root.mkdir()
        existing_canonical = games_root / "doom"
        existing_canonical.mkdir()
        src_folder = games_root / "My Doom Game"
        src_folder.mkdir()
        src_file = src_folder / "doom.exe"
        src_file.write_bytes(b"fake exe")

        _patch_settings(monkeypatch, media_root)
        collection_fields, leaf_fields = _call_prepare(str(src_file), "Doom", mem_session)

        assert (existing_canonical / "doom.exe").is_file()
        assert leaf_fields["folder_path"] == str(existing_canonical)
        assert leaf_fields["file_path"] == str(existing_canonical / "doom.exe")

    def test_loose_file_at_games_root_still_creates_canonical_folder(self, tmp_path, mem_session, monkeypatch):
        """A file placed directly inside games_root (loose, no parent subfolder)
        is not eligible for rename, a new folder is created and the file moved."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        games_root = media_root / "games"
        games_root.mkdir()
        src_file = games_root / "doom.exe"
        src_file.write_bytes(b"fake exe")

        _patch_settings(monkeypatch, media_root)
        collection_fields, leaf_fields = _call_prepare(str(src_file), "Doom", mem_session)

        canonical = games_root / "doom"
        assert canonical.is_dir()
        assert (canonical / "doom.exe").is_file()
        assert not src_file.exists(), "Loose file must have been moved into the canonical folder"
        assert leaf_fields["folder_path"] == str(canonical)

    def test_file_in_deeply_nested_subfolder_not_renamed(self, tmp_path, mem_session, monkeypatch):
        """A file two levels deep (games_root/a/b/file.exe) does not trigger the
        rename path, only direct subfolders of games_root qualify."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        games_root = media_root / "games"
        games_root.mkdir()
        deep_folder = games_root / "outer" / "inner"
        deep_folder.mkdir(parents=True)
        src_file = deep_folder / "doom.exe"
        src_file.write_bytes(b"fake exe")

        _patch_settings(monkeypatch, media_root)
        # _prepare_item will raise because outer/ is inside games_root but
        # inner/ is two levels deep, falls through to create+move; the
        # canonical dest_folder is games_root/doom which doesn't conflict.
        _call_prepare(str(src_file), "Doom", mem_session)

        canonical = games_root / "doom"
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
        games_root = media_root / "games"
        games_root.mkdir()
        folder = games_root / "doom"
        folder.mkdir()
        (folder / "doom.exe").write_bytes(b"fake exe")

        from backend.service.games.items import _ItemAlreadyExists

        _patch_settings(monkeypatch, media_root)
        collection_fields, leaf_fields = _call_prepare(str(folder), "Doom", mem_session)
        _commit_row(collection_fields, leaf_fields, mem_session)

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

        from backend.service.games.items import _ItemAlreadyExists

        _patch_settings(monkeypatch, media_root)
        collection_fields, leaf_fields = _call_prepare(str(src_file), "Doom", mem_session)
        _commit_row(collection_fields, leaf_fields, mem_session)

        canonical_file = Path(leaf_fields["file_path"])
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

        from backend.service.games.items import _ItemAlreadyExists

        _patch_settings(monkeypatch, media_root)
        collection_fields, leaf_fields = _call_prepare(str(src_folder / "doom.exe"), "Doom", mem_session)
        _commit_row(collection_fields, leaf_fields, mem_session)

        canonical_folder = Path(leaf_fields["folder_path"])
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

        from backend.service.games.items import _ItemAlreadyExists

        _patch_settings(monkeypatch, media_root)
        collection_fields, leaf_fields = _call_prepare(str(src_file), "Doom", mem_session)
        _commit_row(collection_fields, leaf_fields, mem_session)

        # The file was moved to the canonical path; that path is now tracked.
        canonical_file = Path(leaf_fields["file_path"])
        with pytest.raises(_ItemAlreadyExists):
            _call_prepare(str(canonical_file), "Doom Again", mem_session)


# ---------------------------------------------------------------------------
# Library folders already on disk: adopt in place, never stage or overwrite
# ---------------------------------------------------------------------------


def _games_root(tmp_path: Path) -> tuple[Path, Path]:
    media_root = tmp_path / "media"
    games_root = media_root / "games"
    games_root.mkdir(parents=True)
    return media_root, games_root


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir()) if p.is_file()}


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available in this environment")


class TestAdoptLibraryFolderInPlace:
    def test_library_file_with_cover_neighbour_imports_in_place(self, tmp_path, mem_session, monkeypatch):
        """(a) games/doom/{doom.exe,cover.png,doom.img}: the neighbours must not
        block the import, and nothing may be moved, copied or created."""
        media_root, games_root = _games_root(tmp_path)
        folder = games_root / "doom"
        folder.mkdir()
        (folder / "doom.exe").write_bytes(b"fake exe")
        (folder / "cover.png").write_bytes(b"png")
        (folder / "doom.img").write_bytes(b"img")
        before = _snapshot(folder)

        _patch_settings(monkeypatch, media_root)
        _collection_fields, leaf_fields = _call_prepare(str(folder / "doom.exe"), "Doom", mem_session)

        assert _snapshot(folder) == before
        assert [p.name for p in games_root.iterdir()] == ["doom"]
        assert leaf_fields["folder_path"] == str(folder)
        assert leaf_fields["file_path"] == str(folder / "doom.exe")
        assert leaf_fields["cover_art_path"] == str(folder / "cover.png")

    def test_upload_matching_leftover_adopts_it_and_drops_staged_copy(self, tmp_path, mem_session, monkeypatch):
        """(b) Same bytes as a leftover folder: find_existing_duplicate (already
        hash-backed) hands the leftover path to the ingest, the staged dir is
        removed, and the in-place adopt leaves no -2 folder behind."""
        from types import SimpleNamespace

        from backend.service.games import items as lib_svc
        from backend.service.uploads import core as cu
        from backend.service.uploads.software_games import finalize_reassembled
        from backend.service.utils import media_dup_index

        media_dup_index._index.clear()
        media_dup_index._built_for = None
        media_root, games_root = _games_root(tmp_path)
        leftover = games_root / "doom"
        leftover.mkdir()
        (leftover / "doom.exe").write_bytes(b"same bytes")
        (leftover / "cover.png").write_bytes(b"png")
        staged = games_root / "doom-2"
        staged.mkdir()
        (staged / "doom.exe").write_bytes(b"same bytes")

        seen: dict = {}

        def _fake_ingest(path, title, db, **_kw):
            seen["path"] = Path(path)
            return SimpleNamespace(id=1, title=title)

        monkeypatch.setattr(lib_svc, "_ingest_media_entry", _fake_ingest)
        reasm = cu.ReassembledUpload(
            kind="file", title="Doom", dest_dir=staged, paths=[staged / "doom.exe"], total_bytes=len(b"same bytes"),
        )
        result = finalize_reassembled(reasm, games_root, mem_session)

        assert result["reused_existing_media"] is True
        assert seen["path"].resolve() == (leftover / "doom.exe").resolve()
        assert not staged.exists()

        monkeypatch.undo()
        _patch_settings(monkeypatch, media_root)
        _cf, leaf_fields = _call_prepare(str(seen["path"]), "Doom", mem_session)
        assert leaf_fields["folder_path"] == str(leftover)
        assert sorted(p.name for p in games_root.iterdir()) == ["doom"]

    def test_different_content_same_slug_gets_suffixed_folder(self, tmp_path, mem_session, monkeypatch):
        """(c) Untracked games/doom holds other bytes: the upload goes to doom-2
        and the original folder is byte-for-byte untouched."""
        media_root, games_root = _games_root(tmp_path)
        folder = games_root / "doom"
        folder.mkdir()
        (folder / "doom.exe").write_bytes(b"original")
        (folder / "cover.png").write_bytes(b"png")
        before = _snapshot(folder)
        incoming = media_root / "incoming" / "doom.exe"
        incoming.parent.mkdir()
        incoming.write_bytes(b"different content")

        _patch_settings(monkeypatch, media_root)
        _cf, leaf_fields = _call_prepare(str(incoming), "Doom", mem_session)

        assert _snapshot(folder) == before
        assert leaf_fields["folder_path"] == str(games_root / "doom-2")
        assert (games_root / "doom-2" / "doom.exe").read_bytes() == b"different content"
        assert not incoming.exists()

    def test_size_only_match_does_not_adopt(self, tmp_path, mem_session, monkeypatch):
        """(g) Equal size, different bytes: the old size check would have reused
        the existing file. It must now be treated as different content."""
        media_root, games_root = _games_root(tmp_path)
        folder = games_root / "doom"
        folder.mkdir()
        (folder / "doom.exe").write_bytes(b"AAAA")
        incoming = media_root / "incoming" / "doom.exe"
        incoming.parent.mkdir()
        incoming.write_bytes(b"BBBB")

        _patch_settings(monkeypatch, media_root)
        _cf, leaf_fields = _call_prepare(str(incoming), "Doom", mem_session)

        assert (folder / "doom.exe").read_bytes() == b"AAAA"
        assert leaf_fields["folder_path"] == str(games_root / "doom-2")
        assert leaf_fields["file_path"] == str(games_root / "doom-2" / "doom.exe")

    def test_empty_leftover_folder_is_reused(self, tmp_path, mem_session, monkeypatch):
        """An empty untracked directory holds nothing to overwrite."""
        media_root, games_root = _games_root(tmp_path)
        (games_root / "doom").mkdir()
        incoming = media_root / "incoming" / "doom.exe"
        incoming.parent.mkdir()
        incoming.write_bytes(b"x")

        _patch_settings(monkeypatch, media_root)
        _cf, leaf_fields = _call_prepare(str(incoming), "Doom", mem_session)

        assert leaf_fields["folder_path"] == str(games_root / "doom")

    def test_mkdir_is_undone_when_created_by_the_call(self, tmp_path, mem_session, monkeypatch):
        from backend.service.games.items import _move_into_folder

        _media_root, games_root = _games_root(tmp_path)
        src = tmp_path / "doom.exe"
        src.write_bytes(b"x")
        folder = games_root / "doom"
        undo: list = []

        _move_into_folder(src, folder, folder / "doom.exe", undo)
        assert folder.is_dir() and not src.exists()
        for fn in reversed(undo):
            fn()
        assert src.is_file()
        assert not folder.exists()


class TestAdoptSafety:
    def test_symlinked_dest_folder_is_refused(self, tmp_path, mem_session, monkeypatch):
        """(d) games/doom is a symlink to a directory elsewhere."""
        from fastapi import HTTPException

        media_root, games_root = _games_root(tmp_path)
        outside = tmp_path / "outside"
        outside.mkdir()
        _symlink_or_skip(games_root / "doom", outside)
        incoming = media_root / "incoming" / "doom.exe"
        incoming.parent.mkdir()
        incoming.write_bytes(b"x")

        _patch_settings(monkeypatch, media_root)
        with pytest.raises(HTTPException) as exc_info:
            _call_prepare(str(incoming), "Doom", mem_session)

        assert exc_info.value.status_code == 409
        assert "symlink" in exc_info.value.detail
        assert list(outside.iterdir()) == []
        assert incoming.is_file()

    def test_symlinked_cover_is_refused(self, tmp_path, mem_session, monkeypatch):
        """(d) A cover.png symlink inside an adopted folder is never followed."""
        from fastapi import HTTPException

        media_root, games_root = _games_root(tmp_path)
        folder = games_root / "doom"
        folder.mkdir()
        (folder / "doom.exe").write_bytes(b"x")
        target = tmp_path / "elsewhere.png"
        target.write_bytes(b"png")
        _symlink_or_skip(folder / "cover.png", target)

        _patch_settings(monkeypatch, media_root)
        with pytest.raises(HTTPException) as exc_info:
            _call_prepare(str(folder / "doom.exe"), "Doom", mem_session)

        assert exc_info.value.status_code == 409
        assert "cover.png" in exc_info.value.detail

    def test_symlinked_file_helper_is_refused(self, tmp_path):
        """(d) _refuse_symlinks catches a symlinked file without resolving it."""
        from fastapi import HTTPException

        from backend.service.games.items import _refuse_symlinks

        real = tmp_path / "real.exe"
        real.write_bytes(b"x")
        link = tmp_path / "link.exe"
        _symlink_or_skip(link, real)

        with pytest.raises(HTTPException) as exc_info:
            _refuse_symlinks(real, link)
        assert exc_info.value.status_code == 409
        assert "link.exe" in exc_info.value.detail

    def test_db_tracked_folder_gives_409_naming_the_files(self, tmp_path, mem_session, monkeypatch):
        """(e) A second file inside an already-tracked folder is not adopted;
        the 409 names up to five entries and counts the rest."""
        from fastapi import HTTPException

        media_root, games_root = _games_root(tmp_path)
        folder = games_root / "doom"
        folder.mkdir()
        (folder / "doom.exe").write_bytes(b"first")

        _patch_settings(monkeypatch, media_root)
        collection_fields, leaf_fields = _call_prepare(str(folder / "doom.exe"), "Doom", mem_session)
        _commit_row(collection_fields, leaf_fields, mem_session)

        (folder / "doom.iso").write_bytes(b"second")
        for extra in ("a.txt", "b.txt", "c.txt", "d.txt"):
            (folder / extra).write_bytes(b"x")
        before = _snapshot(folder)

        with pytest.raises(HTTPException) as exc_info:
            _call_prepare(str(folder / "doom.iso"), "Doom ISO", mem_session)

        assert exc_info.value.status_code == 409
        detail = exc_info.value.detail
        assert "'a.txt'" in detail and "'doom.exe'" in detail
        assert "and 1 more" in detail
        assert _snapshot(folder) == before

    def test_dest_folder_outside_games_root_is_refused(self, tmp_path):
        """(f) Anything that does not resolve to a direct child of the games root."""
        from fastapi import HTTPException

        from backend.service.games.items import _require_direct_child

        _media_root, games_root = _games_root(tmp_path)
        for bad in (
            games_root / ".." / "evil",
            games_root / "a" / "b",
            games_root,
            tmp_path / "elsewhere",
        ):
            with pytest.raises(HTTPException) as exc_info:
                _require_direct_child(bad, games_root)
            assert exc_info.value.status_code == 400

        _require_direct_child(games_root / "doom", games_root)
