@echo off
setlocal

for /f "tokens=2 delims= " %%v in ('py --version 2^>^&1') do set PYVER=%%v
if "%PYVER%"=="" (
    echo ERROR: Python not found. Install Python 3.11 or later from https://www.python.org/downloads/
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

where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js / npm not found. Install Node.js from https://nodejs.org/
    exit /b 1
)

if not exist "config\settings.yaml" (
    echo WARNING: config\settings.yaml not found. Backend may not start correctly.
    echo Copy config\settings.yaml and fill in paths before running.
)

echo Installing backend dependencies...
py -m pip install -r backend\requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: Failed to install backend dependencies.
    exit /b 1
)

echo Installing frontend dependencies...
call npm install --prefix ./frontend --silent
if errorlevel 1 (
    echo ERROR: Failed to install frontend dependencies.
    exit /b 1
)

set PEACH_ENV=development

echo Starting Peach 1UP frontend in a new window...
start "Peach 1UP Frontend" /d "%~dp0frontend" cmd /k "npm run dev"
echo Frontend starting at http://localhost:5173

echo Starting Peach 1UP backend...
echo Backend will be available at http://localhost:8000
py -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

endlocal
