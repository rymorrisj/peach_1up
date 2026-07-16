"""Domain dispatch registry for chunked uploads.

Each upload domain (software_games, software_media, software_apps) owns its
own finalize logic (how a reassembled upload becomes DB rows, or in
software_media's case, deliberately does not, see that module) and registers
itself here as one UploadDomain entry. The route layer (api/routes/uploads.py)
is entirely generic: it looks up a domain by name and calls back into
whichever functions that domain registered.

Registration is an explicit call from backend.core.lifespan at startup, not an
import-time decorator side effect, so a missing registration is easy to spot
during startup instead of depending on which module happened to be imported
first.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

FinalizeInline = Callable[[str, Path, Session], dict]
FinalizeBackground = Callable[[str, str, str], None]  # (upload_id, media_root_str, job_id)


@dataclass(frozen=True)
class UploadDomain:
    name: str  # "software_games" | "software_media" | "software_apps"
    permission_flag: str  # e.g. "can_manage_game"
    allowed_kinds: frozenset[str]  # subset of {"file", "folder", "set"}
    root_resolver: Callable[[], Path]
    finalize_inline: FinalizeInline
    finalize_background: FinalizeBackground


_domains: dict[str, UploadDomain] = {}


def register_domain(domain: UploadDomain) -> None:
    # Idempotent by design, not a strict once-only guard: backend.main.app's
    # lifespan (and therefore _register_upload_domains()) runs once per
    # ``with TestClient(app)`` entry, and many existing tests construct a
    # fresh TestClient per test function against the same module-level app,
    # so this runs many times within one pytest process. Re-registering the
    # same static config is harmless; only overwrite, never raise.
    _domains[domain.name] = domain


def get_domain(name: str) -> UploadDomain:
    try:
        return _domains[name]
    except KeyError:
        raise KeyError(f"Unknown upload domain '{name}'.") from None


def registered_domains() -> list[str]:
    return list(_domains)
