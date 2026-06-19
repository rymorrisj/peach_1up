"""Rating detection for library media files.

Checks NFO sidecar files, ISO disc metadata, and the filename stem (in that order)
for ESRB or PEGI rating strings. Returns the first match found, or None.
"""

from __future__ import annotations

import re
from pathlib import Path

# PEGI before ESRB so the longer "PEGI NN" token is matched first.
_PEGI_RE = re.compile(r'\bPEGI\s*(3|7|12|16|18)\b', re.IGNORECASE)
# E10+ before E/M so the longer token wins. AO before M for the same reason.
_ESRB_RE = re.compile(r'\b(E10\+|EC|AO|M|T|E)\b')

# ESRB ratings that are single common letters — high false-positive risk in bare
# filenames, so they are only matched when surrounded by brackets or parentheses.
_ESRB_BRACKETED_RE = re.compile(r'[\(\[](E10\+|EC|AO|M|T|E)[\)\]]')


def _search(text: str, strict: bool = False) -> str | None:
    """Return the first ESRB or PEGI rating found in *text*.

    When *strict* is True (filename mode) single-letter ESRB ratings must
    appear inside brackets or parentheses to avoid false positives.
    """
    m = _PEGI_RE.search(text)
    if m:
        return f"PEGI {m.group(1)}"
    if strict:
        m = _ESRB_BRACKETED_RE.search(text)
    else:
        m = _ESRB_RE.search(text)
    if m:
        return m.group(1).upper()
    return None


def detect_rating(media_path: str) -> str | None:
    """Return the ESRB or PEGI rating string for *media_path*, or None.

    Search order:
    1. Any ``*.nfo`` file in the same directory as the media file.
    2. Primary Volume Descriptor of the file if it is an ISO image.
    3. The filename stem (bracket-guarded to reduce false positives).
    """
    path = Path(media_path)

    # 1. NFO sidecar in the same directory
    try:
        for nfo in path.parent.glob("*.nfo"):
            try:
                text = nfo.read_text(encoding="utf-8", errors="ignore")
                r = _search(text)
                if r:
                    return r
            except OSError:
                continue
    except OSError:
        pass

    # 2. ISO Primary Volume Descriptor (sector 16, 2 KiB)
    if path.suffix.lower() == ".iso":
        try:
            with path.open("rb") as fh:
                fh.seek(16 * 2048)
                data = fh.read(2048)
            text = data.decode("latin-1", errors="ignore")
            r = _search(text)
            if r:
                return r
        except OSError:
            pass

    # 3. Filename stem (strict — brackets/parens required for single-letter ratings)
    return _search(path.stem, strict=True)
