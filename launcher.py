"""
Peach 1UP main application entry point.
Textual-based TUI launcher for retro game emulation.
"""

from textual.app import App

from screens.main_menu import MainMenuScreen


class Peach1UPApp(App):
    """
    Main Textual application for Peach 1UP retro game launcher.

    Features:
    - Keyboard-driven navigation (no mouse required)
    - Screen-based navigation system
    - Starts with main menu

    Key bindings:
    - Ctrl+C: Emergency exit
    - Various screen-specific bindings
    """

    TITLE = "Peach 1UP - Retro Game Launcher"

    def on_mount(self) -> None:
        """Initialize application and show main menu."""
        self.push_screen(MainMenuScreen())


def main() -> None:
    """Entry point for the Peach 1UP application."""
    app = Peach1UPApp()
    app.run()


if __name__ == "__main__":
    main()