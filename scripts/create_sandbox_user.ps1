# Peach 1UP — Sandbox User Setup
#
# Creates and verifies the peach_sandbox local Windows account.
# Called automatically at backend startup via lifespan.py.
#
# The account exists solely to run emulator processes under a low-privilege
# context. It is not an interactive user account and should never be
# granted elevated permissions or added to any privileged group.
#
# Required environment variable (set by lifespan.py, never on the command line):
#   PEACH_SANDBOX_PASSWORD — the account password
#
# Exit codes:
#   0  — account exists and is correctly configured
#   1  — unrecoverable error (message written to stderr)

param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$AccountName    = "peach_sandbox"
$AccountDesc    = "Peach 1UP emulator sandbox. Do not modify or delete manually."
$AdminGroupName = "Administrators"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Status {
    param([string]$Message)
    Write-Host "[peach_sandbox] $Message"
}

function Fail {
    param([string]$Message)
    Write-Error "[peach_sandbox] $Message"
    exit 1
}

# ---------------------------------------------------------------------------
# Read password from environment (never accept on command line)
# ---------------------------------------------------------------------------

$Password = $env:PEACH_SANDBOX_PASSWORD
if ([string]::IsNullOrEmpty($Password)) {
    Fail "PEACH_SANDBOX_PASSWORD is not set. Backend should supply this at startup."
}

$SecurePassword = ConvertTo-SecureString -String $Password -AsPlainText -Force

# ---------------------------------------------------------------------------
# Locate the account
# ---------------------------------------------------------------------------

$User = $null
try {
    $User = Get-LocalUser -Name $AccountName -ErrorAction SilentlyContinue
} catch {
    $User = $null
}

# ---------------------------------------------------------------------------
# Create account if it does not exist
# ---------------------------------------------------------------------------

if ($null -eq $User) {
    Write-Status "Account not found. Creating..."
    try {
        New-LocalUser `
            -Name $AccountName `
            -Password $SecurePassword `
            -Description $AccountDesc `
            -PasswordNeverExpires `
            -UserMayNotChangePassword `
            -AccountNeverExpires `
            -ErrorAction Stop | Out-Null
    } catch {
        Fail "Failed to create account: $_"
    }
    Write-Status "Account created."
    $User = Get-LocalUser -Name $AccountName -ErrorAction Stop
} else {
    # Account exists — sync the password so Python's stored value stays authoritative.
    Write-Status "Account found. Syncing password..."
    try {
        $User | Set-LocalUser -Password $SecurePassword -ErrorAction Stop
    } catch {
        Fail "Failed to update password: $_"
    }
    Write-Status "Password synced."
}

# ---------------------------------------------------------------------------
# Ensure the account is enabled
# ---------------------------------------------------------------------------

$User = Get-LocalUser -Name $AccountName -ErrorAction Stop
if (-not $User.Enabled) {
    Write-Status "Account is disabled. Enabling..."
    try {
        Enable-LocalUser -Name $AccountName -ErrorAction Stop
    } catch {
        Fail "Failed to enable account: $_"
    }
    Write-Status "Account enabled."
}

# ---------------------------------------------------------------------------
# Ensure the account is NOT in the Administrators group
# ---------------------------------------------------------------------------

$InAdmins = $false
try {
    $Members = Get-LocalGroupMember -Group $AdminGroupName -ErrorAction SilentlyContinue
    if ($Members) {
        $InAdmins = ($Members | Where-Object {
            $_.Name -eq $AccountName -or $_.Name -like "*\$AccountName"
        }).Count -gt 0
    }
} catch {
    # Non-fatal: if we cannot query the group, we cannot fix it — flag and continue.
    Write-Status "Warning: could not verify Administrators group membership: $_"
}

if ($InAdmins) {
    Write-Status "Account is in Administrators group. Removing..."
    try {
        Remove-LocalGroupMember -Group $AdminGroupName -Member $AccountName -ErrorAction Stop
    } catch {
        Fail "Failed to remove account from Administrators group: $_"
    }
    Write-Status "Removed from Administrators group."
}

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

Write-Status "Ready."
exit 0
