from pathlib import Path

from ..result import ScanResult


def validate(path: Path) -> ScanResult | None:
    raise NotImplementedError
