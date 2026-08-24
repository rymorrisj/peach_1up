"""Tests for backend/service/utils/extract_xiso.py's convert_dvd_rip_to_xiso.

extract-xiso can exit 0 without having rewritten anything (its own
err_iso_no_files case resets the exit code internally), so a 0 exit is
re-verified three ways: the file still exists, is a plausible size, and no
longer detects as dvd_rip. One test per leg below.

No real subprocess: subprocess.run is stubbed everywhere.
detect_xbox_image_type is patched at its own module
(backend.service.utils.detection.xbox_image) rather than on extract_xiso,
because convert_dvd_rip_to_xiso imports it inside the function body.
"""

from types import SimpleNamespace

import pytest


def _patch_common(monkeypatch, extract_xiso_mod, tmp_path):
    """Satisfy the binary-existence check and the allowlist, so only the
    exit-code/size/detection behavior drives each scenario."""
    fake_binary = tmp_path / "extract-xiso.exe"
    monkeypatch.setattr(extract_xiso_mod, "get_extract_xiso_path", lambda: fake_binary)
    monkeypatch.setattr(extract_xiso_mod, "allowed_browse_roots", lambda: [tmp_path.resolve()])


def _stub_run(returncode: int, stdout: str = "", stderr: str = ""):
    return lambda *a, **kw: SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class TestConvertDvdRipToXisoPreflight:
    def test_unbuilt_binary_raises_before_touching_the_source(self, tmp_path, monkeypatch):
        """get_extract_xiso_path() returns None when the vendored binary was
        never built; that must be the first thing checked."""
        import backend.service.utils.extract_xiso as extract_xiso_mod

        monkeypatch.setattr(extract_xiso_mod, "get_extract_xiso_path", lambda: None)
        calls = []
        monkeypatch.setattr(extract_xiso_mod.subprocess, "run", lambda *a, **kw: calls.append((a, kw)))

        with pytest.raises(FileNotFoundError, match="not built"):
            extract_xiso_mod.convert_dvd_rip_to_xiso(tmp_path / "rip.iso")

        assert calls == []

    def test_nonexistent_source_raises_before_the_allowlist_check(self, tmp_path, monkeypatch):
        """A missing source must report itself as missing, not as an
        allowlist violation, even with an empty allowlist configured."""
        import backend.service.utils.extract_xiso as extract_xiso_mod

        monkeypatch.setattr(
            extract_xiso_mod, "get_extract_xiso_path", lambda: tmp_path / "extract-xiso.exe")
        monkeypatch.setattr(extract_xiso_mod, "allowed_browse_roots", lambda: [])
        calls = []
        monkeypatch.setattr(extract_xiso_mod.subprocess, "run", lambda *a, **kw: calls.append((a, kw)))

        with pytest.raises(FileNotFoundError, match="Source media not found"):
            extract_xiso_mod.convert_dvd_rip_to_xiso(tmp_path / "missing.iso")

        assert calls == []

    def test_source_outside_allowed_roots_raises_before_subprocess(self, tmp_path, monkeypatch):
        import backend.service.utils.extract_xiso as extract_xiso_mod

        fake_binary = tmp_path / "extract-xiso.exe"
        monkeypatch.setattr(extract_xiso_mod, "get_extract_xiso_path", lambda: fake_binary)
        # Empty allowlist: every path is "outside" regardless of where the
        # source actually lives.
        monkeypatch.setattr(extract_xiso_mod, "allowed_browse_roots", lambda: [])

        calls = []
        monkeypatch.setattr(extract_xiso_mod.subprocess, "run", lambda *a, **kw: calls.append((a, kw)))

        source = tmp_path / "rip.iso"
        source.write_bytes(b"\x00" * 2048)

        with pytest.raises(ValueError, match="outside the configured library"):
            extract_xiso_mod.convert_dvd_rip_to_xiso(source)

        assert calls == []


class TestConvertDvdRipToXisoExitZeroReverification:
    def test_exit_zero_but_source_gone_afterward_raises(self, tmp_path, monkeypatch):
        """Existence leg: the rewrite is in place, so the file disappearing
        under a reported success means the only copy of the rip is gone."""
        import backend.service.utils.extract_xiso as extract_xiso_mod
        import backend.service.utils.detection.xbox_image as xbox_image_mod
        _patch_common(monkeypatch, extract_xiso_mod, tmp_path)

        source = tmp_path / "rip.iso"
        source.write_bytes(b"\x00" * 2048)

        detect_calls = []
        monkeypatch.setattr(
            xbox_image_mod, "detect_xbox_image_type",
            lambda path: detect_calls.append(path) or "xiso",
        )

        def _run_and_delete(*a, **kw):
            source.unlink()
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(extract_xiso_mod.subprocess, "run", _run_and_delete)

        with pytest.raises(RuntimeError, match="no longer exists"):
            extract_xiso_mod.convert_dvd_rip_to_xiso(source)

        assert detect_calls == []

    def test_exit_zero_but_implausibly_small_output_raises(self, tmp_path, monkeypatch):
        """Size-floor leg: exit 0 is not enough if the result is truncated."""
        import backend.service.utils.extract_xiso as extract_xiso_mod
        _patch_common(monkeypatch, extract_xiso_mod, tmp_path)

        source = tmp_path / "rip.iso"
        assert extract_xiso_mod._MIN_PLAUSIBLE_XISO_BYTES == 1_048_576
        source.write_bytes(b"\x00" * 2048)  # well below the real constant

        monkeypatch.setattr(extract_xiso_mod.subprocess, "run", _stub_run(0))

        with pytest.raises(RuntimeError, match="implausibly small"):
            extract_xiso_mod.convert_dvd_rip_to_xiso(source)

    def test_exit_zero_plausible_size_but_still_detects_dvd_rip_raises(self, tmp_path, monkeypatch):
        """Detection leg: the exact silent no-op err_iso_no_files produces."""
        import backend.service.utils.extract_xiso as extract_xiso_mod
        import backend.service.utils.detection.xbox_image as xbox_image_mod
        _patch_common(monkeypatch, extract_xiso_mod, tmp_path)

        source = tmp_path / "rip.iso"
        source.write_bytes(b"\x00" * (extract_xiso_mod._MIN_PLAUSIBLE_XISO_BYTES + 1))

        monkeypatch.setattr(extract_xiso_mod.subprocess, "run", _stub_run(0))
        monkeypatch.setattr(xbox_image_mod, "detect_xbox_image_type", lambda path: "dvd_rip")

        with pytest.raises(RuntimeError, match="still detects as a raw Xbox DVD rip"):
            extract_xiso_mod.convert_dvd_rip_to_xiso(source)


class TestConvertDvdRipToXisoNonZeroExit:
    def test_nonzero_exit_raises_with_binary_failure_surfaced_not_reverification(self, tmp_path, monkeypatch):
        """A nonzero exit must raise on the returncode check, before the
        post-success re-verification. The source here would fail the size and
        detection checks too, so the assertion that detect_xbox_image_type was
        never called is what pins the failure to the exit code."""
        import backend.service.utils.extract_xiso as extract_xiso_mod
        import backend.service.utils.detection.xbox_image as xbox_image_mod
        _patch_common(monkeypatch, extract_xiso_mod, tmp_path)

        source = tmp_path / "rip.iso"
        source.write_bytes(b"\x00" * 2048)

        detect_calls = []
        monkeypatch.setattr(
            xbox_image_mod, "detect_xbox_image_type",
            lambda path: detect_calls.append(path) or "dvd_rip",
        )
        monkeypatch.setattr(extract_xiso_mod.subprocess, "run", _stub_run(1, stderr="corrupt sector table"))

        with pytest.raises(RuntimeError, match="corrupt sector table"):
            extract_xiso_mod.convert_dvd_rip_to_xiso(source)

        assert detect_calls == []


class TestConvertDvdRipToXisoHappyPath:
    def test_exit_zero_plausible_size_xiso_detected_returns_source_path(self, tmp_path, monkeypatch):
        import backend.service.utils.extract_xiso as extract_xiso_mod
        import backend.service.utils.detection.xbox_image as xbox_image_mod
        _patch_common(monkeypatch, extract_xiso_mod, tmp_path)

        source = tmp_path / "rip.iso"
        source.write_bytes(b"\x00" * (extract_xiso_mod._MIN_PLAUSIBLE_XISO_BYTES + 1))

        monkeypatch.setattr(extract_xiso_mod.subprocess, "run", _stub_run(0))
        monkeypatch.setattr(xbox_image_mod, "detect_xbox_image_type", lambda path: "xiso")

        result = extract_xiso_mod.convert_dvd_rip_to_xiso(source)

        assert result == source.resolve()


# INTEGRATION TEST NEEDED: the real extract-xiso.exe against a real rip.
# Everything above stubs subprocess.run, so the invocation contract is
# unverified: that cwd pinning puts the rewritten file next to the source
# rather than in the backend's cwd, that the '<name>.old' backup is created
# and left on disk, that a pre-existing '.old' makes extract-xiso refuse and
# surface its own stderr, and that err_iso_no_files really does exit 0.
