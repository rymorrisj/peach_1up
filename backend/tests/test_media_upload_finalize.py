"""MED-12: the chunked Media upload finalize
(backend/service/uploads/software_media.py) creates the MediaItem row and
its collection-of-one bundle, and removes the uploaded file when row
creation fails."""

import pytest


@pytest.fixture
def db():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine
    import backend.models  # noqa: F401, registers all table models

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _reassembled(tmp_path, name: str, body: bytes = b"ID3data", title: str = "Doom OST", media_kind=None):
    from backend.service.uploads.core import ReassembledUpload

    dest_dir = tmp_path / "media" / "doom-ost"
    dest_dir.mkdir(parents=True)
    path = dest_dir / name
    path.write_bytes(body)
    return ReassembledUpload(
        kind="file", title=title, dest_dir=dest_dir, paths=[path], total_bytes=len(body), media_kind=media_kind
    )


class TestFinalizeCreatesRow:
    def test_item_and_bundle_rows_are_created(self, db, tmp_path):
        from backend.models.media import MediaItem, MediaItemBundle
        from backend.service.uploads.software_media import finalize_reassembled

        reasm = _reassembled(tmp_path, "theme.mp3")

        result = finalize_reassembled(reasm, db)

        item = db.get(MediaItem, result["media_item_id"])
        bundle = db.get(MediaItemBundle, result["id"])
        assert item is not None and bundle is not None
        assert item.media_item_bundle_id == bundle.id
        assert item.file_path == str(reasm.paths[0])
        assert item.media_kind == "audio" and bundle.media_kind == "audio"
        assert item.file_size_bytes == reasm.total_bytes
        assert item.asset_type is None and item.source_url is None
        assert item.slug == "doom-ost"
        assert bundle.slug == "doom-ost-collection"
        assert result["result_type"] == "media_upload"
        assert reasm.paths[0].exists()

    @pytest.mark.parametrize("name,kind", [("scan.png", "image"), ("manual.pdf", "text"), ("clip.mkv", "video")])
    def test_kind_comes_from_the_extension(self, db, tmp_path, name, kind):
        from backend.models.media import MediaItem
        from backend.service.uploads.software_media import finalize_reassembled

        result = finalize_reassembled(_reassembled(tmp_path, name), db)

        assert db.get(MediaItem, result["media_item_id"]).media_kind == kind


class TestFinalizeRollsBack:
    def test_row_failure_removes_the_file_and_leaves_no_rows(self, db, tmp_path, monkeypatch):
        import backend.models.media as media_models
        from backend.models.media import MediaItem, MediaItemBundle
        from backend.service.uploads.software_media import finalize_reassembled

        reasm = _reassembled(tmp_path, "theme.mp3")

        def _boom(*args, **kwargs):
            raise RuntimeError("slug lookup failed")

        monkeypatch.setattr(media_models, "unique_media_slug", _boom)

        with pytest.raises(RuntimeError):
            finalize_reassembled(reasm, db)

        assert not reasm.dest_dir.exists()
        assert db.query(MediaItem).count() == 0
        assert db.query(MediaItemBundle).count() == 0

    def test_commit_failure_removes_the_file_and_leaves_no_rows(self, db, tmp_path, monkeypatch):
        from backend.models.media import MediaItem, MediaItemBundle
        from backend.service.uploads.software_media import finalize_reassembled

        reasm = _reassembled(tmp_path, "theme.mp3")
        real_commit = db.commit

        def _fail_commit():
            raise RuntimeError("disk full")

        monkeypatch.setattr(db, "commit", _fail_commit)
        with pytest.raises(RuntimeError):
            finalize_reassembled(reasm, db)
        monkeypatch.setattr(db, "commit", real_commit)

        assert not reasm.dest_dir.exists()
        assert db.query(MediaItem).count() == 0
        assert db.query(MediaItemBundle).count() == 0

    def test_more_than_one_file_is_refused_and_removed(self, db, tmp_path):
        from backend.models.media import MediaItem
        from backend.service.uploads.software_media import finalize_reassembled

        reasm = _reassembled(tmp_path, "a.mp3")
        extra = reasm.dest_dir / "b.mp3"
        extra.write_bytes(b"ID3")
        reasm.paths.append(extra)

        with pytest.raises(ValueError, match="exactly one file"):
            finalize_reassembled(reasm, db)

        assert not reasm.dest_dir.exists()
        assert db.query(MediaItem).count() == 0

    @pytest.mark.parametrize("media_kind", ["image", "audio", "video", "text"])
    def test_archive_takes_the_supplied_kind(self, db, tmp_path, media_kind):
        from backend.models.media import MediaItem, MediaItemBundle
        from backend.service.uploads.software_media import finalize_reassembled

        reasm = _reassembled(tmp_path, "pack.zip", body=b"PK\x03\x04", media_kind=media_kind)

        result = finalize_reassembled(reasm, db)

        assert db.get(MediaItem, result["media_item_id"]).media_kind == media_kind
        assert db.get(MediaItemBundle, result["id"]).media_kind == media_kind
        assert reasm.paths[0].exists()

    def test_supplied_kind_that_does_not_fit_the_file_is_refused_and_removed(self, db, tmp_path):
        from backend.models.media import MediaItem
        from backend.service.uploads.software_media import finalize_reassembled

        reasm = _reassembled(tmp_path, "theme.mp3", media_kind="image")

        with pytest.raises(ValueError, match="not allowed"):
            finalize_reassembled(reasm, db)

        assert not reasm.dest_dir.exists()
        assert db.query(MediaItem).count() == 0

    def test_archive_is_refused_and_removed(self, db, tmp_path):
        from backend.models.media import MediaItem
        from backend.service.uploads.software_media import finalize_reassembled

        reasm = _reassembled(tmp_path, "pack.zip", body=b"PK\x03\x04")

        with pytest.raises(ValueError, match="media kind"):
            finalize_reassembled(reasm, db)

        assert not reasm.dest_dir.exists()
        assert db.query(MediaItem).count() == 0


class TestFinalizeBackground:
    def test_failure_marks_the_job_failed(self, db, tmp_path, monkeypatch):
        from backend.core import jobs
        from backend.service.uploads import core as cu
        from backend.service.uploads import software_media

        reasm = _reassembled(tmp_path, "pack.zip", body=b"PK\x03\x04")
        monkeypatch.setattr(cu, "reassemble", lambda upload_id, root, job_id=None: reasm)
        monkeypatch.setattr(cu, "abort", lambda upload_id: None)
        import backend.core.database as database_mod
        monkeypatch.setattr(database_mod, "get_engine", lambda: db.get_bind())

        job_id = jobs.create("upload", message="Uploading")
        software_media.finalize_background("u1", str(tmp_path / "media"), job_id)

        job = jobs.get(job_id)
        assert job["status"] == "error"
        assert "media kind" in job["error"]
        assert not reasm.dest_dir.exists()
