import os
import sys
from pathlib import Path

from backend.service.utils import settings as _settings_module

_initialised = False


def get_base_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def init_settings() -> None:
    global _initialised
    if not _initialised:
        _settings_module.init()
        _initialised = True


def get_settings():
    if not _initialised:
        raise RuntimeError("Settings not initialised — call init_settings() first.")
    return _settings_module
