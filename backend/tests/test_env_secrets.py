"""Tests for backend/service/utils/env_secrets.py's real read/write path.

Runs the real implementation, the atomic write that persists PIN_PEPPER and
the third-party API keys, against a tmp_path .env. Every other test file
mocks get_env_secret/set_env_secret out.

Isolation, all handled by the isolated_env fixture:
  - _env_path() points at tmp_path, so the real project .env is never opened.
  - _dotenv_loaded is a process-lifetime cache, reset to False per test.
  - set_env_secret/get_env_secret also touch the real os.environ, so every
    _ENV_KEYS entry is delenv'd up front and monkeypatch restores it at
    teardown, keeping a written value out of the next test.
"""

import pytest


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    import backend.service.utils.env_secrets as env_secrets_mod

    env_file = tmp_path / ".env"
    monkeypatch.setattr(env_secrets_mod, "_env_path", lambda: env_file)
    monkeypatch.setattr(env_secrets_mod, "_dotenv_loaded", False)

    for key in env_secrets_mod._ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    return env_file, env_secrets_mod


class TestSetEnvSecretExistingKey:
    def test_rewrites_only_that_line(self, isolated_env):
        env_file, env_secrets_mod = isolated_env
        original = (
            "# a comment\n"
            "PIN_PEPPER=old_pepper\n"
            "\n"
            "THEGAMESDB_API_KEY=abc123\n"
        )
        env_file.write_text(original, encoding="utf-8")

        env_secrets_mod.set_env_secret("PIN_PEPPER", "new_pepper")

        expected = (
            "# a comment\n"
            "PIN_PEPPER=new_pepper\n"
            "\n"
            "THEGAMESDB_API_KEY=abc123\n"
        )
        assert env_file.read_text(encoding="utf-8") == expected


class TestSetEnvSecretNewKey:
    def test_appends_without_disturbing_existing_content(self, isolated_env):
        env_file, env_secrets_mod = isolated_env
        env_file.write_text("PIN_PEPPER=old_pepper\n", encoding="utf-8")

        env_secrets_mod.set_env_secret("AI_API_KEY", "new_key_value")

        expected = "PIN_PEPPER=old_pepper\nAI_API_KEY=new_key_value\n"
        assert env_file.read_text(encoding="utf-8") == expected


class TestSetEnvSecretDisallowedKey:
    def test_raises_value_error_before_any_write(self, isolated_env):
        env_file, env_secrets_mod = isolated_env
        original = "PIN_PEPPER=old_pepper\n"
        env_file.write_text(original, encoding="utf-8")

        before = env_file.read_text(encoding="utf-8")
        with pytest.raises(ValueError, match="not a recognised"):
            env_secrets_mod.set_env_secret("NOT_A_REAL_SECRET_KEY", "x")
        after = env_file.read_text(encoding="utf-8")

        assert after == before


# INTEGRATION TEST NEEDED: set_env_secret is read-modify-write with no lock,
# so two concurrent settings PATCHes writing different keys can have the
# second rename clobber the first key's line. Needs real concurrent requests
# against a live app to verify both keys survive (or to confirm the race).


class TestSetEnvSecretFailedWrite:
    def test_failed_replace_leaves_original_file_and_no_temp_file(self, isolated_env, monkeypatch):
        """Fails the atomic-rename step itself (os.replace), the mechanism the
        docstring's "Atomic via temp file + rename" guarantee rests on."""
        import os as os_mod
        env_file, env_secrets_mod = isolated_env
        original = "PIN_PEPPER=old_pepper\n"
        env_file.write_text(original, encoding="utf-8")

        def _raise_replace(*args, **kwargs):
            raise OSError("simulated disk failure")
        monkeypatch.setattr(os_mod, "replace", _raise_replace)

        with pytest.raises(OSError, match="simulated disk failure"):
            env_secrets_mod.set_env_secret("PIN_PEPPER", "new_pepper")

        assert env_file.read_text(encoding="utf-8") == original
        leftover = [p for p in env_file.parent.iterdir() if p.name != env_file.name]
        assert leftover == []


class TestGetEnvSecretRoundTrip:
    def test_get_after_set_reads_the_persisted_file_value(self, isolated_env, monkeypatch):
        env_file, env_secrets_mod = isolated_env

        env_secrets_mod.set_env_secret("IGDB_CLIENT_ID", "abc-123-def")

        # Clear the os.environ value set_env_secret also wrote, so the read
        # comes from the file rather than short-circuiting in-process.
        monkeypatch.delenv("IGDB_CLIENT_ID", raising=False)
        monkeypatch.setattr(env_secrets_mod, "_dotenv_loaded", False)

        result = env_secrets_mod.get_env_secret("IGDB_CLIENT_ID")

        assert result == "abc-123-def"


class TestGetEnvSecretDisallowedKey:
    def test_raises_value_error_naming_the_key(self, isolated_env):
        """_check_key gates the read side too, not just set_env_secret."""
        _env_file, env_secrets_mod = isolated_env
        with pytest.raises(ValueError, match="not a recognised"):
            env_secrets_mod.get_env_secret("NOT_A_REAL_SECRET_KEY")


class TestGetEnvSecretUnset:
    def test_allowed_key_with_no_value_returns_empty_string(self, isolated_env):
        """Never None: callers (pin_hashing.get_pin_pepper, the TheGamesDB key
        lookup) treat the return as a str unconditionally."""
        env_file, env_secrets_mod = isolated_env
        env_file.write_text("PIN_PEPPER=set\n", encoding="utf-8")

        assert env_secrets_mod.get_env_secret("AI_API_KEY") == ""


class TestSetEnvSecretUpdatesProcessEnvironment:
    def test_value_is_visible_in_os_environ_without_a_reload(self, isolated_env):
        """Documented: set_env_secret persists to .env *and* the current
        process environment, so a same-process reader sees it immediately."""
        import os
        _env_file, env_secrets_mod = isolated_env

        env_secrets_mod.set_env_secret("THEGAMESDB_API_KEY", "live-key")

        assert os.environ["THEGAMESDB_API_KEY"] == "live-key"
