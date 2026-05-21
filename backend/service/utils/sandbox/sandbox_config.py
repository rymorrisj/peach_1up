from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class DaclGrant:
    path: str
    access: Literal["r", "rx", "rw"]


@dataclass
class SandboxConfig:
    moniker: str
    exe_path: str
    args: list[str] = field(default_factory=list)
    working_dir: str | None = None
    dacl_grants: list[DaclGrant] = field(default_factory=list)
    cpu_max_rate: int = 50
    cpu_min_rate: int = 5
    memory_limit_mb: int | None = None
