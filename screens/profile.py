"""Profile management screen for Peach 1UP."""

from __future__ import annotations

import os
from pathlib import Path
from subprocess import Popen
from typing import Optional

from textual.app import ComposeResult
from textual.screen import Screen, ModalScreen
from textual.widgets import Static, ListView, ListItem, Label, Input
from textual.containers import Container, VerticalScroll

from utils.constants import Era
from utils.profile import Profile, load, list_profiles, save, append_history, load_history
from utils.dosbox_config import generate_conf
from utils.vhd import ensure_hdd
from utils.media_detect import detect_era
from utils import settings
from utils.job_objects import WindowsJobObject
from backends.dosbox import launch_install, launch_game
from screens.error import ErrorScreen


def _profiles_dir() -> Path:
    return Path(settings.get_env_var("PROFILES_PATH"))


def _conf_dir() -> Path:
    return _profiles_dir() / "conf"


def _hdd_dir() -> Path:
    return Path("images") / "hdd"



class InputModal(ModalScreen):
    """Generic single-line text input modal."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, prompt: str, placeholder: str = "") -> None:
        super().__init__()
        self._prompt = prompt
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        yield Container(
            Static(self._prompt, classes="input-prompt"),
            Input(placeholder=self._placeholder, id="modal_input"),
            Static("Enter: Confirm • Esc: Cancel", classes="help"),
            classes="input-modal-container",
        )

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class EraSelectModal(ModalScreen):
    """Era picker modal for the profile create flow."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
    ]

    _ERA_CHOICES = [
        (Era.DOS, "DOS"),
        (Era.WIN31, "Windows 3.1"),
    ]

    def compose(self) -> ComposeResult:
        yield Container(
            Static("Select era:", classes="input-prompt"),
            ListView(
                *[
                    ListItem(Label(label), name=era.value)
                    for era, label in self._ERA_CHOICES
                ],
                id="era_modal_list",
            ),
            Static("↑↓/jk: Navigate • Enter: Select • Esc: Cancel", classes="help"),
            classes="input-modal-container",
        )

    def on_mount(self) -> None:
        self.query_one(ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.name:
            self.dismiss(Era(event.item.name))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        self.query_one(ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(ListView).action_cursor_up()


class HistoryModal(ModalScreen):
    """Read-only view of a profile's save history, newest entry first."""

    DEFAULT_CSS = """
    HistoryModal { align: center middle; }
    #history-panel {
        width: 72;
        height: auto;
        max-height: 88vh;
        border: round $primary;
        padding: 1 2;
    }
    .history-ts { text-style: bold; margin-top: 1; }
    .history-change { margin-left: 2; }
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
    ]

    def __init__(self, profile: Profile) -> None:
        super().__init__()
        self._profile = profile

    def compose(self) -> ComposeResult:
        entries = load_history(self._profile, _profiles_dir())
        rows: list = [
            Static(f"History — {self._profile.name}", classes="title"),
            Static(""),
        ]
        if not entries:
            rows.append(Static("No history recorded yet."))
        else:
            for entry in entries:
                ts  = entry.get("timestamp", "?")
                src = entry.get("source", "?")
                rows.append(Static(f"[{ts}]  source: {src}", classes="history-ts"))
                for ch in entry.get("changes", []):
                    field_name = ch.get("field", "?")
                    old = ch.get("old")
                    new = ch.get("new")
                    rows.append(Static(
                        f"  {field_name}:  {old!r} → {new!r}",
                        classes="history-change",
                    ))
        rows += [Static(""), Static("Esc/q: Close", classes="help")]
        yield VerticalScroll(*rows, id="history-panel")


class ProfileScreen(Screen):
    """List, create, and launch saved game profiles."""

    BINDINGS = [
        ("b", "back", "Back"),
        ("escape", "back", "Back"),
        ("n", "new_profile", "New"),
        ("h", "view_history", "History"),
        ("q", "force_stop", "Force Stop"),
        ("f9", "force_stop", "Force Stop"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._state = "list"
        self._active_profile: Optional[Profile] = None
        self._process: Optional[Popen] = None
        self._job: Optional[WindowsJobObject] = None
        self._monitor_timer = None

    # --- Compose ---

    def compose(self) -> ComposeResult:
        if self._state == "list":
            yield from self._compose_list()
        elif self._state == "install_running":
            yield from self._compose_running("Installing")
        elif self._state == "game_running":
            yield from self._compose_running("Running")

    def _compose_list(self) -> ComposeResult:
        profiles = self._load_profiles()
        if not profiles:
            items = [ListItem(Label("No profiles found — press 'n' to create one."))]
        else:
            items = [
                ListItem(Label(f"{p.name}  [{p.era.value}]  {'✓' if p.installed else '○'}"), name=p.name)
                for p in profiles
            ]
        yield Container(
            Static("💾 Profiles", classes="title"),
            Static(""),
            ListView(*items, id="profile_list"),
            Static(""),
            Static("Enter: Launch • n: New • b/Esc: Back", classes="help"),
            classes="profile-list-container",
        )

    def _compose_running(self, verb: str) -> ComposeResult:
        name = self._active_profile.name if self._active_profile else ""
        widgets: list = [
            Static(f"🎮 {verb}: {name}", classes="title"),
            Static(""),
            Static("Emulator is running.", classes="status"),
            Static(""),
        ]
        if verb == "Installing":
            widgets += [
                Static("Run the installer inside DOSBox, then close the window when done.", classes="info"),
                Static(""),
            ]
        widgets.append(Static("q/F9: Force Stop", classes="help"))
        yield Container(*widgets, classes="profile-running-container")

    # --- Lifecycle ---

    def on_mount(self) -> None:
        self._focus_list()

    def _focus_list(self) -> None:
        try:
            self.query_one("#profile_list", ListView).focus()
        except Exception:
            self.focus()

    def _load_profiles(self) -> list[Profile]:
        result = []
        for path in list_profiles(_profiles_dir()):
            try:
                result.append(load(path))
            except ValueError as exc:
                self.notify(
                    f"Could not load '{path.name}': {exc}",
                    severity="warning",
                    timeout=8,
                )
        return result

    # --- List actions ---

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if self._state != "list" or not event.item.name:
            return
        profile_name = event.item.name
        profiles = self._load_profiles()
        profile = next((p for p in profiles if p.name == profile_name), None)
        if profile is None:
            return
        self._launch_profile(profile)

    def action_new_profile(self) -> None:
        if self._state == "list":
            self._start_create_name()

    def action_view_history(self) -> None:
        if self._state != "list":
            return
        try:
            lv = self.query_one("#profile_list", ListView)
            item = lv.highlighted_child
            if item is None or not item.name:
                return
            profiles = self._load_profiles()
            profile = next((p for p in profiles if p.name == item.name), None)
            if profile is None:
                return
            self.app.push_screen(HistoryModal(profile))
        except Exception:
            pass

    def action_back(self) -> None:
        if self._state in ("install_running", "game_running"):
            return
        from screens.main_menu import MainMenuScreen
        self.app.switch_screen(MainMenuScreen())

    def action_force_stop(self) -> None:
        if self._state not in ("install_running", "game_running"):
            return
        self._stop_monitoring()
        if self._job:
            try:
                self._job.terminate_all()
            except Exception as exc:
                self.app.push_screen(
                    ErrorScreen("Force stop error", str(exc), on_dismiss=lambda: None)
                )
        self._process = None
        self._job = None
        self._state = "list"
        self.refresh(recompose=True)
        self.call_after_refresh(self._focus_list)

    # --- Create flow ---

    def _start_create_name(self) -> None:
        def on_name(value: Optional[str]) -> None:
            if value is None:
                return
            value = value.strip()
            if not value:
                self.app.push_screen(
                    ErrorScreen("Name cannot be empty.", on_dismiss=lambda: None)
                )
                return
            self._start_create_era(value)

        self.app.push_screen(InputModal("Profile name:", "e.g. Doom"), on_name)

    def _start_create_era(self, name: str) -> None:
        def on_era(era: Optional[Era]) -> None:
            if era is None:
                return
            self._start_create_media(name, era)

        self.app.push_screen(EraSelectModal(), on_era)

    def _start_create_media(self, name: str, era: Era) -> None:
        from screens.game_picker import GamePickerScreen

        def on_media(media_path: Optional[Path]) -> None:
            if media_path is None:
                return
            self._finish_create(name, era, media_path)

        self.app.push_screen(GamePickerScreen(era=era, picker_mode=True), on_media)

    def _finish_create(self, name: str, era: Era, media_path: Path) -> None:
        if not media_path.exists():
            self.app.push_screen(
                ErrorScreen(
                    f"Media file not found: {media_path}",
                    on_dismiss=lambda: None,
                )
            )
            return

        suggested = detect_era(media_path)

        profile = Profile(
            name=name,
            era=era,
            media_path=media_path,
            notes="",
        )
        try:
            generate_conf(profile, _conf_dir(), _profiles_dir())
            ensure_hdd(profile, _hdd_dir(), _profiles_dir())
            self.notify(str(profile.hdd_image_path))
        except Exception as exc:
            self.notify(str(exc), severity="error", timeout=10)
            self.app.push_screen(
                ErrorScreen("Profile creation failed", str(exc), on_dismiss=lambda: None)
            )
            return

        append_history(
            profile,
            _profiles_dir(),
            "user",
            [
                {"field": "name",       "old": None, "new": name},
                {"field": "era",        "old": None, "new": era.value},
                {"field": "media_path", "old": None, "new": str(media_path)},
            ],
        )

        self._state = "list"
        self.refresh(recompose=True)
        self.call_after_refresh(self._focus_list)

        self.notify(f"Profile '{name}' created. Press Enter to launch.", timeout=5)

        if suggested is not None and suggested != era:
            self.notify(
                f"Note: auto-detection suggested era '{suggested.value}'. "
                f"Profile saved with your selection: '{era.value}'.",
                severity="information",
                timeout=6,
            )

    # --- Launch flow ---

    def _launch_profile(self, profile: Profile) -> None:
        self._active_profile = profile
        dosbox_executable = settings.get_binary_path("dosbox")
        if not dosbox_executable:
            self.app.push_screen(
                ErrorScreen(
                    "DOSBox-X not found",
                    "Set DOSBOX_PATH in .env, add an override in Settings, "
                    "or drop dosbox-x.exe into emulators/dosbox-x/.",
                    on_dismiss=lambda: None,
                )
            )
            return
        if not profile.installed:
            self._run_install(profile, dosbox_executable)
        else:
            self._run_game(profile, dosbox_executable)

    def _run_install(self, profile: Profile, dosbox_executable: str) -> None:
        try:
            process, job = launch_install(profile, dosbox_executable)
            self._process = process
            self._job = job
            self._state = "install_running"
            self.refresh(recompose=True)
            self._start_monitoring()
            if not job.job_handle:
                self.notify(
                    "Process isolation unavailable — running without Job Objects. "
                    "Network firewall is active.",
                    severity="warning",
                    timeout=8,
                )
        except Exception as exc:
            def _reset_install() -> None:
                def _do() -> None:
                    self._state = "list"
                    self.refresh(recompose=True)
                self.call_after_refresh(_do)
            self.app.push_screen(
                ErrorScreen("Install launch failed", str(exc), on_dismiss=_reset_install)
            )

    def _run_game(self, profile: Profile, dosbox_executable: str) -> None:
        try:
            process, job = launch_game(profile, dosbox_executable)
            self._process = process
            self._job = job
            self._state = "game_running"
            self.refresh(recompose=True)
            self._start_monitoring()
            if not job.job_handle:
                self.notify(
                    "Process isolation unavailable — running without Job Objects. "
                    "Network firewall is active.",
                    severity="warning",
                    timeout=8,
                )
        except Exception as exc:
            def _reset_game() -> None:
                def _do() -> None:
                    self._state = "list"
                    self.refresh(recompose=True)
                self.call_after_refresh(_do)
            self.app.push_screen(
                ErrorScreen("Launch failed", str(exc), on_dismiss=_reset_game)
            )

    # --- Process monitoring ---

    def _start_monitoring(self) -> None:
        if self._monitor_timer is None:
            self._monitor_timer = self.set_interval(1.0, self._check_process)

    def _stop_monitoring(self) -> None:
        if self._monitor_timer is not None:
            self._monitor_timer.stop()
            self._monitor_timer = None

    def _check_process(self) -> None:
        if self._state not in ("install_running", "game_running"):
            self._stop_monitoring()
            return
        if self._process and self._process.poll() is not None:
            self._on_process_exited()

    def _on_process_exited(self) -> None:
        self._stop_monitoring()
        was_install = self._state == "install_running"
        job_error: Optional[str] = None
        if self._job:
            try:
                self._job.terminate_all()
            except Exception as exc:
                job_error = str(exc)
        self._process = None
        self._job = None
        if was_install and self._active_profile is not None:
            profile_name = self._active_profile.name
            self._active_profile.installed = True
            try:
                save(self._active_profile, _profiles_dir())
                append_history(
                    self._active_profile,
                    _profiles_dir(),
                    "user",
                    [{"field": "installed", "old": False, "new": True}],
                )
                self.notify(
                    f"'{profile_name}' installed and ready to launch.",
                    timeout=6,
                )
            except Exception as exc:
                self.app.push_screen(
                    ErrorScreen("Failed to save profile", str(exc), on_dismiss=lambda: None)
                )
        self._active_profile = None
        self._state = "list"
        self.refresh(recompose=True)
        self.call_after_refresh(self._focus_list)
        if job_error:
            self.app.push_screen(
                ErrorScreen("Job cleanup error", job_error, on_dismiss=lambda: None)
            )

