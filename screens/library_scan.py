"""Library scanner screen for Peach 1UP.

Walks a user-supplied directory recursively for .iso, .img, and .cue files,
runs era detection on each, and bulk-imports them as game profiles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen, ModalScreen
from textual.widgets import Static, ListView, ListItem, Label, Checkbox
from textual.containers import Container

from utils.constants import Era
from utils.profile_builder import ScanEntry, scan_directory, import_profiles
from utils import settings


_ERA_LABELS: dict[str, str] = {
    "dos":   "DOS",
    "win31": "Win 3.1",
    "win95": "Win 95",
    "win98": "Win 98",
    "winxp": "Win XP",
}


def _profiles_dir() -> Path:
    return Path(settings.get_env_var("PROFILES_PATH"))


class _ImportConfirmModal(ModalScreen):
    """Confirm bulk import with optional suppression of future prompts."""

    BINDINGS = [
        Binding("y", "do_confirm", "Yes"),
        Binding("n", "do_cancel", "No"),
        Binding("escape", "do_cancel", "Cancel"),
    ]

    def __init__(self, count: int) -> None:
        super().__init__()
        self._count = count

    def compose(self) -> ComposeResult:
        yield Container(
            Static(f"Import {self._count} profile(s)?", classes="input-prompt"),
            Static(""),
            Checkbox("Don't ask again for library imports", False, id="dont_ask"),
            Static(""),
            Static("Y: Import  •  N/Esc: Cancel", classes="help"),
            classes="input-modal-container",
        )

    def on_mount(self) -> None:
        try:
            self.query_one("#dont_ask", Checkbox).focus()
        except Exception:
            self.focus()

    def action_do_confirm(self) -> None:
        try:
            dont_ask = self.query_one("#dont_ask", Checkbox).value
        except Exception:
            dont_ask = False
        self.dismiss(dont_ask)

    def action_do_cancel(self) -> None:
        self.dismiss(None)


class LibraryScanScreen(Screen):
    """Scan a directory for game media and bulk-import as profiles."""

    BINDINGS = [
        Binding("b", "back", "Back"),
        Binding("escape", "back", "Back"),
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("space", "toggle_selected", "Toggle", priority=True),
        Binding("a", "toggle_all", "All/None"),
        Binding("c", "confirm_import", "Import"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._entries: list[ScanEntry] = []
        self._scanned = False
        self._scan_dir: Optional[Path] = None

    def on_mount(self) -> None:
        from screens.profile import InputModal
        self.app.push_screen(
            InputModal("Directory to scan:", r"e.g. D:\Games"),
            self._on_dir_entered,
        )

    def _on_dir_entered(self, value: Optional[str]) -> None:
        if not value or not value.strip():
            from screens.main_menu import MainMenuScreen
            self.app.switch_screen(MainMenuScreen())
            return
        scan_dir = Path(value.strip())
        if not scan_dir.exists() or not scan_dir.is_dir():
            from screens.error import ErrorScreen
            from screens.main_menu import MainMenuScreen as _MainMenu
            self.app.push_screen(ErrorScreen(
                "Directory not found",
                f"No directory exists at:\n{scan_dir}",
                on_dismiss=lambda: self.app.switch_screen(_MainMenu()),
            ))
            return
        self._scan_dir = scan_dir
        self._entries = scan_directory(scan_dir)
        self._scanned = True
        self.refresh(recompose=True)
        self.call_after_refresh(self._focus_list)

    # --- Compose ---

    def compose(self) -> ComposeResult:
        if not self._scanned:
            yield Container(
                Static("📂 Library Scan", classes="title"),
                classes="profile-list-container",
            )
            return

        if not self._entries:
            yield Container(
                Static("📂 Library Scan", classes="title"),
                Static(""),
                Static(f"No .iso / .img / .cue files found in:\n{self._scan_dir}"),
                Static(""),
                Static("b/Esc: Back", classes="help"),
                classes="profile-list-container",
            )
            return

        selected_count = sum(1 for e in self._entries if e.selected)
        items = [
            ListItem(Label(self._entry_label(e)), name=str(i))
            for i, e in enumerate(self._entries)
        ]
        yield Container(
            Static("📂 Library Scan", classes="title"),
            Static(
                f"Found {len(self._entries)} file(s)  •  "
                f"{selected_count} selected  •  {self._scan_dir}"
            ),
            Static(""),
            ListView(*items, id="scan_list"),
            Static(""),
            Static(
                "Space: Toggle  •  A: All/None  •  C: Import selected  •  b/Esc: Back",
                classes="help",
            ),
            classes="profile-list-container",
        )

    def _entry_label(self, entry: ScanEntry) -> str:
        mark = "✓" if entry.selected else "○"
        era_str = _ERA_LABELS.get(entry.era.value, entry.era.value) if entry.era else "?"
        return f"  {mark}  {entry.name}  [{era_str}]  {entry.path.name}"

    # --- Navigation ---

    def _focus_list(self) -> None:
        try:
            self.query_one("#scan_list", ListView).focus()
        except Exception:
            self.focus()

    def action_cursor_down(self) -> None:
        try:
            self.query_one("#scan_list", ListView).action_cursor_down()
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        try:
            self.query_one("#scan_list", ListView).action_cursor_up()
        except Exception:
            pass

    # --- Selection ---

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self._toggle_entry(event.item.name)

    def action_toggle_selected(self) -> None:
        try:
            item = self.query_one("#scan_list", ListView).highlighted_child
            if item:
                self._toggle_entry(item.name)
        except Exception:
            pass

    def _toggle_entry(self, name: Optional[str]) -> None:
        if name is None:
            return
        try:
            idx = int(name)
            self._entries[idx].selected = not self._entries[idx].selected
            self.refresh(recompose=True)
            self.call_after_refresh(self._focus_list)
        except (ValueError, IndexError):
            pass

    def action_toggle_all(self) -> None:
        if not self._entries:
            return
        target = not all(e.selected for e in self._entries)
        for e in self._entries:
            e.selected = target
        self.refresh(recompose=True)
        self.call_after_refresh(self._focus_list)

    # --- Import ---

    def action_confirm_import(self) -> None:
        selected = [e for e in self._entries if e.selected]
        if not selected:
            from screens.error import ErrorScreen
            self.app.push_screen(ErrorScreen(
                "Nothing selected",
                "Select at least one entry before importing.",
                on_dismiss=lambda: None,
            ))
            return

        if settings.is_suppressed("library_scan_import"):
            self._do_import(selected)
            return

        def on_confirmed(dont_ask: Optional[bool]) -> None:
            if dont_ask is None:
                return
            if dont_ask:
                settings.add_suppression("library_scan_import")
            self._do_import(selected)

        self.app.push_screen(_ImportConfirmModal(len(selected)), on_confirmed)

    def _do_import(self, entries: list[ScanEntry]) -> None:
        profiles_dir = _profiles_dir()
        conf_dir = profiles_dir / "conf"
        images_dir = Path("images") / "hdd"
        saved, failed = import_profiles(entries, profiles_dir, conf_dir, images_dir)
        msg = f"Imported {saved} profile(s)."
        if failed:
            msg += f"  {failed} could not be saved."
        self.notify(msg, timeout=5)
        from screens.main_menu import MainMenuScreen
        self.app.switch_screen(MainMenuScreen())

    def action_back(self) -> None:
        from screens.main_menu import MainMenuScreen
        self.app.switch_screen(MainMenuScreen())
