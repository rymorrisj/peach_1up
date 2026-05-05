"""OS platform guidance screen for Peach 1UP.

Shown when no platforms are registered. Explains both media paths and
provides sourcing guidance. Read-only — no form, no file I/O, no backend calls.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen, ModalScreen
from textual.widgets import Button, Label, Static
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


class PlatformHealthModal(ModalScreen):
    """Health check results for all registered platforms.

    Shows one line per platform with pass/fail status. For degraded platforms,
    lists each failing check and offers two recovery actions:
    R — re-register via PlatformRegistrationScreen
    S — restore working image from the most recent snapshot (if available)
    """

    DEFAULT_CSS = """
    PlatformHealthModal { align: center middle; }
    #health-panel {
        width: 74;
        height: auto;
        max-height: 88vh;
        border: round $primary;
        padding: 1 2;
    }
    .health-ok     { color: $success; }
    .health-fail   { color: $error; text-style: bold; }
    .health-issue  { margin-left: 4; color: $warning; }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("r", "re_register", "Re-register"),
        Binding("s", "restore_snapshot", "Restore snapshot"),
    ]

    def __init__(self, results: list) -> None:
        super().__init__()
        self._results = results

    def compose(self) -> ComposeResult:
        rows: list = [
            Static("Platform Health Check", classes="title"),
            Static(""),
        ]

        if not self._results:
            rows.append(Static("No platforms registered."))
        else:
            healthy   = [r for r in self._results if r.is_healthy]
            degraded  = [r for r in self._results if not r.is_healthy]

            for r in healthy:
                rows.append(Static(
                    f"  ✓  {r.platform.name}  ({r.platform.era})",
                    classes="health-ok",
                ))

            if degraded:
                if healthy:
                    rows.append(Static(""))
                rows.append(Static("Degraded — action required:", classes="health-fail"))
                for r in degraded:
                    rows.append(Static(
                        f"  ✗  {r.platform.name}  ({r.platform.era})",
                        classes="health-fail",
                    ))
                    for issue in r.issues:
                        rows.append(Static(f"      {issue}", classes="health-issue"))

        rows += [
            Static(""),
            Static(
                "R: Re-register platform  •  S: Restore from snapshot  •  Esc/q: Close",
                classes="help",
            ),
        ]
        yield VerticalScroll(*rows, id="health-panel")

    def action_re_register(self) -> None:
        from screens.platform_registration import PlatformRegistrationScreen
        self.app.push_screen(PlatformRegistrationScreen())

    def action_restore_snapshot(self) -> None:
        degraded = [r for r in self._results if not r.is_healthy]
        if not degraded:
            return

        for result in degraded:
            p = result.platform
            if p.working_image_path is None:
                continue
            from utils.image_manager import list_snapshots, restore_snapshot
            snapshots = list_snapshots(p.working_image_path)
            if not snapshots:
                continue
            most_recent = snapshots[-1]
            try:
                restore_snapshot(most_recent, p.working_image_path)
                from screens.error import ErrorScreen
                self.app.push_screen(ErrorScreen(
                    "Snapshot restored",
                    f"Platform '{p.name}' restored from {most_recent.name}.\n"
                    "Dismiss to close the health check.",
                    on_dismiss=self.dismiss,
                ))
            except Exception as exc:
                from screens.error import ErrorScreen
                self.app.push_screen(ErrorScreen(
                    "Restore failed",
                    str(exc),
                    on_dismiss=lambda: None,
                ))
            return

        from screens.error import ErrorScreen
        self.app.push_screen(ErrorScreen(
            "No snapshots available",
            "No snapshots were found for any degraded platform.\n"
            "Use R to re-register the platform instead.",
            on_dismiss=lambda: None,
        ))
