"""
Single place that owns environment configuration.

- The ONLY module that calls load_dotenv(): it resolves backend/.env by
  walking up from this file's directory, so it works from any CWD, and it
  never overrides variables already present in the OS environment.
- Validation is LAZY: importing this module requires nothing. A variable is
  only checked when its getter is called (at app/alembic startup).
- Errors name the variable and point at .env.example. A variable's VALUE
  is never included in any error message or log.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    """A required environment variable is missing, empty, or whitespace-only."""


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ConfigError(
            f"Missing required environment variable: {name}. "
            f"Copy backend/.env.example to backend/.env and set it there."
        )
    return value  # verbatim - never stripped, never logged


def get_database_url() -> str:
    return require_env("DATABASE_URL")


def get_secret_key() -> str:
    return require_env("SECRET_KEY")
