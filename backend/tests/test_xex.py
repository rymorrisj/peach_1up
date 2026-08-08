import logging


class TestFindDefaultXex:
    def test_exact_default_xex_match(self, tmp_path):
        from backend.service.utils.detection.xex import find_default_xex
        target = tmp_path / "default.xex"
        target.write_bytes(b"")
        assert find_default_xex(tmp_path) == target

    def test_default_xex_match_is_case_insensitive(self, tmp_path):
        from backend.service.utils.detection.xex import find_default_xex
        target = tmp_path / "Default.XEX"
        target.write_bytes(b"")
        assert find_default_xex(tmp_path) == target

    def test_default_xex_preferred_over_other_xex_files(self, tmp_path):
        from backend.service.utils.detection.xex import find_default_xex
        default = tmp_path / "default.xex"
        default.write_bytes(b"")
        (tmp_path / "alpha.xex").write_bytes(b"")
        (tmp_path / "zeta.xex").write_bytes(b"")
        assert find_default_xex(tmp_path) == default

    def test_falls_back_to_alphabetically_first_when_no_default(self, tmp_path):
        from backend.service.utils.detection.xex import find_default_xex
        alpha = tmp_path / "alpha.xex"
        alpha.write_bytes(b"")
        (tmp_path / "zeta.xex").write_bytes(b"")
        assert find_default_xex(tmp_path) == alpha

    def test_fallback_tie_break_is_case_insensitive_alphabetical(self, tmp_path):
        from backend.service.utils.detection.xex import find_default_xex
        lower_first = tmp_path / "banana.xex"
        lower_first.write_bytes(b"")
        (tmp_path / "Apple.xex").write_bytes(b"")
        assert find_default_xex(tmp_path) == tmp_path / "Apple.xex"

    def test_fallback_logs_warning(self, tmp_path, caplog):
        from backend.service.utils.detection.xex import find_default_xex
        (tmp_path / "zeta.xex").write_bytes(b"")
        with caplog.at_level(logging.WARNING):
            find_default_xex(tmp_path)
        assert any("no default.xex found" in rec.message for rec in caplog.records)

    def test_none_when_no_xex_files(self, tmp_path):
        from backend.service.utils.detection.xex import find_default_xex
        (tmp_path / "readme.txt").write_bytes(b"")
        assert find_default_xex(tmp_path) is None

    def test_none_for_empty_folder(self, tmp_path):
        from backend.service.utils.detection.xex import find_default_xex
        assert find_default_xex(tmp_path) is None

    def test_none_on_nonexistent_folder(self, tmp_path):
        # folder.iterdir() raises OSError (FileNotFoundError) on a missing
        # path; find_default_xex catches it and returns None rather than
        # propagating, matching resolve_xex_target's own folder.is_dir()
        # short-circuit for the same case.
        from backend.service.utils.detection.xex import find_default_xex
        assert find_default_xex(tmp_path / "missing") is None

    def test_non_xex_files_ignored(self, tmp_path):
        from backend.service.utils.detection.xex import find_default_xex
        default = tmp_path / "default.xex"
        default.write_bytes(b"")
        (tmp_path / "readme.txt").write_bytes(b"")
        (tmp_path / "cover.png").write_bytes(b"")
        assert find_default_xex(tmp_path) == default

    def test_subdirectories_not_recursed(self, tmp_path):
        # find_default_xex scans folder.iterdir() only, one level deep.
        from backend.service.utils.detection.xex import find_default_xex
        nested = tmp_path / "nested"
        nested.mkdir()
        (nested / "default.xex").write_bytes(b"")
        assert find_default_xex(tmp_path) is None


class TestResolveXexTarget:
    def test_none_when_folder_is_not_a_directory(self, tmp_path):
        from backend.service.utils.detection.xex import resolve_xex_target
        f = tmp_path / "notafolder.xex"
        f.write_bytes(b"")
        assert resolve_xex_target(f) is None

    def test_none_when_folder_does_not_exist(self, tmp_path):
        from backend.service.utils.detection.xex import resolve_xex_target
        assert resolve_xex_target(tmp_path / "missing") is None

    def test_resolves_with_default_xex(self, tmp_path):
        from backend.service.utils.detection.xex import resolve_xex_target
        default = tmp_path / "default.xex"
        default.write_bytes(b"")

        target = resolve_xex_target(tmp_path)

        assert target is not None
        assert target.kind == "xex_folder"
        # detect_path and launch_path are the same file for xex_folder,
        # unlike PS3's folder-as-launch-target shapes.
        assert target.detect_path == default
        assert target.launch_path == default
        assert target.era == "xbox360"
        assert target.requires_install is False
        assert target.license_files == ()

    def test_resolves_via_fallback_when_no_default_xex(self, tmp_path):
        from backend.service.utils.detection.xex import resolve_xex_target
        alpha = tmp_path / "alpha.xex"
        alpha.write_bytes(b"")
        (tmp_path / "zeta.xex").write_bytes(b"")

        target = resolve_xex_target(tmp_path)

        assert target is not None
        assert target.detect_path == alpha

    def test_none_for_empty_folder(self, tmp_path):
        from backend.service.utils.detection.xex import resolve_xex_target
        assert resolve_xex_target(tmp_path) is None

    def test_none_for_malformed_folder_with_unrelated_contents(self, tmp_path):
        from backend.service.utils.detection.xex import resolve_xex_target
        (tmp_path / "readme.txt").write_bytes(b"")
        (tmp_path / "cover.png").write_bytes(b"")
        assert resolve_xex_target(tmp_path) is None
