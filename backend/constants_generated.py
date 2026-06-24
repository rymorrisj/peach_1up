# Auto-generated from config/constants.yaml — do not edit.
from enum import Enum
from typing import Literal


class Era(Enum):
    DOS = "dos"
    WIN31 = "win31"
    WIN95 = "win95"
    WIN98 = "win98"
    WINXP = "winxp"
    PS1 = "ps1"
    PS2 = "ps2"
    XBOX = "xbox"
    NES = "nes"
    SNES = "snes"
    N64 = "n64"
    DREAMCAST = "dreamcast"
    UNKNOWN = "unknown"


EraValue = Literal["dos", "win31", "win95", "win98", "winxp", "ps1", "ps2", "xbox", "nes", "snes", "n64", "dreamcast", "unknown"]

class BackendSlug(Enum):
    DOSBOX = "dosbox"
    BOX86 = "86box"
    DUCKSTATION = "duckstation"
    PCSX2 = "pcsx2"
    XEMU = "xemu"
    MESEN = "mesen"
    PROJECT64 = "project64"
    FLYCAST = "flycast"


ERA_LABELS: dict[str, str] = {
    "dos": "DOS",
    "win31": "Windows 3.1",
    "win95": "Windows 95",
    "win98": "Windows 98",
    "winxp": "Windows XP",
    "ps1": "PlayStation 1",
    "ps2": "PlayStation 2",
    "xbox": "Original Xbox",
    "nes": "NES",
    "snes": "SNES",
    "n64": "Nintendo 64",
    "dreamcast": "Dreamcast",
    "unknown": "Unknown",
}

BACKEND_LABELS: dict[str, str] = {
    "dosbox": "DOSBox-X",
    "86box": "86Box",
    "duckstation": "DuckStation",
    "pcsx2": "PCSX2",
    "xemu": "xemu",
    "mesen": "Mesen",
    "project64": "Project64",
    "flycast": "Flycast",
}

BACKEND_SYSTEM_LABELS: dict[str, str] = {
    "dosbox": "DOS, Windows 3.1",
    "86box": "Windows 95, 98, XP",
    "duckstation": "PlayStation 1",
    "pcsx2": "PlayStation 2",
    "xemu": "Xbox OG",
    "mesen": "NES",
    "project64": "Nintendo 64",
    "flycast": "Dreamcast",
}

CONTENT_RATINGS: list[dict[str, str]] = [
    {"value": "EC", "label": "EC — Early Childhood"},
    {"value": "E", "label": "E — Everyone"},
    {"value": "E10+", "label": "E10+ — Everyone 10+"},
    {"value": "T", "label": "T — Teen"},
    {"value": "M", "label": "M — Mature"},
    {"value": "AO", "label": "AO — Adults Only"},
    {"value": "PEGI 3", "label": "PEGI 3"},
    {"value": "PEGI 7", "label": "PEGI 7"},
    {"value": "PEGI 12", "label": "PEGI 12"},
    {"value": "PEGI 16", "label": "PEGI 16"},
    {"value": "PEGI 18", "label": "PEGI 18"},
]

DGVOODOO2_SUPPORTED_ERAS: list[str] = [
    "win95",
    "win98",
    "winxp",
]

MediaType = Literal["directory", "iso", "cue", "floppy", "hdd", "exe", "unknown"]

MEDIA_TYPE_LABELS: dict[str, str] = {
    "directory": "Directory",
    "iso": "ISO Image",
    "cue": "CUE/BIN",
    "floppy": "Floppy Image",
    "hdd": "Hard Disk Image",
    "exe": "Executable",
    "unknown": "Unknown",
}

EmulatorCatalogSlug = Literal["86box", "dosbox-x", "duckstation", "flycast", "mesen", "pcsx2", "project64", "xemu"]
