"""Generate the placeholder tray icon: assets/peach1up.png (runtime tray icon,
see backend/tray.py) and assets/peach1up.ico (PyInstaller exe icon, see
peach1up.spec) from the same source image."""
from pathlib import Path

from PIL import Image

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
PNG_OUTPUT = ASSETS_DIR / "peach1up.png"
ICO_OUTPUT = ASSETS_DIR / "peach1up.ico"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

img = Image.new("RGBA", (16, 16), (255, 138, 92, 255))
img.save(PNG_OUTPUT, "PNG")
print(f"Written: {PNG_OUTPUT}")

img.save(ICO_OUTPUT, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
print(f"Written: {ICO_OUTPUT}")
