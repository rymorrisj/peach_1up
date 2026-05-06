@echo off
setlocal

docker --version > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Docker not found.
    echo Install Docker Engine from https://docs.docker.com/engine/install/
    exit /b 1
)

echo Building and starting Peach 1UP...
docker compose up --build -d
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: docker compose up failed.
    exit /b 1
)

echo Waiting for backend to be healthy...
set TIMEOUT=60
set ELAPSED=0

:poll
curl -sf http://localhost:8000/api/v1/health > nul 2>&1
if %ERRORLEVEL% EQU 0 goto healthy
if %ELAPSED% GEQ %TIMEOUT% (
    echo ERROR: Backend did not become healthy within %TIMEOUT%s.
    echo Check logs with: docker compose logs backend
    exit /b 1
)
timeout /t 2 /nobreak > nul
set /a ELAPSED=%ELAPSED%+2
goto poll

:healthy
echo Peach 1UP is running at http://localhost:8080

endlocal
