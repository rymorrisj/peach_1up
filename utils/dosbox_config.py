from __future__ import annotations

from pathlib import Path

from utils.constants import Era
from utils.profile import Profile, save


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


def _build_conf_content(era: Era) -> str:
    d = _ERA_DEFAULTS[era]
    s = _SOUND_DEFAULTS
    return (
        f"[dosbox]\n"
        f"memsize={d['memsize']}\n"
        f"machine={d['machine']}\n"
        f"\n"
        f"[cpu]\n"
        f"core=auto\n"
        f"cputype=auto\n"
        f"cycles={d['cycles']}\n"
        f"\n"
        f"[mixer]\n"
        f"rate={s['mixer_rate']}\n"
        f"\n"
        f"[sblaster]\n"
        f"sbtype={s['sbtype']}\n"
        f"sbbase={s['sbbase']}\n"
        f"irq={s['irq']}\n"
        f"dma={s['dma']}\n"
        f"hdma={s['hdma']}\n"
        f"oplmode={s['oplmode']}\n"
        f"oplrate={s['oplrate']}\n"
        f"\n"
        f"[autoexec]\n"
    )


def generate_conf(profile: Profile, conf_dir: Path, profiles_dir: Path) -> Path:
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
