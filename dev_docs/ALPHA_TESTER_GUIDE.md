# Peach 1UP — Alpha Tester Guide

Thank you for testing Peach 1UP. This is a pre-release build. Expect rough edges,
and please report everything you find — broken flows, confusing UI, crashes, and
anything that feels wrong. Your feedback directly shapes the release.

**Feedback:** Post in the Discord `#alpha-testing` channel. Include your Windows
version, what you were doing, and what happened.

---

## What Peach 1UP Is

A one-click launcher for retro software. Point it at old media, pick an era, and
the correct emulator launches with everything configured — no manual emulator setup
required. The alpha covers DOS, Windows 95/98/XP, and first-generation consoles
(PS1, PS2, Xbox OG, NES, SNES, N64, Dreamcast).

---

## System Requirements

- Windows 10 or Windows 11 (64-bit)
- 8 GB RAM minimum, 16 GB recommended
- GPU with DirectX 11 support
- ~35 GB free disk space for the full bundle
- A modern browser (Chrome, Edge, or Firefox) — Peach 1UP runs as a local web app

---

## Installation

1. Download Peach1UP-alpha.7z from the link posted in Discord
2. Extract the archive to a folder of your choice (e.g. C:\Peach1UP\)
3. Open the extracted folder and double-click peach1up.exe
4. A terminal window opens — this is normal, leave it running in the background
5. Your browser opens automatically to http://localhost:8000

If the browser does not open automatically, navigate to http://localhost:8000 manually.

To stop Peach 1UP, close the terminal window.

---

## First Run

The first-run wizard runs automatically on a clean install.

**Step 1 — Create owner account**
Set a 4–6 digit PIN. This is the owner account — it has full access to everything.
Store it somewhere safe; recovery requires running a script locally.

**Step 2 — Emulator setup**
All emulators ship with the bundle. The wizard confirms each one is detected.
Everything should show green. If any emulator shows as missing, report it in Discord.

**Step 3 — Library**
The bundle includes pre-loaded media. The wizard will find it automatically.
You do not need to point Peach 1UP at any external folders to get started.

When the wizard completes you land on the Library page.

---

## Feature Walkthroughs

### Library

The Library is the main view — all your media in one place.

- **Browse** — scroll through library items; filter by era using the sidebar
- **Add media** — click Add Media, browse to a file or folder, and Peach 1UP detects the era automatically
- **Item detail** — click any item to see its details: era, detected executable, drive, profile, launch history
- **Launch** — select a profile from the dropdown on the item detail page, then click Launch. The profile must be set before Launch is enabled
- **Era mismatch** — if you select a profile from a different era, a warning appears. You can proceed but results may be unexpected
- **Scan** — use the Scan button to scan a folder for new media in bulk

### Emulators

Shows all supported emulators and their detection status.

- **Status** — green means the binary is detected and ready; amber means configuration needed; red means missing
- **Profiles** — each emulator has one or more launch profiles (hardware presets). You can create, edit, clone, and delete profiles
- **Sandbox tier** — shows the current isolation level (Job Object or AppContainer). xemu shows a warning banner instead of a toggle — this is expected, see Known Limitations
- **Auto-detect** — re-scans for emulator binaries if you've moved or updated one

### Environments

Environments are persistent workspaces for software that requires installation — Windows 95, 98, and XP titles that need to be installed before they can run.

- **Create** — register a Windows OS image as an environment
- **Launch** — boots the environment with the selected media attached
- **Snapshots** — create a named snapshot before installing new software; restore from any snapshot if something breaks

### Users

Peach 1UP supports multiple household accounts.

- **Switch user** — click your avatar in the top bar to open the user switcher; select a profile and enter its PIN
- **Add user** — owner only; go to Settings → Users → Add User; set a name, PIN, and content rating limit
- **PIN lockout** — 4 consecutive wrong PINs locks the account; the owner can unlock it in Settings → Users
- **Owner lockout** — if the owner is locked out, run `scripts/setup_admin_user.py` from the install directory in a terminal

### Settings

- **Library paths** — configure where Peach 1UP looks for media (edit `config/settings.yaml` directly for non-standard locations — see Known Limitations)
- **Users** — manage accounts, reset PINs, unlock accounts
- **Attribution** — GPL source links and emulator credits

### Tags

Tags associate profiles with contexts — hardware configs, content types, environments.
System tags are pre-created (voodoo, mt32, soundblaster, adlib, accuracy-mode, networking, mods).
Create custom tags freely. Tags appear on item detail and profile pages for filtering.

---

## Launching Your First Game

1. Go to **Library**
2. Click any item in the list
3. On the item detail page, open the **Profile** dropdown and select a profile
4. Click **Launch**
5. The emulator opens with the media loaded
6. Close the emulator window when done — Peach 1UP detects the exit automatically

If the launch button is greyed out, a profile has not been selected.

---

## Known Limitations

These are confirmed issues in this build. Do not report these as bugs — they are already tracked.

**xemu (Xbox OG) — no AppContainer isolation**
xemu runs on QEMU TCG which requires a kernel call that AppContainer blocks. xemu runs under Job Object isolation only. This is a permanent platform constraint, not a pending fix. The Emulators page shows a warning banner instead of a sandbox toggle for xemu.

**LaunchProfiles — launch commands wiped on save**
If a profile has custom launch commands configured, editing and saving the profile will wipe those commands. Avoid editing profiles that have launch commands set until this is fixed.

**Library path configuration — no UI**
The library path settings panel is not available in the UI for this build. If your media lives outside the default install directory, edit `config/settings.yaml` directly. The 86Box ROM path is the most common case — if 86Box fails to launch, check that `ROMS_PATH` in `settings.yaml` points to the correct directory.

**86Box AppContainer — untested**
86Box runs under Job Object isolation only for this alpha. AppContainer has not been validated for 86Box yet.

**Flycast (Dreamcast) — may have launch issues**
Flycast is included but has a known dispatch bug that may cause launches to fail with a generic error. If Dreamcast titles fail to launch, report it with the exact error message shown.

**Launch history — no delete**
There is no way to clear launch history in this build. It accumulates indefinitely.

**Concurrent DOS launches**
Do not launch two DOS titles at the same time. This is unsupported in the alpha.

---

## Recovery Procedures

**Emulator window opened but nothing loaded / black screen**
Close the emulator. Check the item detail page for a "short-lived exit" warning flag. Try a different profile. If it persists, report it.

**App won't load in browser after restart**
Check the system tray — if the Peach 1UP icon is present, right-click and select Restart. If the icon is absent, relaunch from Start Menu → Peach 1UP.

**PIN lockout (sub-account)**
Owner goes to Settings → Users, finds the locked account, and clicks Unlock.

**PIN lockout (owner)**
Open a terminal in the Peach 1UP install directory and run:

```
python scripts/setup_admin_user.py
```

This overwrites the owner account interactively. You will need to set a new PIN.

**86Box launches but immediately closes**
The ROM pack may not be detected. Check Settings → Emulators → 86Box for a ROM path warning. If the path is wrong, edit `config/settings.yaml` and set `ROMS_PATH` to the correct directory, then restart the backend from the system tray.

**Environment (Win95/98/XP) shows driver prompts on every boot**
This is the PnP hardware detection loop. It should not occur in this build — if you see repeated driver prompts on consecutive boots of the same environment, report it with the era and any steps to reproduce.

**Database or startup error on launch**
Check `logs/peach1up.log` in the install directory for the error message and paste it in Discord.

---

## Reporting Bugs

Post in `#alpha-testing` on Discord. Include:

- **What you were doing** — which feature, which era, which step
- **What happened** — exact error message if shown, or describe what went wrong
- **What you expected** — what should have happened
- **Your system** — Windows version, GPU model
- **Log file** — attach `logs/peach1up.log` from the install directory if the app crashed or threw an error

Screenshots and screen recordings are very welcome.

---

## Out of Scope for This Alpha

Do not spend time testing these — they are known incomplete:

- Linux support (Windows only for alpha)
- Metadata enrichment (cover art, descriptions from external sources)
- LLM-assisted scan (Smart Scan inc.)
- Streaming integration
- Controller remapping UI (Works out the box with Xbox PC controller)
