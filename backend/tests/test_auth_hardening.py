"""Tests for Phase 3: Authentication Hardening (Rate Limiting & Password Policy)."""

import pytest
from starlette.requests import Request
from fastapi.testclient import TestClient

from main import app
from rate_limiter import limiter, get_client_ip


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Ensure limiter storage is reset before and after each test."""
    limiter.reset()
    yield
    limiter.reset()


def make_mock_request(headers=None, client_host="192.168.1.50"):
    """Helper to construct a Starlette Request with custom headers and client host."""
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "headers": raw_headers,
        "client": (client_host, 12345),
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# Rate Limiting Tests
# ---------------------------------------------------------------------------

def test_login_rate_limiting_triggers_429(client: TestClient, monkeypatch):
    """Attempting more than 10 logins per minute from the same IP returns HTTP 429."""
    limiter.reset()

    # Default is 10/minute
    for i in range(10):
        resp = client.post(
            "/auth/login",
            json={"email": "ratelimit_test@example.com", "password": "WrongPassword123!"},
        )
        assert resp.status_code == 401, f"Attempt {i+1} should return 401, got {resp.status_code}"

    # 11th attempt must trigger rate limit (429)
    resp = client.post(
        "/auth/login",
        json={"email": "ratelimit_test@example.com", "password": "WrongPassword123!"},
    )
    assert resp.status_code == 429
    data = resp.json()
    assert "detail" in data
    assert "Rate limit exceeded" in data["detail"]

    # Reset allows requests again
    limiter.reset()
    resp_after = client.post(
        "/auth/login",
        json={"email": "ratelimit_test@example.com", "password": "WrongPassword123!"},
    )
    assert resp_after.status_code == 401


def test_signup_rate_limiting_triggers_429(client: TestClient):
    """Attempting more than 5 signups per minute from the same IP returns HTTP 429."""
    limiter.reset()

    # 5 attempts with valid schema (hits the endpoint handler)
    for i in range(5):
        resp = client.post(
            "/auth/signup",
            json={"email": f"signup_limit_{i}@example.com", "password": "StrongPassword123!"},
        )
        assert resp.status_code == 200

    # 6th attempt must trigger 429
    resp = client.post(
        "/auth/signup",
        json={"email": "signup_limit_6@example.com", "password": "StrongPassword123!"},
    )
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.json()["detail"]


def test_rate_limiting_can_be_disabled(client: TestClient, monkeypatch):
    """When RATE_LIMIT_ENABLED is false, requests beyond the limit succeed/pass through."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    limiter.reset()

    for _ in range(12):
        resp = client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "WrongPassword123!"},
        )
        assert resp.status_code == 401


def test_rate_limit_429_includes_cors_headers(client: TestClient):
    """When a 429 response is returned, CORS headers must be present so frontend receives error cleanly."""
    limiter.reset()

    # Exhaust limit
    for _ in range(10):
        client.post(
            "/auth/login",
            json={"email": "cors_test@example.com", "password": "WrongPassword123!"},
            headers={"Origin": "http://localhost:5173"},
        )

    # 11th request triggers 429 with CORS header
    resp = client.post(
        "/auth/login",
        json={"email": "cors_test@example.com", "password": "WrongPassword123!"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 429
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


# ---------------------------------------------------------------------------
# Client IP Detection & Anti-Spoofing Tests
# ---------------------------------------------------------------------------

def test_client_ip_dev_ignores_proxy_headers(monkeypatch):
    """In local development (no RENDER, TRUST_PROXY_HEADERS not set), fake proxy headers are ignored."""
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)

    req = make_mock_request(
        headers={
            "x-forwarded-for": "1.2.3.4, 5.6.7.8",
            "cf-connecting-ip": "9.9.9.9",
        },
        client_host="127.0.0.1",
    )
    assert get_client_ip(req) == "127.0.0.1"


def test_client_ip_render_prefers_cf_connecting_ip_over_spoofed_xff(monkeypatch):
    """On Render (RENDER env var set), CF-Connecting-IP is trusted over spoofed X-Forwarded-For."""
    monkeypatch.setenv("RENDER", "true")

    # Attacker passes spoofed X-Forwarded-For, but Cloudflare edge sets CF-Connecting-IP
    req = make_mock_request(
        headers={
            "x-forwarded-for": "spoofed.attacker.ip, 10.0.0.1",
            "cf-connecting-ip": "198.51.100.22",
        },
        client_host="10.0.0.1",
    )
    assert get_client_ip(req) == "198.51.100.22"


def test_client_ip_render_uses_rightmost_xff_hop_when_no_cf_header(monkeypatch):
    """When no Cloudflare header is present on Render, take the rightmost XFF hop (not leftmost)."""
    monkeypatch.setenv("RENDER", "true")

    # Render load balancer appends real client IP at the end of incoming XFF
    req = make_mock_request(
        headers={
            "x-forwarded-for": "spoofed.leftmost.ip, real.client.ip",
        },
        client_host="10.0.0.1",
    )
    assert get_client_ip(req) == "real.client.ip"


def test_client_ip_custom_header_order(monkeypatch):
    """Configurable PROXY_HEADER_ORDER allows prioritizing custom reverse proxy headers."""
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("PROXY_HEADER_ORDER", "x-custom-real-ip,cf-connecting-ip")

    req = make_mock_request(
        headers={
            "x-custom-real-ip": "203.0.113.88",
            "cf-connecting-ip": "198.51.100.22",
        },
    )
    assert get_client_ip(req) == "203.0.113.88"


# ---------------------------------------------------------------------------
# Password Policy Tests (Signup vs Login)
# ---------------------------------------------------------------------------

def test_signup_rejects_password_too_short(client: TestClient):
    """Signup rejects passwords shorter than 8 characters with HTTP 422."""
    resp = client.post(
        "/auth/signup",
        json={"email": "short_pw@example.com", "password": "short"},
    )
    assert resp.status_code == 422
    assert "at least 8 characters" in resp.text


def test_signup_rejects_all_digit_password(client: TestClient):
    """Signup rejects entirely numeric passwords with HTTP 422."""
    resp = client.post(
        "/auth/signup",
        json={"email": "numeric_pw@example.com", "password": "1234567890"},
    )
    assert resp.status_code == 422
    assert "entirely numeric" in resp.text


def test_signup_rejects_password_exceeding_72_bytes(client: TestClient):
    """Signup rejects passwords > 72 bytes with HTTP 422 (prevents bcrypt 5.0.0 crash / 500 error)."""
    resp = client.post(
        "/auth/signup",
        json={"email": "long_pw@example.com", "password": "a" * 73},
    )
    assert resp.status_code == 422
    assert "cannot exceed 72 bytes" in resp.text


def test_signup_accepts_valid_password(client: TestClient):
    """Signup succeeds with valid password meeting all policy criteria."""
    resp = client.post(
        "/auth/signup",
        json={
            "email": "policy_valid@example.com",
            "password": "StrongPassword123!",
            "full_name": "Policy Tester",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_does_not_reject_weak_passwords_at_schema(client: TestClient):
    """Login does NOT enforce the signup policy; it accepts weak passwords without 422."""
    # Sending a short or numeric password to login should fail auth (401), not schema (422)
    resp = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "123"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Incorrect email or password"
