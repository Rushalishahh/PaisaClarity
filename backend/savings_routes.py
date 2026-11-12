"""Savings goals and contributions API routes for PaisaClarity (Phase 7)."""

import datetime as dt
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from auth_dependency import get_current_user
from database import get_db
from models import User, SavingsGoal, SavingsContribution
from schemas import (
    SavingsGoalCreate,
    SavingsGoalUpdate,
    SavingsGoalResponse,
    SavingsContributionCreate,
    SavingsContributionResponse,
)

router = APIRouter(prefix="/goals", tags=["savings-goals"])


def _calculate_goal_metrics(
    goal: SavingsGoal,
    contributions: list[SavingsContribution] | None = None
) -> SavingsGoalResponse:
    """Calculate total saved, remaining target, completion percentage, and monthly savings needed."""
    all_conts = contributions if contributions is not None else goal.contributions

    deposits = Decimal("0.00")
    withdrawals = Decimal("0.00")
    cont_responses: list[SavingsContributionResponse] = []

    for c in all_conts:
        amt = Decimal(str(c.amount)).quantize(Decimal("0.01"))
        if c.contribution_type == "withdrawal":
            withdrawals += amt
        else:
            deposits += amt

        cont_responses.append(
            SavingsContributionResponse(
                id=c.id,
                goal_id=c.goal_id,
                user_id=c.user_id,
                amount=amt,
                contribution_date=c.contribution_date,
                contribution_type=c.contribution_type,
                notes=c.notes,
                created_at=c.created_at,
            )
        )

    # Sort contribution responses in descending chronological order
    cont_responses.sort(key=lambda x: (x.contribution_date, x.id), reverse=True)

    net_saved = deposits - withdrawals
    total_saved = max(Decimal("0.00"), net_saved).quantize(Decimal("0.01"))
    target = Decimal(str(goal.target_amount)).quantize(Decimal("0.01"))
    remaining_target = max(Decimal("0.00"), target - total_saved).quantize(Decimal("0.01"))

    if target > Decimal("0.00"):
        completion_pct = min(100.0, round(float((total_saved / target) * 100), 2))
    else:
        completion_pct = 100.0

    is_completed = total_saved >= target

    # Monthly savings needed calculation
    monthly_savings_needed: Decimal | None = None
    today = dt.date.today()
    if goal.target_date and not is_completed:
        if goal.target_date > today:
            months = (goal.target_date.year - today.year) * 12 + (goal.target_date.month - today.month)
            if goal.target_date.day < today.day:
                months -= 1
            months = max(1, months)
            monthly_savings_needed = (remaining_target / Decimal(months)).quantize(Decimal("0.01"))
        else:
            # Deadline passed but not completed
            monthly_savings_needed = remaining_target

    return SavingsGoalResponse(
        id=goal.id,
        user_id=goal.user_id,
        name=goal.name,
        target_amount=target,
        target_date=goal.target_date,
        category=goal.category,
        notes=goal.notes,
        is_archived=goal.is_archived,
        total_saved=total_saved,
        remaining_target=remaining_target,
        completion_pct=completion_pct,
        is_completed=is_completed,
        monthly_savings_needed=monthly_savings_needed,
        contributions=cont_responses,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )


@router.post("", response_model=SavingsGoalResponse, status_code=status.HTTP_201_CREATED)
def create_goal(
    payload: SavingsGoalCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new savings goal."""
    goal = SavingsGoal(
        user_id=current_user.id,
        name=payload.name.strip(),
        target_amount=payload.target_amount,
        target_date=payload.target_date,
        category=payload.category.strip() if payload.category else None,
        notes=payload.notes.strip() if payload.notes else None,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _calculate_goal_metrics(goal, [])


@router.get("", response_model=list[SavingsGoalResponse])
def list_goals(
    include_archived: bool = Query(False),
    category: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all savings goals for the current user with progress metrics."""
    query = db.query(SavingsGoal).filter(SavingsGoal.user_id == current_user.id)
    if not include_archived:
        query = query.filter(SavingsGoal.is_archived.is_(False))
    if category:
        query = query.filter(SavingsGoal.category == category)

    goals = query.order_by(SavingsGoal.is_archived.asc(), SavingsGoal.created_at.desc()).all()
    return [_calculate_goal_metrics(g) for g in goals]


@router.get("/{goal_id}", response_model=SavingsGoalResponse)
def get_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get details of a savings goal including full contribution history."""
    goal = (
        db.query(SavingsGoal)
        .filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == current_user.id)
        .first()
    )
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Savings goal not found",
        )
    return _calculate_goal_metrics(goal)


@router.put("/{goal_id}", response_model=SavingsGoalResponse)
def update_goal(
    goal_id: int,
    payload: SavingsGoalUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update savings goal details."""
    goal = (
        db.query(SavingsGoal)
        .filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == current_user.id)
        .first()
    )
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Savings goal not found",
        )

    if payload.name is not None:
        goal.name = payload.name.strip()
    if payload.target_amount is not None:
        goal.target_amount = payload.target_amount
    if payload.target_date is not None:
        goal.target_date = payload.target_date
    if payload.category is not None:
        goal.category = payload.category.strip() if payload.category else None
    if payload.notes is not None:
        goal.notes = payload.notes.strip() if payload.notes else None
    if payload.is_archived is not None:
        goal.is_archived = payload.is_archived

    db.commit()
    db.refresh(goal)
    return _calculate_goal_metrics(goal)


@router.post("/{goal_id}/archive", response_model=SavingsGoalResponse)
def archive_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Archive a savings goal."""
    goal = (
        db.query(SavingsGoal)
        .filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == current_user.id)
        .first()
    )
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Savings goal not found",
        )
    goal.is_archived = True
    db.commit()
    db.refresh(goal)
    return _calculate_goal_metrics(goal)


@router.post("/{goal_id}/unarchive", response_model=SavingsGoalResponse)
def unarchive_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Restore an archived savings goal."""
    goal = (
        db.query(SavingsGoal)
        .filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == current_user.id)
        .first()
    )
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Savings goal not found",
        )
    goal.is_archived = False
    db.commit()
    db.refresh(goal)
    return _calculate_goal_metrics(goal)


@router.post("/{goal_id}/contributions", response_model=SavingsContributionResponse, status_code=status.HTTP_201_CREATED)
def add_contribution(
    goal_id: int,
    payload: SavingsContributionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a deposit or withdrawal contribution to a savings goal."""
    goal = (
        db.query(SavingsGoal)
        .filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == current_user.id)
        .first()
    )
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Savings goal not found",
        )

    # Compute current balance to prevent over-withdrawal
    current_metrics = _calculate_goal_metrics(goal)
    if payload.contribution_type == "withdrawal":
        if payload.amount > current_metrics.total_saved:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Withdrawal amount (₹{payload.amount}) exceeds current saved balance (₹{current_metrics.total_saved})",
            )

    contrib = SavingsContribution(
        goal_id=goal.id,
        user_id=current_user.id,
        amount=payload.amount,
        contribution_date=payload.contribution_date,
        contribution_type=payload.contribution_type,
        notes=payload.notes.strip() if payload.notes else None,
    )
    db.add(contrib)
    db.commit()
    db.refresh(contrib)

    return SavingsContributionResponse(
        id=contrib.id,
        goal_id=contrib.goal_id,
        user_id=contrib.user_id,
        amount=Decimal(str(contrib.amount)).quantize(Decimal("0.01")),
        contribution_date=contrib.contribution_date,
        contribution_type=contrib.contribution_type,
        notes=contrib.notes,
        created_at=contrib.created_at,
    )


@router.delete("/{goal_id}/contributions/{contribution_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contribution(
    goal_id: int,
    contribution_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a contribution from a savings goal."""
    contrib = (
        db.query(SavingsContribution)
        .filter(
            SavingsContribution.id == contribution_id,
            SavingsContribution.goal_id == goal_id,
            SavingsContribution.user_id == current_user.id,
        )
        .first()
    )
    if not contrib:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contribution not found",
        )

    goal = db.query(SavingsGoal).filter(SavingsGoal.id == goal_id).first()
    # Check if deleting this contribution would leave total_saved negative
    # (e.g. deleting a deposit when withdrawals occurred afterwards)
    if contrib.contribution_type == "deposit":
        other_conts = [c for c in goal.contributions if c.id != contrib.id]
        deposits = sum((Decimal(str(c.amount)) for c in other_conts if c.contribution_type == "deposit"), Decimal("0.00"))
        withdrawals = sum((Decimal(str(c.amount)) for c in other_conts if c.contribution_type == "withdrawal"), Decimal("0.00"))
        if withdrawals > deposits:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete deposit: subsequent withdrawals exceed remaining deposits",
            )

    db.delete(contrib)
    db.commit()
    return None


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a savings goal and all associated contributions."""
    goal = (
        db.query(SavingsGoal)
        .filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == current_user.id)
        .first()
    )
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Savings goal not found",
        )
    db.delete(goal)
    db.commit()
    return None

