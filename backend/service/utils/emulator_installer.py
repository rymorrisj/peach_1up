import glob as _glob
import shutil
import subprocess
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

    if install_type in ("zip", "github_release"):
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


def check_git() -> bool:
    return shutil.which("git") is not None


def record_rom_pack_item(pack_slug: str, emulator_slug: str, install_path: Path | None, is_present: bool) -> None:
    """Insert or update the ``rom_pack_items`` row for *pack_slug*.

    Called after a clone (clone_rom_pack) and from the rom-packs verify
    route, both cases record the owned result without altering the
    underlying install_type == "rom_pack" catalog/clone mechanism.
    """
    from datetime import datetime, timezone
    from sqlalchemy.orm import sessionmaker

    from backend.core.database import get_engine
    from backend.models import RomPackItem

    try:
        entry = get_emulator(pack_slug)
    except ValueError:
        entry = {}

    now = datetime.now(timezone.utc)
    session_factory = sessionmaker(bind=get_engine())
    with session_factory() as db:
        row = db.query(RomPackItem).filter(RomPackItem.slug == pack_slug).one_or_none()
        if row is None:
            row = RomPackItem(slug=pack_slug, name=entry.get("name", pack_slug), emulator_slug=emulator_slug)
            db.add(row)
        row.name = entry.get("name", row.name)
        row.emulator_slug = emulator_slug
        row.source_url = entry.get("source_url", row.source_url)
        row.is_present = is_present
        if install_path is not None:
            row.install_path = str(install_path)
        if is_present:
            row.installed_at = now
        db.commit()


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

    record_rom_pack_item("86box-roms", "86box", target_path, is_present=True)

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
