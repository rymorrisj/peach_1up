"""86Box backend for Peach 1UP.

Handles Win95 and Win98 accuracy mode launches. Accepts a resolved LaunchSpec,
loads the era hardware template, validates all identifiers, optionally injects
game media into the config file, and launches 86Box under Job Objects.
"""

from __future__ import annotations

import configparser
import shutil
import threading
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from backend.constants_generated import Era
from backend.core.logger import get_logger
from backend.core.settings import get_base_path
from backend.service.utils.disk_utils import has_valid_mbr
from backend.service.utils.emulator_catalog import (
    get_emulator,
    get_86box_profile,
    get_container_enabled,
    get_container_config as get_emulator_container_config,
    validate_bios_from_descriptor,
)
from backend.service.utils.ini_writer import patch_ini, write_ini
from backend.service.utils.platform.windows.process.launcher import launch_under_job_object
from backend.service.utils.platform.windows.sandbox import BrokerFile
from backend.service.utils.emulator_catalog import get_install_path

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec

logger = get_logger(__name__)

SUPPORTED_ERAS = {Era.WIN95.value, Era.WIN98.value, Era.WINXP.value}


def _ensure_section(parser: configparser.RawConfigParser, section: str) -> None:
    if not parser.has_section(section):
        parser.add_section(section)


def _set_if_absent(parser: configparser.RawConfigParser, section: str, key: str, value: str) -> None:
    if not parser.has_option(section, key) or parser.get(section, key) == "":
        parser.set(section, key, value)


def _prepare_config(
    working_image_path: Path,
    config_path: Path,
    rom_path: Path,
    hardware_profile: str,
    platform_name: str,
    base_image_path: Optional[Path],
) -> None:
    """Patch all required 86Box config keys before every launch.

    Reads the existing config (BOM-tolerant), overwrites only the keys this
    function manages, and writes back without BOM. All other sections and keys
    that 86Box has written are preserved unchanged.

    Idempotent: calling twice with the same inputs produces the same file.

    Args:
        working_image_path: Resolved path to the working disk image.
        config_path: Path to the 86Box config file.
        rom_path: Path to the 86Box ROM pack directory.
        hardware_profile: Profile slug for machine/CPU/GPU selection.
        platform_name: Human-readable platform name for error messages.
        base_image_path: Optional path to a base ISO used for CD-ROM boot.

    Raises:
        FileNotFoundError: If the config file or disk image does not exist.
        OSError: If the disk image cannot be read or the atomic write fails.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"86Box config not found: {config_path}")

    parser = configparser.RawConfigParser()
    parser.optionxform = str
    parser.read(str(config_path), encoding="utf-8-sig")

    try:
        disk_has_mbr = has_valid_mbr(working_image_path)
    except (ValueError, OSError) as exc:
        raise OSError(
            f"Cannot read disk image for platform '{platform_name}': {working_image_path}"
        ) from exc

    _ensure_section(parser, "General")
    parser.set("General", "boot_order", "hdd_cdrom_fdd" if disk_has_mbr else "cdrom_fdd_hdd")

    hw_profile = get_86box_profile(hardware_profile or "standard")
    _ensure_section(parser, "Machine")
    _set_if_absent(parser, "Machine", "machine",         hw_profile["machine"])
    _set_if_absent(parser, "Machine", "cpu_family",      hw_profile["cpu_family"])
    _set_if_absent(parser, "Machine", "cpu_speed",       str(hw_profile["cpu_speed"]))
    _set_if_absent(parser, "Machine", "cpu_multi",       str(hw_profile["cpu_multi"]))
    _set_if_absent(parser, "Machine", "mem_size",        str(hw_profile["mem_size"]))
    _set_if_absent(parser, "Machine", "cpu_use_dynarec", str(hw_profile["cpu_use_dynarec"]))
    _set_if_absent(parser, "Machine", "fpu_type",        hw_profile["fpu_type"])

    _ensure_section(parser, "Video")
    _set_if_absent(parser, "Video", "gfxcard",      hw_profile["gfxcard"])
    _set_if_absent(parser, "Video", "vid_renderer", hw_profile["vid_renderer"])

    _ensure_section(parser, "Sound")
    _set_if_absent(parser, "Sound", "sndcard", hw_profile["sndcard"])

    for _stale in ("Keyboard", "Mouse"):
        if parser.has_section(_stale):
            parser.remove_section(_stale)
    _ensure_section(parser, "Input devices")
    _set_if_absent(parser, "Input devices", "mouse_type",    "ps2")
    _set_if_absent(parser, "Input devices", "keyboard_type", "keyboard_ps2")

    _ensure_section(parser, "Hard disks")
    parser.set("Hard disks", "hdd_01_fn", working_image_path.name)
    parser.set("Hard disks", "hdd_01_ide_channel", "0:0")
    parser.set("Hard disks", "hdd_01_parameters", "63, 16, 4161, 0, ide")
    parser.set("Hard disks", "hdd_01_speed", "ramdisk")

    cdrom_section = "Floppy and CD-ROM drives"
    is_iso = (
        not disk_has_mbr
        and base_image_path is not None
        and base_image_path.suffix.lower() in {".iso", ".cue"}
        and base_image_path.exists()
    )
    if is_iso:
        _ensure_section(parser, cdrom_section)
        iso_fwd = str(base_image_path.resolve()).replace("\\", "/")
        parser.set(cdrom_section, "cdrom_02_image_path", iso_fwd)
        parser.set(cdrom_section, "cdrom_02_parameters", "1, atapi")
        parser.set(cdrom_section, "cdrom_02_ide_channel", "0:1")
    else:
        if parser.has_section(cdrom_section) and parser.has_option(cdrom_section, "cdrom_02_image_path"):
            parser.remove_option(cdrom_section, "cdrom_02_image_path")

    _ensure_section(parser, "Paths")
    parser.set("Paths", "rompath", str(rom_path.resolve()))

    _ensure_section(parser, "Network")
    parser.set("Network", "net_type", "none")

    write_ini(config_path, parser)



def resolve_rom_path(box86_binary: Path) -> Path:
    """Derive the effective ROM path from the 86Box binary location.

    Checks the descriptor's canonical roms/ directory first — the same
    location validate_bios_from_descriptor("86box") gates on — and only
    falls back to scanning for a single versioned roms-* subdirectory
    (e.g. roms-5.3) when roms/ is absent or empty. This keeps the launch
    gate and this resolver agreeing on the same canonical location.

    Raises:
        FileNotFoundError: If neither the canonical roms/ directory nor a
            single unambiguous versioned ROM subdirectory is found.
    """
    base = box86_binary.parent
    canonical = base / "roms"
    try:
        if canonical.is_dir() and any(canonical.iterdir()):
            return canonical
    except OSError as exc:
        raise FileNotFoundError(f"Cannot read 86Box ROM directory: {canonical}") from exc

    try:
        entries = list(base.iterdir())
    except OSError as exc:
        raise FileNotFoundError(f"Cannot read 86Box directory: {base}") from exc

    subdirs = [e for e in entries if e.is_dir()]
    rom_dirs = [e for e in subdirs if e.name.startswith("roms")]
    if len(rom_dirs) == 1:
        return rom_dirs[0]

    try:
        catalog_entry = get_emulator("86box")
        rom_pack_version = catalog_entry.get("rom_pack_version", "")
        rom_pack_url = catalog_entry.get("rom_pack_url", "https://github.com/86Box/roms")
    except Exception:
        rom_pack_version = ""
        rom_pack_url = "https://github.com/86Box/roms"

    expected_name = f"roms-{rom_pack_version}" if rom_pack_version else "roms-<version>"
    expected_path = base / expected_name
    raise FileNotFoundError(
        f"No ROM directory found alongside the 86Box binary at {base}. "
        f"Expected a versioned subdirectory at {expected_path}. "
        f"Download the 86Box ROM pack from: {rom_pack_url}"
    )


def _inject_media(attachment: dict) -> None:
    """Inject a media path into an 86Box config file atomically.

    Args:
        attachment: Dict from ``build_86box_attachment`` — must contain
            ``config_path``, ``section``, ``key``, and ``value``.

    Raises:
        FileNotFoundError: If the config file does not exist.
        OSError: If reading, writing, or the atomic rename fails.
    """
    config_path = Path(attachment["config_path"])
    if not config_path.exists():
        raise FileNotFoundError(
            f"86Box config file not found: {config_path}. "
            "Ensure the platform config_path is set correctly."
        )
    patch_ini(config_path, {attachment["section"]: {attachment["key"]: attachment["value"]}})


def launch(spec: "LaunchSpec") -> tuple:
    """Launch 86Box in accuracy mode under Job Objects.

    Validates platform state and environment, patches the 86Box config for
    this launch, optionally injects game media, then launches 86Box with
    resource limits applied.

    Args:
        spec: LaunchSpec with era, working_image_path, config_path, vm_dir,
            hardware_profile, platform_name, platform_slug, media_path, and
            enable_networking set.

    Raises:
        ValueError: If the era is unsupported or required fields are unset.
        FileNotFoundError: If working_image_path, config_path, or the 86Box
            binary does not exist on disk, or if a required BIOS/ROM pack
            directory declared in 86box.toml is absent or empty.
        RuntimeError: If BOX86_PATH is not configured.
        OSError: If config injection or Job Object launch fails.
    """
    if spec.era not in SUPPORTED_ERAS:
        raise ValueError(
            f"86Box backend does not support era '{spec.era}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_ERAS))}"
        )

    if spec.working_image_path is None:
        raise ValueError(
            f"Platform '{spec.platform_name}' has no working_image_path set. "
            "Complete platform registration (including image copy) before launching."
        )

    if not spec.working_image_path.exists():
        raise ValueError(
            f"Platform '{spec.platform_name}' working_image_path does not exist on disk: "
            f"{spec.working_image_path}. "
            "Re-register the platform to provision a new disk image."
        )
    if spec.working_image_path.suffix.lower() not in {".img", ".vhd"}:
        raise ValueError(
            f"Platform '{spec.platform_name}' working_image_path must be a disk image "
            f"(.img or .vhd), not '{spec.working_image_path.suffix}': {spec.working_image_path}. "
            "working_image_path is set to a config file — re-register the platform."
        )

    if spec.config_path is None:
        raise ValueError(
            f"Platform '{spec.platform_name}' has no config_path set. "
            "Complete platform registration before launching."
        )

    _box86_install = get_install_path("86box")
    box86_path = str(_box86_install) if _box86_install and _box86_install.is_file() else ""
    if not box86_path:
        raise RuntimeError(
            "86Box executable not found. Install it via the Emulators page."
        )
    if not Path(box86_path).exists():
        raise FileNotFoundError(f"86Box executable not found: {box86_path}")

    validate_bios_from_descriptor("86box")

    effective_rom_path = resolve_rom_path(Path(box86_path))

    _prepare_config(
        working_image_path=spec.working_image_path,
        config_path=spec.config_path,
        rom_path=effective_rom_path,
        hardware_profile=spec.hardware_profile,
        platform_name=spec.platform_name or "",
        base_image_path=spec.base_image_path,
    )

    if spec.enable_networking:
        patch_ini(
            spec.config_path,
            {"Network": {"net_type": "slirp"}},
        )

    # dgVoodoo2 DLL injection — Win9x/XP era only, opt-in via profile flag.
    # SECURITY: target directory is validated against the library root before any copy.
    copied_dgvoodoo2_dlls: list[Path] = []
    if spec.enable_dgvoodoo2 and spec.era in {"win95", "win98", "winxp"}:
        if spec.media_path is None:
            raise ValueError(
                "dgVoodoo2 injection requires a media path but none is set on this spec. "
                "Ensure the library item has a valid media path."
            )
        target_dir = spec.media_path.parent.resolve()
        library_root = (get_base_path() / "library").resolve()
        if not (target_dir == library_root or target_dir.is_relative_to(library_root)):
            raise ValueError(
                f"dgVoodoo2 target directory '{target_dir}' resolves outside the library tree. "
                "DLLs can only be copied to a directory within the configured library."
            )
        dgvoodoo2_src = (get_base_path() / "library" / "system" / "tools" / "dgvoodoo2").resolve()
        dll_names = ["d3d8.dll", "d3d9.dll", "DDraw.dll"]
        missing = [n for n in dll_names if not (dgvoodoo2_src / n).exists()]
        if missing:
            raise ValueError(
                "dgVoodoo2 DLLs not found in library/system/tools/dgvoodoo2/. "
                "Place d3d8.dll, d3d9.dll, and DDraw.dll there to use this feature."
            )
        try:
            for dll_name in dll_names:
                dst = target_dir / dll_name
                shutil.copy2(str(dgvoodoo2_src / dll_name), str(dst))
                copied_dgvoodoo2_dlls.append(dst)
        except OSError as exc:
            for p in copied_dgvoodoo2_dlls:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
            raise ValueError(
                f"Failed to copy dgVoodoo2 DLLs to '{target_dir}': {exc}"
            ) from exc

    vm_dir = spec.vm_dir

    args = [
        "--config", str(spec.config_path),
        "--rompath", str(effective_rom_path),
        "--vmpath", str(vm_dir),
    ]

    job_name_prefix = f"Peach1UP_86box_{spec.era}_{spec.platform_slug}"

    catalog_enabled = get_container_enabled("86box")
    container_enabled = spec.container_enabled if spec.container_enabled is not None else catalog_enabled

    if container_enabled:
        sandbox_config = get_emulator_container_config("86box", box86_path)
        if spec.base_image_path is not None:
            sandbox_config.broker_files.append(
                BrokerFile(path=str(spec.base_image_path), access="r", mode="grant"))
    else:
        sandbox_config = None

    try:
        result = launch_under_job_object(
            executable_path=box86_path,
            args=args,
            era=spec.era,
            job_name_prefix=job_name_prefix,
            slug="86box",
            cwd=str(vm_dir),
            container_enabled=container_enabled,
            sandbox_config=sandbox_config,
        )
    except Exception:
        for p in copied_dgvoodoo2_dlls:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    if copied_dgvoodoo2_dlls:
        proc = result[0] if isinstance(result, tuple) else result
        dlls = list(copied_dgvoodoo2_dlls)

        def _cleanup_dgvoodoo2_dlls(p: object, paths: list[Path]) -> None:
            try:
                p.wait()  # type: ignore[union-attr]
            except Exception:
                pass
            for path in paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

        threading.Thread(
            target=_cleanup_dgvoodoo2_dlls,
            args=(proc, dlls),
            daemon=True,
        ).start()

    return result
