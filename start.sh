#!/usr/bin/env bash
set -e

if ! python3 --version 2>&1 | grep -qE "Python 3\.(1[1-9]|[2-9][0-9])"; then
  echo "ERROR: Python 3.11 or later is required."
  echo "Install it from https://www.python.org/downloads/"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: Node.js / npm not found. Install Node.js from https://nodejs.org/"
  exit 1
fi

if [ ! -f "config/settings.yaml" ]; then
  echo "WARNING: config/settings.yaml not found. Backend may not start correctly."
  echo "Copy config/settings.yaml.template to config/settings.yaml and fill in paths."
fi

export PEACH_ENV=development

FRONTEND_PID=""

cleanup() {
  if [ -n "$FRONTEND_PID" ]; then
    echo ""
    echo "Stopping frontend (PID $FRONTEND_PID)..."
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "Starting Peach 1UP frontend..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!
echo "Frontend starting at http://localhost:5173"

echo "Starting Peach 1UP backend..."
echo "Backend will be available at http://localhost:8000"
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
