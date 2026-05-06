@echo off
setlocal

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
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

if not exist "config\settings.yaml" (
    echo WARNING: config\settings.yaml not found. Backend may not start correctly.
    echo Copy config\settings.yaml and fill in paths before running.
)

set PEACH_ENV=development

echo Starting Peach 1UP backend...
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
echo Backend running at http://localhost:8000 - open http://localhost:8000/api/docs to verify
echo For the frontend run: cd frontend ^&^& npm run dev

endlocal
