# Images Directory

This directory holds user-supplied OS platform images, per-game hard drive images,
and emulator ROM files. **Never commit any files in this directory to version control.**

---

## Directory Structure

```
images/
├── os/          # OS platform images — base and working copies
│   ├── dos/
│   ├── win31/
│   ├── win95/
│   ├── win98/
│   └── winxp/
├── hdd/         # DOS per-game HDD images (.img, auto-created by launcher)
└── roms/
    └── 86box/   # 86Box ROM pack (required for accuracy mode)
```

---

## OS Platform Images (`os/`)

Win95, Win98, and XP use an **OSPlatform** model. When you register a platform image,
the launcher locks your original as the **base image** and creates a separate
**working copy** that all launches use. The base is never modified.

**Disk usage warning:** Registering a platform stores two copies of the image.
Working copies and any snapshots will accumulate over time. Plan for at least 2×
the size of each image you register.

Supported formats: `.img`, `.vhd`, `.iso`

Source images from your own disc media or community archives such as WinWorldPC.
Peach 1UP does not automate any downloads. Ensure you have the right to use any
image you register.

---

## DOS Per-Game HDD Images (`hdd/`)

DOS profiles use standalone per-game HDD images rather than a shared OS platform.
The launcher auto-creates a `.img` file here on first install and reuses it on
subsequent launches. No manual setup required.

---

## 86Box ROM Pack (`roms/86box/`)

86Box requires system ROM files to function. These are used only when a Win95 or
Win98 profile has hardware accuracy mode enabled.

Clone the official ROM pack into `roms/86box/`:

```terminal
git clone https://github.com/86Box/roms images\roms\86box
```

Then set `ROM_PATH` in your `.env` to point at that directory.

If the ROM pack is absent, accuracy mode will be unavailable and a warning will
appear next to the affected eras in the era selector.
