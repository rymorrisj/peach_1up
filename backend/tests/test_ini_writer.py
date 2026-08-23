"""Tests for backend/service/utils/ini_writer.py's set_ini_key.

set_ini_key is a hand-rolled, line-based, comment-preserving INI editor
(distinct from patch_ini, which rewrites via configparser and does not
preserve comments), and it is what every network-isolation write
(box86.py's [Network] net_type, console.py's PCSX2 [DEV9/Eth] EthEnable,
flycast.py's [network] Enable/GGPO, see test_network_isolation.py) and
GameList.RecursivePaths writes depend on to not corrupt an emulator's
existing hand-edited config file.

All expected outputs below were derived by tracing set_ini_key's actual
control flow line by line against each scenario, not assumed from its
docstring.
"""


class TestSetIniKeyExistingKey:
    def test_existing_key_mid_section_changes_only_that_line(self, tmp_path):
        from backend.service.utils.ini_writer import set_ini_key
        ini_path = tmp_path / "test.ini"
        original = (
            "[General]\n"
            "; a comment\n"
            "foo = 1\n"
            "bar = 2\n"
            "\n"
            "[Other]\n"
            "baz = 3\n"
        )
        ini_path.write_text(original, encoding="utf-8")

        set_ini_key(ini_path, "General", "foo", "99")

        expected = original.replace("foo = 1\n", "foo = 99\n")
        assert ini_path.read_text(encoding="utf-8") == expected


class TestSetIniKeyMissingKeyExistingSection:
    def test_missing_key_inserted_before_next_section_header(self, tmp_path):
        from backend.service.utils.ini_writer import set_ini_key
        ini_path = tmp_path / "test.ini"
        ini_path.write_text(
            "[General]\n"
            "foo = 1\n"
            "\n"
            "[Other]\n"
            "baz = 3\n",
            encoding="utf-8",
        )

        set_ini_key(ini_path, "General", "newkey", "v")

        expected = (
            "[General]\n"
            "foo = 1\n"
            "\n"
            "newkey = v\n"
            "[Other]\n"
            "baz = 3\n"
        )
        assert ini_path.read_text(encoding="utf-8") == expected


class TestSetIniKeyMissingSection:
    def test_missing_section_appended_with_blank_line_separator(self, tmp_path):
        """Matches the real else-branch behavior: a blank line is prepended
        to the new section only because it is folded into the same appended
        string as the section header, not written as a separate step."""
        from backend.service.utils.ini_writer import set_ini_key
        ini_path = tmp_path / "test.ini"
        ini_path.write_text("[Existing]\nfoo = 1\n", encoding="utf-8")

        set_ini_key(ini_path, "NewSection", "key", "value")

        expected = "[Existing]\nfoo = 1\n\n[NewSection]\nkey = value\n"
        assert ini_path.read_text(encoding="utf-8") == expected


class TestSetIniKeyIgnoresComments:
    def test_commented_out_key_is_untouched_and_real_key_added_then_updated(self, tmp_path):
        from backend.service.utils.ini_writer import set_ini_key
        ini_path = tmp_path / "test.ini"
        ini_path.write_text(
            "[General]\n"
            "; foo = old_commented\n"
            "bar = 1\n",
            encoding="utf-8",
        )

        set_ini_key(ini_path, "General", "foo", "99")
        after_add = ini_path.read_text(encoding="utf-8")
        assert after_add == "[General]\n; foo = old_commented\nbar = 1\nfoo = 99\n"

        set_ini_key(ini_path, "General", "foo", "100")
        after_update = ini_path.read_text(encoding="utf-8")
        assert after_update == "[General]\n; foo = old_commented\nbar = 1\nfoo = 100\n"


class TestSetIniKeyMissingFile:
    def test_creates_file_with_minimal_content(self, tmp_path):
        from backend.service.utils.ini_writer import set_ini_key
        ini_path = tmp_path / "new_subdir" / "test.ini"

        set_ini_key(ini_path, "Section", "key", "value")

        assert ini_path.read_text(encoding="utf-8") == "[Section]\nkey = value\n"
