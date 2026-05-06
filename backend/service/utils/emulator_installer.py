import shutil
from pathlib import Path

import httpx

from backend.service.utils.emulator_catalog import get_emulator, get_install_path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BASE_DIR = _PROJECT_ROOT / "emulators"


def _validate_path(path: Path) -> None:
    try:
        path.resolve().relative_to(_BASE_DIR.resolve())
    except ValueError:
        raise ValueError(f"Path escapes emulators/ base: {path.resolve()}")


async def download_emulator(slug: str) -> Path:
    entry = get_emulator(slug)
    url = entry.get("linux_url", "")
    if not url or url.startswith("PLACEHOLDER"):
        raise NotImplementedError(
            f"Download URL not yet configured for {slug} — update config/emulators.yaml"
        )

    install_path = get_install_path(slug)
    _validate_path(install_path)

    install_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = install_path.parent / f"{install_path.name}.tmp"

    async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            try:
                with tmp_path.open("wb") as fh:
                    async for chunk in response.aiter_bytes():
                        fh.write(chunk)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise

    tmp_path.rename(install_path)
    install_path.chmod(install_path.stat().st_mode | 0o111)
    return install_path


def remove_emulator(slug: str) -> None:
    get_emulator(slug)
    install_dir = (_BASE_DIR / slug).resolve()
    _validate_path(install_dir)
    if install_dir.exists():
        shutil.rmtree(install_dir)
