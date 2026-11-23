"""Tests for backend.service.utils.asset_fetch:

- _is_forbidden_redirect_host: pure SSRF-guard function (IP literals)
- _validate_request_url: per-request target validation (https, port, no
  userinfo, provider CDN host allowlist, DNS resolution to public IPs only)
- download_remote_image: manual redirect following (max 3 hops, each hop
  validated before it is requested), path-traversal guards on dest_dir and
  the final file path, byte cap (20 MB default), MIME allowlist plus
  magic-byte sniff (SVG rejected), exclusive create, HTTP error passthrough

Both are shared code. enrich.py's cover-art path and media_link.py's Accept
All asset downloads call into them.

No test touches the network: httpx2 is replaced with a MagicMock and the
resolver (_resolve_host_addresses) with a fake, autouse below.
"""

from unittest.mock import MagicMock

import httpx2
import pytest

_TGDB_URL = "https://cdn.thegamesdb.net/images/original/boxart/front/1-1.jpg"
_IGDB_URL = "https://images.igdb.com/igdb/image/upload/t_cover_big/abc.jpg"
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
_GIF = b"GIF89a" + b"\x00" * 16
_WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 8
_SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
_PUBLIC_IP = "151.101.1.1"


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    """Every hostname resolves to one public address unless a test overrides it."""
    import backend.service.utils.asset_fetch as asset_fetch_mod

    monkeypatch.setattr(asset_fetch_mod, "_resolve_host_addresses", lambda host, port: [_PUBLIC_IP])


def _fake_dns(monkeypatch, table: dict[str, list[str]]):
    import backend.service.utils.asset_fetch as asset_fetch_mod

    monkeypatch.setattr(asset_fetch_mod, "_resolve_host_addresses", lambda host, port: table[host])


# ---------------------------------------------------------------------------
# _is_forbidden_redirect_host, pure function
# ---------------------------------------------------------------------------


class TestIsForbiddenRedirectHost:
    def _call(self, host: str) -> bool:
        from backend.service.utils.asset_fetch import _is_forbidden_redirect_host

        return _is_forbidden_redirect_host(host)

    def test_localhost_string_is_forbidden(self):
        assert self._call("localhost") is True

    def test_localhost_with_trailing_dot_is_forbidden(self):
        assert self._call("LOCALHOST.") is True

    def test_loopback_ipv4_is_forbidden(self):
        assert self._call("127.0.0.1") is True

    def test_loopback_ipv6_is_forbidden(self):
        assert self._call("::1") is True

    def test_ipv4_mapped_loopback_is_forbidden(self):
        assert self._call("::ffff:127.0.0.1") is True

    def test_private_class_a_is_forbidden(self):
        assert self._call("10.0.0.1") is True

    def test_private_class_c_is_forbidden(self):
        assert self._call("192.168.1.1") is True

    def test_link_local_is_forbidden(self):
        assert self._call("169.254.1.1") is True

    def test_unspecified_is_forbidden(self):
        assert self._call("0.0.0.0") is True

    def test_shared_cgnat_range_is_forbidden(self):
        assert self._call("100.64.0.1") is True

    def test_multicast_is_forbidden(self):
        assert self._call("224.0.0.1") is True

    def test_public_ipv4_is_not_forbidden(self):
        assert self._call("8.8.8.8") is False

    def test_arbitrary_public_hostname_is_not_forbidden(self):
        # Non-IP string that is not "localhost" → ValueError in ip_address() → False
        assert self._call("cdn.example.com") is False


# ---------------------------------------------------------------------------
# _validate_request_url, per-hop validation
# ---------------------------------------------------------------------------


class TestValidateRequestUrl:
    def _call(self, url: str):
        from backend.service.utils.asset_fetch import _validate_request_url

        return _validate_request_url(url)

    def _assert_422(self, url: str):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            self._call(url)
        assert exc_info.value.status_code == 422
        return exc_info.value

    @pytest.mark.parametrize("url", [_TGDB_URL, _IGDB_URL, "https://CDN.TheGamesDB.net./images/x.jpg"])
    def test_allowlisted_https_host_with_public_dns_passes(self, url):
        self._call(url)

    def test_http_scheme_rejected(self):
        exc = self._assert_422("http://cdn.thegamesdb.net/images/x.jpg")
        assert "https" in exc.detail

    def test_host_not_on_cdn_allowlist_rejected(self):
        exc = self._assert_422("https://evil.example.com/x.jpg")
        assert "allowed" in exc.detail

    @pytest.mark.parametrize(
        "url",
        [
            "https://127.0.0.1/x.jpg",
            "https://[::1]/x.jpg",
            "https://169.254.169.254/latest/meta-data/",
            "https://localhost/x.jpg",
        ],
    )
    def test_ip_literal_and_localhost_targets_rejected(self, url):
        self._assert_422(url)

    def test_userinfo_rejected(self):
        # Classic confusion trick: the real host is after the "@".
        self._assert_422("https://cdn.thegamesdb.net@127.0.0.1/x.jpg")
        self._assert_422("https://user:pw@cdn.thegamesdb.net/x.jpg")

    def test_non_default_port_rejected(self):
        self._assert_422("https://cdn.thegamesdb.net:8443/x.jpg")

    def test_malformed_port_rejected(self):
        self._assert_422("https://cdn.thegamesdb.net:notaport/x.jpg")

    @pytest.mark.parametrize(
        "private_ip",
        [
            "10.0.0.5",
            "127.0.0.1",
            "192.168.1.20",
            "169.254.169.254",
            "::1",
            "fe80::1%eth0",
            "0.0.0.0",
        ],
    )
    def test_allowlisted_name_resolving_to_private_ip_rejected(self, monkeypatch, private_ip):
        """DNS name on the allowlist, but its A/AAAA record points inside."""
        _fake_dns(monkeypatch, {"cdn.thegamesdb.net": [private_ip]})
        exc = self._assert_422(_TGDB_URL)
        assert "private" in exc.detail

    def test_any_private_address_among_several_rejects(self, monkeypatch):
        _fake_dns(monkeypatch, {"cdn.thegamesdb.net": [_PUBLIC_IP, "10.1.2.3"]})
        self._assert_422(_TGDB_URL)

    def test_dns_failure_is_502(self, monkeypatch):
        import backend.service.utils.asset_fetch as asset_fetch_mod
        from fastapi import HTTPException

        def _boom(host, port):
            raise OSError("name resolution failed")

        monkeypatch.setattr(asset_fetch_mod, "_resolve_host_addresses", _boom)
        with pytest.raises(HTTPException) as exc_info:
            self._call(_TGDB_URL)
        assert exc_info.value.status_code == 502

    def test_no_addresses_is_502(self, monkeypatch):
        from fastapi import HTTPException

        _fake_dns(monkeypatch, {"cdn.thegamesdb.net": []})
        with pytest.raises(HTTPException) as exc_info:
            self._call(_TGDB_URL)
        assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _response_ctx(
    *,
    status_code: int = 200,
    url_scheme: str = "https",
    url_host: str = "cdn.thegamesdb.net",
    content_type: str = "image/jpeg",
    body_chunks: list[bytes] | None = None,
    location: str | None = None,
    raise_for_status_exc=None,
) -> MagicMock:
    """One client.stream(...) context manager yielding a fake response."""
    if body_chunks is None:
        body_chunks = [_JPEG]

    mock_url = MagicMock()
    mock_url.scheme = url_scheme
    mock_url.host = url_host

    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.url = mock_url
    headers = {"content-type": content_type}
    if location is not None:
        headers["location"] = location
    mock_resp.headers = headers
    mock_resp.iter_bytes = MagicMock(return_value=iter(body_chunks))

    if raise_for_status_exc is not None:
        mock_resp.raise_for_status = MagicMock(side_effect=raise_for_status_exc)
    else:
        mock_resp.raise_for_status = MagicMock()

    stream_ctx = MagicMock()
    stream_ctx.__enter__ = MagicMock(return_value=mock_resp)
    stream_ctx.__exit__ = MagicMock(return_value=False)
    return stream_ctx


def _make_mock_httpx2(*responses: MagicMock, **single) -> MagicMock:
    """Return a MagicMock suitable for monkeypatching asset_fetch_mod.httpx2.

    Pass response contexts positionally (one per expected request, in
    order) or a single response's fields as keywords. The fake client is
    exposed as ``.fake_client`` so tests can assert which URLs were
    requested. Preserves the real HTTPStatusError class so that
    `except httpx2.HTTPStatusError` in download_remote_image still works.
    """
    contexts = list(responses) or [_response_ctx(**single)]

    mock_client = MagicMock()
    mock_client.stream = MagicMock(side_effect=contexts)

    client_ctx = MagicMock()
    client_ctx.__enter__ = MagicMock(return_value=mock_client)
    client_ctx.__exit__ = MagicMock(return_value=False)

    mock_httpx2 = MagicMock()
    mock_httpx2.Client = MagicMock(return_value=client_ctx)
    # Preserve the real exception class so `except httpx2.HTTPStatusError` still works
    mock_httpx2.HTTPStatusError = httpx2.HTTPStatusError
    mock_httpx2.fake_client = mock_client
    return mock_httpx2


def _requested_urls(mock_httpx2) -> list[str]:
    return [c.args[1] for c in mock_httpx2.fake_client.stream.call_args_list]


@pytest.fixture
def tmp_lib(tmp_path, monkeypatch):
    """Patches LIBRARY_PATH to tmp_path / "library" and yields it."""
    import backend.service.utils.settings as settings_mod

    lib = tmp_path / "library"
    lib.mkdir()

    def _fake_get(key, default=None):
        if key == "LIBRARY_PATH":
            return str(lib)
        return default

    monkeypatch.setattr(settings_mod, "get", _fake_get)
    yield lib


def _download(monkeypatch, mock_httpx2, dest_dir, url=_TGDB_URL, **kwargs):
    import backend.service.utils.asset_fetch as asset_fetch_mod

    monkeypatch.setattr(asset_fetch_mod, "httpx2", mock_httpx2)
    return asset_fetch_mod.download_remote_image(url, dest_dir, **kwargs)


def _expect_status(status: int, fn, *args, **kwargs):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        fn(*args, **kwargs)
    assert exc_info.value.status_code == status, exc_info.value.detail
    return exc_info.value


# ---------------------------------------------------------------------------
# download_remote_image, request validation and destination guards
# ---------------------------------------------------------------------------


class TestDownloadRemoteImage:
    def test_non_https_url_raises_422(self, tmp_lib):
        from backend.service.utils.asset_fetch import download_remote_image

        exc = _expect_status(422, download_remote_image, "http://cdn.thegamesdb.net/art.jpg", tmp_lib)
        assert "https" in exc.detail

    def test_non_allowlisted_host_is_never_requested(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2()
        _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib, url="https://cdn.example.com/art.jpg")
        assert _requested_urls(mock_httpx2) == []

    def test_dns_to_private_ip_is_never_requested(self, tmp_lib, monkeypatch):
        _fake_dns(monkeypatch, {"cdn.thegamesdb.net": ["127.0.0.1"]})
        mock_httpx2 = _make_mock_httpx2()
        _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib)
        assert _requested_urls(mock_httpx2) == []

    def test_dest_dir_outside_library_path_raises_422(self, tmp_lib):
        """Path-traversal guard: destination must be inside LIBRARY_PATH."""
        import backend.service.utils.asset_fetch as asset_fetch_mod

        # A sibling directory that shares the same parent as tmp_lib is not
        # inside LIBRARY_PATH (tmp_lib).
        outside = tmp_lib.parent / "outside_of_lib"
        outside.mkdir(exist_ok=True)

        exc = _expect_status(422, asset_fetch_mod.download_remote_image, _TGDB_URL, outside)
        assert "LIBRARY_PATH" in exc.detail

    def test_dest_dir_traversal_out_of_library_raises_422(self, tmp_lib):
        import backend.service.utils.asset_fetch as asset_fetch_mod

        _expect_status(422, asset_fetch_mod.download_remote_image, _TGDB_URL, tmp_lib / ".." / "x")

    def test_redirects_are_not_followed_automatically(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2()
        _download(monkeypatch, mock_httpx2, tmp_lib)
        assert mock_httpx2.Client.call_args.kwargs["follow_redirects"] is False

    def test_http_error_from_server_raises_502(self, tmp_lib, monkeypatch):
        exc = httpx2.HTTPStatusError("404 Not Found", request=MagicMock(), response=MagicMock())
        mock_httpx2 = _make_mock_httpx2(raise_for_status_exc=exc)
        _expect_status(502, _download, monkeypatch, mock_httpx2, tmp_lib)

    def test_response_url_with_http_scheme_raises_422(self, tmp_lib, monkeypatch):
        """Defensive re-check of the URL actually fetched."""
        mock_httpx2 = _make_mock_httpx2(url_scheme="http")
        exc = _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib)
        assert "https" in exc.detail.lower() or "redirect" in exc.detail.lower()

    def test_response_url_on_private_ip_raises_422(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(url_host="192.168.1.10")
        _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib)


# ---------------------------------------------------------------------------
# download_remote_image, manual redirect handling
# ---------------------------------------------------------------------------


class TestDownloadRedirects:
    def test_redirect_to_loopback_is_rejected_before_it_is_requested(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(
            _response_ctx(status_code=302, location="https://127.0.0.1/admin.jpg"),
            _response_ctx(),
        )
        _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib)
        assert _requested_urls(mock_httpx2) == [_TGDB_URL]

    def test_redirect_to_http_is_rejected_before_it_is_requested(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(
            _response_ctx(status_code=301, location="http://cdn.thegamesdb.net/x.jpg"),
            _response_ctx(),
        )
        _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib)
        assert _requested_urls(mock_httpx2) == [_TGDB_URL]

    def test_redirect_off_the_cdn_allowlist_is_rejected(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(
            _response_ctx(status_code=307, location="https://attacker.example/x.jpg"),
            _response_ctx(),
        )
        _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib)
        assert _requested_urls(mock_httpx2) == [_TGDB_URL]

    def test_redirect_to_allowlisted_name_resolving_private_is_rejected(self, tmp_lib, monkeypatch):
        """Per-hop DNS check: the second host is on the allowlist, but its
        record points at a private address, so it is never requested."""
        _fake_dns(monkeypatch, {"cdn.thegamesdb.net": [_PUBLIC_IP], "images.igdb.com": ["10.0.0.7"]})
        mock_httpx2 = _make_mock_httpx2(
            _response_ctx(status_code=302, location=_IGDB_URL),
            _response_ctx(url_host="images.igdb.com"),
        )
        _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib)
        assert _requested_urls(mock_httpx2) == [_TGDB_URL]

    def test_valid_redirect_chain_is_followed(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(
            _response_ctx(status_code=301, location="/images/original/moved.jpg"),
            _response_ctx(status_code=308, location=_IGDB_URL),
            _response_ctx(url_host="images.igdb.com", body_chunks=[_JPEG]),
        )
        result = _download(monkeypatch, mock_httpx2, tmp_lib)
        assert result.read_bytes() == _JPEG
        assert _requested_urls(mock_httpx2) == [
            _TGDB_URL,
            "https://cdn.thegamesdb.net/images/original/moved.jpg",  # relative Location resolved
            _IGDB_URL,
        ]

    def test_three_redirects_are_allowed(self, tmp_lib, monkeypatch):
        hops = [_response_ctx(status_code=302, location=f"/hop{i}.jpg") for i in range(3)]
        mock_httpx2 = _make_mock_httpx2(*hops, _response_ctx())
        _download(monkeypatch, mock_httpx2, tmp_lib)
        assert len(_requested_urls(mock_httpx2)) == 4

    def test_fourth_redirect_is_rejected(self, tmp_lib, monkeypatch):
        hops = [_response_ctx(status_code=302, location=f"/hop{i}.jpg") for i in range(4)]
        mock_httpx2 = _make_mock_httpx2(*hops, _response_ctx())
        exc = _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib)
        assert "redirect" in exc.detail
        assert len(_requested_urls(mock_httpx2)) == 4

    def test_redirect_without_location_is_502(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(_response_ctx(status_code=302))
        _expect_status(502, _download, monkeypatch, mock_httpx2, tmp_lib)


# ---------------------------------------------------------------------------
# download_remote_image, content checks
# ---------------------------------------------------------------------------


class TestDownloadContent:
    def test_non_image_content_type_raises_422(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(content_type="application/octet-stream")
        exc = _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib)
        assert "content-type" in exc.detail.lower()

    def test_svg_content_type_raises_422(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(content_type="image/svg+xml", body_chunks=[_SVG])
        _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib)
        assert list(tmp_lib.iterdir()) == []

    def test_svg_body_declared_as_png_raises_422(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(content_type="image/png", body_chunks=[_SVG])
        exc = _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib)
        assert "raster" in exc.detail
        assert list(tmp_lib.iterdir()) == []

    def test_html_body_declared_as_jpeg_raises_422(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(body_chunks=[b"<html><script>alert(1)</script></html>"])
        _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib)

    def test_body_exceeding_20mb_aborts_with_422(self, tmp_lib, monkeypatch):
        """Byte cap is enforced during streaming; the download aborts early."""
        # 21 chunks of 1 MB each → 21 MB, exceeding the default 20 MB cap
        chunk = b"x" * (1024 * 1024)
        mock_httpx2 = _make_mock_httpx2(body_chunks=[chunk] * 21)
        exc = _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib)
        assert "20 MB" in exc.detail

    @pytest.mark.parametrize(
        "body,content_type,ext",
        [
            (_JPEG, "image/jpeg", ".jpg"),
            (_JPEG, "image/jpg", ".jpg"),
            (_PNG, "image/png", ".png"),
            (_GIF, "image/gif", ".gif"),
            (_WEBP, "image/webp", ".webp"),
        ],
    )
    def test_allowlisted_formats_are_written(self, tmp_lib, monkeypatch, body, content_type, ext):
        mock_httpx2 = _make_mock_httpx2(content_type=content_type, body_chunks=[body])
        result = _download(monkeypatch, mock_httpx2, tmp_lib)
        assert result.read_bytes() == body
        assert result.suffix == ext

    def test_extension_comes_from_bytes_not_header(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(content_type="image/jpeg", body_chunks=[_PNG])
        result = _download(monkeypatch, mock_httpx2, tmp_lib)
        assert result.suffix == ".png"

    def test_valid_jpeg_is_written_to_disk(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(content_type="image/jpeg", body_chunks=[_JPEG])
        result = _download(monkeypatch, mock_httpx2, tmp_lib)

        assert result.exists()
        assert result.read_bytes() == _JPEG
        assert result.suffix == ".jpg"
        assert result.stem == "cover"  # default filename_stem, unchanged behavior

    def test_custom_filename_stem_is_used(self, tmp_lib, monkeypatch):
        """filename_stem is the one thing generalized out of the old
        _download_cover_art, confirm a caller-supplied stem (e.g. Accept
        All's per-asset naming) actually lands on disk."""
        mock_httpx2 = _make_mock_httpx2(body_chunks=[_JPEG])
        result = _download(monkeypatch, mock_httpx2, tmp_lib, filename_stem="boxart_front-0")
        assert result.stem == "boxart_front-0"


# ---------------------------------------------------------------------------
# download_remote_image, final path guards (META-3) and exclusive create (META-1)
# ---------------------------------------------------------------------------


class TestDownloadFinalPath:
    @pytest.mark.parametrize(
        "stem",
        [
            "..\\..\\evil",
            "../../evil",
            "/etc/evil",
            "C:\\Windows\\evil",
            "\\\\attacker\\share\\evil",
        ],
    )
    def test_hostile_stem_cannot_leave_dest_dir(self, tmp_lib, monkeypatch, stem):
        dest_dir = tmp_lib / "media" / "doom"
        mock_httpx2 = _make_mock_httpx2(body_chunks=[_JPEG])
        result = _download(monkeypatch, mock_httpx2, dest_dir, filename_stem=stem)
        assert result.parent == dest_dir.resolve()
        assert result.name == "evil.jpg"

    def test_empty_stem_falls_back(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(body_chunks=[_JPEG])
        result = _download(monkeypatch, mock_httpx2, tmp_lib, filename_stem="../")
        assert result.parent == tmp_lib.resolve()
        assert result.name == "asset.jpg"

    def test_final_path_outside_library_is_rejected(self, tmp_lib, monkeypatch):
        """The final path is containment-checked on its own, not just
        dest_dir: simulate a join that resolves outside (e.g. via a planted
        link) and confirm nothing is written."""
        import backend.service.utils.asset_fetch as asset_fetch_mod

        outside = tmp_lib.parent / "outside.jpg"
        monkeypatch.setattr(asset_fetch_mod, "resolve_under", lambda base, *parts: outside)
        mock_httpx2 = _make_mock_httpx2(body_chunks=[_JPEG])
        exc = _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib)
        assert "LIBRARY_PATH" in exc.detail
        assert not outside.exists()

    def test_existing_file_is_not_overwritten(self, tmp_lib, monkeypatch):
        existing = tmp_lib / "screenshot-0.jpg"
        existing.write_bytes(b"original")
        mock_httpx2 = _make_mock_httpx2(body_chunks=[_JPEG])
        _expect_status(409, _download, monkeypatch, mock_httpx2, tmp_lib, filename_stem="screenshot-0")
        assert existing.read_bytes() == b"original"

    def test_overwrite_true_replaces(self, tmp_lib, monkeypatch):
        existing = tmp_lib / "cover.jpg"
        existing.write_bytes(b"original")
        mock_httpx2 = _make_mock_httpx2(body_chunks=[_JPEG])
        result = _download(monkeypatch, mock_httpx2, tmp_lib, overwrite=True)
        assert result == existing.resolve()
        assert existing.read_bytes() == _JPEG


# META-21 / META-6: streamed to a temp file, moved with os.replace


def _fetch_to_temp(monkeypatch, mock_httpx2, staging_dir, url=_TGDB_URL, **kwargs):
    import backend.service.utils.asset_fetch as asset_fetch_mod

    monkeypatch.setattr(asset_fetch_mod, "httpx2", mock_httpx2)
    return asset_fetch_mod.fetch_image_to_temp(url, staging_dir, **kwargs)


class TestStreamedTempFetch:
    def test_body_lands_in_a_temp_file_inside_staging(self, tmp_lib, monkeypatch):
        staging = tmp_lib / "staging"
        mock_httpx2 = _make_mock_httpx2(body_chunks=[_JPEG[:2], _JPEG[2:]])

        tmp, ext = _fetch_to_temp(monkeypatch, mock_httpx2, staging)

        assert tmp.parent == staging.resolve()
        assert tmp.read_bytes() == _JPEG
        assert ext == ".jpg"

    def test_sniff_works_across_tiny_chunks(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(content_type="image/png", body_chunks=[bytes([b]) for b in _PNG])

        tmp, ext = _fetch_to_temp(monkeypatch, mock_httpx2, tmp_lib / "staging")

        assert ext == ".png"
        assert tmp.read_bytes() == _PNG

    def test_oversized_body_leaves_no_temp_file(self, tmp_lib, monkeypatch):
        staging = tmp_lib / "staging"
        chunk = b"x" * (1024 * 1024)
        mock_httpx2 = _make_mock_httpx2(body_chunks=[_JPEG] + [chunk] * 21)

        _expect_status(422, _fetch_to_temp, monkeypatch, mock_httpx2, staging)

        assert list(staging.iterdir()) == []

    def test_non_image_body_leaves_no_temp_file(self, tmp_lib, monkeypatch):
        staging = tmp_lib / "staging"
        mock_httpx2 = _make_mock_httpx2(body_chunks=[b"<svg></svg>"])

        _expect_status(422, _fetch_to_temp, monkeypatch, mock_httpx2, staging)

        assert list(staging.iterdir()) == []

    def test_mid_stream_error_leaves_no_temp_file(self, tmp_lib, monkeypatch):
        staging = tmp_lib / "staging"

        def _broken_body():
            yield _JPEG
            raise ConnectionResetError("peer reset")

        ctx = _response_ctx()
        ctx.__enter__.return_value.iter_bytes = MagicMock(return_value=_broken_body())
        mock_httpx2 = _make_mock_httpx2(ctx)

        with pytest.raises(ConnectionResetError):
            _fetch_to_temp(monkeypatch, mock_httpx2, staging)

        assert list(staging.iterdir()) == []

    def test_expired_deadline_is_422_before_any_request(self, tmp_lib, monkeypatch):
        import time

        mock_httpx2 = _make_mock_httpx2(body_chunks=[_JPEG])

        exc = _expect_status(
            422,
            _fetch_to_temp,
            monkeypatch,
            mock_httpx2,
            tmp_lib / "staging",
            deadline=time.monotonic() - 1,
        )

        assert "time budget" in exc.detail
        assert _requested_urls(mock_httpx2) == []

    def test_deadline_passing_mid_stream_aborts(self, tmp_lib, monkeypatch):
        import backend.service.utils.asset_fetch as asset_fetch_mod

        staging = tmp_lib / "staging"
        from types import SimpleNamespace

        # Deadline check, request timeout, hop check and the first chunk
        # see t=0; the second chunk sees t=100, past the deadline.
        clock = iter([0.0, 0.0, 0.0, 0.0])
        monkeypatch.setattr(asset_fetch_mod, "time", SimpleNamespace(monotonic=lambda: next(clock, 100.0)))
        mock_httpx2 = _make_mock_httpx2(body_chunks=[_JPEG, b"a", b"b", b"c"])

        _expect_status(422, _fetch_to_temp, monkeypatch, mock_httpx2, staging, deadline=50.0)

        assert list(staging.iterdir()) == []

    def test_staging_outside_library_is_rejected(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(body_chunks=[_JPEG])

        _expect_status(422, _fetch_to_temp, monkeypatch, mock_httpx2, tmp_lib.parent / "elsewhere")

        assert _requested_urls(mock_httpx2) == []


class TestCommitTempImage:
    def test_failed_download_leaves_nothing_at_the_destination(self, tmp_lib, monkeypatch):
        mock_httpx2 = _make_mock_httpx2(body_chunks=[b"<html></html>"])

        _expect_status(422, _download, monkeypatch, mock_httpx2, tmp_lib / "doom")

        assert list((tmp_lib / "doom").iterdir()) == []

    def test_separate_staging_dir_is_left_empty(self, tmp_lib, monkeypatch):
        staging = tmp_lib / "staging"
        mock_httpx2 = _make_mock_httpx2(body_chunks=[_JPEG])

        result = _download(monkeypatch, mock_httpx2, tmp_lib / "doom", staging_dir=staging)

        assert result.read_bytes() == _JPEG
        assert list(staging.iterdir()) == []

    def test_exclusive_commit_never_replaces_an_existing_file(self, tmp_lib):
        from backend.service.utils.asset_fetch import commit_temp_image

        tmp = tmp_lib / "dl.part"
        tmp.write_bytes(_JPEG)
        dest = tmp_lib / "screenshot-0.jpg"
        dest.write_bytes(b"original")

        _expect_status(409, commit_temp_image, tmp, dest, overwrite=False)

        assert dest.read_bytes() == b"original"

    def test_failed_move_drops_the_exclusive_claim(self, tmp_lib, monkeypatch):
        import backend.service.utils.asset_fetch as asset_fetch_mod

        tmp = tmp_lib / "dl.part"
        tmp.write_bytes(_JPEG)
        dest = tmp_lib / "screenshot-0.jpg"

        def _fail_replace(src, dst):
            raise OSError("cross-device link")

        import os
        from types import SimpleNamespace

        monkeypatch.setattr(asset_fetch_mod, "os", SimpleNamespace(replace=_fail_replace, fdopen=os.fdopen))
        with pytest.raises(OSError):
            asset_fetch_mod.commit_temp_image(tmp, dest, overwrite=False)

        assert not dest.exists()
