"""
Main menu screen for Peach 1UP.
Primary navigation hub with Launch, About, and Quit options.
"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Button
from textual.containers import Container, Vertical


class MainMenuScreen(Screen):
    """
    Main menu screen with three navigation options.

    Key bindings:
    - Tab/Shift+Tab: Navigate between options
    - Enter: Select option
    - q: Quit application
    - l: Launch (navigate to era selector)
    - a: About screen

    Layout:
    - Title at top
    - Five centered buttons: Launch, Profiles, Settings, About, Quit
    - Version 0.1.0 at bottom
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("l", "launch", "Launch"),
        ("p", "profiles", "Profiles"),
        ("s", "settings", "Settings"),
        ("a", "about", "About"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the main menu layout."""
        yield Container(
            Static("🍑 Peach 1UP", classes="title"),
            Static("Retro Game Launcher", classes="subtitle"),
            Static(""),
            Vertical(
                Button("Launch", id="launch", variant="primary"),
                Button("Profiles", id="profiles"),
                Button("Settings", id="settings"),
                Button("About", id="about"),
                Button("Quit", id="quit"),
                classes="menu-buttons"
            ),
            Static(""),
            Static("v0.1.0", classes="version"),
            classes="main-container"
        )

    def on_mount(self) -> None:
        """Set focus to the first button when screen loads."""
        launch_button = self.query_one("#launch", Button)
        launch_button.focus()

    def action_quit(self) -> None:
        """Exit the application."""
        self.app.exit()

    def action_launch(self) -> None:
        """Navigate to era selector."""
        from screens.era_select import EraSelectScreen
        self.app.switch_screen(EraSelectScreen())

    def action_profiles(self) -> None:
        """Navigate to profiles screen."""
        from screens.profile import ProfileScreen
        self.app.switch_screen(ProfileScreen())

    def action_settings(self) -> None:
        """Navigate to settings screen."""
        from screens.settings import SettingsScreen
        self.app.switch_screen(SettingsScreen())

    def action_about(self) -> None:
        """Navigate to about screen."""
        from screens.about import AboutScreen
        self.app.switch_screen(AboutScreen())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "launch":
            self.action_launch()
        elif event.button.id == "profiles":
            self.action_profiles()
        elif event.button.id == "settings":
            self.action_settings()
        elif event.button.id == "about":
            self.action_about()
        elif event.button.id == "quit":
            self.action_quit()