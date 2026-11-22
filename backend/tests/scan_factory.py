"""Shared builder for real formatscout ScanResult objects in tests.

Hand-rolled stand-ins drift from the real dataclass (missing status, method,
authoritative, ...), so tests build the real thing through make_scan() instead.
"""

from formatscout.result import Method, ScanResult


def make_scan(
    platform: str | None,
    *,
    reason: str = "test reason",
    confidence: float = 0.5,
    authoritative: bool = False,
    method: Method = Method.NONE,
    requires_install: bool = False,
) -> ScanResult:
    """Build a real ScanResult. ScanResult itself rejects contradictory
    combinations (for example authoritative=True with era=None)."""
    return ScanResult(
        title=None, platform=None, era=platform, confidence=confidence, reason=reason,
        requires_install=requires_install, method=method, authoritative=authoritative,
    )


def make_detection(platform: str | None, **kwargs):
    """make_scan() passed through the formatscout boundary adapter, the shape
    peach_1up's ingest code receives."""
    from backend.service.utils.detection.formatscout_adapter import from_scan_result

    return from_scan_result(make_scan(platform, **kwargs))
