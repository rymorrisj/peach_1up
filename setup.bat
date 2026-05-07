@echo off
setlocal

echo ============================================================
echo  Peach 1UP - First-run setup
echo ============================================================
echo.

rem ── Python check ─────────────────────────────────────────────
for /f "tokens=2 delims= " %%v in ('py --version 2^>^&1') do set PYVER=%%v
if "%PYVER%"=="" (
    echo ERROR: Python not found.
    echo Install Python 3.11 or later from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    exit /b 1
)
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if %PY_MAJOR% LSS 3 (
    echo ERROR: Python 3.11 or later is required. Found %PYVER%.
    exit /b 1
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 11 (
    echo ERROR: Python 3.11 or later is required. Found %PYVER%.
    exit /b 1
)
echo [OK] Python %PYVER%

rem ── Node / npm check ─────────────────────────────────────────
where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js / npm not found.
    echo Install Node.js from https://nodejs.org/
    exit /b 1
)
for /f "tokens=*" %%n in ('node --version 2^>^&1') do set NODEVER=%%n
echo [OK] Node.js %NODEVER%

rem ── Virtual environment ───────────────────────────────────────
if not exist ".venv" (
    echo Creating virtual environment...
    py -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        exit /b 1
    )
    echo [OK] Virtual environment created at .venv\
) else (
    echo [OK] Virtual environment already exists at .venv\
)

rem ── Activate venv and install backend deps ────────────────────
echo Installing backend dependencies...
call .venv\Scripts\activate.bat
py -m pip install --upgrade pip --quiet
py -m pip install -r backend\requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install backend dependencies.
    exit /b 1
)
echo [OK] Backend dependencies installed

rem ── Frontend deps ────────────────────────────────────────────
echo Installing frontend dependencies...
pushd frontend
npm install
if errorlevel 1 (
    echo ERROR: Failed to install frontend dependencies.
    popd
    exit /b 1
)
popd
echo [OK] Frontend dependencies installed

rem ── Settings check ───────────────────────────────────────────
if not exist "config\settings.yaml" (
    echo.
    echo WARNING: config\settings.yaml not found.
    echo Copy config\settings.yaml.template to config\settings.yaml and fill in paths.
) else (
    echo [OK] config\settings.yaml found
)

echo.
echo ============================================================
echo  Setup complete!
echo ============================================================
echo.
echo Next steps:
echo   1. Activate the virtual environment:  .venv\Scripts\activate
echo   2. Start the app:                     start.bat
echo      (or run backend and frontend separately)
echo.
echo The app will be available at:
echo   Frontend:  http://localhost:5173
echo   Backend:   http://localhost:8000
echo.

endlocal
