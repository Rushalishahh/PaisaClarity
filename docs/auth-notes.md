# Authentication & Rate Limiting Deployment Notes

This document provides deployment guidelines, configuration details, known limitations, and manual verification steps for the authentication rate limiting and hardening introduced in Phase 3.

---

## 1. Environment Variables & Defaults

The following variables can be configured in your deployment platform (e.g. Render Dashboard $\rightarrow$ Environment). All variables have safe defaults and are optional unless custom behavior is required.

| Variable | Default | Description |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | Globally enables or disables rate limiting on `/auth/login` and `/auth/signup`. Set to `false` in development/testing if needed. |
| `RATE_LIMIT_LOGIN` | `10/minute` | Rate limit ceiling for `/auth/login` attempts per client IP. Format: `"<number>/<minute|hour|day>"`. |
| `RATE_LIMIT_SIGNUP` | `5/minute` | Rate limit ceiling for `/auth/signup` attempts per client IP. Format: `"<number>/<minute|hour|day>"`. |
| `TRUST_PROXY_HEADERS` | `false` | Explicitly enables inspection of reverse-proxy headers (`CF-Connecting-IP`, `True-Client-IP`, `X-Forwarded-For`). Automatically treated as `true` when `RENDER` is set. |
| `PROXY_HEADER_ORDER` | `cf-connecting-ip,true-client-ip` | Comma-separated list of trusted upstream proxy headers inspected in priority order before falling back to `X-Forwarded-For`. |

---

## 2. Client IP Resolution & Anti-Spoofing Design

Render's reverse proxy appends incoming client IPs to any existing `X-Forwarded-For` header rather than replacing or stripping it. Because of this, relying on the leftmost `X-Forwarded-For` value would allow an attacker to bypass rate limiting simply by supplying a fake `X-Forwarded-For: <fake-ip>` header.

The resolution logic in `backend/rate_limiter.py` addresses this:
1. **Local Development & Direct Connections**: When neither `RENDER` nor `TRUST_PROXY_HEADERS` is set, all incoming proxy headers are completely ignored, and the rate limiter binds to `request.client.host`.
2. **Cloudflare Edge Headers**: When running on Render (`RENDER` env var is set), the limiter first inspects headers set by Cloudflare edge proxies (`CF-Connecting-IP` or `True-Client-IP`). These headers are stripped and set at the CDN edge and cannot be forged by downstream clients.
3. **Rightmost `X-Forwarded-For` Fallback**: If Cloudflare headers are absent, the limiter parses `X-Forwarded-For` and selects the **rightmost** (nearest) hop (`hops[-1]`), which is the hop appended by the trusted reverse proxy, rather than the client-controlled leftmost hop.
4. **Socket Fallback**: If no headers match, it falls back to `request.client.host`.

---

## 3. Known Limitations & Architecture Notes

- **In-Memory Rate Limiter**: SlowAPI stores attempt counters in process memory. Counters are per-process and reset whenever the application restarts or re-deploys.
- **Multiple Web Instances**: If the Render web service is scaled to multiple dynos/instances, each instance maintains its own in-memory rate limit bucket. For distributed deployments across multiple instances, SlowAPI supports connecting to a shared Redis instance via `storage_uri="redis://..."`.
- **Rightmost `X-Forwarded-For` Hop Caveat**: If Cloudflare headers are ever absent and multiple internal reverse proxies sit between the client and the application, the rightmost hop in `X-Forwarded-For` could theoretically represent an internal proxy IP rather than the remote client. For Render, Cloudflare headers (`CF-Connecting-IP`) are present and provide the exact client IP.
- **Vercel Reverse Proxying & Deferred Refresh Tokens (Part B)**: If the frontend on Vercel were configured to proxy API requests to Render (e.g. via Vercel rewrites `/api/*` $\rightarrow$ Render), all client requests would arrive at Render from Vercel's edge IP addresses unless forwarded headers are explicitly trusted and parsed. For this reason, Part B (refresh tokens / cross-origin proxying) is deferred to ensure rate limiting remains tied to end-user client IPs.

---

## 4. Post-Deployment Manual Verification (curl)

Run the following manual tests against your live deployment (`https://paisa-clarity-api.onrender.com`):

### Test 1: Standard Rate Limit (12 Failed Logins)
Send 12 consecutive failed login requests from your terminal. The first 10 requests should return `401 Unauthorized`, and requests 11 and 12 should return `429 Too Many Requests`:

```bash
for i in {1..12}; do
  echo "Attempt $i:"
  curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "https://paisa-clarity-api.onrender.com/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"nobody@example.com","password":"WrongPassword123!"}'
done
```
**Expected Result**:
- Attempts 1–10: `HTTP 401`
- Attempts 11–12: `HTTP 429`

### Test 2: Spoofed `X-Forwarded-For` Header Bypass Test
Send 12 consecutive failed login requests, each passing a different fake `X-Forwarded-For` IP address:

```bash
for i in {1..12}; do
  echo "Attempt $i with spoofed IP:"
  curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "https://paisa-clarity-api.onrender.com/auth/login" \
    -H "Content-Type: application/json" \
    -H "X-Forwarded-For: 198.51.100.$i" \
    -d '{"email":"nobody@example.com","password":"WrongPassword123!"}'
done
```
**Expected Result**:
- Attempts 11 and 12 **must still return HTTP 429**.
- If spoofing worked, all 12 would return `HTTP 401`. Returning `429` confirms the rate limiter ignores the spoofed leftmost header.

### Test 3: Legitimate Login
Wait 60 seconds for the in-memory window to reset (or authenticate with valid credentials from an unthrottled client):

```bash
curl -X POST "https://paisa-clarity-api.onrender.com/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"your_real_user@example.com","password":"your_real_password"}'
```
**Expected Result**: `HTTP 200` with `{"access_token": "...", "token_type": "bearer"}`.
