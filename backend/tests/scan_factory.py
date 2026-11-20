"""Shared builder for real formatscout ScanResult objects in tests.

Hand-rolled stand-ins drift from the real dataclass (missing status, method,
authoritative, ...), so tests build the real thing through make_scan() instead.
"""

from formatscout.result import Method, ScanResult


def make_scan(
    era: str | None,
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
        title=None, platform=None, era=era, confidence=confidence, reason=reason,
        requires_install=requires_install, method=method, authoritative=authoritative,
    )
