from __future__ import annotations

from pathlib import Path

from utils.constants import Era
from utils.profile import Profile, save


_ERA_HDD_SIZES: dict[Era, int] = {
    Era.DOS:   504 * 1024 * 1024,      # 504 MB — FAT16 safe ceiling for DOS
    Era.WIN31: 1024 * 1024 * 1024,     # 1 GB — Win 3.1 with SVGA
}


def _create_raw_image(dest: Path, size_bytes: int) -> None:
    # sparse on NTFS; zero-filled on other filesystems
    try:
        with dest.open("wb") as fh:
            fh.seek(size_bytes - 1)
            fh.write(b"\x00")
    except OSError as exc:
        raise RuntimeError(
            f"Failed to create HDD image at '{dest}': {exc}"
        ) from exc


def ensure_hdd(profile: Profile, images_dir: Path, profiles_dir: Path) -> Path:
    if profile.era not in _ERA_HDD_SIZES:
        raise ValueError(
            f"Era '{profile.era.value}' is not supported for HDD image creation. "
            f"Supported: {', '.join(e.value for e in _ERA_HDD_SIZES)}"
        )

    # Reuse existing image — never overwrite
    if profile.hdd_image_path != Path("") and profile.hdd_image_path.exists():
        return profile.hdd_image_path

    images_dir.mkdir(parents=True, exist_ok=True)
    dest = images_dir / f"{profile.name}.img"

    # Image already on disk but not recorded in profile — adopt it
    if dest.exists():
        profile.hdd_image_path = dest
        save(profile, profiles_dir)
        return dest

    _create_raw_image(dest, _ERA_HDD_SIZES[profile.era])

    profile.hdd_image_path = dest
    save(profile, profiles_dir)

    return dest
