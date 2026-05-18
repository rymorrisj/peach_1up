import glob as _glob
import shutil
import subprocess
import sys
from pathlib import Path

from backend.service.utils.emulator_catalog import get_emulator

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BASE_DIR = _PROJECT_ROOT / "emulators"


def detect_binary(slug: str) -> Path | None:
    entry = get_emulator(slug)
    install_type = entry.get("install_type", "zip")
    windows_binary = entry.get("windows_binary", "")

    if not windows_binary:
        return None

    if install_type == "zip":
        slug_dir = (_BASE_DIR / slug).resolve()
        path = (slug_dir / windows_binary).resolve()
        try:
            path.relative_to(slug_dir)
        except ValueError:
            return None
        return path if path.exists() else None

    if install_type == "installer":
        matches = _glob.glob(windows_binary)
        return Path(matches[0]) if matches else None

    if install_type == "rom_pack":
        pack_dir = (_PROJECT_ROOT / windows_binary).resolve()
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


def clone_rom_pack(target_path: Path) -> None:
    if not check_git():
        raise RuntimeError("git is not available on PATH. Install git and try again.")

    box86_base = (_PROJECT_ROOT / "emulators" / "86box").resolve()
    try:
        target_path.resolve().relative_to(box86_base)
    except ValueError:
        raise ValueError(
            f"target_path must be inside emulators/86box/: {target_path.resolve()}"
        )

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

    try:
        version = get_emulator("86box").get("rom_pack_version", "")
    except Exception:
        version = ""

    cmd = ["git", "clone", "--depth", "1"]
    if version:
        cmd += ["--branch", version]
    cmd += ["https://github.com/86Box/roms", str(target_path)]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed with exit code {result.returncode}.")


def remove_emulator(slug: str) -> None:
    get_emulator(slug)
    install_dir = (_BASE_DIR / slug).resolve()
    try:
        install_dir.relative_to(_BASE_DIR.resolve())
    except ValueError:
        raise ValueError(f"Path escapes emulators/ base: {install_dir}")
    if install_dir.exists():
        shutil.rmtree(install_dir)
