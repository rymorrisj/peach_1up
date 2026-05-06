#!/usr/bin/env bash
set -e

if ! command -v docker &> /dev/null; then
  echo "ERROR: Docker not found."
  echo "Install Docker Engine from https://docs.docker.com/engine/install/"
  exit 1
fi

echo "Building and starting Peach 1UP..."
docker compose up --build -d

echo "Waiting for backend to be healthy..."
TIMEOUT=60
ELAPSED=0
until curl -sf http://localhost:8000/api/v1/health > /dev/null 2>&1; do
  if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "ERROR: Backend did not become healthy within ${TIMEOUT}s."
    echo "Check logs with: docker compose logs backend"
    exit 1
  fi
  sleep 2
  ELAPSED=$((ELAPSED + 2))
done

echo "Peach 1UP is running at http://localhost:8080"
