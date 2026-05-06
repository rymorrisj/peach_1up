#!/usr/bin/env bash
set -e

if ! python3 --version 2>&1 | grep -E "Python 3\.(11|12|13)" > /dev/null; then
  echo "ERROR: Python 3.11 or later is required."
  echo "Install it from https://www.python.org/downloads/"
  exit 1
fi

if [ ! -f "config/settings.yaml" ]; then
  echo "WARNING: config/settings.yaml not found. Backend may not start correctly."
  echo "Copy config/settings.yaml.template to config/settings.yaml and fill in paths."
fi

export PEACH_ENV=development

echo "Starting Peach 1UP backend..."
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
echo "Backend running at http://localhost:8000 — open http://localhost:8000/api/docs to verify"
echo "For the frontend run: cd frontend && npm run dev"
