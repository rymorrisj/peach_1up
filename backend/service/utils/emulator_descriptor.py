"""
Pydantic schema for config/emulators/*.toml descriptors.

_load_raw_catalog() (emulator_catalog.py) parses every TOML in
config/emulators/ through EmulatorDescriptor before caching it. Unknown
fields are rejected here so a stale or typo'd TOML key fails loudly at load
time instead of silently reading as a no-op default, the same producer
choke-point philosophy _VALID_INSTALL_TYPES already applies to install_type.

_load_raw_catalog dumps each validated descriptor back to a plain dict
(model_dump(exclude_none=True)) before caching, so every existing consumer
across the codebase, which reads catalog entries as bare dicts via .get() or
[...], is unaffected by this schema layer. This module is a validation and
normalisation boundary at the TOML-parse choke-point, not a new type
threaded through the rest of the codebase.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.constants_generated import InstallType
from backend.service.utils.emulator_paths import resolve_derived_path


class EmulatorDependency(BaseModel):
    """One [[dependencies]] entry: a BIOS/ROM/asset requirement."""

    model_config = ConfigDict(extra="forbid")

    name: str
    display_name: str = ""
    platform: str = ""
    acquire_method: str = ""
    acquire_url: str = ""
    acquire_tag: str = ""
    acquire_target: str = ""
    required: bool = True
    bios_path: str = ""
    guidance_text: str = ""
    guidance_url: str = ""
    required_files: Optional[list[str]] = None
    required_glob: Optional[str] = None
    required_glob_excludes: Optional[list[str]] = None


class ContainerBrokerFile(BaseModel):
    """One [[container_broker_files]] entry: an AppContainer broker/DACL grant."""

    model_config = ConfigDict(extra="forbid")

    path_key: Optional[str] = None
    path: Optional[str] = None
    access: Literal["r", "rw", "x"]
    mode: Literal["grant", "secure", "inherit"] = "grant"

    @model_validator(mode="after")
    def _validate_exactly_one_path_source(self) -> "ContainerBrokerFile":
        """An entry with neither field previously passed every check here and
        only failed with a bare KeyError inside app_container.py at actual
        launch time (``entry["path_key"]``), long after descriptor load. Fail
        loud at the TOML-parse choke-point instead, matching every other
        field in this schema.
        """
        if (self.path_key is None) == (self.path is None):
            raise ValueError(
                "container_broker_files entry must set exactly one of "
                f"'path_key' or 'path' (path_key={self.path_key!r}, path={self.path!r})"
            )
        return self


class KnownLimitation(BaseModel):
    """One [[known_limitations]] entry, surfaced verbatim on the Emulators page."""

    model_config = ConfigDict(extra="forbid")

    title: str
    severity: str
    description: str


class EmulatorDescriptor(BaseModel):
    """Schema for a single config/emulators/*.toml file.

    Covers both launchable emulator descriptors and the rom-pack config
    (86box-roms.toml, install_type == "rom_pack") in one shape: the two
    differ only in which optional fields they populate (a rom pack has no
    era, container, or binary-launch fields), not in overall structure.
    """

    model_config = ConfigDict(extra="forbid")

    # slug feeds directly into filesystem paths via
    # emulator_paths.resolve_derived_path (base / "emulators" / slug / ...)
    # with no further sanitisation there, so a value containing "..", a path
    # separator, or a leading dot could escape the intended emulators/<slug>/
    # directory. Every real slug in config/emulators/*.toml today is
    # lowercase alphanumeric with optional internal hyphens; the pattern
    # matches that convention rather than merely blocking traversal.
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str
    display_name: str = ""
    description: str = ""
    era: Optional[str] = None
    supported_eras: list[str] = Field(default_factory=list)
    settings_key: Optional[str] = None
    version: str = ""
    binary: str
    download_url: str = ""
    portable_sentinel: str = ""
    cli_args_prefix: list[str] = Field(default_factory=list)
    container_enabled: bool = False
    container_hardcap_disabled: bool = False
    container_hardcap_note: Optional[str] = None
    container_permanently_excluded: bool = False
    # No default on either flag: a descriptor that omits one must fail at
    # load time, not silently fall back to an unenforced limit at launch
    # time. RPCS3 shipped a full release with skip_cpu_limit unset before
    # this was caught by hand (see commit bc07a5c) - this closes that class
    # of omission for good. 86box-roms.toml (install_type == "rom_pack")
    # sets both to true too, even though it never launches as a Job Object
    # process, purely for schema uniformity across every file in the
    # directory.
    skip_memory_limit: bool
    skip_cpu_limit: bool
    required: bool = False
    install_type: InstallType
    install_scope: str = "portable"
    asset_pattern: Optional[str] = None
    license: str = ""
    copyright: str = ""
    source_url: str = ""
    rom_pack_version: str = ""
    rom_pack_url: str = ""
    supported_formats: list[str] = Field(default_factory=list)
    guidance_text: str = ""
    guidance_url: str = ""
    install_note: Optional[str] = None
    container_broker_files: list[ContainerBrokerFile] = Field(default_factory=list)
    dependencies: list[EmulatorDependency] = Field(default_factory=list)
    known_limitations: list[KnownLimitation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_install_dir_write_access(self) -> "EmulatorDescriptor":
        """A sentinel write into install_dir requires write access to get there.

        ensure_portable_mode() touches portable_sentinel next to the binary
        (install_dir) whenever container_enabled is true and the sentinel is
        non-empty. install_dir must therefore grant "rw" directly, or another
        broker entry with access="rw" and mode="grant" must resolve to the
        identical directory - the 86box pattern, where config_dir doubles
        install_dir, so the "r" grant on install_dir there is inert rather
        than a bug. Path identity is checked via _resolve_path_key's derived
        paths, not by comparing path_key names, since two different keys can
        legitimately resolve to the same directory.

        Path identity is checked against the derived-path map only
        (emulator_paths.resolve_derived_path). The settings tier and the
        appdata_xemu branch of app_container._resolve_path_key are deliberately
        not consulted here: this validator runs at TOML-parse time, so it must
        not pull the settings/database stack into the catalog load, and neither
        tier can produce a path equal to a derived install_dir anyway. An entry
        keyed on either tier resolves to None here, which simply fails to match
        install_dir, exactly as a settings-resolved path would.
        """
        if not (self.container_enabled and self.portable_sentinel):
            return self
        install_dir_entries = [e for e in self.container_broker_files if e.path_key == "install_dir"]
        if not install_dir_entries or install_dir_entries[0].access != "r":
            return self

        def _resolve(entry: ContainerBrokerFile) -> Optional[str]:
            if entry.path:
                return entry.path
            if not entry.path_key:
                return None
            return resolve_derived_path(entry.path_key, self.slug)

        install_dir_path = _resolve(install_dir_entries[0])
        for entry in self.container_broker_files:
            if entry.access == "rw" and entry.mode == "grant" and _resolve(entry) == install_dir_path:
                return self

        raise ValueError(
            f"{self.slug}: container_enabled=true with a non-empty portable_sentinel "
            f"('{self.portable_sentinel}') needs write access to create it, but "
            "install_dir is access='r' and no other rw+grant broker entry resolves "
            "to the identical directory."
        )

    @model_validator(mode="after")
    def _validate_supported_formats_matches_eras(self) -> "EmulatorDescriptor":
        """supported_formats is display-only (GET /emulators) today, no launch
        backend trusts it for validation, they all read config/eras.yaml's
        supported_media directly (see backend.service.utils.file_types.
        supported_extensions_for_era) so a drift here can never cause a real
        launch to accept or reject the wrong file. But a drifted display list
        actively misinforms users on the Emulators page, so this closes it at
        the same producer choke-point every other TOML field already goes
        through: fail loud at load time rather than let it silently diverge
        from the one enforced source of truth.

        supported_eras (when set, e.g. mesen serving both nes and snes) is
        checked in full instead of just era, since a multi-era emulator's
        supported_formats is expected to cover every era it serves, not only
        its single most-demanding one (era's role is AppContainer sizing, a
        different axis, see DECISIONS.md 2026-05-28).

        Skipped entirely for a descriptor with neither era nor supported_eras
        set (the rom_pack config, 86box-roms.toml, has no era of its own).
        """
        eras_to_check = self.supported_eras or ([self.era] if self.era else [])
        if not eras_to_check:
            return self

        # Deferred import: file_types.py -> eras_config.py has no import-time
        # dependency on this module, but every other cross-module import in
        # this file is deferred for consistency with the cycle-avoidance
        # pattern _validate_install_dir_write_access already established.
        from backend.service.utils.file_types import supported_extensions_for_era

        expected: set[str] = set()
        for era in eras_to_check:
            expected.update(supported_extensions_for_era(era))
        actual = set(self.supported_formats)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(
                f"{self.slug}: supported_formats {sorted(actual)} does not match "
                f"config/eras.yaml's supported_media for era(s) {sorted(eras_to_check)} "
                f"(expected {sorted(expected)}). Missing: {missing or 'none'}; "
                f"unexpected: {extra or 'none'}. Update config/emulators/{self.slug}.toml "
                "or config/eras.yaml so they agree."
            )
        return self
