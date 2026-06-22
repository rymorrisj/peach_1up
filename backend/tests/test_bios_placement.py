"""Tests for bios_placement.py — the per-slug copy rules behind POST /api/v1/bios/{slug}/place.

Covers the five slugs that get the new copy-into-place flow (duckstation, pcsx2,
86box ROM pack, flycast, mesen FDS BIOS) plus the explicit xemu carve-out and the
generic source/upload validation shared by all of them.

No pytest-asyncio plugin is configured in this project, so async calls are driven
through asyncio.run() from plain sync test functions rather than `async def test_*`.
"""

import asyncio

import pytest


def _run(coro):
    return asyncio.run(coro)


def _place(**kwargs):
    from backend.service.utils.bios_placement import place_bios_asset
    return _run(place_bios_asset(**kwargs))


def _make_upload(filename: str, content: bytes = b"data"):
    from io import BytesIO
    from starlette.datastructures import Headers, UploadFile
    return UploadFile(BytesIO(content), filename=filename, headers=Headers({}))


# ---------------------------------------------------------------------------
# Shared validation — no source, no uploads, nonexistent path, unknown slug
# ---------------------------------------------------------------------------

class TestSharedValidation:
    def test_no_source_or_uploads_rejected(self, tmp_path):
        from backend.service.utils.bios_placement import PlacementError
        with pytest.raises(PlacementError, match="Provide either"):
            _place(slug="ps1-bios", source_path=None, uploads=[], dest_dir=tmp_path)

    def test_nonexistent_source_path_rejected(self, tmp_path):
        from backend.service.utils.bios_placement import PlacementError
        with pytest.raises(PlacementError, match="does not exist"):
            _place(slug="ps1-bios", source_path=str(tmp_path / "missing"), uploads=[], dest_dir=tmp_path)

    def test_unsupported_slug_rejected(self, tmp_path):
        from backend.service.utils.bios_placement import PlacementError
        src = tmp_path / "src.bin"
        src.write_bytes(b"x")
        with pytest.raises(PlacementError, match="Unsupported"):
            _place(slug="not-a-real-slug", source_path=str(src), uploads=[], dest_dir=tmp_path)

    def test_xbox_bios_always_rejected_with_xemu_guidance(self, tmp_path):
        from backend.service.utils.bios_placement import PlacementError
        src = tmp_path / "mcpx_1.0.bin"
        src.write_bytes(b"x")
        with pytest.raises(PlacementError, match="xemu/asset-paths"):
            _place(slug="xbox-bios", source_path=str(src), uploads=[], dest_dir=tmp_path)


# ---------------------------------------------------------------------------
# DuckStation (ps1-bios) — flat *.bin copy, filenames flexible
# ---------------------------------------------------------------------------

class TestDuckStationPlacement:
    def test_copies_all_bin_files_from_source_dir(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "scph1001.bin").write_bytes(b"bios1")
        (src_dir / "scph5501.bin").write_bytes(b"bios2")
        (src_dir / "readme.txt").write_text("not a bios")
        dest = tmp_path / "dest"

        result = _place(slug="ps1-bios", source_path=str(src_dir), uploads=[], dest_dir=dest)

        assert sorted(result.copied) == ["scph1001.bin", "scph5501.bin"]
        assert (dest / "scph1001.bin").read_bytes() == b"bios1"
        assert not (dest / "readme.txt").exists()

    def test_single_file_source_copies_directly(self, tmp_path):
        src = tmp_path / "scph1001.bin"
        src.write_bytes(b"bios")
        dest = tmp_path / "dest"

        result = _place(slug="ps1-bios", source_path=str(src), uploads=[], dest_dir=dest)

        assert result.copied == ["scph1001.bin"]
        assert (dest / "scph1001.bin").exists()

    def test_no_matching_files_in_dir_rejected(self, tmp_path):
        from backend.service.utils.bios_placement import PlacementError
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "readme.txt").write_text("nope")
        with pytest.raises(PlacementError, match="No PS1 BIOS"):
            _place(slug="ps1-bios", source_path=str(src_dir), uploads=[], dest_dir=tmp_path / "dest")

    def test_existing_dest_file_is_skipped_not_overwritten(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "scph1001.bin").write_bytes(b"new-bytes")
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "scph1001.bin").write_bytes(b"original-bytes")

        result = _place(slug="ps1-bios", source_path=str(src_dir), uploads=[], dest_dir=dest)

        assert result.skipped == ["scph1001.bin"]
        assert result.copied == []
        assert (dest / "scph1001.bin").read_bytes() == b"original-bytes"

    def test_upload_mode_copies_matching_file(self, tmp_path):
        dest = tmp_path / "dest"
        upload = _make_upload("scph1001.bin", b"bios-bytes")

        result = _place(slug="ps1-bios", source_path=None, uploads=[upload], dest_dir=dest)

        assert result.copied == ["scph1001.bin"]
        assert (dest / "scph1001.bin").read_bytes() == b"bios-bytes"

    def test_upload_mode_rejects_when_nothing_matches(self, tmp_path):
        from backend.service.utils.bios_placement import PlacementError
        upload = _make_upload("notes.txt", b"hi")
        with pytest.raises(PlacementError, match="None of the uploaded files"):
            _place(slug="ps1-bios", source_path=None, uploads=[upload], dest_dir=tmp_path / "dest")


# ---------------------------------------------------------------------------
# PCSX2 (ps2-bios) — multi-file set, warn (don't block) if it looks incomplete
# ---------------------------------------------------------------------------

class TestPcsx2Placement:
    def test_full_set_copied_no_incomplete_warning(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "SCPH-70012.bin").write_bytes(b"main")
        (src_dir / "rom1.bin").write_bytes(b"rom1")
        (src_dir / "erom.bin").write_bytes(b"erom")
        dest = tmp_path / "dest"

        result = _place(slug="ps2-bios", source_path=str(src_dir), uploads=[], dest_dir=dest)

        assert len(result.copied) == 3
        assert not any("incomplete" in w for w in result.warnings)

    def test_single_file_warns_incomplete_but_still_copies(self, tmp_path):
        src = tmp_path / "SCPH-70012.bin"
        src.write_bytes(b"main")
        dest = tmp_path / "dest"

        result = _place(slug="ps2-bios", source_path=str(src), uploads=[], dest_dir=dest)

        assert result.copied == ["SCPH-70012.bin"]
        assert any("incomplete" in w for w in result.warnings)
        assert (dest / "SCPH-70012.bin").exists()


# ---------------------------------------------------------------------------
# 86Box ROM pack (86box-roms) — full tree merge, preserve relative structure
# ---------------------------------------------------------------------------

class Test86BoxRomPackPlacement:
    def test_preserves_relative_subdirectory_structure(self, tmp_path):
        src_dir = tmp_path / "roms"
        (src_dir / "ibmpc").mkdir(parents=True)
        (src_dir / "ibmpc" / "bios.bin").write_bytes(b"rom-bytes")
        (src_dir / "top.bin").write_bytes(b"top-level")
        dest = tmp_path / "dest"

        result = _place(slug="86box-roms", source_path=str(src_dir), uploads=[], dest_dir=dest)

        assert sorted(result.copied) == ["ibmpc/bios.bin", "top.bin"]
        assert (dest / "ibmpc" / "bios.bin").read_bytes() == b"rom-bytes"
        assert (dest / "top.bin").exists()

    def test_merge_skips_files_already_present(self, tmp_path):
        src_dir = tmp_path / "roms"
        (src_dir / "ibmpc").mkdir(parents=True)
        (src_dir / "ibmpc" / "bios.bin").write_bytes(b"new")
        dest_sub = tmp_path / "dest" / "ibmpc"
        dest_sub.mkdir(parents=True)
        (dest_sub / "bios.bin").write_bytes(b"already-here")

        result = _place(slug="86box-roms", source_path=str(src_dir), uploads=[], dest_dir=tmp_path / "dest")

        assert result.skipped == ["ibmpc/bios.bin"]
        assert result.copied == []
        assert (dest_sub / "bios.bin").read_bytes() == b"already-here"

    def test_single_file_source_rejected_requires_folder(self, tmp_path):
        from backend.service.utils.bios_placement import PlacementError
        src = tmp_path / "bios.bin"
        src.write_bytes(b"x")
        with pytest.raises(PlacementError, match="requires a folder"):
            _place(slug="86box-roms", source_path=str(src), uploads=[], dest_dir=tmp_path / "dest")

    def test_upload_mode_not_supported(self, tmp_path):
        from backend.service.utils.bios_placement import PlacementError
        upload = _make_upload("bios.bin", b"x")
        with pytest.raises(PlacementError, match="file upload isn't supported"):
            _place(slug="86box-roms", source_path=None, uploads=[upload], dest_dir=tmp_path / "dest")


# ---------------------------------------------------------------------------
# Flycast (dreamcast-bios) — both dc_boot.bin and dc_flash.bin required together
# ---------------------------------------------------------------------------

class TestFlycastPlacement:
    def test_both_files_copied_together_no_warning(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "dc_boot.bin").write_bytes(b"boot")
        (src_dir / "dc_flash.bin").write_bytes(b"flash")
        dest = tmp_path / "dest"

        result = _place(slug="dreamcast-bios", source_path=str(src_dir), uploads=[], dest_dir=dest)

        assert sorted(result.copied) == ["dc_boot.bin", "dc_flash.bin"]
        assert result.warnings == []

    def test_only_one_file_warns_but_places_it(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "dc_boot.bin").write_bytes(b"boot")
        dest = tmp_path / "dest"

        result = _place(slug="dreamcast-bios", source_path=str(src_dir), uploads=[], dest_dir=dest)

        assert result.copied == ["dc_boot.bin"]
        assert any("dc_flash.bin" in w and "still missing" in w for w in result.warnings)

    def test_second_file_completes_set_without_warning(self, tmp_path):
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "dc_boot.bin").write_bytes(b"boot")
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "dc_flash.bin").write_bytes(b"flash")

        result = _place(slug="dreamcast-bios", source_path=str(src_dir), uploads=[], dest_dir=dest)

        assert result.copied == ["dc_flash.bin"]
        assert result.warnings == []

    def test_neither_file_present_rejected(self, tmp_path):
        from backend.service.utils.bios_placement import PlacementError
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "unrelated.bin").write_bytes(b"x")
        with pytest.raises(PlacementError, match="Expected dc_boot.bin and dc_flash.bin"):
            _place(slug="dreamcast-bios", source_path=str(src_dir), uploads=[], dest_dir=tmp_path / "dest")


# ---------------------------------------------------------------------------
# Mesen FDS BIOS (mesen-fds-bios) — optional, exact filename, known-good SHA1
# ---------------------------------------------------------------------------

class TestMesenFdsPlacement:
    def test_known_good_hash_places_without_warning(self, tmp_path):
        import hashlib
        import backend.service.utils.bios_placement as mod

        # Brute-forcing a payload whose real sha1 equals the documented
        # known-good hash isn't practical in a test — instead swap in a hash
        # that matches a fixed payload's real sha1, to exercise the match
        # branch (no-warning path) the same way a genuine dump would.
        payload = b"fds-bios-bytes"
        real_sha1 = hashlib.sha1(payload).hexdigest()
        original = mod._MESEN_FDS_SHA1
        mod._MESEN_FDS_SHA1 = real_sha1
        try:
            src = tmp_path / "FdsBios.bin"
            src.write_bytes(payload)
            dest = tmp_path / "dest"
            result = _place(slug="mesen-fds-bios", source_path=str(src), uploads=[], dest_dir=dest)
        finally:
            mod._MESEN_FDS_SHA1 = original

        assert result.copied == ["FdsBios.bin"]
        assert result.warnings == []
        # Documented value (dev_docs/EMULATORS.md) stays the real default outside the patch.
        assert mod._MESEN_FDS_SHA1 == "e4e41472c454f928e53eb10e0509bf7d1146ecc1"

    def test_hash_mismatch_warns_but_still_places(self, tmp_path):
        src = tmp_path / "FdsBios.bin"
        src.write_bytes(b"definitely-not-the-real-dump")
        dest = tmp_path / "dest"

        result = _place(slug="mesen-fds-bios", source_path=str(src), uploads=[], dest_dir=dest)

        assert result.copied == ["FdsBios.bin"]
        assert any("does not match the known-good" in w for w in result.warnings)
        assert (dest / "FdsBios.bin").exists()

    def test_wrong_filename_rejected(self, tmp_path):
        from backend.service.utils.bios_placement import PlacementError
        src = tmp_path / "fds.bin"
        src.write_bytes(b"x")
        with pytest.raises(PlacementError, match="Expected a file named"):
            _place(slug="mesen-fds-bios", source_path=str(src), uploads=[], dest_dir=tmp_path / "dest")

    def test_upload_mode_rejects_multiple_files(self, tmp_path):
        from backend.service.utils.bios_placement import PlacementError
        uploads = [_make_upload("FdsBios.bin", b"a"), _make_upload("extra.bin", b"b")]
        with pytest.raises(PlacementError, match="Upload exactly one file"):
            _place(slug="mesen-fds-bios", source_path=None, uploads=uploads, dest_dir=tmp_path / "dest")
