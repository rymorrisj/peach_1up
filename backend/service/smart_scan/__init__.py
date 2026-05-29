from pathlib import Path

from backend.service.smart_scan import hash_lookup, llm_scan, model
from backend.service.smart_scan.blocklist import score_executable
from backend.service.smart_scan.types import ScanResult
from backend.service.utils.detection.era_detect import detect_era

_INDEX_PATH = Path(__file__).parent / "hash_index.json"
_EXE_EXTENSIONS = frozenset({".exe", ".com", ".bat"})


def _rank_executables(path: Path) -> list[str]:
    """Return candidate executable names sorted by composite score, best first."""
    if path.is_dir():
        ref_stem = path.name.lower()
        root: Path | None = path
    elif path.is_file() and path.suffix.lower() in _EXE_EXTENSIONS:
        ref_stem = path.stem.lower()
        root = None
    else:
        return []

    # (name, base_score, depth_bonus, size_penalty)
    raw: list[tuple[str, float, float, float]] = []

    def _collect(entry: Path, depth: int) -> None:
        if not entry.is_file() or entry.suffix.lower() not in _EXE_EXTENSIONS:
            return
        base = score_executable(entry.stem)
        depth_bonus = 0.3 if depth == 0 else (0.1 if depth == 1 else 0.0)
        try:
            size_penalty = -0.2 if entry.stat().st_size < 10 * 1024 else 0.0
        except OSError:
            size_penalty = 0.0
        raw.append((entry.name, base, depth_bonus, size_penalty))

    if root is None:
        _collect(path, 0)
    else:
        try:
            for entry in root.iterdir():
                if entry.is_file():
                    _collect(entry, 0)
                elif entry.is_dir():
                    try:
                        for sub in entry.iterdir():
                            _collect(sub, 1)
                    except OSError:
                        pass
        except OSError as exc:
            raise OSError(f"Cannot list executables in {path}: {exc}") from exc

    if not raw:
        return []

    bat_only = {Path(n).suffix.lower() for n, *_ in raw} == {".bat"}

    def _title_bonus(stem: str) -> float:
        s = stem.lower()
        return 0.4 if ref_stem and (ref_stem in s or s in ref_stem) else 0.0

    # (final_score, depth_bonus, name)
    scored: list[tuple[float, float, str]] = []
    for name, base, depth_bonus, size_penalty in raw:
        ext = Path(name).suffix.lower()
        title = _title_bonus(Path(name).stem)
        bat_penalty = -0.15 if ext == ".bat" and not bat_only else 0.0
        final = base + depth_bonus + size_penalty + title + bat_penalty
        scored.append((final, depth_bonus, name))

    all_blocked = all(base == 0.0 for _, base, _, _ in raw)
    if all_blocked:
        scored.sort(key=lambda t: t[1], reverse=True)
    else:
        scored.sort(key=lambda t: t[0], reverse=True)

    return [name for _, _, name in scored]


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
