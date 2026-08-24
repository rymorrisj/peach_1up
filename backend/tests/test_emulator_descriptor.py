"""Tests for backend/service/utils/emulator_descriptor.py, the Pydantic
schema every config/emulators/*.toml file is validated against at load time
(_load_raw_catalog in emulator_catalog.py).

Covers EmulatorDescriptor's required-field enforcement, the slug pattern
(slugs reach filesystem paths with no later sanitisation, so traversal-shaped
ones must be rejected here), the extra="forbid" typo/staleness guard,
ContainerBrokerFile's exactly-one-of path/path_key validator, and both
model_validators: _validate_install_dir_write_access and
_validate_supported_formats_matches_eras.
"""

import pytest
from pydantic import ValidationError

from backend.service.utils.emulator_descriptor import (
    ContainerBrokerFile,
    EmulatorDependency,
    EmulatorDescriptor,
    KnownLimitation,
)


def _valid_kwargs(**overrides):
    kwargs = dict(
        slug="dosbox-x",
        name="DOSBox-X",
        binary="dosbox-x.exe",
        skip_memory_limit=True,
        skip_cpu_limit=True,
        install_type="bundled",
    )
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# Valid minimal descriptor + defaults
# ---------------------------------------------------------------------------


class TestValidMinimalDescriptor:
    def test_minimal_required_fields_construct_successfully(self):
        descriptor = EmulatorDescriptor(**_valid_kwargs())
        assert descriptor.slug == "dosbox-x"
        assert descriptor.binary == "dosbox-x.exe"

    def test_optional_fields_default_correctly(self):
        descriptor = EmulatorDescriptor(**_valid_kwargs())
        assert descriptor.display_name == ""
        assert descriptor.era is None
        assert descriptor.supported_eras == []
        assert descriptor.container_enabled is False
        assert descriptor.install_scope == "portable"
        assert descriptor.container_broker_files == []
        assert descriptor.dependencies == []
        assert descriptor.known_limitations == []

    def test_rom_pack_shape_with_no_era_and_container_fields_still_validates(self):
        """86box-roms.toml (install_type='rom_pack') has no era, container, or
        binary-launch fields populated; it's still schema-uniform with a
        launchable descriptor (see class docstring)."""
        descriptor = EmulatorDescriptor(**_valid_kwargs(
            slug="86box-roms", name="86Box ROM Pack", binary="",
            install_type="rom_pack", skip_memory_limit=True, skip_cpu_limit=True,
        ))
        assert descriptor.era is None
        assert descriptor.supported_eras == []


# ---------------------------------------------------------------------------
# Required-field enforcement: skip_memory_limit / skip_cpu_limit have no
# default, an omission must fail loud at load time (see the field's own
# comment referencing the real RPCS3 incident, commit bc07a5c).
# ---------------------------------------------------------------------------


class TestRequiredFieldsNoSilentDefault:
    def test_missing_skip_memory_limit_raises(self):
        kwargs = _valid_kwargs()
        del kwargs["skip_memory_limit"]
        with pytest.raises(ValidationError):
            EmulatorDescriptor(**kwargs)

    def test_missing_skip_cpu_limit_raises(self):
        kwargs = _valid_kwargs()
        del kwargs["skip_cpu_limit"]
        with pytest.raises(ValidationError):
            EmulatorDescriptor(**kwargs)

    def test_missing_slug_raises(self):
        kwargs = _valid_kwargs()
        del kwargs["slug"]
        with pytest.raises(ValidationError):
            EmulatorDescriptor(**kwargs)

    def test_missing_install_type_raises(self):
        kwargs = _valid_kwargs()
        del kwargs["install_type"]
        with pytest.raises(ValidationError):
            EmulatorDescriptor(**kwargs)

    def test_unknown_install_type_value_raises(self):
        with pytest.raises(ValidationError):
            EmulatorDescriptor(**_valid_kwargs(install_type="not-a-real-type"))


# ---------------------------------------------------------------------------
# extra="forbid": a stale/typo'd TOML key must fail loud at load time, not
# silently read as a no-op default.
# ---------------------------------------------------------------------------


class TestExtraFieldsForbidden:
    def test_unknown_top_level_field_raises(self):
        with pytest.raises(ValidationError):
            EmulatorDescriptor(**_valid_kwargs(totally_unrecognised_field="x"))

    def test_unknown_dependency_field_raises(self):
        with pytest.raises(ValidationError):
            EmulatorDependency(name="ps1-bios", not_a_real_field="x")

    def test_unknown_known_limitation_field_raises(self):
        with pytest.raises(ValidationError):
            KnownLimitation(title="t", severity="low", description="d", extra_field="x")


# ---------------------------------------------------------------------------
# slug pattern: feeds directly into filesystem paths (emulators/<slug>/) with
# no further sanitisation downstream, must reject anything traversal-shaped.
# ---------------------------------------------------------------------------


class TestSlugPattern:
    @pytest.mark.parametrize("slug", ["dosbox-x", "86box", "duckstation", "pcsx2", "a", "a1-b2-c3"])
    def test_valid_slugs_accepted(self, slug):
        EmulatorDescriptor(**_valid_kwargs(slug=slug))

    @pytest.mark.parametrize(
        "slug",
        [
            "..",
            "../evil",
            "..%2Fevil",
            "/etc/passwd",
            "DOSBox-X",  # uppercase
            "-leading-hyphen",
            "trailing-hyphen-",
            "double--hyphen",
            "with space",
            "with_underscore",
            "",
            "with.dot",
        ],
    )
    def test_invalid_slugs_rejected(self, slug):
        with pytest.raises(ValidationError):
            EmulatorDescriptor(**_valid_kwargs(slug=slug))


# ---------------------------------------------------------------------------
# ContainerBrokerFile: exactly one of path_key/path, valid access literal
# ---------------------------------------------------------------------------


class TestContainerBrokerFileExactlyOnePathSource:
    def test_path_key_only_is_valid(self):
        ContainerBrokerFile(path_key="install_dir", access="rw")

    def test_path_only_is_valid(self):
        ContainerBrokerFile(path="C:/some/literal/path", access="r")

    def test_neither_path_key_nor_path_raises(self):
        with pytest.raises(ValidationError):
            ContainerBrokerFile(access="r")

    def test_both_path_key_and_path_raises(self):
        with pytest.raises(ValidationError):
            ContainerBrokerFile(path_key="install_dir", path="C:/literal", access="r")

    def test_invalid_access_literal_raises(self):
        with pytest.raises(ValidationError):
            ContainerBrokerFile(path_key="install_dir", access="not-a-real-access-mode")

    def test_mode_defaults_to_grant(self):
        entry = ContainerBrokerFile(path_key="install_dir", access="r")
        assert entry.mode == "grant"


# ---------------------------------------------------------------------------
# _validate_install_dir_write_access
# ---------------------------------------------------------------------------


class TestValidateInstallDirWriteAccess:
    def test_container_disabled_skips_validator_entirely(self):
        """Even a broker config that would otherwise fail must pass when
        container_enabled is False, the validator's early-return guard."""
        descriptor = EmulatorDescriptor(**_valid_kwargs(
            container_enabled=False,
            portable_sentinel=".installed",
            container_broker_files=[{"path_key": "install_dir", "access": "r"}],
        ))
        assert descriptor.container_enabled is False

    def test_empty_portable_sentinel_skips_validator(self):
        descriptor = EmulatorDescriptor(**_valid_kwargs(
            container_enabled=True,
            portable_sentinel="",
            container_broker_files=[{"path_key": "install_dir", "access": "r"}],
        ))
        assert descriptor.portable_sentinel == ""

    def test_no_install_dir_entry_skips_validator(self):
        descriptor = EmulatorDescriptor(**_valid_kwargs(
            container_enabled=True,
            portable_sentinel=".installed",
            container_broker_files=[{"path_key": "saves_dir", "access": "rw"}],
        ))
        assert descriptor.container_enabled is True

    def test_install_dir_with_rw_access_directly_passes(self):
        """install_dir granted rw directly needs no second broker entry."""
        descriptor = EmulatorDescriptor(**_valid_kwargs(
            container_enabled=True,
            portable_sentinel=".installed",
            container_broker_files=[{"path_key": "install_dir", "access": "rw"}],
        ))
        assert descriptor.container_enabled is True

    def test_install_dir_read_only_with_no_matching_rw_grant_raises(self):
        with pytest.raises(ValidationError, match="needs write access"):
            EmulatorDescriptor(**_valid_kwargs(
                container_enabled=True,
                portable_sentinel=".installed",
                container_broker_files=[{"path_key": "install_dir", "access": "r"}],
            ))

    def test_install_dir_read_only_with_config_dir_rw_grant_resolving_identically_passes(self):
        """The 86box pattern called out in the docstring: config_dir derives
        to the same path as install_dir (both base/emulators/<slug>), so a
        separate rw+grant entry keyed on config_dir satisfies the write-access
        requirement without install_dir itself needing rw."""
        descriptor = EmulatorDescriptor(**_valid_kwargs(
            slug="86box",
            container_enabled=True,
            portable_sentinel=".installed",
            container_broker_files=[
                {"path_key": "install_dir", "access": "r"},
                {"path_key": "config_dir", "access": "rw", "mode": "grant"},
            ],
        ))
        assert descriptor.slug == "86box"

    def test_install_dir_read_only_with_rw_but_non_grant_mode_still_raises(self):
        """A matching path with access='rw' but mode != 'grant' (e.g.
        'secure') does not satisfy the requirement, mode='grant' is checked
        explicitly, not just access."""
        with pytest.raises(ValidationError, match="needs write access"):
            EmulatorDescriptor(**_valid_kwargs(
                slug="86box",
                container_enabled=True,
                portable_sentinel=".installed",
                container_broker_files=[
                    {"path_key": "install_dir", "access": "r"},
                    {"path_key": "config_dir", "access": "rw", "mode": "secure"},
                ],
            ))

    def test_install_dir_read_only_with_rw_grant_at_different_path_still_raises(self):
        """An rw+grant entry that resolves to a DIFFERENT derived directory
        (e.g. saves_dir, not the same physical path as install_dir) must not
        satisfy the requirement, path identity is checked, not just that some
        rw+grant entry exists somewhere in the list."""
        with pytest.raises(ValidationError, match="needs write access"):
            EmulatorDescriptor(**_valid_kwargs(
                container_enabled=True,
                portable_sentinel=".installed",
                container_broker_files=[
                    {"path_key": "install_dir", "access": "r"},
                    {"path_key": "saves_dir", "access": "rw", "mode": "grant"},
                ],
            ))

    def test_install_dir_as_literal_path_matching_rw_grant_literal_path_passes(self):
        """Path-identity check also works for two entries both keyed by
        literal 'path' (not path_key) resolving to the same string."""
        descriptor = EmulatorDescriptor(**_valid_kwargs(
            container_enabled=True,
            portable_sentinel=".installed",
            container_broker_files=[
                {"path": "C:/emulators/dosbox-x", "access": "r"},
                {"path": "C:/emulators/dosbox-x", "access": "rw", "mode": "grant"},
            ],
        ))
        assert descriptor.container_enabled is True


# ---------------------------------------------------------------------------
# _validate_supported_formats_matches_eras
# ---------------------------------------------------------------------------


class TestValidateSupportedFormatsMatchesEras:
    @pytest.fixture(autouse=True)
    def _patch_supported_extensions(self, monkeypatch):
        import backend.service.utils.file_types as file_types_mod

        table = {
            "dos": [".iso", ".img", ".cue"],
            "nes": [".nes"],
            "snes": [".sfc", ".smc"],
        }
        monkeypatch.setattr(
            file_types_mod, "supported_extensions_for_era", lambda era: table.get(era, []),
        )

    def test_no_era_and_no_supported_eras_skips_validator(self):
        """rom_pack config: neither era nor supported_eras set, supported_formats
        is not checked at all regardless of its content."""
        descriptor = EmulatorDescriptor(**_valid_kwargs(
            supported_formats=["totally", "wrong", "values"],
        ))
        assert descriptor.era is None
        assert descriptor.supported_eras == []

    def test_matching_supported_formats_for_single_era_passes(self):
        descriptor = EmulatorDescriptor(**_valid_kwargs(
            era="dos", supported_formats=[".iso", ".img", ".cue"],
        ))
        assert descriptor.era == "dos"

    def test_missing_extension_for_single_era_raises(self):
        with pytest.raises(ValidationError, match="Missing"):
            EmulatorDescriptor(**_valid_kwargs(
                era="dos", supported_formats=[".iso", ".img"],
            ))

    def test_extra_unexpected_extension_for_single_era_raises(self):
        with pytest.raises(ValidationError, match="unexpected"):
            EmulatorDescriptor(**_valid_kwargs(
                era="dos", supported_formats=[".iso", ".img", ".cue", ".xyz"],
            ))

    def test_multi_era_supported_formats_is_the_union(self):
        """mesen-style multi-era emulator: supported_formats must cover the
        union of every era in supported_eras, not just the first/primary one."""
        descriptor = EmulatorDescriptor(**_valid_kwargs(
            era="nes", supported_eras=["nes", "snes"],
            supported_formats=[".nes", ".sfc", ".smc"],
        ))
        assert descriptor.supported_eras == ["nes", "snes"]

    def test_multi_era_missing_one_eras_extensions_raises(self):
        with pytest.raises(ValidationError, match="Missing"):
            EmulatorDescriptor(**_valid_kwargs(
                era="nes", supported_eras=["nes", "snes"],
                supported_formats=[".nes"],  # missing snes's .sfc/.smc
            ))
