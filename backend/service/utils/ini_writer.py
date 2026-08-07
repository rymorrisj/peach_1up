"""INI file read-edit-write utilities for emulator configuration.

patch_ini , high-level: read existing file → apply edits dict → atomic write.
write_ini , low-level: atomic write of a pre-built RawConfigParser to a path.

Both preserve optionxform=str (case-sensitive keys) and read with utf-8-sig
encoding so a BOM written by other tools is silently consumed.
"""

import configparser
import os
from pathlib import Path


def patch_ini(
    path: Path,
    edits: dict[str, dict[str, str]],
    *,
    remove_sections: list[str] | None = None,
) -> None:
    """Read an INI file, apply edits, and write it back atomically.

    Creates the file if it does not exist. Sections listed in *remove_sections*
    are dropped before the edits are applied. Keys within each section in
    *edits* are always set (overwriting any existing value).

    Args:
        path:            Path to the target INI file.
        edits:           ``{section: {key: value}}`` mapping of changes to apply.
        remove_sections: Section names to delete before merging edits.

    Raises:
        OSError: If the atomic write or rename fails.
    """
    parser = configparser.RawConfigParser()
    parser.optionxform = str
    if path.exists():
        parser.read(str(path), encoding="utf-8-sig")
    for section in (remove_sections or []):
        if parser.has_section(section):
            parser.remove_section(section)
    for section, keys in edits.items():
        if not parser.has_section(section):
            parser.add_section(section)
        for key, value in keys.items():
            parser.set(section, key, value)
    write_ini(path, parser)


def set_ini_key(ini_path: Path, section: str, key: str, value: str) -> None:
    """Update a single key in an INI file, preserving all other content exactly.

    Hand-rolled, line-based, comment-preserving edit, distinct from
    :func:`patch_ini`, which rewrites the file via ``configparser`` and does
    not preserve comments.
    """
    if not ini_path.exists():
        ini_path.parent.mkdir(parents=True, exist_ok=True)
        ini_path.write_text(f"[{section}]\n{key} = {value}\n", encoding="utf-8")
        return
    lines = ini_path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_target = False
    section_found = False
    key_written = False
    insert_before: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped[1:-1] == section:
                in_target = True
                section_found = True
            elif in_target and not key_written:
                insert_before = i
                in_target = False
            else:
                in_target = False
        elif in_target and "=" in line:
            k = line.split("=", 1)[0].strip()
            if k == key:
                lines[i] = f"{key} = {value}\n"
                key_written = True
                in_target = False
    if not key_written:
        new_line = f"{key} = {value}\n"
        if insert_before is not None:
            lines.insert(insert_before, new_line)
        elif section_found:
            lines.append(new_line)
        else:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(f"\n[{section}]\n{new_line}")
    ini_path.write_text("".join(lines), encoding="utf-8")


def write_ini(path: Path, parser: configparser.RawConfigParser) -> None:
    """Write a RawConfigParser to *path* atomically via a .tmp sibling.

    The write goes to ``<path>.tmp`` first; on success it is renamed over
    *path* via :func:`os.replace`. If the write fails the temp file is
    cleaned up and the original is left untouched.

    Args:
        path:   Destination path.
        parser: Parser whose current state is written.

    Raises:
        OSError: If writing or renaming fails.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            parser.write(fh)
        os.replace(str(tmp), str(path))
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise
