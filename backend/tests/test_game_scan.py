"""Tests for library scan helpers:

- scan_media_folders (service/utils/profile_builder.py), folder discovery,
  including .git exclusion (hidden directories are skipped via the
  ``not p.name.startswith(".")`` filter).
- generate_collection_slug (service/utils/slug_generator.py), slug collision
  suffixing used during scan import (_prepare_item).
"""

import pytest


class TestScanMediaFoldersGitExclusion:
    def test_git_subfolder_does_not_raise_and_is_skipped(self, tmp_path):
        from backend.service.utils.profile_builder import scan_media_folders

        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("dummy")

        game_dir = tmp_path / "Doom" / "Doom.iso"
        game_dir.parent.mkdir()
        game_dir.write_bytes(b"\x00")

        entries = scan_media_folders(tmp_path)

        names = [e.name for e in entries]
        assert ".git" not in names

    def test_returns_media_from_sibling_dirs_alongside_git_folder(self, tmp_path):
        from backend.service.utils.profile_builder import scan_media_folders

        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main")

        game_dir = tmp_path / "Doom"
        game_dir.mkdir()
        (game_dir / "Doom.iso").write_bytes(b"\x00")

        entries = scan_media_folders(tmp_path)

        names = [e.name for e in entries]
        assert "Doom" in names
        assert ".git" not in names


class TestSlugCollision:
    @pytest.fixture
    def mem_session(self):
        from sqlmodel import SQLModel, Session, create_engine
        import backend.models  # noqa: F401, registers all table models with SQLModel.metadata

        engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            yield session

    def test_slug_collision_appends_integer_suffix(self, mem_session):
        from backend.models.game import GameItemBundle
        from backend.service.utils.slug_generator import generate_collection_slug

        existing = GameItemBundle(title="Doom", era="dos", slug="doom")
        mem_session.add(existing)
        mem_session.commit()

        new_slug = generate_collection_slug("Doom", mem_session)

        assert new_slug == "doom-2"

    def test_collision_does_not_overwrite_existing_item(self, mem_session):
        from backend.models.game import GameItemBundle
        from backend.service.utils.slug_generator import generate_collection_slug

        existing = GameItemBundle(title="Doom", era="dos", slug="doom")
        mem_session.add(existing)
        mem_session.commit()
        mem_session.refresh(existing)
        existing_id = existing.id

        new_slug = generate_collection_slug("Doom", mem_session)
        new_item = GameItemBundle(title="Doom", era="dos", slug=new_slug)
        mem_session.add(new_item)
        mem_session.commit()

        unchanged = mem_session.get(GameItemBundle, existing_id)
        assert unchanged.slug == "doom"
        assert unchanged.title == "Doom"

        next_slug = generate_collection_slug("Doom", mem_session)
        assert next_slug == "doom-3"
