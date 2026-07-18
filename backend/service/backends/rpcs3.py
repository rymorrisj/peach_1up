"""RPCS3 backend for Peach 1UP, scaffolding only.

Registered in backend_router._BACKEND_MODULES so PS3 dispatch resolves end
to end. Executable and media validation run here, but process spawn is not
implemented yet, see rpcs3.toml's known_limitations for what remains.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from backend.core.logger import get_logger
from backend.service.utils.emulator_catalog import get_emulator, get_install_path

logger = get_logger(__name__)

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec
    from backend.service.utils.platform.windows.process.job_objects import WindowsJobObject
    from backend.service.utils.platform.windows.sandbox_process import SandboxProcess


def launch(spec: "LaunchSpec") -> Tuple["SandboxProcess", "WindowsJobObject"]:
    """Validate an RPCS3 launch request. Process spawn is not implemented yet.

    Raises:
        FileNotFoundError: If the executable or media file is missing.
        ValueError: If the media extension is unsupported.
        NotImplementedError: Always, once validation passes, RPCS3 launch
            logic lands in a follow-up pass.
    """
    entry = get_emulator("rpcs3")
    display_name = entry.get("display_name", "rpcs3")
    supported_formats = set(entry.get("supported_formats", []))

    install_path = get_install_path("rpcs3")
    if install_path is None or not install_path.is_file():
        raise FileNotFoundError(
            f"{display_name} executable not found. Install it via the Emulators page."
        )

    if spec.media_path is not None:
        if not spec.media_path.exists():
            raise FileNotFoundError(f"Media file not found: {spec.media_path}")
        if spec.media_path.suffix.lower() not in supported_formats:
            raise ValueError(
                f"Unsupported media format '{spec.media_path.suffix}'. "
                f"{display_name} supports: {', '.join(sorted(supported_formats))}"
            )

    raise NotImplementedError(
        f"{display_name} launch is not implemented yet, scaffolding only in this pass. "
        "Path and dependency wiring is complete; process spawn lands in a follow-up pass."
    )
