# PaisaClarity — Privacy-First Personal Finance Assistant & AI Copilot

[![Backend Tests](https://img.shields.io/badge/pytest-154%20passed-brightgreen.svg)](docs/release-readiness.md)
[![PostgreSQL Integration](https://img.shields.io/badge/postgresql-18.6%20verified-blue.svg)](docs/postgresql-validation.md)
[![Browser E2E](https://img.shields.io/badge/playwright-12%20flows%20passed-success.svg)](docs/e2e-test-results.md)
[![Frontend Quality](https://img.shields.io/badge/eslint-0%20errors-brightgreen.svg)](docs/release-readiness.md)
[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/react-19-cyan.svg)](https://react.dev/)

**PaisaClarity** is a production-hardened, privacy-centric personal finance assistant and intelligent ledger engineered for the Indian banking and investment ecosystem. 

Unlike traditional trackers that demand open banking credentials or store private statements on disk, PaisaClarity processes multi-format bank statements (PDF, CSV, Excel) **entirely in server memory**, normalizes transactions into double-entry ledgers with **exact Decimal arithmetic**, prevents double-counting on inter-account transfers, and pairs verified data with a **secure AI Copilot** powered by deterministic tool calling.

---

## Deployment & Staging Status

> [!NOTE]
> **Deployment Readiness Baseline**: All backend APIs, PostgreSQL migrations, frontend production builds, and Playwright browser suites have been validated locally and against disposable PostgreSQL 18.6 clusters. Live deployment to public cloud hosts (Render / Vercel / Supabase) is fully prepared and runbook-documented, pending explicit production release approval.

---

## The Problem PaisaClarity Solves

1. **Privacy Insecurity in Modern Fintech**: Most financial trackers upload and store raw banking statements or passwords on cloud object stores, introducing massive data leakage risks.
2. **Floating-Point Arithmetic Drift**: Naive budget tools use IEEE-754 floating-point numbers (`0.1 + 0.2 = 0.30000000000000004`), leading to balance drift over large transaction histories.
3. **Double-Counting Transfers**: Moving money between savings and checking accounts is often recorded as both an expense and income, distorting true savings rates and cash flow metrics.
4. **Hallucinating AI Advisors**: Standard LLM chat interfaces invent mathematical totals when answering financial questions. PaisaClarity forces the AI to execute server-side verified SQL tools with enforced multi-tenant boundaries.

---

## Core Capabilities & Features

| Domain | Feature | Technical Implementation |
| :--- | :--- | :--- |
| **Ingestion** | Multi-Format Statement Parsing | In-memory extraction from PDF (tabular and text via `pdfplumber`), CSV, and Excel (`.xlsx`, `.xls`). 10MB ceiling, empty file rejection, and zero disk writes. |
| **Ledger** | Accounts & Reconciliation | Separation of verified bank accounts from unassigned placeholder accounts. Unreconciled accounts are excluded from net worth until reconciled. |
| **Categorization** | Deterministic Engine | Whole-word regex matching tuned for Indian banking narratives (UPI, NEFT, RTGS, IMPS, POS, Swiggy, Zomato, Zerodha, etc.). |
| **Transactions** | Double-Entry & Transfer Pairing | Classifies transactions into `debit`, `credit`, and `transfer`. Inter-account movements are paired and excluded from income and spend aggregates. |
| **Deduplication** | Composite Source Row Tracking | Prevents double-counting using `source_statement_id` + `source_row_index` composite uniqueness, plus fuzzy key hashing for cross-statement safety. |
| **Budgets** | Category & Global Limits | Tracks dynamic spending against monthly limits with real-time 80% threshold alerts and over-budget warnings. |
| **Savings Goals** | Target Milestones & Sinking Funds | Progressive contribution tracking with target dates and negative-balance guardrails. |
| **Cash Flow** | Recurring Payment Intelligence | Identifies subscription patterns (Netflix, Spotify, SIPs, utilities) and forecasts month-ahead obligations. |
| **Alerts** | Proactive Threshold Triggers | Event-driven alert generation for budget breaches, unusual transaction spikes ($>2\times$ baseline), and anomalous debits. |
| **AI Copilot** | Secure Financial Assistant | Tool-calling assistant with 12 deterministic financial tools. Strictly enforces authenticated `user_id` server binding; mock AI prohibited in production. |
| **Reporting** | Executive Financial Reports | In-memory generation of CSV transaction registers (with formula injection defense) and executive PDF financial reports. |
| **Reality Check** | Mutual Fund Valuation | Compares actual investment performance against traditional endowments using live Net Asset Values (NAV) from the AMFI API (`mfapi.in`). |

---

## System Architecture

```mermaid
flowchart TD
    Client["React 19 Frontend\n(Vite 8, Tailwind v4, Recharts 3)"]
    API["FastAPI Backend\n(Python 3.11, Uvicorn, SlowAPI)"]
    DB[("PostgreSQL 16/18 Database\n(SQLAlchemy 2.0, Alembic)")]
    AI["AI Copilot Provider\n(Google Gemini / OpenAI REST)"]
    External["AMFI Mutual Fund API\n(Live NAV Feeds)"]

    Client -->|"JWT Bearer Auth & REST JSON"| API
    API -->|"Connection Pool (pool_pre_ping)"| DB
    API -->|"Tool-Calling (Server-Bound user_id)"| AI
    API -->|"External Market Data"| External
```

For complete technical specifications, see [docs/architecture.md](docs/architecture.md).

---

## Database Architecture & Design

PaisaClarity models a complete personal finance ecosystem across **15 relational tables** and **81 covering indexes**:

1. `users`: Identity, bcrypt credentials, and profile state.
2. `statements`: Ingested bank statement metadata and in-memory analysis summaries.
3. `financial_accounts`: Verified bank, credit, cash, and placeholder accounts with calculated balances.
4. `categories`: Hierarchical and user-defined transaction categories with display preferences.
5. `transactions`: Normalized financial entries with `Decimal(14, 2)` monetary values, transfer links, and deduplication keys.
6. `budgets`: Monthly budget limits and warning thresholds.
7. `budget_categories`: Per-category spending caps.
8. `savings_goals`: Target savings projects, milestones, and target completion dates.
9. `savings_contributions`: Sinking fund deposits and withdrawals.
10. `recurring_payments`: Auto-detected recurring bills, subscriptions, and SIP frequencies.
11. `financial_alerts`: System-generated warnings, threshold notifications, and dismissal state.
12. `ai_conversations`: Multi-turn chat sessions bound to authenticated users.
13. `ai_messages`: Structured conversation history including assistant tool calls and responses.
14. `investments`: Portfolio asset entries (mutual funds, stocks, insurance policies).
15. `alembic_version`: Database migration tracking with ANSI-compliant boolean expressions.

---

## AI Copilot Architecture & Security Guardrails

The PaisaClarity AI Copilot is built on deterministic tool-calling rather than unstructured text prompting:

- **Server-Side Identity Binding**: When a user asks a question, the server binds `user_id = current_user.id`. The LLM has zero capability to choose, inspect, or override the target user.
- **Strictly Typed Tool Calling**: 12 deterministic tools execute SQL queries via SQLAlchemy ORM (e.g., `get_spending_by_category`, `calculate_savings_rate`, `get_budget_status`, `forecast_monthly_spending`).
- **Mathematical Accuracy**: Calculations are executed with Python `Decimal` in backend services. The LLM only receives exact calculated numbers to summarize in natural language.
- **Production Guard**: In production (`ENVIRONMENT=production`), the application strictly prohibits `MockLLMProvider` and refuses to start without a valid `GEMINI_API_KEY` or `OPENAI_API_KEY`.

---

## Verification & Test Results

PaisaClarity enforces a multi-tier testing strategy covering unit, integration, migration, security, frontend build, and headless browser tests:

```
========================================================================================
Test Suite                               Scope / Engine                 Result
========================================================================================
Backend Pytest Suite                     154 unit & feature tests       154 / 154 PASSED (0 failures)
PostgreSQL Integration Tests             PostgreSQL 18.6 disposable     10 / 10 PASSED (0 drift)
Playwright Browser E2E Suite             Chromium Headless (12 flows)   12 / 12 PASSED (9.6s)
Frontend Unit Tests                      Node test runner               5 / 5 PASSED
Frontend Code Quality                    ESLint                         0 errors, 0 warnings
Frontend Production Build                Vite 8 / Rolldown              PASSED (all chunks < 400 kB)
Alembic Migration Consistency            Clean & Populated Upgrade      PASSED (diff = 0)
Git Secrets Inspection                   No tracked .env or credentials PASSED
========================================================================================
```

*Note on Benchmarks*: The above figures represent synthetic regression suites executed in isolated environments. Real-world execution times may vary depending on network latency to external AI providers.

---

## Local Development Setup

### Prerequisites
- Python 3.11+
- Node.js 22 LTS & npm
- PostgreSQL 15+ (optional; SQLite fallback enabled for zero-config local development)

### 1. Backend Setup
```bash
# Clone the repository
git clone https://github.com/your-username/PaisaClarity.git
cd PaisaClarity/backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Copy environment configuration
cp .env.example .env

# Run database migrations (or let auto-create handle local SQLite)
alembic upgrade head

# Start backend server
uvicorn main:app --reload --port 8000
```
Backend will be live at `http://localhost:8000` (API docs at `http://localhost:8000/docs`).

### 2. Frontend Setup
```bash
cd ../frontend-react

# Install dependencies
npm install

# Copy environment configuration
cp .env.example .env

# Run development server
npm run dev
```
Frontend will be live at `http://localhost:5173`.

### 3. Running Test Suites
```bash
# Backend pytest suite (154 tests)
cd backend
pytest -q

# PostgreSQL integration suite (requires local Postgres service)
python scripts/test_postgresql_integration.py

# Frontend lint, unit tests, and production build
cd ../frontend-react
npm run lint
npm test -- --run
npm run build

# Playwright browser end-to-end suite
npx playwright test
```

---

## Environment Variable Reference

### Backend (`backend/.env`)
| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Runtime environment (`development`, `test`, `production`) | `development` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@localhost:5432/finance` |
| `SECRET_KEY` | JWT signing secret (min 32 characters in production) | Random 64-char hex string |
| `ALLOWED_ORIGINS` | Permitted CORS frontend origins | `http://localhost:5173` |
| `AUTO_CREATE_TABLES` | Auto-run DDL on startup (`false` in strict prod) | `true` |
| `DB_POOL_SIZE` | SQLAlchemy connection pool size | `10` |
| `DB_MAX_OVERFLOW` | SQLAlchemy maximum overflow connections | `20` |
| `DB_POOL_RECYCLE` | Stale connection recycling period (seconds) | `300` |
| `GEMINI_API_KEY` | Google Gemini API key for AI Copilot | Optional in dev, required in prod |
| `RATE_LIMIT_AI_CHAT` | Throttling limit for AI Copilot | `20/minute` |

### Frontend (`frontend-react/.env`)
| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `VITE_API_URL` | Base URL of the backend API | `http://localhost:8000` |
| `VITE_API_BASE_URL` | Alternate alias for backend API URL | `http://localhost:8000` |

---

## Production Deployment Architecture

```
[User Browser]
      │
      ▼
[Vercel Frontend] (React 19 SPA, Global CDN, SPA Rewrites via vercel.json)
      │ HTTPS (JWT)
      ▼
[Render API Service] (FastAPI, Python 3.11, Uvicorn, SlowAPI Rate Limiting)
      │ Pooled SQL (SSL required)
      ▼
[Supabase Managed PostgreSQL] (15 Tables, 81 Indexes, Exact Decimal Precision)
```

- **Deployment Runbook**: Detailed migration, verification, and rollback steps in [docs/deployment-runbook.md](docs/deployment-runbook.md).
- **Security Audit**: OWASP security review and vulnerability mitigations in [docs/security-audit.md](docs/security-audit.md).
- **Release Readiness**: Staging verification decision matrix in [docs/release-readiness.md](docs/release-readiness.md).

---

## Known Limitations & Roadmap

### Known Limitations
- **Indian Banking Formats**: While statement parsing supports standard CSV, Excel, and structured PDF layouts from major Indian banks (HDFC, SBI, ICICI, Axis), scanned image-based statements without text layers require OCR preprocessing.
- **Live Market Data**: Mutual fund NAV lookups depend on the public AMFI service (`mfapi.in`); temporary third-party API rate limits or latency may delay live valuation updates.

### Planned Enhancements
- Integration of Tesseract OCR for physical scanned bank slips.
- Direct account aggregation via Account Aggregator (RBI AA framework) APIs.
- Multi-currency ledger support (USD, EUR, GBP) alongside INR.
- WebPush browser notifications for immediate budget threshold alerts.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
