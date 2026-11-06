"""Rate limiting module for PaisaClarity authentication endpoints.

Uses SlowAPI to protect sensitive endpoints (/auth/login and /auth/signup) against
brute-force attacks and credential stuffing.

Security design:
1. Safe IP detection:
   - When running on Render (RENDER env var set) or when TRUST_PROXY_HEADERS=true,
     inspect trusted headers (CF-Connecting-IP, True-Client-IP) first because Cloudflare
     strips and sets them, making them unforgeable by clients.
   - If relying on X-Forwarded-For, take the rightmost / nearest hop (hops[-1]).
     Render appends the real incoming client IP to any existing X-Forwarded-For header,
     so the leftmost entry could be forged by an attacker.
   - In local development and tests (when neither RENDER nor TRUST_PROXY_HEADERS is set),
     always fall back to request.client.host so attackers cannot spoof IP headers.
2. Dynamic configuration:
   - RATE_LIMIT_LOGIN (default: "10/minute")
   - RATE_LIMIT_SIGNUP (default: "5/minute")
   - RATE_LIMIT_ENABLED (default: "true")
   - PROXY_HEADER_ORDER (default: "cf-connecting-ip,true-client-ip")
   - TRUST_PROXY_HEADERS (default: "false")
"""

import os
from fastapi import Request
from starlette.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded


def should_trust_proxy_headers() -> bool:
    """Only trust reverse-proxy headers (like CF-Connecting-IP or X-Forwarded-For)
    when explicitly running in production on Render (RENDER env var set) or when
    TRUST_PROXY_HEADERS is explicitly set to true.
    In local development and tests, using request.client.host prevents spoofing."""
    if os.getenv("RENDER"):
        return True
    return os.getenv("TRUST_PROXY_HEADERS", "").strip().lower() in ("true", "1", "yes")


def get_proxy_header_order() -> list[str]:
    """Comma-separated list of headers to inspect in priority order.
    Defaults to 'cf-connecting-ip,true-client-ip'."""
    raw = os.getenv("PROXY_HEADER_ORDER", "cf-connecting-ip,true-client-ip")
    return [h.strip().lower() for h in raw.split(",") if h.strip()]


def get_client_ip(request: Request) -> str:
    """Extract client IP safely for rate limiting.

    Render's load balancer appends client IPs to X-Forwarded-For rather than stripping it,
    which means the leftmost entry could be client-forged.
    To prevent spoofing:
    1. If not in a trusted proxy environment (local dev/tests), return request.client.host.
    2. Cloudflare sets CF-Connecting-IP / True-Client-IP, which are not client-forgeable.
       We inspect those first.
    3. If falling back to X-Forwarded-For, take the rightmost hop (hops[-1]).
    4. Fall back to request.client.host, then '127.0.0.1'.
    """
    if not should_trust_proxy_headers():
        if request.client and request.client.host:
            return request.client.host
        return "127.0.0.1"

    # 1. Check configured trusted proxy headers
    for header in get_proxy_header_order():
        val = request.headers.get(header)
        if val and val.strip():
            # If comma-separated, take the first entry
            return val.split(",")[0].strip()

    # 2. Check X-Forwarded-For: take rightmost entry, never leftmost
    xff = request.headers.get("x-forwarded-for")
    if xff and xff.strip():
        hops = [ip.strip() for ip in xff.split(",") if ip.strip()]
        if hops:
            return hops[-1]

    # 3. Direct socket IP
    if request.client and request.client.host:
        return request.client.host

    return "127.0.0.1"


def get_login_rate_limit() -> str:
    """Read login rate limit dynamically from environment or default to 10/minute."""
    return os.getenv("RATE_LIMIT_LOGIN", "10/minute").strip()


def get_signup_rate_limit() -> str:
    """Read signup rate limit dynamically from environment or default to 5/minute."""
    return os.getenv("RATE_LIMIT_SIGNUP", "5/minute").strip()


def is_rate_limit_enabled() -> bool:
    """Check if rate limiting is enabled via RATE_LIMIT_ENABLED env var."""
    val = os.getenv("RATE_LIMIT_ENABLED")
    if val is not None:
        return val.strip().lower() in ("true", "1", "yes")
    return True


class DynamicLimiter(Limiter):
    """SlowAPI Limiter subclass that dynamically checks RATE_LIMIT_ENABLED."""

    def __init__(self, *args, **kwargs):
        self._enabled = True
        super().__init__(*args, **kwargs)

    @property
    def enabled(self) -> bool:
        val = os.getenv("RATE_LIMIT_ENABLED")
        if val is not None:
            return val.strip().lower() in ("true", "1", "yes")
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)


limiter = DynamicLimiter(key_func=get_client_ip)


def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom 429 handler returning standard FastAPI detail format."""
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}. Please try again later."},
    )
