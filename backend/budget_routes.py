"""Budget management API routes for PaisaClarity (Phase 7)."""

import calendar
import datetime as dt
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth_dependency import get_current_user
from database import get_db
from models import User, Budget, BudgetAllocation, Transaction
from schemas import (
    BudgetCreate,
    BudgetUpdate,
    BudgetResponse,
    BudgetAllocationResponse,
    BudgetAllocationCreate,
    BudgetPerformanceResponse,
    BudgetPerformanceMonth,
)

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _calculate_budget_metrics(db: Session, budget: Budget) -> BudgetResponse:
    """Calculate actual spending, utilization percentages, remaining amounts and warning flags."""
    _, last_day = calendar.monthrange(budget.year, budget.month)
    start_date = dt.date(budget.year, budget.month, 1)
    end_date = dt.date(budget.year, budget.month, last_day)

    # Query expense transactions within the calendar month
    # Exclude transfers and duplicate/overlap transactions
    tx_list = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == budget.user_id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.classification == "expense",
        )
        .all()
    )

    category_spend_map: dict[str, Decimal] = {}
    for tx in tx_list:
        meta = tx.import_metadata or {}
        if meta.get("is_overlap") is True:
            continue
        norm_key = (tx.category or "Uncategorized").strip().lower()
        val = Decimal(str(tx.amount)).quantize(Decimal("0.01"))
        category_spend_map[norm_key] = category_spend_map.get(norm_key, Decimal("0.00")) + val

    total_spent = sum(category_spend_map.values(), Decimal("0.00")).quantize(Decimal("0.01"))

    # Compute allocation-level metrics
    allocation_responses: list[BudgetAllocationResponse] = []
    total_allocated = Decimal("0.00")

    for alloc in budget.allocations:
        alloc_amt = Decimal(str(alloc.allocated_amount)).quantize(Decimal("0.01"))
        total_allocated += alloc_amt

        norm_cat = (alloc.category_name or "").strip().lower()
        alloc_spent = category_spend_map.get(norm_cat, Decimal("0.00"))
        remaining = (alloc_amt - alloc_spent).quantize(Decimal("0.01"))

        if alloc_amt > Decimal("0.00"):
            utilization_pct = round(float((alloc_spent / alloc_amt) * 100), 2)
            is_exceeded = alloc_spent > alloc_amt
            warning_th = float(budget.warning_threshold)
            is_warning = (utilization_pct >= warning_th) and not is_exceeded
        else:
            utilization_pct = 100.0 if alloc_spent > Decimal("0.00") else 0.0
            is_exceeded = alloc_spent > Decimal("0.00")
            is_warning = False

        allocation_responses.append(
            BudgetAllocationResponse(
                id=alloc.id,
                budget_id=alloc.budget_id,
                category_id=alloc.category_id,
                category_name=alloc.category_name,
                allocated_amount=alloc_amt,
                actual_spent=alloc_spent,
                remaining=remaining,
                utilization_pct=utilization_pct,
                is_exceeded=is_exceeded,
                is_warning=is_warning,
                notes=alloc.notes,
                created_at=alloc.created_at,
                updated_at=alloc.updated_at,
            )
        )

    # Overall budget metrics
    reference_limit = (
        Decimal(str(budget.total_budget_limit)).quantize(Decimal("0.01"))
        if budget.total_budget_limit is not None and budget.total_budget_limit > 0
        else total_allocated
    )

    if reference_limit > Decimal("0.00"):
        overall_utilization = round(float((total_spent / reference_limit) * 100), 2)
        total_remaining = (reference_limit - total_spent).quantize(Decimal("0.01"))
        overall_is_exceeded = total_spent > reference_limit
    else:
        overall_utilization = 100.0 if total_spent > Decimal("0.00") else 0.0
        total_remaining = -total_spent
        overall_is_exceeded = total_spent > Decimal("0.00")

    return BudgetResponse(
        id=budget.id,
        user_id=budget.user_id,
        month=budget.month,
        year=budget.year,
        total_budget_limit=(
            Decimal(str(budget.total_budget_limit)).quantize(Decimal("0.01"))
            if budget.total_budget_limit is not None
            else None
        ),
        total_allocated=total_allocated.quantize(Decimal("0.01")),
        total_spent=total_spent,
        total_remaining=total_remaining,
        overall_utilization_pct=overall_utilization,
        overall_is_exceeded=overall_is_exceeded,
        warning_threshold=Decimal(str(budget.warning_threshold)).quantize(Decimal("0.01")),
        is_archived=budget.is_archived,
        allocations=allocation_responses,
        created_at=budget.created_at,
        updated_at=budget.updated_at,
    )


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
def create_budget(
    payload: BudgetCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new monthly budget with category allocations."""
    # Check if budget already exists for this (user_id, month, year)
    existing = (
        db.query(Budget)
        .filter(
            Budget.user_id == current_user.id,
            Budget.month == payload.month,
            Budget.year == payload.year,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A budget for {payload.month}/{payload.year} already exists",
        )

    budget = Budget(
        user_id=current_user.id,
        month=payload.month,
        year=payload.year,
        total_budget_limit=payload.total_budget_limit,
        warning_threshold=payload.warning_threshold,
    )
    db.add(budget)
    db.flush()  # Populate budget.id

    # Check for duplicate category allocations in payload
    seen_categories: set[str] = set()
    for alloc_in in payload.allocations:
        cat_key = alloc_in.category_name.strip().lower()
        if cat_key in seen_categories:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate allocation for category '{alloc_in.category_name}'",
            )
        seen_categories.add(cat_key)

        allocation = BudgetAllocation(
            budget_id=budget.id,
            category_id=alloc_in.category_id,
            category_name=alloc_in.category_name.strip(),
            allocated_amount=alloc_in.allocated_amount,
            notes=alloc_in.notes,
        )
        db.add(allocation)

    db.commit()
    db.refresh(budget)
    return _calculate_budget_metrics(db, budget)


@router.get("", response_model=list[BudgetResponse])
def list_budgets(
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000, le=2100),
    is_archived: bool | None = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List budgets for current user with actual spend and utilization metrics."""
    query = db.query(Budget).filter(Budget.user_id == current_user.id)
    if is_archived is not None:
        query = query.filter(Budget.is_archived == is_archived)
    if month is not None:
        query = query.filter(Budget.month == month)
    if year is not None:
        query = query.filter(Budget.year == year)

    budgets = query.order_by(Budget.year.desc(), Budget.month.desc()).all()
    return [_calculate_budget_metrics(db, b) for b in budgets]


@router.get("/current", response_model=BudgetResponse)
def get_current_budget(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the budget for the current calendar month and year."""
    today = dt.date.today()
    budget = (
        db.query(Budget)
        .filter(
            Budget.user_id == current_user.id,
            Budget.month == today.month,
            Budget.year == today.year,
        )
        .first()
    )
    if not budget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No budget found for current month ({today.month}/{today.year})",
        )
    return _calculate_budget_metrics(db, budget)


@router.get("/performance/comparison", response_model=BudgetPerformanceResponse)
def get_budget_performance_comparison(
    months: int = Query(6, ge=1, le=24),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get historical performance comparison across past months."""
    today = dt.date.today()
    result_months: list[BudgetPerformanceMonth] = []

    # Iterate backwards from current month
    cur_year = today.year
    cur_month = today.month

    for _ in range(months):
        budget = (
            db.query(Budget)
            .filter(
                Budget.user_id == current_user.id,
                Budget.month == cur_month,
                Budget.year == cur_year,
            )
            .first()
        )
        if budget:
            metrics = _calculate_budget_metrics(db, budget)
            result_months.append(
                BudgetPerformanceMonth(
                    month=cur_month,
                    year=cur_year,
                    total_budget_limit=metrics.total_budget_limit,
                    total_allocated=metrics.total_allocated,
                    total_spent=metrics.total_spent,
                    overall_utilization_pct=metrics.overall_utilization_pct,
                    is_exceeded=metrics.overall_is_exceeded,
                )
            )
        else:
            # Check if there is spending in that month even without a formal budget
            _, last_d = calendar.monthrange(cur_year, cur_month)
            m_start = dt.date(cur_year, cur_month, 1)
            m_end = dt.date(cur_year, cur_month, last_d)
            m_txs = (
                db.query(Transaction)
                .filter(
                    Transaction.user_id == current_user.id,
                    Transaction.date >= m_start,
                    Transaction.date <= m_end,
                    Transaction.classification == "expense",
                )
                .all()
            )
            m_spent_dec = sum(
                (
                    Decimal(str(t.amount))
                    for t in m_txs
                    if not (t.import_metadata or {}).get("is_overlap")
                ),
                Decimal("0.00"),
            ).quantize(Decimal("0.01"))
            result_months.append(
                BudgetPerformanceMonth(
                    month=cur_month,
                    year=cur_year,
                    total_budget_limit=None,
                    total_allocated=Decimal("0.00"),
                    total_spent=m_spent_dec,
                    overall_utilization_pct=0.0,
                    is_exceeded=False,
                )
            )

        # Move to previous month
        cur_month -= 1
        if cur_month == 0:
            cur_month = 12
            cur_year -= 1

    # Return chronological order (oldest to newest)
    result_months.reverse()
    return BudgetPerformanceResponse(history=result_months)


@router.get("/{budget_id}", response_model=BudgetResponse)
def get_budget(
    budget_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve details of a single budget with calculated allocations and spend."""
    budget = (
        db.query(Budget)
        .filter(Budget.id == budget_id, Budget.user_id == current_user.id)
        .first()
    )
    if not budget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found",
        )
    return _calculate_budget_metrics(db, budget)


@router.put("/{budget_id}", response_model=BudgetResponse)
def update_budget(
    budget_id: int,
    payload: BudgetUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update budget limits, warning threshold, or category allocations."""
    budget = (
        db.query(Budget)
        .filter(Budget.id == budget_id, Budget.user_id == current_user.id)
        .first()
    )
    if not budget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found",
        )

    if payload.total_budget_limit is not None:
        budget.total_budget_limit = payload.total_budget_limit
    if payload.warning_threshold is not None:
        budget.warning_threshold = payload.warning_threshold
    if payload.is_archived is not None:
        budget.is_archived = payload.is_archived

    # If allocations are provided, synchronize them
    if payload.allocations is not None:
        # Check duplicate category in payload
        seen_cats: set[str] = set()
        for a in payload.allocations:
            cat_k = a.category_name.strip().lower()
            if cat_k in seen_cats:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Duplicate allocation for category '{a.category_name}'",
                )
            seen_cats.add(cat_k)

        # Remove existing allocations and replace with new ones
        for old_alloc in list(budget.allocations):
            db.delete(old_alloc)
        db.flush()

        for alloc_in in payload.allocations:
            new_alloc = BudgetAllocation(
                budget_id=budget.id,
                category_id=alloc_in.category_id,
                category_name=alloc_in.category_name.strip(),
                allocated_amount=alloc_in.allocated_amount,
                notes=alloc_in.notes,
            )
            db.add(new_alloc)

    db.commit()
    db.refresh(budget)
    return _calculate_budget_metrics(db, budget)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
    budget_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a budget and its category allocations."""
    budget = (
        db.query(Budget)
        .filter(Budget.id == budget_id, Budget.user_id == current_user.id)
        .first()
    )
    if not budget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found",
        )
    db.delete(budget)
    db.commit()
    return None
