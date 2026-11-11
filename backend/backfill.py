"""Backfill module for migrating historical Statement JSON transactions to normalized tables.

Requirements satisfied:
1. Idempotency: Uses (statement_id, source_row_index) unique constraint to ensure
   running the backfill repeatedly produces zero duplicate rows.
2. Legitimate duplicates: Identical transactions in the same statement (e.g., two ₹50 coffees
   on the same day) have different source_row_index values and are both preserved.
3. Monetary precision: Converts values directly to Decimal and quantizes to Decimal('0.01')
   without intermediate rounding floats.
4. Historical account handling: Creates an 'Imported Statements' account per user with
   account_type='imported' and is_reconciled=False, keeping placeholder accounts separate
   from verified net worth.
5. Category & Transfer classification: Synchronizes category_id with Category model and
   assigns semantic classification ('income', 'expense', 'transfer', 'investment').
"""

from decimal import Decimal, ROUND_HALF_UP
import datetime
from sqlalchemy.orm import Session

from models import Statement, FinancialAccount, Category, Transaction
from categorizer import normalize_description, categorize
from transactions import transaction_key


def to_decimal(val) -> Decimal:
    """Convert monetary values directly to Decimal with explicit 2-decimal-place quantization.
    Avoids binary floating-point representation drift."""
    if val is None or val == "":
        return Decimal("0.00")
    # Cast str directly to Decimal and apply quantization
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_date(date_val) -> datetime.date:
    """Parse a date value (string ISO format, date, or Timestamp) into datetime.date."""
    if isinstance(date_val, datetime.date):
        return date_val
    if isinstance(date_val, str):
        # Handle ISO strings e.g. "2026-06-15"
        return datetime.date.fromisoformat(date_val[:10])
    # Fallback to string slicing
    return datetime.date.fromisoformat(str(date_val)[:10])


def resolve_classification(tx_type: str, category_name: str) -> str:
    """Determine financial classification from transaction type and category."""
    cat_lower = (category_name or "").strip().lower()
    if cat_lower in ("income", "salary"):
        return "income"
    if cat_lower == "transfers":
        return "transfer"
    if cat_lower == "investments":
        return "investment"
    if tx_type == "credit":
        return "income"
    return "expense"


def backfill_statement_transactions(db: Session, user_id: int | None = None) -> dict:
    """
    Idempotent migration: extracts transactions from Statement.result['transactions']
    into normalized `transactions` table rows.

    Returns:
        dict: {'statements_processed': int, 'rows_inserted': int, 'rows_skipped_existing': int}
    """
    stmt_query = db.query(Statement).order_by(Statement.uploaded_at.asc())
    if user_id is not None:
        stmt_query = stmt_query.filter(Statement.user_id == user_id)
    statements = stmt_query.all()

    # Pre-cache system categories: {name.lower(): Category}
    categories_map = {c.name.lower(): c for c in db.query(Category).all()}

    # Cache placeholder accounts: {user_id: account_id}
    imported_accounts = {}

    rows_inserted = 0
    rows_skipped_existing = 0
    statements_processed = 0

    for stmt in statements:
        raw_txs = (stmt.result or {}).get("transactions") or []
        if not raw_txs:
            continue

        statements_processed += 1
        uid = stmt.user_id

        # Ensure 'Imported Statements' placeholder account exists for this user
        if uid not in imported_accounts:
            acct = db.query(FinancialAccount).filter(
                FinancialAccount.user_id == uid,
                FinancialAccount.name == "Imported Statements"
            ).first()
            if not acct:
                acct = FinancialAccount(
                    user_id=uid,
                    name="Imported Statements",
                    account_type="imported",
                    currency="INR",
                    opening_balance=Decimal("0.00"),
                    is_reconciled=False,  # Unreconciled placeholder, excluded from verified net worth
                    is_archived=False
                )
                db.add(acct)
                db.flush()
            imported_accounts[uid] = acct.id

        # Query existing source_row_indices for this statement to guarantee idempotency
        existing_row_indices = {
            r[0] for r in db.query(Transaction.source_row_index)
            .filter(Transaction.statement_id == stmt.id)
            .filter(Transaction.source_row_index.isnot(None))
            .all()
        }

        for idx, row in enumerate(raw_txs):
            # Check for existing source row in this statement
            if idx in existing_row_indices:
                rows_skipped_existing += 1
                continue

            date_val = parse_date(row["date"])
            value_date_val = parse_date(row["value_date"]) if row.get("value_date") else None
            amount_dec = to_decimal(row["amount"])
            balance_dec = to_decimal(row["balance"]) if row.get("balance") is not None else None
            desc = str(row.get("description", ""))
            tx_type = str(row.get("type", "debit")).lower()
            ref_no = row.get("ref_no")
            merchant = normalize_description(desc)

            # Category resolution
            cat_label = row.get("category")
            if not cat_label or cat_label == "Other":
                cat_label = categorize(desc)
            cat_obj = categories_map.get(cat_label.lower())
            cat_id = cat_obj.id if cat_obj else None

            classification = resolve_classification(tx_type, cat_label)

            # Compute cross-statement deduplication key
            t_key_tuple = transaction_key(date_val, desc, amount_dec)
            t_key_str = f"{t_key_tuple[0]}_{t_key_tuple[1]}_{t_key_tuple[2]}"

            tx = Transaction(
                user_id=uid,
                account_id=imported_accounts[uid],
                statement_id=stmt.id,
                source_row_index=idx,
                date=date_val,
                value_date=value_date_val,
                description=desc,
                merchant=merchant,
                amount=amount_dec,
                type=tx_type,
                classification=classification,
                category_id=cat_id,
                category=cat_label,
                ref_no=str(ref_no) if ref_no is not None else None,
                balance=balance_dec,
                transaction_key=t_key_str,
                transfer_group_id=None,
                import_metadata={"statement_row_index": idx, "filename": stmt.filename},
            )
            db.add(tx)
            existing_row_indices.add(idx)
            rows_inserted += 1

        db.commit()

    return {
        "statements_processed": statements_processed,
        "rows_inserted": rows_inserted,
        "rows_skipped_existing": rows_skipped_existing,
    }


def ingest_statement_transactions(
    db: Session,
    statement: Statement,
    account_id: int | None = None,
) -> dict:
    """Ingest a single Statement's transactions into the normalized Transaction table.

    1. Reuses or creates the user's placeholder account if account_id is not specified.
    2. Identifies overlapping duplicates against earlier statements for that user,
       flagging them with is_overlap=True while keeping intra-file repeats intact.
    3. Guarantees idempotency via (statement_id, source_row_index).
    """
    raw_txs = (statement.result or {}).get("transactions") or []
    if not raw_txs:
        return {"rows_inserted": 0, "rows_skipped_existing": 0, "overlap_detected": 0}

    uid = statement.user_id

    # Resolve account
    if account_id is not None:
        target_account_id = account_id
    else:
        acct = (
            db.query(FinancialAccount)
            .filter(
                FinancialAccount.user_id == uid,
                FinancialAccount.name == "Imported Statements",
            )
            .first()
        )
        if not acct:
            acct = FinancialAccount(
                user_id=uid,
                name="Imported Statements",
                account_type="imported",
                currency="INR",
                opening_balance=Decimal("0.00"),
                is_reconciled=False,
                is_archived=False,
            )
            db.add(acct)
            db.flush()
        target_account_id = acct.id

    # Pre-cache system + user categories
    categories_map = {c.name.lower(): c for c in db.query(Category).all()}

    # Build seen_keys from earlier statements of this user to detect overlap
    previous_statements = (
        db.query(Statement)
        .filter(Statement.user_id == uid, Statement.id != statement.id)
        .order_by(Statement.uploaded_at.asc())
        .all()
    )
    seen_keys = set()
    for prev in previous_statements:
        for r in ((prev.result or {}).get("transactions") or []):
            try:
                k = transaction_key(r.get("date"), r.get("description"), r.get("amount"))
                seen_keys.add(f"{k[0]}_{k[1]}_{k[2]}")
            except (TypeError, ValueError):
                continue

    # Query existing source_row_indices for this statement
    existing_row_indices = {
        r[0]
        for r in db.query(Transaction.source_row_index)
        .filter(Transaction.statement_id == statement.id)
        .filter(Transaction.source_row_index.isnot(None))
        .all()
    }

    local_keys = set()
    rows_inserted = 0
    rows_skipped_existing = 0
    overlap_detected = 0

    for idx, row in enumerate(raw_txs):
        if idx in existing_row_indices:
            rows_skipped_existing += 1
            continue

        date_val = parse_date(row["date"])
        value_date_val = parse_date(row["value_date"]) if row.get("value_date") else None
        amount_dec = to_decimal(row["amount"])
        balance_dec = to_decimal(row["balance"]) if row.get("balance") is not None else None
        desc = str(row.get("description", ""))
        tx_type = str(row.get("type", "debit")).lower()
        ref_no = row.get("ref_no")
        merchant = normalize_description(desc)

        cat_label = row.get("category")
        if not cat_label or cat_label == "Other":
            cat_label = categorize(desc)
        cat_obj = categories_map.get(cat_label.lower())
        cat_id = cat_obj.id if cat_obj else None
        classification = resolve_classification(tx_type, cat_label)

        t_key_tuple = transaction_key(date_val, desc, amount_dec)
        t_key_str = f"{t_key_tuple[0]}_{t_key_tuple[1]}_{t_key_tuple[2]}"

        # Overlap detection:
        # Intra-file repeat: kept as real transaction (is_overlap=False)
        # Cross-file repeat: flagged as is_overlap=True
        if t_key_str in local_keys:
            is_overlap = False
        elif t_key_str in seen_keys:
            is_overlap = True
            overlap_detected += 1
        else:
            seen_keys.add(t_key_str)
            is_overlap = False
        local_keys.add(t_key_str)

        tx = Transaction(
            user_id=uid,
            account_id=target_account_id,
            statement_id=statement.id,
            source_row_index=idx,
            date=date_val,
            value_date=value_date_val,
            description=desc,
            merchant=merchant,
            amount=amount_dec,
            type=tx_type,
            classification=classification,
            category_id=cat_id,
            category=cat_label,
            ref_no=str(ref_no) if ref_no is not None else None,
            balance=balance_dec,
            transaction_key=t_key_str,
            transfer_group_id=None,
            import_metadata={
                "statement_row_index": idx,
                "filename": statement.filename,
                "is_overlap": is_overlap,
            },
        )
        db.add(tx)
        existing_row_indices.add(idx)
        rows_inserted += 1

    db.commit()
    return {
        "rows_inserted": rows_inserted,
        "rows_skipped_existing": rows_skipped_existing,
        "overlap_detected": overlap_detected,
    }

