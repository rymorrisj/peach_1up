"""Tests for the formatscout boundary adapter
(backend/service/utils/detection/formatscout_adapter.py), the one place
formatscout's era becomes peach_1up's platform."""

from pathlib import Path
from types import SimpleNamespace

from formatscout.result import Method, ScanResult

from backend.service.utils.detection import formatscout_adapter as adapter
from backend.tests.scan_factory import make_scan


def test_from_scan_result_maps_era_to_platform():
    scan = make_scan("ps2", reason="SYSTEM.CNF", authoritative=True, method=Method.MAGIC, requires_install=False)

    detection = adapter.from_scan_result(scan)

    assert detection.platform == "ps2"
    assert detection.reason == "SYSTEM.CNF"
    assert detection.authoritative is True
    assert detection.requires_install is False


def test_from_scan_result_ignores_formatscouts_display_platform_label():
    scan = ScanResult(title=None, platform="Nintendo DS", era=None, confidence=0.0, reason="", warnings=["w"])

    detection = adapter.from_scan_result(scan)

    assert detection.platform is None
    assert detection.warnings == ("w",)


def test_detect_media_calls_formatscout_detect_at_call_time(monkeypatch):
    import formatscout

    calls = []

    def fake_detect(path):
        calls.append(path)
        return make_scan("dos", reason="exe header", method=Method.PE_HEADER)

    monkeypatch.setattr(formatscout, "detect", fake_detect)

    detection = adapter.detect_media(Path("/library/games/dos/doom/DOOM.EXE"))

    assert calls == [Path("/library/games/dos/doom/DOOM.EXE")]
    assert detection.platform == "dos"


def test_detect_media_passes_dir_cache_through(monkeypatch):
    import formatscout

    seen = {}

    def fake_detect(path, dir_cache):
        seen["dir_cache"] = dir_cache
        return make_scan(None)

    monkeypatch.setattr(formatscout, "detect", fake_detect)
    cache: dict = {}

    assert adapter.detect_media(Path("/x.bin"), cache).platform is None
    assert seen["dir_cache"] is cache


def test_classify_media_passes_platform_as_formatscouts_era(monkeypatch):
    import formatscout

    seen = {}

    def fake_classify(path, title, era):
        seen.update(path=path, title=title, era=era)
        return SimpleNamespace(status="verified", similarity=None, computed_sha1="abc")

    monkeypatch.setattr(formatscout, "classify", fake_classify)

    result = adapter.classify_media(Path("/ico.chd"), "Ico", "ps2")

    assert seen == {"path": Path("/ico.chd"), "title": "Ico", "era": "ps2"}
    assert result.status == "verified"
