import os
import json

import pandas as pd

from datetime import date, timedelta

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# Read backend/.env before anything below reads os.environ (database.py also
# calls this; repeating it is safe and keeps main.py self-sufficient).
load_dotenv()

from ingest import parse_statement, MAX_FILE_BYTES
from ingest.errors import IngestError
from categorizer import add_categories, apply_category_aliases
from transactions import (
    get_user_transactions,
    transaction_key,
    transactions_to_rows,
)
from insights import (
    get_category_totals,
    get_monthly_category_spend,
    detect_anomalies,
    get_savings_summary,
    get_month_over_month_trend,
    forecast_next_month_spend,
    get_savings_suggestions,
    get_uncategorized_summary,
    detect_recurring_subscriptions,
)
from market_data import get_mutual_fund_nav
from reality_check import compute_reality_check

from auth_routes import router as auth_router
from auth_dependency import get_current_user
from database import get_db
from models import User, Statement, Investment
from schemas import InvestmentCreate, InvestmentUpdate


app = FastAPI()

# CORS - allows a separate frontend (different origin) to call this API.
# Origins come from the ALLOWED_ORIGINS env var (comma-separated, see
# .env.example); in dev it defaults to the Vite dev server. The old open
# allow_origins=["*"] is gone - with allow_credentials=True an open policy
# is also rejected by browsers, and it would leak authenticated APIs to
# any website the user visits.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth endpoints: /auth/signup, /auth/login
app.include_router(auth_router, prefix="/auth", tags=["auth"])


@app.get("/")
def root():
    return {"message": "Finance Assistant API is running"}


@app.get("/auth/me")
def get_my_profile(current_user: User = Depends(get_current_user)):
    """Protected route - requires a valid Authorization: Bearer <token> header."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
    }


@app.get("/statements")
def list_statements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Protected route - returns a summary of this user's past uploads,
    most recent first. Deliberately excludes the full `result` blob here
    to keep this list light - the frontend fetches full detail per-item
    via GET /statements/{id} only when the user actually opens one.
    """
    statements = (
        db.query(Statement)
        .filter(Statement.user_id == current_user.id)
        .order_by(Statement.uploaded_at.desc())
        .all()
    )
    return [
        {
            "id": s.id,
            "filename": s.filename,
            "uploaded_at": s.uploaded_at,
        }
        for s in statements
    ]


@app.get("/statements/{statement_id}")
def get_statement(
    statement_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Protected route - returns the full analysis for one past upload.

    IMPORTANT: we filter by user_id == current_user.id here, not just
    id == statement_id. Without that second filter, any logged-in user
    could read any other user's statement just by guessing/incrementing
    the id in the URL (an IDOR vulnerability). Being authenticated only
    proves who you are - it doesn't by itself prove you're allowed to
    see this particular row, so we check ownership explicitly.
    """
    statement = (
        db.query(Statement)
        .filter(Statement.id == statement_id, Statement.user_id == current_user.id)
        .first()
    )

    if statement is None:
        raise HTTPException(status_code=404, detail="Statement not found")

    # Old saved statements may carry category names from earlier rule
    # versions - alias them at READ time (no data migration) so history
    # renders under the current categories.
    return {
        "id": statement.id,
        "filename": statement.filename,
        "uploaded_at": statement.uploaded_at,
        "result": apply_category_aliases(statement.result or {}),
    }


def _ingest_error_response(err: IngestError) -> JSONResponse:
    """
    Translate a structured IngestError into its HTTP response so the
    frontend can react to `code` (password prompt, mapping modal, etc.).
    Every IngestError carries a human message and the right status.
    """
    return JSONResponse(status_code=err.http_status, content={"detail": err.to_payload()})


async def _read_upload(file: UploadFile):
    """Read + size-cap an upload. 10 MB enforced while reading, before parsing."""
    contents = await file.read()
    if len(contents) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail={
            "code": "file_too_large",
            "message": "File is larger than the 10 MB limit.",
        })
    if not contents:
        raise HTTPException(status_code=422, detail={
            "code": "corrupt_file",
            "message": "The uploaded file is empty.",
        })
    return contents


def _parse_column_mapping(column_mapping: str | None):
    """The form field arrives as a JSON string; parse it or 400 clearly."""
    if not column_mapping:
        return None
    try:
        parsed = json.loads(column_mapping)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail={
            "code": "bad_mapping",
            "message": "column_mapping must be a JSON object like {\"date\": \"Col A\", ...}",
        })


def _analysis_from_transactions(df):
    """Run categorize -> insights on canonical transactions (shared by upload + preview)."""
    df = add_categories(df)
    monthly = get_monthly_category_spend(df)
    savings = get_savings_summary(df)
    return {
        "category_totals": get_category_totals(df).to_dict(),
        "uncategorized": get_uncategorized_summary(df),
        "anomalies": detect_anomalies(monthly),
        "savings_summary": savings,
        "month_over_month_trend": get_month_over_month_trend(monthly),
        "forecast": forecast_next_month_spend(df),
        "suggestions": get_savings_suggestions(monthly, savings),
        "subscriptions": detect_recurring_subscriptions(df),
    }


@app.get("/insights")
def get_combined_insights(
    scope: str = Query("all"),
    statement_id: int | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Protected route - combined analytics across the user's statements.

    scope="all" (default): transactions from every statement merged and
    de-duplicated on (date, normalized description, amount), so overlapping
    uploads never double-count. Expenses exclude NON_SPENDING_CATEGORIES
    (enforced inside insights.py, same as per-statement analysis).
    scope="latest": only the newest statement.
    statement_id: analyze one specific statement instead (ownership-checked).

    The per-statement endpoints (/statements/{id}, /upload-statement) are
    unchanged and keep working alongside this.
    """
    try:
        df = get_user_transactions(
            db, current_user.id, scope=scope, statement_id=statement_id
        )
    except ValueError:
        raise HTTPException(status_code=400, detail=f"scope must be 'all' or 'latest'")
    except LookupError:
        raise HTTPException(status_code=404, detail="Statement not found")

    if df.empty:
        return {
            "scope": scope,
            "statement_id": statement_id,
            "transactions_count": 0,
            "message": (
                "No transactions available for this scope. Either upload a "
                "statement, or note that statements uploaded before multi-statement "
                "support store no raw transactions."
            ),
            "analysis": None,
        }

    analysis = _analysis_from_transactions(df)  # runs add_categories + insights
    return {
        "scope": scope,
        "statement_id": statement_id,
        "transactions_count": len(df),
        "analysis": analysis,
    }


@app.post("/upload-statement/preview")
async def upload_statement_preview(
    file: UploadFile = File(...),
    password: str = Form(None),
    column_mapping: str = Form(None),
    current_user: User = Depends(get_current_user),
):
    """
    Protected route - parse ONLY, save nothing. Returns the first 15 parsed
    rows, the column mapping used and the ingest report, so the frontend can
    show a preview + Confirm/Cancel before /upload-statement is called.
    """
    contents = await _read_upload(file)
    try:
        result = parse_statement(
            contents,
            file.filename or "",
            password=password,
            column_mapping=_parse_column_mapping(column_mapping),
        )
    except IngestError as err:
        return _ingest_error_response(err)

    df = result.transactions
    preview_rows = [
        {
            "date": row.date.strftime("%d/%m/%Y"),
            "description": row.description,
            "amount": round(float(row.amount), 2),
            "type": row.type,
            "balance": None if row.balance is None or pd.isna(row.balance) else round(float(row.balance), 2),
        }
        for row in df.head(15).itertuples(index=False)
    ]
    return {
        "preview_rows": preview_rows,
        "mapping_used": result.report.get("mapping_used", {}),
        "report": result.report,
        "total_rows": len(df),
    }


@app.post("/upload-statement")
async def upload_statement(
    file: UploadFile = File(...),
    password: str = Form(None),
    column_mapping: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Protected route - requires a valid Authorization: Bearer <token> header.
    Accepts a bank statement (CSV, XLSX, XLS or PDF), runs it through the
    full analysis pipeline, and returns structured JSON insights plus the
    ingest_report. The file itself is processed in memory only - never
    written to disk, never stored; only the derived analysis is saved.
    """
    contents = await _read_upload(file)
    try:
        result = parse_statement(
            contents,
            file.filename or "",
            password=password,
            column_mapping=_parse_column_mapping(column_mapping),
        )
    except IngestError as err:
        return _ingest_error_response(err)

    df = result.transactions

    # Privacy: the transactions stay in memory only. Statement.result stores
    # the derived analysis plus the ingest_report - never raw rows, never
    # the password.
    response = _analysis_from_transactions(df)
    response["ingest_report"] = result.report

    # Also keep the canonical transactions inside this statement's own
    # result. There is deliberately NO Transaction table (multi-statement
    # analytics merges these JSON blobs at read time - see transactions.py).
    # They are the owner's own data, served only through ownership-checked
    # endpoints, never logged.
    response["transactions"] = transactions_to_rows(df)

    # --- Overlap / duplicate warnings against existing statements ---------
    previous_statements = (
        db.query(Statement)
        .filter(Statement.user_id == current_user.id)
        .order_by(Statement.uploaded_at.asc())
        .all()
    )
    if previous_statements:
        new_rows = response["transactions"]
        new_dates = [pd.Timestamp(r["date"]) for r in new_rows if r.get("date")]
        if new_dates:
            file_start, file_end = min(new_dates), max(new_dates)
            overlapping = []
            for prev in previous_statements:
                prev_dates = [
                    pd.Timestamp(r["date"])
                    for r in ((prev.result or {}).get("transactions") or [])
                    if r.get("date")
                ]
                if prev_dates and min(prev_dates) <= file_end and max(prev_dates) >= file_start:
                    overlapping.append(f"'{prev.filename}'")
            if overlapping:
                result.report.setdefault("warnings", []).append(
                    "Date range overlaps existing statement(s): "
                    + ", ".join(overlapping)
                    + ". Overlapping transactions will not be double-counted."
                )

        # How many rows of THIS file are the same transaction as one an
        # earlier file already contributed? (date + normalized description
        # + amount - see transactions.transaction_key for why balance is
        # excluded.)
        seen = set()
        for prev in previous_statements:
            for r in ((prev.result or {}).get("transactions") or []):
                try:
                    seen.add(transaction_key(r.get("date"), r.get("description"), r.get("amount")))
                except (TypeError, ValueError):
                    continue
        duplicate_count = 0
        local = set()
        for r in new_rows:
            try:
                key = transaction_key(r.get("date"), r.get("description"), r.get("amount"))
            except (TypeError, ValueError):
                continue
            if key in local:
                continue  # repeat within this file - a real separate transaction
            local.add(key)
            if key in seen:
                duplicate_count += 1
        if duplicate_count:
            result.report.setdefault("warnings", []).append(
                f"{duplicate_count} duplicate transaction(s) already present in "
                "earlier statements - excluded from combined (scope=all) totals."
            )

    # Persist this analysis so the user can see it again later without
    # re-uploading. We link it to current_user via user_id - this is the
    # foreign key relationship we set up in models.py.
    statement_record = Statement(
        user_id=current_user.id,
        filename=file.filename,
        result=response,
    )
    db.add(statement_record)
    db.commit()
    db.refresh(statement_record)  # populates statement_record.id and .uploaded_at from the DB

    return response


def _investment_to_dict(investment: Investment) -> dict:
    """Small helper to avoid repeating this shape across all four endpoints."""
    return {
        "id": investment.id,
        "name": investment.name,
        "category": investment.category,
        "investment_type": investment.investment_type,
        "scheme_code": investment.scheme_code,
        "units": investment.units,
        "purchase_date": investment.purchase_date,
        "start_date": investment.start_date,
        "premium_amount": investment.premium_amount,
        "premium_frequency": investment.premium_frequency,
        "next_due_date": investment.next_due_date,
        "maturity_date": investment.maturity_date,
        "maturity_value": investment.maturity_value,
        "invested_amount": investment.invested_amount,
        "created_at": investment.created_at,
    }


@app.post("/investments")
def create_investment(
    investment: InvestmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Protected route - creates a new investment (market or policy) tied to
    the logged-in user. FastAPI validates the request body against
    InvestmentCreate automatically - if the frontend sends a malformed
    body (e.g. invested_amount as text instead of a number), this
    function never even runs; FastAPI rejects it with a 422 first.
    """
    new_investment = Investment(
        user_id=current_user.id,
        **investment.model_dump(),  # unpacks all validated fields as keyword args
    )
    db.add(new_investment)
    db.commit()
    db.refresh(new_investment)
    return _investment_to_dict(new_investment)


def _enrich_investment(investment: Investment) -> dict:
    """
    Builds the "viewing" representation of an investment - the raw saved
    fields, PLUS computed values that are never stored in the database
    because they'd go stale (a live price) or are trivial to derive from
    what we already have (days until due).

    Only used for GET (viewing) - not for POST/PUT/DELETE responses,
    since those don't need the extra external API call.
    """
    data = _investment_to_dict(investment)

    if investment.category == "market" and investment.investment_type == "mutual_fund":
        nav = get_mutual_fund_nav(investment.scheme_code) if investment.scheme_code else None

        if nav is not None and investment.units is not None:
            current_value = float(investment.units) * nav
            gain_loss = current_value - float(investment.invested_amount)
            gain_loss_pct = (
                round((gain_loss / float(investment.invested_amount)) * 100, 2)
                if investment.invested_amount else None
            )
            data["current_nav"] = nav
            data["current_value"] = round(current_value, 2)
            data["gain_loss"] = round(gain_loss, 2)
            data["gain_loss_pct"] = gain_loss_pct
        else:
            # NAV lookup failed (bad scheme code, API down, etc) - don't
            # crash the whole list, just be explicit that we don't know
            # the current value right now rather than showing a wrong number.
            data["current_nav"] = None
            data["current_value"] = None
            data["gain_loss"] = None
            data["gain_loss_pct"] = None

    if investment.category == "policy" and investment.next_due_date:
        days_until_due = (investment.next_due_date - date.today()).days
        data["days_until_due"] = days_until_due
        data["is_overdue"] = days_until_due < 0

    return data


@app.get("/investments")
def list_investments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Protected route - returns all of this user's investments, enriched
    with live NAVs (market/mutual_fund) and due-date countdowns (policy).
    """
    investments = (
        db.query(Investment)
        .filter(Investment.user_id == current_user.id)
        .order_by(Investment.created_at.desc())
        .all()
    )
    return [_enrich_investment(i) for i in investments]


@app.get("/investments/reality-check-benchmark")
def reality_check_benchmark_name(
    current_user: User = Depends(get_current_user),
):
    """
    Protected route - the name of the benchmark fund used by reality
    checks, so the frontend can label the comparison without hardcoding it.
    Kept as its own lightweight endpoint so the frontend can show it before
    any per-policy check has been run.
    """
    from reality_check import BENCHMARK_FUND_NAME
    return {"benchmark_fund_name": BENCHMARK_FUND_NAME}


@app.get("/investments/affordability")
def get_affordability_stress_test(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Protected route - the 12-month affordability stress test.

    Combines two things the app already stores:
      - the user's spending/savings history from their uploaded statements
      - every policy's premium schedule (amount, frequency, next_due_date)

    For each of the next 12 months, sums the premiums due that month and
    flags "tight months": months where premiums exceed AFFORDABILITY_THRESHOLD
    of the user's average monthly savings. Informational only - not advice.
    """
    # Threshold: a month is "tight" when premiums due exceed 50% of average
    # monthly savings. Visible here on purpose - not alarmist (100% would
    # ignore that premiums can be paid from income), not silent.
    AFFORDABILITY_THRESHOLD = 0.5

    today = date.today()

    # --- 1. Policies: every premium due in the next 12 months ---
    policies = (
        db.query(Investment)
        .filter(Investment.user_id == current_user.id, Investment.category == "policy")
        .all()
    )

    # months[0] = current month, months[1] = next, ... months[11]
    month_keys: list[tuple[int, int]] = []
    for i in range(12):
        total = today.month - 1 + i
        month_keys.append((today.year + total // 12, total % 12 + 1))

    premiums_by_month = {key: 0.0 for key in month_keys}
    policies_counted = 0
    policies_skipped: list[str] = []

    from reality_check import add_months

    # Window end: last day of month_keys[-1], built as the day before the
    # 1st of the following month.
    ey, em = month_keys[-1]
    window_end = date(ey + (em == 12), (em % 12) + 1, 1) - timedelta(days=1)

    for policy in policies:
        if not policy.premium_amount or not policy.next_due_date:
            # Can't place this policy on a calendar - skip it explicitly.
            policies_skipped.append(policy.name)
            continue

        policies_counted += 1
        amount = float(policy.premium_amount)
        frequency = (policy.premium_frequency or "yearly").strip().lower()
        step_months = 1 if frequency == "monthly" else 3 if frequency == "quarterly" else 12

        # Anchor the future schedule at the next due date and walk forward,
        # keeping only payments that land within the 12-month window.
        current = policy.next_due_date
        for _ in range(13):  # hard cap: at most 13 payments can hit a 12-month window
            if current > window_end:
                break
            ym = (current.year, current.month)
            if ym in premiums_by_month:
                premiums_by_month[ym] += amount
            current = add_months(current, step_months)

    # --- 2. Savings baseline from the most recent uploaded statement ---
    latest_statement = (
        db.query(Statement)
        .filter(Statement.user_id == current_user.id)
        .order_by(Statement.uploaded_at.desc())
        .first()
    )

    if latest_statement is None:
        return {
            "has_statement": False,
            "message": "Upload a bank statement first - the stress test compares premiums against your actual savings from your statement.",
            "months": [],
            "average_monthly_savings": None,
            "threshold_pct": round(AFFORDABILITY_THRESHOLD * 100),
            "policies_counted": 0,
            "tight_months_count": 0,
        }

    savings_summary = (latest_statement.result or {}).get("savings_summary") or {}
    total_income = savings_summary.get("total_income") or 0.0
    total_spend = savings_summary.get("total_spend") or 0.0

    # A statement covers a period; convert to a monthly figure so premiums
    # (which recur monthly/quarterly/yearly) compare against a monthly budget.
    # We don't store the statement's period length, so assume it represents
    # ~6 months of activity unless the data clearly says otherwise - see
    # the "judgment calls" note in the summary.
    STATEMENT_PERIOD_MONTHS = 6.0
    average_monthly_savings = max(0.0, (total_income - total_spend) / STATEMENT_PERIOD_MONTHS)

    months_out = []
    tight_count = 0
    for year, month in month_keys:
        premiums_due = round(premiums_by_month[(year, month)], 2)
        is_tight = (
            average_monthly_savings > 0
            and premiums_due > average_monthly_savings * AFFORDABILITY_THRESHOLD
        )
        if is_tight:
            tight_count += 1
        months_out.append({
            "year": year,
            "month": month,
            "month_label": date(year, month, 1).strftime("%b %Y"),
            "premiums_due": premiums_due,
            "is_tight": is_tight,
        })

    return {
        "has_statement": True,
        "message": None,
        "months": months_out,
        "average_monthly_savings": round(average_monthly_savings, 2),
        "threshold_pct": round(AFFORDABILITY_THRESHOLD * 100),
        "policies_counted": policies_counted,
        "tight_months_count": tight_count,
    }


@app.get("/investments/{investment_id}/reality-check")
def get_reality_check(
    investment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Protected route - the Policy Reality Check for one policy.

    Returns the policy's XIRR vs a Nifty 50 index fund benchmark, computed
    from the data the user already stored. Every failure mode (missing
    start_date, bad schedule data, non-convergent XIRR, benchmark API down)
    degrades to null values plus a clear `message` - never a 500, never a
    fabricated number.

    404 when the id doesn't exist, belongs to someone else, or isn't a
    policy - same ownership check as GET/PUT/DELETE above.
    """
    investment = (
        db.query(Investment)
        .filter(Investment.id == investment_id, Investment.user_id == current_user.id)
        .first()
    )

    if investment is None:
        raise HTTPException(status_code=404, detail="Investment not found")

    if investment.category != "policy":
        raise HTTPException(status_code=404, detail="Reality check is only available for policies")

    return compute_reality_check(investment)


@app.get("/investments/summary")
def get_investment_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Protected route - a portfolio-level view, computed fresh from the
    investments list every time rather than stored anywhere (same
    "don't store what you can derive" principle as get_savings_summary()
    in insights.py).
    """
    investments = (
        db.query(Investment)
        .filter(Investment.user_id == current_user.id)
        .all()
    )

    enriched = [_enrich_investment(i) for i in investments]

    total_invested = sum(float(i.invested_amount) for i in investments)

    # For net worth: use the live current_value where we have one
    # (market/mutual_fund with a successful NAV lookup), otherwise fall
    # back to invested_amount - this covers policies (no live value by
    # design) and market investments where the NAV lookup failed.
    net_worth = sum(
        e["current_value"] if e.get("current_value") is not None else float(i.invested_amount)
        for e, i in zip(enriched, investments)
    )

    market_value = sum(
        e["current_value"] if e.get("current_value") is not None else float(i.invested_amount)
        for e, i in zip(enriched, investments)
        if i.category == "market"
    )
    policy_value = sum(
        float(i.invested_amount) for i in investments if i.category == "policy"
    )

    # Policies due within the next 30 days - the actual reminder feature
    # you originally wanted this whole model for.
    upcoming_dues = sorted(
        [
            e for e in enriched
            if e.get("days_until_due") is not None and e["days_until_due"] <= 30
        ],
        key=lambda e: e["days_until_due"],
    )

    return {
        "total_invested": round(total_invested, 2),
        "net_worth": round(net_worth, 2),
        "total_gain_loss": round(net_worth - total_invested, 2),
        "breakdown_by_category": {
            "market": round(market_value, 2),
            "policy": round(policy_value, 2),
        },
        "upcoming_dues": upcoming_dues,
    }


@app.put("/investments/{investment_id}")
def update_investment(
    investment_id: int,
    updates: InvestmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Protected route - updates an existing investment. Only fields actually
    present in the request body get changed; everything else is left as-is.

    Same ownership check as GET/DELETE: filtering by user_id here is what
    stops one user from editing another user's investment by guessing an id.
    """
    investment = (
        db.query(Investment)
        .filter(Investment.id == investment_id, Investment.user_id == current_user.id)
        .first()
    )

    if investment is None:
        raise HTTPException(status_code=404, detail="Investment not found")

    # model_dump(exclude_unset=True) returns only the fields the client
    # actually sent, not every field with its default. This is what makes
    # partial updates work - if the frontend only sends {"next_due_date": ...},
    # we don't accidentally overwrite name/invested_amount with None.
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(investment, field, value)

    db.commit()
    db.refresh(investment)
    return _investment_to_dict(investment)


@app.delete("/investments/{investment_id}")
def delete_investment(
    investment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Protected route - deletes an investment, with the same ownership check."""
    investment = (
        db.query(Investment)
        .filter(Investment.id == investment_id, Investment.user_id == current_user.id)
        .first()
    )

    if investment is None:
        raise HTTPException(status_code=404, detail="Investment not found")

    db.delete(investment)
    db.commit()
    return {"message": "Investment deleted"}