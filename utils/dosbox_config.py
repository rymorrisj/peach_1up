from __future__ import annotations

from pathlib import Path

from utils.constants import Era
from utils.profile import Profile, save


# Per-era DOSBox-X hardware defaults.  memsize is in MB; machine selects the
# emulated video card; cycles controls CPU speed ("auto" lets DOSBox-X guess).
_ERA_DEFAULTS = {
    Era.DOS: {
        "memsize": 16,
        "machine": "vga",
        "cycles": "auto",
    },
    Era.WIN31: {
        "memsize": 64,
        "machine": "svga_s3",
        "cycles": "auto",
    },
}

# Sound Blaster 16 defaults shared across all eras.  These match the most
# common SB16 hardware configuration and are recognised by the majority of
# DOS-era games without manual IRQ/DMA setup.
_SOUND_DEFAULTS = {
    "sbtype": "sb16",
    "sbbase": 220,
    "irq": 7,
    "dma": 1,
    "hdma": 5,
    "oplmode": "auto",
    "oplrate": 44100,
    "mixer_rate": 44100,
}


def _build_conf_content(era: Era, autoexec_lines: list[str] | None = None) -> str:
    era_defaults = _ERA_DEFAULTS[era]
    sound_defaults = _SOUND_DEFAULTS
    body = (
        f"[dosbox]\n"
        f"memsize={era_defaults['memsize']}\n"
        f"machine={era_defaults['machine']}\n"
        f"\n"
        f"[cpu]\n"
        f"core=auto\n"
        f"cputype=auto\n"
        f"cycles={era_defaults['cycles']}\n"
        f"\n"
        f"[mixer]\n"
        f"rate={sound_defaults['mixer_rate']}\n"
        f"\n"
        f"[sblaster]\n"
        f"sbtype={sound_defaults['sbtype']}\n"
        f"sbbase={sound_defaults['sbbase']}\n"
        f"irq={sound_defaults['irq']}\n"
        f"dma={sound_defaults['dma']}\n"
        f"hdma={sound_defaults['hdma']}\n"
        f"oplmode={sound_defaults['oplmode']}\n"
        f"oplrate={sound_defaults['oplrate']}\n"
        f"\n"
        f"[dos]\n"
        f"automount=false\n"
        f"mountwarning=false\n"
        f"\n"
        f"[autoexec]\n"
    )
    if autoexec_lines:
        body += "\n".join(autoexec_lines) + "\n"
    return body


# NAMING: generate_conf creates the conf file and records its path in the profile
# (first-time setup); regenerate_conf overwrites the file at the already-recorded
# path (subsequent launches).  The re- prefix alone does not make this distinction
# obvious — consider create_conf / rewrite_conf at the next refactor pass.

def regenerate_conf(
    profile: Profile,
    autoexec_lines: list[str] | None = None,
) -> None:
    """Overwrite the conf file at the path already stored in the profile.

    Used on every launch after the first to refresh the ``[autoexec]`` section
    (e.g. updated mount commands) without changing the recorded path.
    ``profile.dosbox_conf_path`` must already point to a valid location;
    use ``generate_conf`` for first-time setup.

    Args:
        profile: The game profile whose conf file to overwrite.
        autoexec_lines: Lines to write into the ``[autoexec]`` section.
            Pass ``None`` to produce an empty section.

    Raises:
        ValueError: If the era is not supported by DOSBox-X config generation.
    """
    if profile.era not in _ERA_DEFAULTS:
        raise ValueError(
            f"Era '{profile.era.value}' is not supported by DOSBox-X config generation. "
            f"Supported: {', '.join(e.value for e in _ERA_DEFAULTS)}"
        )
    dest = profile.dosbox_conf_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_build_conf_content(profile.era, autoexec_lines), encoding="utf-8")


def generate_conf(profile: Profile, conf_dir: Path, profiles_dir: Path) -> Path:
    """Create a new conf file for the profile, record its path, and save the profile.

    Used during first-time profile setup.  Writes the conf to
    ``<conf_dir>/<profile.name>.conf``, stores the path in
    ``profile.dosbox_conf_path``, and persists the profile to disk.  On
    subsequent launches use ``regenerate_conf``, which overwrites the file at
    the path already recorded in the profile without changing it.

    Args:
        profile: The game profile for which to generate a conf file.
        conf_dir: Directory in which to write the ``.conf`` file.
        profiles_dir: Directory in which to save the updated profile ``.yaml``.

    Returns:
        Path to the newly created ``.conf`` file.

    Raises:
        ValueError: If the era is not supported by DOSBox-X config generation.
    """
    if profile.era not in _ERA_DEFAULTS:
        raise ValueError(
            f"Era '{profile.era.value}' is not supported by DOSBox-X config generation. "
            f"Supported: {', '.join(e.value for e in _ERA_DEFAULTS)}"
        )

    conf_dir.mkdir(parents=True, exist_ok=True)
    dest = conf_dir / f"{profile.name}.conf"
    dest.write_text(_build_conf_content(profile.era), encoding="utf-8")

    profile.dosbox_conf_path = dest
    save(profile, profiles_dir)

    return dest
