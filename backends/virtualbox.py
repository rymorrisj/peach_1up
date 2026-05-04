"""VirtualBox backend for Peach 1UP.

Handles Win95, Win98 (default path), and WinXP launches. Accepts a registered
OSPlatform, loads the era hardware template, registers the VM if not already
present, optionally attaches game media, and launches VirtualBoxVM.exe under
Job Objects.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from subprocess import Popen
from typing import Optional, Tuple

import yaml

from utils.job_objects import launch_under_job_object, WindowsJobObject
from utils.media_attach import build_virtualbox_attachment
from utils.platform import OSPlatform


SUPPORTED_ERAS = {"win95", "win98", "winxp"}

_TEMPLATE_DIR = Path("config") / "templates"


def _vboxmanage_path() -> str:
    """Return the VBoxManage.exe path from VIRTUALBOX_PATH env var.

    Raises:
        RuntimeError: If VIRTUALBOX_PATH is not set.
        FileNotFoundError: If the path does not exist on disk.
    """
    path = os.getenv("VIRTUALBOX_PATH", "")
    if not path:
        raise RuntimeError(
            "VIRTUALBOX_PATH is not set. "
            "Add it to your .env file pointing to VBoxManage.exe."
        )
    if not Path(path).exists():
        raise FileNotFoundError(
            f"VBoxManage.exe not found: {path}. "
            "Download VirtualBox from: https://www.virtualbox.org"
        )
    return path


def _run_vbm(vbm: str, args: list[str], desc: str) -> None:
    """Run a VBoxManage command. Raise RuntimeError on non-zero exit.

    Args:
        vbm: Path to VBoxManage.exe.
        args: Arguments to pass after the executable.
        desc: Short description used in error messages.

    Raises:
        RuntimeError: If VBoxManage exits with a non-zero return code.
    """
    result = subprocess.run([vbm] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"VBoxManage {desc} failed (exit {result.returncode}):\n"
            f"{result.stderr.strip()}"
        )


def load_template(era: str) -> dict:
    """Load the VirtualBox hardware template for the given era.

    Args:
        era: Era string — must be one of ``SUPPORTED_ERAS``.

    Returns:
        Validated template dict.

    Raises:
        FileNotFoundError: If the template file does not exist.
        ValueError: If the file is not a valid YAML mapping.
    """
    template_path = _TEMPLATE_DIR / f"virtualbox_{era}.yaml"
    if not template_path.exists():
        raise FileNotFoundError(
            f"VirtualBox hardware template not found: {template_path}. "
            "Expected a template file per supported era under config/templates/."
        )
    with template_path.open("r", encoding="utf-8") as fh:
        template = yaml.safe_load(fh)
    if not isinstance(template, dict):
        raise ValueError(
            f"VirtualBox template '{template_path.name}' is not a valid YAML mapping."
        )
    return template


def _vm_is_registered(vbm: str, vm_name: str) -> bool:
    """Return True if a VM with the given name is registered in VirtualBox.

    Args:
        vbm: Path to VBoxManage.exe.
        vm_name: VM name to query (the platform_id UUID string).

    Returns:
        True if ``VBoxManage showvminfo`` exits 0, False otherwise.
    """
    result = subprocess.run(
        [vbm, "showvminfo", vm_name, "--machinereadable"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _ensure_registered(vbm: str, platform: OSPlatform, template: dict) -> None:
    """Register and configure a VirtualBox VM for the platform if not yet present.

    Idempotent: returns immediately if the VM is already registered. On first
    call, creates the VM, applies era hardware settings from the template, adds
    SATA (HDD) and IDE (DVD) controllers, and attaches the working image to
    SATA port 0.

    Args:
        vbm: Path to VBoxManage.exe.
        platform: Registered OSPlatform with ``era`` and ``working_image_path`` set.
        template: Era hardware template dict from ``load_template``.

    Raises:
        RuntimeError: If any VBoxManage command fails.
    """
    vm_name = platform.platform_id

    if _vm_is_registered(vbm, vm_name):
        return

    _run_vbm(vbm, [
        "createvm",
        "--name", vm_name,
        "--ostype", template["ostype"],
        "--register",
    ], "createvm")

    _run_vbm(vbm, [
        "modifyvm", vm_name,
        "--memory", str(template["memory_mb"]),
        "--chipset", template["chipset"],
        "--audio-controller", template["audio_controller"],
        "--graphicscontroller", template["graphics_controller"],
        "--vram", str(template["vram_mb"]),
    ], "modifyvm")

    _run_vbm(vbm, [
        "storagectl", vm_name,
        "--name", "SATA",
        "--add", "sata",
        "--controller", "IntelAHCI",
    ], "storagectl SATA")

    _run_vbm(vbm, [
        "storagectl", vm_name,
        "--name", "IDE",
        "--add", "ide",
    ], "storagectl IDE")

    _run_vbm(vbm, [
        "storageattach", vm_name,
        "--storagectl", "SATA",
        "--port", "0",
        "--device", "0",
        "--type", "hdd",
        "--medium", str(platform.working_image_path),
    ], "storageattach HDD")


def _attach_media(vbm: str, attachment: dict) -> None:
    """Attach game media to the VM via VBoxManage storageattach.

    ISO files attach to the IDE controller as a DVD drive (port 1, device 0).
    HDD images attach to the SATA controller at port 1. Replaces any medium
    previously attached at the same location.

    Args:
        vbm: Path to VBoxManage.exe.
        attachment: Descriptor from ``build_virtualbox_attachment`` — must
            contain ``platform_id``, ``controller``, and ``media_path``.

    Raises:
        RuntimeError: If the VBoxManage storageattach command fails.
    """
    vm_name = attachment["platform_id"]
    controller = attachment["controller"]
    media_path = attachment["media_path"]

    if controller == "IDE":
        _run_vbm(vbm, [
            "storageattach", vm_name,
            "--storagectl", "IDE",
            "--port", "1",
            "--device", "0",
            "--type", "dvddrive",
            "--medium", media_path,
        ], "storageattach DVD")
    else:
        _run_vbm(vbm, [
            "storageattach", vm_name,
            "--storagectl", "SATA",
            "--port", "1",
            "--device", "0",
            "--type", "hdd",
            "--medium", media_path,
        ], "storageattach media HDD")


def _virtualboxvm_path(vbm_path: str) -> str:
    """Derive VirtualBoxVM.exe path from the VBoxManage.exe path.

    VirtualBoxVM.exe is the actual VM host process and lives alongside
    VBoxManage.exe in the VirtualBox installation directory. It is launched
    directly (not via VBoxManage startvm) so it can be placed under a Job Object.

    Args:
        vbm_path: Full path to VBoxManage.exe.

    Returns:
        Full path to VirtualBoxVM.exe.

    Raises:
        FileNotFoundError: If VirtualBoxVM.exe is absent from the same directory.
    """
    vboxvm = Path(vbm_path).parent / "VirtualBoxVM.exe"
    if not vboxvm.exists():
        raise FileNotFoundError(
            f"VirtualBoxVM.exe not found at {vboxvm}. "
            "Ensure VirtualBox is correctly installed."
        )
    return str(vboxvm)


def launch(
    platform: OSPlatform,
    media_path: Optional[Path] = None,
) -> Tuple[Popen, WindowsJobObject]:
    """Launch a VirtualBox VM under Job Objects.

    Validates platform state, registers the VM if needed, optionally attaches
    game media, then launches VirtualBoxVM.exe with network blocked and
    resource limits applied.

    Args:
        platform: Registered OSPlatform. ``era`` and ``working_image_path``
            must be set before calling.
        media_path: Optional game media to attach at launch time. ISO files
            attach as DVD; .img/.vhd files attach as a second HDD on SATA port 1.

    Returns:
        ``(process, job_object)`` — the running ``Popen`` and the
        ``WindowsJobObject`` that owns it. Caller must call
        ``job_object.terminate_all()`` when the VM exits.

    Raises:
        ValueError: If the era is unsupported or required platform fields are unset.
        FileNotFoundError: If ``working_image_path``, ``VIRTUALBOX_PATH``,
            ``VirtualBoxVM.exe``, or game media do not exist on disk.
        RuntimeError: If ``VIRTUALBOX_PATH`` env var is unset, any VBoxManage
            command fails, or Job Object launch fails.
    """
    if platform.era not in SUPPORTED_ERAS:
        raise ValueError(
            f"VirtualBox backend does not support era '{platform.era}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_ERAS))}"
        )

    if platform.working_image_path is None:
        raise ValueError(
            f"Platform '{platform.name}' has no working_image_path set. "
            "Complete platform registration (including image copy) before launching."
        )

    if not platform.working_image_path.exists():
        raise FileNotFoundError(
            f"Working image not found: {platform.working_image_path}. "
            "Re-register the platform or restore from base."
        )

    if media_path is not None and not media_path.exists():
        raise FileNotFoundError(f"Game media not found: {media_path}")

    vbm = _vboxmanage_path()
    template = load_template(platform.era)

    _ensure_registered(vbm, platform, template)

    if media_path is not None:
        attachment = build_virtualbox_attachment(media_path, platform.platform_id)
        _attach_media(vbm, attachment)

    vboxvm = _virtualboxvm_path(vbm)

    media_paths = [str(platform.working_image_path)]
    if media_path is not None:
        media_paths.append(str(media_path))

    job_name = f"peach1up_virtualbox_{platform.era}_{platform.platform_id}"

    return launch_under_job_object(
        executable_path=vboxvm,
        args=["--startvm", platform.platform_id],
        media_paths=media_paths,
        era=platform.era,
        job_name=job_name,
    )
