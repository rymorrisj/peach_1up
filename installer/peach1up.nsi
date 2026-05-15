; Peach 1UP — NSIS installer script
; Prerequisites:
;   - dist\peach1up\ produced by PyInstaller
;   - frontend\dist\ produced by npm run build
;   - installer\tools\nssm.exe present (download from https://nssm.cc)
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
!define MUI_ICON "..\assets\peach1up.png"

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
    ExecWait '"$INSTDIR\tools\nssm.exe" stop ${SERVICE_NAME}' $0

    ; --- Application bundle (PyInstaller one-dir output) ---
    SetOutPath "$INSTDIR"
    File /r "..\dist\peach1up\*.*"

    ; --- Frontend dist ---
    SetOutPath "$INSTDIR\frontend\dist"
    File /r "..\frontend\dist\*.*"

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

    ; --- NSSM ---
    SetOutPath "$INSTDIR\tools"
    File "tools\nssm.exe"

    ; --- Register Windows service ---
    ExecWait '"$INSTDIR\tools\nssm.exe" install ${SERVICE_NAME} "$INSTDIR\${EXE_NAME}"' $0
    ${If} $0 != 0
        MessageBox MB_OK|MB_ICONEXCLAMATION "Service registration failed (exit $0). \
            The application was installed but will not start automatically. \
            Run as administrator and re-run the installer to retry."
    ${Else}
        ExecWait '"$INSTDIR\tools\nssm.exe" set ${SERVICE_NAME} AppDirectory "$INSTDIR"'
        ExecWait '"$INSTDIR\tools\nssm.exe" set ${SERVICE_NAME} AppStdout "$INSTDIR\logs\peach1up.log"'
        ExecWait '"$INSTDIR\tools\nssm.exe" set ${SERVICE_NAME} AppStderr "$INSTDIR\logs\peach1up.log"'
        ExecWait '"$INSTDIR\tools\nssm.exe" set ${SERVICE_NAME} AppRotateFiles 1'
        ExecWait '"$INSTDIR\tools\nssm.exe" set ${SERVICE_NAME} AppRotateBytes 10485760'
        ExecWait '"$INSTDIR\tools\nssm.exe" set ${SERVICE_NAME} Start SERVICE_AUTO_START'
        ExecWait '"$INSTDIR\tools\nssm.exe" start ${SERVICE_NAME}' $0
    ${EndIf}

    ; --- Create logs directory ---
    CreateDirectory "$INSTDIR\logs"

    ; --- Start Menu shortcut ---
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
        "$INSTDIR\${EXE_NAME}" "" "$INSTDIR\${EXE_NAME}" 0

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
    ExecWait '"$INSTDIR\tools\nssm.exe" stop ${SERVICE_NAME}'
    ExecWait '"$INSTDIR\tools\nssm.exe" remove ${SERVICE_NAME} confirm'

    ; Start Menu
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    RMDir  "$SMPROGRAMS\${APP_NAME}"

    ; Files — preserve user config
    RMDir /r "$INSTDIR\frontend"
    RMDir /r "$INSTDIR\emulators"
    RMDir /r "$INSTDIR\logs"
    RMDir /r "$INSTDIR\tools"
    Delete   "$INSTDIR\${EXE_NAME}"
    Delete   "$INSTDIR\Uninstall.exe"
    ; Leave $INSTDIR\config\ so user data survives uninstall
    RMDir    "$INSTDIR"   ; removes only if empty

    ; Registry
    DeleteRegKey HKLM "${REG_UNINSTALL}"
    DeleteRegKey HKLM "${REG_APP}"
SectionEnd
