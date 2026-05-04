"""
Peach 1UP main application entry point.
Textual-based TUI launcher for retro game emulation.
"""

from pathlib import Path

from textual.app import App

from screens.main_menu import MainMenuScreen
from utils import settings
from utils.system_check import is_elevated, check_missing_binaries


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

    def on_ready(self) -> None:
        """Configure app for keyboard navigation when ready."""
        self.set_focus(None)

    def on_mount(self) -> None:
        """Load settings, check elevation, then show main menu or setup wizard."""
        settings.init()

        if not is_elevated():
            from screens.error import ErrorScreen
            self.push_screen(
                ErrorScreen(
                    "Administrator privileges required.",
                    "Peach 1UP must run as Administrator to manage Windows Firewall "
                    "rules and Job Objects.\n"
                    "Right-click the launcher and select 'Run as administrator'.",
                    on_dismiss=lambda: self.exit(),
                )
            )
            return

        self.push_screen(MainMenuScreen())

        if self._wizard_needed():
            from screens.first_run_wizard import FirstRunWizardScreen
            self.push_screen(FirstRunWizardScreen())
        else:
            missing = check_missing_binaries()
            if missing:
                from screens.system_warning import MissingBinaryScreen
                self.push_screen(MissingBinaryScreen(missing))

    def _wizard_needed(self) -> bool:
        """Return True if the first-run setup wizard should be shown."""
        from utils.platform import load_all
        if settings.is_first_run():
            return True
        for emulator in ("dosbox", "virtualbox"):
            path = settings.get_binary_path(emulator)
            if not path or not Path(path).is_file():
                return True
        try:
            if not load_all(Path("config") / "platforms.yaml"):
                return True
        except Exception:
            return True
        return False


def main() -> None:
    """Entry point for the Peach 1UP application."""
    app = Peach1UPApp()
    app.run()


if __name__ == "__main__":
    main()
