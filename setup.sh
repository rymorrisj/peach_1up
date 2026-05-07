#!/usr/bin/env bash
set -e

echo "============================================================"
echo " Peach 1UP - First-run setup"
echo "============================================================"
echo

# ── Python check ─────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found."
  echo "Install Python 3.11 or later from https://www.python.org/downloads/"
  exit 1
fi

PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYMAJOR=$(echo "$PYVER" | cut -d. -f1)
PYMINOR=$(echo "$PYVER" | cut -d. -f2)

if [ "$PYMAJOR" -lt 3 ] || { [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 11 ]; }; then
  echo "ERROR: Python 3.11 or later is required. Found $PYVER."
  exit 1
fi
echo "[OK] Python $PYVER"

# ── Node / npm check ─────────────────────────────────────────────
if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm not found."
  echo "Install Node.js from https://nodejs.org/"
  exit 1
fi
echo "[OK] Node.js $(node --version)"

# ── Virtual environment ───────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
  echo "[OK] Virtual environment created at .venv/"
else
  echo "[OK] Virtual environment already exists at .venv/"
fi

# ── Activate venv and install backend deps ────────────────────────
echo "Installing backend dependencies..."
# shellcheck source=/dev/null
source .venv/bin/activate
python3 -m pip install --upgrade pip -q
python3 -m pip install -r backend/requirements.txt
echo "[OK] Backend dependencies installed"

# ── Frontend deps ─────────────────────────────────────────────────
echo "Installing frontend dependencies..."
(cd frontend && npm install)
echo "[OK] Frontend dependencies installed"

# ── Settings check ────────────────────────────────────────────────
if [ ! -f "config/settings.yaml" ]; then
  echo
  echo "WARNING: config/settings.yaml not found."
  echo "Copy config/settings.yaml.template to config/settings.yaml and fill in paths."
else
  echo "[OK] config/settings.yaml found"
fi

echo
echo "============================================================"
echo " Setup complete!"
echo "============================================================"
echo
echo "Next steps:"
echo "  1. Activate the virtual environment:  source .venv/bin/activate"
echo "  2. Start the app:                     ./start.sh"
echo
echo "The app will be available at:"
echo "  Frontend:  http://localhost:5173"
echo "  Backend:   http://localhost:8000"
echo
