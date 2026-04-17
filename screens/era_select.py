"""
Era selector screen for Peach 1UP.
Allows user to choose between DOS, Windows 3.1, Windows 95, Windows 98, and Windows XP.
"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, ListView, ListItem, Label
from textual.containers import Container

from utils.rom_check import is_rom_pack_present


def _create_era_item(era_name: str, era_key: str, requires_rom_warning: bool) -> ListItem:
    """
    Create a list item for an era with optional ROM warning.

    Args:
        era_name: Display name for the era (e.g., "Windows 95")
        era_key: Internal key for the era (e.g., "win95")
        requires_rom_warning: Whether to show ROM warning for this era

    Returns:
        ListItem with era name and warning if ROM missing
    """
    if requires_rom_warning:
        return ListItem(
            Label(f"⚠️ {era_name}"),
            Label("ROM pack required — download it in Settings or add it manually to ROM_PATH", classes="warning"),
            name=era_key
        )
    else:
        return ListItem(
            Label(era_name),
            name=era_key
        )


class EraSelectScreen(Screen):
    """
    Era selection screen with five retro gaming eras.

    Key bindings:
    - Arrow keys or j/k: Navigate between eras
    - Enter: Select era
    - b/Escape: Back to main menu

    Layout:
    - Title at top
    - List of five eras with warnings for ROM-dependent ones
    - Help text at bottom

    Eras:
    - DOS (no ROM required)
    - Windows 3.1 (no ROM required)
    - Windows 95 (ROM pack required - shows warning if missing)
    - Windows 98 (ROM pack required - shows warning if missing)
    - Windows XP (ROM pack required - shows warning if missing)
    """

    BINDINGS = [
        ("b", "back", "Back"),
        ("escape", "back", "Back"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the era selection layout with ROM warnings."""
        # Check ROM pack presence once
        rom_present = is_rom_pack_present("")

        yield Container(
            Static("🕹️ Select Era", classes="title"),
            Static(""),
            ListView(
                _create_era_item("DOS", "dos", False),
                _create_era_item("Windows 3.1", "win31", False),
                _create_era_item("Windows 95", "win95", not rom_present),
                _create_era_item("Windows 98", "win98", not rom_present),
                _create_era_item("Windows XP", "winxp", not rom_present),
                id="era_list"
            ),
            Static(""),
            Static("↑↓/jk: Navigate • Enter: Select • b/Esc: Back", classes="help"),
            classes="era-select-container"
        )

    def action_back(self) -> None:
        """Navigate back to main menu."""
        from screens.main_menu import MainMenuScreen
        self.app.switch_screen(MainMenuScreen())

    def action_cursor_down(self) -> None:
        """Move cursor down in the list (proxy for j key)."""
        era_list = self.query_one("#era_list", ListView)
        era_list.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in the list (proxy for k key)."""
        era_list = self.query_one("#era_list", ListView)
        era_list.action_cursor_up()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle era selection and navigate to media picker."""
        selected_item = event.item
        era_key = selected_item.name

        from screens.stub import StubScreen
        self.app.switch_screen(StubScreen(f"Game Picker — coming in P0-6 (Era: {era_key})"))