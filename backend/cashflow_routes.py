"""Cash Flow Intelligence and financial analytics API routes for PaisaClarity (Phase 8)."""

from collections import defaultdict
import datetime as dt
from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth_dependency import get_current_user
from database import get_db
from models import User, FinancialAccount, Transaction
from schemas import (
    CashFlowAnalysisResponse,
    CashFlowMonthly,
    CashFlowCategorySpend,
    CashFlowTopExpense,
    CashFlowAccountSummary,
    HealthIndicator,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _compute_account_balance(db: Session, account: FinancialAccount) -> tuple[Decimal | None, Decimal, Decimal]:
    """Calculate verified account balance and movements."""
    credit_sum = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.account_id == account.id,
            Transaction.type == "credit",
        )
        .scalar()
    )
    debit_sum = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.account_id == account.id,
            Transaction.type == "debit",
        )
        .scalar()
    )
    tot_credits = Decimal(str(credit_sum)).quantize(Decimal("0.01"))
    tot_debits = Decimal(str(debit_sum)).quantize(Decimal("0.01"))

    if not account.is_reconciled or account.account_type == "imported":
        return None, tot_credits, tot_debits

    opening = account.opening_balance if account.opening_balance is not None else Decimal("0.00")
    bal = Decimal(str(opening)) + tot_credits - tot_debits
    return bal.quantize(Decimal("0.01")), tot_credits, tot_debits


@router.get("/cash-flow", response_model=CashFlowAnalysisResponse)
def get_cash_flow_intelligence(
    start_date: dt.date | None = Query(None, description="Start date (inclusive)"),
    end_date: dt.date | None = Query(None, description="End date (inclusive)"),
    account_id: int | None = Query(None, description="Filter by account"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve comprehensive cash-flow intelligence and financial health indicators."""
    tx_query = db.query(Transaction).filter(Transaction.user_id == current_user.id)

    if start_date is not None:
        tx_query = tx_query.filter(Transaction.date >= start_date)
    if end_date is not None:
        tx_query = tx_query.filter(Transaction.date <= end_date)
    if account_id is not None:
        tx_query = tx_query.filter(Transaction.account_id == account_id)

    transactions = tx_query.order_by(Transaction.date.asc(), Transaction.id.asc()).all()

    # Filter out overlap duplicates
    valid_txs = [t for t in transactions if not (t.import_metadata or {}).get("is_overlap")]

    # Accumulate metrics
    total_income = Decimal("0.00")
    total_expenses = Decimal("0.00")
    category_spend_map: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    monthly_data: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"income": Decimal("0.00"), "expenses": Decimal("0.00")})
    top_expense_candidates: list[Transaction] = []

    for tx in valid_txs:
        amt = Decimal(str(tx.amount)).quantize(Decimal("0.01"))
        month_key = tx.date.strftime("%Y-%m")

        # Exclude transfers from both income and expenses
        if tx.classification == "transfer":
            continue

        # Income: credits classified as income
        if tx.type == "credit" and tx.classification == "income":
            total_income += amt
            monthly_data[month_key]["income"] += amt

        # Expenses: debits classified as expense (excluding investments which are savings/asset allocation)
        elif tx.type == "debit" and tx.classification == "expense":
            total_expenses += amt
            monthly_data[month_key]["expenses"] += amt

            cat = (tx.category or "Other").strip()
            category_spend_map[cat] += amt
            top_expense_candidates.append(tx)

    net_cash_flow = (total_income - total_expenses).quantize(Decimal("0.01"))
    if total_income > Decimal("0.00"):
        savings_rate = round(float((net_cash_flow / total_income) * 100), 2)
    else:
        savings_rate = 0.0

    # Monthly cash-flow history (chronological)
    all_months = sorted(monthly_data.keys())
    monthly_history: list[CashFlowMonthly] = []
    for m in all_months:
        m_inc = monthly_data[m]["income"].quantize(Decimal("0.01"))
        m_exp = monthly_data[m]["expenses"].quantize(Decimal("0.01"))
        m_net = (m_inc - m_exp).quantize(Decimal("0.01"))
        m_rate = round(float((m_net / m_inc) * 100), 2) if m_inc > Decimal("0.00") else 0.0
        monthly_history.append(
            CashFlowMonthly(
                month=m,
                income=m_inc,
                expenses=m_exp,
                net_cash_flow=m_net,
                savings_rate_pct=m_rate,
            )
        )

    # Month-over-month comparisons between the latest two recorded months
    mom_income_pct: float | None = None
    mom_expense_pct: float | None = None
    mom_net_diff: Decimal | None = None

    if len(monthly_history) >= 2:
        curr_m = monthly_history[-1]
        prev_m = monthly_history[-2]

        if prev_m.income > Decimal("0.00"):
            mom_income_pct = round(float(((curr_m.income - prev_m.income) / prev_m.income) * 100), 2)
        if prev_m.expenses > Decimal("0.00"):
            mom_expense_pct = round(float(((curr_m.expenses - prev_m.expenses) / prev_m.expenses) * 100), 2)
        mom_net_diff = (curr_m.net_cash_flow - prev_m.net_cash_flow).quantize(Decimal("0.01"))

    # Category breakdown (sorted by spending descending)
    cat_breakdown: list[CashFlowCategorySpend] = []
    for cat_name, amt in sorted(category_spend_map.items(), key=lambda x: x[1], reverse=True):
        pct = round(float((amt / total_expenses) * 100), 2) if total_expenses > Decimal("0.00") else 0.0
        cat_breakdown.append(
            CashFlowCategorySpend(
                category=cat_name,
                amount=amt.quantize(Decimal("0.01")),
                percentage=pct,
            )
        )

    # Top expenses (top 10 largest individual purchases)
    top_expense_candidates.sort(key=lambda t: t.amount, reverse=True)
    top_expenses: list[CashFlowTopExpense] = [
        CashFlowTopExpense(
            id=t.id,
            date=t.date,
            description=t.description,
            category=t.category or "Other",
            amount=Decimal(str(t.amount)).quantize(Decimal("0.01")),
        )
        for t in top_expense_candidates[:10]
    ]

    # Account summaries
    user_accounts = (
        db.query(FinancialAccount)
        .filter(FinancialAccount.user_id == current_user.id, FinancialAccount.is_archived.is_(False))
        .all()
    )
    account_summaries: list[CashFlowAccountSummary] = []
    total_liquid_balance = Decimal("0.00")

    for acc in user_accounts:
        bal, credits, debits = _compute_account_balance(db, acc)
        if bal is not None and acc.is_reconciled:
            total_liquid_balance += bal

        account_summaries.append(
            CashFlowAccountSummary(
                id=acc.id,
                name=acc.name,
                account_type=acc.account_type,
                is_reconciled=acc.is_reconciled,
                opening_balance=Decimal(str(acc.opening_balance)).quantize(Decimal("0.01")) if acc.opening_balance is not None else None,
                calculated_balance=bal,
                total_credits=credits,
                total_debits=debits,
            )
        )

    # Financial health indicators (deterministic, transparent rules)
    health_indicators: list[HealthIndicator] = []

    # 1. Cash Flow Health
    if total_income == Decimal("0.00") and total_expenses == Decimal("0.00"):
        health_indicators.append(
            HealthIndicator(
                name="Cash Flow",
                status="neutral",
                score=None,
                label="No Data",
                description="Upload transactions or bank statements to evaluate cash flow.",
            )
        )
    elif net_cash_flow > Decimal("0.00"):
        health_indicators.append(
            HealthIndicator(
                name="Cash Flow",
                status="healthy",
                score=float(net_cash_flow),
                label="Positive Cash Flow",
                description=f"You earned ₹{net_cash_flow} more than you spent in this period.",
            )
        )
    elif net_cash_flow == Decimal("0.00"):
        health_indicators.append(
            HealthIndicator(
                name="Cash Flow",
                status="warning",
                score=0.0,
                label="Break-even",
                description="Your income matches your expenses exactly.",
            )
        )
    else:
        health_indicators.append(
            HealthIndicator(
                name="Cash Flow",
                status="critical",
                score=float(net_cash_flow),
                label="Cash Flow Deficit",
                description=f"Spending exceeded earnings by ₹{abs(net_cash_flow)} in this period.",
            )
        )

    # 2. Savings Rate Benchmark (Recommended: >= 20%)
    if total_income > Decimal("0.00"):
        if savings_rate >= 30.0:
            health_indicators.append(
                HealthIndicator(
                    name="Savings Rate",
                    status="healthy",
                    score=savings_rate,
                    label=f"Super Saver ({savings_rate}%)",
                    description="You are saving over 30% of your earnings — well above the 20% benchmark.",
                )
            )
        elif savings_rate >= 20.0:
            health_indicators.append(
                HealthIndicator(
                    name="Savings Rate",
                    status="healthy",
                    score=savings_rate,
                    label=f"Healthy ({savings_rate}%)",
                    description="Your savings rate meets the recommended 20% benchmark.",
                )
            )
        elif savings_rate >= 10.0:
            health_indicators.append(
                HealthIndicator(
                    name="Savings Rate",
                    status="warning",
                    score=savings_rate,
                    label=f"Moderate ({savings_rate}%)",
                    description="Your savings rate is between 10% and 20%. Aim to increase toward 20%.",
                )
            )
        elif savings_rate >= 0.0:
            health_indicators.append(
                HealthIndicator(
                    name="Savings Rate",
                    status="warning",
                    score=savings_rate,
                    label=f"Low ({savings_rate}%)",
                    description="Your savings rate is under 10%. Consider reviewing discretionary spending.",
                )
            )
        else:
            health_indicators.append(
                HealthIndicator(
                    name="Savings Rate",
                    status="critical",
                    score=savings_rate,
                    label=f"Negative ({savings_rate}%)",
                    description="Deficit spending in progress. Expenses exceed income.",
                )
            )

    # 3. Expense Volatility / Surge Check
    if mom_expense_pct is not None:
        if mom_expense_pct > 25.0:
            health_indicators.append(
                HealthIndicator(
                    name="Expense Trend",
                    status="warning",
                    score=mom_expense_pct,
                    label=f"Spike (+{mom_expense_pct}%)",
                    description=f"Expenses jumped {mom_expense_pct}% compared to the previous month.",
                )
            )
        elif mom_expense_pct < -15.0:
            health_indicators.append(
                HealthIndicator(
                    name="Expense Trend",
                    status="healthy",
                    score=mom_expense_pct,
                    label=f"Reduction ({mom_expense_pct}%)",
                    description=f"Spending reduced by {abs(mom_expense_pct)}% compared to last month.",
                )
            )
        else:
            health_indicators.append(
                HealthIndicator(
                    name="Expense Trend",
                    status="healthy",
                    score=mom_expense_pct,
                    label="Stable Spending",
                    description="Month-over-month expenses are consistent within normal bounds.",
                )
            )

    # 4. Emergency Buffer Indicator
    if monthly_history and total_liquid_balance > Decimal("0.00"):
        avg_monthly_exp = sum((m.expenses for m in monthly_history), Decimal("0.00")) / Decimal(len(monthly_history))
        if avg_monthly_exp > Decimal("0.00"):
            months_buffer = round(float(total_liquid_balance / avg_monthly_exp), 1)
            if months_buffer >= 6.0:
                health_indicators.append(
                    HealthIndicator(
                        name="Emergency Buffer",
                        status="healthy",
                        score=months_buffer,
                        label=f"{months_buffer} Months",
                        description=f"Your verified account balances cover {months_buffer} months of average expenses.",
                    )
                )
            elif months_buffer >= 3.0:
                health_indicators.append(
                    HealthIndicator(
                        name="Emergency Buffer",
                        status="healthy",
                        score=months_buffer,
                        label=f"{months_buffer} Months",
                        description=f"Your verified funds cover {months_buffer} months of expenses (good baseline).",
                    )
                )
            else:
                health_indicators.append(
                    HealthIndicator(
                        name="Emergency Buffer",
                        status="warning",
                        score=months_buffer,
                        label=f"{months_buffer} Months",
                        description="Less than 3 months of expenses in verified liquid accounts. Build emergency savings.",
                    )
                )

    return CashFlowAnalysisResponse(
        period_start=start_date,
        period_end=end_date,
        total_income=total_income,
        total_expenses=total_expenses,
        net_cash_flow=net_cash_flow,
        savings_rate_pct=savings_rate,
        mom_income_change_pct=mom_income_pct,
        mom_expense_change_pct=mom_expense_pct,
        mom_net_cash_flow_change=mom_net_diff,
        monthly_history=monthly_history,
        category_breakdown=cat_breakdown,
        top_expenses=top_expenses,
        accounts=account_summaries,
        health_indicators=health_indicators,
    )

