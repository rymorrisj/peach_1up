# Auto-generated from config/constants.yaml — do not edit.
from enum import Enum


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
    N64 = "n64"
    DREAMCAST = "dreamcast"


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
    "n64": "Nintendo 64",
    "dreamcast": "Dreamcast",
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
