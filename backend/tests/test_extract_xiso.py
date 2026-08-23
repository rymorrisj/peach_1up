"""Tests for backend/service/utils/extract_xiso.py's convert_dvd_rip_to_xiso.

The module's own docstring states the guarantee under test: extract-xiso can
report success (exit 0) without having actually rewritten anything (its own
err_iso_no_files case resets the exit code to 0 internally), so exit 0 is
never trusted on its own. After a 0 exit, the result is re-inspected: the
file must still exist, be a plausible size, and no longer detect as
dvd_rip. Each test below that locks in one leg of that re-verification says
so.

No real subprocess is ever spawned: subprocess.run is monkeypatched to
return a stubbed result in every test. detect_xbox_image_type is
monkeypatched the same way test_xbox_image.py's own tests stub detection,
except at its real import site (backend.service.utils.detection.xbox_image),
since convert_dvd_rip_to_xiso imports it locally inside the function body,
not at extract_xiso module level.
"""

from types import SimpleNamespace

import pytest


def _patch_common(monkeypatch, extract_xiso_mod, tmp_path):
    """Bypass the binary-existence check and allowlist against a fake path
    and tmp_path itself, so only the exit-code/size/detection behavior under
    test drives each scenario."""
    fake_binary = tmp_path / "extract-xiso.exe"
    monkeypatch.setattr(extract_xiso_mod, "get_extract_xiso_path", lambda: fake_binary)
    monkeypatch.setattr(extract_xiso_mod, "allowed_browse_roots", lambda: [tmp_path.resolve()])


def _stub_run(returncode: int, stdout: str = "", stderr: str = ""):
    return lambda *a, **kw: SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class TestConvertDvdRipToXisoAllowlist:
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
    def test_exit_zero_but_implausibly_small_output_raises(self, tmp_path, monkeypatch):
        """Locks in the size-floor leg of the re-verification: exit 0 alone
        is not enough if the file is implausibly small afterward."""
        import backend.service.utils.extract_xiso as extract_xiso_mod
        _patch_common(monkeypatch, extract_xiso_mod, tmp_path)

        source = tmp_path / "rip.iso"
        assert extract_xiso_mod._MIN_PLAUSIBLE_XISO_BYTES == 1_048_576
        source.write_bytes(b"\x00" * 2048)  # well below the real constant

        monkeypatch.setattr(extract_xiso_mod.subprocess, "run", _stub_run(0))

        with pytest.raises(RuntimeError, match="implausibly small"):
            extract_xiso_mod.convert_dvd_rip_to_xiso(source)

    def test_exit_zero_plausible_size_but_still_detects_dvd_rip_raises(self, tmp_path, monkeypatch):
        """Locks in the detection leg: a plausible size is not enough either
        if the rewritten file still detects as a raw DVD rip."""
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
        """A nonzero exit must raise on the returncode check itself, before
        ever reaching the post-success re-verification, confirmed here by a
        source that would ALSO fail the size and detection checks (small,
        still dvd_rip) but whose failure is attributable only to the exit
        code: detect_xbox_image_type is never even called."""
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
