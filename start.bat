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
if exist "services\vendor\wincage\wincage\sandbox_host.exe" (
    echo [OK] sandbox_host.exe found
) else (
    echo sandbox_host.exe not found. Attempting to build via MSYS2 UCRT64...
    if exist "C:\msys64\msys2_shell.cmd" (
        "C:\msys64\msys2_shell.cmd" -ucrt64 -defterm -no-start -here -c "bash services/vendor/wincage/wincage/build.sh"
        if errorlevel 1 (
            echo ERROR: sandbox_host.exe build failed.
            echo Run build.sh manually from an MSYS2 UCRT64 shell.
            exit /b 1
        )
        if not exist "services\vendor\wincage\wincage\sandbox_host.exe" (
            echo ERROR: build.sh ran but sandbox_host.exe was not produced.
            echo Check build.sh output for errors.
            exit /b 1
        )
        echo [OK] sandbox_host.exe built successfully
    ) else (
        echo ERROR: sandbox_host.exe not found and MSYS2 is not installed.
        echo To build it manually:
        echo   1. Install MSYS2 from https://www.msys2.org/
        echo   2. Open an MSYS2 UCRT64 shell and run: bash services/vendor/wincage/wincage/build.sh
        echo   3. Re-run start.bat
        exit /b 1
    )
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