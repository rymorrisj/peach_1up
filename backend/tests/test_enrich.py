"""Tests for backend.service.games.enrich.enrich_entity: error branches for
not-found entities and unsupported operations.

_is_forbidden_redirect_host and download_remote_image (the download logic
enrich_entity's cover_art_url path calls into) live in
backend/service/utils/asset_fetch.py now and are tested in
backend/tests/test_asset_fetch.py, not here.

Run with:
    pytest backend/tests/test_enrich.py
"""
import pytest


@pytest.fixture
def mem_session():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, Session, create_engine
    import backend.models  # noqa: F401 — registers all table models

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestEnrichEntity:
    def test_library_collection_not_found_raises_404(self, mem_session):
        from fastapi import HTTPException
        from backend.service.games.enrich import enrich_entity

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity("game_item_bundle", 9999, title="New Title", db=mem_session)
        assert exc_info.value.status_code == 404

    def test_library_item_not_found_raises_404(self, mem_session):
        from fastapi import HTTPException
        from backend.service.games.enrich import enrich_entity

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity("game_item", 9999, cover_art_url="https://cdn.example.com/a.jpg", db=mem_session)
        assert exc_info.value.status_code == 404

    def test_library_collection_with_cover_art_url_raises_422(self, mem_session):
        """Collections don't support direct cover art — must be applied to individual discs."""
        from fastapi import HTTPException
        from backend.models.game import GameItemBundle
        from backend.service.games.enrich import enrich_entity

        c = GameItemBundle(title="My Set", era="ps1", slug="my-set")
        mem_session.add(c)
        mem_session.commit()
        mem_session.refresh(c)

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity(
                "game_item_bundle",
                c.id,
                cover_art_url="https://cdn.example.com/art.jpg",
                db=mem_session,
            )
        assert exc_info.value.status_code == 422
        assert "cover_art_url" in exc_info.value.detail

    def test_library_item_with_metadata_fields_raises_422(self, mem_session):
        """Disc-level leaves (library_item) do not accept metadata fields."""
        from fastapi import HTTPException
        from backend.models.game import GameItemBundle, GameItem
        from backend.service.games.enrich import enrich_entity

        c = GameItemBundle(title="My Set", era="ps1", slug="my-set")
        mem_session.add(c)
        mem_session.commit()
        mem_session.refresh(c)

        leaf = GameItem(game_item_bundle_id=c.id, file_path="/tmp/disc1.bin", disc_number=1)
        mem_session.add(leaf)
        mem_session.commit()
        mem_session.refresh(leaf)

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity(
                "game_item",
                leaf.id,
                title="Should Not Work",
                db=mem_session,
            )
        assert exc_info.value.status_code == 422
        assert "metadata" in exc_info.value.detail.lower()

    def test_invalid_entity_type_raises_422(self, mem_session):
        from fastapi import HTTPException
        from backend.service.games.enrich import enrich_entity

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity("unknown_type", 1, db=mem_session)
        assert exc_info.value.status_code == 422
        assert "entity_type" in exc_info.value.detail

    def test_metadata_fetched_at_set_on_bundle_keep(self, mem_session):
        """A Keep that actually applies bundle-level metadata stamps
        metadata_fetched_at; an empty payload does not."""
        from backend.models.game import GameItemBundle
        from backend.service.games.enrich import enrich_entity

        c = GameItemBundle(title="My Set", era="ps1", slug="my-set")
        mem_session.add(c)
        mem_session.commit()
        mem_session.refresh(c)
        assert c.metadata_fetched_at is None

        entity, _ = enrich_entity(
            "game_item_bundle", c.id, metadata_source="TheGamesDB", db=mem_session,
        )
        assert entity.metadata_fetched_at is not None

    def test_metadata_fetched_at_set_on_leaf_cover_art_keep(self, mem_session, monkeypatch):
        """A leaf-level Keep that actually applies cover art stamps
        metadata_fetched_at too, the only leaf-level fetch path that exists."""
        from backend.models.game import GameItemBundle, GameItem
        from backend.service.games import enrich as enrich_mod

        c = GameItemBundle(title="My Set", era="ps1", slug="my-set")
        mem_session.add(c)
        mem_session.commit()
        mem_session.refresh(c)

        leaf = GameItem(game_item_bundle_id=c.id, file_path="/tmp/disc1.bin", disc_number=1)
        mem_session.add(leaf)
        mem_session.commit()
        mem_session.refresh(leaf)
        assert leaf.metadata_fetched_at is None

        monkeypatch.setattr(
            enrich_mod, "download_remote_image", lambda url, dest_dir, **kw: dest_dir / "cover.jpg"
        )

        entity, _ = enrich_mod.enrich_entity(
            "game_item", leaf.id, cover_art_url="https://cdn.example.com/art.jpg", db=mem_session,
        )
        assert entity.metadata_fetched_at is not None
