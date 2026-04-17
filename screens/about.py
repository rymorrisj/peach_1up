"""
About screen for Peach 1UP.
Shows version information, project description, and repository URL.
"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static
from textual.containers import Container


class AboutScreen(Screen):
    """
    About screen with project information.

    Key bindings:
    - b/Escape: Back to main menu
    - Tab/Shift+Tab: Navigate (if needed)

    Layout:
    - Project title
    - Version 0.1.0
    - One line description
    - Repository URL: https://github.com/rymorrisj/peach_1up
    - Back button
    """

    BINDINGS = [
        ("b", "back", "Back"),
        ("escape", "back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the about screen layout."""
        yield Container(
            Static("🍑 Peach 1UP", classes="title"),
            Static("Version 0.1.0", classes="version"),
            Static(""),
            Static("Retro game launcher and VM manager for DOS through Windows XP", classes="description"),
            Static(""),
            Static("Repository: https://github.com/rymorrisj/peach_1up", classes="url"),
            Static(""),
            Static("Press 'b' or Escape to go back", classes="help"),
            classes="about-container"
        )

    def action_back(self) -> None:
        """Navigate back to main menu."""
        from screens.main_menu import MainMenuScreen
        self.app.switch_screen(MainMenuScreen())