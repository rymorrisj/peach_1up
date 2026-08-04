"""Core settings façade.

This module's import of backend.service.utils.settings is a deliberate
downward dependency (façade over the lower-level settings module), not a
layering accident — the import is deferred into the functions below because
service.utils.settings calls back into get_base_path(), and a top-level
import here would create a circular import depending on which module loads
first.
"""

import sys
from pathlib import Path

_initialised = False


def get_base_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def get_db_path() -> Path:
    """Single source of truth for the SQLite file location, used by
    backend.core.database to build its engine."""
    return get_base_path() / "database" / "data" / "peach1up.db"


def init_settings() -> None:
    global _initialised
    if not _initialised:
        from backend.service.utils import settings as _settings_module
        _settings_module.init()
        _initialised = True


def get_settings():
    if not _initialised:
        raise RuntimeError("Settings not initialised — call init_settings() first.")
    from backend.service.utils import settings as _settings_module
    return _settings_module
