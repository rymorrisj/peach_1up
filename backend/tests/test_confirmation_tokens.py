"""Tests for backend.service.utils.confirmation_tokens.

The module's public API is `issue(resource, resource_id, action)` and
`consume(token, resource, resource_id, action)` — there is no
create_confirmation_token / consume_confirmation_token wrapper.
"""

import time

import pytest


@pytest.fixture(autouse=True)
def _clear_token_store():
    import backend.service.utils.confirmation_tokens as mod
    with mod._lock:
        mod._tokens.clear()
    yield
    with mod._lock:
        mod._tokens.clear()


class TestConfirmationTokens:
    def test_valid_token_consumed_successfully_returns_true(self):
        from backend.service.utils.confirmation_tokens import issue, consume

        token = issue("library", 1, "delete")
        assert consume(token, "library", 1, "delete") is True

    def test_token_used_twice_second_consume_returns_false(self):
        from backend.service.utils.confirmation_tokens import issue, consume

        token = issue("library", 1, "delete")
        assert consume(token, "library", 1, "delete") is True
        assert consume(token, "library", 1, "delete") is False

    def test_expired_token_returns_false(self, monkeypatch):
        from backend.service.utils.confirmation_tokens import issue, consume
        import backend.service.utils.confirmation_tokens as mod

        token = issue("library", 1, "delete")
        # Advance monotonic clock past the 60s TTL.
        real_monotonic = time.monotonic()
        monkeypatch.setattr(mod.time, "monotonic", lambda: real_monotonic + mod.TOKEN_TTL + 1)

        assert consume(token, "library", 1, "delete") is False

    def test_nonexistent_token_returns_false(self):
        from backend.service.utils.confirmation_tokens import consume

        assert consume("does-not-exist", "library", 1, "delete") is False
