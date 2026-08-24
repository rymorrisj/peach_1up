"""Tests for backend/service/utils/platform/windows/app_container.py.

Covers get_container_config's settings-tier CPU/memory limit resolution
(SECURITY.md, "Both skip flags are honoured on both isolation layers"),
build_container_moniker's string format, and
validate_descriptor_grant_surface's startup-validation contract.

Config generation only (SandboxConfig construction), never wincage.launch()
or any Win32/AppContainer call, so no process/thread/handle is created.
"""

import pytest


_FAKE_ERA = {"cpu_limit_percent": 75, "memory_limit_mb": 2048}


def _patch_common(monkeypatch, app_container, *, descriptor=None, skip_cpu=False, skip_mem=False):
    """Isolate get_container_config from the real catalog/eras.yaml/settings.

    descriptor defaults to a bare entry with no container_broker_files, so
    tests that only care about the CPU/memory/moniker fields never reach
    _resolve_path_key.
    """
    monkeypatch.setattr(app_container, "get_emulator", lambda slug: descriptor or {"container_broker_files": []})
    monkeypatch.setattr(app_container, "_load_era", lambda slug: dict(_FAKE_ERA))
    monkeypatch.setattr(app_container, "get_skip_cpu_limit", lambda slug: skip_cpu)
    monkeypatch.setattr(app_container, "get_skip_memory_limit", lambda slug: skip_mem)


# ---------------------------------------------------------------------------
# get_container_config: skip_cpu_limit resolution
# ---------------------------------------------------------------------------
#
# get_container_config must source the flag from get_skip_cpu_limit()
# rather than reading descriptor["skip_cpu_limit"] directly.
# Each test patches get_skip_cpu_limit to disagree with the
# descriptor field so a return to descriptor.get() fails them.
#
# Resolution *within* get_skip_cpu_limit is emulator_catalog's own concern and
# is covered there so settings=True/descriptor=False deliberately does not yield True.

class TestGetContainerConfigSkipCpuLimit:
    def test_skip_cpu_limit_sourced_from_get_skip_cpu_limit_not_descriptor(self, monkeypatch):
        """Descriptor says False, the resolver says True; the resolver wins."""
        import backend.service.utils.platform.windows.app_container as app_container
        descriptor = {"container_broker_files": [], "skip_cpu_limit": False}
        _patch_common(monkeypatch, app_container, descriptor=descriptor, skip_cpu=True, skip_mem=False)

        cfg = app_container.get_container_config("fake-emu", "fake.exe")
        assert cfg.skip_cpu_limit is True

    def test_skip_cpu_limit_false_from_resolver_is_honoured(self, monkeypatch):
        import backend.service.utils.platform.windows.app_container as app_container
        descriptor = {"container_broker_files": [], "skip_cpu_limit": True}
        _patch_common(monkeypatch, app_container, descriptor=descriptor, skip_cpu=False, skip_mem=False)

        cfg = app_container.get_container_config("fake-emu", "fake.exe")
        assert cfg.skip_cpu_limit is False


# ---------------------------------------------------------------------------
# get_container_config: skip_memory_limit resolution + memory_limit_mb
# ---------------------------------------------------------------------------

class TestGetContainerConfigSkipMemoryLimit:
    def test_skip_memory_limit_true_nulls_memory_limit_mb(self, monkeypatch):
        """Same call-boundary regression as skip_cpu_limit above."""
        import backend.service.utils.platform.windows.app_container as app_container
        descriptor = {"container_broker_files": [], "skip_memory_limit": False}
        _patch_common(monkeypatch, app_container, descriptor=descriptor, skip_cpu=False, skip_mem=True)

        cfg = app_container.get_container_config("fake-emu", "fake.exe")
        assert cfg.memory_limit_mb is None

    def test_skip_memory_limit_false_uses_era_derived_value(self, monkeypatch):
        import backend.service.utils.platform.windows.app_container as app_container
        descriptor = {"container_broker_files": [], "skip_memory_limit": True}
        _patch_common(monkeypatch, app_container, descriptor=descriptor, skip_cpu=False, skip_mem=False)

        cfg = app_container.get_container_config("fake-emu", "fake.exe")
        assert cfg.memory_limit_mb == _FAKE_ERA["memory_limit_mb"]


# ---------------------------------------------------------------------------
# get_container_config: launch_paths override vs directory-wide fallback
# ---------------------------------------------------------------------------

class TestGetContainerConfigLaunchPathsOverride:
    def test_launch_paths_entry_overrides_directory_fallback_grant(self, monkeypatch):
        import backend.service.utils.platform.windows.app_container as app_container
        descriptor = {"container_broker_files": [{"path_key": "hdd_image", "access": "r"}]}
        _patch_common(monkeypatch, app_container, descriptor=descriptor)
        monkeypatch.setattr(app_container, "_resolve_path_key", lambda path_key, slug: "/fallback/xemu/")

        cfg_without_override = app_container.get_container_config("xemu", "xemu.exe")
        assert cfg_without_override.broker_files[0].path == "/fallback/xemu/"

        cfg_with_override = app_container.get_container_config(
            "xemu", "xemu.exe", launch_paths={"hdd_image": "/exact/game.qcow2"})
        assert cfg_with_override.broker_files[0].path == "/exact/game.qcow2"


# ---------------------------------------------------------------------------
# get_container_config: era-derived cpu_limit_percent
# ---------------------------------------------------------------------------

class TestGetContainerConfigCpuLimitMissing:
    def test_missing_cpu_limit_percent_raises_instead_of_defaulting(self, monkeypatch):
        """Fail-loud: an era block with no cpu_limit_percent must raise, never
        fall back to an unlimited (or arbitrary) rate on the container path."""
        import backend.service.utils.platform.windows.app_container as app_container
        _patch_common(monkeypatch, app_container)
        monkeypatch.setattr(app_container, "_load_era", lambda slug: {"memory_limit_mb": 2048})

        with pytest.raises(RuntimeError, match="cpu_limit_percent"):
            app_container.get_container_config("fake-emu", "fake.exe")


# ---------------------------------------------------------------------------
# _resolve_path_key: derived map wins over a same-named settings row
# ---------------------------------------------------------------------------

class TestResolvePathKeyPrecedence:
    def test_derived_path_wins_over_a_same_named_settings_row(self, monkeypatch):
        """The descriptor vocabulary (install_dir, cache, content, nvram, ...)
        is schema-fixed, so a user-editable settings key spelled the same must
        never redirect a grant the descriptor already gave a fixed meaning."""
        import backend.service.utils.platform.windows.app_container as app_container
        from backend.service.utils import settings as settings_mod

        monkeypatch.setattr(app_container, "resolve_derived_path", lambda pk, slug: "/derived/cache")
        monkeypatch.setattr(settings_mod, "get", lambda key, *a, **kw: "/settings/cache")

        assert app_container._resolve_path_key("cache", "xemu") == "/derived/cache"

    def test_settings_row_is_used_only_when_the_derived_map_misses(self, monkeypatch):
        import backend.service.utils.platform.windows.app_container as app_container
        from backend.service.utils import settings as settings_mod

        monkeypatch.setattr(app_container, "resolve_derived_path", lambda pk, slug: None)
        monkeypatch.setattr(settings_mod, "get", lambda key, *a, **kw: "/settings/roms")

        assert app_container._resolve_path_key("ROMS_PATH", "xemu") == "/settings/roms"


# ---------------------------------------------------------------------------
# build_container_moniker: pure string construction
# ---------------------------------------------------------------------------

class TestBuildContainerMoniker:
    def test_none_scope_yields_shared_moniker(self):
        from backend.service.utils.platform.windows.app_container import build_container_moniker
        assert build_container_moniker("xemu", None) == "Peach1UP.xemu.shared"

    def test_int_scope_yields_per_user_moniker(self):
        from backend.service.utils.platform.windows.app_container import build_container_moniker
        assert build_container_moniker("xemu", 7) == "Peach1UP.xemu.7"


# INTEGRATION TEST NEEDED: nothing above proves the SandboxConfig built here
# is the one that reaches sandbox_host.exe, or that the native side honours
# skip_cpu_limit/memory_limit_mb once it does. Needs a real launch with a
# live process. See TESTING.md, "AppContainer and sandbox_host.exe".

# ---------------------------------------------------------------------------
# validate_descriptor_grant_surface
# ---------------------------------------------------------------------------

class TestValidateDescriptorGrantSurface:
    def test_passes_against_real_emulator_catalog(self, monkeypatch, tmp_path):
        """Runs against the real config/emulators/ catalog, unpatched. APPDATA
        is stubbed so xemu's appdata_xemu path_key resolves off Windows too."""
        import backend.service.utils.platform.windows.app_container as app_container
        monkeypatch.setenv("APPDATA", str(tmp_path))
        app_container.validate_descriptor_grant_surface()

    def test_raises_for_descriptor_with_unresolvable_path_key(self, monkeypatch):
        """Fake descriptor via a patched load_catalog, never a real one."""
        from backend.service.utils import emulator_catalog
        import backend.service.utils.platform.windows.app_container as app_container
        fake_descriptor = {
            "slug": "fake-emu",
            "container_broker_files": [{"path_key": "nonexistent_key_xyz"}],
        }
        monkeypatch.setattr(emulator_catalog, "load_catalog", lambda: [fake_descriptor])

        with pytest.raises(RuntimeError, match="nonexistent_key_xyz"):
            app_container.validate_descriptor_grant_surface()
