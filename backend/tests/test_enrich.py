"""Tests for backend.service.library.enrich:

- _is_forbidden_redirect_host: pure SSRF-guard function
- _download_cover_art: scheme validation, path-traversal guard, byte cap (20 MB),
  SSRF via redirect, non-image content-type, HTTP error passthrough
- enrich_entity: error branches for not-found entities and unsupported operations

Run with:
    pytest backend/tests/test_enrich.py
"""
from pathlib import Path
from unittest.mock import MagicMock

import httpx as real_httpx
import pytest


# ---------------------------------------------------------------------------
# _is_forbidden_redirect_host — pure function
# ---------------------------------------------------------------------------


class TestIsForbiddenRedirectHost:
    def _call(self, host: str) -> bool:
        from backend.service.library.enrich import _is_forbidden_redirect_host

        return _is_forbidden_redirect_host(host)

    def test_localhost_string_is_forbidden(self):
        assert self._call("localhost") is True

    def test_loopback_ipv4_is_forbidden(self):
        assert self._call("127.0.0.1") is True

    def test_loopback_ipv6_is_forbidden(self):
        assert self._call("::1") is True

    def test_private_class_a_is_forbidden(self):
        assert self._call("10.0.0.1") is True

    def test_private_class_c_is_forbidden(self):
        assert self._call("192.168.1.1") is True

    def test_link_local_is_forbidden(self):
        assert self._call("169.254.1.1") is True

    def test_public_ipv4_is_not_forbidden(self):
        assert self._call("8.8.8.8") is False

    def test_arbitrary_public_hostname_is_not_forbidden(self):
        # Non-IP string that is not "localhost" → ValueError in ip_address() → False
        assert self._call("cdn.example.com") is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_httpx(
    *,
    url_scheme: str = "https",
    url_host: str = "cdn.example.com",
    content_type: str = "image/jpeg",
    body_chunks: list[bytes] | None = None,
    raise_for_status_exc=None,
) -> MagicMock:
    """Return a MagicMock suitable for monkeypatching enrich_mod.httpx.

    Preserves the real HTTPStatusError class so that
    `except httpx.HTTPStatusError` in _download_cover_art still works.
    """
    if body_chunks is None:
        body_chunks = [b"fake-image-data"]

    mock_url = MagicMock()
    mock_url.scheme = url_scheme
    mock_url.host = url_host

    mock_resp = MagicMock()
    mock_resp.url = mock_url
    mock_resp.headers = {"content-type": content_type}
    mock_resp.iter_bytes = MagicMock(return_value=iter(body_chunks))

    if raise_for_status_exc is not None:
        mock_resp.raise_for_status = MagicMock(side_effect=raise_for_status_exc)
    else:
        mock_resp.raise_for_status = MagicMock()

    stream_ctx = MagicMock()
    stream_ctx.__enter__ = MagicMock(return_value=mock_resp)
    stream_ctx.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=stream_ctx)

    client_ctx = MagicMock()
    client_ctx.__enter__ = MagicMock(return_value=mock_client)
    client_ctx.__exit__ = MagicMock(return_value=False)

    mock_httpx = MagicMock()
    mock_httpx.Client = MagicMock(return_value=client_ctx)
    # Preserve the real exception class so `except httpx.HTTPStatusError` still works
    mock_httpx.HTTPStatusError = real_httpx.HTTPStatusError

    return mock_httpx


@pytest.fixture
def tmp_lib(tmp_path, monkeypatch):
    """Patches LIBRARY_PATH to tmp_path and yields it."""
    import backend.service.utils.settings as settings_mod

    def _fake_get(key, default=None):
        if key == "LIBRARY_PATH":
            return str(tmp_path)
        return default

    monkeypatch.setattr(settings_mod, "get", _fake_get)
    yield tmp_path


# ---------------------------------------------------------------------------
# _download_cover_art
# ---------------------------------------------------------------------------


class TestDownloadCoverArt:
    def test_non_https_url_raises_422(self, tmp_lib):
        from fastapi import HTTPException
        from backend.service.library.enrich import _download_cover_art

        with pytest.raises(HTTPException) as exc_info:
            _download_cover_art("http://example.com/art.jpg", tmp_lib)
        assert exc_info.value.status_code == 422
        assert "https" in exc_info.value.detail

    def test_dest_dir_outside_library_path_raises_422(self, tmp_lib):
        """Path-traversal guard: destination must be inside LIBRARY_PATH."""
        import backend.service.library.enrich as enrich_mod
        from fastapi import HTTPException

        # A sibling directory that shares the same parent as tmp_lib is not
        # inside LIBRARY_PATH (tmp_lib).
        outside = tmp_lib.parent / "outside_of_lib"
        outside.mkdir(exist_ok=True)

        with pytest.raises(HTTPException) as exc_info:
            enrich_mod._download_cover_art("https://cdn.example.com/art.jpg", outside)
        assert exc_info.value.status_code == 422
        assert "LIBRARY_PATH" in exc_info.value.detail

    def test_http_error_from_server_raises_502(self, tmp_lib, monkeypatch):
        import backend.service.library.enrich as enrich_mod
        from fastapi import HTTPException

        exc = real_httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=MagicMock()
        )
        mock_httpx = _make_mock_httpx(raise_for_status_exc=exc)
        monkeypatch.setattr(enrich_mod, "httpx", mock_httpx)

        with pytest.raises(HTTPException) as exc_info:
            enrich_mod._download_cover_art("https://cdn.example.com/art.jpg", tmp_lib)
        assert exc_info.value.status_code == 502

    def test_redirect_to_http_scheme_raises_422(self, tmp_lib, monkeypatch):
        import backend.service.library.enrich as enrich_mod
        from fastapi import HTTPException

        mock_httpx = _make_mock_httpx(url_scheme="http")
        monkeypatch.setattr(enrich_mod, "httpx", mock_httpx)

        with pytest.raises(HTTPException) as exc_info:
            enrich_mod._download_cover_art("https://cdn.example.com/art.jpg", tmp_lib)
        assert exc_info.value.status_code == 422
        assert "https" in exc_info.value.detail.lower() or "redirect" in exc_info.value.detail.lower()

    def test_redirect_to_private_ip_raises_422(self, tmp_lib, monkeypatch):
        import backend.service.library.enrich as enrich_mod
        from fastapi import HTTPException

        mock_httpx = _make_mock_httpx(url_scheme="https", url_host="192.168.1.10")
        monkeypatch.setattr(enrich_mod, "httpx", mock_httpx)

        with pytest.raises(HTTPException) as exc_info:
            enrich_mod._download_cover_art("https://cdn.example.com/art.jpg", tmp_lib)
        assert exc_info.value.status_code == 422

    def test_non_image_content_type_raises_422(self, tmp_lib, monkeypatch):
        import backend.service.library.enrich as enrich_mod
        from fastapi import HTTPException

        mock_httpx = _make_mock_httpx(content_type="application/octet-stream")
        monkeypatch.setattr(enrich_mod, "httpx", mock_httpx)

        with pytest.raises(HTTPException) as exc_info:
            enrich_mod._download_cover_art("https://cdn.example.com/art.jpg", tmp_lib)
        assert exc_info.value.status_code == 422
        assert "content-type" in exc_info.value.detail.lower()

    def test_body_exceeding_20mb_aborts_with_422(self, tmp_lib, monkeypatch):
        """Byte cap is enforced during streaming; the download aborts early."""
        import backend.service.library.enrich as enrich_mod
        from fastapi import HTTPException

        # 21 chunks of 1 MB each → 21 MB, exceeding the 20 MB cap
        chunk = b"x" * (1024 * 1024)
        mock_httpx = _make_mock_httpx(body_chunks=[chunk] * 21)
        monkeypatch.setattr(enrich_mod, "httpx", mock_httpx)

        with pytest.raises(HTTPException) as exc_info:
            enrich_mod._download_cover_art("https://cdn.example.com/art.jpg", tmp_lib)
        assert exc_info.value.status_code == 422
        assert "20 MB" in exc_info.value.detail

    def test_valid_jpeg_is_written_to_disk(self, tmp_lib, monkeypatch):
        import backend.service.library.enrich as enrich_mod

        image_data = b"\xff\xd8\xff"  # minimal JPEG header
        mock_httpx = _make_mock_httpx(content_type="image/jpeg", body_chunks=[image_data])
        monkeypatch.setattr(enrich_mod, "httpx", mock_httpx)

        result = enrich_mod._download_cover_art("https://cdn.example.com/art.jpg", tmp_lib)

        assert result.exists()
        assert result.read_bytes() == image_data
        assert result.suffix == ".jpg"


# ---------------------------------------------------------------------------
# enrich_entity — error branches (no real download needed)
# ---------------------------------------------------------------------------


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
        from backend.service.library.enrich import enrich_entity

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity("library_collection", 9999, title="New Title", db=mem_session)
        assert exc_info.value.status_code == 404

    def test_library_item_not_found_raises_404(self, mem_session):
        from fastapi import HTTPException
        from backend.service.library.enrich import enrich_entity

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity("library_item", 9999, cover_art_url="https://cdn.example.com/a.jpg", db=mem_session)
        assert exc_info.value.status_code == 404

    def test_library_collection_with_cover_art_url_raises_422(self, mem_session):
        """Collections don't support direct cover art — must be applied to individual discs."""
        from fastapi import HTTPException
        from backend.models.library import LibraryCollection
        from backend.service.library.enrich import enrich_entity

        c = LibraryCollection(title="My Set", era="ps1", slug="my-set")
        mem_session.add(c)
        mem_session.commit()
        mem_session.refresh(c)

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity(
                "library_collection",
                c.id,
                cover_art_url="https://cdn.example.com/art.jpg",
                db=mem_session,
            )
        assert exc_info.value.status_code == 422
        assert "cover_art_url" in exc_info.value.detail

    def test_library_item_with_metadata_fields_raises_422(self, mem_session):
        """Disc-level leaves (library_item) do not accept metadata fields."""
        from fastapi import HTTPException
        from backend.models.library import LibraryCollection, LibraryItem
        from backend.service.library.enrich import enrich_entity

        c = LibraryCollection(title="My Set", era="ps1", slug="my-set")
        mem_session.add(c)
        mem_session.commit()
        mem_session.refresh(c)

        leaf = LibraryItem(library_collection_id=c.id, media_path="/tmp/disc1.bin", disc_number=1)
        mem_session.add(leaf)
        mem_session.commit()
        mem_session.refresh(leaf)

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity(
                "library_item",
                leaf.id,
                title="Should Not Work",
                db=mem_session,
            )
        assert exc_info.value.status_code == 422
        assert "metadata" in exc_info.value.detail.lower()

    def test_invalid_entity_type_raises_422(self, mem_session):
        from fastapi import HTTPException
        from backend.service.library.enrich import enrich_entity

        with pytest.raises(HTTPException) as exc_info:
            enrich_entity("unknown_type", 1, db=mem_session)
        assert exc_info.value.status_code == 422
        assert "entity_type" in exc_info.value.detail
