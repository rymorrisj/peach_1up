"""Tests for backend routing — era → backend mapping and routing invariants."""

import sys
from unittest.mock import MagicMock

import pytest

from backend.constants_generated import BackendSlug, Era


# ---------------------------------------------------------------------------
# Shared parametrize data
# ---------------------------------------------------------------------------

_ROUTE_CASES = [
    (Era.DOS,   BackendSlug.DOSBOX.value),
    (Era.WIN31, BackendSlug.DOSBOX.value),
    (Era.WIN95, BackendSlug.BOX86.value),
    (Era.WIN98, BackendSlug.BOX86.value),
    (Era.WINXP, BackendSlug.BOX86.value),
    (Era.PS1,   BackendSlug.DUCKSTATION.value),
    (Era.PS2,   BackendSlug.PCSX2.value),
    (Era.XBOX,  BackendSlug.XEMU.value),
    (Era.NES,       BackendSlug.MESEN.value),
    (Era.N64,       BackendSlug.PROJECT64.value),
    (Era.DREAMCAST, BackendSlug.FLYCAST.value),
]

_ROUTE_IDS = ["dos", "win31", "win95", "win98", "winxp",
              "ps1", "ps2", "xbox", "nes", "n64", "dreamcast"]

_EXEC_CASES = [
    (Era.DOS,   "DOSBOX_PATH",      "dosbox"),
    (Era.WIN31, "DOSBOX_PATH",      "dosbox"),
    (Era.WIN95, "BOX86_PATH",       "box86"),
    (Era.WIN98, "BOX86_PATH",       "box86"),
    (Era.WINXP, "BOX86_PATH",       "box86"),
    (Era.PS1,   "DUCKSTATION_PATH", "duckstation"),
    (Era.PS2,   "PCSX2_PATH",       "pcsx2"),
    (Era.XBOX,  "XEMU_PATH",        "xemu"),
    (Era.NES,       "MESEN_PATH",       "mesen"),
    (Era.N64,       "PROJECT64_PATH",   "project64"),
    (Era.DREAMCAST, "FLYCAST_PATH",     "flycast"),
]

_EXEC_IDS = ["dos", "win31", "win95", "win98", "winxp",
             "ps1", "ps2", "xbox", "nes", "n64", "dreamcast"]

# Slug → module path for dispatch tests.
_DISPATCH_CASES = [
    (Era.DOS,   BackendSlug.DOSBOX.value,      "backend.service.backends.dosbox"),
    (Era.WIN31, BackendSlug.DOSBOX.value,      "backend.service.backends.dosbox"),
    (Era.WIN95, BackendSlug.BOX86.value,       "backend.service.backends.box86"),
    (Era.WIN98, BackendSlug.BOX86.value,       "backend.service.backends.box86"),
    (Era.WINXP, BackendSlug.BOX86.value,       "backend.service.backends.box86"),
    (Era.PS1,   BackendSlug.DUCKSTATION.value, "backend.service.backends.console"),
    (Era.PS2,   BackendSlug.PCSX2.value,       "backend.service.backends.console"),
    (Era.XBOX,  BackendSlug.XEMU.value,        "backend.service.backends.xemu"),
    (Era.NES,   BackendSlug.MESEN.value,       "backend.service.backends.console"),
    (Era.N64,   BackendSlug.PROJECT64.value,   "backend.service.backends.console"),
    (Era.DREAMCAST, BackendSlug.FLYCAST.value, "backend.service.backends.flycast"),
]

_DISPATCH_IDS = ["dos", "win31", "win95", "win98", "winxp",
                 "ps1", "ps2", "xbox", "nes", "n64", "dreamcast"]


# ---------------------------------------------------------------------------
# resolve_backend_name — complete era→backend string mapping
# ---------------------------------------------------------------------------

class TestResolveBackendName:
    @pytest.mark.parametrize("era,expected", _ROUTE_CASES, ids=_ROUTE_IDS)
    def test_era_routes_to_expected_backend(self, era, expected):
        from backend.service.utils.backend_router import resolve_backend_name
        assert resolve_backend_name(era) == expected

    @pytest.mark.parametrize("era", [Era.WIN95, Era.WIN98, Era.WINXP])
    def test_win9x_does_not_route_to_dosbox(self, era):
        from backend.service.utils.backend_router import resolve_backend_name
        assert resolve_backend_name(era) != BackendSlug.DOSBOX.value

    def test_resolve_raises_value_error_for_missing_era_in_config(self, monkeypatch):
        import backend.service.utils.emulator_catalog as catalog_mod
        monkeypatch.setattr(catalog_mod, "_ERAS_CONFIG_CACHE", {})
        from backend.service.utils.backend_router import resolve_backend_name
        with pytest.raises((ValueError, RuntimeError)):
            resolve_backend_name(Era.DOS)


# ---------------------------------------------------------------------------
# Settings key invariants — get_settings_key must return correct key per slug
# ---------------------------------------------------------------------------

class TestSettingsKeyMapping:
    @pytest.mark.parametrize("slug,expected_key", [
        ("dosbox-x",    "DOSBOX_PATH"),
        ("86box",       "BOX86_PATH"),
        ("duckstation", "DUCKSTATION_PATH"),
        ("pcsx2",       "PCSX2_PATH"),
        ("xemu",        "XEMU_PATH"),
        ("mesen",       "MESEN_PATH"),
        ("project64",   "PROJECT64_PATH"),
        ("flycast",     "FLYCAST_PATH"),
    ])
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
# H9 fix — routing must not read or branch on accuracy_mode
# ---------------------------------------------------------------------------

class TestNoAccuracyMode:
    def test_routing_module_source_does_not_contain_accuracy_mode(self):
        import inspect
        import backend.service.utils.backend_router as router_mod
        assert "accuracy_mode" not in inspect.getsource(router_mod)

    @pytest.mark.parametrize("era", [Era.WIN95, Era.WIN98, Era.WINXP])
    def test_win9x_routes_to_86box_with_no_accuracy_mode_context(self, era):
        from backend.service.utils.backend_router import resolve_backend_name
        assert resolve_backend_name(era) == BackendSlug.BOX86.value


# ---------------------------------------------------------------------------
# dispatch — data-driven routing to the correct backend module
# ---------------------------------------------------------------------------

def _fake_backend(label: str) -> MagicMock:
    mod = MagicMock(name=label)
    mod.launch = MagicMock(name=f"{label}.launch", return_value=(MagicMock(), MagicMock()))
    return mod


class TestDispatch:
    @pytest.mark.parametrize("era,slug,module_path", _DISPATCH_CASES, ids=_DISPATCH_IDS)
    def test_dispatch_routes_to_correct_module(self, era, slug, module_path, monkeypatch):
        from backend.service.launch.launch_spec import LaunchSpec
        from backend.service.utils.backend_router import dispatch

        fake = _fake_backend(module_path)
        monkeypatch.setitem(sys.modules, module_path, fake)

        spec = LaunchSpec(slug=slug, era=era.value)
        dispatch(spec)
        fake.launch.assert_called_once_with(spec)

    def test_dispatch_raises_value_error_for_unknown_slug(self):
        from backend.service.launch.launch_spec import LaunchSpec
        from backend.service.utils.backend_router import dispatch

        spec = LaunchSpec(slug="ghost_backend", era="dos")
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

        spec = LaunchSpec(slug="dosbox", era="dos")
        with pytest.raises(ImportError, match="could not be imported"):
            router_mod.dispatch(spec)

    def test_flycast_is_reachable_via_dispatch(self, monkeypatch):
        """Flycast was previously unreachable due to missing settings entry."""
        from backend.service.launch.launch_spec import LaunchSpec
        from backend.service.utils.backend_router import dispatch

        fake = _fake_backend("backend.service.backends.flycast")
        monkeypatch.setitem(sys.modules, "backend.service.backends.flycast", fake)

        spec = LaunchSpec(slug=BackendSlug.FLYCAST.value, era=Era.DREAMCAST.value)
        dispatch(spec)
        fake.launch.assert_called_once_with(spec)

    def test_win95_routes_to_86box_via_dispatch(self, monkeypatch):
        from backend.service.launch.launch_spec import LaunchSpec
        from backend.service.utils.backend_router import dispatch, resolve_backend_name

        slug = resolve_backend_name(Era.WIN95)
        fake_box86 = _fake_backend("backend.service.backends.box86")
        monkeypatch.setitem(sys.modules, "backend.service.backends.box86", fake_box86)

        spec = LaunchSpec(slug=slug, era=Era.WIN95.value)
        dispatch(spec)
        fake_box86.launch.assert_called_once_with(spec)


# ---------------------------------------------------------------------------
# get_executable_path — correct settings key and emulator key per era
# get_binary_path is mocked so no configured paths are required.
# ---------------------------------------------------------------------------

class TestGetExecutablePath:
    @pytest.mark.parametrize(
        "era,expected_settings_key,expected_emulator_key",
        _EXEC_CASES,
        ids=_EXEC_IDS,
    )
    def test_returns_correct_keys_for_era(
        self, era, expected_settings_key, expected_emulator_key, monkeypatch
    ):
        import backend.service.utils.backend_router as router_mod
        monkeypatch.setattr(
            router_mod, "get_binary_path", lambda key: f"/fake/{key}.exe"
        )
        path, settings_key = router_mod.get_executable_path(era)
        assert settings_key == expected_settings_key
        assert path == f"/fake/{expected_emulator_key}.exe"
