@echo off
rem ============================================================
rem scripts\build_sandbox_host.bat
rem
rem Compiles sandbox_host.exe using the MSVC toolchain located
rem via vswhere.exe. Must be run from any directory — all paths
rem are derived from the script's own location.
rem
rem Usage:
rem   scripts\build_sandbox_host.bat
rem
rem Requirements:
rem   Visual Studio 2019 or later with the
rem   "Desktop development with C++" workload installed.
rem ============================================================

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
for %%i in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fi"
set "SANDBOX_DIR=%PROJECT_ROOT%\backend\service\utils\platform\windows\sandbox"
set "SRC_DIR=%SANDBOX_DIR%\src"
set "OUT_EXE=%SANDBOX_DIR%\sandbox_host.exe"
set "OBJ_DIR=%SANDBOX_DIR%\build_tmp"

rem -- Locate vswhere --------------------------------------------------
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" set "VSWHERE=%ProgramFiles%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
    echo ERROR: vswhere.exe not found.
    echo        Install Visual Studio 2019 or later with the C++ workload.
    exit /b 1
)

rem -- Find VS installation with C++ tools -----------------------------
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2^>nul`) do set "VS_INSTALL=%%i"
if not defined VS_INSTALL (
    echo ERROR: No Visual Studio installation with C++ tools found.
    echo        Install the "Desktop development with C++" workload.
    exit /b 1
)

set "VCVARS=%VS_INSTALL%\VC\Auxiliary\Build\vcvarsall.bat"
if not exist "%VCVARS%" (
    echo ERROR: vcvarsall.bat not found: %VCVARS%
    exit /b 1
)

rem -- Init x64 toolchain ----------------------------------------------
echo Initializing MSVC x64 toolchain from: %VS_INSTALL%
call "%VCVARS%" x64 >nul 2>&1
if errorlevel 1 (
    echo ERROR: vcvarsall.bat x64 failed.
    exit /b 1
)

rem -- Prepare obj output directory ------------------------------------
if not exist "%OBJ_DIR%" mkdir "%OBJ_DIR%"

rem -- Compile ---------------------------------------------------------
echo Building sandbox_host.exe...
echo   Output : %OUT_EXE%

cl.exe /nologo /std:c++20 /O2 /W3 /EHsc ^
    /I"%SRC_DIR%" ^
    "%SRC_DIR%\main.cpp" ^
    "%SRC_DIR%\container.cpp" ^
    "%SRC_DIR%\job.cpp" ^
    "%SRC_DIR%\watchdog.cpp" ^
    "%SRC_DIR%\event.cpp" ^
    /Fe:"%OUT_EXE%" ^
    /Fo:"%OBJ_DIR%\\" ^
    /link userenv.lib ole32.lib advapi32.lib kernel32.lib shlwapi.lib

set "BUILD_RESULT=%errorlevel%"

rem -- Clean intermediate objects --------------------------------------
rmdir /s /q "%OBJ_DIR%" 2>nul

if %BUILD_RESULT% neq 0 (
    echo.
    echo FAILED: Compilation errors above. sandbox_host.exe was NOT updated.
    exit /b %BUILD_RESULT%
)

echo.
echo SUCCESS: %OUT_EXE%
exit /b 0
