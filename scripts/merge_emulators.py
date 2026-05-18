#!/usr/bin/env python3
"""
Reads all .toml files from config/emulators/ and merges them into
config/emulators.toml with a top-level [[emulators]] array.
Exits with code 1 if any file fails to parse.
"""
import sys
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _ROOT / "config" / "emulators"
_OUT_PATH = _ROOT / "config" / "emulators.toml"


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return _toml_str(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(v)
    raise TypeError(f"Cannot serialize {type(v).__name__!r} as TOML scalar")


def _toml_array(items: list) -> str:
    if not items:
        return "[]"
    return "[" + ", ".join(_toml_scalar(x) for x in items) + "]"


def _render_flat(data: dict) -> list[str]:
    lines = []
    for k, v in data.items():
        if isinstance(v, list):
            if v and isinstance(v[0], dict):
                continue  # array-of-tables rendered separately
            lines.append(f"{k} = {_toml_array(v)}")
        elif isinstance(v, dict):
            continue  # nested dicts not expected in this schema
        else:
            lines.append(f"{k} = {_toml_scalar(v)}")
    return lines


def _render_emulator(data: dict) -> str:
    deps = data.pop("dependencies", [])
    grants = data.pop("filesystem_grants", [])
    parts = ["[[emulators]]"]
    parts.extend(_render_flat(data))
    for dep in deps:
        parts.append("")
        parts.append("[[emulators.dependencies]]")
        parts.extend(_render_flat(dep))
    for grant in grants:
        parts.append("")
        parts.append("[[emulators.filesystem_grants]]")
        parts.extend(_render_flat(grant))
    return "\n".join(parts)


def main() -> None:
    if not _SRC_DIR.is_dir():
        print(f"ERROR: source directory not found: {_SRC_DIR}", file=sys.stderr)
        sys.exit(1)

    toml_files = sorted(_SRC_DIR.glob("*.toml"))
    if not toml_files:
        print(f"ERROR: no .toml files in {_SRC_DIR}", file=sys.stderr)
        sys.exit(1)

    sections: list[str] = []
    for path in toml_files:
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            print(f"ERROR: {path.name}: {exc}", file=sys.stderr)
            sys.exit(1)
        sections.append(_render_emulator(data))
        print(f"  merged {path.name}")

    _OUT_PATH.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    print(f"written {_OUT_PATH}")


if __name__ == "__main__":
    main()
