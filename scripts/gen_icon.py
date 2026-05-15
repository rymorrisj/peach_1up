"""Generate the placeholder tray icon at assets/peach1up.png."""
from pathlib import Path

from PIL import Image

OUTPUT = Path(__file__).resolve().parent.parent / "assets" / "peach1up.png"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

img = Image.new("RGBA", (16, 16), (255, 138, 92, 255))
img.save(OUTPUT, "PNG")
print(f"Written: {OUTPUT}")
