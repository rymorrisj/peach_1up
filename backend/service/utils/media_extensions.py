"""File-extension policy for the archival Media domain and the /media route.

Single source of truth for which extensions may be uploaded as Media, stored
on a MediaItem of a given kind, and served back by GET /media/{path}
(backend/main.py). An uploaded file keeps its extension on disk and is
served from the application's own origin, so an unrestricted extension
(.html, .svg, .xhtml, .js) would let an upload run script in the app's
origin (MED-11).

Extensions are compared lowercased, after safe_basename sanitisation, so
the check applies to the extension that actually lands on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.constants_generated import MediaKind
from backend.service.utils.path_utils import safe_basename

# Raster images a browser may render inline from our origin. MIME types are
# fixed here rather than guessed, because Python's mimetypes reads the
# Windows registry, which can map extensions to unexpected types.
INLINE_IMAGE_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".avif": "image/avif",
}

# Archives are accepted for every kind (a zipped soundtrack, a scan pack).
# They are only ever served as attachments, and only from under MEDIA_PATH:
# elsewhere in the library a .zip/.7z is typically a ROM or BIOS pack.
ARCHIVE_EXTENSIONS: frozenset[str] = frozenset({".zip", ".7z"})

MEDIA_KIND_EXTENSIONS: dict[MediaKind, frozenset[str]] = {
    "image": frozenset(INLINE_IMAGE_TYPES) | {".tif", ".tiff"} | ARCHIVE_EXTENSIONS,
    "audio": frozenset({
        ".mp3", ".flac", ".ogg", ".oga", ".opus", ".wav", ".m4a", ".aac",
        ".aif", ".aiff", ".wma", ".mid", ".midi",
    }) | ARCHIVE_EXTENSIONS,
    "video": frozenset({
        ".mp4", ".m4v", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".mpg", ".mpeg", ".ogv",
    }) | ARCHIVE_EXTENSIONS,
    "text": frozenset({".txt", ".pdf", ".md", ".nfo", ".rtf", ".epub", ".cbz"}) | ARCHIVE_EXTENSIONS,
}

# Any kind: what a Media upload may be before its kind is known.
MEDIA_UPLOAD_EXTENSIONS: frozenset[str] = frozenset().union(*MEDIA_KIND_EXTENSIONS.values())

# What GET /media/{path} will serve at all. Game and App cover art
# (profile_builder._COVER_EXTENSIONS, asset_fetch's sniffed formats) is a
# subset of the inline image set.
SERVABLE_MEDIA_EXTENSIONS: frozenset[str] = MEDIA_UPLOAD_EXTENSIONS


def media_extension(filename: str) -> str:
    """The lowercased extension *filename* would have on disk after
    safe_basename sanitisation, or "" if none survives."""
    return Path(safe_basename(filename)).suffix.lower()


def check_media_extension(filename: str, media_kind: Optional[MediaKind] = None) -> str:
    """Validate *filename*'s on-disk extension against *media_kind*'s
    allowlist, or against every kind's when *media_kind* is None.

    Returns:
        The lowercased extension.

    Raises:
        ValueError: If the extension is missing or not allowed.
    """
    ext = media_extension(filename)
    allowed = MEDIA_KIND_EXTENSIONS[media_kind] if media_kind is not None else MEDIA_UPLOAD_EXTENSIONS
    if not ext or ext not in allowed:
        scope = f"'{media_kind}' media" if media_kind is not None else "media"
        raise ValueError(f"File extension '{ext or '(none)'}' is not allowed for {scope}.")
    return ext
