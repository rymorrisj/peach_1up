"""Tests for backend/service/utils/env_secrets.py's real read/write path.

Every existing caller-side test mocks get_env_secret/set_env_secret out, so
the actual atomic-write implementation (persists PIN_PEPPER and third-party
API keys to .env) had no coverage. These tests exercise the real
implementation against a tmp_path .env file, never the real project .env.

Isolation notes:
  - _env_path() is monkeypatched to a tmp_path file, so the real .env is
    never opened.
  - _dotenv_loaded is a module-level, process-lifetime cache; monkeypatched
    back to False for each test so a test observes only its own tmp_path
    file, and restored on teardown.
  - set_env_secret/get_env_secret also read/write the real process
    os.environ for each key directly, not just the file. Every key in
    _ENV_KEYS is monkeypatch.delenv'd (raising=False) at the start of each
    test so a value written by one test can never leak into the next test
    or file: monkeypatch restores whatever os.environ held for that key
    before the test, once at teardown, regardless of what env_secrets.py
    wrote to it in between.
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


class TestSetEnvSecretFailedWrite:
    def test_failed_replace_leaves_original_file_and_no_temp_file(self, isolated_env, monkeypatch):
        """Injection point: os.replace, the atomic-rename step. This is the
        real internal write mechanism the docstring calls out ('Atomic via
        temp file + rename'), not an internal detail invented for the test."""
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

        # Force get_env_secret to actually reload from the .env file rather
        # than short-circuiting on the in-process os.environ value
        # set_env_secret also wrote, so this exercises the real read path.
        monkeypatch.delenv("IGDB_CLIENT_ID", raising=False)
        monkeypatch.setattr(env_secrets_mod, "_dotenv_loaded", False)

        result = env_secrets_mod.get_env_secret("IGDB_CLIENT_ID")

        assert result == "abc-123-def"
