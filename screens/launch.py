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

from ..utils.constants import Era
from ..utils.backend_router import get_launch_fn
from ..utils.job_objects import WindowsJobObject
from .error import ErrorScreen


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

    def compose(self) -> ComposeResult:
        """Compose the launch screen layout based on current state."""
        if self._state == "confirm":
            yield self._create_confirm_layout()
        elif self._state == "running":
            yield self._create_running_layout()

    def action_launch(self) -> None:
        """Launch emulator with selected era and media file."""
        if self._state != "confirm":
            return

        launch_fn = get_launch_fn(self.era)
        if launch_fn is None:
            # 86Box not implemented yet
            return

        try:
            # Get DOSBox path from env
            dosbox_path = os.getenv('DOSBOX_PATH', '')
            if not dosbox_path:
                self.app.push_screen(
                    ErrorScreen(
                        "Environment Configuration Error",
                        "DOSBOX_PATH environment variable not set",
                        on_dismiss=lambda: self.app.pop_screen()
                    )
                )
                return

            # Launch emulator under Job Objects
            self._process, self._job = launch_fn(
                media_path=self.media_path,
                era=self.era.value,
                dosbox_path=dosbox_path
            )

            # Transition to running state
            self._state = "running"
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
            from .game_picker import GamePickerScreen
            self.app.switch_screen(GamePickerScreen(era=self.era))

    def action_force_stop(self) -> None:
        """Force stop running emulator and return to confirm state."""
        if self._state == "running" and self._job:
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

    def _create_confirm_layout(self) -> Container:
        """
        Create layout for confirm state.

        Returns:
            Container with era, file, backend info and launch confirmation
        """
        launch_fn = get_launch_fn(self.era)
        backend_available = launch_fn is not None

        if backend_available:
            backend_name = "DOSBox-X"
            launch_text = "Press Enter to launch"
        else:
            backend_name = "86Box"
            launch_text = "86Box support coming in P0-9"

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
        # Determine backend name from era
        if self.era.value in ['dos', 'win31']:
            backend_name = "DOSBox-X"
        else:  # win95, win98, winxp
            backend_name = "86Box"

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