"""Tests for backend/service/utils/github_release_installer.py's pure,
locally-testable guards: the zip-slip and .git rejection in
_safe_extract_zip, the digest comparison in _verify_digest, the required-
field check in _manifest_entry, and the decompression-bomb size cap in
_safe_extract_7z.

Module docstring: "Security-sensitive: this downloads and extracts an
executable archive to disk based on the fetched manifest. The zip-slip
guard and the .git component rejection are load-bearing; do not relax
them." Each test below that locks in one of those guards says so.

No network calls anywhere in this file: _fetch_manifest, _download_asset,
and install_from_github_release (the functions that touch httpx) are never
invoked. Archives are built in-memory with zipfile/BytesIO and written to
tmp_path only so _safe_extract_zip (which takes a real Path) has something
to open. _safe_extract_7z is tested with _list_7z_entries and _run_7za
monkeypatched, so 7za.exe is never invoked and no subprocess is spawned.
"""

import io
import zipfile
from pathlib import Path

import pytest


def _build_zip(tmp_path: Path, members: dict[str, bytes]) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    zip_path = tmp_path / "asset.zip"
    zip_path.write_bytes(buf.getvalue())
    return zip_path


# ---------------------------------------------------------------------------
# _safe_extract_zip
# ---------------------------------------------------------------------------

class TestSafeExtractZip:
    def test_path_traversal_member_raises_before_writing_anything(self, tmp_path):
        """Locks in the zip-slip guard: a member escaping dest_dir via '..'
        must raise before any file lands on disk."""
        from backend.service.utils.github_release_installer import _safe_extract_zip
        zip_path = _build_zip(tmp_path, {"../../evil.exe": b"payload"})
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        with pytest.raises(RuntimeError, match="Zip-slip"):
            _safe_extract_zip(zip_path, dest_dir)

        assert list(dest_dir.iterdir()) == []

    def test_git_path_component_member_raises(self, tmp_path):
        """Locks in the '.git' component rejection: only the repo's own root
        .git is allowed, an extracted member must never carry one."""
        from backend.service.utils.github_release_installer import _safe_extract_zip
        zip_path = _build_zip(tmp_path, {"sub/.git/config": b"data"})
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        with pytest.raises(RuntimeError, match=r"\.git"):
            _safe_extract_zip(zip_path, dest_dir)

        assert list(dest_dir.iterdir()) == []

    def test_normal_member_extracts_successfully(self, tmp_path):
        """Confirms the guards aren't overly broad: legitimate nested content
        still extracts."""
        from backend.service.utils.github_release_installer import _safe_extract_zip
        zip_path = _build_zip(tmp_path, {
            "bin/app.exe": b"binary-content",
            "readme.txt": b"hello",
        })
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


# ---------------------------------------------------------------------------
# _safe_extract_7z: decompression-bomb size cap
# ---------------------------------------------------------------------------

class TestSafeExtract7zSizeCap:
    def test_total_size_over_cap_raises_before_invoking_7za(self, tmp_path, monkeypatch):
        """Locks in the decompression-bomb cap: total uncompressed size is
        summed and checked against _MAX_7Z_EXTRACT_SIZE before 7za.exe is
        ever invoked to actually extract."""
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
