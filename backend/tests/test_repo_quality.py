"""Tests for Phase 7: Repo and Deployment Quality (Health probes & create_all gating)."""

import asyncio
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from main import app, should_auto_create_tables, lifespan
from database import get_db, Base


def test_health_liveness_ok(client: TestClient):
    """GET /health returns 200 and {'status': 'ok'} without touching DB or auth."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_readiness_ok(client: TestClient):
    """GET /health/ready returns 200 and {'status': 'ok', 'database': 'ok'} when DB is healthy."""
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}


def test_health_readiness_degraded_when_db_fails(client: TestClient):
    """GET /health/ready returns 503 {'status': 'degraded', 'database': 'unreachable'} when DB query fails."""
    # Create a mock session that fails on execute
    failing_db = MagicMock()
    failing_db.execute.side_effect = Exception("Simulated DB connection failure")

    def override_get_db():
        yield failing_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data == {"status": "degraded", "database": "unreachable"}
        # Ensure raw exception text is NEVER leaked in the response body
        assert "Simulated DB connection failure" not in resp.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_health_endpoints_never_leak_credentials(client: TestClient, monkeypatch):
    """Health probes must never reveal database credentials or internal secrets."""
    secret_marker = "SUPER_SECRET_DB_PASSWORD_12345"
    monkeypatch.setenv("DATABASE_URL", f"postgresql://postgres:{secret_marker}@localhost:5432/db")

    for path in ["/health", "/health/ready"]:
        resp = client.get(path)
        assert secret_marker not in resp.text


def test_should_auto_create_tables_flag(monkeypatch):
    """should_auto_create_tables() defaults to true and honors boolean-like strings."""
    monkeypatch.delenv("AUTO_CREATE_TABLES", raising=False)
    assert should_auto_create_tables() is True

    monkeypatch.setenv("AUTO_CREATE_TABLES", "true")
    assert should_auto_create_tables() is True

    monkeypatch.setenv("AUTO_CREATE_TABLES", "1")
    assert should_auto_create_tables() is True

    monkeypatch.setenv("AUTO_CREATE_TABLES", "false")
    assert should_auto_create_tables() is False

    monkeypatch.setenv("AUTO_CREATE_TABLES", "0")
    assert should_auto_create_tables() is False


def test_lifespan_respects_auto_create_tables(monkeypatch):
    """Base.metadata.create_all is called only when AUTO_CREATE_TABLES is true."""
    async def run_lifespan():
        async with lifespan(app):
            pass

    # When enabled (default)
    monkeypatch.setenv("AUTO_CREATE_TABLES", "true")
    with patch.object(Base.metadata, "create_all") as mock_create:
        asyncio.run(run_lifespan())
        mock_create.assert_called_once()

    # When disabled
    monkeypatch.setenv("AUTO_CREATE_TABLES", "false")
    with patch.object(Base.metadata, "create_all") as mock_create:
        asyncio.run(run_lifespan())
        mock_create.assert_not_called()
