"""OS platform guidance screen for Peach 1UP.

Shown when no platforms are registered. Explains both media paths and
provides sourcing guidance. Read-only — no form, no file I/O, no backend calls.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Label
from textual.containers import Horizontal, VerticalScroll


class PlatformGuidanceScreen(Screen):
    """Informational screen shown when no OS platforms are registered."""

    DEFAULT_CSS = """
    PlatformGuidanceScreen {
        align: center middle;
    }

    #panel {
        width: 72;
        height: auto;
        max-height: 90vh;
        border: round $primary;
        padding: 1 2;
    }

    #panel-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    .section-heading {
        text-style: bold;
        margin-top: 1;
    }

    .section-body {
        margin-left: 2;
    }

    .notice {
        color: $warning;
        margin-left: 2;
    }

    .legal {
        color: $warning;
        margin-top: 1;
    }

    #button-row {
        margin-top: 2;
        height: auto;
        align: center middle;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="panel"):
            yield Label("OS Platforms — Getting Started", id="panel-title")

            yield Label("Pre-installed HDD image  (recommended)", classes="section-heading")
            yield Label(
                "The OS and any software are already present on the image. "
                "Register it, and Peach 1UP will launch directly — no installation step required.",
                classes="section-body",
            )
            yield Label(
                "Two copies of the image will be stored on disk: a locked base and an active "
                "working copy. Disk usage will grow over time.",
                classes="notice",
            )

            yield Label("Original installer media", classes="section-heading")
            yield Label(
                "Provide an installer ISO or disc image. Peach 1UP mounts the media and boots "
                "the platform. You complete the installation manually inside the emulator.",
                classes="section-body",
            )
            yield Label(
                "You will need to complete the installation manually inside the emulator.",
                classes="notice",
            )

            yield Label("Sourcing images", classes="section-heading")
            yield Label(
                "WinWorldPC — abandonware OS images and software:  https://winworldpc.com",
                classes="section-body",
            )
            yield Label(
                "Internet Archive — legacy software and disc images:  https://archive.org",
                classes="section-body",
            )
            yield Label(
                "Only use images you own or that are legally available as abandonware in your region.",
                classes="legal",
            )

            with Horizontal(id="button-row"):
                yield Button("Register a Platform", variant="primary", id="btn-register")

    @on(Button.Pressed, "#btn-register")
    def _on_register_pressed(self) -> None:
        from screens.platform_registration import PlatformRegistrationScreen
        self.app.push_screen(PlatformRegistrationScreen())
