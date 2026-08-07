"""Flycast backend for Peach 1UP.

Handles Dreamcast emulation via Flycast.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Tuple

from backend.constants_generated import Era
from backend.service.utils.emulator_catalog import (
    resolve_container_enabled,
    build_media_broker_config,
    validate_bios_from_descriptor,
)
from backend.service.utils.file_types import supported_extensions_for_era
from backend.service.utils.ini_writer import set_ini_key
from backend.service.utils.platform.windows.process.launcher import launch_under_job_object
from sandbox.sandbox_process import SandboxProcess
from sandbox.job import WindowsJobObject

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec

SUPPORTED_ERAS = {Era.DREAMCAST.value}
# eras.yaml is the same source scan/upload/directory-resolution already use
# (file_types.py), rather than the separate constants.py dict this backend
# used to read its own launch-time check from.
SUPPORTED_MEDIA = frozenset(supported_extensions_for_era(Era.DREAMCAST.value))


def launch(spec: "LaunchSpec") -> Tuple[SandboxProcess, WindowsJobObject]:
    """Launch Flycast with the given Dreamcast media under Job Object isolation.

    Args:
        spec: LaunchSpec with slug, era, media_path, executable_path set.
            enable_networking gates Dreamcast/NAOMI netplay: when False the
            emu.cfg [network] Enable and GGPO keys are forced to ``no``; when
            True the emulator default is used.

    Returns:
        Tuple of ``(process, job_object)``.

    Raises:
        FileNotFoundError: If the executable or media path does not exist.
        ValueError: If the era or media format is unsupported.
        FileNotFoundError: If BIOS directory declared in flycast.toml is absent or empty.
    """
    if spec.era not in SUPPORTED_ERAS:
        raise ValueError(
            f"Flycast backend does not support era '{spec.era}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_ERAS))}"
        )

    if not spec.executable_path or not Path(spec.executable_path).exists():
        raise FileNotFoundError(f"Flycast executable not found: {spec.executable_path}")

    validate_bios_from_descriptor("flycast")

    if spec.media_path is None or not spec.media_path.exists():
        raise FileNotFoundError(f"Media file not found: {spec.media_path}")

    if spec.media_path.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(
            f"Unsupported media format '{spec.media_path.suffix}'. "
            f"Flycast supports: {', '.join(sorted(SUPPORTED_MEDIA))}"
        )

    emu_cfg = Path(spec.executable_path).parent / "emu.cfg"
    set_ini_key(emu_cfg, "config", "Dreamcast.ContentPath", str(spec.media_path.parent))
    if not spec.enable_networking:
        # Dreamcast/NAOMI netplay: disable both the network stack and GGPO
        # rollback netplay unless the profile explicitly opts in.
        set_ini_key(emu_cfg, "network", "Enable", "no")
        set_ini_key(emu_cfg, "network", "GGPO", "no")

    args: list[str] = [str(spec.media_path.resolve())]
    job_name_prefix = f"Peach1UP_flycast_{spec.era}_{spec.media_path.stem}"

    container_enabled = resolve_container_enabled("flycast", spec.container_enabled)
    sandbox_config = build_media_broker_config(
        "flycast", spec.executable_path, spec.media_path, spec.user_item_id, container_enabled)

    return launch_under_job_object(
        executable_path=spec.executable_path,
        args=args,
        era=spec.era,
        job_name_prefix=job_name_prefix,
        slug="flycast",
        cwd=str(Path(spec.executable_path).parent),
        container_enabled=container_enabled,
        sandbox_config=sandbox_config,
    )
