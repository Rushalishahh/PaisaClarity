AGENTS.md — Paisa Clarity

Personal finance web app for Indian users. Owner is a student who is learning this codebase while building it, so explanation matters as much as code.

Stack
Backend: Python (venv at backend/venv), FastAPI, SQLAlchemy, Alembic, PostgreSQL (Supabase) via psycopg2-binary, pandas, scikit-learn, pdfplumber
Frontend: React 19, Vite, react-router-dom 7, Tailwind CSS 4 (tokens in frontend-react/src/index.css), Recharts
Tests: pytest (run from repo root: pytest; config in pytest.ini)
Ignore frontend/ (legacy vanilla prototype, not live)
Layout
backend/main.py entry + routes; auth_*.py, jwt_utils.py auth; models.py / schemas.py DB + validation; config.py env loading + required-var validation (the ONLY load_dotenv() caller)
backend/ingest/ statement parsing → canonical DataFrame (date, value_date, description, ref_no, amount, type, balance)
backend/categorizer.py, insights.py, transactions.py, xirr.py, reality_check.py, market_data.py
frontend-react/src/ pages/, components/, api.js (the ONLY place that calls fetch), config.js, utils/format.js
Commands
Backend (Windows PowerShell): cd backend; venv\Scripts\activate; uvicorn main:app --reload --port 8000
Frontend: cd frontend-react && npm install && npm run dev (port 5173)
Tests: pytest ; lint: cd frontend-react && npm run lint ; build: npm run build
Migrations: cd backend && alembic revision --autogenerate -m "msg" && alembic upgrade head
Hard rules
Never read, print, edit or commit backend/.env or any secret. Use .env.example for new variables and keep names identical to what the code reads (SECRET_KEY, DATABASE_URL, ALLOWED_ORIGINS, LLM_API_KEY).
Every data query must filter by current_user.id. Every new protected route uses Depends(get_current_user).
Money uses Decimal/Numeric, never float in the DB. Display with formatINR (₹, lakh/crore grouping).
All frontend network calls go through src/api.js. No raw fetch in components.
Business logic goes in pure functions in their own module (like xirr.py) so it can be unit-tested without FastAPI or a DB. New routes go in backend/routers/<feature>.py, not in main.py.
Schema changes need an Alembic migration. Never edit applied migrations.
Every new feature ships with tests (backend) and must pass pytest, npm run lint, npm run build before you say it's done.
Don't add dependencies without saying why and what the alternative was.
Never call real payment/bank/insurer systems. "Bill payment" and "banking" are simulated or sit behind a provider interface with a mock implementation.
Financial output is educational, not advice. Credit score is a simulation, not a real CIBIL score. Show a disclaimer in the UI.
Never run git commit, git push or git add. I commit myself after reviewing the diff. You may run git status and git diff.
Never hardcode secrets, passwords or API keys in any file, including scripts and tests.
Teaching protocol (important)

After finishing any task:

Append an entry to LEARNING_LOG.md: what was built, which files, why each design choice (and the alternative rejected), and 3 interview questions with short answers.
Add short "why" comments only where logic is non-obvious. Don't narrate trivial code.
If I ask "explain X", explain with reference to real files and line ranges, then quiz me with 3 questions.
Workflow
Start in Plan mode: propose files to change and wait for my approval before editing.
One feature per branch/commit. Small diffs. Show me the diff summary at the end.
If requirements are ambiguous, ask one concise question rather than guessing.
Design system (target)

Dark navy base with mint/coral accents. Glassmorphism: translucent surfaces (bg-white/5, backdrop-blur-xl, 1px border-white/10), soft glows, consistent radius. Motion: purposeful, 200–600 ms, ease-out; respect prefers-reduced-motion. Reuse components in components/UI.jsx instead of inventing new card styles.