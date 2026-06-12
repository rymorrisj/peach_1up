; Peach 1UP — NSIS installer script
; Prerequisites:
;   - dist\peach1up\ produced by PyInstaller
;   - frontend\dist\ produced by npm run build
;   - installer\tools\Peach1UP.exe present (WinSW-x64.exe renamed; download from
;     https://github.com/winsw/winsw/releases)
; Build: makensis installer\peach1up.nsi

!define APP_NAME    "Peach 1UP"
!define APP_VERSION "0.1.0"
!define SERVICE_NAME "Peach1UP"
!define EXE_NAME    "peach1up.exe"
!define INSTALL_DIR "$PROGRAMFILES\Peach1UP"
!define REG_UNINSTALL "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
!define REG_APP      "Software\Peach1UP"

; UAC elevation on install only — uninstaller inherits elevation
RequestExecutionLevel admin

Name "${APP_NAME} ${APP_VERSION}"
OutFile "Peach1UP-Setup.exe"
InstallDir "${INSTALL_DIR}"
InstallDirRegKey HKLM "${REG_APP}" "InstallDir"

!include "MUI2.nsh"
!include "LogicLib.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON "..\assets\peach1up.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ── Install ──────────────────────────────────────────────────────────────────

Section "Peach 1UP" SecMain
    SectionIn RO  ; mandatory section

    ; Stop existing service before updating files
    ExecWait '"$INSTDIR\tools\Peach1UP.exe" stop' $0

    ; --- Application bundle (PyInstaller one-dir output) ---
    SetOutPath "$INSTDIR"
    File /r "..\dist\peach1up\*.*"

    ; --- Emulators ---
    SetOutPath "$INSTDIR\emulators"
    File /r "..\emulators\*.*"

    ; --- Config (template only; user config is preserved on update) ---
    SetOutPath "$INSTDIR\config"
    File /nonfatal "..\config\settings.yaml.template"

    ; Preserve existing settings.yaml on update
    ${IfNot} ${FileExists} "$INSTDIR\config\settings.yaml"
        File /nonfatal "..\config\settings.yaml.template"
        Rename "$INSTDIR\config\settings.yaml.template" "$INSTDIR\config\settings.yaml"
    ${EndIf}

    ; --- WinSW ---
    SetOutPath "$INSTDIR\tools"
    File "tools\Peach1UP.exe"
    File "tools\Peach1UP.xml"

    ; --- Register Windows service ---
    ExecWait '"$INSTDIR\tools\Peach1UP.exe" install' $0
    ${If} $0 != 0
        MessageBox MB_OK|MB_ICONEXCLAMATION "Service registration failed (exit $0). \
            The application was installed but will not start automatically. \
            Run as administrator and re-run the installer to retry."
    ${Else}
        ExecWait '"$INSTDIR\tools\Peach1UP.exe" start' $0
    ${EndIf}

    ; --- Create logs directory ---
    CreateDirectory "$INSTDIR\logs"
    CreateDirectory "$INSTDIR\database\data"

    ; --- Reset Owner script ---
    SetOutPath "$INSTDIR"
    File "..\reset_owner.bat"

    ; --- Start Menu shortcut ---
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
        "$INSTDIR\${EXE_NAME}" "" "$INSTDIR\${EXE_NAME}" 0
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Reset Owner Account.lnk" \
        "$INSTDIR\reset_owner.bat" "" "$INSTDIR\${EXE_NAME}" 0
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall ${APP_NAME}.lnk" "$INSTDIR\Uninstall.exe"

    ; --- Uninstaller ---
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; --- Registry ---
    WriteRegStr HKLM "${REG_APP}" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "${REG_APP}" "Version"    "${APP_VERSION}"

    WriteRegStr   HKLM "${REG_UNINSTALL}" "DisplayName"          "${APP_NAME}"
    WriteRegStr   HKLM "${REG_UNINSTALL}" "DisplayVersion"       "${APP_VERSION}"
    WriteRegStr   HKLM "${REG_UNINSTALL}" "Publisher"            "Peach 1UP"
    WriteRegStr   HKLM "${REG_UNINSTALL}" "InstallLocation"      "$INSTDIR"
    WriteRegStr   HKLM "${REG_UNINSTALL}" "UninstallString"      "$INSTDIR\Uninstall.exe"
    WriteRegStr   HKLM "${REG_UNINSTALL}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
    WriteRegDWORD HKLM "${REG_UNINSTALL}" "NoModify"             1
    WriteRegDWORD HKLM "${REG_UNINSTALL}" "NoRepair"             1
SectionEnd

; ── Uninstall ─────────────────────────────────────────────────────────────────

Section "Uninstall"
    ; Stop and remove service
    ExecWait '"$INSTDIR\tools\Peach1UP.exe" stop'
    ExecWait '"$INSTDIR\tools\Peach1UP.exe" uninstall'

    ; Start Menu
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\Reset Owner Account.lnk"
    RMDir  "$SMPROGRAMS\${APP_NAME}"

    ; Files — preserve user config
    RMDir /r "$INSTDIR\frontend"
    RMDir /r "$INSTDIR\emulators"
    RMDir /r "$INSTDIR\logs"
    RMDir /r "$INSTDIR\tools"
    Delete   "$INSTDIR\${EXE_NAME}"
    Delete   "$INSTDIR\reset_owner.bat"
    Delete   "$INSTDIR\Uninstall.exe"
    ; Leave $INSTDIR\config\ so user data survives uninstall
    RMDir    "$INSTDIR"   ; removes only if empty

    ; Registry
    DeleteRegKey HKLM "${REG_UNINSTALL}"
    DeleteRegKey HKLM "${REG_APP}"
SectionEnd
