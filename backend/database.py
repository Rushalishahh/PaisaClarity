import logging
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
# Load environment from backend/.env if present
load_dotenv(dotenv_path=BASE_DIR / ".env")
load_dotenv()

# Valid environments: development, test, production (with aliases)
VALID_ENVIRONMENTS = {"development", "dev", "test", "testing", "production", "prod"}
RETRY_DELAYS = [1.0, 2.0, 4.0]  # Backoff delays in seconds; patchable in tests


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


def mask_url(url: str | None) -> str:
    """Safely render a database URL masking any credentials for logging/errors."""
    if not url:
        return "<empty>"
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return "<invalid-url>"


def init_engine(url: str | None = None, fallback_dir: Path | None = None):
    """
    Initializes and returns a SQLAlchemy Engine.

    - In production: Refuses to start if DATABASE_URL is missing, points to SQLite,
      or cannot be connected to after retries. Password credentials are masked in all logs/errors.
    - In development/test: If DATABASE_URL is unreachable or not configured, falls back
      to a local SQLite database with a visible warning.
    """
    env = get_environment()
    target_url = url if url is not None else os.getenv("DATABASE_URL")
    target_url = target_url.strip() if target_url else ""

    if env == "production":
        if not target_url:
            raise RuntimeError(
                "CRITICAL: DATABASE_URL is not set. Production refuses to start without a configured PostgreSQL database."
            )
        if target_url.startswith("sqlite"):
            raise RuntimeError(
                "CRITICAL: SQLite is not permitted in production. A persistent PostgreSQL DATABASE_URL is required."
            )

        safe_url = mask_url(target_url)
        # 5 second connection timeout for PostgreSQL
        connect_args = {"connect_timeout": 5}
        eng = create_engine(target_url, connect_args=connect_args)

        last_err = None
        for attempt, delay in enumerate(RETRY_DELAYS, start=1):
            try:
                with eng.connect():
                    pass
                return eng
            except Exception as exc:
                last_err = exc
                if attempt < len(RETRY_DELAYS) and delay > 0:
                    time.sleep(delay)

        # Sanitize exception message to ensure raw password is never exposed
        err_msg = str(last_err)
        try:
            parsed = make_url(target_url)
            if parsed.password and parsed.password in err_msg:
                err_msg = err_msg.replace(parsed.password, "******")
        except Exception:
            pass

        raise RuntimeError(
            f"CRITICAL: Production DATABASE_URL ({safe_url}) is unreachable after "
            f"{len(RETRY_DELAYS)} attempts: {err_msg}"
        )

    # Development or Test environment
    target_dir = fallback_dir or BASE_DIR
    sqlite_fallback = f"sqlite:///{target_dir / 'finance.db'}"
    chosen_url = target_url if target_url else sqlite_fallback
    connect_args = {"check_same_thread": False} if chosen_url.startswith("sqlite") else {}
    safe_chosen = mask_url(chosen_url)

    if not chosen_url.startswith("sqlite"):
        try:
            eng = create_engine(chosen_url, connect_args=connect_args)
            with eng.connect():
                pass
            return eng
        except Exception as exc:
            safe_fallback = mask_url(sqlite_fallback)
            logger.warning(
                f"Configured database ({safe_chosen}) is unreachable. "
                f"Falling back to local SQLite database at {safe_fallback}."
            )
            return create_engine(sqlite_fallback, connect_args={"check_same_thread": False})

    return create_engine(chosen_url, connect_args=connect_args)


# Initialized at module load for application runtime
engine = init_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
