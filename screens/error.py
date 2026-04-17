"""
Error display screen for Peach 1UP.
Modal screen for consistent error presentation across the application.
"""

from typing import Callable, Optional

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static
from textual.containers import Container, Vertical


class ErrorScreen(ModalScreen):
    """
    Modal error display screen.

    Features:
    - Modal overlay that preserves underlying screen
    - Primary error message with optional detail text
    - Consistent dismiss behavior across the application
    - Optional callback on dismiss for navigation control

    Key bindings:
    - Enter: Dismiss error screen
    - Escape: Dismiss error screen

    Args:
        message: Primary error message to display
        detail: Optional detailed error information
        on_dismiss: Optional callback function called when screen is dismissed
                   If None, pops the current screen returning to previous screen
    """

    BINDINGS = [
        ("enter", "dismiss", "OK"),
        ("escape", "dismiss", "Cancel"),
    ]

    def __init__(
        self,
        message: str,
        detail: str = "",
        on_dismiss: Optional[Callable[[], None]] = None
    ):
        """
        Initialize error screen with message and optional dismiss handler.

        Args:
            message: Primary error message to display
            detail: Optional detailed error information
            on_dismiss: Optional callback for custom dismiss behavior
        """
        super().__init__()
        self.message = message
        self.detail = detail
        self.on_dismiss_callback = on_dismiss

    def compose(self) -> ComposeResult:
        """Compose the error display layout."""
        widgets = [
            Static("❌ Error", classes="error-title"),
            Static(""),
            Static(self.message, classes="error-message"),
        ]

        # Add detail text if provided
        if self.detail:
            widgets.extend([
                Static(""),
                Static(self.detail, classes="error-detail"),
            ])

        widgets.extend([
            Static(""),
            Static("Enter/Esc: OK", classes="help"),
        ])

        yield Container(
            Vertical(*widgets, classes="error-content"),
            classes="error-container"
        )

    def action_dismiss(self) -> None:
        """Dismiss the error screen and handle navigation."""
        self.dismiss()

        # Call custom dismiss handler if provided, otherwise pop the screen
        if self.on_dismiss_callback:
            self.on_dismiss_callback()
        else:
            self.app.pop_screen()