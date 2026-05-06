import pytest
from pathlib import Path


def test_load_catalog_returns_all_emulators():
    from backend.service.utils.emulator_catalog import load_catalog
    catalog = load_catalog()
    assert len(catalog) == 8
    slugs = {e["slug"] for e in catalog}
    assert "dosbox-x" in slugs
    assert "virtualbox" in slugs


def test_is_installed_returns_false_when_binary_absent():
    from backend.service.utils.emulator_catalog import is_installed
    assert is_installed("dosbox-x") is False


def test_get_install_path_returns_correct_path():
    from backend.service.utils.emulator_catalog import get_install_path
    path = get_install_path("dosbox-x")
    assert isinstance(path, Path)
    assert path.parts[-2] == "dosbox-x"
    assert path.parts[-1] == "dosbox-x"


def test_get_emulator_raises_for_unknown_slug():
    from backend.service.utils.emulator_catalog import get_emulator
    with pytest.raises(ValueError, match="Unknown emulator slug"):
        get_emulator("nonexistent-slug-xyz")
