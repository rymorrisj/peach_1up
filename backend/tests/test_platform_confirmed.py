"""Tests for how ingest sets GameItemBundle.platform_confirmed
(_platform_confirmed_at_ingest and its wiring into _finalize_row_fields, plus the
PS3 folder scan in _detect_directory_source, all in
backend/service/games/items.py).

Rule: confirmed at ingest when the user chose the platform (override path), or when
the winning scan is authoritative (MediaDetection.authoritative, or
the PS3 folder structure). Non-authoritative detection and an unknown platform stay
unconfirmed.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.service.games import items as svc
from formatscout.result import Method

from backend.tests.scan_factory import make_detection


def _scan(platform, authoritative=False, method=Method.NONE):
    return make_detection(platform, authoritative=authoritative, method=method)


def _authoritative_scan(platform="ps1"):
    return _scan(platform, authoritative=True, method=Method.HASH_SHA1)


def _title_match_scan(platform="ps1"):
    return make_detection(platform, confidence=0.4, method=Method.TITLE_MATCH)


@pytest.fixture
def mem_session():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, Session, create_engine
    import backend.models  # noqa: F401, registers all table models

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestPlatformConfirmedAtIngest:
    def test_authoritative_scan_is_confirmed(self):
        assert svc._platform_confirmed_at_ingest(_authoritative_scan(), None) is True

    def test_non_authoritative_title_match_scan_is_not_confirmed(self):
        assert svc._platform_confirmed_at_ingest(_title_match_scan(), None) is False

    def test_unknown_platform_is_not_confirmed(self):
        assert svc._platform_confirmed_at_ingest(_scan(None), None) is False

    def test_user_override_is_confirmed_over_a_non_authoritative_scan(self):
        assert svc._platform_confirmed_at_ingest(_title_match_scan(), "ps2") is True

    def test_user_override_is_confirmed_over_a_scan_that_found_nothing(self):
        assert svc._platform_confirmed_at_ingest(_scan(None), "dos") is True

    def test_user_override_of_unknown_is_not_confirmed(self):
        assert svc._platform_confirmed_at_ingest(_scan(None), "unknown") is False


class TestFinalizeRowFieldsSetsPlatformConfirmed:
    @pytest.fixture(autouse=True)
    def _isolate_file_work(self, monkeypatch):
        import formatscout

        monkeypatch.setattr(
            formatscout,
            "classify",
            lambda target, title, platform: SimpleNamespace(
                status="unchecked", similarity=None, computed_sha1=None,
            ),
        )
        monkeypatch.setattr("backend.service.utils.rating_detect.detect_rating", lambda path: None)

    def _fields(self, scan, db, **kwargs):
        collection_fields, _ = svc._finalize_row_fields(
            "Ico", [Path("/library/games/ps1/ico/ico.chd")], scan, db, **kwargs,
        )
        return collection_fields

    def test_authoritative_detection_persists_confirmed(self, mem_session):
        fields = self._fields(_authoritative_scan(), mem_session)

        assert fields["platform"] == "ps1"
        assert fields["platform_confirmed"] is True

    def test_weak_detection_persists_unconfirmed(self, mem_session):
        fields = self._fields(_title_match_scan(), mem_session)

        assert fields["platform"] == "ps1"
        assert fields["platform_confirmed"] is False

    def test_user_override_persists_confirmed(self, mem_session):
        from backend.constants import PLATFORM_SELECTED_BY_USER_REASON

        collection_fields, leaves = svc._finalize_row_fields(
            "Ico",
            [Path("/library/games/ps2/ico/ico.iso")],
            _title_match_scan(),
            mem_session,
            user_override_platform="ps2",
        )

        assert collection_fields["platform"] == "ps2"
        assert collection_fields["platform_confirmed"] is True
        assert leaves[0]["detection_reason"] == PLATFORM_SELECTED_BY_USER_REASON

    def test_nothing_detected_persists_unknown_and_unconfirmed(self, mem_session):
        fields = self._fields(_scan(None), mem_session)

        assert fields["platform"] == "unknown"
        assert fields["platform_confirmed"] is False

    def test_multi_disc_set_uses_the_one_scan_for_every_disc(self, mem_session):
        collection_fields, leaves = svc._finalize_row_fields(
            "Final Fantasy VII",
            [Path("/library/games/ps1/ff7/d1.chd"), Path("/library/games/ps1/ff7/d2.chd")],
            _authoritative_scan(),
            mem_session,
        )

        assert collection_fields["platform_confirmed"] is True
        assert len(leaves) == 2

    def test_platform_confirmed_is_a_persisted_collection_column(self):
        assert "platform_confirmed" in svc._COLLECTION_COLUMNS


class TestPs3FolderScanIsAuthoritative:
    def test_ps3_folder_result_is_confirmed_at_ingest(self, tmp_path, monkeypatch):
        import logging

        folder = tmp_path / "ps3game"
        folder.mkdir()
        monkeypatch.setattr(svc, "_pick_folder_executable", lambda f: None)
        monkeypatch.setattr(svc, "best_detect_path", lambda f, e: f)
        monkeypatch.setattr(
            "backend.service.utils.detection.resolve_ps3_target",
            lambda f: SimpleNamespace(platform="ps3", requires_install=True),
        )

        def _no_single_media_file(directory, platform):
            raise ValueError("no single media file, the folder is the launch target")

        monkeypatch.setattr(svc, "resolve_media_file_from_directory", _no_single_media_file)

        detection = svc._detect_directory_source(
            folder, user_override_platform=None, platform_hint=None, log=logging.getLogger(__name__),
        )

        assert detection.scan.platform == "ps3"
        assert detection.scan.authoritative is True
        assert svc._platform_confirmed_at_ingest(detection.scan, None) is True
