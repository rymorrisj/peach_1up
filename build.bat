@echo off
cd /d "%~dp0"
setlocal

echo ============================================================
echo Peach 1UP - Setup and Start (Windows)
echo ============================================================
echo.

REM ── Clean previous build outputs ─────────────────────────────
echo Cleaning previous build outputs...
if exist "frontend\dist" rmdir /s /q "frontend\dist"
if exist "dist" rmdir /s /q "dist"
for /r "backend" %%d in (__pycache__) do (
    if exist "%%d" rmdir /s /q "%%d"
)
del /s /q "backend\*.pyc" >nul 2>&1
echo [OK] Clean complete

REM ── Python check ─────────────────────────────────────────────
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

REM ── Node / npm check ─────────────────────────────────────────
where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js / npm not found.
    exit /b 1
)

for /f "tokens=*" %%n in ('node --version 2^>^&1') do set NODEVER=%%n
echo [OK] Node.js %NODEVER%

REM ── Virtual environment ──────────────────────────────────────
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

REM ── Activate venv and install backend deps ───────────────────
echo Installing backend dependencies...

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment.
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip.
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 (
    echo ERROR: Failed to install backend dependencies.
    exit /b 1
)

echo [OK] Backend dependencies installed

REM ── Frontend deps ────────────────────────────────────────────
echo Installing frontend dependencies...
pushd "frontend"
call npm install
if errorlevel 1 (
    echo ERROR: Failed to install frontend dependencies.
    popd
    exit /b 1
)

call npm run build
if errorlevel 1 (
    echo ERROR: Frontend build failed.
    popd
    exit /b 1
)

popd
echo [OK] Frontend dependencies installed

REM ── Generate API types ───────────────────────────────────────
echo Generating OpenAPI spec and frontend types...
py scripts\export_and_build_types.py
if errorlevel 1 (
    echo ERROR: Type generation failed. Aborting.
    exit /b 1
)

popd
echo [OK] API types generated

REM ── Settings check ───────────────────────────────────────────
if not exist "config\settings.yaml" (
    echo.
    echo WARNING: config\settings.yaml not found.
    echo Copy config\settings.yaml.template to config\settings.yaml and fill in paths.
) else (
    echo [OK] config\settings.yaml found
)

REM ── Build sandbox_host.exe via MSYS2 (or validate pre-built) ──
echo Building sandbox_host.exe...
where bash >nul 2>&1
if not errorlevel 1 (
    bash "backend/service/utils/sandbox/build.sh"
    if errorlevel 1 (
        echo ERROR: sandbox_host.exe build failed.
        goto :error
    )
    echo [OK] sandbox_host.exe built
) else (
    if not exist "backend\service\utils\sandbox\sandbox_host.exe" (
        echo ERROR: bash/MSYS2 not found and sandbox_host.exe is missing.
        echo Install MSYS2 UCRT64 with gcc and run:
        echo   bash backend/service/utils/sandbox/build.sh
        goto :error
    )
    echo [OK] sandbox_host.exe found ^(pre-built; MSYS2 not available to rebuild^)
)

echo === Running PyInstaller ===
.venv\Scripts\python.exe -m PyInstaller --clean peach1up.spec
if errorlevel 1 goto :error

echo === Copying emulators, library and config beside exe ===
xcopy /E /I /Y emulators dist\peach1up\emulators
xcopy /E /I /Y library dist\peach1up\library
xcopy /E /I /Y config dist\peach1up\config

echo === Copying sandbox executables ===
if not exist "backend\service\utils\sandbox\sandbox_host.exe" (
    echo ERROR: backend\service\utils\sandbox\sandbox_host.exe not found.
    echo Run build.sh from an MSYS2 UCRT64 shell first to compile the sandbox executables.
    goto :error
)
if not exist "dist\peach1up\backend\service\utils\sandbox\" mkdir "dist\peach1up\backend\service\utils\sandbox\"
copy /Y "backend\service\utils\sandbox\sandbox_host.exe" "dist\peach1up\backend\service\utils\sandbox\"
if errorlevel 1 (
    echo ERROR: Failed to copy sandbox_host.exe to dist.
    goto :error
)

dir /b "backend\service\utils\sandbox_checker\src\*.exe" >nul 2>&1
if errorlevel 1 (
    echo ERROR: No executables found in backend\service\utils\sandbox_checker\src\
    echo Run build.sh from an MSYS2 UCRT64 shell first to compile the sandbox executables.
    goto :error
)
if not exist "dist\peach1up\backend\service\utils\sandbox_checker\src\" mkdir "dist\peach1up\backend\service\utils\sandbox_checker\src\"
copy /Y "backend\service\utils\sandbox_checker\src\*.exe" "dist\peach1up\backend\service\utils\sandbox_checker\src\"
if errorlevel 1 (
    echo ERROR: Failed to copy sandbox_checker executables to dist.
    goto :error
)
echo [OK] sandbox exes copied

echo === Stripping first_run_complete from dist settings.yaml ===
python -c "import yaml,pathlib; p=pathlib.Path('dist/peach1up/config/settings.yaml'); d=yaml.safe_load(p.read_text()) or {}; d.pop('first_run_complete',None); p.write_text(yaml.dump(d))"

echo === Writing peach_env=production to dist settings.yaml ===
python -c "import yaml,pathlib; p=pathlib.Path('dist/peach1up/config/settings.yaml'); d=yaml.safe_load(p.read_text()) or {}; d['peach_env']='production'; p.write_text(yaml.dump(d))"

echo === Build complete ===
goto :eof

:error_cd
cd ..
:error
echo === Build FAILED ===
exit /b 1
