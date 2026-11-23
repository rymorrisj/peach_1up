"""Tests for backend/service/utils/github_release_installer.py's offline
guards: the zip-slip and .git rejection in _safe_extract_zip and
_safe_extract_7z, the digest comparison in _verify_digest, the required-field
check in _manifest_entry (including the optional version default), and the
decompression-bomb size cap in _safe_extract_7z.

Security-sensitive: the module extracts an executable archive to disk from a
fetched manifest. The zip-slip guard and the .git component rejection are
load-bearing, do not relax them.

No network and no subprocess: _fetch_manifest, _download_asset, get_emulator,
and ensure_portable_mode are patched wherever install_from_github_release is
invoked; zips are built in-memory and written to tmp_path only because
_safe_extract_zip takes a real Path; the 7z tests patch _list_7z_entries and
_run_7za so 7za.exe is never run.
"""

import hashlib
import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest


def _build_zip(tmp_path: Path, members: dict[str, bytes]) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    zip_path = tmp_path / "asset.zip"
    zip_path.write_bytes(buf.getvalue())
    return zip_path


def _manifest_shaped_entry(**overrides) -> dict:
    """A manifest.json entry as published for an emulator with no upstream
    version: tag, asset, sha256, released_at, and no version key. Pass
    ``version=...`` to add one, or any other key to override it."""
    entry = {
        "tag": "duckstation-2026-08-01",
        "asset": "emulator.zip",
        "sha256": "ab" * 32,
        "released_at": "2026-08-01T00:00:00Z",
    }
    entry.update(overrides)
    return entry


# ---------------------------------------------------------------------------
# _safe_extract_zip
# ---------------------------------------------------------------------------


class TestSafeExtractZip:
    def test_path_traversal_member_raises_before_writing_anything(self, tmp_path):
        """Zip-slip guard: a member escaping dest_dir via '..' must raise
        before any file lands on disk."""
        from backend.service.utils.github_release_installer import _safe_extract_zip

        zip_path = _build_zip(tmp_path, {"../../evil.exe": b"payload"})
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        with pytest.raises(RuntimeError, match="Zip-slip"):
            _safe_extract_zip(zip_path, dest_dir)

        assert list(dest_dir.iterdir()) == []

    def test_git_path_component_member_raises(self, tmp_path):
        """Only the repo's own root .git is allowed, an extracted member must
        never carry one."""
        from backend.service.utils.github_release_installer import _safe_extract_zip

        zip_path = _build_zip(tmp_path, {"sub/.git/config": b"data"})
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        with pytest.raises(RuntimeError, match=r"\.git"):
            _safe_extract_zip(zip_path, dest_dir)

        assert list(dest_dir.iterdir()) == []

    def test_normal_member_extracts_successfully(self, tmp_path):
        """The guards must not be so broad that nested content stops extracting."""
        from backend.service.utils.github_release_installer import _safe_extract_zip

        zip_path = _build_zip(
            tmp_path,
            {
                "bin/app.exe": b"binary-content",
                "readme.txt": b"hello",
            },
        )
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        _safe_extract_zip(zip_path, dest_dir)

        assert (dest_dir / "bin" / "app.exe").read_bytes() == b"binary-content"
        assert (dest_dir / "readme.txt").read_bytes() == b"hello"


# ---------------------------------------------------------------------------
# _verify_digest
# ---------------------------------------------------------------------------


class TestVerifyDigest:
    def test_case_differing_but_unequal_digest_raises(self):
        from backend.service.utils.github_release_installer import _verify_digest

        with pytest.raises(RuntimeError, match="SHA256 mismatch"):
            _verify_digest("ABCDEF0123456789", "abcdef0123456780", "asset.zip")

    def test_case_differing_but_equal_digest_passes(self):
        from backend.service.utils.github_release_installer import _verify_digest

        _verify_digest("ABCDEF0123456789", "abcdef0123456789", "asset.zip")


# ---------------------------------------------------------------------------
# _manifest_entry
# ---------------------------------------------------------------------------


class TestManifestEntry:
    def test_missing_sha256_field_raises_naming_it(self):
        from backend.service.utils.github_release_installer import _manifest_entry

        manifest = {"flycast": {"version": "1.0", "tag": "v1.0", "asset": "flycast.zip"}}

        with pytest.raises(RuntimeError, match="sha256"):
            _manifest_entry(manifest, "flycast")

    def test_slug_absent_from_manifest_raises(self):
        from backend.service.utils.github_release_installer import _manifest_entry

        with pytest.raises(RuntimeError, match="No manifest entry for 'flycast'"):
            _manifest_entry({"pcsx2": {}}, "flycast")

    @pytest.mark.parametrize("field", ["tag", "asset", "sha256"])
    def test_missing_required_field_raises_naming_it(self, field):
        from backend.service.utils.github_release_installer import _manifest_entry

        entry = _manifest_shaped_entry()
        del entry[field]

        with pytest.raises(RuntimeError, match=rf"\['{field}'\]"):
            _manifest_entry({"rpcs3": entry}, "rpcs3")

    def test_entry_with_version_is_returned_unchanged(self):
        from backend.service.utils.github_release_installer import _manifest_entry

        entry = _manifest_shaped_entry(version="0.0.41")

        assert _manifest_entry({"rpcs3": entry}, "rpcs3") == entry

    def test_absent_version_defaults_to_latest(self):
        from backend.service.utils.github_release_installer import _manifest_entry

        entry = _manifest_shaped_entry()
        assert "version" not in entry

        result = _manifest_entry({"duckstation": entry}, "duckstation")

        assert result["version"] == "latest"
        assert result["tag"] == entry["tag"]
        assert result["asset"] == entry["asset"]
        assert result["sha256"] == entry["sha256"]

    @pytest.mark.parametrize("empty_version", [None, ""])
    def test_null_or_empty_version_defaults_to_latest(self, empty_version):
        from backend.service.utils.github_release_installer import _manifest_entry

        entry = _manifest_shaped_entry(version=empty_version)

        result = _manifest_entry({"xenia": entry}, "xenia")

        assert result["version"] == "latest"

    def test_default_does_not_mutate_the_fetched_manifest(self):
        from backend.service.utils.github_release_installer import _manifest_entry

        manifest = {"duckstation": _manifest_shaped_entry()}

        _manifest_entry(manifest, "duckstation")

        assert "version" not in manifest["duckstation"]


# ---------------------------------------------------------------------------
# install_from_github_release: version handling, network and catalog stubbed
# ---------------------------------------------------------------------------


def _patch_install_flow(monkeypatch, installer, tmp_path, manifest, zip_bytes):
    """Stub every external dependency of install_from_github_release so the
    real manifest check, digest check, zip-slip guard, and extraction run
    against an in-memory archive. Returns the list of download URLs requested."""
    requested_urls: list[str] = []

    def _fake_download(download_url, dest):
        requested_urls.append(download_url)
        dest.write_bytes(zip_bytes)

    monkeypatch.setattr(installer, "_BASE_DIR", tmp_path / "emulators")
    monkeypatch.setattr(installer, "_fetch_manifest", lambda: manifest)
    monkeypatch.setattr(installer, "_download_asset", _fake_download)
    monkeypatch.setattr(
        installer,
        "get_emulator",
        lambda slug: {"install_type": "github_release", "binary": "app.exe"},
    )
    monkeypatch.setattr(installer, "ensure_portable_mode", lambda slug, binary_path: None)
    return requested_urls


class TestInstallVersionHandling:
    def test_entry_without_version_installs_normally_as_latest(self, tmp_path, monkeypatch):
        from backend.service.utils import github_release_installer as installer

        zip_bytes = _build_zip(tmp_path, {"app.exe": b"binary"}).read_bytes()
        digest = hashlib.sha256(zip_bytes).hexdigest()
        entry = _manifest_shaped_entry(sha256=digest)
        assert "version" not in entry
        requested = _patch_install_flow(
            monkeypatch,
            installer,
            tmp_path,
            {"duckstation": entry},
            zip_bytes,
        )

        result = installer.install_from_github_release("duckstation")

        assert result["version"] == "latest"
        assert result["digest_verified"] is True
        assert result["sha256"] == digest
        assert requested == [f"{installer._RELEASE_DOWNLOAD_ROOT}/{entry['tag']}/{entry['asset']}"]
        assert (tmp_path / "emulators" / "duckstation" / "app.exe").read_bytes() == b"binary"

    def test_entry_with_version_keeps_it(self, tmp_path, monkeypatch):
        from backend.service.utils import github_release_installer as installer

        zip_bytes = _build_zip(tmp_path, {"app.exe": b"binary"}).read_bytes()
        entry = _manifest_shaped_entry(
            version="0.0.41",
            sha256=hashlib.sha256(zip_bytes).hexdigest(),
        )
        _patch_install_flow(monkeypatch, installer, tmp_path, {"rpcs3": entry}, zip_bytes)

        result = installer.install_from_github_release("rpcs3")

        assert result["version"] == "0.0.41"

    def test_digest_mismatch_still_aborts_for_an_entry_without_version(self, tmp_path, monkeypatch):
        from backend.service.utils import github_release_installer as installer

        zip_bytes = _build_zip(tmp_path, {"app.exe": b"binary"}).read_bytes()
        entry = _manifest_shaped_entry(sha256="0" * 64)
        _patch_install_flow(monkeypatch, installer, tmp_path, {"xenia": entry}, zip_bytes)

        with pytest.raises(RuntimeError, match="SHA256 mismatch"):
            installer.install_from_github_release("xenia")

        assert not (tmp_path / "emulators" / "xenia").exists()


# ---------------------------------------------------------------------------
# _safe_extract_7z: same guards as the zip path, plus the size cap
# ---------------------------------------------------------------------------


def _patch_7z_listing(monkeypatch, installer, entries):
    """Return the list _run_7za calls are recorded into, so a test can assert
    a guard fired before extraction rather than after. The stub returns a
    zero-exit CompletedProcess shape for the cases that do reach it."""
    monkeypatch.setattr(installer, "_list_7z_entries", lambda archive_path: entries)
    run_calls: list[list[str]] = []

    def _fake_run_7za(args):
        run_calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(installer, "_run_7za", _fake_run_7za)
    return run_calls


class TestSafeExtract7zGuards:
    def test_path_traversal_entry_raises_before_invoking_7za(self, tmp_path, monkeypatch):
        """The zip path's zip-slip guard, on the 7z path. 7za.exe reports
        backslash-separated paths, which _safe_extract_7z normalises first."""
        from backend.service.utils import github_release_installer as installer

        run_calls = _patch_7z_listing(
            monkeypatch,
            installer,
            [{"Path": r"..\..\evil.exe", "Size": "10", "Attributes": "A"}],
        )
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        archive_path = tmp_path / "fake.7z"
        archive_path.write_bytes(b"")

        with pytest.raises(RuntimeError, match="Zip-slip"):
            installer._safe_extract_7z(archive_path, dest_dir)

        assert run_calls == []
        assert list(dest_dir.iterdir()) == []

    def test_git_path_component_entry_raises_before_invoking_7za(self, tmp_path, monkeypatch):
        from backend.service.utils import github_release_installer as installer

        run_calls = _patch_7z_listing(
            monkeypatch,
            installer,
            [{"Path": r"sub\.git\config", "Size": "10", "Attributes": "A"}],
        )
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        archive_path = tmp_path / "fake.7z"
        archive_path.write_bytes(b"")

        with pytest.raises(RuntimeError, match=r"\.git"):
            installer._safe_extract_7z(archive_path, dest_dir)

        assert run_calls == []
        assert list(dest_dir.iterdir()) == []

    def test_directory_entries_do_not_count_toward_the_size_cap(self, tmp_path, monkeypatch):
        """Directory entries carry 7za's 'D' attribute and a Size field that
        must not be summed, or a deep tree would trip the cap on its own."""
        from backend.service.utils import github_release_installer as installer

        entries = [
            {"Path": "bigdir", "Size": str(installer._MAX_7Z_EXTRACT_SIZE), "Attributes": "D"},
            {"Path": "bigdir/app.exe", "Size": "1024", "Attributes": "A"},
        ]
        run_calls = _patch_7z_listing(monkeypatch, installer, entries)
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        archive_path = tmp_path / "fake.7z"
        archive_path.write_bytes(b"")

        installer._safe_extract_7z(archive_path, dest_dir)

        assert len(run_calls) == 1


class TestSafeExtract7zSizeCap:
    def test_total_size_over_cap_raises_before_invoking_7za(self, tmp_path, monkeypatch):
        """Decompression-bomb cap: the summed uncompressed size is checked
        against _MAX_7Z_EXTRACT_SIZE before 7za.exe is invoked to extract."""
        from backend.service.utils import github_release_installer as installer

        fake_entries = [
            {"Path": "big1.bin", "Size": str(installer._MAX_7Z_EXTRACT_SIZE), "Attributes": "A"},
            {"Path": "big2.bin", "Size": "1", "Attributes": "A"},
        ]
        monkeypatch.setattr(installer, "_list_7z_entries", lambda archive_path: fake_entries)
        run_calls: list[list[str]] = []
        monkeypatch.setattr(installer, "_run_7za", lambda args: run_calls.append(args))

        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        archive_path = tmp_path / "fake.7z"
        archive_path.write_bytes(b"")

        with pytest.raises(RuntimeError, match="exceeds limit"):
            installer._safe_extract_7z(archive_path, dest_dir)

        assert run_calls == []


# INTEGRATION TEST NEEDED: install_from_github_release end to end. Needs the
# live manifest and a real release download, so it cannot run here. Would
# verify the ordered guarantees the module docstring makes: the asset is
# downloaded in full before extraction starts, a digest mismatch aborts
# without writing into emulators/<slug>/, the tempdir is removed on both
# success and failure, and a missing expected binary after extraction raises
# with the actual extracted contents listed.
#
# INTEGRATION TEST NEEDED: _list_7z_entries against a real 7za.exe -slt
# listing. Its parser skips the archive's own header block by splitting on
# the "----------" separator, which is 7za output-format-dependent and
# stubbed out in every test above.
