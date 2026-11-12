"""Recurring payments and subscriptions management API routes for PaisaClarity (Phase 8)."""

from collections import defaultdict
import datetime as dt
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth_dependency import get_current_user
from database import get_db
from models import User, RecurringPayment, Transaction
from schemas import (
    RecurringPaymentCreate,
    RecurringPaymentUpdate,
    RecurringPaymentResponse,
    RecurringSummaryResponse,
)
from insights import _normalize_merchant
from categorizer import NON_SPENDING_CATEGORIES

router = APIRouter(prefix="/recurring", tags=["recurring-payments"])


def _calculate_next_date(last_date: dt.date, frequency: str = "monthly") -> dt.date:
    """Estimate the next payment date based on last payment and frequency."""
    if frequency == "weekly":
        return last_date + dt.timedelta(days=7)
    elif frequency == "quarterly":
        # Roughly 3 months
        year = last_date.year + (last_date.month + 3 - 1) // 12
        month = (last_date.month + 3 - 1) % 12 + 1
        day = min(last_date.day, 28)
        return dt.date(year, month, day)
    elif frequency == "yearly":
        return dt.date(last_date.year + 1, last_date.month, min(last_date.day, 28))
    else:  # monthly default
        year = last_date.year + last_date.month // 12
        month = last_date.month % 12 + 1
        day = min(last_date.day, 28)
        return dt.date(year, month, day)


@router.get("", response_model=RecurringSummaryResponse)
def list_recurring_payments(
    status_filter: str | None = Query(None, alias="status"),
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List recurring payments with monthly commitment, active count, and upcoming bills."""
    query = db.query(RecurringPayment).filter(RecurringPayment.user_id == current_user.id)

    if status_filter:
        query = query.filter(RecurringPayment.status == status_filter)
    elif not include_inactive:
        # Default view shows detected and confirmed, excludes rejected and inactive
        query = query.filter(RecurringPayment.status.in_(["detected", "confirmed"]))

    items = query.order_by(RecurringPayment.next_expected_date.asc().nulls_last(), RecurringPayment.id.desc()).all()

    # Calculate summary metrics across all user recurring payments
    all_user_items = db.query(RecurringPayment).filter(RecurringPayment.user_id == current_user.id).all()

    total_monthly = Decimal("0.00")
    active_count = 0
    detected_count = 0
    today = dt.date.today()
    upcoming_limit = today + dt.timedelta(days=30)
    upcoming: list[RecurringPayment] = []

    for item in all_user_items:
        amt = Decimal(str(item.average_amount)).quantize(Decimal("0.01"))
        if item.status == "confirmed":
            active_count += 1
            # Normalize to monthly commitment
            if item.frequency == "weekly":
                total_monthly += (amt * Decimal("4.33")).quantize(Decimal("0.01"))
            elif item.frequency == "quarterly":
                total_monthly += (amt / Decimal("3")).quantize(Decimal("0.01"))
            elif item.frequency == "yearly":
                total_monthly += (amt / Decimal("12")).quantize(Decimal("0.01"))
            else:
                total_monthly += amt

            if item.next_expected_date and today <= item.next_expected_date <= upcoming_limit:
                upcoming.append(item)
        elif item.status == "detected":
            detected_count += 1

    upcoming.sort(key=lambda x: x.next_expected_date or dt.date.max)

    return RecurringSummaryResponse(
        total_monthly_commitment=total_monthly,
        active_count=active_count,
        detected_count=detected_count,
        upcoming_payments=[RecurringPaymentResponse.model_validate(p) for p in upcoming],
        items=[RecurringPaymentResponse.model_validate(p) for p in items],
    )


@router.post("/scan")
def scan_recurring_transactions(
    min_months: int = Query(2, ge=2, le=12),
    amount_tolerance: float = Query(0.15, ge=0.01, le=0.5),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Scan normalized transactions to automatically detect recurring payments."""
    txs = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == current_user.id,
            Transaction.type == "debit",
            Transaction.classification == "expense",
        )
        .order_by(Transaction.date.asc())
        .all()
    )

    # Filter out overlap duplicates and non-spending categories
    valid_txs = [
        t for t in txs
        if not (t.import_metadata or {}).get("is_overlap")
        and t.category not in NON_SPENDING_CATEGORIES
    ]

    # Group by normalized merchant
    merchant_groups: dict[str, list[Transaction]] = defaultdict(list)
    for t in valid_txs:
        merchant_name = (t.merchant or _normalize_merchant(t.description)).strip()
        if len(merchant_name) >= 3:
            merchant_groups[merchant_name.upper()].append(t)

    new_detected = 0
    updated_count = 0

    for merchant_name, m_txs in merchant_groups.items():
        # Group by Year-Month to check distinct months seen
        month_to_amounts: dict[str, list[Decimal]] = defaultdict(list)
        for t in m_txs:
            month_key = t.date.strftime("%Y-%m")
            month_to_amounts[month_key].append(Decimal(str(t.amount)))

        if len(month_to_amounts) < min_months:
            continue

        # Average amount per month
        monthly_avgs = [sum(amts) / Decimal(len(amts)) for amts in month_to_amounts.values()]
        overall_avg = sum(monthly_avgs) / Decimal(len(monthly_avgs))

        if overall_avg <= Decimal("0.00"):
            continue

        # Check tolerance
        is_consistent = True
        for m_avg in monthly_avgs:
            diff = abs(m_avg - overall_avg)
            fraction = diff / overall_avg
            if fraction > Decimal(str(amount_tolerance)):
                is_consistent = False
                break

        if not is_consistent:
            continue

        # Found consistent recurring payment!
        all_dates = sorted([t.date for t in m_txs])
        first_date = all_dates[0]
        last_date = all_dates[-1]
        next_date = _calculate_next_date(last_date, "monthly")
        cat = m_txs[-1].category or "Bills"
        acc_id = m_txs[-1].account_id

        # Check existing recurring record
        existing = (
            db.query(RecurringPayment)
            .filter(
                RecurringPayment.user_id == current_user.id,
                func.upper(RecurringPayment.name) == merchant_name,
            )
            .first()
        )

        if existing:
            # Update occurrence count and dates
            existing.occurrence_count = len(m_txs)
            existing.last_payment_date = last_date
            existing.average_amount = overall_avg.quantize(Decimal("0.01"))
            if not existing.next_expected_date or existing.next_expected_date < dt.date.today():
                existing.next_expected_date = next_date
            updated_count += 1
        else:
            # Create new detected recurring payment
            rec = RecurringPayment(
                user_id=current_user.id,
                account_id=acc_id,
                name=merchant_name,
                category=cat,
                average_amount=overall_avg.quantize(Decimal("0.01")),
                frequency="monthly",
                status="detected",
                next_expected_date=next_date,
                last_payment_date=last_date,
                first_seen_date=first_date,
                occurrence_count=len(m_txs),
                is_auto_detected=True,
                notes=f"Auto-detected from {len(m_txs)} transactions across {len(month_to_amounts)} months",
            )
            db.add(rec)
            new_detected += 1

    db.commit()
    return {
        "status": "success",
        "new_detected": new_detected,
        "updated": updated_count,
        "total_scanned_merchants": len(merchant_groups),
    }


@router.post("", response_model=RecurringPaymentResponse, status_code=status.HTTP_201_CREATED)
def create_recurring_payment(
    payload: RecurringPaymentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a recurring payment or subscription manually."""
    rec = RecurringPayment(
        user_id=current_user.id,
        account_id=payload.account_id,
        name=payload.name.strip(),
        category=payload.category.strip() if payload.category else "Bills",
        average_amount=payload.average_amount,
        frequency=payload.frequency.strip().lower(),
        status="confirmed",
        next_expected_date=payload.next_expected_date,
        last_payment_date=dt.date.today(),
        first_seen_date=dt.date.today(),
        occurrence_count=1,
        is_auto_detected=False,
        notes=payload.notes.strip() if payload.notes else None,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return RecurringPaymentResponse.model_validate(rec)


@router.get("/{payment_id}", response_model=RecurringPaymentResponse)
def get_recurring_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get details of a recurring payment."""
    rec = (
        db.query(RecurringPayment)
        .filter(RecurringPayment.id == payment_id, RecurringPayment.user_id == current_user.id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring payment not found")
    return RecurringPaymentResponse.model_validate(rec)


@router.put("/{payment_id}", response_model=RecurringPaymentResponse)
def update_recurring_payment(
    payment_id: int,
    payload: RecurringPaymentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update recurring payment details."""
    rec = (
        db.query(RecurringPayment)
        .filter(RecurringPayment.id == payment_id, RecurringPayment.user_id == current_user.id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring payment not found")

    if payload.name is not None:
        rec.name = payload.name.strip()
    if payload.category is not None:
        rec.category = payload.category.strip()
    if payload.average_amount is not None:
        rec.average_amount = payload.average_amount
    if payload.frequency is not None:
        rec.frequency = payload.frequency.strip().lower()
    if payload.status is not None:
        st = payload.status.strip().lower()
        if st in ("detected", "confirmed", "rejected", "inactive"):
            rec.status = st
    if payload.next_expected_date is not None:
        rec.next_expected_date = payload.next_expected_date
    if payload.notes is not None:
        rec.notes = payload.notes.strip() if payload.notes else None

    db.commit()
    db.refresh(rec)
    return RecurringPaymentResponse.model_validate(rec)


@router.post("/{payment_id}/confirm", response_model=RecurringPaymentResponse)
def confirm_recurring_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirm a detected recurring payment as active."""
    rec = (
        db.query(RecurringPayment)
        .filter(RecurringPayment.id == payment_id, RecurringPayment.user_id == current_user.id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring payment not found")
    rec.status = "confirmed"
    db.commit()
    db.refresh(rec)
    return RecurringPaymentResponse.model_validate(rec)


@router.post("/{payment_id}/reject", response_model=RecurringPaymentResponse)
def reject_recurring_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reject a detected recurring payment."""
    rec = (
        db.query(RecurringPayment)
        .filter(RecurringPayment.id == payment_id, RecurringPayment.user_id == current_user.id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring payment not found")
    rec.status = "rejected"
    db.commit()
    db.refresh(rec)
    return RecurringPaymentResponse.model_validate(rec)


@router.post("/{payment_id}/pause", response_model=RecurringPaymentResponse)
def pause_recurring_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a recurring payment as inactive/paused."""
    rec = (
        db.query(RecurringPayment)
        .filter(RecurringPayment.id == payment_id, RecurringPayment.user_id == current_user.id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring payment not found")
    rec.status = "inactive"
    db.commit()
    db.refresh(rec)
    return RecurringPaymentResponse.model_validate(rec)


@router.post("/{payment_id}/resume", response_model=RecurringPaymentResponse)
def resume_recurring_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resume an inactive recurring payment."""
    rec = (
        db.query(RecurringPayment)
        .filter(RecurringPayment.id == payment_id, RecurringPayment.user_id == current_user.id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring payment not found")
    rec.status = "confirmed"
    db.commit()
    db.refresh(rec)
    return RecurringPaymentResponse.model_validate(rec)


@router.delete("/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recurring_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a recurring payment record."""
    rec = (
        db.query(RecurringPayment)
        .filter(RecurringPayment.id == payment_id, RecurringPayment.user_id == current_user.id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring payment not found")
    db.delete(rec)
    db.commit()
    return None
