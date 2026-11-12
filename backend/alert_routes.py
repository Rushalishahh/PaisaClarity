"""Financial alerts and notification preferences API routes for PaisaClarity (Phase 8)."""

from collections import defaultdict
import datetime as dt
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth_dependency import get_current_user
from database import get_db
from models import User, FinancialAlert, Budget, SavingsGoal, RecurringPayment, Transaction
from schemas import (
    AlertResponse,
    AlertListResponse,
    AlertPreferencesResponse,
    AlertPreferencesUpdate,
)
from budget_routes import _calculate_budget_metrics
from savings_routes import _calculate_goal_metrics

router = APIRouter(prefix="/alerts", tags=["financial-alerts"])

DEFAULT_PREFERENCES = {
    "budget_alerts": True,
    "recurring_alerts": True,
    "unusual_spending_alerts": True,
    "goal_alerts": True,
    "large_expense_threshold": "5000.00",
}


def _get_user_preferences(user: User) -> dict:
    """Return user preferences merged with defaults."""
    user_prefs = user.alert_preferences or {}
    prefs = dict(DEFAULT_PREFERENCES)
    prefs.update(user_prefs)
    return prefs


def evaluate_financial_alerts(db: Session, user: User) -> int:
    """Evaluate financial conditions and generate deterministic, deduplicated alerts.
    
    Returns the count of new alerts created.
    """
    prefs = _get_user_preferences(user)
    today = dt.date.today()
    new_alerts_count = 0

    def _create_alert_if_not_exists(
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        dedup_key: str,
        entity_type: str | None = None,
        entity_id: int | None = None,
    ) -> bool:
        existing = (
            db.query(FinancialAlert.id)
            .filter(FinancialAlert.user_id == user.id, FinancialAlert.dedup_key == dedup_key)
            .first()
        )
        if existing:
            return False

        alert = FinancialAlert(
            user_id=user.id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            dedup_key=dedup_key,
            related_entity_type=entity_type,
            related_entity_id=entity_id,
        )
        db.add(alert)
        return True

    # -----------------------------------------------------------------------
    # 1. Budget Alerts
    # -----------------------------------------------------------------------
    if prefs.get("budget_alerts", True):
        current_budget = (
            db.query(Budget)
            .filter(Budget.user_id == user.id, Budget.month == today.month, Budget.year == today.year)
            .first()
        )
        if current_budget:
            metrics = _calculate_budget_metrics(db, current_budget)
            # Overall cap check
            if metrics.overall_is_exceeded:
                key = f"budget_exceeded_{today.year}_{today.month}_overall"
                if _create_alert_if_not_exists(
                    alert_type="budget_exceeded",
                    severity="critical",
                    title="Overall Monthly Budget Exceeded",
                    message=f"You have spent ₹{metrics.total_spent}, exceeding your limit of ₹{metrics.total_budget_limit or metrics.total_allocated} for {today.strftime('%B %Y')}.",
                    dedup_key=key,
                    entity_type="budget",
                    entity_id=current_budget.id,
                ):
                    new_alerts_count += 1
            elif metrics.overall_utilization_pct >= float(current_budget.warning_threshold):
                key = f"budget_warning_{today.year}_{today.month}_overall"
                if _create_alert_if_not_exists(
                    alert_type="budget_warning",
                    severity="warning",
                    title="Monthly Budget Warning",
                    message=f"You have used {metrics.overall_utilization_pct}% of your monthly budget (₹{metrics.total_spent} of ₹{metrics.total_budget_limit or metrics.total_allocated}).",
                    dedup_key=key,
                    entity_type="budget",
                    entity_id=current_budget.id,
                ):
                    new_alerts_count += 1

            # Category allocations check
            for alloc in metrics.allocations:
                clean_cat = alloc.category_name.strip().replace(" ", "_").lower()
                if alloc.is_exceeded:
                    key = f"budget_exceeded_{today.year}_{today.month}_{clean_cat}"
                    if _create_alert_if_not_exists(
                        alert_type="budget_exceeded",
                        severity="warning",
                        title=f"{alloc.category_name} Budget Exceeded",
                        message=f"You have spent ₹{alloc.actual_spent} in {alloc.category_name}, exceeding the allocated ₹{alloc.allocated_amount}.",
                        dedup_key=key,
                        entity_type="budget",
                        entity_id=current_budget.id,
                    ):
                        new_alerts_count += 1
                elif alloc.is_warning:
                    key = f"budget_warning_{today.year}_{today.month}_{clean_cat}"
                    if _create_alert_if_not_exists(
                        alert_type="budget_warning",
                        severity="info",
                        title=f"{alloc.category_name} Near Limit",
                        message=f"{alloc.category_name} spending has reached {alloc.utilization_pct}% of allocation (₹{alloc.actual_spent} of ₹{alloc.allocated_amount}).",
                        dedup_key=key,
                        entity_type="budget",
                        entity_id=current_budget.id,
                    ):
                        new_alerts_count += 1

    # -----------------------------------------------------------------------
    # 2. Upcoming Recurring Payment Alerts (Due in next 3 days)
    # -----------------------------------------------------------------------
    if prefs.get("recurring_alerts", True):
        confirmed_recurring = (
            db.query(RecurringPayment)
            .filter(
                RecurringPayment.user_id == user.id,
                RecurringPayment.status == "confirmed",
                RecurringPayment.next_expected_date >= today,
                RecurringPayment.next_expected_date <= today + dt.timedelta(days=3),
            )
            .all()
        )
        for rec in confirmed_recurring:
            key = f"upcoming_bill_{rec.id}_{rec.next_expected_date.isoformat()}"
            days_left = (rec.next_expected_date - today).days
            due_text = "today" if days_left == 0 else "tomorrow" if days_left == 1 else f"in {days_left} days"
            if _create_alert_if_not_exists(
                alert_type="upcoming_recurring",
                severity="info",
                title=f"Upcoming Bill: {rec.name}",
                message=f"Your recurring payment of ₹{rec.average_amount} for {rec.name} is due {due_text} ({rec.next_expected_date.strftime('%d %b')}).",
                dedup_key=key,
                entity_type="recurring",
                entity_id=rec.id,
            ):
                new_alerts_count += 1

    # -----------------------------------------------------------------------
    # 3. Savings Goal Pace Alerts
    # -----------------------------------------------------------------------
    if prefs.get("goal_alerts", True):
        goals = (
            db.query(SavingsGoal)
            .filter(SavingsGoal.user_id == user.id, SavingsGoal.is_archived.is_(False))
            .all()
        )
        for g in goals:
            g_metrics = _calculate_goal_metrics(g)
            if not g_metrics.is_completed and g.target_date:
                days_remaining = (g.target_date - today).days
                if days_remaining < 30 and g_metrics.completion_pct < 70.0:
                    key = f"goal_behind_{g.id}_{today.strftime('%Y_%m')}"
                    if _create_alert_if_not_exists(
                        alert_type="savings_goal_behind",
                        severity="warning",
                        title=f"Goal Deadline Approaching: {g.name}",
                        message=f"{g.name} is at {g_metrics.completion_pct}% with only {max(0, days_remaining)} days left. Estimated ₹{g_metrics.monthly_savings_needed or g_metrics.remaining_target} needed to complete.",
                        dedup_key=key,
                        entity_type="goal",
                        entity_id=g.id,
                    ):
                        new_alerts_count += 1

    # -----------------------------------------------------------------------
    # 4. Unusual Large Spending Alert (Single transaction > threshold in last 7 days)
    # -----------------------------------------------------------------------
    if prefs.get("unusual_spending_alerts", True):
        raw_threshold = prefs.get("large_expense_threshold", "5000.00")
        try:
            threshold = Decimal(str(raw_threshold))
        except Exception:
            threshold = Decimal("5000.00")

        week_ago = today - dt.timedelta(days=7)
        recent_large_txs = (
            db.query(Transaction)
            .filter(
                Transaction.user_id == user.id,
                Transaction.date >= week_ago,
                Transaction.type == "debit",
                Transaction.classification == "expense",
                Transaction.amount >= threshold,
            )
            .all()
        )
        for tx in recent_large_txs:
            if (tx.import_metadata or {}).get("is_overlap"):
                continue
            key = f"unusual_tx_{tx.id}"
            if _create_alert_if_not_exists(
                alert_type="unusual_spending",
                severity="info",
                title=f"Large Expense: ₹{tx.amount}",
                message=f"A transaction of ₹{tx.amount} was recorded on {tx.date.strftime('%d %b')} for '{tx.description}'.",
                dedup_key=key,
                entity_type="transaction",
                entity_id=tx.id,
            ):
                new_alerts_count += 1

    # -----------------------------------------------------------------------
    # 5. Month-over-Month Expense Surge (> 25% increase)
    # -----------------------------------------------------------------------
    prev_month = today.month - 1 if today.month > 1 else 12
    prev_year = today.year if today.month > 1 else today.year - 1

    cur_start = dt.date(today.year, today.month, 1)
    prev_start = dt.date(prev_year, prev_month, 1)

    cur_spent = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.user_id == user.id,
            Transaction.date >= cur_start,
            Transaction.date <= today,
            Transaction.type == "debit",
            Transaction.classification == "expense",
        )
        .scalar()
    )
    # To be fair in comparison, compare against the same day range in previous month
    prev_end_day = min(today.day, 28)
    prev_end = dt.date(prev_year, prev_month, prev_end_day)
    prev_spent = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.user_id == user.id,
            Transaction.date >= prev_start,
            Transaction.date <= prev_end,
            Transaction.type == "debit",
            Transaction.classification == "expense",
        )
        .scalar()
    )

    cur_spent_dec = Decimal(str(cur_spent))
    prev_spent_dec = Decimal(str(prev_spent))

    if prev_spent_dec > Decimal("5000.00") and cur_spent_dec > prev_spent_dec:
        surge_pct = round(float(((cur_spent_dec - prev_spent_dec) / prev_spent_dec) * 100), 1)
        if surge_pct >= 25.0:
            key = f"expense_surge_{today.year}_{today.month}"
            if _create_alert_if_not_exists(
                alert_type="expense_surge",
                severity="warning",
                title="Expense Surge Detected",
                message=f"Your expenses so far this month (₹{cur_spent_dec}) are {surge_pct}% higher than the same period last month (₹{prev_spent_dec}).",
                dedup_key=key,
            ):
                new_alerts_count += 1

    if new_alerts_count > 0:
        db.commit()

    return new_alerts_count


@router.get("", response_model=AlertListResponse)
def list_financial_alerts(
    is_dismissed: bool = Query(False),
    is_read: bool | None = Query(None),
    severity: str | None = Query(None),
    alert_type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve financial alerts with unread counter and filters."""
    # First evaluate any new alerts on the fly
    evaluate_financial_alerts(db, current_user)

    query = db.query(FinancialAlert).filter(
        FinancialAlert.user_id == current_user.id,
        FinancialAlert.is_dismissed == is_dismissed,
    )

    if is_read is not None:
        query = query.filter(FinancialAlert.is_read == is_read)
    if severity:
        query = query.filter(FinancialAlert.severity == severity)
    if alert_type:
        query = query.filter(FinancialAlert.alert_type == alert_type)

    alerts = query.order_by(FinancialAlert.created_at.desc()).all()

    unread_count = (
        db.query(func.count(FinancialAlert.id))
        .filter(
            FinancialAlert.user_id == current_user.id,
            FinancialAlert.is_dismissed.is_(False),
            FinancialAlert.is_read.is_(False),
        )
        .scalar()
        or 0
    )

    return AlertListResponse(
        unread_count=unread_count,
        items=[AlertResponse.model_validate(a) for a in alerts],
    )


@router.post("/evaluate")
def trigger_alert_evaluation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually trigger alert evaluation."""
    new_count = evaluate_financial_alerts(db, current_user)
    return {"status": "success", "new_alerts_created": new_count}


@router.post("/{alert_id}/read", response_model=AlertResponse)
def mark_alert_read(
    alert_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark an alert as read."""
    alert = (
        db.query(FinancialAlert)
        .filter(FinancialAlert.id == alert_id, FinancialAlert.user_id == current_user.id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    alert.is_read = True
    alert.read_at = func.now()
    db.commit()
    db.refresh(alert)
    return AlertResponse.model_validate(alert)


@router.post("/read-all")
def mark_all_alerts_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark all active alerts as read."""
    db.query(FinancialAlert).filter(
        FinancialAlert.user_id == current_user.id,
        FinancialAlert.is_dismissed.is_(False),
        FinancialAlert.is_read.is_(False),
    ).update({FinancialAlert.is_read: True, FinancialAlert.read_at: func.now()})
    db.commit()
    return {"status": "success", "message": "All alerts marked as read"}


@router.post("/{alert_id}/dismiss", response_model=AlertResponse)
def dismiss_alert(
    alert_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dismiss an alert from the active view."""
    alert = (
        db.query(FinancialAlert)
        .filter(FinancialAlert.id == alert_id, FinancialAlert.user_id == current_user.id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    alert.is_dismissed = True
    alert.dismissed_at = func.now()
    db.commit()
    db.refresh(alert)
    return AlertResponse.model_validate(alert)


@router.get("/preferences", response_model=AlertPreferencesResponse)
def get_alert_preferences(
    current_user: User = Depends(get_current_user),
):
    """Get user's notification preferences."""
    prefs = _get_user_preferences(current_user)
    return AlertPreferencesResponse(
        budget_alerts=prefs["budget_alerts"],
        recurring_alerts=prefs["recurring_alerts"],
        unusual_spending_alerts=prefs["unusual_spending_alerts"],
        goal_alerts=prefs["goal_alerts"],
        large_expense_threshold=Decimal(str(prefs["large_expense_threshold"])),
    )


@router.put("/preferences", response_model=AlertPreferencesResponse)
def update_alert_preferences(
    payload: AlertPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update user's notification preferences."""
    current_prefs = _get_user_preferences(current_user)

    if payload.budget_alerts is not None:
        current_prefs["budget_alerts"] = payload.budget_alerts
    if payload.recurring_alerts is not None:
        current_prefs["recurring_alerts"] = payload.recurring_alerts
    if payload.unusual_spending_alerts is not None:
        current_prefs["unusual_spending_alerts"] = payload.unusual_spending_alerts
    if payload.goal_alerts is not None:
        current_prefs["goal_alerts"] = payload.goal_alerts
    if payload.large_expense_threshold is not None:
        current_prefs["large_expense_threshold"] = str(payload.large_expense_threshold)

    current_user.alert_preferences = current_prefs
    db.commit()

    return AlertPreferencesResponse(
        budget_alerts=current_prefs["budget_alerts"],
        recurring_alerts=current_prefs["recurring_alerts"],
        unusual_spending_alerts=current_prefs["unusual_spending_alerts"],
        goal_alerts=current_prefs["goal_alerts"],
        large_expense_threshold=Decimal(str(current_prefs["large_expense_threshold"])),
    )

