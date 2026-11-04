"""
Cross-statement transaction access (multi-statement support).

Historically the app analyzed one uploaded file at a time; Statement.result
stored only the derived aggregates. To make combined analytics possible
without a new Transaction table, uploads now ALSO store their canonical
transactions inside Statement.result["transactions"], and this module
merges + de-duplicates them across all of a user's statements.

Privacy note: the stored transactions are the owner's own data, in their
own row, readable only through ownership-checked endpoints. They are
never logged, never shared across users, and PDF passwords are never
stored anywhere.
"""

import pandas as pd
from sqlalchemy.orm import Session

from categorizer import normalize_description
from models import Statement

# The canonical transaction contract shared with ingest/normalizer.py.
CANONICAL_COLUMNS = ["date", "value_date", "description", "ref_no", "amount", "type", "balance"]

VALID_SCOPES = ("all", "latest")


def transaction_key(date_value, description, amount):
    """
    Cross-statement duplicate identity: (date, normalized description, amount).

    The description is normalized with the categorizer's normalizer, so
    'UPI-SWIGGY-910620' and 'UPI-SWIGGY-575435' both become 'SWIGGY'.
    Combined with the same date and amount, that identifies the same
    real-world transaction seen in two overlapping files.

    Balance is deliberately NOT part of the cross-file key: overlapping
    statements exported from different windows carry different RUNNING
    balances (their opening balances differ), so requiring balance equality
    would fail to dedupe exactly the rows we must not double-count
    (e.g. the same month of rent appearing in two files). Within a single
    file duplicates don't exist by construction, so balance isn't needed
    as a discriminator either.
    """
    return (
        pd.Timestamp(date_value).date(),
        normalize_description(description),
        round(float(amount), 2),
    )


def transactions_to_rows(df):
    """Serialize the canonical transactions DataFrame into JSON-safe dicts."""
    rows = []
    for r in df.itertuples(index=False):
        value_date = getattr(r, "value_date", None)
        ref_no = getattr(r, "ref_no", None)
        rows.append({
            "date": pd.Timestamp(r.date).date().isoformat(),
            "value_date": (
                pd.Timestamp(value_date).date().isoformat()
                if value_date is not None and pd.notna(value_date) else None
            ),
            "description": str(r.description),
            "ref_no": None if ref_no is None or pd.isna(ref_no) else str(ref_no),
            "amount": round(float(r.amount), 2),
            "type": str(r.type),
            "balance": (
                round(float(r.balance), 2)
                if r.balance is not None and pd.notna(r.balance) else None
            ),
        })
    return rows


def dataframe_from_rows(rows):
    """Rebuild the canonical transactions DataFrame from stored dicts."""
    df = pd.DataFrame(rows if rows else [])
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[CANONICAL_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["value_date"] = pd.to_datetime(df["value_date"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["balance"] = pd.to_numeric(df["balance"], errors="coerce")
    df["type"] = df["type"].astype(str)
    df["description"] = df["description"].astype(str)
    return df.sort_values("date", kind="stable").reset_index(drop=True)


def _merge_statement_rows(statements):
    """
    Merge transactions across statements oldest-first, dropping rows whose
    (date, normalized description, amount) was already seen in an EARLIER
    statement. Repeats WITHIN one file are kept (two same-price coffees on
    the same day are real), but a file repeats a transaction that an earlier
    file already contributed, it is dropped as the overlap duplicate.
    Returns (merged_rows, duplicates_dropped).
    """
    seen = set()
    merged = []
    duplicates = 0
    for statement in statements:
        rows = (statement.result or {}).get("transactions") or []
        local = set()
        for r in rows:
            try:
                key = transaction_key(r.get("date"), r.get("description"), r.get("amount"))
            except (TypeError, ValueError):
                # Malformed stored row - keep it rather than silently losing data.
                merged.append(r)
                continue
            if key in local:
                # Repeat inside the same file: a real, separate transaction.
                merged.append(r)
                continue
            local.add(key)
            if key in seen:
                duplicates += 1  # same transaction already contributed by an earlier file
                continue
            seen.add(key)
            merged.append(r)
    return merged, duplicates


def get_user_transactions(db: Session, user_id: int, scope: str = "all", statement_id=None):
    """
    Transactions for one user, merged across their statements.

    scope="all":    every statement, de-duplicated on
                    (date, normalized description, amount) - overlapping
                    uploads are NOT double-counted.
    scope="latest": only the newest statement's transactions.

    statement_id:   restrict to one specific statement (ownership-checked;
                    raises LookupError when missing or not owned).

    Raises ValueError for an unknown scope and LookupError for a missing /
    foreign statement. Returns the canonical DataFrame (uncategorized -
    callers run add_categories themselves). Statements uploaded before
    transactions were stored in result have nothing to contribute and are
    skipped; if nothing contributes, an empty canonical DataFrame comes back.
    """
    if scope not in VALID_SCOPES:
        raise ValueError(f"scope must be one of {VALID_SCOPES}")

    if statement_id is not None:
        statement = (
            db.query(Statement)
            .filter(Statement.id == statement_id, Statement.user_id == user_id)
            .first()
        )
        if statement is None:
            raise LookupError("Statement not found")
        rows = (statement.result or {}).get("transactions") or []
        return dataframe_from_rows(rows)

    if scope == "latest":
        statement = (
            db.query(Statement)
            .filter(Statement.user_id == user_id)
            .order_by(Statement.uploaded_at.desc())
            .first()
        )
        rows = ((statement.result or {}).get("transactions") or []) if statement else []
        return dataframe_from_rows(rows)

    # scope == "all": oldest first so the earliest file "owns" each
    # transaction and later overlapping files drop their duplicates.
    statements = (
        db.query(Statement)
        .filter(Statement.user_id == user_id)
        .order_by(Statement.uploaded_at.asc())
        .all()
    )
    merged, _duplicates = _merge_statement_rows(statements)
    return dataframe_from_rows(merged)
