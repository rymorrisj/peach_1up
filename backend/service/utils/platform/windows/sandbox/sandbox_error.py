from __future__ import annotations

from dataclasses import dataclass, field

from backend.service.utils.platform.windows.sandbox.sandbox_event import SandboxStage

@dataclass
class SandboxError(Exception):
    message: str
    stage: SandboxStage
    suggestions: list[str] = field(default_factory=list)
    disable_sandbox: bool = False

    def __str__(self) -> str:
        return self.message
