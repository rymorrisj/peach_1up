"""Non-fatal startup warning screen for missing emulator binaries."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static
from textual.containers import Container, Vertical

from backend.service.utils.system_check import MissingBinary


class MissingBinaryScreen(ModalScreen):
    """
    Modal warning shown on startup when one or more emulator binaries are missing.
    Non-fatal — user dismisses and continues with partial functionality.

    Key bindings:
    - Enter / Escape: Dismiss and continue to main menu
    """

    BINDINGS = [
        ("enter", "dismiss_warning", "Continue"),
        ("escape", "dismiss_warning", "Continue"),
    ]

    def __init__(self, missing: list[MissingBinary]) -> None:
        super().__init__()
        self._missing = missing

    def compose(self) -> ComposeResult:
        lines: list[Static] = [
            Static("⚠️  Missing Emulator Binaries", classes="error-title"),
            Static(""),
            Static(
                "The following emulators were not found. "
                "Affected eras will be unavailable.",
                classes="error-message",
            ),
            Static(""),
        ]
        for binary in self._missing:
            lines.append(
                Static(
                    f"{binary.name}  ({binary.env_var})",
                    classes="error-message",
                )
            )
            lines.append(
                Static(f"  Download: {binary.download_url}", classes="error-detail")
            )
            lines.append(Static(""))

        lines.append(Static("Enter/Esc: Continue", classes="help"))

        yield Container(
            Vertical(*lines, classes="error-content"),
            classes="error-container",
        )

    def action_dismiss_warning(self) -> None:
        self.dismiss()
