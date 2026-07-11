# Peach 1UP — Emulator Reference

Canonical reference for every supported emulator. Used to build and maintain
the per-emulator descriptor manifests (`config/emulators/*.toml`).

---

## DOSBox-X

**Supported eras:** DOS

**Portable mode mechanism:** Pass `-conf <path>` to specify config file, or
set `working directory = program` in the config — DOSBox-X resolves data paths
relative to the config file's directory.

**Default user data path (Windows):** `%APPDATA%\DOSBox-X\`

**Required files:** None. No BIOS required for DOS.

**Optional files:**

| Filename   | Purpose                  | Location       |
| ---------- | ------------------------ | -------------- |
| `FONT.ROM` | PC-98 BIOS (NEC systems) | next to binary |

**ROM/BIOS version coupling:** None. PC-98 BIOS is optional and version-independent.

**Official download:** https://dosbox-x.com

**BIOS/ROM source:** N/A

**Bundleable:** Yes

**Portable mode confirmed:** Yes

**Multi-disc capability:** Can mount more than one floppy image at once with
a built-in swap command. Automating the swap from Peach 1UP vs. relying on
DOSBox-X's own swap-floppy hotkey is undecided. Note: DOSBox-X's swap key
differs from classic DOSBox (not Ctrl+F4).

---

## 86Box

**Supported eras:** Windows 95, Windows 98, Windows XP

**Portable mode mechanism:** Place `roms/` and `assets/` directories next to
the binary. 86Box detects portable mode by checking for these directories at
startup.

**Default user data path (Windows):** `%APPDATA%\86Box\`

**Required files:**

| Filename/Path      | Purpose          | Location               | Notes                                                                                                                                                                                                      |
| ------------------ | ---------------- | ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --- | --------- | --------- | ------------------------ | --- |
| `roms/<machine>/…` | Machine ROM pack | `roms/` next to binary | Filenames and subdirectory structure are hardcoded — renaming any file breaks emulation. Peach 1UP validates directory presence only — per-machine completeness is unvalidated, see limitation note below. |     | `assets/` | UI assets | `assets/` next to binary |     |

**Optional files:** None beyond the ROM pack.

**ROM/BIOS version coupling:** The ROM pack version must match the emulator
version exactly. Mixing ROM pack and binary versions causes silent emulation
failures or startup errors. Always update both together.
ROM pack: https://github.com/86Box/roms

**Per-machine ROM completeness — not validated (known limitation):** 86Box's
hard-fail-on-missing-ROMs behavior only covers total absence of the ROM set —
if no ROM dumps are found at all, 86Box errors and closes on startup. It does
NOT mean every individual machine/video-card ROM is verified before launch.
A specific machine profile (e.g. one routing to a Voodoo2 card) can be missing
just that card's ROM and 86Box will not necessarily surface a clean, scriptable
error — behavior here is unconfirmed. 86Box does expose `-M`/`--dumpmissing`,
a CLI flag that outputs a list of all machines and video cards with missing
ROMs, and prints the full ROM search path list to stdout/log on every startup.
Neither is wired into Peach 1UP today. Tracked as a PX item: shell out to
`--dumpmissing` as a pre-flight check before/after launch to surface per-machine
gaps instead of relying on 86Box's own (currently unverified) in-app behavior.

**Official download:** https://86box.net

**BIOS/ROM source:** https://github.com/86Box/roms

**Bundleable:** Yes (binary only; ROM pack is user-supplied)

**Portable mode confirmed:** Yes

**Multi-disc capability:** Only one secondary optical drive slot per machine.
A multi-disc install requires swapping the disc image manually through
86Box's own Media menu — no playlist/stack equivalent exists or is planned.

---

## DuckStation

**Supported eras:** PS1

**Portable mode mechanism:** Place an empty `portable.txt` file next to the
binary. DuckStation detects this file on startup and redirects all user data
to a `userdata/` directory next to the binary.

**Default user data path (Windows):** `%APPDATA%\DuckStation\`

**Required files:**

| Filename | Purpose  | Location       | Notes                                          |
| -------- | -------- | -------------- | ---------------------------------------------- |
| `*.bin`  | PS1 BIOS | `bios/` subdir | Filenames are flexible — auto-detected by hash |

**Optional files:** None.

**ROM/BIOS version coupling:** DuckStation auto-detects BIOS region via hash.
Multiple BIOS files (SCPH-1001, SCPH-7502, etc.) can coexist in `bios/` and
the correct one is selected automatically per disc.

**Official download:** https://www.duckstation.org

**BIOS/ROM source:** Dump from your own PS1 hardware.

**Bundleable:** Yes

**Portable mode confirmed:** Yes

**Multi-disc capability:** Natively supports .m3u playlists listing every
disc in a set — Peach 1UP can point DuckStation at a generated playlist
instead of a single disc. Mid-session disc switching can be bound to a
hotkey inside DuckStation; no external trigger exists.

---

## PCSX2

**Supported eras:** PS2

**Portable mode mechanism:** Any of the following triggers portable mode:

- Place an empty `portable.txt` next to the binary
- Place an empty `portable.ini` next to the binary
- Pass `-portable` on the command line

All user data redirects to a `userdata/` directory next to the binary.

**Default user data path (Windows):** `%APPDATA%\PCSX2\`

**Required files:**

| Filename                                   | Purpose  | Location       | Notes                                                                       |
| ------------------------------------------ | -------- | -------------- | --------------------------------------------------------------------------- |
| PS2 BIOS set (`*.bin`, `*.rom*`, `*.erom`) | PS2 BIOS | `bios/` subdir | Multi-file BIOS sets must keep original filenames — renaming breaks the set |

**Optional files:** None.

**ROM/BIOS version coupling:** The full multi-file BIOS set must be kept
intact. Partial sets or renamed files will fail to load.
The `bios/` subdirectory path is configurable in PCSX2 settings.

**Official download:** https://pcsx2.net

**BIOS/ROM source:** Dump from your own PS2 hardware.

**Bundleable:** Yes

**Portable mode confirmed:** Yes

**Multi-disc capability:** Natively supports .m3u playlists, same as
DuckStation. No hotkey or external command for switching discs mid-session —
only via PCSX2's own in-game "Change Disc" menu.

---

## xemu

**Supported eras:** Xbox OG

**Portable mode mechanism:** Place `xemu.toml` next to the binary. xemu
detects this file on startup and uses the directory as its data root.

**Caveat:** The `-config_path` flag does **not** redirect the shader cache or
log files — these always write to the default user profile location regardless
of portable mode. See [xemu issue #2480](https://github.com/mborgerson/xemu/issues/2480).

**Default user data path (Windows):** `%APPDATA%\xemu\`

**Required files:**

| Filename         | Purpose        | Location                  | Notes                                                               |
| ---------------- | -------------- | ------------------------- | ------------------------------------------------------------------- |
| `mcpx_1.0.bin`   | MCPX boot ROM  | configured in `xemu.toml` | Known-bad dump MD5: `196a5f59a13382c185636e691d6c323d` — do not use |
| `*.bin`          | Flash BIOS     | configured in `xemu.toml` |                                                                     |
| `xbox_hdd.qcow2` | 8 GB HDD image | configured in `xemu.toml` | Must be a properly formatted 8 GB qcow2 image                       |

**Optional files:** None.

**ROM/BIOS version coupling:** The MCPX boot ROM and Flash BIOS are tied to
specific Xbox revisions. Mismatched pairs will fail to boot.

**Official download:** https://xemu.app

**BIOS/ROM source:** Dump from your own Xbox OG hardware.

**Bundleable:** Yes

**Portable mode confirmed:** Yes (with shader cache caveat above)

### Xbox disc image format (xiso)

xemu requires disc images in xiso format — the Xbox game partition extracted
with the video partition stripped. The `.iso` extension is identical to a
standard disc image; the difference is internal layout.

**Detection:** xiso images have the magic string `MICROSOFT*XBOX*MEDIA` at
offset `0x10000`. A raw DVD rip has ISO 9660 structure (`CD001` at `0x8001`)
with no Xbox magic present.

**Raw DVD rips (7–8 GB)** will be rejected at launch with a clear error.
Use [extract-xiso](https://github.com/xboxdev/extract-xiso) to convert:
`extract-xiso -r <image.iso>`

Detection logic lives in `backend/service/utils/xbox_image.py`.

### Current State as of 7/7/2026
xemu crashes on relaunch with configured BIOS/EEPROM/disk files (0xc0000409, msvcrt.dll)
Confirmed upstream xemu bug, not Peach 1UP or driver-specific as it can be reproduced with a completely fresh xemu 0.8.136 download run standalone outside Peach 1UP entirely, using only Peach 1UP's existing BIOS/EEPROM/qcow2 files. First-boot (unconfigured) launches work fine; any launch that actually attempts to boot a machine with system files configured crashes with STATUS_STACK_BUFFER_OVERRUN in msvcrt.dll. Cross-vendor: reported on both AMD (this project, RX 9070 XT) and NVIDIA (upstream issue #1486, RTX 3080 Ti) GPUs, ruling out a driver-specific cause. See xemu-project/xemu#1486 (https://github.com/xemu-project/xemu/issues/1486) for a near-identical upstream report.

Workaround: disable Control Flow Guard for xemu.exe, specifically, for Windows: Security → App & browser control → Exploit protection settings → Program settings → Add program to customize → By name → xemu.exe → override system settings, disable CFG. No code fix possible on our end.

---

## Mesen

**Supported eras:** NES, Famicom Disk System (FDS)

**Portable mode mechanism:** On first run, Mesen presents a setup dialog
asking where to store data. Select the application directory to enable
portable mode. This dialog was added in version 0.9.2.

**Default user data path (Windows):** `%APPDATA%\Mesen\` (if not set to portable)

**Required files:** None. No BIOS required for standard NES/Famicom titles.

**Optional files:**

| Filename      | Purpose                  | Location         | SHA1                                       |
| ------------- | ------------------------ | ---------------- | ------------------------------------------ |
| `FdsBios.bin` | Famicom Disk System BIOS | `FirmwareFiles\` | `e4e41472c454f928e53eb10e0509bf7d1146ecc1` |

Mesen 2 adds optional SNES coprocessor ROMs (DSP-1, ST-010, etc.) for enhanced
compatibility with SNES titles.

**ROM/BIOS version coupling:** None beyond the optional FDS BIOS.

**Official download:** https://www.mesen.ca

**BIOS/ROM source:** Dump from your own Famicom Disk System hardware.

**Bundleable:** Yes

**Portable mode confirmed:** Yes

**Multi-disc capability:** Not applicable — FDS multi-disk titles are single
self-contained files; side/disk switching is handled inside Mesen itself.

---

## Project64

**Supported eras:** N64

**Portable mode mechanism:** Project64 is portable by default when its install
directory is writable. All configuration is stored in `Config\` under the
application path (`AppPath\Config\`).

**Default user data path (Windows):** `<install dir>\Config\`

**Required files:** None. No BIOS required.

**Optional files:** None.

**ROM/BIOS version coupling:** None.

**Official download:** https://www.pj64-emu.com

**BIOS/ROM source:** N/A

**Bundleable:** Yes

**Portable mode confirmed:** Yes

**Multi-disc capability:** Not applicable for cartridge games. 64DD disk
titles (rare in this app's supported library) require manual swapping
inside Project64's own menu.

---

## Flycast

**Supported eras:** Dreamcast

**Portable mode mechanism:** Place `emu.cfg` next to the binary. Flycast
checks for this file on startup and uses the directory as its data root.

**Default user data path (Windows):** `%APPDATA%\flycast\`

**Required files:**

| Filename       | Purpose             | Location               | Notes                             |
| -------------- | ------------------- | ---------------------- | --------------------------------- |
| `dc_boot.bin`  | Dreamcast BIOS ROM  | `data/` next to binary | Required for boot                 |
| `dc_flash.bin` | Dreamcast flash ROM | `data/` next to binary | Required for region/date settings |

**Optional files:** None.

**ROM/BIOS version coupling:** `dc_boot.bin` and `dc_flash.bin` must be from
the same hardware revision. Mismatched pairs may cause region or boot failures.

**Official download:** https://github.com/flyinghead/flycast

**BIOS/ROM source:** Dump from your own Dreamcast hardware.

**Bundleable:** Yes

**Portable mode confirmed:** Yes

_Note:_ Flycast will not support DX9 out of the box. This means Flycast will not run on older OSs like Windows 7 or earlier.
You can fix this by rebuilding Flycast frmo the emulators/flycast dir with the DX9 SDK installed on your PC. See Flycast Github for
build details.

Dependencies are included in `peach_1up\emulators\flycast\dependencies`. The release build is built with:

```bash
cmake -S . -B build -A x64 -DUSE_DX9=OFF -DUSE_VULKAN=ON -DUSE_DX11=ON -DUSE_OPENGL=ON
```

---

## Legal

The root `LICENSE` file for this repository is GPL-2.0-or-later. DuckStation is distributed unmodified under CC BY-NC-ND 4.0 (non-GPL, non-commercial only). All other bundled emulators are GPL-2.0 or GPL-3.0.

| Emulator    | License         | License File   | SOURCE_OFFER.txt | Install Type     |
| ----------- | --------------- | -------------- | ---------------- | ---------------- |
| 86Box       | GPL-2.0         | COPYING        | Yes              | github_release   |
| DOSBox-X    | GPL-2.0         | COPYING        | Yes              | github_release   |
| DuckStation | CC BY-NC-ND 4.0 | LICENSE.txt    | No               | zip              |
| Flycast     | GPL-2.0         | LICENSE        | Yes              | github_release   |
| Mesen       | GPL-3.0         | LICENSE        | Yes              | github_release   |
| PCSX2       | GPL-3.0         | COPYING.GPLv3  | Yes              | bundled          |
| Project64   | GPL-2.0         | license.md     | Yes              | bundled          |
| xemu        | GPL-2.0         | LICENSE.txt    | Yes              | github_release   |
