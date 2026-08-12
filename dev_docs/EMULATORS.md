# Emulator Reference

Canonical reference for every supported emulator. This is the source material behind the
per-emulator descriptors in [`config/emulators/`](../config/emulators/); when the two
disagree, the TOML wins and this file is the bug.

Related: [TECH.md](TECH.md) (stack) · [SECURITY.md](SECURITY.md) (isolation policy) ·
[windows-sandbox.md](windows-sandbox.md) (resource caps).

## Summary

| Emulator | Eras | Portable via | Data root | Required user files |
|---|---|---|---|---|
| DOSBox-X | DOS | `-conf <path>` | Config file directory | None |
| 86Box | Win95, Win98, WinXP | `roms/` + `assets/` next to binary | `emulators/86box/` | 86Box ROM pack |
| DuckStation | PS1 | `portable.txt` | `userdata/` next to binary | PS1 BIOS |
| PCSX2 | PS2 | `portable.txt` | `userdata/` next to binary | PS2 BIOS set |
| RPCS3 | PS3 | Automatic on Windows | Install directory | PS3 firmware (`PS3UPDAT.PUP`) |
| xemu | Xbox OG | `xemu.toml` | Binary directory, partial | Xbox BIOS, `xbox_hdd.qcow2` |
| Xenia | Xbox 360 | `portable.txt` | `emulators/xenia/` | None |
| Mesen | NES, SNES | First-run dialog choice | Binary directory or `%APPDATA%` | None (FDS BIOS optional) |
| Project64 | N64 | Default when install dir is writable | `<install dir>\Config\` | None |
| Flycast | Dreamcast | `emu.cfg` | `emulators/flycast/` | Dreamcast BIOS pair |

Without its sentinel, each emulator falls back to `%APPDATA%\<Name>\`, except Xenia
(`Documents\Xenia\`) and Project64 (already portable).

## DOSBox-X

**Eras:** DOS. **Download:** https://dosbox-x.com

Pass `-conf <path>` and DOSBox-X resolves data paths relative to the config file's
directory. Peach 1UP writes a fresh conf per launch into a private temp directory; see
[windows-sandbox.md](windows-sandbox.md) § DOSBox-X specifics.

No BIOS required. `FONT.ROM` (PC-98 BIOS for NEC systems) is optional, sits next to the
binary, and is version-independent.

**Multi-disc:** can mount multiple floppy images at once with a built-in swap command.
Whether Peach 1UP drives the swap or leaves it to DOSBox-X's hotkey is undecided. The swap
key differs from classic DOSBox (not Ctrl+F4).

**Known limitation:** games that write sound config to their install directory (Doom's
`DEFAULT.CFG`) have no in-game sound from a read-only ISO. Install to a writable HDD image
to persist it.

## 86Box

**Eras:** Windows 95, 98, XP. **Download:** https://86box.net ·
**ROM pack:** https://github.com/86Box/roms

Portable mode is detected by the presence of `roms/` and `assets/` next to the binary.

| Path | Purpose | Notes |
|---|---|---|
| `roms/<machine>/…` | Machine ROM pack | Filenames and subdirectory structure are hardcoded. Renaming anything breaks emulation. |
| `assets/` | UI assets | |

**Version coupling is strict.** The ROM pack version must match the binary version
exactly. Mixing them causes silent emulation failures or startup errors. Update both
together.

**Per-machine ROM completeness is not validated.** 86Box hard-fails only on total absence
of the ROM set: if no dumps are found at all it errors and closes. It does not verify every
individual machine or video-card ROM. A machine profile routing to a Voodoo2 can be missing
just that card's ROM, and whether 86Box surfaces a clean, scriptable error is unconfirmed.
86Box exposes `-M` / `--dumpmissing`, which lists every machine and video card with missing
ROMs, and prints the full ROM search path on every startup. Neither is wired into Peach 1UP.

86Box also ships no guest drivers, so a provisioned environment has the ROM pack and BIOS
but nothing installed to use them.

**Multi-disc:** one secondary optical drive slot per machine. Swapping is manual through
86Box's own Media menu; there is no playlist equivalent and none is planned.

**AppContainer:** disabled by default. It works in some environments and not others, is
environment-dependent, and is not being investigated further. Not hard-capped, so it can be
enabled per install.

## DuckStation

**Eras:** PS1. **Download:** https://www.duckstation.org

Drop an empty `portable.txt` next to the binary and all user data redirects to `userdata/`.

PS1 BIOS files go in `emulators/duckstation/bios/`. Filenames are flexible: DuckStation
auto-detects region by hash, and multiple region files (SCPH-1001, SCPH-7502, and so on)
can coexist with the right one selected per disc.

**Multi-disc:** natively supports `.m3u` playlists, so Peach 1UP can point at a generated
playlist instead of a single disc. Mid-session disc switching is a DuckStation hotkey only;
there is no external trigger.

**Not bundled.** DuckStation is CC BY-NC-ND 4.0 (non-commercial, no derivatives), so it is
never redistributed. It is fetched unmodified from the project's own release, published
under the fixed tag `latest`.

## PCSX2

**Eras:** PS2. **Download:** https://pcsx2.net

Any of `portable.txt`, `portable.ini`, or `-portable` triggers portable mode, redirecting
user data to `userdata/`.

The PS2 BIOS is a multi-file set (`*.bin`, `*.rom*`, `*.erom`) and goes in
`emulators/pcsx2/bios/`. All files must be present with original filenames. Partial sets or
renames fail to load.

**Multi-disc:** `.m3u` playlists, same as DuckStation. Mid-session switching is PCSX2's own
in-game Change Disc menu only.

The Windows Qt build ships as a `.7z` and is extracted with the vendored 7-Zip.

## RPCS3

**Eras:** PS3. **Download:** https://rpcs3.net/download

Portable on Windows automatically: RPCS3 treats its executable directory as the data root,
so no sentinel is created or needed and `rpcs3.toml` has no `portable_sentinel`. The
install directory holds `dev_flash/`, `dev_hdd0/`, `dev_bdvd/`, `config/`, `cache/`, and
`games/`.

Firmware (`PS3UPDAT.PUP`) is installed by RPCS3 itself, not copied into place: use
`File > Install Firmware` or pass `--installfw`. Peach 1UP does not provide, link to, or
assist with acquiring firmware. Any reasonably current version works.

Installed from `github.com/RPCS3/rpcs3-binaries-win`, a companion binaries repo to the
`RPCS3/rpcs3` source repo, which publishes no downloadable releases of its own. The asset
is a `.7z`, extracted with the vendored 7-Zip.

**Multi-disc:** not applicable, PS3 titles are single-disc.

| Limitation | Severity | Detail |
|---|---|---|
| AppContainer not supported | critical | Heavily JIT-based recompiler (Cell PPU/SPU and RSX) relying on runtime code generation and low-level syscalls that AppContainer's restricted token blocks. Job Object isolation only. Note that `container_permanently_excluded = false` in the TOML contradicts this entry; see the open items in [CHANGELOG.md](../CHANGELOG.md). |
| `.pkg` installs need two launches | info | RPCS3 refuses `--installpkg` combined with `--no-gui` and never exits on its own after an unattended install, so one call cannot both install and boot inside the coordinator's 30s dispatch window. The first launch starts the install and returns once it stabilizes on disk (RPCS3 is terminated automatically, no dialog to dismiss). Launching again boots normally from `dev_hdd0/game/<TITLE_ID>/`. |
| First-launch stutter | info | Shaders and PPU/SPU code are compiled on first boot of a title. Later launches are smoother once caches are warm. |
| Controllers need manual binding | info | No auto-detection. Open Pads Settings inside RPCS3 and bind a gamepad, or input falls back to keyboard. |

Both Job Object caps are enforced (`skip_cpu_limit = false`, `skip_memory_limit = false`).

## xemu

**Eras:** Xbox OG. **Download:** https://xemu.app

Place `xemu.toml` next to the binary and xemu uses that directory as its data root.

| File | Purpose | Notes |
|---|---|---|
| `mcpx_1.0.bin` | MCPX boot ROM | Known-bad dump MD5 `196a5f59a13382c185636e691d6c323d`, do not use |
| `*.bin` | Flash BIOS | Tied to a specific Xbox revision; mismatched pairs will not boot |
| `xbox_hdd.qcow2` | 8 GB HDD image | Must be a properly formatted 8 GB qcow2 |

All three go in `emulators/xemu/data/default/`.

**Portability is partial.** `-config_path` does not redirect the shader cache or log files,
which always write to `%APPDATA%\xemu\` regardless. See
[xemu issue #2480](https://github.com/mborgerson/xemu/issues/2480). AppContainer does not
redirect `%APPDATA%` either, so the container SID is granted write access to that directory
at first launch.

**Memory cap must stay above 2048 MB.** xemu pre-allocates a 1 GB JIT buffer at startup and
exits immediately with a paging file error if the `xbox` era cap is smaller. This is why the
cap is enforced rather than skipped: sizing it correctly is the fix.

**AppContainer is enabled** as of 2026-08-11. The previous exclusion blamed QEMU's TCG
backend calling `DeviceIoControl` for qcow2 geometry; that diagnosis was wrong. The real
cause was memory and CPU limits sized below the JIT heap, producing an early exit that
looked like an incompatibility.

### Xbox disc images must be xiso

xemu needs the Xbox game partition extracted with the video partition stripped. The `.iso`
extension is identical to a standard disc image; the difference is internal layout.

| Signature | Meaning |
|---|---|
| `MICROSOFT*XBOX*MEDIA` at offset `0x10000` | xiso |
| `CD001` at `0x8001`, file over 4 GB | Raw DVD rip |

Raw rips (7 to 8 GB) are rejected at launch with a clear error. Convert with
[extract-xiso](https://github.com/xboxdev/extract-xiso):

```bash
extract-xiso -r <image.iso>
```

Detection lives in
[`detection/xbox_image.py`](../backend/service/utils/detection/xbox_image.py), with the
format-level checks in the vendored `formatscout` package.

### Upstream relaunch crash (unresolved)

xemu crashes on relaunch with configured BIOS, EEPROM, and disk files: `0xc0000409`
(`STATUS_STACK_BUFFER_OVERRUN`) in `msvcrt.dll`. Confirmed upstream, not Peach 1UP
specific: reproducible with a completely fresh xemu 0.8.136 download run standalone,
using only Peach 1UP's existing BIOS/EEPROM/qcow2 files. First-boot (unconfigured) launches
work; any launch that actually boots a configured machine crashes. Reported on both AMD
(RX 9070 XT) and NVIDIA (RTX 3080 Ti) hardware, ruling out a driver cause. See
[xemu-project/xemu#1486](https://github.com/xemu-project/xemu/issues/1486).

Workaround, no code fix possible: disable Control Flow Guard for `xemu.exe` via Windows
Security → App & browser control → Exploit protection settings → Program settings → Add
program to customize → By name → `xemu.exe` → override system settings, CFG off.

## Xenia

**Eras:** Xbox 360. **Download:** https://xenia.jp

An empty `portable.txt` next to the binary resolves `storage_root` to
`emulators/xenia/` instead of `Documents\Xenia\`. Peach 1UP creates the sentinel
automatically after install via `ensure_portable_mode`, driven by `portable_sentinel` in
the descriptor. The data root then holds `content/` (saves and DLC) and `cache/` (shader
cache).

No BIOS or firmware required.

Installed from `github.com/xenia-project/release-builds-windows`, a companion CI repo to
the `xenia-project/xenia` source repo. Asset is `xenia_master.zip`.

**Known limitation (warning):** the default `gpu = "any"` resolves to D3D12 and has been
confirmed to trigger an AMD GPU driver timeout during gameplay. Switching to
`gpu = "vulkan"` avoids it, but Xenia's own in-app warning calls its Vulkan FBO render path
"heavily incomplete, early development". There is no clean default. Change the `gpu` key in
Xenia's portable `xenia.config.toml` (or in-app under Settings) and restart.

**Multi-disc:** not applicable for `.iso` and `.xex`.

## Mesen

**Eras:** NES, SNES, Famicom Disk System. **Download:** https://www.mesen.ca

`eras.yaml` routes both `nes` and `snes` to Mesen, and `mesen.toml` covers `.nes`, `.chd`,
`.sfc`, `.smc`, `.fig`, `.swc`, and `.zip`.

**Portable mode depends on an interactive first-run choice.** Mesen asks where to store
data on first run (dialog added in 0.9.2); selecting the application directory enables
portable mode. Peach 1UP cannot set this, so portability cannot be assumed.

`FdsBios.bin` (SHA1 `e4e41472c454f928e53eb10e0509bf7d1146ecc1`) is optional and goes in
`emulators/mesen/data/`. It is only needed for Famicom Disk System titles. Mesen 2 also
adds optional SNES coprocessor ROMs (DSP-1, ST-010) for wider compatibility.

**Multi-disc:** not applicable. FDS multi-disk titles are single self-contained files and
side switching happens inside Mesen.

## Project64

**Eras:** N64. **Download:** https://www.pj64-emu.com

Portable by default whenever its install directory is writable; all config lives in
`AppPath\Config\`. No BIOS required.

**Not auto-installable.** The project publishes git tags but no GitHub release assets, so
there is nothing for the installer to match. The user downloads the Windows build from
pj64-emu.com and extracts it into `emulators/project64/`. This is permanent, not a deferred
decision.

**AppContainer permanently excluded** (`container_permanently_excluded = true`). Project64
crashes on launch under AppContainer (`Main.cpp:99`, `exit_code=1`), reproduced with memory
and CPU limits raised. Root cause unknown. Job Object caps remain the only active isolation
layer, and both are enforced.

**Multi-disc:** not applicable for cartridges. 64DD disk titles, rare here, swap manually
inside Project64's own menu.

## Flycast

**Eras:** Dreamcast. **Download:** https://github.com/flyinghead/flycast

Place `emu.cfg` next to the binary and Flycast uses that directory as its data root.

| File | Purpose |
|---|---|
| `dc_boot.bin` | Dreamcast BIOS ROM, required for boot |
| `dc_flash.bin` | Flash ROM, required for region and date settings |

Both go in `emulators/flycast/data/` and **must be from the same hardware revision**.
Mismatched pairs cause region or boot failures.

Flycast has no `saves/` directory: save states, VMU images, and `dc_nvmem.bin` all live
flat in `data/`, which the `install_dir` broker grant already covers. The descriptor
deliberately has no `saves_dir` entry, because it pointed at a directory the archive never
creates and aborted the launch at the DACL grant stage until someone made it by hand.

**AppContainer is enabled.** The descriptor's own `known_limitations` entry still says
otherwise; that text is stale and the flag is authoritative.

Flycast does not support DX9 out of the box, so it will not run on Windows 7 or earlier.
Rebuilding from `emulators/flycast/` with the DX9 SDK installed fixes that. The release
build uses:

```bash
cmake -S . -B build -A x64 -DUSE_DX9=OFF -DUSE_VULKAN=ON -DUSE_DX11=ON -DUSE_OPENGL=ON
```

Dependencies are in `emulators/flycast/dependencies`.

## Legal

The root [`LICENSE`](../LICENSE) is GPL-2.0-or-later.

**Peach 1UP does not redistribute emulator binaries.** Every emulator is fetched from its
own upstream release at the user's request and installed into `emulators/<slug>/`, or
(Project64 only) downloaded manually. What ships in the repository and in a release build
is the license and attribution set: each emulator's license file plus, for the GPL
emulators, a `SOURCE_OFFER.txt` pointing at the corresponding source.

This also settles DuckStation. It is CC BY-NC-ND 4.0 (non-GPL, non-commercial only), and
fetching it unmodified from the project's own GitHub release avoids redistributing it at
all. Every other emulator is GPL-2.0, GPL-3.0, or BSD-3-Clause.

`Install Type` is the `install_type` field in `config/emulators/<slug>.toml` and is the
source of truth for how a binary arrives.

| Emulator | License | License file | `SOURCE_OFFER.txt` | Install type | In `NOTICE` |
|---|---|---|---|---|---|
| 86Box | GPL-2.0 | `COPYING` | Yes | `github_release` | Yes |
| DOSBox-X | GPL-2.0 | `COPYING` | Yes | `github_release` | Yes |
| DuckStation | CC BY-NC-ND 4.0 | `LICENSE.txt` | Not required | `github_release` | **No** |
| Flycast | GPL-2.0 | `LICENSE` | Yes | `github_release` | Yes |
| Mesen | GPL-3.0 | `LICENSE` | Yes | `github_release` | Yes |
| PCSX2 | GPL-3.0 | `COPYING.GPLv3` | Yes | `github_release` | Yes |
| Project64 | GPL-2.0 | `license.md` | Yes | `zip` (manual) | Yes |
| RPCS3 | GPL-2.0 | `LICENSE.txt` | **No** | `github_release` | Yes |
| Xenia | BSD-3-Clause | `LICENSE` | Not required | `github_release` | Yes |
| xemu | GPL-2.0 | `LICENSE.txt` | Yes | `github_release` | Yes |

Two gaps remain in [`NOTICE`](../NOTICE):

- **DuckStation has no `NOTICE` entry.** It is installed by the app and should be listed
  alongside the rest.
- **RPCS3 has no `SOURCE_OFFER.txt`.** Its binary comes from `RPCS3/rpcs3-binaries-win`
  (which is what `source_url` points at, because the installer derives the release repo
  from that field), and the corresponding source is the public `RPCS3/rpcs3` repository.
  A `SOURCE_OFFER.txt` naming that repository would match the other GPL emulators.

Xenia needs no source offer: BSD-3-Clause carries no such obligation.
