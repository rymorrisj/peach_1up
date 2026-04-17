"""
Stub screen for Peach 1UP placeholder functionality.
Generic screen for features not yet implemented.
"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static
from textual.containers import Container


class StubScreen(Screen):
    """
    Generic placeholder screen for unimplemented features.

    Key bindings:
    - b/Escape: Back to main menu

    Layout:
    - "Not yet implemented" message
    - Custom label describing the feature
    - Back button
    """

    BINDINGS = [
        ("b", "back", "Back"),
        ("escape", "back", "Back"),
    ]

    def __init__(self, label: str):
        """
        Initialize stub screen with custom label.

        Args:
            label: Description of the feature being stubbed
        """
        super().__init__()
        self.label = label

    def compose(self) -> ComposeResult:
        """Compose the stub screen layout."""
        yield Container(
            Static("🚧 Not yet implemented", classes="title"),
            Static(self.label, classes="subtitle"),
            Static(""),
            Static("Press 'b' or Escape to go back", classes="help"),
            classes="stub-container"
        )

    def action_back(self) -> None:
        """Navigate back to main menu."""
        from screens.main_menu import MainMenuScreen
        self.app.switch_screen(MainMenuScreen())