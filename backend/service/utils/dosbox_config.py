from __future__ import annotations

import os
from pathlib import Path

from backend.constants_generated import Era
from backend.service.utils.profile import Profile, save

# Per-era DOSBox-X hardware defaults. memsize is in MB; machine selects the
# emulated video card; cycles controls CPU speed ("auto" lets DOSBox-X guess).
_ERA_DEFAULTS = {
    Era.DOS: {
        "memsize": 16,
        "machine": "vga",
        "cycles": "auto",
        "core": "normal",
    },
    Era.WIN31: {
        "memsize": 64,
        "machine": "svga_s3",
        "cycles": "auto",
        "core": "auto",
    },
}

# Sound Blaster 16 defaults shared across all eras. These match the most
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


def get_shared_dosbox_conf_dir() -> Path:
    """Return the shared directory used for generated DOSBox-X conf files.

    On Windows, conf files are written to a machine-wide directory under
    ``%ProgramData%`` so the low-privilege ``peach_sandbox`` account can read
    them once setup has granted ACLs on that directory tree. This avoids
    writing launch confs into user-private project or temp directories that
    the sandbox account cannot access.

    On non-Windows platforms, use a standard per-user data directory under the
    current user's home directory.

    Returns:
        Path to the directory that should contain generated DOSBox-X conf files.
    """
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Peach1Up" / "temp"
    return Path.home() / ".local" / "share" / "peach1up" / "temp"


def get_profile_conf_path(profile: Profile) -> Path:
    """Return the canonical conf path for a profile.

    Each profile is assigned a stable conf filename in the shared DOSBox-X
    conf directory. Using a deterministic path makes it easy to regenerate
    the conf on every launch and migrate older profiles away from inaccessible
    directories.

    Args:
        profile: The profile whose DOSBox-X conf path should be derived.

    Returns:
        Path to the profile's canonical ``.conf`` file.
    """
    return get_shared_dosbox_conf_dir() / f"{profile.name}.conf"


def build_conf_content(era: Era, autoexec_lines: list[str] | None = None) -> str:
    """Build the DOSBox-X configuration text for a supported era.

    The generated config contains the core DOSBox-X sections needed by Peach
    1UP plus an ``[autoexec]`` section that can be populated with mount and
    launch commands.

    Args:
        era: Supported DOSBox-X era.
        autoexec_lines: Optional lines to append under ``[autoexec]``.

    Returns:
        Complete DOSBox-X config text ending with a trailing newline.

    Raises:
        ValueError: If the era is not supported by DOSBox-X config generation.
    """
    if era not in _ERA_DEFAULTS:
        raise ValueError(
            f"Era '{era.value}' is not supported by DOSBox-X config generation. "
            f"Supported: {', '.join(e.value for e in _ERA_DEFAULTS)}"
        )

    era_defaults = _ERA_DEFAULTS[era]
    sound_defaults = _SOUND_DEFAULTS

    lines = [
        "[dosbox]",
        f"memsize={era_defaults['memsize']}",
        f"machine={era_defaults['machine']}",
        "",
        "[cpu]",
        f"core={era_defaults['core']}",
        "cputype=auto",
        f"cycles={era_defaults['cycles']}",
        "",
        "[mixer]",
        f"rate={sound_defaults['mixer_rate']}",
        "",
        "[sblaster]",
        f"sbtype={sound_defaults['sbtype']}",
        f"sbbase={sound_defaults['sbbase']}",
        f"irq={sound_defaults['irq']}",
        f"dma={sound_defaults['dma']}",
        f"hdma={sound_defaults['hdma']}",
        f"oplmode={sound_defaults['oplmode']}",
        f"oplrate={sound_defaults['oplrate']}",
        "",
        "[dos]",
        "automount=false",
        "mountwarning=false",
        "",
        "[autoexec]",
    ]

    if autoexec_lines:
        lines.extend(autoexec_lines)

    return "\n".join(lines) + "\n"


def write_launch_conf(
    dest: Path,
    era: Era,
    autoexec_lines: list[str] | None = None,
) -> Path:
    """Write a DOSBox-X launch conf to ``dest``.

    The parent directory is created automatically. This helper performs only
    the file write; callers are responsible for choosing an appropriate
    destination, typically under ``get_shared_dosbox_conf_dir()``.

    Args:
        dest: Full path to the conf file to write.
        era: Supported DOSBox-X era.
        autoexec_lines: Optional lines to append under ``[autoexec]``.

    Returns:
        The written conf path.

    Raises:
        ValueError: If the era is not supported by DOSBox-X config generation.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(build_conf_content(era, autoexec_lines), encoding="utf-8")
    return dest


# NAMING: generate_conf creates the conf file and records its path in the profile
# (first-time setup); regenerate_conf overwrites the file at the already-recorded
# path (subsequent launches). The re- prefix alone does not make this distinction
# obvious — consider create_conf / rewrite_conf at the next refactor pass.
def regenerate_conf(
    profile: Profile,
    autoexec_lines: list[str] | None = None,
    profiles_dir: Path | None = None,
) -> None:
    """Overwrite the profile's conf file in the shared DOSBox-X conf directory.

    Used on every launch after the first to refresh the ``[autoexec]`` section
    (for example, updated mount commands) without relying on an older stored
    path that may point to a user-private or otherwise inaccessible directory.

    If the profile currently points somewhere else, its conf path is migrated
    to the canonical shared location. When ``profiles_dir`` is provided, the
    updated profile is saved immediately after migration.

    Args:
        profile: The game profile whose conf file to overwrite.
        autoexec_lines: Lines to write into the ``[autoexec]`` section.
            Pass ``None`` to produce an empty section.
        profiles_dir: Optional directory in which to persist the migrated
            profile path after updating ``profile.dosbox_conf_path``.

    Raises:
        ValueError: If the era is not supported by DOSBox-X config generation.
    """
    if profile.era not in _ERA_DEFAULTS:
        raise ValueError(
            f"Era '{profile.era.value}' is not supported by DOSBox-X config generation. "
            f"Supported: {', '.join(e.value for e in _ERA_DEFAULTS)}"
        )

    dest = get_profile_conf_path(profile)

    if profile.dosbox_conf_path != dest:
        profile.dosbox_conf_path = dest
        if profiles_dir is not None:
            save(profile, profiles_dir)

    write_launch_conf(dest, profile.era, autoexec_lines)


def generate_conf(
    profile: Profile,
    conf_dir: Path | None,
    profiles_dir: Path,
) -> Path:
    """Create a new conf file for the profile, record its path, and save it.

    New conf files are written to the shared DOSBox-X conf directory so they
    can be read by the low-privilege ``peach_sandbox`` account during launch.
    The ``conf_dir`` parameter is accepted for backwards-compatible call-site
    symmetry but is no longer used as the primary destination.

    Args:
        profile: The game profile for which to generate a conf file.
        conf_dir: Unused legacy parameter retained for compatibility.
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

    dest = get_profile_conf_path(profile)
    write_launch_conf(dest, profile.era)
    profile.dosbox_conf_path = dest
    save(profile, profiles_dir)
    return dest