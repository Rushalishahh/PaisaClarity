"""Account management API routes for PaisaClarity (Phase 6)."""

from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth_dependency import get_current_user
from database import get_db
from models import User, FinancialAccount, Transaction
from schemas import (
    AccountCreate,
    AccountUpdate,
    AccountReconcile,
    AccountResponse,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _compute_calculated_balance(db: Session, account: FinancialAccount) -> Decimal | None:
    """Calculate account balance from opening balance and transactions.
    
    Returns None for imported/unreconciled accounts to prevent presenting
    unverified data as accurate balance.
    """
    if not account.is_reconciled or account.account_type == "imported":
        return None

    # Calculate sum of credits and debits for this account
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
    opening = account.opening_balance if account.opening_balance is not None else Decimal("0.00")
    return Decimal(str(opening)) + Decimal(str(credit_sum)) - Decimal(str(debit_sum))


def _account_to_response(db: Session, account: FinancialAccount) -> AccountResponse:
    tx_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.account_id == account.id)
        .scalar()
        or 0
    )
    calc_bal = _compute_calculated_balance(db, account)
    return AccountResponse(
        id=account.id,
        user_id=account.user_id,
        name=account.name,
        account_type=account.account_type,
        currency=account.currency,
        opening_balance=account.opening_balance,
        calculated_balance=calc_bal,
        masked_identifier=account.masked_identifier,
        is_archived=account.is_archived,
        is_reconciled=account.is_reconciled,
        transaction_count=tx_count,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    account_in: AccountCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new financial account owned by the authenticated user."""
    account = FinancialAccount(
        user_id=current_user.id,
        name=account_in.name,
        account_type=account_in.account_type,
        currency=account_in.currency,
        opening_balance=account_in.opening_balance,
        masked_identifier=account_in.masked_identifier,
        is_archived=False,
        is_reconciled=True if account_in.account_type != "imported" else False,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return _account_to_response(db, account)


@router.get("", response_model=list[AccountResponse])
def list_accounts(
    include_archived: bool = Query(False, description="Include archived accounts"),
    include_imported: bool = Query(True, description="Include unreconciled imported accounts"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List financial accounts owned by the authenticated user."""
    query = db.query(FinancialAccount).filter(FinancialAccount.user_id == current_user.id)
    if not include_archived:
        query = query.filter(FinancialAccount.is_archived == False)
    if not include_imported:
        query = query.filter(FinancialAccount.account_type != "imported")

    accounts = query.order_by(FinancialAccount.created_at.asc()).all()
    return [_account_to_response(db, acc) for acc in accounts]


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get details of a specific financial account."""
    account = (
        db.query(FinancialAccount)
        .filter(FinancialAccount.id == account_id, FinancialAccount.user_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return _account_to_response(db, account)


@router.put("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: int,
    account_in: AccountUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update details of a financial account."""
    account = (
        db.query(FinancialAccount)
        .filter(FinancialAccount.id == account_id, FinancialAccount.user_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if account_in.name is not None:
        name_val = account_in.name.strip()
        if not name_val:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account name cannot be empty")
        account.name = name_val
    if account_in.account_type is not None:
        account.account_type = account_in.account_type
    if account_in.currency is not None:
        account.currency = account_in.currency
    if account_in.opening_balance is not None:
        account.opening_balance = account_in.opening_balance
    if account_in.masked_identifier is not None:
        account.masked_identifier = account_in.masked_identifier

    db.commit()
    db.refresh(account)
    return _account_to_response(db, account)


@router.post("/{account_id}/archive", response_model=AccountResponse)
def archive_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Archive an account so it no longer appears in default listings."""
    account = (
        db.query(FinancialAccount)
        .filter(FinancialAccount.id == account_id, FinancialAccount.user_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    account.is_archived = True
    db.commit()
    db.refresh(account)
    return _account_to_response(db, account)


@router.post("/{account_id}/unarchive", response_model=AccountResponse)
def unarchive_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unarchive an account."""
    account = (
        db.query(FinancialAccount)
        .filter(FinancialAccount.id == account_id, FinancialAccount.user_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    account.is_archived = False
    db.commit()
    db.refresh(account)
    return _account_to_response(db, account)


@router.post("/{account_id}/reconcile", response_model=AccountResponse)
def reconcile_account(
    account_id: int,
    workflow: AccountReconcile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reconcile an imported placeholder account:
    Either convert it into a verified account (setting real account_type, name, mask)
    OR reassign/merge its transactions into an existing verified account.
    """
    account = (
        db.query(FinancialAccount)
        .filter(FinancialAccount.id == account_id, FinancialAccount.user_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if workflow.merge_into_account_id is not None:
        target = (
            db.query(FinancialAccount)
            .filter(
                FinancialAccount.id == workflow.merge_into_account_id,
                FinancialAccount.user_id == current_user.id,
            )
            .first()
        )
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target merge account not found")
        if target.id == account.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot merge an account into itself")

        # Query existing transactions in target account to prevent double counting
        target_txs = (
            db.query(Transaction)
            .filter(Transaction.account_id == target.id, Transaction.user_id == current_user.id)
            .all()
        )
        target_keys = {
            (t.date, t.transaction_key, t.amount, t.type)
            for t in target_txs
            if not (t.import_metadata or {}).get("is_overlap")
        }

        source_txs = (
            db.query(Transaction)
            .filter(Transaction.account_id == account.id, Transaction.user_id == current_user.id)
            .all()
        )
        for s_tx in source_txs:
            s_key = (s_tx.date, s_tx.transaction_key, s_tx.amount, s_tx.type)
            if s_key in target_keys:
                meta = dict(s_tx.import_metadata or {})
                meta["is_overlap"] = True
                meta["merged_duplicate"] = True
                s_tx.import_metadata = meta
            s_tx.account_id = target.id

        # Archive the source imported account
        account.is_archived = True
        account.is_reconciled = True
        db.commit()
        db.refresh(target)
        return _account_to_response(db, target)

    # In-place reconciliation
    if workflow.name:
        account.name = workflow.name.strip()
    if workflow.account_type:
        account.account_type = workflow.account_type
    if workflow.masked_identifier:
        account.masked_identifier = workflow.masked_identifier

    account.is_reconciled = True
    db.commit()
    db.refresh(account)
    return _account_to_response(db, account)


@router.delete("/{account_id}", status_code=status.HTTP_200_OK)
def delete_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Safely delete an account if and only if it has NO associated transactions.
    If transactions exist, deletion is rejected to prevent orphaning records.
    """
    account = (
        db.query(FinancialAccount)
        .filter(FinancialAccount.id == account_id, FinancialAccount.user_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    tx_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.account_id == account.id)
        .scalar()
        or 0
    )
    if tx_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot delete account '{account.name}' because it contains {tx_count} transaction(s). "
                "Please archive the account or reassign its transactions before deleting."
            ),
        )

    db.delete(account)
    db.commit()
    return {"status": "ok", "message": f"Account '{account.name}' deleted successfully"}
