"""
Unit tests for the config helpers (backend/config.py).

Pure functions only - no database, no network, no FastAPI. monkeypatch does
all env manipulation and restores os.environ after each test, so these tests
behave the same whether or not backend/.env (or conftest's fallback dummies)
provided a value: delenv removes even a dummy, and getters re-read os.environ
on every call (load_dotenv runs once at config import, never inside getters).
"""

import pytest

from config import ConfigError, get_database_url, get_secret_key, require_env


def test_missing_database_url_raises_with_guidance(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ConfigError) as exc_info:
        get_database_url()
    message = str(exc_info.value)
    assert "DATABASE_URL" in message  # names the variable
    assert ".env.example" in message  # points at the fix


def test_blank_database_url_raises(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "   ")  # whitespace-only = missing
    with pytest.raises(ConfigError):
        get_database_url()


def test_empty_database_url_raises(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")  # `DATABASE_URL=` in .env lands as ""
    with pytest.raises(ConfigError):
        get_database_url()


def test_valid_database_url_returned_verbatim(monkeypatch):
    # No scheme parsing and no stripping: every valid scheme passes through
    # exactly as set (postgresql:// routes to psycopg2, +psycopg to psycopg3 -
    # that choice stays with the URL, not with this validation).
    for url in (
        "postgresql://user:pass@host:5432/db",
        "postgresql+psycopg://user:pass@host:5432/db",
        "sqlite:///:memory:",
    ):
        monkeypatch.setenv("DATABASE_URL", url)
        assert get_database_url() == url


def test_missing_secret_key_raises_with_guidance(monkeypatch):
    # delenv removes even conftest's fallback dummy, so this genuinely
    # simulates an unset variable.
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ConfigError) as exc_info:
        get_secret_key()
    assert "SECRET_KEY" in str(exc_info.value)


def test_blank_secret_key_raises(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "  \t  ")
    with pytest.raises(ConfigError):
        get_secret_key()


def test_valid_secret_key_returned_verbatim(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "abc123")
    assert get_secret_key() == "abc123"


def test_error_message_never_contains_secret_values(monkeypatch):
    # A canary value present in the environment must not leak into the error
    # raised for a DIFFERENT missing variable.
    canary = "CANARY-SECRET-VALUE-12345"
    monkeypatch.setenv("SECRET_KEY", canary)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ConfigError) as exc_info:
        get_database_url()
    assert canary not in str(exc_info.value)


def test_require_env_generic_helper(monkeypatch):
    monkeypatch.delenv("PAISA_TEST_UNSET_VAR", raising=False)
    with pytest.raises(ConfigError):
        require_env("PAISA_TEST_UNSET_VAR")
    monkeypatch.setenv("PAISA_TEST_UNSET_VAR", "present")
    assert require_env("PAISA_TEST_UNSET_VAR") == "present"
