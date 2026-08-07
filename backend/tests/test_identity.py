"""Tests for backend.core.identity: generate_identity_secret, mint_session_token,
hash_session_token, issue_session, clear_session, and validate_session.
"""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def mem_session():
    from sqlmodel import SQLModel, Session, create_engine
    import backend.models  # noqa: F401, registers all table models with SQLModel.metadata

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def user(mem_session):
    from backend.core.identity import generate_identity_secret
    from backend.models.user import UserItem

    u = UserItem(name="Test UserItem", is_owner=True, is_admin=True, identity_token_secret=generate_identity_secret())
    mem_session.add(u)
    mem_session.commit()
    mem_session.refresh(u)
    return u


class TestGenerateIdentitySecret:
    def test_distinct_per_call(self):
        from backend.core.identity import generate_identity_secret

        assert generate_identity_secret() != generate_identity_secret()


class TestMintSessionToken:
    def test_distinct_per_call(self):
        from backend.core.identity import generate_identity_secret, mint_session_token

        secret = generate_identity_secret()
        token1, _ = mint_session_token(secret)
        token2, _ = mint_session_token(secret)
        assert token1 != token2

    def test_returns_hex_digest_and_issued_at(self):
        from backend.core.identity import generate_identity_secret, mint_session_token

        secret = generate_identity_secret()
        token, issued_at = mint_session_token(secret)
        assert isinstance(token, str)
        assert len(token) == 64  # sha256 hexdigest
        assert isinstance(issued_at, datetime)


class TestHashSessionToken:
    def test_deterministic(self):
        from backend.core.identity import hash_session_token

        assert hash_session_token("abc") == hash_session_token("abc")

    def test_differs_for_different_input(self):
        from backend.core.identity import hash_session_token

        assert hash_session_token("abc") != hash_session_token("xyz")


class TestIssueSession:
    def test_sets_hash_and_no_expiry_when_ttl_none(self, mem_session, user):
        from backend.core.identity import hash_session_token, issue_session

        token, expires_at = issue_session(mem_session, user)

        assert user.session_token_hash == hash_session_token(token)
        assert expires_at is None
        assert user.session_token_expires_at is None

    def test_sets_expiry_when_ttl_set(self, mem_session, user):
        from backend.core.identity import issue_session

        user.session_token_ttl = 30
        mem_session.add(user)
        mem_session.commit()

        _token, expires_at = issue_session(mem_session, user)

        expected = datetime.now(timezone.utc) + timedelta(minutes=30)
        assert expires_at is not None
        delta = abs((expires_at.replace(tzinfo=timezone.utc) - expected).total_seconds())
        assert delta < 5

    def test_overwrites_previous_session(self, mem_session, user):
        from backend.core.identity import issue_session

        token1, _ = issue_session(mem_session, user)
        token2, _ = issue_session(mem_session, user)

        assert token1 != token2
        from backend.core.identity import hash_session_token
        assert user.session_token_hash == hash_session_token(token2)

    def test_backfills_missing_identity_secret(self, mem_session):
        from backend.core.identity import issue_session
        from backend.models.user import UserItem

        u = UserItem(name="NoSecret", is_owner=False)
        mem_session.add(u)
        mem_session.commit()
        mem_session.refresh(u)
        assert u.identity_token_secret is None

        issue_session(mem_session, u)

        assert u.identity_token_secret is not None


class TestClearSession:
    def test_nulls_hash_and_expiry(self, mem_session, user):
        from backend.core.identity import clear_session, issue_session

        issue_session(mem_session, user)
        clear_session(mem_session, user)

        assert user.session_token_hash is None
        assert user.session_token_expires_at is None


class TestValidateSession:
    def test_happy_path_returns_user(self, mem_session, user):
        from backend.core.identity import issue_session, validate_session

        token, _ = issue_session(mem_session, user)
        resolved = validate_session(mem_session, user.id, token)

        assert resolved is not None
        assert resolved.id == user.id

    def test_wrong_user_id_returns_none(self, mem_session, user):
        from backend.core.identity import issue_session, validate_session

        token, _ = issue_session(mem_session, user)
        resolved = validate_session(mem_session, user.id + 999, token)

        assert resolved is None

    def test_tampered_token_returns_none(self, mem_session, user):
        from backend.core.identity import issue_session, validate_session

        token, _ = issue_session(mem_session, user)
        tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
        resolved = validate_session(mem_session, user.id, tampered)

        assert resolved is None

    def test_expired_session_returns_none(self, mem_session, user):
        from backend.core.identity import issue_session, validate_session

        user.session_token_ttl = 30
        mem_session.add(user)
        mem_session.commit()
        token, _ = issue_session(mem_session, user)

        user.session_token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        mem_session.add(user)
        mem_session.commit()

        assert validate_session(mem_session, user.id, token) is None

    def test_logged_out_session_returns_none(self, mem_session, user):
        from backend.core.identity import clear_session, issue_session, validate_session

        token, _ = issue_session(mem_session, user)
        clear_session(mem_session, user)

        assert validate_session(mem_session, user.id, token) is None

    def test_nonexistent_user_returns_none(self, mem_session):
        from backend.core.identity import validate_session

        assert validate_session(mem_session, 9999, "whatever") is None


class TestParseSessionCookie:
    def test_valid_cookie_splits_user_id_and_token(self):
        from backend.core.identity import parse_session_cookie

        assert parse_session_cookie("42.abc123") == (42, "abc123")

    def test_no_separator_returns_none(self):
        from backend.core.identity import parse_session_cookie

        assert parse_session_cookie("no-dot-here") is None

    def test_non_digit_user_id_returns_none(self):
        from backend.core.identity import parse_session_cookie

        assert parse_session_cookie("abc.sometoken") is None

    def test_empty_user_id_returns_none(self):
        from backend.core.identity import parse_session_cookie

        assert parse_session_cookie(".sometoken") is None
