"""Tests for backend routing — era → backend mapping and routing invariants."""

import functools
import inspect
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

# Console backends now dispatch through console.py; others keep per-module paths.
_LAUNCH_FN_CASES = [
    (Era.DOS,   "backend.service.backends.dosbox"),
    (Era.WIN31, "backend.service.backends.dosbox"),
    (Era.WIN95, "backend.service.backends.box86"),
    (Era.WIN98, "backend.service.backends.box86"),
    (Era.WINXP, "backend.service.backends.box86"),
    (Era.PS1,   "backend.service.backends.console"),
    (Era.PS2,   "backend.service.backends.console"),
    (Era.XBOX,  "backend.service.backends.xemu"),
    (Era.NES,   "backend.service.backends.console"),
    (Era.N64,   "backend.service.backends.console"),
    (Era.DREAMCAST, "backend.service.backends.flycast"),
]

_LAUNCH_FN_IDS = ["dos", "win31", "win95", "win98", "winxp",
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
    def test_win9x_does_not_route_to_virtualbox(self, era):
        from backend.service.utils.backend_router import resolve_backend_name
        assert resolve_backend_name(era) != BackendSlug.VIRTUALBOX.value

    @pytest.mark.parametrize("era", [Era.WIN95, Era.WIN98, Era.WINXP])
    def test_win9x_does_not_route_to_dosbox(self, era):
        from backend.service.utils.backend_router import resolve_backend_name
        assert resolve_backend_name(era) != BackendSlug.DOSBOX.value


# ---------------------------------------------------------------------------
# Settings key invariants — get_settings_key must return correct key per slug
# ---------------------------------------------------------------------------

class TestSettingsKeyMapping:
    @pytest.mark.parametrize("slug,expected_key", [
        ("dosbox-x",    "DOSBOX_PATH"),
        ("86box",       "BOX86_PATH"),
        ("virtualbox",  "VIRTUALBOX_PATH"),
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
        import backend.service.utils.backend_router as router_mod
        assert "accuracy_mode" not in inspect.getsource(router_mod)

    @pytest.mark.parametrize("era", [Era.WIN95, Era.WIN98, Era.WINXP])
    def test_win9x_routes_to_86box_with_no_accuracy_mode_context(self, era):
        from backend.service.utils.backend_router import resolve_backend_name
        assert resolve_backend_name(era) == BackendSlug.BOX86.value


# ---------------------------------------------------------------------------
# H3 fix — unknown era raises, does not silently misfire
# ---------------------------------------------------------------------------

class TestUnknownEraHandling:
    def test_launch_media_raises_value_error_for_unknown_era_string(self):
        from backend.service.utils.backend_router import launch_media
        with pytest.raises(ValueError, match="Unknown era"):
            launch_media("not_a_real_era", "/fake/game.iso")

    def test_get_launch_fn_raises_runtime_error_when_era_absent_from_config(self, monkeypatch):
        import backend.service.utils.emulator_catalog as catalog_mod
        monkeypatch.setattr(catalog_mod, "_ERAS_CONFIG_CACHE", {})
        import backend.service.utils.backend_router as router_mod
        with pytest.raises(RuntimeError):
            router_mod.get_launch_fn(Era.DOS)


# ---------------------------------------------------------------------------
# get_launch_fn — returns the correct launch callable per era
# Backend modules are stubbed in sys.modules so no real binaries are needed.
# ---------------------------------------------------------------------------

def _fake_backend(label: str) -> MagicMock:
    mod = MagicMock(name=label)
    mod.launch = MagicMock(name=f"{label}.launch")
    return mod


class TestGetLaunchFn:
    @pytest.mark.parametrize("era,module_path", _LAUNCH_FN_CASES, ids=_LAUNCH_FN_IDS)
    def test_returns_launch_callable_for_era(self, era, module_path, monkeypatch):
        fake = _fake_backend(module_path)
        monkeypatch.setitem(sys.modules, module_path, fake)
        import backend.service.utils.backend_router as router_mod
        fn = router_mod.get_launch_fn(era)
        if module_path == "backend.service.backends.console":
            # Console backends return a partial wrapping console.launch
            assert isinstance(fn, functools.partial)
            assert fn.func is fake.launch
        else:
            assert fn is fake.launch

    def test_win95_returns_86box_launch_not_virtualbox(self, monkeypatch):
        fake_vbox = _fake_backend("virtualbox")
        fake_box86 = _fake_backend("box86")
        monkeypatch.setitem(sys.modules, "backend.service.backends.virtualbox", fake_vbox)
        monkeypatch.setitem(sys.modules, "backend.service.backends.box86", fake_box86)
        import backend.service.utils.backend_router as router_mod
        fn = router_mod.get_launch_fn(Era.WIN95)
        assert fn is fake_box86.launch
        assert fn is not fake_vbox.launch

    def test_win98_returns_86box_launch_not_virtualbox(self, monkeypatch):
        fake_vbox = _fake_backend("virtualbox")
        fake_box86 = _fake_backend("box86")
        monkeypatch.setitem(sys.modules, "backend.service.backends.virtualbox", fake_vbox)
        monkeypatch.setitem(sys.modules, "backend.service.backends.box86", fake_box86)
        import backend.service.utils.backend_router as router_mod
        fn = router_mod.get_launch_fn(Era.WIN98)
        assert fn is fake_box86.launch
        assert fn is not fake_vbox.launch


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
