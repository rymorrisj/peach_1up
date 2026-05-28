BLOCK_PREFIXES: tuple[str, ...] = (
    "inst",
    "setup",
    "setp",
    "set_",
    "instal",
    "arcinst",
    "uninst",
    "unstall",
    "unwise",
)

BLOCK_EXACT: frozenset[str] = frozenset({
    "deice",
    "pkunzip",
    "pkzip",
    "lzma",
    "expand",
    "mscdex",
    "smartdrv",
    "readme",
    "unwise",
    "uninst",
    "arj",
    "pkware",
    "lha",
    "zoo",
    "arc",
})

BLOCK_SUFFIXES: tuple[str, ...] = (
    "_ins",
    "_set",
    "_inst",
)


def score_executable(stem: str) -> float:
    """Return 0.0 if the stem matches any block rule, 1.0 otherwise."""
    lower = stem.lower()
    if lower in BLOCK_EXACT:
        return 0.0
    if lower.startswith(BLOCK_PREFIXES):
        return 0.0
    if lower.endswith(BLOCK_SUFFIXES):
        return 0.0
    return 1.0


def is_blocked(stem: str) -> bool:
    return score_executable(stem) == 0.0
