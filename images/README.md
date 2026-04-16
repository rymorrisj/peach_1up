# Images Directory

This directory is for user-supplied OS base images, ROM files, and game media.

**⚠️ IMPORTANT: Never commit any files in this directory to version control.**

## Required Files

### ROM Files (for 86Box - Windows 95/98/XP support)

86Box requires system ROM files to function. Download the official ROM pack:

**Official 86Box ROM Pack:** https://github.com/86Box/roms

Extract the ROM pack to: `./images/roms/`

### OS Base Images (Optional)

You can place OS installation images here for reference:

- `./images/os/` - Windows 95/98/XP installation ISOs
- `./images/games/` - Game media files (.iso, .img, .cue)

## File Types Supported

- **.iso** - CD-ROM image files
- **.img** - Disk image files  
- **.cue** - Cue sheet files (with accompanying .bin)
- **.bin** - Binary data files (used with .cue)

## Official Download Links

### Required Software
- **Docker Desktop:** https://www.docker.com/products/docker-desktop
- **VcXsrv:** https://sourceforge.net/projects/vcxsrv

### Emulators (bundled in Docker containers)
- **DOSBox-X:** https://dosbox-x.com
- **86Box:** https://86box.net

### ROM Requirements
- **86Box ROM pack:** https://github.com/86Box/roms

## Safety Notes

- All media files are mounted **read-only** in containers
- No modifications are made to your original files
- Containers run with **networking disabled** by default