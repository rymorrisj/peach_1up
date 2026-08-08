@echo off
rem ============================================================
rem scripts\build_sandbox_host.bat
rem
rem Compiles sandbox_host.exe using the Microsoft C++ toolchain.
rem
rem Design goals:
rem   - Can be run from any directory; all project paths are derived
rem     from this script's own location.
rem   - Works if already launched from a Developer Command Prompt /
rem     MSVC-initialized shell (cl.exe already on PATH).
rem   - Otherwise, locates Visual Studio / Build Tools via vswhere.exe
rem     and initializes the x64 toolchain with vcvarsall.bat.
rem   - Avoids common batch parsing bugs caused by parentheses in paths
rem     like "Program Files (x86)" by using delayed expansion inside
rem     parenthesized blocks.
rem
rem Usage:
rem   scripts\build_sandbox_host.bat
rem
rem Requirements:
rem   - Visual Studio Build Tools or Visual Studio 2019+ installed
rem   - "Desktop development with C++" workload installed
rem
rem Output:
rem   services\vendor\wincage\wincage\sandbox_host.exe
rem ============================================================

setlocal EnableExtensions EnableDelayedExpansion

rem --------------------------------------------------------------------
rem Resolve project-relative paths
rem --------------------------------------------------------------------
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

set "SANDBOX_DIR=%PROJECT_ROOT%\services\vendor\wincage\wincage"
set "SRC_DIR=%SANDBOX_DIR%\src"
set "OUT_EXE=%SANDBOX_DIR%\sandbox_host.exe"
set "OBJ_DIR=%SANDBOX_DIR%\build_tmp"

rem --------------------------------------------------------------------
rem Basic input validation
rem --------------------------------------------------------------------
if not exist "!SRC_DIR!\main.cpp" (
    echo ERROR: Source file not found: !SRC_DIR!\main.cpp
    echo        Expected project root: !PROJECT_ROOT!
    exit /b 1
)

if not exist "!SRC_DIR!\container.cpp" (
    echo ERROR: Source file not found: !SRC_DIR!\container.cpp
    exit /b 1
)

if not exist "!SRC_DIR!\job.cpp" (
    echo ERROR: Source file not found: !SRC_DIR!\job.cpp
    exit /b 1
)

if not exist "!SRC_DIR!\watchdog.cpp" (
    echo ERROR: Source file not found: !SRC_DIR!\watchdog.cpp
    exit /b 1
)

if not exist "!SRC_DIR!\event.cpp" (
    echo ERROR: Source file not found: !SRC_DIR!\event.cpp
    exit /b 1
)

rem --------------------------------------------------------------------
rem If cl.exe is already available, do not force a Visual Studio lookup.
rem This supports running from a Developer Command Prompt / pre-inited shell.
rem --------------------------------------------------------------------
where cl.exe >nul 2>nul
if !errorlevel! EQU 0 (
    echo Found cl.exe on PATH; using existing MSVC environment.
    goto :build
)

rem --------------------------------------------------------------------
rem Locate vswhere.exe
rem
rem Note:
rem   Do NOT expand %%ProgramFiles(x86)%% directly inside a parenthesized
rem   IF block; that commonly causes:
rem       "\Microsoft was unexpected at this time."
rem   We assign it first, then use delayed expansion (!VAR!).
rem --------------------------------------------------------------------
set "PF32=%ProgramFiles(x86)%"
if not defined PF32 set "PF32=%ProgramFiles%"

set "VSWHERE=!PF32!\Microsoft Visual Studio\Installer\vswhere.exe"

if not exist "!VSWHERE!" (
    rem Fallback: some environments may only expose ProgramFiles
    set "VSWHERE=%ProgramFiles%\Microsoft Visual Studio\Installer\vswhere.exe"
)

if not exist "!VSWHERE!" (
    echo ERROR: vswhere.exe not found.
    echo        Looked for:
    echo          !PF32!\Microsoft Visual Studio\Installer\vswhere.exe
    echo          %ProgramFiles%\Microsoft Visual Studio\Installer\vswhere.exe
    echo        Install Visual Studio Build Tools or Visual Studio
    echo        with the "Desktop development with C++" workload.
    exit /b 1
)

rem --------------------------------------------------------------------
rem Find latest VS / Build Tools installation that has MSVC x86/x64 tools
rem --------------------------------------------------------------------
set "VS_INSTALL="

for /f "usebackq delims=" %%I in (`
    "!VSWHERE!" -latest -products * ^
    -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 ^
    -property installationPath 2^>nul
`) do (
    set "VS_INSTALL=%%~I"
)

if not defined VS_INSTALL (
    echo ERROR: No Visual Studio installation with C++ tools found.
    echo        Install the "Desktop development with C++" workload.
    exit /b 1
)

rem --------------------------------------------------------------------
rem Initialize MSVC x64 environment
rem
rem We prefer vcvarsall.bat because your original script used it and it
rem is the canonical way to prepare the environment for cl.exe builds.
rem --------------------------------------------------------------------
set "VCVARS=!VS_INSTALL!\VC\Auxiliary\Build\vcvarsall.bat"

if not exist "!VCVARS!" (
    echo ERROR: vcvarsall.bat not found:
    echo        !VCVARS!
    exit /b 1
)

echo Initializing MSVC x64 toolchain from:
echo   !VS_INSTALL!

call "!VCVARS!" x64 >nul 2>&1
if errorlevel 1 (
    echo ERROR: vcvarsall.bat x64 failed.
    exit /b 1
)

where cl.exe >nul 2>nul
if errorlevel 1 (
    echo ERROR: cl.exe is still not available after vcvarsall.bat.
    exit /b 1
)

:build
rem --------------------------------------------------------------------
rem Prepare intermediate output directory
rem --------------------------------------------------------------------
if exist "!OBJ_DIR!" rmdir /s /q "!OBJ_DIR!" >nul 2>nul
mkdir "!OBJ_DIR!" >nul 2>nul
if errorlevel 1 (
    echo ERROR: Failed to create object directory:
    echo        !OBJ_DIR!
    exit /b 1
)

rem --------------------------------------------------------------------
rem Compile + link
rem
rem Notes:
rem   - /std:c++20 : C++20 mode
rem   - /O2        : optimize for speed
rem   - /W3        : warning level 3
rem   - /EHsc      : standard C++ exception semantics
rem   - /Fo        : object output directory
rem   - /Fe        : final executable path
rem --------------------------------------------------------------------
echo Building sandbox_host.exe...
echo   Source : !SRC_DIR!
echo   Output : !OUT_EXE!
echo.

cl.exe /nologo /std:c++20 /O2 /W3 /EHsc ^
    /I"!SRC_DIR!" ^
    "!SRC_DIR!\main.cpp" ^
    "!SRC_DIR!\container.cpp" ^
    "!SRC_DIR!\job.cpp" ^
    "!SRC_DIR!\watchdog.cpp" ^
    "!SRC_DIR!\event.cpp" ^
    /Fe:"!OUT_EXE!" ^
    /Fo:"!OBJ_DIR!\\" ^
    /link user32.lib userenv.lib ole32.lib advapi32.lib kernel32.lib shlwapi.lib

set "BUILD_RESULT=!errorlevel!"

rem --------------------------------------------------------------------
rem Clean intermediates
rem --------------------------------------------------------------------
if exist "!OBJ_DIR!" rmdir /s /q "!OBJ_DIR!" >nul 2>nul

if not "!BUILD_RESULT!"=="0" (
    echo.
    echo FAILED: Compilation errors above. sandbox_host.exe was NOT updated.
    exit /b !BUILD_RESULT!
)

echo.
echo SUCCESS: !OUT_EXE!
exit /b 0