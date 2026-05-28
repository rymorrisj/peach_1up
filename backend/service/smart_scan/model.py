from pathlib import Path

from backend.service.smart_scan.types import ScanResult


def detect(path: Path) -> ScanResult | None:
    # PSS-3: trained decision tree — not yet implemented
    return None
