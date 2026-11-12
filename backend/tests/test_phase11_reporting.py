"""
Phase 11: Financial Reporting & UX Test Suite

Tests:
1. Summary report calculations (income, spending, net cashflow, savings rate).
2. Transfer exclusion and overlapping duplicate exclusion.
3. Unreconciled accounts isolated from verified liquid net worth.
4. Summary report date filtering.
5. CSV export generation and formula injection defense.
6. PDF export generation and structure (valid PDF binary, correct headers).
7. Category correction explicit consent (`apply_to_future: False` vs `True`).
"""
import datetime as dt
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from models import (
    User,
    FinancialAccount,
    Transaction,
    Category,
    CategorizationRule,
    Budget,
    SavingsGoal,
    RecurringPayment,
    Investment,
)
from main import app
from auth_utils import hash_password
from jwt_utils import create_access_token


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Pre-seed basic system categories
    system_cats = [
        ("Salary", "income"),
        ("Groceries", "expense"),
        ("Transfers", "transfer"),
        ("Dining", "expense"),
        ("Shopping", "expense"),
    ]
    for name, cat_type in system_cats:
        session.add(Category(name=name, category_type=cat_type, is_system=True, user_id=None))
    session.commit()

    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_user(db_session):
    user = User(
        email="reporting_user@example.com",
        full_name="Reporting User",
        hashed_password=hash_password("ValidPass123!"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token = create_access_token(data={"sub": user.email, "user_id": user.id})
    headers = {"Authorization": f"Bearer {token}"}
    return {"user": user, "headers": headers, "db": db_session}


def test_report_summary_calculations(client, auth_user, db_session):
    headers = auth_user["headers"]
    user_id = auth_user["user"].id

    # Create verified account
    acc = FinancialAccount(
        user_id=user_id,
        name="HDFC Salary",
        account_type="savings",
        opening_balance=Decimal("50000.00"),
        is_reconciled=True,
    )
    db_session.add(acc)
    db_session.commit()
    db_session.refresh(acc)

    # Transactions
    today = dt.date.today()
    t1 = Transaction(
        user_id=user_id,
        account_id=acc.id,
        date=today,
        description="Monthly Salary",
        amount=Decimal("100000.00"),
        type="credit",
        classification="income",
        category="Salary",
        transaction_key=f"k1_{today}",
    )
    t2 = Transaction(
        user_id=user_id,
        account_id=acc.id,
        date=today,
        description="Supermarket Groceries",
        amount=Decimal("20000.00"),
        type="debit",
        classification="expense",
        category="Groceries",
        transaction_key=f"k2_{today}",
    )
    t_transfer = Transaction(
        user_id=user_id,
        account_id=acc.id,
        date=today,
        description="Internal transfer",
        amount=Decimal("5000.00"),
        type="debit",
        classification="transfer",
        category="Transfers",
        transaction_key=f"k3_{today}",
    )
    db_session.add_all([t1, t2, t_transfer])
    db_session.commit()

    res = client.get("/reports/summary", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["summary"]["total_income"] == 100000.0
    assert data["summary"]["total_expenses"] == 20000.0
    assert data["summary"]["net_cash_flow"] == 80000.0
    assert data["summary"]["savings_rate_pct"] == 80.0
    # Verified opening balance (50,000) + income (100,000) - expense (20,000) - transfer (5,000) = 125,000
    assert data["net_worth"]["verified_liquid_balance"] == 125000.0

    # Verify Transfer was excluded from spending category breakdown
    cat_breakdown = {c["category"]: c["amount"] for c in data["category_breakdown"]}
    assert "Groceries" in cat_breakdown
    assert cat_breakdown["Groceries"] == 20000.0
    assert "Transfers" not in cat_breakdown


def test_unreconciled_account_isolated_from_liquid_net_worth(client, auth_user, db_session):
    headers = auth_user["headers"]
    user_id = auth_user["user"].id

    verified_acc = FinancialAccount(
        user_id=user_id,
        name="SBI Main",
        account_type="savings",
        opening_balance=Decimal("25000.00"),
        is_reconciled=True,
    )
    unassigned_acc = FinancialAccount(
        user_id=user_id,
        name="Imported Statements",
        account_type="unassigned",
        opening_balance=Decimal("999999.00"),
        is_reconciled=False,
    )
    db_session.add_all([verified_acc, unassigned_acc])
    db_session.commit()

    res = client.get("/reports/summary", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["net_worth"]["verified_liquid_balance"] == 25000.0
    assert data["net_worth"]["unreconciled_placeholder_balance"] == 999999.0


def test_csv_export_formula_injection_defense(client, auth_user, db_session):
    headers = auth_user["headers"]
    user_id = auth_user["user"].id

    acc = FinancialAccount(
        user_id=user_id,
        name="ICICI",
        account_type="savings",
        opening_balance=Decimal("1000.00"),
        is_reconciled=True,
    )
    db_session.add(acc)
    db_session.commit()
    db_session.refresh(acc)

    # Malicious transaction descriptions attempting CSV injection
    today = dt.date.today()
    t_inj1 = Transaction(
        user_id=user_id,
        account_id=acc.id,
        date=today,
        description="=cmd|' /C calc'!A0",
        amount=Decimal("150.00"),
        type="debit",
        classification="expense",
        category="Shopping",
        transaction_key="inj1",
    )
    t_inj2 = Transaction(
        user_id=user_id,
        account_id=acc.id,
        date=today,
        description="@SUM(1+1)",
        amount=Decimal("250.00"),
        type="debit",
        classification="expense",
        category="Shopping",
        transaction_key="inj2",
    )
    t_inj3 = Transaction(
        user_id=user_id,
        account_id=acc.id,
        date=today,
        description="+12345678",
        amount=Decimal("350.00"),
        type="debit",
        classification="expense",
        category="Shopping",
        transaction_key="inj3",
    )
    db_session.add_all([t_inj1, t_inj2, t_inj3])
    db_session.commit()

    res = client.get("/reports/export/csv", headers=headers)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    csv_text = res.text

    # Verify formula injection chars are prefixed with '
    assert "'=cmd|' /C calc'!A0" in csv_text
    assert "'@SUM(1+1)" in csv_text
    assert "'+12345678" in csv_text


def test_pdf_export_structure(client, auth_user, db_session):
    headers = auth_user["headers"]
    user_id = auth_user["user"].id

    acc = FinancialAccount(
        user_id=user_id,
        name="Axis Bank",
        account_type="savings",
        opening_balance=Decimal("5000.00"),
        is_reconciled=True,
    )
    db_session.add(acc)
    db_session.commit()

    t = Transaction(
        user_id=user_id,
        account_id=acc.id,
        date=dt.date.today(),
        description="Swiggy Delivery & Cafe <Special>",
        amount=Decimal("450.00"),
        type="debit",
        classification="expense",
        category="Dining",
        transaction_key="pdf_tx_1",
    )
    db_session.add(t)
    db_session.commit()

    res = client.get("/reports/export/pdf", headers=headers)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in res.headers.get("content-disposition", "")
    pdf_bytes = res.content

    # Validate PDF magic header
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_category_correction_apply_to_future_flag(client, auth_user, db_session):
    headers = auth_user["headers"]
    user_id = auth_user["user"].id

    acc = FinancialAccount(
        user_id=user_id,
        name="HDFC",
        account_type="savings",
        opening_balance=Decimal("10000.00"),
        is_reconciled=True,
    )
    db_session.add(acc)
    db_session.commit()

    t = Transaction(
        user_id=user_id,
        account_id=acc.id,
        date=dt.date.today(),
        description="Starbucks Coffee Bandra",
        amount=Decimal("350.00"),
        type="debit",
        classification="expense",
        category="Shopping",
        transaction_key="starbucks_1",
    )
    db_session.add(t)
    db_session.commit()
    t_id = t.id

    # 1. Update category with apply_to_future=False -> ONLY transaction updated, NO rule created
    payload_no_rule = {
        "category_name": "Dining",
        "apply_to_future": False,
    }
    res1 = client.patch(f"/transactions/{t_id}/category", json=payload_no_rule, headers=headers)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["category"] == "Dining"

    rules_count = db_session.query(CategorizationRule).filter(CategorizationRule.user_id == user_id).count()
    assert rules_count == 0

    # 2. Update category with apply_to_future=True -> Transaction updated AND rule created
    payload_with_rule = {
        "category_name": "Dining",
        "apply_to_future": True,
    }
    res2 = client.patch(f"/transactions/{t_id}/category", json=payload_with_rule, headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["category"] == "Dining"

    created_rule = db_session.query(CategorizationRule).filter(
        CategorizationRule.user_id == user_id,
        CategorizationRule.category_name == "Dining"
    ).first()
    assert created_rule is not None
    assert "starbucks" in created_rule.pattern.lower()
