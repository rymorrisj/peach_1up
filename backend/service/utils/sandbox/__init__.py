from backend.service.utils.sandbox import sandbox as _sandbox_module
from backend.service.utils.sandbox.sandbox import launch, reset_container, SandboxHandle
from backend.service.utils.sandbox.sandbox_config import DaclGrant, SandboxConfig
from backend.service.utils.sandbox.sandbox_error import SandboxError
from backend.service.utils.sandbox.sandbox_event import (
    SandboxEvent,
    SandboxPayload,
    SandboxStage,
)

EXE_NAME: str = _sandbox_module.EXE_NAME


def __setattr__(name: str, value: object) -> None:
    # Write-through so `import sandbox; sandbox.EXE_NAME = "x"` takes effect
    # on the submodule that _exe() reads from.
    globals()[name] = value
    if name == "EXE_NAME":
        _sandbox_module.EXE_NAME = value  # type: ignore[assignment]


__all__ = [
    "launch",
    "reset_container",
    "EXE_NAME",
    "SandboxConfig",
    "SandboxHandle",
    "SandboxEvent",
    "SandboxPayload",
    "SandboxError",
    "SandboxStage",
    "DaclGrant",
]
