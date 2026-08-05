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

REM ── Sync venv and backend deps (build group includes PyInstaller) ──
echo Syncing backend dependencies via uv...
uv sync --group build
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
call npm ci
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

@REM REM ── Build sandbox_host.exe via MSYS2 (or validate pre-built) ──
@REM echo Building sandbox_host.exe...
@REM where bash >nul 2>&1
@REM if not errorlevel 1 (
@REM     bash "backend/service/utils/platform/windows/sandbox/build.sh"
@REM     if errorlevel 1 (
@REM         echo ERROR: sandbox_host.exe build failed.
@REM         goto :error
@REM     )
@REM     echo [OK] sandbox_host.exe built
@REM ) else (
@REM     if not exist "backend\service\utils\platform\windows\sandbox\sandbox_host.exe" (
@REM         echo ERROR: bash/MSYS2 not found and sandbox_host.exe is missing.
@REM         echo Install MSYS2 UCRT64 with gcc and run:
@REM         echo   bash backend/service/utils/platform/windows/sandbox/build.sh
@REM         goto :error
@REM     )
@REM     echo [OK] sandbox_host.exe found ^(pre-built; MSYS2 not available to rebuild^)
@REM )

@REM REM ── Build extract-xiso via MSYS2 (or validate pre-built) ─────
@REM echo Building extract-xiso...
@REM where bash >nul 2>&1
@REM if not errorlevel 1 (
@REM     bash "services/vendor/extract-xiso/build.sh"
@REM     if errorlevel 1 (
@REM         echo ERROR: extract-xiso build failed.
@REM         goto :error
@REM     )
@REM     echo [OK] extract-xiso built
@REM ) else (
@REM     if not exist "services\vendor\extract-xiso\build\extract-xiso.exe" (
@REM         echo ERROR: bash/MSYS2 not found and extract-xiso.exe is missing.
@REM         echo Install MSYS2 UCRT64 with gcc/cmake and run:
@REM         echo   bash services/vendor/extract-xiso/build.sh
@REM         goto :error
@REM     )
@REM     echo [OK] extract-xiso found ^(pre-built; MSYS2 not available to rebuild^)
@REM )

if not exist "installer\tools\Peach1UP.exe" (
    echo ERROR: installer\tools\Peach1UP.exe not found.
    echo Download WinSW-x64.exe from https://github.com/winsw/winsw/releases, rename it to Peach1UP.exe, and place it at installer\tools\Peach1UP.exe
    goto :error
)

echo === Running PyInstaller ===
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm peach1up.spec
if errorlevel 1 goto :error

REM ── Emulator license and attribution files ───────────────────
REM Emulator binaries are NOT bundled. Every emulator installs on demand from
REM its upstream GitHub release (see config/emulators/*.toml install_type), so
REM the working-tree emulators\ directory holds local installs and user data
REM (BIOS, saves, memory cards) that must never enter a release build. Only the
REM git-tracked license and attribution files ship, which is the exact set the
REM .gitignore negations under /emulators/** keep under version control.
echo === Copying emulator license and attribution files beside exe ===
where git >nul 2>&1
if errorlevel 1 (
    echo ERROR: git not found on PATH.
    echo git is required to determine which emulator attribution files to ship.
    goto :error
)
setlocal enabledelayedexpansion
for /f "usebackq delims=" %%f in (`git ls-files emulators`) do (
    set "REL=%%f"
    set "REL=!REL:/=\!"
    for %%p in ("dist\peach1up\!REL!") do (
        if not exist "%%~dpp" mkdir "%%~dpp"
        copy /Y "!REL!" "%%~dpp" >nul
    )
)
endlocal
echo [OK] emulator attribution files copied

REM ── Optional alpha test media ────────────────────────────────
REM library\ holds user media (disc images, OS install media, BIOS/ROM assets)
REM and is many tens of GB on a populated checkout. It is excluded from release
REM builds. Set INCLUDE_TEST_MEDIA=1 before running this script to bundle it
REM for internal alpha builds only.
if defined INCLUDE_TEST_MEDIA (
    echo === Copying library beside exe ^(INCLUDE_TEST_MEDIA is set^) ===
    echo WARNING: this bundles the full library\ tree, including any commercial
    echo          media it contains. Do not distribute this build.
    xcopy /E /I /Y library dist\peach1up\library
    if errorlevel 1 (
        echo ERROR: Failed to copy library to dist.
        goto :error
    )
) else (
    echo === Skipping library ^(set INCLUDE_TEST_MEDIA=1 to bundle test media^) ===
)

echo === Copying config beside exe ===
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

@REM echo === Building sandbox_checker capability probes ===
@REM where bash >nul 2>&1
@REM if not errorlevel 1 (
@REM     bash "backend/service/utils/platform/windows/sandbox_checker/src/build_tests.sh"
@REM     if errorlevel 1 (
@REM         echo ERROR: sandbox_checker build_tests.sh failed.
@REM         goto :error
@REM     )
@REM     echo [OK] sandbox_checker probes built
@REM ) else (
@REM     echo WARNING: bash/MSYS2 not found - cannot rebuild sandbox_checker probes.
@REM )

@REM if not exist "backend\service\utils\platform\windows\sandbox_checker\src\test_sdl2_d3d11.exe" (
@REM     echo ERROR: No executables found in backend\service\utils\platform\windows\sandbox_checker\src\
@REM     echo Run build_tests.sh from an MSYS2 UCRT64 shell first to compile the sandbox executables.
@REM     goto :error
@REM )
@REM if not exist "dist\peach1up\backend\service\utils\platform\windows\sandbox_checker\src\" mkdir "dist\peach1up\backend\service\utils\platform\windows\sandbox_checker\src\"
@REM copy /Y "backend\service\utils\platform\windows\sandbox_checker\src\*.exe" "dist\peach1up\backend\service\utils\platform\windows\sandbox_checker\src\"
@REM if errorlevel 1 (
@REM     echo ERROR: Failed to copy sandbox_checker executables to dist.
@REM     goto :error
@REM )
@REM echo [OK] sandbox exes copied

echo === Copying extract-xiso ===
if not exist "services\vendor\extract-xiso\build\extract-xiso.exe" (
    echo ERROR: services\vendor\extract-xiso\build\extract-xiso.exe not found.
    echo Run build.sh from an MSYS2 UCRT64 shell first to compile extract-xiso.
    goto :error
)
if not exist "dist\peach1up\services\vendor\extract-xiso\build\" mkdir "dist\peach1up\services\vendor\extract-xiso\build\"
copy /Y "services\vendor\extract-xiso\build\extract-xiso.exe" "dist\peach1up\services\vendor\extract-xiso\build\"
if errorlevel 1 (
    echo ERROR: Failed to copy extract-xiso.exe to dist.
    goto :error
)
echo [OK] extract-xiso copied

echo === Copying vendored 7-Zip ===
if not exist "services\vendor\7z\7za.exe" (
    echo ERROR: services\vendor\7z\7za.exe not found.
    goto :error
)
xcopy /E /I /Y "services\vendor\7z" "dist\peach1up\services\vendor\7z"
if errorlevel 1 (
    echo ERROR: Failed to copy services\vendor\7z to dist.
    goto :error
)
echo [OK] vendored 7-Zip copied

REM ── NSIS installer ───────────────────────────────────────────
REM Must run after the copy steps above: peach1up.nsi packages dist\peach1up\
REM wholesale, so whatever those steps placed there ends up in the installer.
echo === Building NSIS installer ===
set "MAKENSIS=makensis"
where makensis >nul 2>&1
if not errorlevel 1 goto :nsis_ready
set "NSIS_DEFAULT=%ProgramFiles(x86)%\NSIS\makensis.exe"
if exist "%NSIS_DEFAULT%" set "MAKENSIS=%NSIS_DEFAULT%"
if exist "%NSIS_DEFAULT%" goto :nsis_ready
echo ERROR: makensis not found on PATH and not present at
echo        %NSIS_DEFAULT%
echo Install NSIS from https://nsis.sourceforge.io/Download, then re-run this script.
goto :error

:nsis_ready
if not exist "VERSION" (
    echo ERROR: VERSION file not found at repo root.
    echo It is generated by scripts\gen_constants.py — re-run the "Generating constants" step above.
    goto :error
)
set /p APP_VERSION=<VERSION
if "%APP_VERSION%"=="" (
    echo ERROR: VERSION file is empty.
    goto :error
)
echo Installer version: %APP_VERSION%
"%MAKENSIS%" /DAPP_VERSION=%APP_VERSION% installer\peach1up.nsi
if errorlevel 1 goto :error
echo [OK] Installer built: Peach1UP-Setup.exe

echo === Build complete ===

goto :eof

:error_cd
cd ..
:error
echo === Build FAILED ===
exit /b 1
