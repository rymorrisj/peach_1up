import locale
import os
from pathlib import Path
from typing import List

from ..constants import Era, ERA_MEDIA_TYPES


def _list_files(path: str) -> List[Path]:
    try:
        if not os.path.exists(path) or not os.path.isdir(path):
            return []

        entries = os.listdir(path)
        files = []

        for entry in entries:
            entry_path = Path(path) / entry
            try:
                if entry_path.is_file():
                    files.append(entry_path)
            except (OSError, PermissionError):
                continue

        files.sort(key=lambda p: locale.strxfrm(p.name))
        return files

    except Exception:
        return []


_BLOCKED_EXTENSIONS = frozenset({".img"})
_BLOCKED_FILENAMES = frozenset({"setup.exe", "setup.bat", "install.exe", "install.bat"})


def get_compatible_media(era: Era, path: str) -> List[Path]:
    all_files = _list_files(path)
    allowed_extensions = ERA_MEDIA_TYPES[era] - _BLOCKED_EXTENSIONS

    compatible_files = []
    for file_path in all_files:
        if file_path.suffix.lower() in allowed_extensions:
            if file_path.name.lower() not in _BLOCKED_FILENAMES:
                compatible_files.append(file_path)

    return compatible_files
