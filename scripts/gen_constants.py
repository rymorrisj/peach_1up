"""Generate backend/constants_generated.py and frontend/src/generated/constants.ts
from config/constants.yaml and config/platforms.yaml. Also writes the repo-root VERSION file and syncs the
"version" field of frontend/package.json and docs/package.json to app_version.

Run from the project root:
    python scripts/gen_constants.py
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "constants.yaml"
PLATFORMS_CONFIG = ROOT / "config" / "platforms.yaml"
EMULATORS_DIR = ROOT / "config" / "emulators"
PY_OUT = ROOT / "backend" / "constants_generated.py"
TS_OUT = ROOT / "frontend" / "src" / "generated" / "constants.ts"
VERSION_OUT = ROOT / "VERSION"
FRONTEND_PKG = ROOT / "frontend" / "package.json"
DOCS_PKG = ROOT / "docs" / "package.json"

HEADER_PY = "# Auto-generated from config/constants.yaml and config/platforms.yaml, do not edit.\n"
HEADER_TS = "// Auto-generated from config/constants.yaml and config/platforms.yaml, do not edit.\n"


_SLUG_TO_ENUM: dict[str, str] = {
    "86box": "BOX86",
}


def _enum_name(slug: str) -> str:
    """Convert a slug like '86box' or 'win31' to a valid Python identifier."""
    if slug in _SLUG_TO_ENUM:
        return _SLUG_TO_ENUM[slug]
    s = re.sub(r"[^a-zA-Z0-9]", "_", slug).upper()
    if s[0].isdigit():
        s = "_" + s
    return s


def _ts_union_type(type_name: str, slugs: list[str]) -> str:
    """Emit a TS string-literal union type, e.g. export type Foo = 'a' | 'b';"""
    members = " | ".join(f"'{slug}'" for slug in slugs)
    return f"export type {type_name} = {members};\n"


def _py_literal_type(type_name: str, slugs: list[str]) -> str:
    """Emit a Python typing.Literal alias, e.g. Foo = Literal["a", "b"]"""
    members = ", ".join(f'"{slug}"' for slug in slugs)
    return f"{type_name} = Literal[{members}]\n"


def discover_catalog_slugs() -> list[str]:
    """Scan config/emulators/*.toml for launchable catalog slugs.

    The TOMLs are the source of truth for the emulator catalog domain, this
    is distinct from constants.yaml's backend_slugs (the dispatch domain).
    Entries with install_type == "rom_pack" are dependency-only assets
    (e.g. 86box-roms), never a launchable emulator_slug value, and are
    excluded.
    """
    slugs: list[str] = []
    for path in sorted(EMULATORS_DIR.glob("*.toml")):
        with path.open("rb") as fh:
            entry = tomllib.load(fh)
        if entry.get("install_type") == "rom_pack":
            continue
        slugs.append(entry["slug"])
    return slugs


def load_platforms(data: dict) -> dict[str, dict]:
    """Read config/platforms.yaml and validate it against constants.yaml.

    Every labelled platform except "unknown" needs a block with a valid kind
    and a known backend, and every block needs a label.
    """
    with PLATFORMS_CONFIG.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    blocks = {k: v for k, v in raw.items() if isinstance(v, dict)}
    labels: dict[str, str] = data["platforms"]
    kinds = set(data["item_types"])
    backends = set(data["backend_slugs"])
    expected = [p for p in labels if p != "unknown"]
    missing = sorted(set(expected) - set(blocks))
    extra = sorted(set(blocks) - set(expected))
    if missing or extra:
        raise RuntimeError(
            f"platforms.yaml and constants.yaml platforms disagree: missing={missing} extra={extra}"
        )
    for platform_id, block in blocks.items():
        if block.get("kind") not in kinds:
            raise RuntimeError(f"platforms.yaml: '{platform_id}' kind must be one of {sorted(kinds)}")
        if block.get("backend") not in backends:
            raise RuntimeError(f"platforms.yaml: '{platform_id}' backend must be one of {sorted(backends)}")
    return {p: blocks[p] for p in expected}


def generate_python(data: dict, catalog_slugs: list[str], platform_blocks: dict[str, dict]) -> str:
    app_version: str = data["app_version"]
    platforms: dict[str, str] = data["platforms"]
    backends: dict[str, str] = data["backend_slugs"]
    system_labels: dict[str, str] = data["backend_system_labels"]
    ratings: list[dict[str, str]] = data["content_ratings"]
    file_types: dict[str, str] = data["file_types"]
    hardware_profiles: dict[str, str] = data["hardware_profiles"]
    tag_colors: list[dict[str, str]] = data["tag_colors"]
    install_types: list[str] = data["install_types"]
    item_types: list[str] = data["item_types"]
    media_kinds: list[str] = data["media_kinds"]
    dgvoodoo2_platforms = [p for p, b in platform_blocks.items() if b.get("dgvoodoo2_supported")]

    lines: list[str] = [HEADER_PY, "from enum import Enum\n", "from typing import Literal\n\n\n"]

    # APP_VERSION, single source of truth, also mirrored to VERSION (repo root),
    # frontend/package.json, docs/package.json, and installer/peach1up.nsi (via build.bat).
    lines.append(f'APP_VERSION = "{app_version}"\n\n\n')

    # Platform enum
    lines.append("class Platform(Enum):\n")
    for slug in platforms:
        lines.append(f'    {_enum_name(slug)} = "{slug}"\n')
    lines.append("\n\n")

    # PlatformValue literal, boundary type (DB columns, API I/O); Platform enum
    # above is for internal named-member dispatch only, see platform_to_enum().
    lines.append(_py_literal_type("PlatformValue", list(platforms)))
    lines.append("\n")

    # BackendSlug enum
    lines.append("class BackendSlug(Enum):\n")
    for slug in backends:
        lines.append(f'    {_enum_name(slug)} = "{slug}"\n')
    lines.append("\n\n")

    # PLATFORM_LABELS
    lines.append("PLATFORM_LABELS: dict[str, str] = {\n")
    for slug, label in platforms.items():
        lines.append(f'    "{slug}": "{label}",\n')
    lines.append("}\n\n")

    # BACKEND_LABELS
    lines.append("BACKEND_LABELS: dict[str, str] = {\n")
    for slug, label in backends.items():
        lines.append(f'    "{slug}": "{label}",\n')
    lines.append("}\n\n")

    # BACKEND_SYSTEM_LABELS
    lines.append("BACKEND_SYSTEM_LABELS: dict[str, str] = {\n")
    for slug, label in system_labels.items():
        lines.append(f'    "{slug}": "{label}",\n')
    lines.append("}\n\n")

    # CONTENT_RATINGS
    lines.append("CONTENT_RATINGS: list[dict[str, str]] = [\n")
    for r in ratings:
        lines.append(
            f'    {{"value": "{r["value"]}", "label": "{r["label"]}", "scheme": "{r["scheme"]}"}},\n'
        )
    lines.append("]\n\n")

    # DGVOODOO2_SUPPORTED_PLATFORMS
    lines.append("DGVOODOO2_SUPPORTED_PLATFORMS: list[str] = [\n")
    for platform_id in dgvoodoo2_platforms:
        lines.append(f'    "{platform_id}",\n')
    lines.append("]\n\n")

    # FileType literal
    lines.append(_py_literal_type("FileType", list(file_types)))
    lines.append("\n")

    # EmulatorCatalogSlug literal (sourced from config/emulators/*.toml, not constants.yaml)
    lines.append(_py_literal_type("EmulatorCatalogSlug", catalog_slugs))
    lines.append("\n")

    # HardwareProfile literal + labels
    lines.append(_py_literal_type("HardwareProfile", list(hardware_profiles)))
    lines.append("\n")
    lines.append("HARDWARE_PROFILE_LABELS: dict[str, str] = {\n")
    for slug, label in hardware_profiles.items():
        lines.append(f'    "{slug}": "{label}",\n')
    lines.append("}\n\n")

    # TagColor literal + hex map
    lines.append(_py_literal_type("TagColor", [c["id"] for c in tag_colors]))
    lines.append("\n")
    lines.append("TAG_COLOR_HEX: dict[str, str] = {\n")
    for c in tag_colors:
        lines.append(f'    "{c["id"]}": "{c["hex"]}",\n')
    lines.append("}\n\n")

    # InstallType literal
    lines.append(_py_literal_type("InstallType", list(install_types)))
    lines.append("\n")

    # ItemType literal
    lines.append(_py_literal_type("ItemType", list(item_types)))
    lines.append("\n")

    # MediaKind literal
    lines.append(_py_literal_type("MediaKind", list(media_kinds)))
    lines.append("\n")

    # PLATFORM_BACKENDS, PLATFORM_KINDS, PC_PLATFORMS (from platforms.yaml)
    lines.append("PLATFORM_BACKENDS: dict[str, str] = {\n")
    for platform_id, block in platform_blocks.items():
        lines.append(f'    "{platform_id}": "{block["backend"]}",\n')
    lines.append("}\n\n")
    lines.append("PLATFORM_KINDS: dict[str, str] = {\n")
    for platform_id, block in platform_blocks.items():
        lines.append(f'    "{platform_id}": "{block["kind"]}",\n')
    lines.append("}\n\n")
    pc = ", ".join(f'"{p}"' for p, b in platform_blocks.items() if b["kind"] == "pc")
    lines.append(f"PC_PLATFORMS: frozenset[str] = frozenset({{{pc}}})\n")

    return "".join(lines)


def generate_typescript(data: dict, catalog_slugs: list[str], platform_blocks: dict[str, dict]) -> str:
    app_version: str = data["app_version"]
    platforms: dict[str, str] = data["platforms"]
    backends: dict[str, str] = data["backend_slugs"]
    system_labels: dict[str, str] = data["backend_system_labels"]
    ratings: list[dict[str, str]] = data["content_ratings"]
    file_types: dict[str, str] = data["file_types"]
    hardware_profiles: dict[str, str] = data["hardware_profiles"]
    tag_colors: list[dict[str, str]] = data["tag_colors"]
    install_types: list[str] = data["install_types"]
    item_types: list[str] = data["item_types"]
    media_kinds: list[str] = data["media_kinds"]
    dgvoodoo2_platforms = [p for p, b in platform_blocks.items() if b.get("dgvoodoo2_supported")]

    lines: list[str] = [HEADER_TS, "\n"]

    # APP_VERSION, single source of truth, also mirrored to VERSION (repo root),
    # frontend/package.json, docs/package.json, and installer/peach1up.nsi (via build.bat).
    lines.append(f'export const APP_VERSION = "{app_version}"\n\n')

    # Platform union
    lines.append(_ts_union_type("Platform", list(platforms)))
    lines.append("\n")

    # PLATFORM_LABELS
    lines.append("export const PLATFORM_LABELS: Record<string, string> = {\n")
    for slug, label in platforms.items():
        key = f'"{slug}"' if not slug.isidentifier() else slug
        lines.append(f'  {key}: "{label}",\n')
    lines.append("}\n\n")

    # BACKEND_LABELS
    lines.append("export const BACKEND_LABELS: Record<string, string> = {\n")
    for slug, label in backends.items():
        # '86box' is not a valid bare identifier, quote it
        key = f'"{slug}"' if not slug.isidentifier() else slug
        lines.append(f"  {key}: \"{label}\",\n")
    lines.append("}\n\n")

    # BACKEND_SYSTEM_LABELS
    lines.append("export const BACKEND_SYSTEM_LABELS: Record<string, string> = {\n")
    for slug, label in system_labels.items():
        key = f'"{slug}"' if not slug.isidentifier() else slug
        lines.append(f"  {key}: \"{label}\",\n")
    lines.append("}\n\n")

    # BACKEND_SLUGS
    slugs_ts = ", ".join(f'"{s}"' for s in backends)
    lines.append(f"export const BACKEND_SLUGS: string[] = [{slugs_ts}]\n\n")

    # BackendSlug union
    lines.append(_ts_union_type("BackendSlug", list(backends)))
    lines.append("\n")

    # RATING_OPTIONS, includes a leading empty option for form use
    lines.append(
        "export const RATING_OPTIONS: { value: string; label: string; scheme?: string }[] = [\n"
    )
    lines.append('  { value: \'\', label: \'— No rating —\' },\n')
    for r in ratings:
        label = r["label"].replace("'", "\\'")
        lines.append(
            f"  {{ value: '{r['value']}', label: '{label}', scheme: '{r['scheme']}' }},\n"
        )
    lines.append("]\n\n")

    # DGVOODOO2_SUPPORTED_PLATFORMS
    dgvoodoo2_ts = ", ".join(f'"{p}"' for p in dgvoodoo2_platforms)
    lines.append(f"export const DGVOODOO2_SUPPORTED_PLATFORMS: string[] = [{dgvoodoo2_ts}]\n\n")

    # FileType union
    lines.append(_ts_union_type("FileType", list(file_types)))
    lines.append("\n")

    # EmulatorCatalogSlug union (sourced from config/emulators/*.toml, not constants.yaml)
    lines.append(_ts_union_type("EmulatorCatalogSlug", catalog_slugs))
    lines.append("\n")

    # EMULATOR_CATALOG_SLUGS, runtime companion for <select> options
    catalog_slugs_ts = ", ".join(f'"{s}"' for s in catalog_slugs)
    lines.append(f"export const EMULATOR_CATALOG_SLUGS: string[] = [{catalog_slugs_ts}]\n\n")

    # HardwareProfile union + labels
    lines.append(_ts_union_type("HardwareProfile", list(hardware_profiles)))
    lines.append("\n")
    lines.append("export const HARDWARE_PROFILE_LABELS: Record<string, string> = {\n")
    for slug, label in hardware_profiles.items():
        key = f'"{slug}"' if not slug.isidentifier() else slug
        lines.append(f'  {key}: "{label}",\n')
    lines.append("}\n\n")

    # TagColor union + hex map
    lines.append(_ts_union_type("TagColor", [c["id"] for c in tag_colors]))
    lines.append("\n")
    lines.append("export const TAG_COLOR_HEX: Record<string, string> = {\n")
    for c in tag_colors:
        key = c["id"]
        lines.append(f'  {key}: "{c["hex"]}",\n')
    lines.append("}\n\n")

    # InstallType union
    lines.append(_ts_union_type("InstallType", list(install_types)))
    lines.append("\n")

    # ItemType union
    lines.append(_ts_union_type("ItemType", list(item_types)))
    lines.append("\n")

    # MediaKind union
    lines.append(_ts_union_type("MediaKind", list(media_kinds)))
    lines.append("\n")

    # PLATFORM_BACKENDS, PLATFORM_KINDS, PC_PLATFORMS (from platforms.yaml)
    lines.append("export const PLATFORM_BACKENDS: Record<string, string> = {\n")
    for platform_id, block in platform_blocks.items():
        key = f'"{platform_id}"' if not platform_id.isidentifier() else platform_id
        lines.append(f'  {key}: "{block["backend"]}",\n')
    lines.append("}\n\n")
    lines.append("export const PLATFORM_KINDS: Record<string, ItemType> = {\n")
    for platform_id, block in platform_blocks.items():
        key = f'"{platform_id}"' if not platform_id.isidentifier() else platform_id
        lines.append(f'  {key}: "{block["kind"]}",\n')
    lines.append("}\n\n")
    pc_ts = ", ".join(f'"{p}"' for p, b in platform_blocks.items() if b["kind"] == "pc")
    lines.append(f"export const PC_PLATFORMS: string[] = [{pc_ts}]\n")

    return "".join(lines)


def sync_package_json_version(path: Path, version: str) -> None:
    """Overwrite the top-level "version" field of a package.json in place.

    Uses a targeted regex substitution rather than json.load/dump so that
    dependency ordering, spacing, and every other field are left byte-for-byte
    untouched, only the version string changes.
    """
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(r'"version":\s*"[^"]*"', f'"version": "{version}"', text, count=1)
    if count == 0:
        raise RuntimeError(f'{path}: no "version" field found to sync')
    path.write_text(new_text, encoding="utf-8")


def main() -> None:
    with CONFIG.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    app_version: str = data["app_version"]
    catalog_slugs = discover_catalog_slugs()
    platform_blocks = load_platforms(data)

    py_src = generate_python(data, catalog_slugs, platform_blocks)
    ts_src = generate_typescript(data, catalog_slugs, platform_blocks)

    PY_OUT.write_text(py_src, encoding="utf-8")
    print(f"wrote {PY_OUT.relative_to(ROOT)}")

    TS_OUT.parent.mkdir(parents=True, exist_ok=True)
    TS_OUT.write_text(ts_src, encoding="utf-8")
    print(f"wrote {TS_OUT.relative_to(ROOT)}")

    VERSION_OUT.write_text(f"{app_version}\n", encoding="utf-8")
    print(f"wrote {VERSION_OUT.relative_to(ROOT)}")

    sync_package_json_version(FRONTEND_PKG, app_version)
    print(f"synced version in {FRONTEND_PKG.relative_to(ROOT)}")

    sync_package_json_version(DOCS_PKG, app_version)
    print(f"synced version in {DOCS_PKG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
