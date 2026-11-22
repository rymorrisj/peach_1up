"""The only place peach_1up reads formatscout's era or passes one to it.

formatscout still calls the platform "era" (ScanResult.era, classify's era
argument). It will be renamed later; until then every caller goes through
this module and sees only "platform".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MediaDetection:
    platform: str | None
    reason: str
    authoritative: bool = False
    requires_install: bool = False
    warnings: tuple[str, ...] = ()


def from_scan_result(scan) -> MediaDetection:
    """Convert a formatscout ScanResult into a MediaDetection (era to platform)."""
    return MediaDetection(
        platform=scan.era,
        reason=scan.reason,
        authoritative=bool(scan.authoritative),
        requires_install=bool(scan.requires_install),
        warnings=tuple(scan.warnings),
    )


def detect_media(path: Path, dir_cache: dict | None = None) -> MediaDetection:
    import formatscout

    if dir_cache is None:
        return from_scan_result(formatscout.detect(path))
    return from_scan_result(formatscout.detect(path, dir_cache))


def classify_media(path: Path, title: str, platform: str | None):
    """formatscout.classify scoped to *platform*, passed as its era argument."""
    import formatscout

    return formatscout.classify(path, title, platform)
