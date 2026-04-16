# Images Directory

This directory is for user-supplied ROM files and game media.

**⚠️ IMPORTANT: Never commit any files in this directory to version control.**

## Directory Structure

- `./images/roms/` - 86Box ROM pack (required for Windows 95/98/XP)
- `./images/games/` - Game media files (.iso, .img, .cue)

## ROM Pack Setup (Windows 95, 98, XP era)

86Box requires system ROM files to function. These are copyrighted but required for 86Box to work.

**Option 1 — Automatic (recommended)**
Open Peach 1UP, go to Settings, and select "Download ROM pack". The launcher will clone the official ROM pack automatically.

**Option 2 — Manual**
Clone or download the ROM pack yourself from https://github.com/86Box/roms and place the files in `./images/roms/`

## File Types Supported

- **.iso** - CD-ROM image files
- **.img** - Disk image files
- **.cue** - Cue sheet files (with accompanying .bin)

## Emulators

Emulators run natively on Windows under Job Objects isolation — not inside containers.

- **DOSBox-X** (DOS, Windows 3.1): https://dosbox-x.com
- **86Box** (Windows 95, 98, XP): https://86box.net

## Safety Notes

- All media files are mounted read-only
- No modifications are made to your original files
- Network access is blocked for every emulator launch via Windows Firewall
