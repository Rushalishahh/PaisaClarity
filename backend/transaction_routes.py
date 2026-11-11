"""Transaction management API routes for PaisaClarity (Phase 6)."""

import hashlib
import math
import uuid
from decimal import Decimal
import datetime as dt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, and_, desc, asc
from sqlalchemy.orm import Session

from auth_dependency import get_current_user
from categorizer import normalize_description
from database import get_db
from models import User, FinancialAccount, Category, Transaction
from schemas import (
    TransactionCreate,
    TransferCreate,
    TransactionUpdate,
    CategoryCorrection,
    TransactionResponse,
    PaginatedTransactionsResponse,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _compute_tx_key(date_val: dt.date, description: str, amount_val: Decimal) -> str:
    norm_desc = normalize_description(description)
    key_str = f"{date_val.isoformat()}|{norm_desc}|{amount_val:.2f}"
    return hashlib.sha256(key_str.encode("utf-8")).hexdigest()


def _resolve_category_and_classification(
    db: Session,
    user_id: int,
    category_id: int | None,
    category_name: str | None,
    tx_type: str,
    explicit_classification: str | None = None,
) -> tuple[int | None, str, str]:
    """Resolves category_id and category string synchronously, and determines classification.
    
    Returns (category_id, category_string, classification).
    """
    found_cat = None
    if category_id is not None:
        found_cat = (
            db.query(Category)
            .filter(
                Category.id == category_id,
                or_(Category.is_system == True, Category.user_id == user_id),
            )
            .first()
        )
        if not found_cat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with id {category_id} not found",
            )
    elif category_name:
        clean_name = category_name.strip()
        found_cat = (
            db.query(Category)
            .filter(
                Category.name.ilike(clean_name),
                or_(Category.is_system == True, Category.user_id == user_id),
            )
            .first()
        )

    if found_cat:
        resolved_cat_id = found_cat.id
        resolved_cat_name = found_cat.name
        cat_type = found_cat.category_type
    else:
        resolved_cat_id = None
        resolved_cat_name = category_name.strip() if category_name else ("Income" if tx_type == "credit" else "Other")
        cat_type = "income" if tx_type == "credit" else "expense"

    if explicit_classification:
        classification = explicit_classification.lower().strip()
    else:
        if cat_type == "transfer" or resolved_cat_name.lower() in ("transfers", "transfer"):
            classification = "transfer"
        elif cat_type == "investment" or resolved_cat_name.lower() in ("investments", "investment"):
            classification = "investment"
        elif tx_type == "credit" or cat_type == "income":
            classification = "income"
        else:
            classification = "expense"

    return resolved_cat_id, resolved_cat_name, classification


@router.get("", response_model=PaginatedTransactionsResponse)
def list_transactions(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    account_id: int | None = Query(None, description="Filter by financial account"),
    category_id: int | None = Query(None, description="Filter by category ID"),
    category: str | None = Query(None, description="Filter by category name"),
    start_date: dt.date | None = Query(None, description="Filter start date"),
    end_date: dt.date | None = Query(None, description="Filter end date"),
    type: str | None = Query(None, description="Filter by debit/credit"),
    classification: str | None = Query(None, description="Filter by classification"),
    min_amount: Decimal | None = Query(None, description="Filter minimum amount"),
    max_amount: Decimal | None = Query(None, description="Filter maximum amount"),
    search: str | None = Query(None, description="Search description or merchant"),
    sort_by: str = Query("date", description="Field to sort by: date or amount"),
    sort_order: str = Query("desc", description="Sort direction: asc or desc"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List transactions for the authenticated user with multi-dimensional filtering,
    full-text search, and pagination.
    """
    query = db.query(Transaction).filter(Transaction.user_id == current_user.id)

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)
    if category_id is not None:
        query = query.filter(Transaction.category_id == category_id)
    if category:
        query = query.filter(Transaction.category.ilike(f"%{category.strip()}%"))
    if start_date is not None:
        query = query.filter(Transaction.date >= start_date)
    if end_date is not None:
        query = query.filter(Transaction.date <= end_date)
    if type:
        query = query.filter(Transaction.type == type.lower().strip())
    if classification:
        query = query.filter(Transaction.classification == classification.lower().strip())
    if min_amount is not None:
        query = query.filter(Transaction.amount >= min_amount)
    if max_amount is not None:
        query = query.filter(Transaction.amount <= max_amount)
    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Transaction.description.ilike(search_pattern),
                Transaction.merchant.ilike(search_pattern),
                Transaction.ref_no.ilike(search_pattern),
            )
        )

    # Sorting
    order_func = desc if sort_order.lower() == "desc" else asc
    if sort_by.lower() == "amount":
        query = query.order_by(order_func(Transaction.amount), desc(Transaction.date), desc(Transaction.id))
    else:
        query = query.order_by(order_func(Transaction.date), desc(Transaction.id))

    total = query.count()
    pages = math.ceil(total / page_size) if total > 0 else 1
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedTransactionsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_manual_transaction(
    tx_in: TransactionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a manual transaction owned by the authenticated user."""
    # Validate account ownership if account_id is provided
    if tx_in.account_id is not None:
        acc = (
            db.query(FinancialAccount)
            .filter(FinancialAccount.id == tx_in.account_id, FinancialAccount.user_id == current_user.id)
            .first()
        )
        if not acc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Financial account not found",
            )

    # Synchronize category and classification
    cat_id, cat_name, classification = _resolve_category_and_classification(
        db,
        current_user.id,
        tx_in.category_id,
        tx_in.category,
        tx_in.type,
        tx_in.classification,
    )

    amount_quantized = tx_in.amount.quantize(Decimal("0.01"))
    tx_key = _compute_tx_key(tx_in.date, tx_in.description, amount_quantized)

    transaction = Transaction(
        user_id=current_user.id,
        account_id=tx_in.account_id,
        date=tx_in.date,
        value_date=tx_in.value_date or tx_in.date,
        description=tx_in.description.strip(),
        merchant=tx_in.merchant.strip() if tx_in.merchant else None,
        amount=amount_quantized,
        type=tx_in.type.lower().strip(),
        classification=classification,
        category_id=cat_id,
        category=cat_name,
        ref_no=tx_in.ref_no.strip() if tx_in.ref_no else None,
        transaction_key=tx_key,
        import_metadata={"source": "manual"},
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.post("/transfer", status_code=status.HTTP_201_CREATED)
def create_transfer(
    transfer_in: TransferCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an atomic dual-leg transfer between two accounts owned by the authenticated user.
    Both legs share a unique transfer_group_id UUID.
    """
    from_acc = (
        db.query(FinancialAccount)
        .filter(FinancialAccount.id == transfer_in.from_account_id, FinancialAccount.user_id == current_user.id)
        .first()
    )
    if not from_acc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source account not found",
        )

    to_acc = (
        db.query(FinancialAccount)
        .filter(FinancialAccount.id == transfer_in.to_account_id, FinancialAccount.user_id == current_user.id)
        .first()
    )
    if not to_acc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Destination account not found",
        )

    group_id = str(uuid.uuid4())
    amount_quantized = transfer_in.amount.quantize(Decimal("0.01"))
    
    # Resolve Transfers category
    transfers_cat = (
        db.query(Category)
        .filter(
            Category.name.ilike("Transfers"),
            or_(Category.is_system == True, Category.user_id == current_user.id),
        )
        .first()
    )
    cat_id = transfers_cat.id if transfers_cat else None
    cat_name = transfers_cat.name if transfers_cat else "Transfers"

    desc = transfer_in.description or f"Transfer from {from_acc.name} to {to_acc.name}"

    # Leg 1: Outgoing debit from source account
    outgoing_tx = Transaction(
        user_id=current_user.id,
        account_id=from_acc.id,
        date=transfer_in.date,
        value_date=transfer_in.date,
        description=f"Transfer to {to_acc.name}: {desc}",
        amount=amount_quantized,
        type="debit",
        classification="transfer",
        category_id=cat_id,
        category=cat_name,
        ref_no=transfer_in.ref_no,
        transfer_group_id=group_id,
        transaction_key=_compute_tx_key(transfer_in.date, f"Transfer to {to_acc.name}", amount_quantized),
        import_metadata={"transfer_role": "outgoing", "to_account_id": to_acc.id},
    )

    # Leg 2: Incoming credit to destination account
    incoming_tx = Transaction(
        user_id=current_user.id,
        account_id=to_acc.id,
        date=transfer_in.date,
        value_date=transfer_in.date,
        description=f"Transfer from {from_acc.name}: {desc}",
        amount=amount_quantized,
        type="credit",
        classification="transfer",
        category_id=cat_id,
        category=cat_name,
        ref_no=transfer_in.ref_no,
        transfer_group_id=group_id,
        transaction_key=_compute_tx_key(transfer_in.date, f"Transfer from {from_acc.name}", amount_quantized),
        import_metadata={"transfer_role": "incoming", "from_account_id": from_acc.id},
    )

    db.add(outgoing_tx)
    db.add(incoming_tx)
    db.commit()
    db.refresh(outgoing_tx)
    db.refresh(incoming_tx)

    return {
        "status": "ok",
        "transfer_group_id": group_id,
        "outgoing_transaction": TransactionResponse.model_validate(outgoing_tx),
        "incoming_transaction": TransactionResponse.model_validate(incoming_tx),
    }


@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get single transaction details."""
    tx = (
        db.query(Transaction)
        .filter(Transaction.id == transaction_id, Transaction.user_id == current_user.id)
        .first()
    )
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return tx


@router.put("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: int,
    tx_in: TransactionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update details of a transaction."""
    tx = (
        db.query(Transaction)
        .filter(Transaction.id == transaction_id, Transaction.user_id == current_user.id)
        .first()
    )
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    if tx_in.account_id is not None:
        acc = (
            db.query(FinancialAccount)
            .filter(FinancialAccount.id == tx_in.account_id, FinancialAccount.user_id == current_user.id)
            .first()
        )
        if not acc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        tx.account_id = acc.id

    if tx_in.date is not None:
        tx.date = tx_in.date
    if tx_in.value_date is not None:
        tx.value_date = tx_in.value_date
    if tx_in.description is not None:
        tx.description = tx_in.description.strip()
    if tx_in.merchant is not None:
        tx.merchant = tx_in.merchant.strip() if tx_in.merchant else None
    if tx_in.amount is not None:
        tx.amount = tx_in.amount.quantize(Decimal("0.01"))
    if tx_in.type is not None:
        t_clean = tx_in.type.lower().strip()
        if t_clean not in ("debit", "credit"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Type must be debit or credit")
        tx.type = t_clean
    if tx_in.ref_no is not None:
        tx.ref_no = tx_in.ref_no.strip() if tx_in.ref_no else None

    # Handle Category & Classification update
    if tx_in.category_id is not None or tx_in.category is not None or tx_in.classification is not None:
        cat_id, cat_name, classification = _resolve_category_and_classification(
            db,
            current_user.id,
            tx_in.category_id if tx_in.category_id is not None else tx.category_id,
            tx_in.category if tx_in.category is not None else tx.category,
            tx.type,
            tx_in.classification,
        )
        tx.category_id = cat_id
        tx.category = cat_name
        tx.classification = classification

    # Recompute key
    tx.transaction_key = _compute_tx_key(tx.date, tx.description, tx.amount)

    db.commit()
    db.refresh(tx)
    return tx


@router.patch("/{transaction_id}/category", response_model=TransactionResponse)
def correct_transaction_category(
    transaction_id: int,
    correction: CategoryCorrection,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Quickly correct or reassign a transaction's category.
    Synchronizes both category_id and denormalized category string.
    """
    tx = (
        db.query(Transaction)
        .filter(Transaction.id == transaction_id, Transaction.user_id == current_user.id)
        .first()
    )
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    cat_id, cat_name, classification = _resolve_category_and_classification(
        db,
        current_user.id,
        correction.category_id,
        correction.category_name,
        tx.type,
    )
    tx.category_id = cat_id
    tx.category = cat_name
    tx.classification = classification

    db.commit()
    db.refresh(tx)
    return tx


@router.delete("/{transaction_id}", status_code=status.HTTP_200_OK)
def delete_transaction(
    transaction_id: int,
    delete_paired_transfer: bool = Query(True, description="If this is a transfer, also delete the opposite leg"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Safely delete a transaction.
    If part of a transfer and delete_paired_transfer=True, both legs are deleted.
    """
    tx = (
        db.query(Transaction)
        .filter(Transaction.id == transaction_id, Transaction.user_id == current_user.id)
        .first()
    )
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    # Check for transfer pairing
    if tx.transfer_group_id and delete_paired_transfer:
        db.query(Transaction).filter(
            Transaction.user_id == current_user.id,
            Transaction.transfer_group_id == tx.transfer_group_id,
        ).delete(synchronize_session=False)
    else:
        db.delete(tx)

    db.commit()
    return {"status": "ok", "message": "Transaction deleted successfully"}
