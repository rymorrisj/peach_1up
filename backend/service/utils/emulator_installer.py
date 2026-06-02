import glob as _glob
import shutil
import subprocess
import sys
from pathlib import Path

from backend.core.settings import get_base_path
from backend.service.utils.emulator_catalog import get_emulator

_BASE_DIR = get_base_path() / "emulators"


def detect_binary(slug: str) -> Path | None:
    entry = get_emulator(slug)
    install_type = entry.get("install_type", "zip")
    binary = entry.get("binary", "")

    if not binary:
        return None

    if install_type == "zip":
        slug_dir = (_BASE_DIR / slug).resolve()
        path = (slug_dir / binary).resolve()
        try:
            path.relative_to(slug_dir)
        except ValueError:
            return None
        return path if path.exists() else None

    if install_type == "installer":
        matches = _glob.glob(binary)
        return Path(matches[0]) if matches else None

    if install_type == "rom_pack":
        pack_dir = (get_base_path() / binary).resolve()
        try:
            if pack_dir.exists() and pack_dir.is_dir() and any(pack_dir.iterdir()):
                return pack_dir
        except PermissionError:
            pass
        return None

    return None


def launch_installer(slug: str) -> dict:
    if sys.platform != "win32":
        raise RuntimeError("Installer launch is only supported on Windows.")

    import ctypes

    entry = get_emulator(slug)
    if entry.get("install_type") != "installer":
        raise ValueError(f"'{slug}' is not an installer-type emulator.")

    installer_glob = entry.get("windows_installer_glob")
    if not installer_glob:
        raise ValueError(f"No windows_installer_glob configured for '{slug}'.")

    slug_dir = (_BASE_DIR / slug).resolve()
    matches = _glob.glob(str(slug_dir / installer_glob))

    valid = []
    for m in matches:
        resolved = Path(m).resolve()
        try:
            resolved.relative_to(slug_dir)
            valid.append(resolved)
        except ValueError:
            pass

    if not valid:
        raise FileNotFoundError(
            f"No installer matching '{installer_glob}' found in emulators/{slug}/. "
            "Download the installer and place it there."
        )

    installer = valid[0]
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", str(installer), None, str(slug_dir), 1
    )
    if result <= 32:
        raise RuntimeError(
            f"ShellExecuteW failed with code {result} for '{installer.name}'."
        )

    return {"installer": str(installer)}


def check_git() -> bool:
    return shutil.which("git") is not None


def clone_rom_pack() -> Path:
    if not check_git():
        raise RuntimeError("git is not available on PATH. Install git and try again.")

    from backend.service.utils.emulator_catalog import get_install_path
    _box86_install = get_install_path("86box")
    if _box86_install and _box86_install.is_file():
        box86_base = _box86_install.resolve().parent
    else:
        box86_base = (get_base_path() / "emulators" / "86box").resolve()

    target_path = box86_base / "roms"

    if target_path.exists():
        try:
            if any(target_path.iterdir()):
                raise FileExistsError(
                    f"Target directory already has content: {target_path}. "
                    "Remove it before cloning."
                )
        except PermissionError:
            pass

    target_path.mkdir(parents=True, exist_ok=True)

    # Read acquire_tag from the 86box-roms dependency entry in the manifest.
    try:
        catalog_entry = get_emulator("86box")
        roms_dep = next(
            (d for d in catalog_entry.get("dependencies", []) if d.get("name") == "86box-roms"),
            None,
        )
        version = roms_dep.get("acquire_tag", "") if roms_dep else ""
    except Exception:
        version = ""

    cmd = ["git", "clone", "--depth", "1"]
    if version:
        cmd += ["--branch", version]
    cmd += ["https://github.com/86Box/roms", str(target_path)]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed with exit code {result.returncode}.")

    return target_path


def remove_emulator(slug: str) -> None:
    get_emulator(slug)
    install_dir = (_BASE_DIR / slug).resolve()
    try:
        install_dir.relative_to(_BASE_DIR.resolve())
    except ValueError:
        raise ValueError(f"Path escapes emulators/ base: {install_dir}")
    if install_dir.exists():
        shutil.rmtree(install_dir)
