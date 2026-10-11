# LEARNING_LOG

## 2026-10-11 — Configuration hardening (env validation + .env.example fix)

### What was built
Fail-fast, centralized environment configuration for the backend. Before this,
`backend/.env.example` defined `JWT_SECRET` while the code read `SECRET_KEY`
(so following the setup docs guaranteed a cryptic PyJWT crash on first login),
and a missing `DATABASE_URL` surfaced as SQLAlchemy's `ArgumentError` at import
(or `AttributeError: 'NoneType'` in Alembic). Now a missing/blank variable
raises `ConfigError` naming the variable and pointing at `.env.example` —
never printing the value.

### Files changed
- `backend/config.py` (NEW) — the ONLY module that calls `load_dotenv()`;
  exposes `require_env()`, `get_database_url()`, `get_secret_key()`.
- `backend/.env.example` — `JWT_SECRET` renamed to `SECRET_KEY` (docs follow
  code; AGENTS.md already mandated the name).
- `backend/database.py` — engine built with `get_database_url()`; own
  `load_dotenv()` call removed.
- `backend/jwt_utils.py` — `SECRET_KEY = get_secret_key()`; own
  `load_dotenv()` call removed.
- `backend/main.py` — redundant `load_dotenv()` removed (the import chain
  `main → auth_routes → jwt_utils → config` loads env before main.py reads
  `ALLOWED_ORIGINS`).
- `backend/alembic/env.py` — `db_url = get_database_url()`; `%%`-escaping kept.
- `backend/tests/conftest.py` — `import config` (loads dotenv) THEN
  `os.environ.setdefault(...)` dummies for both vars; fixtures untouched.
- `backend/tests/test_config.py` (NEW) — 9 tests, pure functions + monkeypatch.
- `AGENTS.md` — psycopg doc drift fixed (`psycopg[binary]` → `psycopg2-binary`);
  `config.py` added to the Layout section.

### Why each design choice (and the rejected alternative)
1. **Import-time validation via a pure `config.py` module, not a FastAPI
   startup event.** `create_engine(None)` already explodes at import before
   any startup handler could run; making the engine lazy would be a bigger
   refactor. Import-time is also the existing de-facto behavior — this change
   only makes the message legible. Rejected: startup-event validation
   (too late) and lazy engine factory (too invasive).
2. **One `load_dotenv()` caller in `config.py`.** python-dotenv 1.2.4's
   `find_dotenv()` walks up from the *calling file's* directory (not CWD), so
   placing the call in `backend/config.py` resolves the same `backend/.env`
   as before from every entry point (uvicorn, pytest from root or backend/,
   alembic). Rejected: leaving four scattered calls (drift-prone).
3. **Lazy getters, no module-level constants in `config.py`.** `import config`
   alone requires nothing; validation fires when a getter is called. This is
   what lets `test_config.py` import the module with no env set, and lets
   `monkeypatch.delenv` genuinely simulate a missing variable (getters re-read
   `os.environ` each call; dotenv is never re-run inside a getter).
4. **conftest: dotenv first, then `setdefault`.** `load_dotenv()` defaults to
   `override=False` — it skips variables already in `os.environ`. Doing
   `setdefault` *first* would have made the dummies silently win over a real
   `.env`. With dotenv first, a real `.env` yields a byte-identical test env
   to before; without one, the dummies keep collection working. Rejected:
   setdefault-first ordering (would have masked real config in tests).
5. **Presence-only validation; values returned verbatim.** No scheme parsing
   (so `postgresql://`, `postgresql+psycopg://`, `sqlite:///...` all pass) and
   no stripping (never mutate a secret). Rejected: scheme whitelists and
   placeholder-value detection (magic strings, scope creep).
6. **`from config import get_database_url` in `alembic/env.py`, never
   `import config`.** env.py rebinds the name `config` to `context.config`
   at module level; a bare `import config` would be shadowed.
7. **No dependency change for the psycopg mismatch.** The venv contains both
   psycopg 3.3.6 and psycopg2-binary 2.9.13, but `requirements.txt` declares
   only psycopg2-binary and `.env.example`'s plain `postgresql://` scheme
   routes to psycopg2 under SQLAlchemy 2.x. Fixed the doc; reported the rest.

### Verification
- `pytest` from repo root: 64 passed (55 existing + 9 new).
- `PYTHON_DOTENV_DISABLED=1 python -c "import database"` →
  `ConfigError: Missing required environment variable: DATABASE_URL...`;
  same for `import jwt_utils` → names `SECRET_KEY`. No values printed.
- `import main` OK with real `.env`; `alembic/env.py` compiles.
- `npm run build` OK. `npm run lint` has 2 PRE-EXISTING errors in
  `App.jsx`/`Dashboard.jsx` (files untouched by this change).

### Convention going forward
`config.py` stays the only `load_dotenv()` caller, and getters must never
re-run it — otherwise `monkeypatch.delenv`-based tests would see deleted
variables resurrected from `.env`.

### Interview questions
1. **Q: Why is `load_dotenv(override=False)`'s default important for
   deployment?** A: Because real environment variables (set by the OS, Docker,
   or a host's secret manager) always win over the `.env` file — the file is
   only a local-dev convenience, never an override of production config.
2. **Q: Why validate required config at import time rather than on first
   request?** A: Fail-fast. A misconfigured process should die before it
   binds a port or serves traffic, so the operator sees the error immediately
   in logs instead of as intermittent 500s under load. Import time is also
   the earliest point every entry point (uvicorn, alembic, tests) shares.
3. **Q: How do you test "env var is missing" when the test harness itself
   sets a fallback value?** A: `monkeypatch.delenv(name, raising=False)`
   removes the key from `os.environ` for the test's duration regardless of who
   set it, provided the code under test reads `os.environ` at call time and
   doesn't re-load the `.env` file inside the getter. monkeypatch restores the
   previous value afterwards, so tests stay isolated.
