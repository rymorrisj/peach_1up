"""Profile builder utilities for Peach 1UP.

Constructs Profile instances from scanned media for the library scanner.
"""

from pathlib import Path

from utils.constants import Era
from utils.profile import Profile


def build_profile(media_path: Path, era: Era, name: str) -> Profile:
    """Build a Profile from a media file, era, and proposed name.

    Does not save the profile — caller must call ``utils.profile.save()``
    explicitly and then ``append_history()`` to record the event.

    Args:
        media_path: Absolute path to the game's media file.
        era: Gaming era to assign to this profile.
        name: Sanitised profile name used as the file stem.

    Returns:
        A new unsaved ``Profile`` instance.
    """
    return Profile(
        name=name,
        era=era,
        media_path=media_path,
        notes="",
    )
