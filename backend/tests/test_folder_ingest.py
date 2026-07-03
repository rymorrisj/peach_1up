"""Tests for folder-upload ingest decision tree.

Covers three functions introduced in the folder-upload / multi-disc feature:

- _pick_folder_launch_file (library route): single-disc pre-flight launch file
  selection including GDI-first priority.
- _detect_disc_files (library route): multi-disc detection and 422 guard for
  ambiguous mixed .cue/.gdi uploads.
- _create_multi_disc_collection (library service): DB creation of LibraryCollection +
  LibraryItem records for a multi-disc folder.

GDI divergence note: _EXECUTABLE_PRIORITY in profile_builder.py did NOT include
.gdi, so _prepare_item would store executable_path=None for Dreamcast folders
even though _pick_folder_launch_file correctly identified the .gdi file first.
The fix (prepending .gdi to _EXECUTABLE_PRIORITY) landed before these tests were
written, so all tests reflect the corrected behaviour.
"""

from pathlib import Path

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# _pick_folder_launch_file
# ---------------------------------------------------------------------------

class TestPickFolderLaunchFile:
    def _call(self, *names: str, base: Path | None = None) -> Path:
        from backend.service.library.folder_ingest import pick_folder_launch_file
        if base is None:
            paths = [Path(n) for n in names]
        else:
            paths = [base / n for n in names]
        return pick_folder_launch_file(paths)

    def test_gdi_returned_first_dreamcast_era(self, tmp_path):
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
        from backend.service.library.folder_ingest import pick_folder_launch_file
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
        from backend.service.library.folder_ingest import detect_disc_files
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
# _create_multi_disc_collection — DB integration
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_session():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, Session, create_engine
    import backend.models  # noqa: F401 — registers all ORM tables

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


class TestCreateMultiDiscSet:
    @pytest.fixture(autouse=True)
    def _patch_detect(self, monkeypatch):
        import backend.service.utils.smart_media_detector as smd
        monkeypatch.setattr(smd, "detect", lambda path: _FakeScanResult())

    @pytest.fixture(autouse=True)
    def _patch_era_defaults(self, monkeypatch):
        import backend.service.utils.era_defaults as ead
        # Return (None, None) to skip platform/profile lookup — not under test here.
        monkeypatch.setattr(ead, "defaults_for_era", lambda era: (None, None))

    def _make_disc_files(self, tmp_path: Path, names: list[str]) -> list[Path]:
        files = []
        for name in names:
            p = tmp_path / name
            p.write_bytes(b"\x00" * 16)
            files.append(p)
        return files

    def test_two_disc_set_creates_one_set_and_two_items(self, tmp_path, mem_session):
        from backend.service.library.items import _create_multi_disc_collection
        from backend.models.library import LibraryCollection, LibraryItem

        disc_files = self._make_disc_files(tmp_path, ["disc1.gdi", "disc2.gdi"])
        _create_multi_disc_collection(disc_files, "Sonic Adventure", mem_session)

        sets = mem_session.query(LibraryCollection).all()
        assert len(sets) == 1
        assert sets[0].title == "Sonic Adventure"

        items = mem_session.query(LibraryItem).filter(LibraryItem.library_collection_id == sets[0].id).all()
        assert len(items) == 2

    def test_launch_disk_id_points_to_first_disc(self, tmp_path, mem_session):
        from backend.service.library.items import _create_multi_disc_collection
        from backend.models.library import LibraryCollection, LibraryItem

        disc_files = self._make_disc_files(tmp_path, ["disc1.gdi", "disc2.gdi"])
        library_set = _create_multi_disc_collection(disc_files, "Test Game", mem_session)

        items = (
            mem_session.query(LibraryItem)
            .filter(LibraryItem.library_collection_id == library_set.id)
            .order_by(LibraryItem.disc_number)
            .all()
        )
        assert library_set.launch_disk_id == items[0].id

    def test_each_item_has_gdi_as_executable_path(self, tmp_path, mem_session):
        from backend.service.library.items import _create_multi_disc_collection
        from backend.models.library import LibraryItem

        disc_files = self._make_disc_files(tmp_path, ["disc1.gdi", "disc2.gdi"])
        library_set = _create_multi_disc_collection(disc_files, "Dreamcast Game", mem_session)

        items = (
            mem_session.query(LibraryItem)
            .filter(LibraryItem.library_collection_id == library_set.id)
            .order_by(LibraryItem.disc_number)
            .all()
        )
        for idx, item in enumerate(items):
            assert item.executable_path == str(disc_files[idx])
            assert item.media_path == str(disc_files[idx])
            assert Path(item.executable_path).suffix.lower() == ".gdi"

    def test_disc_numbers_are_sequential_from_one(self, tmp_path, mem_session):
        from backend.service.library.items import _create_multi_disc_collection
        from backend.models.library import LibraryItem

        disc_files = self._make_disc_files(tmp_path, ["disc1.cue", "disc2.cue", "disc3.cue"])
        library_set = _create_multi_disc_collection(disc_files, "Triple-Disc Game", mem_session)

        items = (
            mem_session.query(LibraryItem)
            .filter(LibraryItem.library_collection_id == library_set.id)
            .order_by(LibraryItem.disc_number)
            .all()
        )
        assert [i.disc_number for i in items] == [1, 2, 3]

    def test_era_from_detector_stored_on_set(self, tmp_path, mem_session):
        from backend.service.library.items import _create_multi_disc_collection
        from backend.models.library import LibraryCollection

        disc_files = self._make_disc_files(tmp_path, ["d1.gdi", "d2.gdi"])
        library_set = _create_multi_disc_collection(disc_files, "Era Test", mem_session)

        stored = mem_session.get(LibraryCollection, library_set.id)
        assert stored.era == "dreamcast"
