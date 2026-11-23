"""Fixtures for the Accept All tests: an in-memory db and the fake storage env."""

import tempfile
from pathlib import Path

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


class _Env:
    def __init__(self, lib: Path, media: Path):
        self.lib = lib
        self.media = media
        self.fetched: list[str] = []
        self.fail_on: str | None = None
        self.before_fetch = None

    def files(self) -> list[Path]:
        """Every file under MEDIA_PATH outside the staging area."""
        return sorted(
            p for p in self.media.rglob("*") if p.is_file() and "_asset_staging" not in p.relative_to(self.media).parts
        )

    def staging_leftovers(self) -> list[Path]:
        staging = self.media / "_asset_staging"
        return list(staging.rglob("*")) if staging.exists() else []


@pytest.fixture
def env(tmp_path, monkeypatch):
    import backend.core.settings as core_settings
    import backend.service.utils.asset_fetch as asset_fetch_mod
    import backend.service.utils.settings as utils_settings

    lib = tmp_path / "library"
    media = lib / "software" / "media"
    media.mkdir(parents=True)
    state = _Env(lib, media)

    class _S:
        def get_env_var(self, key):
            return str(media) if key == "MEDIA_PATH" else str(lib)

        def get(self, key, default=None):
            return default

    monkeypatch.setattr(core_settings, "get_settings", lambda: _S())
    monkeypatch.setattr(utils_settings, "get", lambda key, default=None: str(lib) if key == "LIBRARY_PATH" else default)

    def _fake_fetch(url, staging_dir, **kwargs):
        from fastapi import HTTPException

        if state.before_fetch is not None:
            state.before_fetch(url, kwargs)
        if url == state.fail_on:
            raise HTTPException(status_code=502, detail="Asset fetch failed: boom")
        state.fetched.append(url)
        fd, raw = tempfile.mkstemp(suffix=".part", dir=staging_dir)
        with open(fd, "wb") as fh:
            fh.write(b"\xff\xd8\xff" + url.encode())
        return Path(raw), ".jpg"

    monkeypatch.setattr(asset_fetch_mod, "fetch_image_to_temp", _fake_fetch)
    return state
