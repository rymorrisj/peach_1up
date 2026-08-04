import pytest


def test_load_catalog_returns_all_emulators():
    from backend.service.utils.emulator_catalog import load_catalog
    catalog = load_catalog()
    slugs = {e["slug"] for e in catalog}
    required = {
        "86box-roms", "duckstation", "pcsx2", "mesen",
        "86box", "flycast", "project64", "xemu", "dosbox-x",
    }
    assert required <= slugs


def test_is_installed_returns_false_when_binary_absent(monkeypatch):
    from backend.service.utils import emulator_catalog
    monkeypatch.setattr(emulator_catalog, "get_install_path", lambda slug: None)
    assert emulator_catalog.is_installed("dosbox-x") is False


def test_get_install_path_returns_correct_path(tmp_path, monkeypatch):
    from backend.service.utils import emulator_catalog
    monkeypatch.setattr(emulator_catalog, "_BASE_DIR", tmp_path)
    binary_path = tmp_path / "dosbox-x" / "dosbox-x.exe"
    binary_path.parent.mkdir(parents=True)
    binary_path.touch()

    path = emulator_catalog.get_install_path("dosbox-x")
    assert path == binary_path


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
        ("duckstation", ["-batch"]),
        ("pcsx2",       ["-nogui", "-batch"]),
        ("mesen",       []),
        ("project64",   []),
    ])
    def test_cli_args_prefix_declared_in_toml(self, slug, expected):
        from backend.service.utils.emulator_catalog import get_emulator
        entry = get_emulator(slug)
        assert entry.get("cli_args_prefix") == expected


# ---------------------------------------------------------------------------
# resolve_container_enabled
# ---------------------------------------------------------------------------

class TestResolveContainerEnabled:
    def test_override_true_wins_for_normal_slug(self, monkeypatch):
        from backend.service.utils import emulator_catalog
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: {"container_enabled": False})
        assert emulator_catalog.resolve_container_enabled("dosbox-x", True) is True

    def test_override_false_wins_for_normal_slug(self, monkeypatch):
        from backend.service.utils import emulator_catalog
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: {"container_enabled": True})
        assert emulator_catalog.resolve_container_enabled("dosbox-x", False) is False

    def test_none_override_falls_back_to_catalog_value(self, monkeypatch):
        from backend.service.utils import emulator_catalog
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: {"container_enabled": True})
        monkeypatch.setattr(emulator_catalog._settings, "get", lambda key, default=None: default)
        assert emulator_catalog.resolve_container_enabled("dosbox-x", None) is True

    def test_permanently_excluded_slug_rejects_true_override(self, monkeypatch):
        from backend.service.utils import emulator_catalog
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: {"container_permanently_excluded": True})
        assert emulator_catalog.resolve_container_enabled("xemu", True) is False

    def test_permanently_excluded_slug_ignores_none_override_too(self, monkeypatch):
        from backend.service.utils import emulator_catalog
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: {"container_permanently_excluded": True})
        assert emulator_catalog.resolve_container_enabled("xemu", None) is False

    def test_permanently_excluded_rejection_is_logged(self, monkeypatch, caplog):
        from backend.service.utils import emulator_catalog
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: {"container_permanently_excluded": True})
        with caplog.at_level("WARNING"):
            emulator_catalog.resolve_container_enabled("xemu", True)
        assert any("permanently excluded" in r.getMessage() for r in caplog.records)

    def test_permanently_excluded_false_override_does_not_log(self, monkeypatch, caplog):
        # override is falsy (False), so the warning branch (`if override:`) is not hit.
        from backend.service.utils import emulator_catalog
        monkeypatch.setattr(emulator_catalog, "get_emulator",
                            lambda slug: {"container_permanently_excluded": True})
        with caplog.at_level("WARNING"):
            emulator_catalog.resolve_container_enabled("xemu", False)
        assert not any("permanently excluded" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# build_media_broker_config
# ---------------------------------------------------------------------------

class TestBuildMediaBrokerConfig:
    def test_returns_none_when_container_disabled(self, tmp_path):
        from backend.service.utils.emulator_catalog import build_media_broker_config
        result = build_media_broker_config(
            "flycast", "flycast.exe", tmp_path / "game.chd", user_item_id=1, container_enabled=False)
        assert result is None

    def test_builds_grant_and_inherit_broker_files_when_enabled(self, tmp_path, monkeypatch):
        from backend.service.utils import emulator_catalog
        from backend.service.utils.platform.windows.sandbox.sandbox_config import SandboxConfig

        media_path = tmp_path / "media" / "game.chd"
        base_config = SandboxConfig(moniker="flycast", exe_path="flycast.exe")
        monkeypatch.setattr(emulator_catalog, "get_container_config",
                            lambda slug, exe_path, user_item_id=None: base_config)

        result = emulator_catalog.build_media_broker_config(
            "flycast", "flycast.exe", media_path, user_item_id=1, container_enabled=True)

        assert result is base_config
        assert len(result.broker_files) == 2
        grant, inherit = result.broker_files
        assert grant.path == str(media_path.parent)
        assert grant.access == "r"
        assert grant.mode == "grant"
        assert inherit.path == str(media_path)
        assert inherit.access == "r"
        assert inherit.mode == "inherit"
