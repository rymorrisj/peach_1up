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

    slug: str
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
        """
        if not (self.container_enabled and self.portable_sentinel):
            return self
        install_dir_entries = [e for e in self.container_broker_files if e.path_key == "install_dir"]
        if not install_dir_entries or install_dir_entries[0].access != "r":
            return self

        # Deferred import: app_container.py imports get_emulator/get_emulator_era
        # from emulator_catalog.py at module level, so importing it at module
        # level here would create a cycle (this module is imported by
        # emulator_catalog.py to build the catalog in the first place).
        from backend.service.utils.platform.windows.app_container import _resolve_path_key

        def _resolve(entry: ContainerBrokerFile) -> Optional[str]:
            if entry.path:
                return entry.path
            if not entry.path_key:
                return None
            try:
                return _resolve_path_key(entry.path_key, self.slug)
            except Exception:
                return None

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
