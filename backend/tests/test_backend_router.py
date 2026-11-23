"""Tests for backend routing, platform → backend mapping and routing invariants."""

import sys
from unittest.mock import MagicMock

import pytest

from backend.constants_generated import BackendSlug, Platform


# ---------------------------------------------------------------------------
# Shared parametrize data
# ---------------------------------------------------------------------------

_ROUTE_CASES = [
    (Platform.DOS, BackendSlug.DOSBOX_X.value),
    (Platform.WIN95, BackendSlug.BOX86.value),
    (Platform.WIN98, BackendSlug.BOX86.value),
    (Platform.WINXP, BackendSlug.BOX86.value),
    (Platform.PS1, BackendSlug.DUCKSTATION.value),
    (Platform.PS2, BackendSlug.PCSX2.value),
    (Platform.XBOX, BackendSlug.XEMU.value),
    (Platform.NES, BackendSlug.MESEN.value),
    (Platform.N64, BackendSlug.PROJECT64.value),
    (Platform.DREAMCAST, BackendSlug.FLYCAST.value),
]

_ROUTE_IDS = ["dos", "win95", "win98", "winxp", "ps1", "ps2", "xbox", "nes", "n64", "dreamcast"]

_EXEC_CASES = [
    (Platform.DOS, "dosbox-x"),
    (Platform.WIN95, "86box"),
    (Platform.WIN98, "86box"),
    (Platform.WINXP, "86box"),
    (Platform.PS1, "duckstation"),
    (Platform.PS2, "pcsx2"),
    (Platform.XBOX, "xemu"),
    (Platform.NES, "mesen"),
    (Platform.N64, "project64"),
    (Platform.DREAMCAST, "flycast"),
]

_EXEC_IDS = ["dos", "win95", "win98", "winxp", "ps1", "ps2", "xbox", "nes", "n64", "dreamcast"]

# Slug → module path for dispatch tests.
_DISPATCH_CASES = [
    (Platform.DOS, BackendSlug.DOSBOX_X.value, "backend.service.backends.dosbox"),
    (Platform.WIN95, BackendSlug.BOX86.value, "backend.service.backends.box86"),
    (Platform.WIN98, BackendSlug.BOX86.value, "backend.service.backends.box86"),
    (Platform.WINXP, BackendSlug.BOX86.value, "backend.service.backends.box86"),
    (Platform.PS1, BackendSlug.DUCKSTATION.value, "backend.service.backends.console"),
    (Platform.PS2, BackendSlug.PCSX2.value, "backend.service.backends.console"),
    (Platform.XBOX, BackendSlug.XEMU.value, "backend.service.backends.xemu"),
    (Platform.NES, BackendSlug.MESEN.value, "backend.service.backends.console"),
    (Platform.N64, BackendSlug.PROJECT64.value, "backend.service.backends.console"),
    (Platform.DREAMCAST, BackendSlug.FLYCAST.value, "backend.service.backends.flycast"),
]

_DISPATCH_IDS = ["dos", "win95", "win98", "winxp", "ps1", "ps2", "xbox", "nes", "n64", "dreamcast"]


# ---------------------------------------------------------------------------
# resolve_backend_name, complete platform→backend string mapping
# ---------------------------------------------------------------------------


class TestResolveBackendName:
    @pytest.mark.parametrize("platform,expected", _ROUTE_CASES, ids=_ROUTE_IDS)
    def test_platform_routes_to_expected_backend(self, platform, expected):
        from backend.service.utils.backend_router import resolve_backend_name

        assert resolve_backend_name(platform) == expected

    @pytest.mark.parametrize("platform", [Platform.WIN95, Platform.WIN98, Platform.WINXP])
    def test_win9x_does_not_route_to_dosbox(self, platform):
        from backend.service.utils.backend_router import resolve_backend_name

        assert resolve_backend_name(platform) != BackendSlug.DOSBOX_X.value

    def test_resolve_raises_value_error_for_missing_platform_in_config(self, monkeypatch):
        import backend.service.utils.platforms_config as platforms_config_mod

        monkeypatch.setattr(platforms_config_mod, "_PLATFORMS_CACHE", {})
        from backend.service.utils.backend_router import resolve_backend_name

        with pytest.raises((ValueError, RuntimeError)):
            resolve_backend_name(Platform.DOS)


# ---------------------------------------------------------------------------
# Settings key invariants, get_settings_key must return correct key per slug
# ---------------------------------------------------------------------------


class TestSettingsKeyMapping:
    @pytest.mark.parametrize(
        "slug,expected_key",
        [
            ("dosbox-x", "DOSBOX_PATH"),
            ("86box", "BOX86_PATH"),
            ("duckstation", "DUCKSTATION_PATH"),
            ("pcsx2", "PCSX2_PATH"),
            ("xemu", "XEMU_PATH"),
            ("mesen", "MESEN_PATH"),
            ("project64", "PROJECT64_PATH"),
            ("flycast", "FLYCAST_PATH"),
        ],
    )
    def test_get_settings_key_returns_correct_key(self, slug, expected_key):
        from backend.service.utils.emulator_catalog import get_settings_key

        assert get_settings_key(slug) == expected_key

    def test_dosbox_x_uses_toml_settings_key_not_derived(self):
        from backend.service.utils.emulator_catalog import get_settings_key

        # Derived would give "DOSBOXX_PATH"; TOML override gives "DOSBOX_PATH"
        assert get_settings_key("dosbox-x") == "DOSBOX_PATH"

    def test_86box_uses_toml_settings_key_not_derived(self):
        from backend.service.utils.emulator_catalog import get_settings_key

        # Derived would give "86BOX_PATH"; TOML override gives "BOX86_PATH"
        assert get_settings_key("86box") == "BOX86_PATH"


# ---------------------------------------------------------------------------
# H9 fix, routing must not read or branch on accuracy_mode
# ---------------------------------------------------------------------------


class TestNoAccuracyMode:
    def test_routing_module_source_does_not_contain_accuracy_mode(self):
        import inspect
        import backend.service.utils.backend_router as router_mod

        assert "accuracy_mode" not in inspect.getsource(router_mod)

    @pytest.mark.parametrize("platform", [Platform.WIN95, Platform.WIN98, Platform.WINXP])
    def test_win9x_routes_to_86box_with_no_accuracy_mode_context(self, platform):
        from backend.service.utils.backend_router import resolve_backend_name

        assert resolve_backend_name(platform) == BackendSlug.BOX86.value


# ---------------------------------------------------------------------------
# dispatch, data-driven routing to the correct backend module
# ---------------------------------------------------------------------------


def _fake_backend(label: str) -> MagicMock:
    mod = MagicMock(name=label)
    mod.launch = MagicMock(name=f"{label}.launch", return_value=(MagicMock(), MagicMock()))
    return mod


class TestDispatch:
    @pytest.mark.parametrize("platform,slug,module_path", _DISPATCH_CASES, ids=_DISPATCH_IDS)
    def test_dispatch_routes_to_correct_module(self, platform, slug, module_path, monkeypatch):
        from backend.service.launch.launch_spec import LaunchSpec
        from backend.service.utils.backend_router import dispatch

        fake = _fake_backend(module_path)
        monkeypatch.setitem(sys.modules, module_path, fake)

        spec = LaunchSpec(slug=slug, platform=platform.value)
        dispatch(spec)
        fake.launch.assert_called_once_with(spec)

    def test_dispatch_raises_value_error_for_unknown_slug(self):
        from backend.service.launch.launch_spec import LaunchSpec
        from backend.service.utils.backend_router import dispatch

        spec = LaunchSpec(slug="ghost_backend", platform="dos")
        with pytest.raises(ValueError, match="Unknown backend slug"):
            dispatch(spec)

    def test_dispatch_surfaces_import_error_clearly(self, monkeypatch):
        from backend.service.launch.launch_spec import LaunchSpec
        import backend.service.utils.backend_router as router_mod
        import importlib as _importlib

        original_import_module = _importlib.import_module

        def failing_import(name):
            if name == "backend.service.backends.dosbox":
                raise ImportError("dosbox module unavailable in test")
            return original_import_module(name)

        monkeypatch.setattr(router_mod.importlib, "import_module", failing_import)

        # Also remove from cache so the patched import is actually called.
        monkeypatch.delitem(sys.modules, "backend.service.backends.dosbox", raising=False)

        spec = LaunchSpec(slug="dosbox-x", platform="dos")
        with pytest.raises(ImportError, match="could not be imported"):
            router_mod.dispatch(spec)

    def test_flycast_is_reachable_via_dispatch(self, monkeypatch):
        """Flycast was previously unreachable due to missing settings entry."""
        from backend.service.launch.launch_spec import LaunchSpec
        from backend.service.utils.backend_router import dispatch

        fake = _fake_backend("backend.service.backends.flycast")
        monkeypatch.setitem(sys.modules, "backend.service.backends.flycast", fake)

        spec = LaunchSpec(slug=BackendSlug.FLYCAST.value, platform=Platform.DREAMCAST.value)
        dispatch(spec)
        fake.launch.assert_called_once_with(spec)

    def test_win95_routes_to_86box_via_dispatch(self, monkeypatch):
        from backend.service.launch.launch_spec import LaunchSpec
        from backend.service.utils.backend_router import dispatch, resolve_backend_name

        slug = resolve_backend_name(Platform.WIN95)
        fake_box86 = _fake_backend("backend.service.backends.box86")
        monkeypatch.setitem(sys.modules, "backend.service.backends.box86", fake_box86)

        spec = LaunchSpec(slug=slug, platform=Platform.WIN95.value)
        dispatch(spec)
        fake_box86.launch.assert_called_once_with(spec)


# ---------------------------------------------------------------------------
# get_executable_path, correct catalog slug resolved per platform
# get_install_path is mocked so no installed emulators are required.
# ---------------------------------------------------------------------------


class TestGetExecutablePath:
    @pytest.mark.parametrize(
        "platform,expected_catalog_slug",
        _EXEC_CASES,
        ids=_EXEC_IDS,
    )
    def test_returns_correct_path_for_platform(self, platform, expected_catalog_slug, monkeypatch, tmp_path):
        import backend.service.utils.emulator_catalog as catalog_mod

        fake_exe = tmp_path / f"{expected_catalog_slug}.exe"
        fake_exe.touch()
        monkeypatch.setattr(
            catalog_mod, "get_install_path", lambda slug: fake_exe if slug == expected_catalog_slug else None
        )
        import backend.service.utils.backend_router as router_mod

        path = router_mod.get_executable_path(platform)
        assert path == str(fake_exe)
