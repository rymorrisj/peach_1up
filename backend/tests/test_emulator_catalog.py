import pytest
from pathlib import Path


def test_load_catalog_returns_all_emulators():
    from backend.service.utils.emulator_catalog import load_catalog
    catalog = load_catalog()
    assert len(catalog) == 10
    slugs = {e["slug"] for e in catalog}
    assert "dosbox-x" in slugs
    assert "flycast" in slugs


def test_is_installed_returns_false_when_binary_absent(monkeypatch):
    from backend.service.utils import emulator_catalog
    monkeypatch.setattr(emulator_catalog, "get_install_path", lambda slug: None)
    assert emulator_catalog.is_installed("dosbox-x") is False


def test_get_install_path_returns_correct_path():
    from backend.service.utils.emulator_catalog import get_install_path
    path = get_install_path("dosbox-x")
    assert isinstance(path, Path)
    assert path.parts[-2] == "dosbox-x"
    assert path.stem == "dosbox-x"


def test_get_emulator_raises_for_unknown_slug():
    from backend.service.utils.emulator_catalog import get_emulator
    with pytest.raises(ValueError, match="Unknown emulator slug"):
        get_emulator("nonexistent-slug-xyz")
