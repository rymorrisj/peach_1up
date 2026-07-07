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
if exist "docs\build" rmdir /s /q "docs\build"
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

REM ── Docs (Docusaurus) dependencies ────────────────────────────
echo Installing docs dependencies...
pushd "docs"
call npm install
if errorlevel 1 (
    echo ERROR: Failed to install docs dependencies.
    popd
    exit /b 1
)
popd
echo [OK] Docs dependencies installed

REM ── Generate constants ───────────────────────────────────────
REM Must run before export_and_build_types.py below — constants_generated.py
REM feeds the SQLModel tables that backend.api.routes.ROUTERS pulls in.
echo Generating constants...
.venv\Scripts\python.exe scripts\gen_constants.py
if errorlevel 1 (
    echo ERROR: Constants generation failed. Aborting.
    exit /b 1
)

echo [OK] Constants generated

REM ── Generate API types ───────────────────────────────────────
REM Must run before the docs build below — it produces shared/openapi.json,
REM which docusaurus-plugin-openapi-docs reads to generate docs/docs/api/.
echo Generating OpenAPI spec and frontend types...
.venv\Scripts\python.exe scripts\export_and_build_types.py
if errorlevel 1 (
    echo ERROR: Type generation failed. Aborting.
    exit /b 1
)

echo [OK] API types generated

REM ── Docs (Docusaurus) build ───────────────────────────────────
pushd "docs"
call npm run gen-api-docs
if errorlevel 1 (
    echo ERROR: API docs generation failed.
    popd
    exit /b 1
)

call npm run build
if errorlevel 1 (
    echo ERROR: Docs build failed.
    popd
    exit /b 1
)

popd
echo [OK] Docs built

REM ── Add MSYS2 UCRT64 to PATH for g++ ─────────────────────────────────────────
set "MSYS2_UCRT64=%SystemDrive%\msys64\ucrt64\bin"
if exist "%MSYS2_UCRT64%\g++.exe" (
    set "PATH=%MSYS2_UCRT64%;%PATH%"
    echo [OK] MSYS2 UCRT64 g++ found at %MSYS2_UCRT64%
) else (
    echo WARNING: MSYS2 UCRT64 g++ not found at %MSYS2_UCRT64%
    echo          If sandbox_host.exe build fails, install MSYS2 from https://www.msys2.org
    echo          then run: pacman -S mingw-w64-ucrt-x86_64-gcc
)

REM ── Build sandbox_host.exe via MSYS2 (or validate pre-built) ──
echo Building sandbox_host.exe...
where bash >nul 2>&1
if not errorlevel 1 (
    bash "backend/service/utils/platform/windows/sandbox/build.sh"
    if errorlevel 1 (
        echo ERROR: sandbox_host.exe build failed.
        goto :error
    )
    echo [OK] sandbox_host.exe built
) else (
    if not exist "backend\service\utils\platform\windows\sandbox\sandbox_host.exe" (
        echo ERROR: bash/MSYS2 not found and sandbox_host.exe is missing.
        echo Install MSYS2 UCRT64 with gcc and run:
        echo   bash backend/service/utils/platform/windows/sandbox/build.sh
        goto :error
    )
    echo [OK] sandbox_host.exe found ^(pre-built; MSYS2 not available to rebuild^)
)

if not exist "installer\tools\Peach1UP.exe" (
    echo ERROR: installer\tools\Peach1UP.exe not found.
    echo Download WinSW-x64.exe from https://github.com/winsw/winsw/releases, rename it to Peach1UP.exe, and place it at installer\tools\Peach1UP.exe
    goto :error
)

echo === Running PyInstaller ===
.venv\Scripts\python.exe -m PyInstaller --clean peach1up.spec
if errorlevel 1 goto :error

echo === Copying emulators, library and config beside exe ===
xcopy /E /I /Y emulators dist\peach1up\emulators
REM NOTE: xcopy of library includes bundled alpha test media. Remove for release builds.
xcopy /E /I /Y library dist\peach1up\library
xcopy /E /I /Y config dist\peach1up\config
if not exist "dist\peach1up\database\data\" mkdir "dist\peach1up\database\data\"

echo === Copying docs build beside exe ===
xcopy /E /I /Y docs\build dist\peach1up\docs\build
if errorlevel 1 (
    echo ERROR: Failed to copy docs build to dist.
    goto :error
)
echo [OK] docs build copied

echo === Copying sandbox executables ===
if not exist "backend\service\utils\platform\windows\sandbox\sandbox_host.exe" (
    echo ERROR: backend\service\utils\platform\windows\sandbox\sandbox_host.exe not found.
    echo Run build.sh from an MSYS2 UCRT64 shell first to compile the sandbox executables.
    goto :error
)
if not exist "dist\peach1up\backend\service\utils\platform\windows\sandbox\" mkdir "dist\peach1up\backend\service\utils\platform\windows\sandbox\"
copy /Y "backend\service\utils\platform\windows\sandbox\sandbox_host.exe" "dist\peach1up\backend\service\utils\platform\windows\sandbox\"
if errorlevel 1 (
    echo ERROR: Failed to copy sandbox_host.exe to dist.
    goto :error
)

echo === Building sandbox_checker capability probes ===
where bash >nul 2>&1
if not errorlevel 1 (
    bash "backend/service/utils/platform/windows/sandbox_checker/src/build_tests.sh"
    if errorlevel 1 (
        echo ERROR: sandbox_checker build_tests.sh failed.
        goto :error
    )
    echo [OK] sandbox_checker probes built
) else (
    echo WARNING: bash/MSYS2 not found - cannot rebuild sandbox_checker probes.
)

if not exist "backend\service\utils\platform\windows\sandbox_checker\src\test_sdl2_d3d11.exe" (
    echo ERROR: No executables found in backend\service\utils\platform\windows\sandbox_checker\src\
    echo Run build_tests.sh from an MSYS2 UCRT64 shell first to compile the sandbox executables.
    goto :error
)
if not exist "dist\peach1up\backend\service\utils\platform\windows\sandbox_checker\src\" mkdir "dist\peach1up\backend\service\utils\platform\windows\sandbox_checker\src\"
copy /Y "backend\service\utils\platform\windows\sandbox_checker\src\*.exe" "dist\peach1up\backend\service\utils\platform\windows\sandbox_checker\src\"
if errorlevel 1 (
    echo ERROR: Failed to copy sandbox_checker executables to dist.
    goto :error
)
echo [OK] sandbox exes copied

echo === Build complete ===

REM === Building NSIS installer ===
REM makensis installer\peach1up.nsi
REM if errorlevel 1 goto :error
REM echo === Installer built: Peach1UP-Setup.exe ===

goto :eof

:error_cd
cd ..
:error
echo === Build FAILED ===
exit /b 1
