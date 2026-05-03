"""Settings screen for Peach 1UP — edit .env path settings in the TUI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dotenv import set_key, dotenv_values
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, ListView, ListItem, Label
from textual.containers import Container

from screens.profile import InputModal


_ENV_PATH = Path(".env")

_FIELDS: list[tuple[str, str]] = [
    ("DOSBOX_PATH",   "DOSBox-X Executable"),
    ("BOX86_PATH",    "86Box Executable"),
    ("ROM_PATH",      "ROM Pack Directory"),
    ("PROFILES_PATH", "Profiles Directory"),
]


def _load_env_values() -> dict[str, str]:
    stored = dotenv_values(_ENV_PATH) if _ENV_PATH.exists() else {}
    return {key: stored.get(key) or "" for key, _ in _FIELDS}


class SettingsScreen(Screen):
    """View and edit .env path settings."""

    BINDINGS = [
        ("escape", "back", "Back"),
        ("b", "back", "Back"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._values: dict[str, str] = _load_env_values()
        self._saved = False

    def compose(self) -> ComposeResult:
        items = [
            ListItem(
                Label(f"{label}:  {self._values.get(key, '')}"),
                name=key,
            )
            for key, label in _FIELDS
        ]
        help_text = (
            "Saved — restart Peach 1UP to apply changes."
            if self._saved
            else "Enter: Edit • b/Esc: Back"
        )
        yield Container(
            Static("⚙️  Settings", classes="title"),
            Static(""),
            ListView(*items, id="settings_list"),
            Static(""),
            Static(help_text, classes="help"),
            classes="profile-list-container",
        )

    def on_mount(self) -> None:
        self._focus_list()

    def _focus_list(self) -> None:
        try:
            self.query_one("#settings_list", ListView).focus()
        except Exception:
            self.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        key = event.item.name
        if not key:
            return
        label = next((lbl for k, lbl in _FIELDS if k == key), key)
        current = self._values.get(key, "")

        def on_value(value: Optional[str]) -> None:
            if value is None:
                return
            value = value.strip()
            try:
                set_key(str(_ENV_PATH), key, value)
            except Exception as exc:
                from screens.error import ErrorScreen
                self.app.push_screen(
                    ErrorScreen("Failed to save setting", str(exc), on_dismiss=lambda: None)
                )
                return
            self._values[key] = value
            self._saved = True
            self.refresh(recompose=True)
            self.call_after_refresh(self._focus_list)

        self.app.push_screen(InputModal(f"{label}:", current), on_value)

    def action_back(self) -> None:
        from screens.main_menu import MainMenuScreen
        self.app.switch_screen(MainMenuScreen())

    def action_cursor_down(self) -> None:
        self.query_one(ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(ListView).action_cursor_up()
