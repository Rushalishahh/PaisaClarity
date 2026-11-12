import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
import jwt

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")
load_dotenv()

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # token valid for 24 hours

DEV_DEFAULT_SECRET = "dev-insecure-secret-key-change-in-production"
MIN_SECRET_LENGTH = 32
VALID_ENVIRONMENTS = {"development", "dev", "test", "testing", "production", "prod"}


def get_environment() -> str:
    """
    Returns the normalized environment name ('development', 'test', or 'production').
    Treats the environment as production if ENVIRONMENT is 'production'/'prod' OR the RENDER env var is set.
    Rejects unrecognized ENVIRONMENT values with a ValueError.
    """
    raw_env = os.getenv("ENVIRONMENT")
    is_render = bool(os.getenv("RENDER"))

    if raw_env and raw_env.strip():
        cleaned = raw_env.strip().lower()
        if cleaned not in VALID_ENVIRONMENTS:
            raise ValueError(
                f"Invalid ENVIRONMENT '{raw_env}'. Valid options are: development, test, production."
            )
        if cleaned in ("production", "prod"):
            return "production"
        if cleaned in ("test", "testing"):
            return "test"
        return "development"

    if is_render:
        return "production"

    return "development"


def get_secret_key() -> str:
    """
    Retrieves the JWT signing secret at call time.

    Prefers SECRET_KEY; falls back to JWT_SECRET.
    - In production: Refuses to start if secret is missing, matches known dev default,
      or is shorter than 32 characters.
    - In development/test: If neither is set, emits a warning and uses DEV_DEFAULT_SECRET.
    """
    env = get_environment()
    secret = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET")

    if env == "production":
        if not secret or not secret.strip():
            raise RuntimeError(
                "CRITICAL: Neither SECRET_KEY nor JWT_SECRET is configured. "
                "Refusing to start in production without a secure JWT signing secret."
            )
        secret = secret.strip()
        if secret == DEV_DEFAULT_SECRET:
            raise RuntimeError(
                "CRITICAL: Insecure default SECRET_KEY detected in production. "
                "You must set a unique, randomly-generated secret (min 32 characters)."
            )
        if len(secret) < MIN_SECRET_LENGTH:
            raise RuntimeError(
                f"CRITICAL: SECRET_KEY is too short ({len(secret)} characters). "
                f"Production requires a secret with at least {MIN_SECRET_LENGTH} characters."
            )
        return secret

    # Development or Test environment
    if not secret or not secret.strip():
        logger.warning(
            "No SECRET_KEY or JWT_SECRET found in environment. "
            "Using insecure development secret key. Do NOT use this in production!"
        )
        return DEV_DEFAULT_SECRET

    return secret.strip()


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    Create a signed JWT containing the given data (e.g. {'user_id': 5}).
    Adds an expiration time automatically, or uses expires_delta if specified.
    """
    secret = get_secret_key()
    to_encode = data.copy()
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, secret, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict | None:
    """
    Verify and decode a JWT. Returns the payload dict if valid,
    or None if the token is invalid/expired/tampered with.
    """
    secret = get_secret_key()
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None  # token was valid but has expired
    except jwt.InvalidTokenError:
        return None  # token is malformed or signature doesn't match
