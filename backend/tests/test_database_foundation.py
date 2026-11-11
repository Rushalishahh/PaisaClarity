"""Tests for Phase 5: Database Foundation (FinancialAccount, Category, Transaction, & Idempotent Backfill)."""

import pytest
from decimal import Decimal
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import User, Statement, Investment, FinancialAccount, Category, Transaction
from backfill import backfill_statement_transactions, to_decimal, resolve_classification


@pytest.fixture
def test_db():
    """In-memory SQLite session with all tables created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Seed system categories (as Alembic migration does)
    system_cats = [
        ("Income", "income"),
        ("Investments", "investment"),
        ("Transfers", "transfer"),
        ("Rent", "expense"),
        ("EMI & Loans", "expense"),
        ("Insurance", "expense"),
        ("Cash Withdrawal", "expense"),
        ("Food", "expense"),
        ("Groceries", "expense"),
        ("Shopping", "expense"),
        ("Transport", "expense"),
        ("Travel", "expense"),
        ("Bills", "expense"),
        ("Entertainment", "expense"),
        ("Health", "expense"),
        ("Education", "expense"),
        ("Other", "expense"),
    ]
    for name, cat_type in system_cats:
        session.add(Category(name=name, category_type=cat_type, is_system=True, user_id=None))
    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Precision & Utility Tests
# ---------------------------------------------------------------------------

def test_decimal_conversion_and_quantization():
    """Test monetary quantization avoids binary float drift."""
    assert to_decimal("250.0") == Decimal("250.00")
    assert to_decimal(250.0) == Decimal("250.00")
    assert to_decimal("19.994") == Decimal("19.99")
    assert to_decimal("19.995") == Decimal("20.00")
    assert to_decimal(None) == Decimal("0.00")
    assert to_decimal("") == Decimal("0.00")


def test_resolve_classification():
    """Test financial classification mapping."""
    assert resolve_classification("credit", "Income") == "income"
    assert resolve_classification("credit", "Salary") == "income"
    assert resolve_classification("debit", "Transfers") == "transfer"
    assert resolve_classification("credit", "Transfers") == "transfer"
    assert resolve_classification("debit", "Investments") == "investment"
    assert resolve_classification("debit", "Food") == "expense"
    assert resolve_classification("debit", "Other") == "expense"


# ---------------------------------------------------------------------------
# Backfill & Idempotency Tests
# ---------------------------------------------------------------------------

def test_backfill_populated_database(test_db):
    """Test backfill extracts transactions into normalized table with proper relationships."""
    user = User(email="backfill_user@example.com", hashed_password="hashed_pw_test123")
    test_db.add(user)
    test_db.commit()

    # Statement with varied transactions including legitimate identical ones
    statement_txs = [
        {
            "date": "2026-06-01",
            "value_date": "2026-06-01",
            "description": "UPI-SWIGGY-111",
            "amount": 250.0,
            "type": "debit",
            "balance": 10000.0,
            "category": "Food",
            "ref_no": "REF001",
        },
        # Legitimate duplicate in same file (second coffee/meal at Swiggy on same day)
        {
            "date": "2026-06-01",
            "value_date": "2026-06-01",
            "description": "UPI-SWIGGY-111",
            "amount": 250.0,
            "type": "debit",
            "balance": 9750.0,
            "category": "Food",
            "ref_no": "REF002",
        },
        {
            "date": "2026-06-05",
            "value_date": None,
            "description": "SALARY CREDIT ACME",
            "amount": 75000.0,
            "type": "credit",
            "balance": 84750.0,
            "category": "Income",
            "ref_no": "SAL12345",
        },
        {
            "date": "2026-06-10",
            "value_date": None,
            "description": "TRANSFER TO SAVINGS",
            "amount": 10000.0,
            "type": "debit",
            "balance": 74750.0,
            "category": "Transfers",
            "ref_no": "TRF999",
        },
    ]

    stmt = Statement(
        user_id=user.id,
        filename="hdfc_statement_june.pdf",
        result={"transactions": statement_txs, "category_totals": {"Food": 500.0}},
    )
    test_db.add(stmt)
    test_db.commit()

    # Run backfill
    res = backfill_statement_transactions(test_db, user_id=user.id)
    assert res["statements_processed"] == 1
    assert res["rows_inserted"] == 4
    assert res["rows_skipped_existing"] == 0

    # Verify rows in database
    txs = test_db.query(Transaction).filter(Transaction.user_id == user.id).order_by(Transaction.source_row_index.asc()).all()
    assert len(txs) == 4

    # Verify both legitimate identical transactions exist with distinct source_row_index
    assert txs[0].source_row_index == 0
    assert txs[0].amount == Decimal("250.00")
    assert txs[0].classification == "expense"
    assert txs[0].category == "Food"

    assert txs[1].source_row_index == 1
    assert txs[1].amount == Decimal("250.00")
    assert txs[1].ref_no == "REF002"

    # Verify income transaction
    assert txs[2].classification == "income"
    assert txs[2].amount == Decimal("75000.00")

    # Verify transfer transaction
    assert txs[3].classification == "transfer"
    assert txs[3].amount == Decimal("10000.00")

    # Verify placeholder account was created with is_reconciled=False
    acct = test_db.query(FinancialAccount).filter(FinancialAccount.user_id == user.id).first()
    assert acct is not None
    assert acct.name == "Imported Statements"
    assert acct.account_type == "imported"
    assert acct.is_reconciled is False  # Excluded from verified net worth

    # All transactions point to this account
    for tx in txs:
        assert tx.account_id == acct.id
        assert tx.statement_id == stmt.id


def test_backfill_idempotency(test_db):
    """Running backfill a second time must insert 0 rows and skip all existing."""
    user = User(email="idempotent@example.com", hashed_password="pw")
    test_db.add(user)
    test_db.commit()

    stmt = Statement(
        user_id=user.id,
        filename="july.pdf",
        result={
            "transactions": [
                {"date": "2026-07-01", "description": "UBER", "amount": 350.0, "type": "debit", "category": "Transport"},
                {"date": "2026-07-02", "description": "ZEPTO", "amount": 420.0, "type": "debit", "category": "Groceries"},
            ]
        },
    )
    test_db.add(stmt)
    test_db.commit()

    # Pass 1
    res1 = backfill_statement_transactions(test_db)
    assert res1["rows_inserted"] == 2
    assert res1["rows_skipped_existing"] == 0
    assert test_db.query(Transaction).filter(Transaction.user_id == user.id).count() == 2

    # Pass 2: MUST insert 0 rows
    res2 = backfill_statement_transactions(test_db)
    assert res2["rows_inserted"] == 0
    assert res2["rows_skipped_existing"] == 2
    assert test_db.query(Transaction).filter(Transaction.user_id == user.id).count() == 2


def test_backfill_handles_empty_or_missing_transactions(test_db):
    """Statements without transactions (e.g., uploaded before multi-statement support) are safely skipped."""
    user = User(email="empty_test@example.com", hashed_password="pw")
    test_db.add(user)
    test_db.commit()

    # Old statement without "transactions" key
    s1 = Statement(user_id=user.id, filename="old.pdf", result={"category_totals": {}})
    # Statement with empty transactions list
    s2 = Statement(user_id=user.id, filename="empty.pdf", result={"transactions": []})
    test_db.add_all([s1, s2])
    test_db.commit()

    res = backfill_statement_transactions(test_db, user_id=user.id)
    assert res["statements_processed"] == 0
    assert res["rows_inserted"] == 0
    assert test_db.query(Transaction).filter(Transaction.user_id == user.id).count() == 0


# ---------------------------------------------------------------------------
# Category & Transfer Integrity Tests
# ---------------------------------------------------------------------------

def test_category_synchronization_and_deletion_safety(test_db):
    """Deleting a category sets category_id to NULL while preserving the denormalized category string."""
    user = User(email="cat_user@example.com", hashed_password="pw")
    test_db.add(user)
    test_db.commit()

    # Custom category
    custom_cat = Category(user_id=user.id, name="Custom Tech Books", category_type="expense", is_system=False)
    test_db.add(custom_cat)
    test_db.commit()

    tx = Transaction(
        user_id=user.id,
        date=datetime.date(2026, 8, 1),
        description="O'REILLY BOOKS",
        amount=Decimal("1200.00"),
        type="debit",
        classification="expense",
        category_id=custom_cat.id,
        category=custom_cat.name,
        transaction_key="2026-08-01_OREILLY_1200.00",
    )
    test_db.add(tx)
    test_db.commit()

    assert tx.category_id == custom_cat.id
    assert tx.category == "Custom Tech Books"

    # Delete custom category: foreign key should set null, but denormalized string remains!
    test_db.delete(custom_cat)
    test_db.commit()

    test_db.refresh(tx)
    assert tx.category_id is None
    assert tx.category == "Custom Tech Books"  # Preserved historical record!


def test_transfer_pairing_with_group_id(test_db):
    """Test transfer debit and credit legs paired with transfer_group_id."""
    user = User(email="transfer_test@example.com", hashed_password="pw")
    test_db.add(user)
    test_db.commit()

    acct_a = FinancialAccount(user_id=user.id, name="Checking A", account_type="savings", opening_balance=Decimal("50000.00"))
    acct_b = FinancialAccount(user_id=user.id, name="Savings B", account_type="savings", opening_balance=Decimal("10000.00"))
    test_db.add_all([acct_a, acct_b])
    test_db.commit()

    transfer_uuid = "e3b0c442-98fc-1c14-9afb-4c8996fb9242"
    transfer_amount = Decimal("5000.00")

    # Debit leg from Account A
    debit_leg = Transaction(
        user_id=user.id,
        account_id=acct_a.id,
        date=datetime.date(2026, 9, 1),
        description="Transfer to Savings B",
        amount=transfer_amount,
        type="debit",
        classification="transfer",
        category="Transfers",
        transaction_key="2026-09-01_TRF_A_5000.00",
        transfer_group_id=transfer_uuid,
    )
    # Credit leg to Account B
    credit_leg = Transaction(
        user_id=user.id,
        account_id=acct_b.id,
        date=datetime.date(2026, 9, 1),
        description="Transfer from Checking A",
        amount=transfer_amount,
        type="credit",
        classification="transfer",
        category="Transfers",
        transaction_key="2026-09-01_TRF_B_5000.00",
        transfer_group_id=transfer_uuid,
    )
    test_db.add_all([debit_leg, credit_leg])
    test_db.commit()

    # Query transfer pair
    paired = test_db.query(Transaction).filter(Transaction.transfer_group_id == transfer_uuid).all()
    assert len(paired) == 2
    types = {p.type for p in paired}
    assert types == {"debit", "credit"}
    for leg in paired:
        assert leg.classification == "transfer"


# ---------------------------------------------------------------------------
# Multi-Tenant Isolation Tests
# ---------------------------------------------------------------------------

def test_multi_tenant_isolation(test_db):
    """User A cannot access User B's accounts or transactions."""
    user_a = User(email="user_a@example.com", hashed_password="pw")
    user_b = User(email="user_b@example.com", hashed_password="pw")
    test_db.add_all([user_a, user_b])
    test_db.commit()

    acct_a = FinancialAccount(user_id=user_a.id, name="User A Account", account_type="savings")
    acct_b = FinancialAccount(user_id=user_b.id, name="User B Account", account_type="savings")
    test_db.add_all([acct_a, acct_b])
    test_db.commit()

    tx_a = Transaction(
        user_id=user_a.id, account_id=acct_a.id, date=datetime.date(2026, 10, 1),
        description="A's Spend", amount=Decimal("100.00"), type="debit", transaction_key="key_a"
    )
    tx_b = Transaction(
        user_id=user_b.id, account_id=acct_b.id, date=datetime.date(2026, 10, 1),
        description="B's Spend", amount=Decimal("200.00"), type="debit", transaction_key="key_b"
    )
    test_db.add_all([tx_a, tx_b])
    test_db.commit()

    # User A query
    user_a_txs = test_db.query(Transaction).filter(Transaction.user_id == user_a.id).all()
    assert len(user_a_txs) == 1
    assert user_a_txs[0].description == "A's Spend"

    # User B query
    user_b_txs = test_db.query(Transaction).filter(Transaction.user_id == user_b.id).all()
    assert len(user_b_txs) == 1
    assert user_b_txs[0].description == "B's Spend"
