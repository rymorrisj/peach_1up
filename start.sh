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
python3 -m pip install -r backend/requirements-dev.txt
echo "[OK] Backend dependencies installed"

# ── Frontend deps ─────────────────────────────────────────────
echo "Installing frontend dependencies..."
( cd frontend && npm install )
echo "[OK] Frontend dependencies installed"

# ── Sandbox build check ────────────────────────────────────────
# sandbox_host.exe is a Windows-only artifact; no build step is run on Unix.
if [ ! -f "backend/service/utils/platform/windows/sandbox/sandbox_host.exe" ]; then
  echo
  echo "NOTICE: backend/service/utils/platform/windows/sandbox/sandbox_host.exe not found."
  echo "sandbox_host.exe is a Windows-only artifact and is not required on this platform."
  echo "To build it for a Windows deployment, run backend/service/utils/platform/windows/sandbox/build.sh from an MSYS2 UCRT64 shell."
else
  echo "[OK] sandbox_host.exe found"
fi

# ── Generate constants ──────────────────────────────────────────
# Must run before export_and_build_types.py below — constants_generated.py
# feeds the SQLModel tables that backend.api.routes.ROUTERS pulls in.
echo "Generating constants..."
python3 scripts/gen_constants.py
if [ $? -ne 0 ]; then
  echo "ERROR: Constants generation failed. Aborting."
  exit 1
fi
echo "[OK] Constants generated"

# ── Generate API types ─────────────────────────────────────────
echo "Generating OpenAPI spec and frontend types..."
python3 scripts/export_and_build_types.py
if [ $? -ne 0 ]; then
  echo "ERROR: Type generation failed. Aborting."
  exit 1
fi

# ── Environment and start services ─────────────────────────────
export PEACH_ENV=development

echo
echo "Starting Peach 1UP (frontend :5173, backend :8000)..."
( cd frontend && npm run dev ) &
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

echo
echo "Backend stopped."