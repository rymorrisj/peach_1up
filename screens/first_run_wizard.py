"""First-run setup wizard for Peach 1UP.

Shown on first launch, or whenever required emulators are unconfigured
or no OS platforms are registered. Guides the user through binary path
configuration and links to platform registration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static, ListView, ListItem, Label
from textual.containers import VerticalScroll

from utils import settings


# (key, display_name, required, download_url_or_none)
_CHECKS: list[tuple[str, str, bool, Optional[str]]] = [
    ("dosbox",     "DOSBox-X",       True,  "https://dosbox-x.com"),
    ("virtualbox", "VirtualBox",     True,  "https://www.virtualbox.org"),
    ("box86",      "86Box",          False, "https://86box.net"),
    ("roms",       "86Box ROM Pack", False, "https://github.com/86Box/roms"),
    ("platforms",  "OS Platforms",   False, None),
]

_BINARY_PROMPTS: dict[str, str] = {
    "dosbox":      "Path to DOSBox-X executable:",
    "virtualbox":  "Path to VirtualBox (VBoxManage.exe):",
    "box86":       "Path to 86Box executable:",
}


class FirstRunWizardScreen(Screen):
    """First-run setup wizard — configure emulators and register platforms."""

    DEFAULT_CSS = """
    FirstRunWizardScreen {
        align: center middle;
    }

    #wizard-panel {
        width: 78;
        height: auto;
        max-height: 90vh;
        border: round $primary;
        padding: 1 2;
    }

    #wizard-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #wizard-intro {
        margin-bottom: 1;
    }

    #wizard-help {
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("s", "skip", "Skip setup"),
        Binding("c", "confirm", "Continue"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._status: dict[str, str] = {}

    def on_mount(self) -> None:
        self._refresh_status()
        self.call_after_refresh(self._focus_list)

    # --- Status computation ---

    def _refresh_status(self) -> None:
        self._status = self._compute_status()

    def _compute_status(self) -> dict[str, str]:
        result: dict[str, str] = {}

        for key in ("dosbox", "virtualbox", "box86"):
            p = settings.get_binary_path(key)
            result[key] = "ok" if (p and Path(p).is_file()) else "missing"

        rom = settings.get_env_var("ROM_PATH")
        result["roms"] = "ok" if (rom and Path(rom).is_dir()) else "missing"

        try:
            from utils.platform import load_all
            result["platforms"] = "ok" if load_all(Path("config") / "platforms.yaml") else "missing"
        except Exception:
            result["platforms"] = "missing"

        return result

    def _all_required_ok(self) -> bool:
        return all(
            self._status.get(key) == "ok"
            for key, _, required, _ in _CHECKS
            if required
        )

    # --- Compose ---

    def _item_label(self, key: str, name: str, required: bool, url: Optional[str]) -> str:
        status = self._status.get(key, "missing")
        if status == "ok":
            return f"  ✓  {name}   Found"
        suffix = f"   {url}" if url else ""
        if required:
            return f"  ✗  {name}   Not found — required{suffix}"
        return f"  ⚠  {name}   Not found — optional{suffix}"

    def compose(self) -> ComposeResult:
        items = [
            ListItem(Label(self._item_label(key, name, required, url)), name=key)
            for key, name, required, url in _CHECKS
        ]
        continue_hint = (
            "C: Continue"
            if self._all_required_ok()
            else "C: Continue (required items outstanding)"
        )
        yield VerticalScroll(
            Static("Setup Wizard — Peach 1UP", id="wizard-title"),
            Static(
                "Configure required emulators below. "
                "Select an item and press Enter to set its path.",
                id="wizard-intro",
            ),
            ListView(*items, id="wizard-list"),
            Static(
                f"Enter: Configure  •  {continue_hint}  •  S: Skip",
                id="wizard-help",
                classes="help",
            ),
            id="wizard-panel",
        )

    # --- Interaction ---

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        key = event.item.name
        if key in _BINARY_PROMPTS:
            self._prompt_binary(key)
        elif key == "roms":
            self._show_rom_guidance()
        elif key == "platforms":
            from screens.platform_guidance import PlatformGuidanceScreen
            self.app.push_screen(PlatformGuidanceScreen(), lambda _: self._recompose())

    def _prompt_binary(self, emulator: str) -> None:
        current = settings.get_binary_path(emulator)

        def on_path(value: Optional[str]) -> None:
            if not value:
                return
            value = value.strip()
            if not value:
                return
            p = Path(value)
            if not p.exists():
                from screens.error import ErrorScreen
                self.app.push_screen(ErrorScreen(
                    "Path not found",
                    f"No file exists at:\n{value}",
                    on_dismiss=lambda: None,
                ))
                return
            if not p.is_file():
                from screens.error import ErrorScreen
                self.app.push_screen(ErrorScreen(
                    "Not an executable file",
                    f"The path exists but is not a file:\n{value}",
                    on_dismiss=lambda: None,
                ))
                return
            settings.set_override_path(emulator, value)
            self._recompose()

        from screens.profile import InputModal
        self.app.push_screen(InputModal(_BINARY_PROMPTS[emulator], current), on_path)

    def _show_rom_guidance(self) -> None:
        from screens.error import ErrorScreen
        self.app.push_screen(ErrorScreen(
            "86Box ROM Pack",
            "Set ROM_PATH in your .env file to the directory containing 86Box ROM files.\n"
            "Download:  https://github.com/86Box/roms\n\n"
            "ROM pack is optional — 86Box accuracy mode will not work without it.",
            on_dismiss=lambda: None,
        ))

    def _recompose(self) -> None:
        self._refresh_status()
        self.refresh(recompose=True)
        self.call_after_refresh(self._focus_list)

    def _focus_list(self) -> None:
        try:
            self.query_one("#wizard-list", ListView).focus()
        except Exception:
            self.focus()

    # --- Actions ---

    def action_skip(self) -> None:
        from screens.error import ErrorScreen
        self.app.push_screen(ErrorScreen(
            "Setup incomplete",
            "Some required emulators are not configured.\n"
            "Peach 1UP may not work correctly until setup is complete.\n"
            "You can configure paths in Settings or restart to run this wizard again.",
            on_dismiss=self.dismiss,
        ))

    def action_confirm(self) -> None:
        if not self._all_required_ok():
            from screens.error import ErrorScreen
            self.app.push_screen(ErrorScreen(
                "Required items not configured",
                "DOSBox-X and VirtualBox must both be configured before continuing.\n"
                "Select each missing item and enter the path to the executable.",
                on_dismiss=lambda: None,
            ))
            return
        settings.mark_first_run_complete()
        self.dismiss()
