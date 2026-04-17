"""
Game picker screen for Peach 1UP.
Displays compatible media files for the selected gaming era.
"""

import os
from pathlib import Path
from typing import List
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, ListView, ListItem, Label
from textual.containers import Container

from utils.constants import Era
from utils.media_detect import get_compatible_media


def _get_search_path(images_path: str) -> str:
    """
    Get the directory path to search for media files.

    Args:
        images_path: Directory path from constructor

    Returns:
        Absolute directory path from parameter or IMAGES_PATH env var.
        Returns empty string if both are unavailable.
    """
    path_to_resolve = images_path or os.getenv('IMAGES_PATH')
    if not path_to_resolve:
        return ""

    # Convert relative paths to absolute paths based on project root
    # launcher.py is run from project root, so __file__ points to screens/game_picker.py
    project_root = Path(__file__).parent.parent
    resolved_path = project_root / path_to_resolve
    return str(resolved_path.resolve())


def _create_file_list(files: List[Path]) -> ListView:
    """Create ListView with files or empty state message."""
    if not files:
        return ListView(
            ListItem(Label("No compatible game files found.")),
            ListItem(Label("Add .iso, .img, or .cue files to images/games/ to get started.")),
            id="file_list"
        )

    file_items = []
    for file_path in files:
        file_items.append(ListItem(Label(file_path.name), name=str(file_path)))

    return ListView(*file_items, id="file_list")


class GamePickerScreen(Screen):
    """
    Game file picker screen with era-specific media filtering.

    Key bindings:
    - Arrow keys or j/k: Navigate between files
    - Enter: Select file
    - b/Escape: Back to era selector

    Layout:
    - Selected era display at top
    - List of compatible media files (filenames only)
    - Empty state message if no files found
    - Help text at bottom

    Navigation:
    - File selection → StubScreen("Launch Flow — coming in P0-7")
    - Back → EraSelectScreen
    """

    BINDINGS = [
        ("b", "back", "Back"),
        ("escape", "back", "Back"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
    ]

    def __init__(self, era: Era, images_path: str = ""):
        """
        Initialize game picker screen for specified era.

        Args:
            era: Gaming era to filter media files for
            images_path: Directory path to search. If empty, reads from IMAGES_PATH env var.
        """
        super().__init__()
        self.era = era
        self.images_path = images_path

    def compose(self) -> ComposeResult:
        """Compose the game picker layout with media file list."""
        search_path = _get_search_path(self.images_path)
        compatible_files = get_compatible_media(self.era, search_path)

        yield Container(
            Static(f"🎮 {self.era.value.upper()} Games", classes="title"),
            Static(""),
            _create_file_list(compatible_files),
            Static(""),
            Static("↑↓/jk: Navigate • Enter: Select • b/Esc: Back", classes="help"),
            classes="game-picker-container"
        )

    def action_back(self) -> None:
        """Navigate back to era selector screen."""
        from screens.era_select import EraSelectScreen
        self.app.switch_screen(EraSelectScreen())

    def action_cursor_down(self) -> None:
        """Move cursor down in the list (proxy for j key)."""
        file_list = self.query_one("#file_list", ListView)
        file_list.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in the list (proxy for k key)."""
        file_list = self.query_one("#file_list", ListView)
        file_list.action_cursor_up()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle file selection and navigate to launch flow."""
        selected_item = event.item
        if selected_item.name:  # Only proceed if item has a file path
            file_path = selected_item.name

            from screens.launch import LaunchScreen
            self.app.switch_screen(LaunchScreen(era=self.era, media_path=Path(file_path)))