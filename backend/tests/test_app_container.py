"""Tests for backend/service/utils/platform/windows/app_container.py.

Covers get_container_config's settings-tier CPU/memory limit resolution
(SECURITY.md, "Both skip flags are honoured on both isolation layers"),
build_container_moniker's pure string format, and
validate_descriptor_grant_surface's startup-validation contract.

Only pure config-generation logic is exercised here (SandboxConfig
construction), never wincage.launch() or any Win32/AppContainer call, so
these tests carry no process/thread/handle risk.
"""

import pytest


_FAKE_ERA = {"cpu_limit_percent": 75, "memory_limit_mb": 2048}


def _patch_common(monkeypatch, app_container, *, descriptor=None, skip_cpu=False, skip_mem=False):
    """Isolate get_container_config from the real catalog/eras.yaml/settings.

    descriptor defaults to a bare entry with no container_broker_files, so
    broker_files resolution (and therefore _resolve_path_key/settings) is
    never exercised by tests that only care about the CPU/memory/moniker
    fields.
    """
    monkeypatch.setattr(app_container, "get_emulator", lambda slug: descriptor or {"container_broker_files": []})
    monkeypatch.setattr(app_container, "_load_era", lambda slug: dict(_FAKE_ERA))
    monkeypatch.setattr(app_container, "get_skip_cpu_limit", lambda slug: skip_cpu)
    monkeypatch.setattr(app_container, "get_skip_memory_limit", lambda slug: skip_mem)


# ---------------------------------------------------------------------------
# get_container_config: skip_cpu_limit resolution
# ---------------------------------------------------------------------------
#
# NOTE on scenario framing: the task that produced this file asked for a
# settings=true / descriptor=false combination to assert skip_cpu_limit=True.
# That combination does not reach True in the real resolver: emulator_catalog
# ._resolve_skip_flag() treats a descriptor False as a floor a settings-tier
# override cannot raise (SECURITY.md never documents that combination as
# yielding True; the settings row may only move the flag toward *more*
# restrictive, never less). Asserting True there would assert behavior the
# code deliberately does not have. The regression SECURITY.md actually
# documents is narrower: get_container_config must source skip_cpu_limit
# from get_skip_cpu_limit() (the settings-aware resolver), not read the
# descriptor field directly the way the container path used to (fixed value,
# cap applied unconditionally). These tests lock in that call boundary by
# monkeypatching get_skip_cpu_limit directly and using a descriptor whose own
# (unread) skip_cpu_limit field disagrees with it, so the test would fail if
# get_container_config ever went back to reading descriptor.get(...) instead.

class TestGetContainerConfigSkipCpuLimit:
    def test_skip_cpu_limit_sourced_from_get_skip_cpu_limit_not_descriptor(self, monkeypatch):
        """SECURITY.md: 'sandbox_host.exe had no representation of
        skip_cpu_limit at all ... job.cpp applied CPU rate control
        unconditionally. It now travels ... resolved through
        get_skip_cpu_limit().' Descriptor disagrees (False) with the
        resolver (True); the resolver must win."""
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
        """SECURITY.md notes this mirrors the skip_cpu_limit bug class:
        resolved through get_skip_memory_limit(), not descriptor.get()."""
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
# build_container_moniker: pure string construction
# ---------------------------------------------------------------------------

class TestBuildContainerMoniker:
    def test_none_scope_yields_shared_moniker(self):
        from backend.service.utils.platform.windows.app_container import build_container_moniker
        assert build_container_moniker("xemu", None) == "Peach1UP.xemu.shared"

    def test_int_scope_yields_per_user_moniker(self):
        from backend.service.utils.platform.windows.app_container import build_container_moniker
        assert build_container_moniker("xemu", 7) == "Peach1UP.xemu.7"


# ---------------------------------------------------------------------------
# validate_descriptor_grant_surface
# ---------------------------------------------------------------------------

class TestValidateDescriptorGrantSurface:
    def test_passes_against_real_emulator_catalog(self, monkeypatch, tmp_path):
        """Same catalog-loading pattern as test_emulator_catalog.py's
        test_load_catalog_returns_all_emulators: no monkeypatching of the
        catalog itself. APPDATA is stubbed only so xemu's appdata_xemu
        path_key resolves deterministically off Windows too (the real
        launch-time behavior already requires APPDATA to be set)."""
        import backend.service.utils.platform.windows.app_container as app_container
        monkeypatch.setenv("APPDATA", str(tmp_path))
        app_container.validate_descriptor_grant_surface()

    def test_raises_for_descriptor_with_unresolvable_path_key(self, monkeypatch):
        """Negative case uses a minimal fake descriptor via a patched
        load_catalog rather than mutating the real config/emulators/ catalog."""
        from backend.service.utils import emulator_catalog
        import backend.service.utils.platform.windows.app_container as app_container
        fake_descriptor = {
            "slug": "fake-emu",
            "container_broker_files": [{"path_key": "nonexistent_key_xyz"}],
        }
        monkeypatch.setattr(emulator_catalog, "load_catalog", lambda: [fake_descriptor])

        with pytest.raises(RuntimeError, match="nonexistent_key_xyz"):
            app_container.validate_descriptor_grant_surface()
