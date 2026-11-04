import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SQLITE_FALLBACK = f"sqlite:///{BASE_DIR / 'finance.db'}"


def init_engine(url: str | None):
    chosen_url = url if url and url.strip() else SQLITE_FALLBACK
    connect_args = {"check_same_thread": False} if chosen_url.startswith("sqlite") else {}

    try:
        eng = create_engine(chosen_url, connect_args=connect_args)
        # Test connection immediately if remote to detect DNS / connectivity issues early
        if not chosen_url.startswith("sqlite"):
            with eng.connect():
                pass
        return eng
    except Exception as exc:
        logger.warning(
            f"Configured database ({chosen_url}) is unreachable: {exc}. "
            f"Falling back to local SQLite database at {SQLITE_FALLBACK}."
        )
        return create_engine(SQLITE_FALLBACK, connect_args={"check_same_thread": False})


engine = init_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
