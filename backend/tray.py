import logging
import os
import signal
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import pystray
from PIL import Image

logger = logging.getLogger(__name__)

_ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "peach1up.png"
_APP_URL = "http://localhost:8000"
_icon: pystray.Icon | None = None


def _load_image() -> Image.Image:
    try:
        return Image.open(_ICON_PATH)
    except Exception:
        return Image.new("RGBA", (16, 16), (255, 138, 92, 255))


def _on_open(icon, item) -> None:
    webbrowser.open(_APP_URL)


def _on_restart(icon, item) -> None:
    icon.stop()
    subprocess.Popen(
        [sys.executable] + sys.argv,
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )
    os.kill(os.getpid(), signal.SIGINT)


def _on_quit(icon, item) -> None:
    icon.stop()
    os.kill(os.getpid(), signal.SIGINT)


def _run() -> None:
    global _icon
    menu = pystray.Menu(
        pystray.MenuItem("Open", _on_open, default=True),
        pystray.MenuItem("Restart", _on_restart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _on_quit),
    )
    _icon = pystray.Icon("Peach 1UP", _load_image(), "Peach 1UP", menu)
    try:
        _icon.run()
    except Exception as exc:
        logger.warning("Tray icon unavailable: %s", exc)


def start() -> threading.Thread:
    t = threading.Thread(target=_run, daemon=True, name="tray")
    t.start()
    return t


def stop() -> None:
    global _icon
    if _icon is not None:
        try:
            _icon.stop()
        except Exception:
            pass
        _icon = None
