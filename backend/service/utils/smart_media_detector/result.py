from dataclasses import dataclass, field
from typing import Literal


@dataclass(slots=True)
class ScanResult:
    title: str | None
    platform: str | None
    era: str | None
    confidence: float
    reason: str
    requires_install: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VerifyResult:
    """Result of verify(), a hash-only re-check of a single file, distinct
    from ScanResult, which is detect()'s full-pipeline identification result.

    status:
        "matched", computed sha1 is present in the hash index and equals
            expected_sha1.
        "mismatched", computed sha1 is present in the hash index but does
            not equal expected_sha1 (the file changed since it was recorded).
        "not_in_index", computed sha1 is not present in the hash index at
            all, regardless of expected_sha1.
    """
    status: Literal["matched", "mismatched", "not_in_index"]
    computed_sha1: str
    expected_sha1: str
    reason: str


@dataclass(slots=True)
class ClassifyResult:
    """Five-state verification classification for a single file, combining
    exact hash-tier lookup (sha1/md5/crc32) with a fuzzy title-match fallback.
    Unlike verify(), this needs no prior expected_sha1, it establishes a
    classification from scratch, used both at ingest and on a manual re-check.

    status:
        "verified", sha1 (or, for a CHD container, its embedded rawsha1)
            exactly matches a hash_index.json entry. Highest confidence, the
            only state that should ever read as a positive confirmation.
        "caution", no sha1 match, but md5 or crc32 exactly matches an entry.
            Real index coverage, weaker confidence than a sha1 hit.
        "suspect", no hash of any kind matched, but the title is an
            approximate (>=threshold) match for a title that does exist in
            hash_index.json. The only state that warns of a possibly bad
            file. Deliberately conservative, an ambiguous or below-threshold
            title match never produces this state, it falls through to
            "not_in_index" instead. A false "suspect" must never fire.
        "not_in_index", no hash matched and no confident title match either.
            Neutral, "we have no data on this file", not a warning.
        "unchecked", the file could not be hashed at all (missing, unreadable,
            permission error). No classification was possible.

    computed_sha1 is the file's own raw sha1 (hash_file()'s result), persisted
    whenever hashing succeeds, regardless of which status was reached. It is
    None only for "unchecked". This is not the embedded CHD rawsha1 used
    internally for the verified-tier lookup, a caller needing that value
    should use validators.chd_validator.extract_embedded_sha1 directly.

    matched_title/similarity are populated only for "suspect": the specific
    index title the fuzzy match landed on and its similarity ratio, useful
    for logging, not required for handling the status itself.
    """
    status: Literal["verified", "caution", "suspect", "not_in_index", "unchecked"]
    computed_sha1: str | None
    matched_title: str | None
    similarity: float | None
    reason: str
