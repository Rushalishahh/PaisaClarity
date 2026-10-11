from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import get_database_url

# get_database_url() fails fast with a clear error (naming the variable, never
# its value) if DATABASE_URL is missing - create_engine itself is lazy and
# opens no connection here.
engine = create_engine(get_database_url())

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
