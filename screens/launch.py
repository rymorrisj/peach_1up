"""
Launch screen for Peach 1UP.
Handles emulator confirmation, launch, and process management.
"""

import os
from pathlib import Path
from subprocess import Popen
from typing import Optional

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static
from textual.containers import Container

from utils.constants import Era
from utils.backend_router import get_launch_fn, get_backend_name, get_executable_path
from utils.job_objects import WindowsJobObject
from screens.error import ErrorScreen


class LaunchScreen(Screen):
    """
    Launch confirmation and process management screen.

    Key bindings:
    - Enter: Launch emulator (from confirm state)
    - b/Escape: Back to game picker (from confirm state)
    - q/F9: Force stop emulator (from running state)

    States:
    - "confirm": Shows launch details and confirmation prompt
    - "running": Shows running status with force stop option

    Layout varies by state:
    - Confirm: era, filename, backend, launch button, back option
    - Running: emulator status, force stop instructions
    """

    BINDINGS = [
        ("enter", "launch", "Launch"),
        ("b", "back", "Back"),
        ("escape", "back", "Back"),
        ("q", "force_stop", "Force Stop"),
        ("f9", "force_stop", "Force Stop"),
    ]

    def __init__(self, era: Era, media_path: Path):
        """
        Initialize launch screen for era and media file.

        Args:
            era: Gaming era for the selected media
            media_path: Path to the media file to launch
        """
        super().__init__()
        self.era = era
        self.media_path = media_path
        self._state = "confirm"
        self._process: Optional[Popen] = None
        self._job: Optional[WindowsJobObject] = None
        self._monitor_timer = None

    def compose(self) -> ComposeResult:
        """Compose the launch screen layout based on current state."""
        if self._state == "confirm":
            yield self._create_confirm_layout()
        elif self._state == "running":
            yield self._create_running_layout()

    def on_mount(self) -> None:
        """Set focus when screen loads for keyboard navigation."""
        self.focus()

    def action_launch(self) -> None:
        """Launch emulator with selected era and media file."""
        if self._state != "confirm":
            return

        try:
            launch_fn = get_launch_fn(self.era)
        except (ValueError, RuntimeError) as e:
            self.app.push_screen(
                ErrorScreen(
                    "Backend Error",
                    str(e),
                    on_dismiss=lambda: self.app.pop_screen()
                )
            )
            return

        try:
            # Get appropriate emulator path based on era
            executable_path, emulator_env_var = get_executable_path(self.era)

            if not executable_path:
                self.app.push_screen(
                    ErrorScreen(
                        "Environment Configuration Error",
                        f"{emulator_env_var} environment variable not set",
                        on_dismiss=lambda: self.app.pop_screen()
                    )
                )
                return

            # Launch emulator under Job Objects - unified interface
            self._process, self._job = launch_fn(
                media_path=self.media_path,
                era=self.era.value,
                executable_path=executable_path
            )

            # Transition to running state and start monitoring
            self._state = "running"
            self._start_process_monitoring()
            self.refresh()

        except Exception as e:
            self.app.push_screen(
                ErrorScreen(
                    "Launch Failed",
                    str(e),
                    on_dismiss=lambda: self.app.pop_screen()
                )
            )

    def action_back(self) -> None:
        """Navigate back to game picker (only from confirm state)."""
        if self._state == "confirm":
            from screens.game_picker import GamePickerScreen
            self.app.switch_screen(GamePickerScreen(era=self.era))

    def action_force_stop(self) -> None:
        """Force stop running emulator and return to confirm state."""
        if self._state == "running" and self._job:
            self._stop_process_monitoring()
            try:
                self._job.terminate_all()
                # On successful stop, return to confirm state
                self._process = None
                self._job = None
                self._state = "confirm"
                self.refresh()
            except Exception as e:
                self._process = None
                self._job = None
                self._state = "confirm"
                self.app.push_screen(
                    ErrorScreen(
                        "Force Stop Failed",
                        str(e),
                        on_dismiss=lambda: self.app.pop_screen()
                    )
                )

    def _start_process_monitoring(self) -> None:
        """Start monitoring the emulator process for natural exit."""
        if self._monitor_timer is None:
            self._monitor_timer = self.set_interval(1.0, self._check_process_status)

    def _stop_process_monitoring(self) -> None:
        """Stop monitoring the emulator process."""
        if self._monitor_timer is not None:
            self._monitor_timer.stop()
            self._monitor_timer = None

    def _check_process_status(self) -> None:
        """Check if emulator process is still running."""
        if self._state != "running" or not self._process or not self._job:
            self._stop_process_monitoring()
            return

        # Check if process has exited naturally
        if self._process.poll() is not None or not self._job.is_active():
            self._handle_natural_process_exit()

    def _handle_natural_process_exit(self) -> None:
        """Handle emulator process exiting naturally."""
        self._stop_process_monitoring()

        # Clean up job object if still active
        if self._job and self._job.is_active():
            try:
                self._job.terminate_all()
            except Exception:
                # Ignore cleanup errors on natural exit
                pass

        # Reset state and return to confirm
        self._process = None
        self._job = None
        self._state = "confirm"
        self.refresh()

    def _create_confirm_layout(self) -> Container:
        """
        Create layout for confirm state.

        Returns:
            Container with era, file, backend info and launch confirmation
        """
        backend_error = None
        try:
            launch_fn = get_launch_fn(self.era)
            backend_available = True
        except (ValueError, RuntimeError) as e:
            backend_available = False
            backend_error = str(e)
        backend_name = get_backend_name(self.era)

        if backend_available:
            launch_text = "Press Enter to launch"
        else:
            if backend_error:
                launch_text = f"Backend error: {backend_error}"
            else:
                launch_text = f"{backend_name} backend not implemented"

        widgets = [
            Static("🚀 Launch Game", classes="title"),
            Static(""),
            Static(f"Era: {self.era.value.upper()}", classes="info"),
            Static(f"File: {self.media_path.name}", classes="info"),
            Static(f"Backend: {backend_name}", classes="info"),
            Static(""),
            Static(launch_text, classes="launch-status"),
            Static(""),
            Static("Enter: Launch • b/Esc: Back", classes="help"),
        ]

        return Container(*widgets, classes="launch-confirm-container")

    def _create_running_layout(self) -> Container:
        """
        Create layout for running state.

        Returns:
            Container with running status and force stop instructions
        """
        backend_name = get_backend_name(self.era)

        widgets = [
            Static("🎮 Emulator Running", classes="title"),
            Static(""),
            Static(backend_name, classes="emulator-name"),
            Static(f"Era: {self.era.value.upper()}", classes="info"),
            Static(f"File: {self.media_path.name}", classes="info"),
            Static(""),
            Static("Emulator is running in isolated environment", classes="status"),
            Static(""),
            Static("q/F9: Force Stop", classes="help"),
        ]

        return Container(*widgets, classes="launch-running-container")