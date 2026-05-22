#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo " Peach 1UP - Setup and Start (Unix)"
echo "============================================================"
echo

# ── Python check ────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found."
  echo "Install Python 3.11 or later from https://www.python.org/downloads/"
  exit 1
fi

PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYMAJOR=${PYVER%%.*}
PYMINOR=${PYVER#*.}

if [ "$PYMAJOR" -lt 3 ] || { [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 11 ]; }; then
  echo "ERROR: Python 3.11 or later is required. Found $PYVER."
  exit 1
fi
echo "[OK] Python $PYVER"

# ── Node / npm check ────────────────────────────────────────────
if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm not found."
  echo "Install Node.js from https://nodejs.org/"
  exit 1
fi
echo "[OK] Node.js $(node --version)"

# ── Virtual environment ────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
  echo "[OK] Virtual environment created at .venv/"
else
  echo "[OK] Virtual environment already exists at .venv/"
fi

# ── Activate venv and install backend deps ─────────────────────
echo "Installing backend dependencies..."
# shellcheck source=/dev/null
source .venv/bin/activate
python3 -m pip install --upgrade pip -q
python3 -m pip install -r backend/requirements.txt
echo "[OK] Backend dependencies installed"

# ── Frontend deps ──────────────────────────────────────────────
echo "Installing frontend dependencies..."
( cd frontend && npm install )
echo "[OK] Frontend dependencies installed"

# ── Settings check ─────────────────────────────────────────────
if [ ! -f "config/settings.yaml" ]; then
  echo
  echo "WARNING: config/settings.yaml not found."
  echo "Copy config/settings.yaml.template to config/settings.yaml and fill in paths."
else
  echo "[OK] config/settings.yaml found"
fi

# ── Sandbox build check ────────────────────────────────────────
# sandbox_host.exe is a Windows-only artifact; no build step is run on Unix.
if [ ! -f "backend/service/utils/sandbox/sandbox_host.exe" ]; then
  echo
  echo "NOTICE: backend/service/utils/sandbox/sandbox_host.exe not found."
  echo "sandbox_host.exe is a Windows-only artifact and is not required on this platform."
  echo "To build it for a Windows deployment, run build.sh from an MSYS2 UCRT64 shell."
else
  echo "[OK] sandbox_host.exe found"
fi

# ── Generate API types ─────────────────────────────────────────
echo "Exporting OpenAPI spec..."
python3 scripts/export_openapi.py
if [ $? -ne 0 ]; then
  echo "ERROR: OpenAPI export failed. Aborting."
  exit 1
fi
echo "Generating frontend API types..."
( cd frontend && npm run generate:api )
if [ $? -ne 0 ]; then
  echo "ERROR: API type generation failed. Aborting."
  exit 1
fi
echo "[OK] API types generated"

# ── Merge emulator manifests ───────────────────────────────────
echo "Merging emulator manifests..."
python3 scripts/merge_emulators.py
if [ $? -ne 0 ]; then
  echo "ERROR: Failed to merge emulator manifests."
  exit 1
fi
echo "[OK] Emulator manifests merged"

# ── Environment and start services ─────────────────────────────
export PEACH_ENV=development

FRONTEND_PID=""

cleanup() {
  if [ -n "$FRONTEND_PID" ]; then
    echo
    echo "Stopping frontend (PID $FRONTEND_PID)..."
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo
echo "Starting Peach 1UP frontend..."
( cd frontend && npm run dev ) &
FRONTEND_PID=$!
echo "Frontend starting at http://localhost:5173"

echo
echo "Starting Peach 1UP backend..."
echo "Backend will be available at http://localhost:8000"
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

echo
echo "Backend stopped."