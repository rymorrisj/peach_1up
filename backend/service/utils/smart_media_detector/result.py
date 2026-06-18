from dataclasses import dataclass, field


@dataclass(slots=True)
class ScanResult:
    title: str | None
    platform: str | None
    era: str | None
    confidence: float
    reason: str
    requires_manual_boot: bool = False
    requires_install: bool = False
    warnings: list[str] = field(default_factory=list)
    executable_hints: list[str] = field(default_factory=list)
