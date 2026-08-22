@echo off
cd /d "%~dp0"
setlocal

echo ============================================================
echo Peach 1UP - Setup and Start (Windows)
echo ============================================================
echo.

REM ── Python check ─────────────────────────────────────────────
for /f "tokens=2 delims= " %%v in ('py --version 2^>^&1') do set PYVER=%%v
if "%PYVER%"=="" (
    echo ERROR: Python not found.
    echo Install Python 3.14 or later from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    exit /b 1
)

for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)

if %PY_MAJOR% LSS 3 (
    echo ERROR: Python 3.14 or later is required. Found %PYVER%.
    exit /b 1
)

if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 14 (
    echo ERROR: Python 3.14 or later is required. Found %PYVER%.
    exit /b 1
)

echo [OK] Python %PYVER%

REM ── Node / npm check ─────────────────────────────────────────
where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js / npm not found.
    exit /b 1
)

for /f "tokens=*" %%n in ('node --version 2^>^&1') do set NODEVER=%%n
echo [OK] Node.js %NODEVER%

REM ── uv check ──────────────────────────────────────────────────
where uv >nul 2>&1
if errorlevel 1 (
    echo ERROR: uv not found.
    echo Install uv from https://docs.astral.sh/uv/getting-started/installation/
    exit /b 1
)

REM ── Sync venv and backend deps (dev group includes pytest/ruff) ──
echo Syncing backend dependencies via uv...
uv sync --group dev
if errorlevel 1 (
    echo ERROR: Failed to sync backend dependencies.
    exit /b 1
)

echo [OK] Backend dependencies installed

REM ── Frontend deps ────────────────────────────────────────────
echo Installing frontend dependencies...
pushd "frontend"
call npm ci
if errorlevel 1 (
    echo ERROR: Failed to install frontend dependencies.
    popd
    exit /b 1
)

popd
echo [OK] Frontend dependencies installed

REM ── Docs deps ─────────────────────────────────────────────────
echo Installing docs dependencies...
pushd "docs"
call npm ci
if errorlevel 1 (
    echo ERROR: Failed to install docs dependencies.
    popd
    exit /b 1
)

popd
echo [OK] Docs dependencies installed

REM ── Generate constants ───────────────────────────────────────
REM Must run before export_and_build_types.py below, constants_generated.py
REM feeds the SQLModel tables that backend.api.routes.ROUTERS pulls in.
echo Generating constants...
.venv\Scripts\python.exe scripts\gen_constants.py
if errorlevel 1 (
    echo ERROR: Constants generation failed. Aborting.
    exit /b 1
)

echo [OK] Constants generated

REM ── Generate API types ───────────────────────────────────────
echo Generating OpenAPI spec and frontend types...
.venv\Scripts\python.exe scripts\export_and_build_types.py
if errorlevel 1 (
    echo ERROR: Type generation failed. Aborting.
    exit /b 1
)

echo [OK] API types generated

REM ── Generate API reference docs ──────────────────────────────
REM Must run after shared/openapi.json exists (above) and before the
REM docs dev server starts below.
pushd "docs"
call npm run gen-api-docs
if errorlevel 1 (
    echo ERROR: API docs generation failed.
    popd
    exit /b 1
)
popd
echo [OK] API reference docs generated

REM ── Sandbox build check ──────────────────────────────────────
REM sandbox_host.exe ships prebuilt inside the pip-installed wincage wheel
REM (site-packages\wincage\sandbox_host.exe). There is no vendor source tree
REM to build it from anymore, so a missing binary here means the installed
REM wheel is wrong or incomplete, not something to compile around.
set "WINCAGE_DIR="
for /f "usebackq delims=" %%W in (`.venv\Scripts\python.exe -c "import os, wincage; print(os.path.dirname(wincage.__file__))"`) do set "WINCAGE_DIR=%%W"
if not defined WINCAGE_DIR (
    echo ERROR: Could not resolve the installed wincage package directory.
    echo Run "uv sync" first so wincage is installed in .venv.
    exit /b 1
)
if exist "%WINCAGE_DIR%\sandbox_host.exe" (
    echo [OK] sandbox_host.exe found
) else (
    echo ERROR: %WINCAGE_DIR%\sandbox_host.exe not found.
    echo The installed wincage wheel did not include a prebuilt sandbox_host.exe.
    echo Reinstall wincage ^(uv sync^) or verify the wheel on PyPI ships the win_amd64 binary.
    exit /b 1
)

REM ── Environment and start services ───────────────────────────
set PEACH_ENV=development

echo.
echo Starting Peach 1UP (frontend :5173, backend :8000, docs :3000)...
start "Peach 1UP Frontend" /d "%~dp0frontend" cmd /k "npm run dev"
start "Peach 1UP Docs" /d "%~dp0docs" cmd /k "npm run start"
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend

echo.
echo Backend stopped.
endlocal