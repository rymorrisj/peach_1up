from pathlib import Path

from backend.service.smart_scan import hash_lookup, llm_scan, model
from backend.service.smart_scan.blocklist import score_executable
from backend.service.smart_scan.types import ScanResult
from backend.service.utils.era_detect import detect_era

_INDEX_PATH = Path(__file__).parent / "hash_index.json"
_EXE_EXTENSIONS = frozenset({".exe", ".com", ".bat"})


def _rank_executables(path: Path) -> list[str]:
    """Return candidate executable names sorted by score: 1.0 first, 0.0 last."""
    candidates: list[tuple[float, str]] = []

    if path.is_dir():
        try:
            for entry in path.iterdir():
                if entry.is_file() and entry.suffix.lower() in _EXE_EXTENSIONS:
                    score = score_executable(entry.stem)
                    candidates.append((score, entry.name))
        except OSError as exc:
            raise OSError(f"Cannot list executables in {path}: {exc}") from exc
    elif path.is_file() and path.suffix.lower() in _EXE_EXTENSIONS:
        score = score_executable(path.stem)
        candidates.append((score, path.name))

    candidates.sort(key=lambda t: t[0], reverse=True)
    return [name for _, name in candidates]


def detect(path: Path) -> ScanResult:
    index = hash_lookup.load_index(_INDEX_PATH)

    result = hash_lookup.lookup(path, index)
    if result is not None:
        return result

    result = model.detect(path)
    if result is not None:
        return result

    era_slug, reason = detect_era(path)
    if era_slug is not None:
        return ScanResult(
            title=None,
            platform=None,
            era=era_slug,
            confidence=0.5,
            reason=f"heuristic: {reason}",
            executable_hints=_rank_executables(path),
        )

    result = llm_scan.detect(path)
    if result is not None:
        return result

    return ScanResult(
        title=None,
        platform=None,
        era=None,
        confidence=0.0,
        reason="no signal found",
        executable_hints=_rank_executables(path),
    )
