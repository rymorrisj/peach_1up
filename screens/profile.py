"""Profile management screen for Peach 1UP."""

from __future__ import annotations

import os
from pathlib import Path
from subprocess import Popen
from typing import Optional

from textual.app import ComposeResult
from textual.screen import Screen, ModalScreen
from textual.widgets import Static, ListView, ListItem, Label, Input
from textual.containers import Container

from utils.constants import Era
from utils.profile import Profile, load, list_profiles, save
from utils.dosbox_config import generate_conf
from utils.vhd import ensure_hdd
from utils.media_detect import detect_era
from utils.backend_router import get_executable_path
from utils.job_objects import WindowsJobObject
from backends.dosbox import launch_install, launch_game
from screens.error import ErrorScreen


def _profiles_dir() -> Path:
    return Path(os.getenv("PROFILES_PATH", "profiles"))


def _conf_dir() -> Path:
    return _profiles_dir() / "conf"


def _hdd_dir() -> Path:
    return Path("images") / "hdd"


def _validate_exe_path(path_str: str) -> str:
    """Return an error message if invalid, empty string if valid."""
    if not path_str:
        return "Path cannot be empty."
    if len(path_str) >= 2 and path_str[1] == ':':
        return "Path must be relative to C: — remove the drive letter (e.g. DOOM\\DOOM.EXE)."
    if path_str.startswith('/') or path_str.startswith('\\'):
        return "Path must be relative — remove the leading backslash."
    return ""


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


class ProfileScreen(Screen):
    """List, create, and launch saved game profiles."""

    BINDINGS = [
        ("b", "back", "Back"),
        ("escape", "back", "Back"),
        ("n", "new_profile", "New"),
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
        self._exe_error: str = ""

    # --- Compose ---

    def compose(self) -> ComposeResult:
        if self._state == "list":
            yield from self._compose_list()
        elif self._state == "install_running":
            yield from self._compose_running("Installing")
        elif self._state == "exe_input":
            yield from self._compose_exe_input()
        elif self._state == "game_running":
            yield from self._compose_running("Running")

    def _compose_list(self) -> ComposeResult:
        profiles = self._load_profiles()
        if not profiles:
            items = [ListItem(Label("No profiles found — press 'n' to create one."))]
        else:
            items = [
                ListItem(Label(f"{p.name}  [{p.era.value}]"), name=p.name)
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
        yield Container(
            Static(f"🎮 {verb}: {name}", classes="title"),
            Static(""),
            Static("Emulator is running in isolated environment.", classes="status"),
            Static(""),
            Static("q/F9: Force Stop", classes="help"),
            classes="profile-running-container",
        )

    def _compose_exe_input(self) -> ComposeResult:
        widgets: list = [
            Static("✅ Installation complete", classes="title"),
            Static(""),
            Static(
                "Enter the path to the game executable relative to C:",
                classes="info",
            ),
            Static("Example:  DOOM\\DOOM.EXE", classes="info"),
            Static(""),
            Input(placeholder="GAME\\GAME.EXE", id="exe_input"),
        ]
        if self._exe_error:
            widgets += [Static(""), Static(self._exe_error, classes="error-message")]
        widgets += [Static(""), Static("Enter: Confirm", classes="help")]
        yield Container(*widgets, classes="profile-exe-container")

    # --- Lifecycle ---

    def on_mount(self) -> None:
        self._focus_list()

    def _focus_list(self) -> None:
        try:
            self.query_one("#profile_list", ListView).focus()
        except Exception:
            self.focus()

    def _focus_exe_input(self) -> None:
        try:
            self.query_one("#exe_input", Input).focus()
        except Exception:
            self.focus()

    def _load_profiles(self) -> list[Profile]:
        result = []
        for path in list_profiles(_profiles_dir()):
            try:
                result.append(load(path))
            except ValueError:
                pass
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

    def action_back(self) -> None:
        if self._state in ("install_running", "game_running"):
            return
        from screens.main_menu import MainMenuScreen
        self.app.switch_screen(MainMenuScreen())

    def action_force_stop(self) -> None:
        if self._state not in ("install_running", "game_running"):
            return
        was_install = self._state == "install_running"
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
        if was_install:
            self._exe_error = ""
            self._state = "exe_input"
        else:
            self._state = "list"
        self.refresh(recompose=True)
        self.call_after_refresh(self._post_recompose_focus)

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
        def on_media(value: Optional[str]) -> None:
            if value is None:
                return
            value = value.strip()
            media_path = Path(value)
            if not media_path.exists():
                self.app.push_screen(
                    ErrorScreen(
                        "Media file not found.",
                        str(media_path),
                        on_dismiss=lambda: self._start_create_media(name, era),
                    )
                )
                return
            if media_path.suffix.lower() not in {".iso", ".img", ".cue"}:
                self.app.push_screen(
                    ErrorScreen(
                        f"Unsupported file type: {media_path.suffix}",
                        "Accepted: .iso  .img  .cue",
                        on_dismiss=lambda: self._start_create_media(name, era),
                    )
                )
                return
            self._finish_create(name, era, media_path)

        self.app.push_screen(
            InputModal(
                "Full path to media file (.iso / .img / .cue):",
                r"C:\path\to\game.iso",
            ),
            on_media,
        )

    def _finish_create(self, name: str, era: Era, media_path: Path) -> None:
        suggested = detect_era(media_path)

        backend = "dosbox" if era.value in ("dos", "win31") else "86box"
        profile = Profile(
            name=name,
            era=era,
            media_path=media_path,
            backend=backend,
            dosbox_conf_path=Path(""),
            hdd_image_path=Path(""),
            executable_path=Path(""),
            notes="",
        )
        try:
            generate_conf(profile, _conf_dir(), _profiles_dir())
            ensure_hdd(profile, _hdd_dir(), _profiles_dir())
        except Exception as exc:
            self.app.push_screen(
                ErrorScreen("Profile creation failed", str(exc), on_dismiss=lambda: None)
            )
            return

        self._state = "list"
        self.refresh(recompose=True)
        self.call_after_refresh(self._focus_list)

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
        dosbox_executable, env_var = get_executable_path(profile.era)
        if not dosbox_executable:
            self.app.push_screen(
                ErrorScreen(
                    "Emulator not configured",
                    f"{env_var} is not set in .env",
                    on_dismiss=lambda: None,
                )
            )
            return
        if profile.executable_path == Path(""):
            self._run_install(profile, dosbox_executable)
        else:
            self._run_game(profile, dosbox_executable)

    def _run_install(self, profile: Profile, dosbox_executable: str) -> None:
        try:
            process, job = launch_install(profile, dosbox_executable)
        except Exception as exc:
            self.app.push_screen(
                ErrorScreen("Install launch failed", str(exc), on_dismiss=lambda: None)
            )
            return
        self._process = process
        self._job = job
        self._state = "install_running"
        self.refresh(recompose=True)
        self._start_monitoring()

    def _run_game(self, profile: Profile, dosbox_executable: str) -> None:
        try:
            process, job = launch_game(profile, dosbox_executable)
        except Exception as exc:
            self.app.push_screen(
                ErrorScreen("Launch failed", str(exc), on_dismiss=lambda: None)
            )
            return
        self._process = process
        self._job = job
        self._state = "game_running"
        self.refresh(recompose=True)
        self._start_monitoring()

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
        if was_install:
            self._exe_error = ""
            self._state = "exe_input"
            self.refresh(recompose=True)
            self.call_after_refresh(self._focus_exe_input)
        else:
            self._state = "list"
            self.refresh(recompose=True)
            self.call_after_refresh(self._focus_list)
        if job_error:
            self.app.push_screen(
                ErrorScreen("Job cleanup error", job_error, on_dismiss=lambda: None)
            )

    # --- Exe input state ---

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._state != "exe_input":
            return
        path_str = event.value.strip()
        error = _validate_exe_path(path_str)
        if error:
            self._exe_error = error
            self.refresh(recompose=True)
            self.call_after_refresh(self._focus_exe_input)
            return
        if self._active_profile is None:
            return
        self._active_profile.executable_path = Path(path_str)
        try:
            save(self._active_profile, _profiles_dir())
        except Exception as exc:
            self._exe_error = f"Failed to save profile: {exc}"
            self.refresh(recompose=True)
            self.call_after_refresh(self._focus_exe_input)
            return
        self._active_profile = None
        self._exe_error = ""
        self._state = "list"
        self.refresh(recompose=True)
        self.call_after_refresh(self._focus_list)

    def _post_recompose_focus(self) -> None:
        if self._state == "exe_input":
            self._focus_exe_input()
        else:
            self._focus_list()
