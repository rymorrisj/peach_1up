"""Tests for backend/service/utils/ini_writer.py.

set_ini_key is a hand-rolled, line-based, comment-preserving INI editor, and
it is what the network-isolation writes (console.py's PCSX2 [DEV9/Eth]
EthEnable, flycast.py's [network] Enable/GGPO, see test_network_isolation.py)
and the GameList.RecursivePaths write depend on to not corrupt an emulator's
hand-edited config file. Its exact output text is asserted, since preserving
the rest of the file byte for byte is the whole point of it.

patch_ini and write_ini are the configparser-based pair, used for configs the
project owns outright (86Box). They rewrite the file and drop comments.
"""

import configparser

import pytest


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


class TestPatchIni:
    def test_remove_sections_runs_before_edits_are_applied(self, tmp_path):
        """A section named in both remove_sections and edits ends up holding
        only the edited keys, never the dropped file's leftovers."""
        from backend.service.utils.ini_writer import patch_ini
        ini_path = tmp_path / "86box.cfg"
        ini_path.write_text(
            "[Machine]\nmachine = old\nstale_key = 1\n\n[Video]\ngfxcard = vga\n",
            encoding="utf-8",
        )

        patch_ini(ini_path, {"Machine": {"machine": "bf6"}}, remove_sections=["Machine"])

        parser = configparser.RawConfigParser()
        parser.optionxform = str
        parser.read(str(ini_path), encoding="utf-8")
        assert parser.get("Machine", "machine") == "bf6"
        assert not parser.has_option("Machine", "stale_key")
        assert parser.get("Video", "gfxcard") == "vga"

    def test_bom_written_by_another_tool_is_consumed_not_duplicated(self, tmp_path):
        """86Box and other tools write a UTF-8 BOM. patch_ini reads utf-8-sig
        so the first section header stays parseable, and write_ini emits plain
        utf-8, so the BOM is consumed rather than accumulating on each edit."""
        from backend.service.utils.ini_writer import patch_ini
        ini_path = tmp_path / "86box.cfg"
        ini_path.write_bytes("\ufeff[General]\nvid_resize = 0\n".encode("utf-8"))

        patch_ini(ini_path, {"General": {"vid_resize": "1"}})

        text = ini_path.read_text(encoding="utf-8")
        assert not text.startswith("\ufeff")
        assert text.count("[General]") == 1
        assert "vid_resize = 1" in text


class TestWriteIni:
    def test_failed_write_removes_the_temp_file_and_leaves_the_original(self, tmp_path, monkeypatch):
        """Documented guarantee: a failed atomic write must not leave a .tmp
        sibling behind or a half-written config in place of the real one."""
        import os as os_mod
        from backend.service.utils.ini_writer import write_ini
        ini_path = tmp_path / "86box.cfg"
        original = "[General]\nvid_resize = 0\n"
        ini_path.write_text(original, encoding="utf-8")

        parser = configparser.RawConfigParser()
        parser.optionxform = str
        parser.add_section("General")
        parser.set("General", "vid_resize", "1")

        def _raise_replace(*args, **kwargs):
            raise OSError("simulated disk failure")
        monkeypatch.setattr(os_mod, "replace", _raise_replace)

        with pytest.raises(OSError, match="simulated disk failure"):
            write_ini(ini_path, parser)

        assert ini_path.read_text(encoding="utf-8") == original
        assert list(tmp_path.iterdir()) == [ini_path]
