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
        from backend.models.software import SoftwareCollection, SoftwareItem

        disc_files = self._make_disc_files(tmp_path, ["disc1.gdi", "disc2.gdi"])
        _create_multi_disc_collection(disc_files, "Sonic Adventure", mem_session)

        sets = mem_session.query(SoftwareCollection).all()
        assert len(sets) == 1
        assert sets[0].title == "Sonic Adventure"

        items = mem_session.query(SoftwareItem).filter(SoftwareItem.software_collection_id == sets[0].id).all()
        assert len(items) == 2

    def test_launch_disk_id_points_to_first_disc(self, tmp_path, mem_session):
        from backend.service.library.items import _create_multi_disc_collection
        from backend.models.software import SoftwareCollection, SoftwareItem

        disc_files = self._make_disc_files(tmp_path, ["disc1.gdi", "disc2.gdi"])
        library_set = _create_multi_disc_collection(disc_files, "Test Game", mem_session)

        items = (
            mem_session.query(SoftwareItem)
            .filter(SoftwareItem.software_collection_id == library_set.id)
            .order_by(SoftwareItem.disc_number)
            .all()
        )
        assert library_set.launch_disk_id == items[0].id

    def test_each_item_has_gdi_as_executable_path(self, tmp_path, mem_session):
        from backend.service.library.items import _create_multi_disc_collection
        from backend.models.software import SoftwareItem

        disc_files = self._make_disc_files(tmp_path, ["disc1.gdi", "disc2.gdi"])
        library_set = _create_multi_disc_collection(disc_files, "Dreamcast Game", mem_session)

        items = (
            mem_session.query(SoftwareItem)
            .filter(SoftwareItem.software_collection_id == library_set.id)
            .order_by(SoftwareItem.disc_number)
            .all()
        )
        for idx, item in enumerate(items):
            assert item.executable_path == str(disc_files[idx])
            assert item.file_path == str(disc_files[idx])
            assert Path(item.executable_path).suffix.lower() == ".gdi"

    def test_disc_numbers_are_sequential_from_one(self, tmp_path, mem_session):
        from backend.service.library.items import _create_multi_disc_collection
        from backend.models.software import SoftwareItem

        disc_files = self._make_disc_files(tmp_path, ["disc1.cue", "disc2.cue", "disc3.cue"])
        library_set = _create_multi_disc_collection(disc_files, "Triple-Disc Game", mem_session)

        items = (
            mem_session.query(SoftwareItem)
            .filter(SoftwareItem.software_collection_id == library_set.id)
            .order_by(SoftwareItem.disc_number)
            .all()
        )
        assert [i.disc_number for i in items] == [1, 2, 3]

    def test_era_from_detector_stored_on_set(self, tmp_path, mem_session):
        from backend.service.library.items import _create_multi_disc_collection
        from backend.models.software import SoftwareCollection

        disc_files = self._make_disc_files(tmp_path, ["d1.gdi", "d2.gdi"])
        library_set = _create_multi_disc_collection(disc_files, "Era Test", mem_session)

        stored = mem_session.get(SoftwareCollection, library_set.id)
        assert stored.era == "dreamcast"

    def test_content_rating_detected_from_disc_one_filename(self, tmp_path, mem_session):
        """detect_rating is called with disc_files[0] only — a bracketed rating
        tag on disc 1's filename must land on the SoftwareCollection, matching
        rating_detect's strict (bracket-guarded) filename-stem fallback."""
        from backend.service.library.items import _create_multi_disc_collection
        from backend.models.software import SoftwareCollection

        disc_files = self._make_disc_files(tmp_path, ["disc1 [M].gdi", "disc2.gdi"])
        library_set = _create_multi_disc_collection(disc_files, "Rated Game", mem_session)

        stored = mem_session.get(SoftwareCollection, library_set.id)
        assert stored.content_rating == "M"

    def test_cover_art_found_next_to_disc_one_lands_on_first_disc_only(self, tmp_path, mem_session):
        """_find_cover is called on disc_files[0]'s parent — a cover image found
        there must land on disc 1's item only, never on later discs."""
        from backend.service.library.items import _create_multi_disc_collection
        from backend.models.software import SoftwareItem

        (tmp_path / "cover.jpg").write_bytes(b"\xff\xd8\xff")
        disc_files = self._make_disc_files(tmp_path, ["disc1.gdi", "disc2.gdi"])
        library_set = _create_multi_disc_collection(disc_files, "Cover Game", mem_session)

        items = (
            mem_session.query(SoftwareItem)
            .filter(SoftwareItem.software_collection_id == library_set.id)
            .order_by(SoftwareItem.disc_number)
            .all()
        )
        assert items[0].cover_art_path == str(tmp_path / "cover.jpg")
        assert items[1].cover_art_path is None


# ---------------------------------------------------------------------------
# dedup_disc_anchor — content-hash dedup for multi-disc disc-1 anchors
# ---------------------------------------------------------------------------

class TestDedupDiscAnchor:
    @pytest.fixture(autouse=True)
    def _patch_detect(self, monkeypatch):
        import backend.service.utils.smart_media_detector as smd
        monkeypatch.setattr(smd, "detect", lambda path: _FakeScanResult())

    @pytest.fixture(autouse=True)
    def _patch_era_defaults(self, monkeypatch):
        import backend.service.utils.era_defaults as ead
        monkeypatch.setattr(ead, "defaults_for_era", lambda era: (None, None))

    def test_repoints_to_existing_orphaned_duplicate(self, tmp_path, mem_session):
        """A byte-identical file already on disk but not referenced by any live
        SoftwareItem (an orphan, e.g. left behind after its item was removed) is
        reused: the anchor is repointed at it and the newly-uploaded copy is
        deleted rather than kept as a redundant second copy."""
        from backend.service.library.folder_ingest import dedup_disc_anchor
        from backend.service.library.items import _create_multi_disc_collection
        from backend.models.software import SoftwareItem

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
        new_disc2 = incoming_dir / "disc2.gdi"
        new_disc2.write_bytes(b"disc2 bytes, unrelated content")

        disc_files = [new_disc1, new_disc2]
        disc_files[0] = dedup_disc_anchor(media_root, disc_files[0], mem_session)

        assert disc_files[0] == orphan_disc1.resolve()
        assert not new_disc1.exists()  # redundant upload copy removed

        collection = _create_multi_disc_collection(disc_files, "Dedup Orphan Game", mem_session)
        leaf1 = (
            mem_session.query(SoftwareItem)
            .filter(SoftwareItem.software_collection_id == collection.id, SoftwareItem.disc_number == 1)
            .first()
        )
        assert leaf1.file_path == str(orphan_disc1.resolve())

    def test_raises_item_already_exists_when_duplicate_is_still_tracked(self, tmp_path, mem_session):
        """A byte-identical file that is still a live SoftwareItem.file_path must
        not be silently repointed — that would create a second tracked row
        sharing one file_path with an existing collection. dedup_disc_anchor
        raises _ItemAlreadyExists instead, same as the file-kind upload path."""
        from backend.service.library.folder_ingest import dedup_disc_anchor
        from backend.service.library.items import _ItemAlreadyExists
        from backend.models.software import SoftwareCollection, SoftwareItem

        media_root = tmp_path
        content = b"identical disc1 bytes still tracked by a live item"

        tracked_dir = media_root / "tracked"
        tracked_dir.mkdir()
        tracked_disc1 = tracked_dir / "disc1.gdi"
        tracked_disc1.write_bytes(content)

        existing_collection = SoftwareCollection(title="Existing Game", era="dreamcast", slug="existing-game")
        mem_session.add(existing_collection)
        mem_session.flush()
        existing_leaf = SoftwareItem(
            software_collection_id=existing_collection.id,
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
