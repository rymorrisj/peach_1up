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


# ---------------------------------------------------------------------------
# ensure_portable_mode
# ---------------------------------------------------------------------------

class TestEnsurePortableMode:
    def test_creates_sentinel_when_declared(self, tmp_path, monkeypatch):
        from backend.service.utils import emulator_catalog
        exe = tmp_path / "duckstation-qt-x64-ReleaseLTCG.exe"
        exe.touch()
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: {"portable_sentinel": "portable.txt"})
        emulator_catalog.ensure_portable_mode("duckstation", exe)
        assert (tmp_path / "portable.txt").exists()

    def test_skips_when_sentinel_is_empty_string(self, tmp_path, monkeypatch):
        from backend.service.utils import emulator_catalog
        exe = tmp_path / "Mesen.exe"
        exe.touch()
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: {"portable_sentinel": ""})
        emulator_catalog.ensure_portable_mode("mesen", exe)
        assert list(tmp_path.iterdir()) == [exe]

    def test_idempotent_when_sentinel_already_exists(self, tmp_path, monkeypatch):
        from backend.service.utils import emulator_catalog
        exe = tmp_path / "pcsx2-qt.exe"
        exe.touch()
        sentinel = tmp_path / "portable.txt"
        sentinel.write_text("existing")
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: {"portable_sentinel": "portable.txt"})
        emulator_catalog.ensure_portable_mode("pcsx2", exe)
        assert sentinel.read_text() == "existing"

    def test_silent_for_unknown_slug(self, tmp_path):
        from backend.service.utils import emulator_catalog
        exe = tmp_path / "unknown.exe"
        exe.touch()
        emulator_catalog.ensure_portable_mode("no-such-slug", exe)


# ---------------------------------------------------------------------------
# validate_bios_from_descriptor
# ---------------------------------------------------------------------------

class TestValidateBiosFromDescriptor:
    def _make_entry(self, bios_path: str, required: bool = True) -> dict:
        return {
            "dependencies": [{
                "bios_path": bios_path,
                "display_name": "Test BIOS",
                "required": required,
            }]
        }

    def test_raises_when_bios_directory_missing(self, tmp_path, monkeypatch):
        from backend.service.utils import emulator_catalog
        monkeypatch.setattr(emulator_catalog, "get_base_path", lambda: tmp_path)
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: self._make_entry("library/system/bios/ps1"))
        with pytest.raises(FileNotFoundError, match="Test BIOS"):
            emulator_catalog.validate_bios_from_descriptor("duckstation")

    def test_raises_when_bios_directory_empty(self, tmp_path, monkeypatch):
        from backend.service.utils import emulator_catalog
        bios_dir = tmp_path / "library" / "system" / "bios" / "ps1"
        bios_dir.mkdir(parents=True)
        monkeypatch.setattr(emulator_catalog, "get_base_path", lambda: tmp_path)
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: self._make_entry("library/system/bios/ps1"))
        with pytest.raises(FileNotFoundError, match="empty"):
            emulator_catalog.validate_bios_from_descriptor("duckstation")

    def test_passes_when_bios_directory_populated(self, tmp_path, monkeypatch):
        from backend.service.utils import emulator_catalog
        bios_dir = tmp_path / "library" / "system" / "bios" / "ps1"
        bios_dir.mkdir(parents=True)
        (bios_dir / "scph1001.bin").write_bytes(b"\x00" * 16)
        monkeypatch.setattr(emulator_catalog, "get_base_path", lambda: tmp_path)
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: self._make_entry("library/system/bios/ps1"))
        emulator_catalog.validate_bios_from_descriptor("duckstation")

    def test_noop_for_slug_with_no_bios_dependencies(self, tmp_path, monkeypatch):
        from backend.service.utils import emulator_catalog
        monkeypatch.setattr(emulator_catalog, "get_base_path", lambda: tmp_path)
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: {"dependencies": []})
        emulator_catalog.validate_bios_from_descriptor("mesen")

    def test_optional_dependency_does_not_raise_when_missing(self, tmp_path, monkeypatch):
        from backend.service.utils import emulator_catalog
        monkeypatch.setattr(emulator_catalog, "get_base_path", lambda: tmp_path)
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: self._make_entry("library/system/bios/ps1", required=False))
        emulator_catalog.validate_bios_from_descriptor("duckstation")

    def test_rejects_path_escaping_project_root(self, tmp_path, monkeypatch):
        from backend.service.utils import emulator_catalog
        monkeypatch.setattr(emulator_catalog, "get_base_path", lambda: tmp_path)
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: self._make_entry("../../etc/passwd"))
        with pytest.raises(ValueError, match="outside the project root"):
            emulator_catalog.validate_bios_from_descriptor("duckstation")


# ---------------------------------------------------------------------------
# cli_args_prefix in TOML descriptors
# ---------------------------------------------------------------------------

class TestCliArgsPrefixInDescriptors:
    @pytest.mark.parametrize("slug,expected", [
        ("duckstation", ["-nogui"]),
        ("pcsx2",       ["--nogui"]),
        ("mesen",       []),
        ("project64",   []),
    ])
    def test_cli_args_prefix_declared_in_toml(self, slug, expected):
        from backend.service.utils.emulator_catalog import get_emulator
        entry = get_emulator(slug)
        assert entry.get("cli_args_prefix") == expected
