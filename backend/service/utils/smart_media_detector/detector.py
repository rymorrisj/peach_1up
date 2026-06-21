import struct
from pathlib import Path

from .hashing import hash_lookup as _hash_lookup
from .magic.magic_detect import detect_from_magic
from .result import ScanResult
from .validators import bin_validator
from .validators import chd_validator

_INDEX_PATH = Path(__file__).parent / "hashing" / "hash_index.json"

_DOS_PUBLISHERS = frozenset({
    "GT INTERACTIVE", "ID SOFTWARE", "APOGEE", "3D REALMS", "SIERRA ON-LINE",
    "SIERRA", "ACTIVISION", "MICROPROSE", "LUCASARTS", "INTERPLAY", "BRODERBUND",
})
_WINDOWS_MARKERS = frozenset({"WINDOWS", "WIN", "SYSTEM", "SYSTEM32", "PROGRAM FILES", "PROGRA~1"})
_DOS_TOOLS = frozenset({"DEICE.EXE", "PKUNZIP.EXE", "PKUNZIP.COM", "LZMA.EXE"})


# ── requires_install heuristic ───────────────────────────────────────────────
# Heuristic — may need tuning post-beta. Covers the three cases the old
# detect_media_type-based logic handled plus installer-only DOS directories.

def _compute_requires_install(path: Path, era: str | None) -> bool:
    if path.is_file():
        suffix = path.suffix.lower()
        if suffix in {".iso", ".cue"}:
            return True
        if suffix == ".img":
            try:
                return path.stat().st_size < 2 * 1024 * 1024
            except OSError:
                return False
        return False
    if path.is_dir() and era in {"dos", "win31", "win95", "win98", "winxp"}:
        from .utils.blocklist import is_blocked
        try:
            exes = [
                e for e in path.iterdir()
                if e.is_file() and e.suffix.lower() in {".exe", ".com", ".bat"}
            ]
            if exes and all(is_blocked(e.stem) for e in exes):
                return True
        except OSError:
            pass
    return False


# ── Public entry point ────────────────────────────────────────────────────────

def detect(path: Path) -> ScanResult:
    try:
        return _detect(path)
    except Exception as exc:
        return ScanResult(
            title=None,
            platform=None,
            era=None,
            confidence=0.0,
            reason="unexpected detection error",
            warnings=[str(exc)],
        )


def _detect(path: Path) -> ScanResult:
    if not path.exists():
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason="path does not exist",
        )

    # Tier 1: hash lookup — highest confidence, return immediately on match
    try:
        result = _hash_lookup.lookup(path, _INDEX_PATH)
        if result is not None:
            result.requires_manual_boot = _requires_manual_boot(
                result.era, path, result.confidence, result.reason
            )
            result.requires_install = _compute_requires_install(path, result.era)
            return result
    except Exception:
        pass  # empty or missing index — continue to signal detection

    if path.is_file():
        result = _detect_file(path)
    elif path.is_dir():
        result = _detect_directory(path)
    else:
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason="path is neither a file nor a directory",
        )

    result.requires_manual_boot = _requires_manual_boot(
        result.era, path, result.confidence, result.reason
    )
    result.requires_install = _compute_requires_install(path, result.era)
    return result


# ── File dispatch ─────────────────────────────────────────────────────────────

def _detect_file(path: Path) -> ScanResult:
    suffix = path.suffix.lower()

    if suffix == ".nds":
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason="NDS format is not supported",
            warnings=["NDS format is not supported by Peach 1UP"],
        )

    if suffix == ".xiso":
        return ScanResult(
            title=None, platform=None, era="xbox", confidence=0.7,
            reason="file extension .xiso indicates Original Xbox disc image",
        )

    if suffix in {".z64", ".n64", ".v64"}:
        return ScanResult(
            title=None, platform=None, era="n64", confidence=0.7,
            reason=f"file extension {suffix} indicates Nintendo 64 ROM",
        )

    if suffix in {".sfc", ".smc", ".fig", ".swc"}:
        return ScanResult(
            title=None, platform=None, era="snes", confidence=0.7,
            reason=f"file extension {suffix} indicates SNES ROM",
        )

    if suffix == ".nes":
        return ScanResult(
            title=None, platform=None, era="nes", confidence=0.7,
            reason="file extension .nes indicates NES ROM",
        )

    if suffix in {".gdi", ".cdi"}:
        era, reason = detect_from_magic(path, suffix[1:])
        if era is not None:
            return ScanResult(title=None, platform=None, era=era, confidence=0.9, reason=reason)
        return ScanResult(
            title=None, platform=None, era="dreamcast", confidence=0.5,
            reason=f"file extension {suffix} suggests Dreamcast disc image",
            warnings=["no magic byte match; era inferred from extension only"],
        )

    if suffix == ".iso":
        return _detect_iso(path)

    if suffix == ".bin":
        era, reason = detect_from_magic(path, "bin")
        if era is not None:
            return ScanResult(title=None, platform=None, era=era, confidence=0.9, reason=reason)
        pvd = _detect_from_pvd(path)
        if pvd.era is not None:
            return pvd
        return bin_validator.resolve_bin_cue(path)

    if suffix == ".cue":
        return _detect_cue(path)

    if suffix == ".chd":
        return _detect_chd(path)

    if suffix == ".img":
        try:
            if path.stat().st_size < 800 * 1024 * 1024:
                return ScanResult(
                    title=None, platform=None, era="dos", confidence=0.35,
                    reason="file extension .img under 800 MB suggests DOS-era image",
                    warnings=["low confidence: era inferred from extension and size only"],
                )
        except OSError:
            pass
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason="no signal found",
        )

    if suffix == ".exe":
        return _detect_exe(path)

    return ScanResult(
        title=None, platform=None, era=None, confidence=0.0,
        reason="no signal found",
    )


# ── ISO / CHD / CUE handlers ─────────────────────────────────────────────────

def _detect_iso(path: Path) -> ScanResult:
    era, reason = detect_from_magic(path, "iso")
    if era is not None:
        return ScanResult(title=None, platform=None, era=era, confidence=0.9, reason=reason)

    pvd = _detect_from_pvd(path)
    if pvd.era is not None:
        return pvd

    return _iso_size_fallback(path)


def _detect_cue(path: Path) -> ScanResult:
    bin_path = _cue_bin_path(path)
    if bin_path is None:
        candidate = path.with_suffix(".bin")
        if candidate.exists():
            bin_path = candidate
    if bin_path is None:
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason="no .bin file found for .cue sheet",
            warnings=[f"could not locate the .bin file referenced by {path.name}"],
        )
    era, reason = detect_from_magic(bin_path, "bin")
    if era is not None:
        return ScanResult(title=None, platform=None, era=era, confidence=0.9, reason=reason)
    pvd = _detect_from_pvd(bin_path)
    if pvd.era is not None:
        return pvd
    return bin_validator.resolve_bin_cue(bin_path)


def _detect_chd(path: Path) -> ScanResult:
    return chd_validator.detect(path)


# ── ISO 9660 PVD ─────────────────────────────────────────────────────────────

def _detect_from_pvd(iso_path: Path) -> ScanResult:
    _null = ScanResult(title=None, platform=None, era=None, confidence=0.0, reason="")
    try:
        with iso_path.open("rb") as fh:
            fh.seek(32768)  # sector 16 at 2048 bytes/sector
            pvd = fh.read(2048)

        if len(pvd) < 574 or pvd[0] != 1:
            return _null

        def _field(data: bytes) -> str:
            return data.replace(b"\x00", b"").decode("ascii", errors="replace").strip().upper()

        sys_id = _field(pvd[8:40])
        vol_id = _field(pvd[40:72])
        publisher = _field(pvd[318:446])
        preparer = _field(pvd[446:574])

        for kw, era in (
            (("WINDOWS XP", "WINXP", "WXPEVOL", "XP_"), "winxp"),
            (("WIN98", "WINDOWS 98", "W98", "MEMPHIS"), "win98"),
            (("WIN95", "WINDOWS 95", "CHICAGO"), "win95"),
            (("WIN31", "WINDOWS 3", "WFW"), "win31"),
            (("MSDOS", "MS-DOS", "PCDOS", "FREEDOS", "CDROM", "DOS"), "dos"),
        ):
            if any(k in vol_id for k in kw):
                return ScanResult(
                    title=None, platform=None, era=era, confidence=0.75,
                    reason=f"ISO volume label contains '{vol_id}'",
                )

        for meta, label in ((publisher, "publisher"), (preparer, "preparer")):
            if any(p in meta for p in _DOS_PUBLISHERS):
                matched = next(p for p in _DOS_PUBLISHERS if p in meta)
                return ScanResult(
                    title=None, platform=None, era="dos", confidence=0.7,
                    reason=f"ISO {label} '{meta[:40]}' matches known DOS publisher '{matched}'",
                )

        ps_prefixes = ("SLUS", "SCES", "SCUS", "SLPS", "SCPS", "SLES", "SLEJ")
        vol_starts_ps = any(vol_id.startswith(p) for p in ps_prefixes)
        publisher_sony = "SONY" in publisher

        if vol_starts_ps or (sys_id == "CD-ROM" and publisher_sony):
            try:
                size_bytes = iso_path.stat().st_size
            except OSError:
                size_bytes = 0
            if vol_starts_ps and size_bytes > 4_700_000_000:
                return ScanResult(
                    title=None, platform=None, era="ps2", confidence=0.75,
                    reason=f"ISO volume label '{vol_id}' matches PS2 pattern (DVD size)",
                )
            return ScanResult(
                title=None, platform=None, era="ps1", confidence=0.75,
                reason=f"ISO volume label '{vol_id}', publisher '{publisher[:30]}' match PS1",
            )

        return _detect_from_xbe_scan(iso_path)

    except Exception as exc:
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason=f"ISO PVD read error: {exc}",
        )


def _detect_from_xbe_scan(iso_path: Path) -> ScanResult:
    _null = ScanResult(title=None, platform=None, era=None, confidence=0.0, reason="")
    try:
        with iso_path.open("rb") as fh:
            fh.seek(32768)
            pvd = fh.read(2048)
        if len(pvd) < 190 or pvd[0] != 1:
            return _null
        root_lba = struct.unpack_from("<I", pvd, 158)[0]
        root_size = struct.unpack_from("<I", pvd, 166)[0]
        if root_lba == 0 or root_size == 0 or root_size > 65536:
            return _null
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
            name = dir_data[i + 33: i + 33 + name_len].decode("ascii", errors="replace")
            name = name.split(";")[0].upper()
            if name.endswith(".XBE"):
                return ScanResult(
                    title=None, platform=None, era="xbox", confidence=0.8,
                    reason="ISO filesystem contains .xbe — Original Xbox executable",
                )
            i += rec_len
        return _null
    except Exception:
        return _null


def _iso_size_fallback(path: Path) -> ScanResult:
    try:
        size = path.stat().st_size
    except OSError:
        return ScanResult(title=None, platform=None, era=None, confidence=0.0, reason="no signal found")
    if size > 4 * 1024 ** 3:
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.2,
            reason="ISO exceeds 4 GB but no PVD signal",
            warnings=["could be PS2 or Xbox OG — please select era manually"],
        )
    if size < 800 * 1024 * 1024:
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.2,
            reason="ISO under 800 MB but no PVD signal",
            warnings=["era ambiguous — please select era manually"],
        )
    return ScanResult(title=None, platform=None, era=None, confidence=0.0, reason="no signal found")


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


# ── .exe / PE header ─────────────────────────────────────────────────────────

def _detect_exe(exe_path: Path) -> ScanResult:
    try:
        with exe_path.open("rb") as fh:
            header = fh.read(4096)

        if len(header) < 2 or header[:2] != b"MZ":
            return ScanResult(
                title=None, platform=None, era="dos", confidence=0.6,
                reason="no MZ header — likely DOS COM-style executable",
            )
        if len(header) < 0x40:
            return ScanResult(
                title=None, platform=None, era="dos", confidence=0.7,
                reason="MZ header present, no PE signature — DOS executable",
            )

        pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
        try:
            file_size = exe_path.stat().st_size
        except OSError:
            file_size = len(header)

        if pe_offset >= file_size or pe_offset + 96 > len(header):
            return ScanResult(
                title=None, platform=None, era="dos", confidence=0.7,
                reason="MZ header present, no PE signature — DOS executable",
            )
        if header[pe_offset: pe_offset + 4] != b"PE\x00\x00":
            return ScanResult(
                title=None, platform=None, era="dos", confidence=0.7,
                reason="MZ header present, no PE signature — DOS executable",
            )

        # Optional header offset 40 = MajorOperatingSystemVersion; pe_offset + 24 + 40 = pe_offset + 64
        major_os = struct.unpack_from("<H", header, pe_offset + 64)[0]
        if major_os >= 5:
            return ScanResult(
                title=None, platform=None, era="winxp", confidence=0.75,
                reason=f"PE MajorOSVersion={major_os} — Windows XP era executable",
            )
        if major_os == 4:
            return ScanResult(
                title=None, platform=None, era="win98", confidence=0.75,
                reason=f"PE MajorOSVersion={major_os} — Windows 9x era executable",
            )
        if major_os <= 3:
            return ScanResult(
                title=None, platform=None, era="win31", confidence=0.75,
                reason=f"PE MajorOSVersion={major_os} — Windows 3.x era executable",
            )
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason=f"PE MajorOSVersion={major_os} not mapped to a known era",
        )
    except Exception as exc:
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason=f"detection error reading PE header: {exc}",
        )


# ── Directory detection ───────────────────────────────────────────────────────

def _detect_directory(path: Path) -> ScanResult:
    result = _detect_from_autorun(path)
    if result.era is not None:
        return result
    return _detect_from_directory(path)


def _detect_from_autorun(root: Path) -> ScanResult:
    _null = ScanResult(title=None, platform=None, era=None, confidence=0.0, reason="")
    try:
        autorun = None
        for name in ("AUTORUN.INF", "Autorun.inf", "autorun.inf"):
            candidate = root / name
            if candidate.is_file():
                autorun = candidate
                break
        if autorun is None:
            return _null
        exe_rel = _parse_autorun_exe(autorun)
        if exe_rel is None:
            return _null
        exe_path = root / exe_rel.replace("\\", "/")
        if not exe_path.is_file():
            return _null
        return _detect_from_pe(exe_path)
    except Exception as exc:
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason=f"autorun detection error: {exc}",
        )


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


def _detect_from_pe(exe_path: Path) -> ScanResult:
    _null = ScanResult(title=None, platform=None, era=None, confidence=0.0, reason="")
    try:
        with exe_path.open("rb") as fh:
            header = fh.read(4096)

        if len(header) < 2 or header[:2] != b"MZ":
            return _null
        if len(header) < 0x40:
            return ScanResult(
                title=None, platform=None, era="dos", confidence=0.65,
                reason="AUTORUN.INF points to MZ-only (DOS) executable",
            )

        pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
        if pe_offset + 96 > len(header):
            return _null
        if header[pe_offset: pe_offset + 4] != b"PE\x00\x00":
            return ScanResult(
                title=None, platform=None, era="dos", confidence=0.65,
                reason="AUTORUN.INF exe has MZ header but no PE signature — likely DOS",
            )

        # Optional header offset 68 = Subsystem; offset 40 = MajorOperatingSystemVersion
        subsystem = struct.unpack_from("<H", header, pe_offset + 92)[0]
        major_os = struct.unpack_from("<H", header, pe_offset + 64)[0]

        if subsystem not in (2, 3):
            return _null

        if major_os >= 5:
            return ScanResult(
                title=None, platform=None, era="winxp", confidence=0.75,
                reason=f"PE MajorOperatingSystemVersion={major_os} (Windows NT 5+)",
            )
        if major_os == 4:
            return ScanResult(
                title=None, platform=None, era="win98", confidence=0.75,
                reason=f"PE MajorOperatingSystemVersion={major_os} (Windows 9x era)",
            )
        if major_os == 3:
            return ScanResult(
                title=None, platform=None, era="win31", confidence=0.75,
                reason=f"PE MajorOperatingSystemVersion={major_os} (Windows 3.x era)",
            )
        return _null
    except Exception as exc:
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason=f"PE parse error: {exc}",
        )


def _detect_from_directory(root: Path) -> ScanResult:
    try:
        entries = {e.name.upper() for e in root.iterdir()}
    except OSError:
        return ScanResult(
            title=None, platform=None, era=None, confidence=0.0,
            reason="cannot list directory",
        )

    if "XPSP" in entries or "I386" in entries:
        return ScanResult(
            title=None, platform=None, era="winxp", confidence=0.6,
            reason="directory contains Windows XP installer structure (XPSP or I386)",
        )
    if "WIN98" in entries or ("AUTOEXEC.BAT" in entries and "SYSTEM.DAT" in entries):
        return ScanResult(
            title=None, platform=None, era="win98", confidence=0.6,
            reason="directory contains Win98 marker files",
        )
    if "WIN95" in entries or ("SETUP.EXE" in entries and "WIN.COM" in entries):
        return ScanResult(
            title=None, platform=None, era="win95", confidence=0.6,
            reason="directory contains Win95 marker files",
        )
    if "WIN.INI" in entries and "SYSTEM.INI" in entries:
        return ScanResult(
            title=None, platform=None, era="win31", confidence=0.6,
            reason="directory contains WIN.INI and SYSTEM.INI",
        )
    if "SYSTEM.CNF" in entries:
        try:
            size_bytes = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
        except OSError:
            size_bytes = 0
        if size_bytes > 4_700_000_000:
            return ScanResult(
                title=None, platform=None, era="ps2", confidence=0.6,
                reason="directory contains SYSTEM.CNF and total size suggests DVD (PS2)",
            )
        return ScanResult(
            title=None, platform=None, era="ps1", confidence=0.6,
            reason="directory contains SYSTEM.CNF (PlayStation boot descriptor)",
        )
    if "INSTALL.BAT" in entries or "INSTALL.COM" in entries:
        return ScanResult(
            title=None, platform=None, era="dos", confidence=0.55,
            reason="directory contains INSTALL.BAT or INSTALL.COM at root",
        )

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
        return ScanResult(
            title=None, platform=None, era="dos", confidence=0.6,
            reason=f"directory contains DOS decompression tool {matched}",
        )
    if any(n.endswith(".WAD") for n in depth2_names):
        return ScanResult(
            title=None, platform=None, era="dos", confidence=0.55,
            reason="directory contains .WAD file (DOS game data)",
        )
    root_exts_all = {Path(e).suffix.lower() for e in entries}
    if root_exts_all.intersection({".1", ".2", ".3"}) and ".dat" in root_exts_all:
        return ScanResult(
            title=None, platform=None, era="dos", confidence=0.55,
            reason="directory contains split archive files (.1/.2/.3) with .DAT — DOS installer",
        )
    if any(e.endswith(".BAT") for e in entries) and not entries.intersection(_WINDOWS_MARKERS):
        return ScanResult(
            title=None, platform=None, era="dos", confidence=0.5,
            reason="directory contains .BAT file at root with no Windows indicators",
        )
    root_exts = {Path(e).suffix.lower() for e in entries if "." in e}
    dos_only = root_exts.issubset({".exe", ".com", ".bat", ".cfg", ".txt", ".ini", ""})
    if root_exts and dos_only and not entries.intersection(_WINDOWS_MARKERS):
        return ScanResult(
            title=None, platform=None, era="dos", confidence=0.5,
            reason="directory contains only DOS-era executables with no Windows folders",
        )

    return ScanResult(
        title=None, platform=None, era=None, confidence=0.0,
        reason="no signal found",
    )


# ── requires_manual_boot ─────────────────────────────────────────────────────

def _requires_manual_boot(
    era: str | None, path: Path, confidence: float, reason: str = ""
) -> bool:
    if confidence < 0.5:
        return True
    if era is None:
        return False
    suffix = path.suffix.lower() if path.is_file() else ""
    if era == "ps2" and suffix == ".img":
        return True
    # xbox + .iso: requires manual boot UNLESS it's confirmed xiso format
    if era == "xbox" and suffix == ".iso" and "xiso" not in reason.lower():
        return True
    return False
