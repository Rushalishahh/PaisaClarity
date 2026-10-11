import os

import config  # noqa: F401 - importing it runs load_dotenv() once, so a real
               # backend/.env populates os.environ BEFORE the fallbacks below.

# Fallbacks so test collection works without backend/.env (fresh clone/CI).
# setdefault never overrides a real OS/.env value. The dummy DATABASE_URL is
# never connected to - the `client` fixture overrides get_db with SQLite.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-only-value-not-a-secret")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from auth_utils import hash_password
from models import User
from jwt_utils import create_access_token


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    def _get_test_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(db_session):
    user = db_session.query(User).filter_by(email="testuser@example.com").first()
    if not user:
        user = User(
            email="testuser@example.com",
            hashed_password=hash_password("Password123!"),
            full_name="Test User",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

    token = create_access_token({"user_id": user.id, "sub": user.email})
    return {"Authorization": f"Bearer {token}"}
