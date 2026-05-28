from pathlib import Path

from backend.service.smart_scan.types import ScanResult


def detect(path: Path, api_key: str = "") -> ScanResult | None:
    # PSS-6: LLM-assisted scan — not yet implemented
    return None
