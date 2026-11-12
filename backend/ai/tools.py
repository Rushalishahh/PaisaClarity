"""Safe financial query tools for PaisaClarity AI Copilot (Phase 9).

These tools are read-only and strictly scoped to the authenticated user.
They query normalized transactions, accounts, budgets, goals, recurring payments,
alerts, and investments without exposing raw credentials or allowing mutations.
"""

from collections import defaultdict
import calendar
import datetime as dt
from decimal import Decimal
import math
from typing import Any, Callable, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import (
    User,
    FinancialAccount,
    Transaction,
    Budget,
    BudgetAllocation,
    SavingsGoal,
    SavingsContribution,
    RecurringPayment,
    FinancialAlert,
    Investment,
)
from cashflow_routes import _compute_account_balance
from budget_routes import _calculate_budget_metrics
from savings_routes import _calculate_goal_metrics
from categorizer import NON_SPENDING_CATEGORIES
from forecasting import forecast_hybrid_month_end


def _parse_date(val: Any) -> Optional[dt.date]:
    """Helper to safely parse an ISO date string or return date object."""
    if val is None or val == "":
        return None
    if isinstance(val, dt.date):
        return val
    try:
        return dt.date.fromisoformat(str(val).strip())
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Tool 1: Spending Summary
# ---------------------------------------------------------------------------
def get_spending_summary(
    db: Session,
    user: User,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    account_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Get total income, total expenses, net savings, and savings rate for a date range."""
    d_start = _parse_date(start_date)
    d_end = _parse_date(end_date)

    query = db.query(Transaction).filter(Transaction.user_id == user.id)
    if d_start:
        query = query.filter(Transaction.date >= d_start)
    if d_end:
        query = query.filter(Transaction.date <= d_end)
    if account_id:
        query = query.filter(Transaction.account_id == account_id)

    txs = query.all()
    tot_income = Decimal("0.00")
    tot_expense = Decimal("0.00")
    count = 0

    for tx in txs:
        meta = tx.import_metadata or {}
        if meta.get("is_overlap") is True:
            continue
        amt = Decimal(str(tx.amount)).quantize(Decimal("0.01"))
        cat = (tx.category or "").strip()
        if cat in NON_SPENDING_CATEGORIES:
            continue

        if tx.classification == "income":
            tot_income += amt
            count += 1
        elif tx.classification == "expense":
            tot_expense += amt
            count += 1

    net_cashflow = tot_income - tot_expense
    savings_rate = (
        round(float((net_cashflow / tot_income) * 100), 2)
        if tot_income > Decimal("0.00")
        else 0.0
    )

    return {
        "period_start": str(d_start) if d_start else "earliest",
        "period_end": str(d_end) if d_end else "latest",
        "total_income": float(tot_income),
        "total_expenses": float(tot_expense),
        "net_cash_flow": float(net_cashflow),
        "savings_rate_pct": savings_rate,
        "transaction_count": count,
    }


# ---------------------------------------------------------------------------
# Tool 2: Category Breakdown
# ---------------------------------------------------------------------------
def get_category_breakdown(
    db: Session,
    user: User,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Get category-wise spending breakdown, percentage share, and top expense categories."""
    d_start = _parse_date(start_date)
    d_end = _parse_date(end_date)

    query = db.query(Transaction).filter(
        Transaction.user_id == user.id,
        Transaction.classification == "expense",
    )
    if d_start:
        query = query.filter(Transaction.date >= d_start)
    if d_end:
        query = query.filter(Transaction.date <= d_end)

    cat_map: Dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    cat_counts: Dict[str, int] = defaultdict(int)
    total_spend = Decimal("0.00")

    for tx in query.all():
        meta = tx.import_metadata or {}
        if meta.get("is_overlap") is True:
            continue
        cat = (tx.category or "Uncategorized").strip()
        if cat in NON_SPENDING_CATEGORIES:
            continue
        amt = Decimal(str(tx.amount)).quantize(Decimal("0.01"))
        cat_map[cat] += amt
        cat_counts[cat] += 1
        total_spend += amt

    sorted_cats = sorted(cat_map.items(), key=lambda x: x[1], reverse=True)
    categories = []
    for cat_name, amt in sorted_cats[:limit]:
        pct = round(float((amt / total_spend) * 100), 2) if total_spend > Decimal("0.00") else 0.0
        categories.append({
            "category": cat_name,
            "amount": float(amt),
            "percentage": pct,
            "transaction_count": cat_counts[cat_name],
        })

    return {
        "period_start": str(d_start) if d_start else "all-time",
        "period_end": str(d_end) if d_end else "all-time",
        "total_expense": float(total_spend),
        "category_count": len(cat_map),
        "breakdown": categories,
    }


# ---------------------------------------------------------------------------
# Tool 3: Compare Spending Periods
# ---------------------------------------------------------------------------
def compare_spending_periods(
    db: Session,
    user: User,
    period1_start: str,
    period1_end: str,
    period2_start: str,
    period2_end: str,
) -> Dict[str, Any]:
    """Compare income and expense trends and category changes between two periods."""
    p1_summary = get_spending_summary(db, user, period1_start, period1_end)
    p2_summary = get_spending_summary(db, user, period2_start, period2_end)

    p1_exp = Decimal(str(p1_summary["total_expenses"]))
    p2_exp = Decimal(str(p2_summary["total_expenses"]))
    p1_inc = Decimal(str(p1_summary["total_income"]))
    p2_inc = Decimal(str(p2_summary["total_income"]))

    exp_change_pct = (
        round(float(((p2_exp - p1_exp) / p1_exp) * 100), 2)
        if p1_exp > Decimal("0.00")
        else 0.0
    )
    inc_change_pct = (
        round(float(((p2_inc - p1_inc) / p1_inc) * 100), 2)
        if p1_inc > Decimal("0.00")
        else 0.0
    )

    return {
        "period_1": {
            "start": period1_start,
            "end": period1_end,
            "income": float(p1_inc),
            "expenses": float(p1_exp),
            "net": float(p1_inc - p1_exp),
        },
        "period_2": {
            "start": period2_start,
            "end": period2_end,
            "income": float(p2_inc),
            "expenses": float(p2_exp),
            "net": float(p2_inc - p2_exp),
        },
        "expense_change_amount": float(p2_exp - p1_exp),
        "expense_change_pct": exp_change_pct,
        "income_change_amount": float(p2_inc - p1_inc),
        "income_change_pct": inc_change_pct,
    }


# ---------------------------------------------------------------------------
# Tool 4: Monthly Cashflow History
# ---------------------------------------------------------------------------
def get_monthly_cashflow(
    db: Session,
    user: User,
    months: int = 6,
) -> Dict[str, Any]:
    """Get month-by-month historical cash flow trends (income, expenses, net)."""
    months = max(1, min(months, 36))
    today = dt.date.today()
    start_date = dt.date(today.year, today.month, 1)
    # Go back (months - 1) months
    m = start_date.month - (months - 1)
    y = start_date.year
    while m <= 0:
        m += 12
        y -= 1
    start_date = dt.date(y, m, 1)

    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id, Transaction.date >= start_date)
        .all()
    )

    monthly_map: Dict[str, Dict[str, Decimal]] = defaultdict(
        lambda: {"income": Decimal("0.00"), "expense": Decimal("0.00")}
    )

    for tx in txs:
        meta = tx.import_metadata or {}
        if meta.get("is_overlap") is True:
            continue
        cat = (tx.category or "").strip()
        if cat in NON_SPENDING_CATEGORIES:
            continue
        key = tx.date.strftime("%Y-%m")
        amt = Decimal(str(tx.amount)).quantize(Decimal("0.01"))
        if tx.classification == "income":
            monthly_map[key]["income"] += amt
        elif tx.classification == "expense":
            monthly_map[key]["expense"] += amt

    sorted_keys = sorted(monthly_map.keys())
    history = []
    for k in sorted_keys:
        inc = monthly_map[k]["income"]
        exp = monthly_map[k]["expense"]
        net = inc - exp
        savings_rate = round(float((net / inc) * 100), 2) if inc > Decimal("0.00") else 0.0
        history.append({
            "month": k,
            "income": float(inc),
            "expenses": float(exp),
            "net": float(net),
            "savings_rate_pct": savings_rate,
        })

    return {
        "months_requested": months,
        "history": history,
    }


# ---------------------------------------------------------------------------
# Tool 5: Account Summary
# ---------------------------------------------------------------------------
def get_account_summary(
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """Get all financial accounts, verified balances, liquid assets total, and status."""
    accounts = (
        db.query(FinancialAccount)
        .filter(FinancialAccount.user_id == user.id, FinancialAccount.is_archived == False)
        .all()
    )

    account_list = []
    total_liquid = Decimal("0.00")

    for acc in accounts:
        bal, credits, debits = _compute_account_balance(db, acc)
        if bal is not None:
            total_liquid += bal
        account_list.append({
            "id": acc.id,
            "name": acc.name,
            "type": acc.account_type,
            "currency": acc.currency,
            "is_reconciled": acc.is_reconciled,
            "verified_balance": float(bal) if bal is not None else None,
            "total_credits": float(credits),
            "total_debits": float(debits),
            "masked_identifier": acc.masked_identifier,
        })

    return {
        "accounts": account_list,
        "total_liquid_verified_balance": float(total_liquid),
        "reconciled_accounts_count": sum(1 for a in account_list if a["is_reconciled"]),
        "unreconciled_accounts_count": sum(1 for a in account_list if not a["is_reconciled"]),
    }


# ---------------------------------------------------------------------------
# Tool 6: Budget Status
# ---------------------------------------------------------------------------
def get_budget_status(
    db: Session,
    user: User,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """Get budget status, limits, category spending allocations, and over-budget warnings."""
    today = dt.date.today()
    q_month = month or today.month
    q_year = year or today.year

    budget = (
        db.query(Budget)
        .filter(
            Budget.user_id == user.id,
            Budget.month == q_month,
            Budget.year == q_year,
        )
        .first()
    )

    if not budget:
        return {
            "has_budget": False,
            "month": q_month,
            "year": q_year,
            "message": f"No budget defined for {q_year}-{q_month:02d}.",
        }

    metrics = _calculate_budget_metrics(db, budget)
    allocations = []
    for alloc in metrics.allocations:
        allocations.append({
            "category": alloc.category_name,
            "allocated_limit": float(alloc.allocated_amount),
            "actual_spent": float(alloc.actual_spent),
            "utilization_pct": alloc.utilization_pct,
            "remaining_amount": float(alloc.remaining),
            "is_over_budget": alloc.is_exceeded,
            "warning_threshold_exceeded": alloc.is_warning,
        })

    return {
        "has_budget": True,
        "month": q_month,
        "year": q_year,
        "total_budget_limit": float(metrics.total_budget_limit) if metrics.total_budget_limit else None,
        "total_actual_spent": float(metrics.total_spent),
        "total_remaining": float(metrics.total_remaining),
        "total_utilization_pct": metrics.overall_utilization_pct,
        "is_over_budget": metrics.overall_is_exceeded,
        "total_allocated": float(metrics.total_allocated),
        "allocations": allocations,
    }


# ---------------------------------------------------------------------------
# Tool 7: Savings Goals
# ---------------------------------------------------------------------------
def get_savings_goals(
    db: Session,
    user: User,
    include_archived: bool = False,
) -> Dict[str, Any]:
    """Get all savings goals, target amounts, current saved, progress %, and monthly target."""
    query = db.query(SavingsGoal).filter(SavingsGoal.user_id == user.id)
    if not include_archived:
        query = query.filter(SavingsGoal.is_archived == False)

    goals = query.all()
    results = []
    total_target = Decimal("0.00")
    total_saved = Decimal("0.00")

    for g in goals:
        resp = _calculate_goal_metrics(g)
        total_target += resp.target_amount
        total_saved += resp.total_saved
        results.append({
            "id": resp.id,
            "name": resp.name,
            "target_amount": float(resp.target_amount),
            "current_saved": float(resp.total_saved),
            "remaining_amount": float(resp.remaining_target),
            "progress_percentage": resp.completion_pct,
            "target_date": str(resp.target_date) if resp.target_date else None,
            "monthly_savings_needed": float(resp.monthly_savings_needed) if resp.monthly_savings_needed else None,
            "is_completed": resp.is_completed,
            "is_archived": resp.is_archived,
        })

    return {
        "goals": results,
        "total_target_amount": float(total_target),
        "total_saved_amount": float(total_saved),
        "overall_progress_pct": round(float((total_saved / total_target) * 100), 2) if total_target > Decimal("0.00") else 0.0,
    }


# ---------------------------------------------------------------------------
# Tool 8: Recurring Payments
# ---------------------------------------------------------------------------
def get_recurring_payments(
    db: Session,
    user: User,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """Get recurring subscriptions, upcoming bills, frequencies, and monthly commitment."""
    query = db.query(RecurringPayment).filter(RecurringPayment.user_id == user.id)
    if status:
        query = query.filter(RecurringPayment.status == status)
    else:
        query = query.filter(RecurringPayment.status.in_(["confirmed", "detected"]))

    items = query.all()
    results = []
    tot_monthly = Decimal("0.00")

    for r in items:
        amt = Decimal(str(r.average_amount)).quantize(Decimal("0.01"))
        # Normalize to monthly equivalent
        if r.frequency == "weekly":
            monthly_equiv = amt * Decimal("4.33")
        elif r.frequency == "quarterly":
            monthly_equiv = amt / Decimal("3.0")
        elif r.frequency == "yearly":
            monthly_equiv = amt / Decimal("12.0")
        else:
            monthly_equiv = amt
        tot_monthly += monthly_equiv

        results.append({
            "id": r.id,
            "name": r.name,
            "category": r.category,
            "frequency": r.frequency,
            "amount": float(amt),
            "monthly_equivalent": round(float(monthly_equiv), 2),
            "next_expected_date": str(r.next_expected_date) if r.next_expected_date else None,
            "status": r.status,
            "is_auto_detected": r.is_auto_detected,
        })

    return {
        "recurring_payments": results,
        "total_monthly_commitment": round(float(tot_monthly), 2),
        "active_count": len(results),
    }


# ---------------------------------------------------------------------------
# Tool 9: Financial Alerts
# ---------------------------------------------------------------------------
def get_financial_alerts(
    db: Session,
    user: User,
    unread_only: bool = True,
) -> Dict[str, Any]:
    """Get active financial alerts (budget overruns, upcoming dues, unusual spending)."""
    query = db.query(FinancialAlert).filter(FinancialAlert.user_id == user.id)
    if unread_only:
        query = query.filter(FinancialAlert.is_read == False)

    alerts = query.order_by(FinancialAlert.created_at.desc()).limit(20).all()
    results = []
    for a in alerts:
        results.append({
            "id": a.id,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "title": a.title,
            "message": a.message,
            "is_read": a.is_read,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })

    return {
        "alerts": results,
        "count": len(results),
    }


# ---------------------------------------------------------------------------
# Tool 10: Investment Summary
# ---------------------------------------------------------------------------
def get_investment_summary(
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """Get total portfolio value, category breakdown (market vs policy), and invested amounts."""
    investments = db.query(Investment).filter(Investment.user_id == user.id).all()
    tot_invested = Decimal("0.00")
    market_val = Decimal("0.00")
    policy_val = Decimal("0.00")

    items = []
    for inv in investments:
        amt = Decimal(str(inv.invested_amount or 0)).quantize(Decimal("0.01"))
        tot_invested += amt
        if inv.category == "market":
            market_val += amt
        else:
            policy_val += amt

        items.append({
            "id": inv.id,
            "name": inv.name,
            "category": inv.category,
            "investment_type": inv.investment_type,
            "invested_amount": float(amt),
            "next_due_date": str(inv.next_due_date) if inv.next_due_date else None,
            "maturity_date": str(inv.maturity_date) if inv.maturity_date else None,
        })

    return {
        "total_invested": float(tot_invested),
        "market_investments_total": float(market_val),
        "policy_investments_total": float(policy_val),
        "investment_count": len(items),
        "investments": items,
    }


# ---------------------------------------------------------------------------
# Tool 11: Spending Forecast
# ---------------------------------------------------------------------------
def get_spending_forecast(
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """Forecast end-of-month spending based on current month-to-date pace, IQR outlier filtering, and recurring bills."""
    today = dt.date.today()
    _, days_in_month = calendar.monthrange(today.year, today.month)
    days_elapsed = max(1, today.day)
    days_remaining = max(0, days_in_month - days_elapsed)

    # Month-to-date expenses
    first_of_month = dt.date(today.year, today.month, 1)
    mtd_summary = get_spending_summary(db, user, str(first_of_month), str(today))
    mtd_expenses = Decimal(str(mtd_summary["total_expenses"]))

    # Daily spend history for current month to feed IQR outlier detection
    daily_txs = (
        db.query(Transaction.date, Transaction.amount, Transaction.category, Transaction.import_metadata)
        .filter(
            Transaction.user_id == user.id,
            Transaction.classification == "expense",
            Transaction.date >= first_of_month,
            Transaction.date <= today,
        )
        .all()
    )
    daily_spend_map: Dict[dt.date, float] = defaultdict(float)
    for d, amt, cat, meta in daily_txs:
        if (cat or "").strip() in NON_SPENDING_CATEGORIES:
            continue
        if meta and meta.get("is_overlap") is True:
            continue
        daily_spend_map[d] += float(amt)
    daily_history = [daily_spend_map[first_of_month + dt.timedelta(days=i)] for i in range(days_elapsed)]

    # Past completed months history (up to 6 months)
    six_months_ago = first_of_month - dt.timedelta(days=180)
    past_txs = (
        db.query(Transaction.date, Transaction.amount, Transaction.category, Transaction.import_metadata)
        .filter(
            Transaction.user_id == user.id,
            Transaction.classification == "expense",
            Transaction.date >= six_months_ago,
            Transaction.date < first_of_month,
        )
        .all()
    )
    monthly_totals: Dict[str, float] = defaultdict(float)
    for t_date, amt, cat, meta in past_txs:
        if (cat or "").strip() in NON_SPENDING_CATEGORIES:
            continue
        if meta and meta.get("is_overlap") is True:
            continue
        key = f"{t_date.year}-{t_date.month:02d}"
        monthly_totals[key] += float(amt)
    completed_months = list(monthly_totals.values())

    # Upcoming recurring bills this month
    recurring = (
        db.query(RecurringPayment)
        .filter(
            RecurringPayment.user_id == user.id,
            RecurringPayment.status.in_(["confirmed", "detected"]),
            RecurringPayment.next_expected_date >= today,
            RecurringPayment.next_expected_date <= dt.date(today.year, today.month, days_in_month),
        )
        .all()
    )
    upcoming_recurring_total = sum(
        (Decimal(str(r.average_amount)) for r in recurring), Decimal("0.00")
    )

    # Hybrid run-rate forecast with IQR outlier resilience
    forecast_result = forecast_hybrid_month_end(
        today=today,
        mtd_expenses=float(mtd_expenses),
        daily_spend_history=daily_history,
        upcoming_recurring_total=float(upcoming_recurring_total),
        completed_months_history=completed_months,
    )

    res = forecast_result.to_dict()
    # Backward compatibility keys
    daily_pace = mtd_expenses / Decimal(days_elapsed)
    res.update({
        "current_date": str(today),
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "month_to_date_spend": float(mtd_expenses),
        "daily_average_spend": round(float(daily_pace), 2),
        "upcoming_recurring_bills_total": float(upcoming_recurring_total),
        "projected_month_end_total": round(forecast_result.predicted_total, 2),
    })
    return res


# ---------------------------------------------------------------------------
# Tool 12: Savings Projection Math
# ---------------------------------------------------------------------------
def calculate_savings_projection(
    goal_amount: float,
    monthly_contribution: float,
    current_savings: float = 0.0,
    annual_interest_rate_pct: float = 0.0,
) -> Dict[str, Any]:
    """Calculate time to reach a savings goal given current savings and monthly contribution."""
    g_amt = Decimal(str(goal_amount))
    m_cont = Decimal(str(monthly_contribution))
    c_sav = Decimal(str(current_savings))
    rate = Decimal(str(annual_interest_rate_pct)) / Decimal("100.0")

    if m_cont <= Decimal("0.00"):
        return {
            "error": "Monthly contribution must be greater than zero.",
            "months_to_goal": None,
        }

    remaining = max(Decimal("0.00"), g_amt - c_sav)
    if remaining == Decimal("0.00"):
        return {
            "months_to_goal": 0,
            "projected_completion_date": str(dt.date.today()),
            "message": "Goal is already fully funded!",
        }

    if rate == Decimal("0.00"):
        months_needed = int(math.ceil(float(remaining / m_cont)))
    else:
        # Compound interest projection: Future Value formula
        # FV = c_sav*(1+r/12)^n + m_cont*(((1+r/12)^n - 1)/(r/12))
        monthly_rate = float(rate / Decimal("12.0"))
        # Simple iterative calculation to avoid log domain errors
        current = float(c_sav)
        m_float = float(m_cont)
        g_float = float(g_amt)
        months_needed = 0
        while current < g_float and months_needed < 600:
            current = (current + m_float) * (1.0 + monthly_rate)
            months_needed += 1

    today = dt.date.today()
    # Add months
    target_year = today.year + (today.month + months_needed - 1) // 12
    target_month = (today.month + months_needed - 1) % 12 + 1
    target_day = min(today.day, 28)
    proj_date = dt.date(target_year, target_month, target_day)

    return {
        "goal_amount": float(g_amt),
        "current_savings": float(c_sav),
        "monthly_contribution": float(m_cont),
        "remaining_amount": float(remaining),
        "annual_interest_rate_pct": float(annual_interest_rate_pct),
        "months_to_goal": months_needed,
        "projected_completion_date": str(proj_date),
    }


# ---------------------------------------------------------------------------
# Declarative Tool Schemas & Dispatcher
# ---------------------------------------------------------------------------
FINANCIAL_TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "name": "get_spending_summary",
        "description": "Fetch overall spending summary including total income, total expenses, net cash flow, and savings rate for an optional date range or account.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "ISO start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "ISO end date (YYYY-MM-DD)"},
                "account_id": {"type": "integer", "description": "Optional account ID to filter by"},
            },
        },
    },
    {
        "name": "get_category_breakdown",
        "description": "Get category-wise expense breakdown, spending shares, percentages, and top expense categories for a date range.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "ISO start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "ISO end date (YYYY-MM-DD)"},
                "limit": {"type": "integer", "description": "Max categories to return (default 10)"},
            },
        },
    },
    {
        "name": "compare_spending_periods",
        "description": "Compare spending, income, and percentage changes between two distinct time periods (e.g., this month vs last month).",
        "parameters": {
            "type": "object",
            "properties": {
                "period1_start": {"type": "string", "description": "Period 1 start date (YYYY-MM-DD)"},
                "period1_end": {"type": "string", "description": "Period 1 end date (YYYY-MM-DD)"},
                "period2_start": {"type": "string", "description": "Period 2 start date (YYYY-MM-DD)"},
                "period2_end": {"type": "string", "description": "Period 2 end date (YYYY-MM-DD)"},
            },
            "required": ["period1_start", "period1_end", "period2_start", "period2_end"],
        },
    },
    {
        "name": "get_monthly_cashflow",
        "description": "Get month-by-month historical cash flow trends (income, expenses, net savings) for the last N months.",
        "parameters": {
            "type": "object",
            "properties": {
                "months": {"type": "integer", "description": "Number of historical months to fetch (1-36, default 6)"},
            },
        },
    },
    {
        "name": "get_account_summary",
        "description": "Get all user bank and financial accounts, verified balances, liquid assets total, and reconciliation status.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_budget_status",
        "description": "Get budget status for a given month/year, including overall limit, actual spend, category allocations, and over-budget alerts.",
        "parameters": {
            "type": "object",
            "properties": {
                "month": {"type": "integer", "description": "Month number (1-12, default current month)"},
                "year": {"type": "integer", "description": "Year (YYYY, default current year)"},
            },
        },
    },
    {
        "name": "get_savings_goals",
        "description": "Get all active savings goals, target amounts, current saved amounts, completion progress percentage, and monthly savings needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "include_archived": {"type": "boolean", "description": "Whether to include archived goals"},
            },
        },
    },
    {
        "name": "get_recurring_payments",
        "description": "Get active subscriptions and recurring bills, payment frequencies, expected amounts, next due dates, and total monthly commitment.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status: active, review, or cancelled"},
            },
        },
    },
    {
        "name": "get_financial_alerts",
        "description": "Get active financial alerts such as budget overruns, upcoming recurring bills, and unusual spending spikes.",
        "parameters": {
            "type": "object",
            "properties": {
                "unread_only": {"type": "boolean", "description": "If true, returns only unread alerts (default true)"},
            },
        },
    },
    {
        "name": "get_investment_summary",
        "description": "Get investment portfolio summary, total invested amount, market vs insurance policy values, and upcoming premium dues.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_spending_forecast",
        "description": "Forecast end-of-month spending based on current month-to-date pace and upcoming recurring commitments.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "calculate_savings_projection",
        "description": "Calculate projected time and completion date to reach a target savings goal given monthly contribution and optional interest rate.",
        "parameters": {
            "type": "object",
            "properties": {
                "goal_amount": {"type": "number", "description": "Target savings amount"},
                "monthly_contribution": {"type": "number", "description": "Monthly contribution amount"},
                "current_savings": {"type": "number", "description": "Current savings amount (default 0)"},
                "annual_interest_rate_pct": {"type": "number", "description": "Expected annual interest rate % (default 0)"},
            },
            "required": ["goal_amount", "monthly_contribution"],
        },
    },
]


import inspect

TOOL_FUNCTIONS: Dict[str, Callable] = {
    "get_spending_summary": get_spending_summary,
    "get_category_breakdown": get_category_breakdown,
    "compare_spending_periods": compare_spending_periods,
    "get_monthly_cashflow": get_monthly_cashflow,
    "get_account_summary": get_account_summary,
    "get_budget_status": get_budget_status,
    "get_savings_goals": get_savings_goals,
    "get_recurring_payments": get_recurring_payments,
    "get_financial_alerts": get_financial_alerts,
    "get_investment_summary": get_investment_summary,
    "get_spending_forecast": get_spending_forecast,
    "calculate_savings_projection": calculate_savings_projection,
}


def execute_tool(name: str, args: Dict[str, Any], db: Session, user: User) -> Dict[str, Any]:
    """Safely dispatch and execute a registered financial tool with strict argument sanitization."""
    func_target = TOOL_FUNCTIONS.get(name)
    if not func_target:
        return {"error": f"Unknown tool: '{name}'"}

    # Strict security & ownership guarantee:
    # 1. Strip any parameters not explicitly declared in the tool signature.
    # 2. Never allow user_id, db, or user to be injected or overridden by LLM payloads.
    sig = inspect.signature(func_target)
    allowed_params = set(sig.parameters.keys()) - {"db", "user", "current_user"}
    sanitized_args = {k: v for k, v in (args or {}).items() if k in allowed_params}

    try:
        if name == "calculate_savings_projection":
            # Pure math tool, does not require db or user
            return func_target(**sanitized_args)
        else:
            return func_target(db=db, user=user, **sanitized_args)
    except Exception as exc:
        return {"error": f"Tool execution failed: {str(exc)}"}
