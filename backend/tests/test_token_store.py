"""Tests for backend.core.token_store.

Covers create_token, resolve_token, revoke_token, and cleanup_expired_tokens
against an in-memory SQLite session.
"""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def mem_session():
    from sqlmodel import SQLModel, Session, create_engine
    import backend.models  # noqa: F401 — registers all table models with SQLModel.metadata
    import backend.models.auth_token  # noqa: F401 — registers AuthToken with SQLModel.metadata

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def user(mem_session):
    from backend.models.user import User

    u = User(name="Test User", is_owner=True, is_admin=True)
    mem_session.add(u)
    mem_session.commit()
    mem_session.refresh(u)
    return u


class TestCreateToken:
    def test_sets_expires_at_around_30_days_out(self, mem_session, user):
        from backend.core.token_store import create_token
        from backend.models.auth_token import AuthToken

        token_str = create_token(mem_session, user.id, session_expiry_minutes=30 * 24 * 60)

        row = mem_session.query(AuthToken).filter(AuthToken.token == token_str).first()
        assert row is not None
        assert row.revoked is False

        expected = datetime.now(timezone.utc) + timedelta(days=30)
        delta = abs((row.expires_at.replace(tzinfo=timezone.utc) - expected).total_seconds())
        assert delta < 60


class TestResolveToken:
    def test_valid_unexpired_token_returns_user(self, mem_session, user):
        from backend.core.token_store import create_token, resolve_token

        token_str = create_token(mem_session, user.id, session_expiry_minutes=30)
        resolved = resolve_token(mem_session, token_str)

        assert resolved is not None
        assert resolved.id == user.id

    def test_expired_token_returns_none(self, mem_session, user):
        from backend.core.token_store import resolve_token
        from backend.models.auth_token import AuthToken

        row = AuthToken(
            token="expired-token",
            user_id=user.id,
            issued_at=datetime.now(timezone.utc) - timedelta(days=2),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            revoked=False,
        )
        mem_session.add(row)
        mem_session.commit()

        assert resolve_token(mem_session, "expired-token") is None

    def test_revoked_token_returns_none(self, mem_session, user):
        from backend.core.token_store import create_token, resolve_token, revoke_token

        token_str = create_token(mem_session, user.id, session_expiry_minutes=30)
        revoke_token(mem_session, token_str)

        assert resolve_token(mem_session, token_str) is None

    def test_nonexistent_token_returns_none(self, mem_session):
        from backend.core.token_store import resolve_token

        assert resolve_token(mem_session, "does-not-exist") is None


class TestRevokeToken:
    def test_sets_revoked_flag(self, mem_session, user):
        from backend.core.token_store import create_token, revoke_token
        from backend.models.auth_token import AuthToken

        token_str = create_token(mem_session, user.id, session_expiry_minutes=30)
        revoke_token(mem_session, token_str)

        row = mem_session.query(AuthToken).filter(AuthToken.token == token_str).first()
        assert row.revoked is True

    def test_subsequent_resolve_returns_none(self, mem_session, user):
        from backend.core.token_store import create_token, resolve_token, revoke_token

        token_str = create_token(mem_session, user.id, session_expiry_minutes=30)
        revoke_token(mem_session, token_str)

        assert resolve_token(mem_session, token_str) is None


class TestCleanupExpiredTokens:
    def test_deletes_expired_rows_keeps_valid_rows(self, mem_session, user):
        from backend.core.token_store import cleanup_expired_tokens
        from backend.models.auth_token import AuthToken

        expired = AuthToken(
            token="expired-token",
            user_id=user.id,
            issued_at=datetime.now(timezone.utc) - timedelta(days=40),
            expires_at=datetime.now(timezone.utc) - timedelta(days=10),
            revoked=False,
        )
        valid = AuthToken(
            token="valid-token",
            user_id=user.id,
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=10),
            revoked=False,
        )
        mem_session.add(expired)
        mem_session.add(valid)
        mem_session.commit()

        cleanup_expired_tokens(mem_session)

        remaining = {row.token for row in mem_session.query(AuthToken).all()}
        assert "expired-token" not in remaining
        assert "valid-token" in remaining
