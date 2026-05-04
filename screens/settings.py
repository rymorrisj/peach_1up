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
from utils import settings


_ENV_PATH = Path(".env")

# (env_var_or_settings_key, display_label, field_type)
# field_type: "env" → saved to .env via dotenv
#             "override" → saved to settings.yaml via settings.set_override_path()
_FIELDS: list[tuple[str, str, str]] = [
    ("DOSBOX_PATH",              "DOSBox-X Executable",          "env"),
    ("BOX86_PATH",               "86Box Executable",             "env"),
    ("VIRTUALBOX_PATH",          "VirtualBox (VBoxManage.exe)",  "env"),
    ("ROM_PATH",                 "ROM Pack Directory",           "env"),
    ("PROFILES_PATH",            "Profiles Directory",           "env"),
    ("dosbox_path_override",     "DOSBox-X Path Override",       "override"),
    ("box86_path_override",      "86Box Path Override",          "override"),
    ("virtualbox_path_override", "VirtualBox Path Override",     "override"),
]

_OVERRIDE_EMULATORS: dict[str, str] = {
    "dosbox_path_override":     "dosbox",
    "box86_path_override":      "box86",
    "virtualbox_path_override": "virtualbox",
}


def _load_values() -> dict[str, str]:
    stored = dotenv_values(_ENV_PATH) if _ENV_PATH.exists() else {}
    result: dict[str, str] = {}
    for key, _, field_type in _FIELDS:
        if field_type == "env":
            result[key] = stored.get(key) or ""
        else:
            result[key] = settings.get(key, "") or ""
    return result


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
        self._values: dict[str, str] = _load_values()
        self._saved = False

    def compose(self) -> ComposeResult:
        items = [
            ListItem(
                Label(f"{label}:  {self._values.get(key, '')}"),
                name=key,
            )
            for key, label, _ in _FIELDS
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
        field_def = next(((k, lbl, t) for k, lbl, t in _FIELDS if k == key), None)
        if not field_def:
            return
        _, label, field_type = field_def
        current = self._values.get(key, "")

        def on_value(value: Optional[str]) -> None:
            if value is None:
                return
            value = value.strip()
            if field_type == "override":
                try:
                    settings.set_override_path(_OVERRIDE_EMULATORS[key], value)
                except Exception as exc:
                    from screens.error import ErrorScreen
                    self.app.push_screen(
                        ErrorScreen("Failed to save override", str(exc), on_dismiss=lambda: None)
                    )
                    return
            else:
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
