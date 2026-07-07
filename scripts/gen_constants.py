"""Generate backend/constants_generated.py and frontend/src/generated/constants.ts
from config/constants.yaml.

Run from the project root:
    python scripts/gen_constants.py
"""

from __future__ import annotations

import re
import textwrap
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "constants.yaml"
EMULATORS_DIR = ROOT / "config" / "emulators"
PY_OUT = ROOT / "backend" / "constants_generated.py"
TS_OUT = ROOT / "frontend" / "src" / "generated" / "constants.ts"

HEADER_PY = "# Auto-generated from config/constants.yaml — do not edit.\n"
HEADER_TS = "// Auto-generated from config/constants.yaml — do not edit.\n"


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

    The TOMLs are the source of truth for the emulator catalog domain — this
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


def generate_python(data: dict, catalog_slugs: list[str]) -> str:
    eras: dict[str, str] = data["eras"]
    backends: dict[str, str] = data["backend_slugs"]
    system_labels: dict[str, str] = data["backend_system_labels"]
    ratings: list[dict[str, str]] = data["content_ratings"]
    dgvoodoo2_eras: list[str] = data.get("dgvoodoo2_supported_eras", [])
    media_types: dict[str, str] = data["media_types"]
    hardware_profiles: dict[str, str] = data["hardware_profiles"]
    tag_colors: list[dict[str, str]] = data["tag_colors"]
    install_types: list[str] = data["install_types"]

    lines: list[str] = [HEADER_PY, "from enum import Enum\n", "from typing import Literal\n\n\n"]

    # Era enum
    lines.append("class Era(Enum):\n")
    for slug in eras:
        lines.append(f'    {_enum_name(slug)} = "{slug}"\n')
    lines.append("\n\n")

    # EraValue literal — boundary type (DB columns, API I/O); Era enum above is
    # for internal named-member dispatch only, see era_to_enum().
    lines.append(_py_literal_type("EraValue", list(eras)))
    lines.append("\n")

    # BackendSlug enum
    lines.append("class BackendSlug(Enum):\n")
    for slug in backends:
        lines.append(f'    {_enum_name(slug)} = "{slug}"\n')
    lines.append("\n\n")

    # ERA_LABELS
    lines.append("ERA_LABELS: dict[str, str] = {\n")
    for slug, label in eras.items():
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

    # DGVOODOO2_SUPPORTED_ERAS
    lines.append("DGVOODOO2_SUPPORTED_ERAS: list[str] = [\n")
    for era in dgvoodoo2_eras:
        lines.append(f'    "{era}",\n')
    lines.append("]\n\n")

    # MediaType literal
    lines.append(_py_literal_type("MediaType", list(media_types)))
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

    return "".join(lines)


def generate_typescript(data: dict, catalog_slugs: list[str]) -> str:
    eras: dict[str, str] = data["eras"]
    backends: dict[str, str] = data["backend_slugs"]
    system_labels: dict[str, str] = data["backend_system_labels"]
    ratings: list[dict[str, str]] = data["content_ratings"]
    dgvoodoo2_eras: list[str] = data.get("dgvoodoo2_supported_eras", [])
    media_types: dict[str, str] = data["media_types"]
    hardware_profiles: dict[str, str] = data["hardware_profiles"]
    tag_colors: list[dict[str, str]] = data["tag_colors"]
    install_types: list[str] = data["install_types"]

    lines: list[str] = [HEADER_TS, "\n"]

    # Era union
    lines.append(_ts_union_type("Era", list(eras)))
    lines.append("\n")

    # ERA_LABELS
    lines.append("export const ERA_LABELS: Record<string, string> = {\n")
    for slug, label in eras.items():
        lines.append(f'  {slug}: "{label}",\n')
    lines.append("}\n\n")

    # BACKEND_LABELS
    lines.append("export const BACKEND_LABELS: Record<string, string> = {\n")
    for slug, label in backends.items():
        # '86box' is not a valid bare identifier — quote it
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

    # RATING_OPTIONS — includes a leading empty option for form use
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

    # DGVOODOO2_SUPPORTED_ERAS
    eras_ts = ", ".join(f'"{e}"' for e in dgvoodoo2_eras)
    lines.append(f"export const DGVOODOO2_SUPPORTED_ERAS: string[] = [{eras_ts}]\n\n")

    # MediaType union
    lines.append(_ts_union_type("MediaType", list(media_types)))
    lines.append("\n")

    # EmulatorCatalogSlug union (sourced from config/emulators/*.toml, not constants.yaml)
    lines.append(_ts_union_type("EmulatorCatalogSlug", catalog_slugs))
    lines.append("\n")

    # EMULATOR_CATALOG_SLUGS — runtime companion for <select> options
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

    return "".join(lines)


def main() -> None:
    with CONFIG.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    catalog_slugs = discover_catalog_slugs()

    py_src = generate_python(data, catalog_slugs)
    ts_src = generate_typescript(data, catalog_slugs)

    PY_OUT.write_text(py_src, encoding="utf-8")
    print(f"wrote {PY_OUT.relative_to(ROOT)}")

    TS_OUT.parent.mkdir(parents=True, exist_ok=True)
    TS_OUT.write_text(ts_src, encoding="utf-8")
    print(f"wrote {TS_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
