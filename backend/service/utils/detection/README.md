# Peach 1UP — Era Detection

Self-contained detection pipeline that identifies gaming era from media
files and directories. No network calls, no external dependencies at
runtime. Designed to be extractable as a standalone library.

---

## Pipeline

Detection runs in tiers, fastest and most reliable first:

### Tier 1 — Magic Numbers (`magic_detect.py`)

Reads a small number of bytes at known offsets to identify platform from
binary signatures. Fast, offline, works on any file regardless of
extension or metadata. Signature definitions live in
`magic_signatures.toml` — community-editable, no code changes required
to add new signatures.

### Tier 2 — ISO 9660 PVD (`era_detect.py` → `_detect_from_pvd`)

Reads the Primary Volume Descriptor of ISO/BIN disc images. Matches
volume labels, publisher strings, and filesystem contents (e.g. presence
of `default.xbe` for Xbox, `SYSTEM.CNF` for PlayStation). Reliable for
well-mastered disc images but depends on metadata being present.

### Tier 3 — Directory Structure (`era_detect.py` → `_detect_from_directory`)

Heuristic scan of directory contents — marker files, executable types,
known tool names, archive structures. Lower confidence than Tiers 1–2.

### Tier 4 — Hash Lookup (planned, `hash_detect.py`)

Full file hash (MD5/CRC32) matched against Redump and TOSEC DAT files
for exact title identification. Provides game name, region, and revision
in addition to era. Not yet implemented at runtime — DAT parsing is
scaffolded in `smart_scan/`. Deferred because hashing large disc images
(4–6 GB) adds significant scan time and requires users to supply or
download DAT files. When implemented, this will run before all other
tiers and short-circuit on a confirmed match.

---

## Known Limitations

**Xbox ISOs ripped as ISO 9660**
Some Xbox disc images are ripped into standard ISO 9660 containers rather
than the native XDVDFS format. These will not match the XDVDFS magic
number. Detection falls back to scanning the ISO root directory for
`default.xbe`. If the rip does not contain an XBE at the root, era
detection will return no signal and the user must select the era manually.
This is a rip quality issue, not a Peach 1UP limitation.

**PS1 vs PS2 ambiguity on CD-based games**
Both PS1 and PS2 CD discs use the same Mode 2 sector sync pattern. The
distinction is resolved by reading `SYSTEM.CNF` inside the disc image and
checking for `BOOT` (PS1) vs `BOOT2` (PS2). DVD-based PS2 games do not
have the sync pattern and are identified by PVD signals only.

**Generic ISOs**
An ISO with no volume label, no publisher metadata, no XDVDFS magic, and
no XBE file cannot be automatically identified. The user must select the
era manually. Hash-based Redump lookup (Tier 4) will resolve most of
these cases when implemented.

**ZIP files**
ZIP archives cannot be identified by magic number without extraction.
Era detection always returns no signal for ZIP files. The user must
select the era manually after adding a ZIP to the library.

---

## Adding Signatures

To add a new magic number signature, append a `[[signatures]]` block to
`magic_signatures.toml` and restart the backend. No code changes needed.
See the existing entries and field documentation in that file for the
correct format.

To add a new filesystem or structural signal, add a detector function to
`era_detect.py` following the existing pattern and wire it into
`detect_era`.

Community contributions to both files are welcome via pull request.
