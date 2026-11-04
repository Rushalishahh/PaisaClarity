import logging
import pytest
from database import (
    get_environment,
    init_engine,
    mask_url,
)
import database
from jwt_utils import (
    get_secret_key,
    create_access_token,
    decode_access_token,
    DEV_DEFAULT_SECRET,
    MIN_SECRET_LENGTH,
)


def test_environment_parsing(monkeypatch):
    """Verify environment detection, aliases, and rejection of unrecognized values."""
    monkeypatch.delenv("RENDER", raising=False)

    monkeypatch.setenv("ENVIRONMENT", "production")
    assert get_environment() == "production"

    monkeypatch.setenv("ENVIRONMENT", "prod")
    assert get_environment() == "production"

    monkeypatch.setenv("ENVIRONMENT", "development")
    assert get_environment() == "development"

    monkeypatch.setenv("ENVIRONMENT", "dev")
    assert get_environment() == "development"

    monkeypatch.setenv("ENVIRONMENT", "test")
    assert get_environment() == "test"

    monkeypatch.setenv("ENVIRONMENT", "testing")
    assert get_environment() == "test"

    # Default when unset
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert get_environment() == "development"

    # RENDER env var triggers production
    monkeypatch.setenv("RENDER", "true")
    assert get_environment() == "production"

    # Unrecognized environment values raise ValueError
    monkeypatch.setenv("ENVIRONMENT", "staging")
    with pytest.raises(ValueError, match="Invalid ENVIRONMENT 'staging'"):
        get_environment()


def test_mask_url():
    """Verify passwords are masked and invalid URLs do not crash."""
    masked = mask_url("postgresql://myuser:supersecret123@db.example.com:5432/mydb")
    assert "supersecret123" not in masked
    assert "myuser:***@db.example.com:5432/mydb" in masked

    assert mask_url(None) == "<empty>"
    assert mask_url("") == "<empty>"


def test_production_rejects_missing_database_url(monkeypatch):
    """Production mode must refuse to start if DATABASE_URL is missing or empty."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        init_engine(url="")

    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        init_engine(url=None)


def test_production_rejects_sqlite_url(monkeypatch):
    """Production mode must refuse to start if DATABASE_URL points to SQLite."""
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="SQLite is not permitted in production"):
        init_engine(url="sqlite:///finance.db")


def test_production_rejects_unreachable_database_and_masks_password(monkeypatch, caplog):
    """
    Production mode must retry connection and raise RuntimeError if unreachable.
    Crucially, the password must never appear in the exception message or logs.
    """
    monkeypatch.setenv("ENVIRONMENT", "production")
    # Set retry delays to 0 so the test runs instantly
    monkeypatch.setattr(database, "RETRY_DELAYS", [0, 0, 0])

    raw_password = "SuperSecretDbPassword999"
    unreachable_url = f"postgresql://pguser:{raw_password}@127.0.0.1:54329/testdb"

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError) as exc_info:
            init_engine(url=unreachable_url)

    err_text = str(exc_info.value)
    # Password must NOT be in error message or log output
    assert raw_password not in err_text
    assert raw_password not in caplog.text

    # Masked URL must be present
    assert "pguser:***@127.0.0.1:54329/testdb" in err_text
    assert "unreachable after 3 attempts" in err_text


def test_production_rejects_missing_jwt_secret(monkeypatch):
    """Production mode must refuse to start without a JWT secret configured."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="Neither SECRET_KEY nor JWT_SECRET is configured"):
        get_secret_key()


def test_production_rejects_default_dev_secret(monkeypatch):
    """Production mode must reject the known development secret."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", DEV_DEFAULT_SECRET)

    with pytest.raises(RuntimeError, match="Insecure default SECRET_KEY detected in production"):
        get_secret_key()


def test_production_rejects_short_secret(monkeypatch):
    """Production mode must reject secrets shorter than 32 characters."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "short-key-12345")

    with pytest.raises(RuntimeError, match="SECRET_KEY is too short"):
        get_secret_key()


def test_jwt_supports_secret_key_and_jwt_secret(monkeypatch):
    """Verify SECRET_KEY is preferred and JWT_SECRET works as a fallback."""
    valid_key_1 = "a" * MIN_SECRET_LENGTH
    valid_key_2 = "b" * MIN_SECRET_LENGTH

    # Fallback to JWT_SECRET when SECRET_KEY is absent
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("JWT_SECRET", valid_key_2)
    assert get_secret_key() == valid_key_2

    # SECRET_KEY takes precedence over JWT_SECRET
    monkeypatch.setenv("SECRET_KEY", valid_key_1)
    assert get_secret_key() == valid_key_1

    # End-to-end token creation and decoding with valid production secret
    token = create_access_token({"user_id": 42})
    payload = decode_access_token(token)
    assert payload is not None
    assert payload.get("user_id") == 42


def test_development_allows_sqlite_fallback(tmp_path, monkeypatch, caplog):
    """
    In development mode, unreachable database URLs must fall back to SQLite.
    The fallback path must be redirected to tmp_path so it never touches the repo.
    Database passwords must be masked in any warning logs.
    """
    monkeypatch.setenv("ENVIRONMENT", "development")
    dev_secret_pw = "DevPasswordToMask123"
    unreachable_url = f"postgresql://devuser:{dev_secret_pw}@127.0.0.1:54329/devdb"

    with caplog.at_level(logging.WARNING):
        eng = init_engine(url=unreachable_url, fallback_dir=tmp_path)

    assert eng.url.drivername == "sqlite"
    # Ensure fallback file was created in tmp_path, not in the repo
    expected_db = tmp_path / "finance.db"
    assert str(tmp_path) in str(eng.url)
    assert dev_secret_pw not in caplog.text
