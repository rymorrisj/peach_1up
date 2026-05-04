"""Platform registration screen for Peach 1UP."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Input, Label, Select
from textual.containers import Horizontal, Vertical, VerticalScroll

from utils.constants import Era
from utils.platform import OSPlatform, save as platform_save
from utils.backend_router import resolve_backend_name


_VALID_MEDIA_EXTENSIONS = frozenset({".img", ".vhd", ".iso"})

_ERA_OPTIONS: list[tuple[str, str]] = [
    ("Windows 95", "win95"),
    ("Windows 98", "win98"),
    ("Windows XP", "winxp"),
]

_MEDIA_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("Pre-installed image", "preinstalled"),
    ("Installer disc or image", "installer"),
]


def _platforms_path() -> Path:
    return Path("config") / "platforms.yaml"


class PlatformRegistrationScreen(Screen):
    """Form screen for registering a new OS platform."""

    DEFAULT_CSS = """
    PlatformRegistrationScreen {
        align: center middle;
    }

    #form {
        width: 72;
        height: auto;
        max-height: 90vh;
        border: round $primary;
        padding: 1 2;
    }

    #form-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    .field-label {
        margin-top: 1;
    }

    .error {
        color: $error;
        display: none;
    }

    .notice {
        color: $warning;
        display: none;
    }

    #status-success {
        color: $success;
        display: none;
        text-align: center;
        margin-top: 1;
    }

    #accuracy-container {
        display: none;
        margin-top: 1;
    }

    #button-row {
        margin-top: 1;
        height: auto;
        align: right middle;
    }

    #btn-cancel {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="form"):
            yield Label("Register OS Platform", id="form-title")

            yield Label("Platform name", classes="field-label")
            yield Input(placeholder="e.g. Windows 98 SE", id="input-name")
            yield Label("", id="error-name", classes="error")

            yield Label("Era", classes="field-label")
            yield Select(_ERA_OPTIONS, prompt="Select era…", id="select-era")
            yield Label("", id="error-era", classes="error")

            yield Label("Image path", classes="field-label")
            yield Input(
                placeholder="Full path to .img, .vhd, or .iso file",
                id="input-media-path",
            )
            yield Label("", id="error-media-path", classes="error")

            yield Label("Image type", classes="field-label")
            yield Select(
                _MEDIA_TYPE_OPTIONS,
                prompt="Select image type…",
                id="select-media-type",
            )
            yield Label("", id="error-media-type", classes="error")
            yield Label(
                "You will need to complete the installation manually inside the emulator.",
                id="notice-installer",
                classes="notice",
            )

            with Vertical(id="accuracy-container"):
                yield Checkbox(
                    "Hardware accuracy mode"
                    " (slower — only needed for specific hardware requirements)",
                    id="checkbox-accuracy",
                )

            yield Label("Notes (optional)", classes="field-label")
            yield Input(placeholder="", id="input-notes")

            yield Label("", id="status-success")

            with Horizontal(id="button-row"):
                yield Button("Confirm", variant="primary", id="btn-confirm")
                yield Button("Cancel", id="btn-cancel")

    @on(Select.Changed, "#select-era")
    def _on_era_changed(self, event: Select.Changed) -> None:
        show = event.value in ("win95", "win98")
        self.query_one("#accuracy-container").display = show
        if not show:
            self.query_one("#checkbox-accuracy", Checkbox).value = False

    @on(Select.Changed, "#select-media-type")
    def _on_media_type_changed(self, event: Select.Changed) -> None:
        self.query_one("#notice-installer").display = (event.value == "installer")

    @on(Button.Pressed, "#btn-confirm")
    def _on_confirm_pressed(self) -> None:
        self._do_confirm()

    @on(Button.Pressed, "#btn-cancel")
    def _on_cancel_pressed(self) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss()

    def _clear_errors(self) -> None:
        for widget_id in ("error-name", "error-era", "error-media-path", "error-media-type"):
            label = self.query_one(f"#{widget_id}", Label)
            label.update("")
            label.display = False

    def _show_error(self, widget_id: str, message: str) -> None:
        label = self.query_one(f"#{widget_id}", Label)
        label.update(message)
        label.display = True

    def _do_confirm(self) -> None:
        self._clear_errors()
        valid = True

        name = self.query_one("#input-name", Input).value.strip()
        if not name:
            self._show_error("error-name", "Platform name is required.")
            valid = False

        era_raw = self.query_one("#select-era", Select).value
        if era_raw is Select.BLANK:
            self._show_error("error-era", "Please select an era.")
            valid = False
            era_raw = None

        media_path_str = self.query_one("#input-media-path", Input).value.strip()
        if not media_path_str:
            self._show_error("error-media-path", "Image path is required.")
            valid = False
        else:
            media_path = Path(media_path_str)
            if not media_path.exists():
                self._show_error(
                    "error-media-path", f"File not found: {media_path_str}"
                )
                valid = False
            elif media_path.suffix.lower() not in _VALID_MEDIA_EXTENSIONS:
                self._show_error(
                    "error-media-path",
                    f"Unsupported extension '{media_path.suffix}'. "
                    f"Accepted: {', '.join(sorted(_VALID_MEDIA_EXTENSIONS))}",
                )
                valid = False

        if not valid:
            return

        media_path = Path(media_path_str)

        media_type_raw = self.query_one("#select-media-type", Select).value
        if media_type_raw is Select.BLANK:
            self._show_error("error-media-type", "Please select an image type.")
            return
        media_path_type = str(media_type_raw)

        accuracy_mode = False
        if era_raw in ("win95", "win98"):
            accuracy_mode = bool(
                self.query_one("#checkbox-accuracy", Checkbox).value
            )

        notes = self.query_one("#input-notes", Input).value.strip()

        try:
            era_enum = Era(era_raw)
        except ValueError:
            self._show_error("error-era", f"Unrecognised era '{era_raw}'.")
            return

        backend = resolve_backend_name(era_enum, accuracy_mode)

        platform = OSPlatform(
            name=name,
            era=str(era_raw),
            backend=backend,
            accuracy_mode=accuracy_mode,
            base_image_path=media_path,
            media_path_type=media_path_type,
            notes=notes,
            status="registered",
        )

        platform_save(platform, _platforms_path())

        self.query_one("#status-success", Label).update(
            "Platform registered successfully."
        )
        self.query_one("#status-success").display = True
        self.query_one("#btn-confirm", Button).disabled = True
