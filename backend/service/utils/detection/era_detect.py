"""
Era detection for Peach 1UP — signal-based, no network calls, no external DAT files.
Public function: detect_era(path) -> (slug, reason)
"""

import struct
from pathlib import Path

from backend.service.utils.detection.magic_detect import detect_from_magic

_DOS_PUBLISHERS = frozenset({
    "GT INTERACTIVE", "ID SOFTWARE", "APOGEE", "3D REALMS", "SIERRA ON-LINE",
    "SIERRA", "ACTIVISION", "MICROPROSE", "LUCASARTS", "INTERPLAY", "BRODERBUND",
})


def detect_era(path: Path) -> tuple[str | None, str]:
    """
    Detect gaming era from a media file or directory.

    Returns (era_slug, reason) where reason is a short human-readable string
    explaining which signal matched. Returns (None, "no signal found") when no
    confident match is found. Never raises.
    """
    try:
        if not path.exists():
            return None, "path does not exist"

        if path.is_file():
            suffix = path.suffix.lower()

            if suffix == ".nds":
                return None, "NDS format is not supported by Peach 1UP"
            if suffix == ".xiso":
                return "xbox", "file extension .xiso indicates Original Xbox disc image"
            if suffix in {".z64", ".n64", ".v64"}:
                return "n64", "file extension indicates Nintendo 64 ROM"
            if suffix in {".sfc", ".smc"}:
                return "snes", "file extension indicates SNES ROM"
            if suffix == ".nes":
                return "nes", "file extension indicates NES ROM"
            if suffix in {".gdi", ".cdi"}:
                era, reason = detect_from_magic(path, suffix[1:])
                if era is not None:
                    return era, reason
                return "dreamcast", "file extension suggests Dreamcast disc image"

            if suffix == ".iso":
                era, reason = detect_from_magic(path, "iso")
                if era is not None:
                    return era, reason
                result = _detect_from_pvd(path)
                if result[0] is not None:
                    return result
                return _iso_size_fallback(path)

            if suffix == ".bin":
                era, reason = detect_from_magic(path, "bin")
                if era is not None:
                    return era, reason
                result = _detect_from_pvd(path)
                if result[0] is not None:
                    return result

            if suffix == ".cue":
                bin_path = _cue_bin_path(path)
                if bin_path is None:
                    candidate = path.with_suffix(".bin")
                    if candidate.exists():
                        bin_path = candidate
                if bin_path is not None:
                    era, reason = detect_from_magic(bin_path, "bin")
                    if era is not None:
                        return era, reason
                    result = _detect_from_pvd(bin_path)
                    if result[0] is not None:
                        return result
                    return None, "no signal found"
                return None, "no signal found"

            if suffix == ".img":
                try:
                    size = path.stat().st_size
                    if size < 800 * 1024 * 1024:
                        return "dos", "file extension .img under 800 MB suggests DOS-era image (low confidence)"
                except OSError:
                    pass

            if suffix == ".exe":
                return _detect_from_exe(path)

        elif path.is_dir():
            result = _detect_from_autorun(path)
            if result[0] is not None:
                return result

            result = _detect_from_directory(path)
            if result[0] is not None:
                return result

        return None, "no signal found"

    except Exception as exc:
        return None, f"detection error: {exc}"


# ── Step a: ISO 9660 Primary Volume Descriptor ──────────────────────────────

def _detect_from_pvd(iso_path: Path) -> tuple[str | None, str]:
    try:
        with iso_path.open("rb") as fh:
            fh.seek(32768)  # sector 16, 2048 bytes per sector
            pvd = fh.read(2048)

        if len(pvd) < 574 or pvd[0] != 1:
            return None, "not a valid ISO 9660 PVD"

        # Strip null bytes before decoding — ISO 9660 fields are null-padded to fixed width
        def _field(data: bytes) -> str:
            return data.replace(b'\x00', b'').decode("ascii", errors="replace").strip().upper()

        sys_id = _field(pvd[8:40])
        vol_id = _field(pvd[40:72])
        publisher = _field(pvd[318:446])
        preparer = _field(pvd[446:574])

        if any(k in vol_id for k in ("WINDOWS XP", "WINXP", "WXPEVOL", "XP_")):
            return "winxp", f"ISO volume label contains '{vol_id}'"

        if any(k in vol_id for k in ("WIN98", "WINDOWS 98", "W98", "MEMPHIS")):
            return "win98", f"ISO volume label contains '{vol_id}'"

        if any(k in vol_id for k in ("WIN95", "WINDOWS 95", "CHICAGO")):
            return "win95", f"ISO volume label contains '{vol_id}'"

        if any(k in vol_id for k in ("WIN31", "WINDOWS 3", "WFW")):
            return "win31", f"ISO volume label contains '{vol_id}'"

        if any(k in vol_id for k in ("MSDOS", "MS-DOS", "PCDOS", "FREEDOS", "CDROM", "DOS")):
            return "dos", f"ISO volume label contains '{vol_id}'"

        # Match known DOS publisher/preparer names (catches game-specific volume labels)
        for meta, label in ((publisher, "publisher"), (preparer, "preparer")):
            if any(p in meta for p in _DOS_PUBLISHERS):
                matched = next(p for p in _DOS_PUBLISHERS if p in meta)
                return "dos", f"ISO {label} '{meta[:40]}' matches known DOS publisher '{matched}'"

        ps_prefixes = ("SLUS", "SCES", "SCUS", "SLPS", "SCPS", "SLES", "SLEJ")
        vol_starts_ps = any(vol_id.startswith(p) for p in ps_prefixes)
        publisher_sony = "SONY" in publisher

        if vol_starts_ps or (sys_id == "CD-ROM" and publisher_sony):
            try:
                size_bytes = iso_path.stat().st_size
            except OSError:
                size_bytes = 0
            if vol_starts_ps and size_bytes > 4_700_000_000:
                return "ps2", f"ISO volume label '{vol_id}' matches PS2 pattern (DVD size)"
            return "ps1", f"ISO volume label '{vol_id}', publisher '{publisher[:30]}' match PS1"

        xbe = _detect_from_xbe_scan(iso_path)
        if xbe[0] is not None:
            return xbe

        return None, "ISO 9660 PVD present but no era signal matched"

    except Exception as exc:
        return None, f"ISO PVD read error: {exc}"


def _detect_from_xbe_scan(iso_path: Path) -> tuple[str | None, str]:
    try:
        with iso_path.open("rb") as fh:
            fh.seek(32768)
            pvd = fh.read(2048)
        if len(pvd) < 190 or pvd[0] != 1:
            return None, ""
        root_lba = struct.unpack_from("<I", pvd, 158)[0]
        root_size = struct.unpack_from("<I", pvd, 166)[0]
        if root_lba == 0 or root_size == 0 or root_size > 65536:
            return None, ""
        with iso_path.open("rb") as fh:
            fh.seek(root_lba * 2048)
            dir_data = fh.read(root_size)
        i = 0
        while i < len(dir_data):
            rec_len = dir_data[i]
            if rec_len == 0:
                i = (i | 2047) + 1
                continue
            if i + 33 > len(dir_data):
                break
            name_len = dir_data[i + 32]
            if i + 33 + name_len > len(dir_data):
                break
            raw_name = dir_data[i + 33: i + 33 + name_len].decode("ascii", errors="replace")
            name = raw_name.split(";")[0].upper()
            if name.endswith(".XBE"):
                return "xbox", "ISO filesystem contains .xbe — Original Xbox executable"
            i += rec_len
        return None, ""
    except Exception:
        return None, ""


def _iso_size_fallback(path: Path) -> tuple[str | None, str]:
    try:
        size = path.stat().st_size
    except OSError:
        return None, "no signal found"
    if size > 4 * 1024 ** 3:
        return None, "ISO exceeds 4 GB but no PVD signal — could be PS2 or Xbox OG, please select era manually"
    if size < 800 * 1024 * 1024:
        return None, "ISO under 800 MB but no PVD signal — era ambiguous, please select era manually"
    return None, "no signal found"


def _cue_bin_path(cue_path: Path) -> Path | None:
    try:
        for line in cue_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.upper().startswith("FILE "):
                parts = line.split('"')
                if len(parts) >= 2:
                    candidate = cue_path.parent / parts[1]
                    if candidate.exists():
                        return candidate
        return None
    except Exception:
        return None


# ── Step 3: Loose .exe detection ───────────────────────────────────────────

def _detect_from_exe(exe_path: Path) -> tuple[str | None, str]:
    try:
        with exe_path.open("rb") as fh:
            header = fh.read(4096)

        if len(header) < 2 or header[:2] != b"MZ":
            return "dos", "no MZ header — likely DOS COM-style executable"

        if len(header) < 0x40:
            return "dos", "MZ header present, no PE signature — DOS executable"

        pe_offset = struct.unpack_from("<I", header, 0x3C)[0]

        try:
            file_size = exe_path.stat().st_size
        except OSError:
            file_size = len(header)

        if pe_offset >= file_size or pe_offset + 96 > len(header):
            return "dos", "MZ header present, no PE signature — DOS executable"

        if header[pe_offset:pe_offset + 4] != b"PE\x00\x00":
            return "dos", "MZ header present, no PE signature — DOS executable"

        # Optional header starts at pe_offset + 24; MajorOperatingSystemVersion at offset 40
        major_os = struct.unpack_from("<H", header, pe_offset + 64)[0]

        if major_os >= 5:
            return "winxp", f"PE MajorOSVersion={major_os} — Windows XP era executable"
        if major_os == 4:
            return "win98", f"PE MajorOSVersion={major_os} — Windows 9x era executable"
        if major_os <= 3:
            return "win31", f"PE MajorOSVersion={major_os} — Windows 3.x era executable"

        return None, f"PE MajorOSVersion={major_os} not mapped to a known era"

    except Exception as exc:
        return None, f"detection error reading PE header: {exc}"


# ── Step b: Autorun.inf → PE header ────────────────────────────────────────

def _detect_from_autorun(root: Path) -> tuple[str | None, str]:
    try:
        autorun = None
        for name in ("AUTORUN.INF", "Autorun.inf", "autorun.inf"):
            candidate = root / name
            if candidate.is_file():
                autorun = candidate
                break

        if autorun is None:
            return None, "no AUTORUN.INF found"

        exe_rel = _parse_autorun_exe(autorun)
        if exe_rel is None:
            return None, "AUTORUN.INF has no OPEN/RUN entry pointing to an .exe"

        exe_path = root / exe_rel.replace("\\", "/")
        if not exe_path.is_file():
            return None, "AUTORUN.INF exe not found on disk"

        return _detect_from_pe(exe_path)

    except Exception as exc:
        return None, f"autorun detection error: {exc}"


def _parse_autorun_exe(autorun: Path) -> str | None:
    try:
        for line in autorun.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.upper().startswith(("OPEN=", "RUN=")):
                value = stripped.split("=", 1)[1].strip().strip('"')
                if value.lower().endswith(".exe"):
                    return value
        return None
    except Exception:
        return None


def _detect_from_pe(exe_path: Path) -> tuple[str | None, str]:
    try:
        with exe_path.open("rb") as fh:
            header = fh.read(4096)

        if len(header) < 2 or header[:2] != b"MZ":
            return None, "AUTORUN.INF points to a non-MZ file"

        if len(header) < 0x40:
            return "dos", "AUTORUN.INF points to MZ-only (DOS) executable"

        pe_offset = struct.unpack_from("<I", header, 0x3C)[0]

        if pe_offset + 96 > len(header):
            return None, "PE header extends beyond read buffer"

        sig = header[pe_offset:pe_offset + 4]
        if sig != b"PE\x00\x00":
            return "dos", "AUTORUN.INF exe has MZ header but no PE signature — likely DOS"

        # Optional header starts at pe_offset + 24
        # MajorOperatingSystemVersion at optional header offset 40
        # Subsystem at optional header offset 68
        subsystem = struct.unpack_from("<H", header, pe_offset + 92)[0]
        major_os = struct.unpack_from("<H", header, pe_offset + 64)[0]

        if subsystem not in (2, 3):
            return None, f"PE subsystem {subsystem} is not a standard Windows GUI/console app"

        if major_os >= 5:
            return "winxp", f"PE MajorOperatingSystemVersion={major_os} (Windows NT 5+)"
        if major_os == 4:
            return "win98", f"PE MajorOperatingSystemVersion={major_os} (Windows 9x era)"
        if major_os == 3:
            return "win31", f"PE MajorOperatingSystemVersion={major_os} (Windows 3.x era)"

        return None, f"PE MajorOperatingSystemVersion={major_os} not mapped to a known era"

    except Exception as exc:
        return None, f"PE parse error: {exc}"


# ── Step c: Directory structure heuristics ──────────────────────────────────

_WINDOWS_MARKERS = frozenset({"WINDOWS", "WIN", "SYSTEM", "SYSTEM32", "PROGRAM FILES", "PROGRA~1"})
_DOS_TOOLS = frozenset({"DEICE.EXE", "PKUNZIP.EXE", "PKUNZIP.COM", "LZMA.EXE"})


def _detect_from_directory(root: Path) -> tuple[str | None, str]:
    try:
        entries = {e.name.upper() for e in root.iterdir()}
    except OSError:
        return None, "cannot list directory"

    if "XPSP" in entries or "I386" in entries:
        return "winxp", "directory contains Windows XP installer structure (XPSP or I386)"

    if "WIN98" in entries or ("AUTOEXEC.BAT" in entries and "SYSTEM.DAT" in entries):
        return "win98", "directory contains Win98 marker files"

    if "WIN95" in entries or ("SETUP.EXE" in entries and "WIN.COM" in entries):
        return "win95", "directory contains Win95 marker files"

    if "WIN.INI" in entries and "SYSTEM.INI" in entries:
        return "win31", "directory contains WIN.INI and SYSTEM.INI"

    if "SYSTEM.CNF" in entries:
        try:
            size_bytes = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
        except OSError:
            size_bytes = 0
        if size_bytes > 4_700_000_000:
            return "ps2", "directory contains SYSTEM.CNF and total size suggests DVD (PS2)"
        return "ps1", "directory contains SYSTEM.CNF (PlayStation boot descriptor)"

    if "INSTALL.BAT" in entries or "INSTALL.COM" in entries:
        return "dos", "directory contains INSTALL.BAT or INSTALL.COM at root"

    depth2_names: set[str] = set(entries)
    try:
        for entry in root.iterdir():
            if entry.is_dir():
                try:
                    for sub in entry.iterdir():
                        depth2_names.add(sub.name.upper())
                except OSError:
                    pass
    except OSError:
        pass

    if _DOS_TOOLS.intersection(depth2_names):
        matched = next(iter(_DOS_TOOLS.intersection(depth2_names)))
        return "dos", f"directory contains DOS decompression tool {matched}"

    if any(n.endswith(".WAD") for n in depth2_names):
        return "dos", "directory contains .WAD file (DOS game data)"

    root_exts_all = {Path(e).suffix.lower() for e in entries}
    if root_exts_all.intersection({".1", ".2", ".3"}) and ".dat" in root_exts_all:
        return "dos", "directory contains split archive files (.1/.2/.3) with .DAT — DOS installer"

    if any(e.endswith(".BAT") for e in entries) and not entries.intersection(_WINDOWS_MARKERS):
        return "dos", "directory contains .BAT file at root with no Windows indicators"

    root_exts = {Path(e).suffix.lower() for e in entries if "." in e}
    dos_only = root_exts.issubset({".exe", ".com", ".bat", ".cfg", ".txt", ".ini", ""})
    if root_exts and dos_only and not entries.intersection(_WINDOWS_MARKERS):
        return "dos", "directory contains only DOS-era executables with no Windows folders"

    return None, "no directory structure signal matched"
