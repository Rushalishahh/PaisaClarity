"""Authoritative Financial Reporting and Export API routes for PaisaClarity (Phase 11).

Provides:
- GET /reports/summary: Comprehensive server-side financial summary with date-range filtering.
- GET /reports/export/csv: Secure CSV export with formula injection prevention.
- GET /reports/export/pdf: Executive financial report PDF export with ReportLab.
"""

from collections import defaultdict
import csv
import datetime as dt
from decimal import Decimal
import io
from typing import Any, Dict, List, Optional
import xml.sax.saxutils

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from auth_dependency import get_current_user
from database import get_db
from models import (
    User,
    FinancialAccount,
    Category,
    Transaction,
    Budget,
    BudgetAllocation,
    SavingsGoal,
    SavingsContribution,
    RecurringPayment,
    Investment,
)
from categorizer import NON_SPENDING_CATEGORIES
from cashflow_routes import _compute_account_balance
from budget_routes import _calculate_budget_metrics
from savings_routes import _calculate_goal_metrics

# ReportLab imports for professional PDF generation
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


router = APIRouter(prefix="/reports", tags=["reports"])


def _parse_report_dates(
    start_date: Optional[str], end_date: Optional[str]
) -> tuple[dt.date, dt.date]:
    """Safely parse or default report date range."""
    today = dt.date.today()
    if end_date:
        try:
            d_end = dt.date.fromisoformat(end_date.strip())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date format. Expected YYYY-MM-DD.",
            )
    else:
        d_end = today

    if start_date:
        try:
            d_start = dt.date.fromisoformat(start_date.strip())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Expected YYYY-MM-DD.",
            )
    else:
        # Default to first day of current month or 30 days prior
        d_start = dt.date(d_end.year, d_end.month, 1)

    if d_start > d_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date cannot be after end_date.",
        )

    return d_start, d_end


def _sanitize_csv_cell(value: Any) -> str:
    """Defend against CSV / Spreadsheet Formula Injection (CWE-1236).

    Prepends single quote (') if string starts with dangerous characters (=, +, -, @, tab, CR).
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{s}"
    return s


def _format_inr_text(amount: float) -> str:
    """Format floating point numbers into Indian Rupee text representation."""
    return f"Rs. {amount:,.2f}"


@router.get("/summary")
def get_financial_report_summary(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Generate an authoritative, consolidated financial summary report for the user."""
    d_start, d_end = _parse_report_dates(start_date, end_date)

    # 1. Fetch transactions within range
    txs = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == current_user.id,
            Transaction.date >= d_start,
            Transaction.date <= d_end,
        )
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )

    tot_income = Decimal("0.00")
    tot_expense = Decimal("0.00")
    category_totals: Dict[str, Decimal] = defaultdict(Decimal)
    category_counts: Dict[str, int] = defaultdict(int)
    monthly_trends: Dict[str, Dict[str, Decimal]] = defaultdict(
        lambda: {"income": Decimal("0.00"), "expense": Decimal("0.00")}
    )
    valid_tx_count = 0

    for tx in txs:
        meta = tx.import_metadata or {}
        if meta.get("is_overlap") is True:
            continue
        amt = Decimal(str(tx.amount)).quantize(Decimal("0.01"))
        cat = (tx.category or "Other").strip()
        month_key = f"{tx.date.year}-{tx.date.month:02d}"

        if tx.classification == "income":
            tot_income += amt
            monthly_trends[month_key]["income"] += amt
            valid_tx_count += 1
        elif tx.classification == "expense":
            if cat not in NON_SPENDING_CATEGORIES:
                tot_expense += amt
                category_totals[cat] += amt
                category_counts[cat] += 1
                monthly_trends[month_key]["expense"] += amt
                valid_tx_count += 1

    net_cashflow = tot_income - tot_expense
    savings_rate = (
        round(float((net_cashflow / tot_income) * 100), 2)
        if tot_income > Decimal("0.00")
        else 0.0
    )

    # Sort categories by spending descending
    category_breakdown = []
    tot_exp_float = float(tot_expense)
    for cat, amt_dec in sorted(category_totals.items(), key=lambda x: x[1], reverse=True):
        amt_f = float(amt_dec)
        pct = round((amt_f / tot_exp_float * 100), 2) if tot_exp_float > 0 else 0.0
        category_breakdown.append({
            "category": cat,
            "amount": amt_f,
            "percentage": pct,
            "count": category_counts[cat],
        })

    # Sort monthly trends chronologically
    sorted_months = []
    for m_key in sorted(monthly_trends.keys()):
        m_inc = float(monthly_trends[m_key]["income"])
        m_exp = float(monthly_trends[m_key]["expense"])
        sorted_months.append({
            "month": m_key,
            "income": m_inc,
            "expense": m_exp,
            "net": round(m_inc - m_exp, 2),
        })

    # 2. Account balances & net worth (verified vs unreconciled separation)
    accounts = (
        db.query(FinancialAccount)
        .filter(FinancialAccount.user_id == current_user.id, FinancialAccount.is_archived == False)
        .all()
    )
    verified_liquid_balance = Decimal("0.00")
    unreconciled_placeholder_balance = Decimal("0.00")
    account_items = []

    for acc in accounts:
        calc_bal, _, _ = _compute_account_balance(db, acc)
        balance_val = float(calc_bal) if calc_bal is not None else 0.0
        acc_info = {
            "id": acc.id,
            "name": acc.name,
            "account_type": acc.account_type,
            "is_reconciled": acc.is_reconciled,
            "balance": balance_val,
        }
        account_items.append(acc_info)
        if acc.is_reconciled and acc.account_type in ("savings", "current", "checking"):
            if calc_bal is not None:
                verified_liquid_balance += calc_bal
        elif not acc.is_reconciled:
            # For unreconciled/imported accounts, track placeholder balance
            opening = acc.opening_balance if acc.opening_balance is not None else Decimal("0.00")
            unreconciled_placeholder_balance += opening

    # 3. Budget performance for target months in range
    budgets = (
        db.query(Budget)
        .filter(
            Budget.user_id == current_user.id,
            Budget.is_archived == False,
        )
        .all()
    )
    budget_items = []
    for b in budgets:
        # Check if budget falls into target date range
        b_date = dt.date(b.year, b.month, 1)
        if (d_start.year, d_start.month) <= (b.year, b.month) <= (d_end.year, d_end.month):
            metrics = _calculate_budget_metrics(db, b)
            budget_items.append(metrics)

    # 4. Savings goals
    goals = (
        db.query(SavingsGoal)
        .filter(SavingsGoal.user_id == current_user.id, SavingsGoal.is_archived == False)
        .all()
    )
    goal_items = []
    tot_target = Decimal("0.00")
    tot_saved = Decimal("0.00")
    for g in goals:
        gm = _calculate_goal_metrics(g)
        goal_items.append(gm)
        tot_target += Decimal(str(gm.target_amount))
        tot_saved += Decimal(str(gm.total_saved))

    # 5. Recurring payment commitments
    recurring = (
        db.query(RecurringPayment)
        .filter(
            RecurringPayment.user_id == current_user.id,
            RecurringPayment.status.in_(["confirmed", "detected"]),
        )
        .all()
    )
    tot_monthly_recurring = sum(
        (Decimal(str(r.average_amount)) for r in recurring), Decimal("0.00")
    )
    confirmed_count = sum(1 for r in recurring if r.status == "confirmed")
    detected_count = sum(1 for r in recurring if r.status == "detected")

    # 6. Investment portfolio
    investments = (
        db.query(Investment)
        .filter(Investment.user_id == current_user.id)
        .all()
    )
    tot_invested = Decimal("0.00")
    mkt_invested = Decimal("0.00")
    pol_invested = Decimal("0.00")
    for inv in investments:
        i_amt = Decimal(str(inv.invested_amount or 0)).quantize(Decimal("0.01"))
        tot_invested += i_amt
        if inv.category == "market":
            mkt_invested += i_amt
        else:
            pol_invested += i_amt

    return {
        "period": {
            "start_date": str(d_start),
            "end_date": str(d_end),
            "days_count": (d_end - d_start).days + 1,
        },
        "summary": {
            "total_income": float(tot_income),
            "total_expenses": float(tot_expense),
            "net_cash_flow": float(net_cashflow),
            "savings_rate_pct": savings_rate,
            "transaction_count": valid_tx_count,
        },
        "category_breakdown": category_breakdown,
        "monthly_trends": sorted_months,
        "net_worth": {
            "verified_liquid_balance": float(verified_liquid_balance),
            "unreconciled_placeholder_balance": float(unreconciled_placeholder_balance),
            "total_investments": float(tot_invested),
            "estimated_verified_net_worth": float(verified_liquid_balance + tot_invested),
            "accounts": account_items,
        },
        "budgets": budget_items,
        "savings_goals": {
            "total_target": float(tot_target),
            "total_saved": float(tot_saved),
            "progress_pct": round(float((tot_saved / tot_target) * 100), 2) if tot_target > 0 else 0.0,
            "goals": goal_items,
        },
        "recurring_payments": {
            "total_monthly_commitment": float(tot_monthly_recurring),
            "confirmed_count": confirmed_count,
            "detected_count": detected_count,
            "total_count": len(recurring),
        },
        "investments": {
            "total_invested": float(tot_invested),
            "market_total": float(mkt_invested),
            "policy_total": float(pol_invested),
            "count": len(investments),
        },
    }


@router.get("/export/csv")
def export_transactions_csv(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export transactions as an RFC 4180 compliant CSV with formula injection defense."""
    d_start, d_end = _parse_report_dates(start_date, end_date)

    txs = (
        db.query(Transaction, FinancialAccount.name.label("account_name"))
        .outerjoin(FinancialAccount, Transaction.account_id == FinancialAccount.id)
        .filter(
            Transaction.user_id == current_user.id,
            Transaction.date >= d_start,
            Transaction.date <= d_end,
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Header
    writer.writerow([
        "Date",
        "Account",
        "Description",
        "Merchant",
        "Classification",
        "Category",
        "Type",
        "Amount (INR)",
        "Reference No",
        "Categorization Method",
    ])

    for tx, acc_name in txs:
        meta = tx.import_metadata or {}
        method = "User Override" if meta.get("is_user_override") else meta.get("categorization_method", "System")
        writer.writerow([
            str(tx.date),
            _sanitize_csv_cell(acc_name or "Unassigned"),
            _sanitize_csv_cell(tx.description),
            _sanitize_csv_cell(tx.merchant or ""),
            _sanitize_csv_cell(tx.classification),
            _sanitize_csv_cell(tx.category),
            _sanitize_csv_cell(tx.type),
            f"{Decimal(str(tx.amount)):.2f}",
            _sanitize_csv_cell(tx.ref_no or ""),
            _sanitize_csv_cell(method),
        ])

    csv_content = output.getvalue()
    filename = f"paisaclarity_transactions_{d_start}_{d_end}.csv"

    return Response(
        content=csv_content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/pdf")
def export_financial_report_pdf(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a clean executive financial report PDF using ReportLab Platypus."""
    report_data = get_financial_report_summary(
        start_date=start_date,
        end_date=end_date,
        current_user=current_user,
        db=db,
    )

    period = report_data["period"]
    summary = report_data["summary"]
    categories = report_data["category_breakdown"]
    net_worth = report_data["net_worth"]
    budgets = report_data["budgets"]
    goals = report_data["savings_goals"]
    recurring = report_data["recurring_payments"]
    investments = report_data["investments"]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        alignment=0,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#64748b"),
    )
    heading_style = ParagraphStyle(
        "ReportHeading",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=6,
    )
    cell_style = ParagraphStyle(
        "ReportCell",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
    )
    cell_bold = ParagraphStyle(
        "ReportCellBold",
        parent=cell_style,
        fontName="Helvetica-Bold",
    )

    elements = []

    # 1. Header Banner
    safe_email = xml.sax.saxutils.escape(current_user.email)
    elements.append(Paragraph("PaisaClarity Executive Financial Report", title_style))
    elements.append(
        Paragraph(
            f"Period: <b>{period['start_date']}</b> to <b>{period['end_date']}</b> ({period['days_count']} days) | Prepared for: {safe_email}",
            subtitle_style,
        )
    )
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0f766e"), spaceAfter=14))

    # 2. Executive Financial KPIs Table
    kpi_data = [
        [
            Paragraph("Total Income", cell_style),
            Paragraph(_format_inr_text(summary["total_income"]), cell_bold),
            Paragraph("Verified Liquid Balances", cell_style),
            Paragraph(_format_inr_text(net_worth["verified_liquid_balance"]), cell_bold),
        ],
        [
            Paragraph("Total Spending", cell_style),
            Paragraph(_format_inr_text(summary["total_expenses"]), cell_bold),
            Paragraph("Total Investments", cell_style),
            Paragraph(_format_inr_text(investments["total_invested"]), cell_bold),
        ],
        [
            Paragraph("Net Cash Flow", cell_style),
            Paragraph(
                _format_inr_text(summary["net_cash_flow"]),
                ParagraphStyle("KpiNet", parent=cell_bold, textColor=colors.HexColor("#047857") if summary["net_cash_flow"] >= 0 else colors.HexColor("#b91c1c")),
            ),
            Paragraph("Estimated Net Worth", cell_style),
            Paragraph(_format_inr_text(net_worth["estimated_verified_net_worth"]), cell_bold),
        ],
        [
            Paragraph("Savings Rate", cell_style),
            Paragraph(f"{summary['savings_rate_pct']}%", cell_bold),
            Paragraph("Monthly Subscriptions", cell_style),
            Paragraph(_format_inr_text(recurring["total_monthly_commitment"]), cell_bold),
        ],
    ]
    t_kpi = Table(kpi_data, colWidths=[130, 130, 140, 140])
    t_kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(t_kpi)
    elements.append(Spacer(1, 14))

    # 3. Category Spending Breakdown
    elements.append(Paragraph("Category Spending Breakdown", heading_style))
    if categories:
        cat_rows = [[
            Paragraph("Category", cell_bold),
            Paragraph("Amount", cell_bold),
            Paragraph("% of Expenses", cell_bold),
            Paragraph("Txns", cell_bold),
        ]]
        for c in categories[:10]:  # Top 10 categories
            cat_rows.append([
                Paragraph(xml.sax.saxutils.escape(c["category"]), cell_style),
                Paragraph(_format_inr_text(c["amount"]), cell_style),
                Paragraph(f"{c['percentage']}%", cell_style),
                Paragraph(str(c["count"]), cell_style),
            ])
        t_cat = Table(cat_rows, colWidths=[180, 140, 120, 100])
        t_cat.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(t_cat)
    else:
        elements.append(Paragraph("No categorized spending recorded during this period.", cell_style))

    elements.append(Spacer(1, 14))

    # 4. Budget & Savings Goals Summary
    elements.append(Paragraph("Budgets & Savings Goals", heading_style))
    bs_data = [
        [
            Paragraph("Active Budgets Evaluated", cell_style),
            Paragraph(str(len(budgets)), cell_bold),
            Paragraph("Savings Goals Progress", cell_style),
            Paragraph(f"{goals['progress_pct']}% funded ({_format_inr_text(goals['total_saved'])} / {_format_inr_text(goals['total_target'])})", cell_bold),
        ],
        [
            Paragraph("Confirmed Subscriptions", cell_style),
            Paragraph(f"{recurring['confirmed_count']} confirmed ({_format_inr_text(recurring['total_monthly_commitment'])}/mo)", cell_bold),
            Paragraph("Detected Subscriptions", cell_style),
            Paragraph(f"{recurring['detected_count']} pending review", cell_style),
        ],
    ]
    t_bs = Table(bs_data, colWidths=[160, 110, 140, 130])
    t_bs.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(t_bs)
    elements.append(Spacer(1, 16))

    # 5. Disclaimer & Footer Notice
    disclaimer_text = (
        "<b>Important Notice:</b> This report is generated automatically by PaisaClarity from user-verified transactions, "
        "budgets, and statements. It excludes internal transfers and duplicate overlapping statements. Unreconciled account balances "
        "are strictly separated from verified net worth. This document is provided for informational and financial awareness "
        "purposes only and does not constitute certified tax or legal advice."
    )
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=8))
    elements.append(Paragraph(disclaimer_text, ParagraphStyle("Disc", parent=subtitle_style, fontSize=8, leading=11)))

    doc.build(elements)

    pdf_content = buffer.getvalue()
    filename = f"paisaclarity_financial_report_{period['start_date']}_{period['end_date']}.pdf"

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
