"""Comprehensive test suite for Phase 8: Cash Flow Intelligence, Recurring Payments, and Financial Alerts."""

import datetime as dt
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from models import (
    User, FinancialAccount, Category, Transaction,
    Budget, BudgetAllocation, SavingsGoal,
    RecurringPayment, FinancialAlert
)
from main import app
from auth_utils import hash_password
from jwt_utils import create_access_token


@pytest.fixture
def db_session():
    """In-memory SQLite database session isolated for tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Pre-seed system categories
    system_cats = [
        ("Income", "income"),
        ("Investments", "investment"),
        ("Transfers", "transfer"),
        ("Food", "expense"),
        ("Utilities", "expense"),
        ("Bills", "expense"),
        ("Entertainment", "expense"),
        ("Shopping", "expense"),
        ("Rent", "expense"),
        ("Other", "expense"),
    ]
    for name, cat_type in system_cats:
        session.add(Category(name=name, category_type=cat_type, is_system=True, user_id=None))
    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
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
def user_a(db_session):
    u = User(
        email="user_a_p8@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="User Alpha",
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def user_b(db_session):
    u = User(
        email="user_b_p8@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="User Beta",
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def auth_headers_a(user_a):
    token = create_access_token(data={"sub": user_a.email, "user_id": user_a.id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_b(user_b):
    token = create_access_token(data={"sub": user_b.email, "user_id": user_b.id})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Cash Flow Intelligence Tests
# ---------------------------------------------------------------------------

def test_cash_flow_calculation_and_exclusions(client, auth_headers_a, user_a, db_session):
    """Verify cash-flow calculation, transfer exclusions, overlap exclusions, and metrics."""
    acc = FinancialAccount(
        user_id=user_a.id,
        name="HDFC Checking",
        account_type="savings",
        opening_balance=Decimal("10000.00"),
        is_reconciled=True,
    )
    db_session.add(acc)
    db_session.flush()

    # 1. Income: Salary ₹80,000 in March 2026
    t1 = Transaction(
        user_id=user_a.id,
        account_id=acc.id,
        date=dt.date(2026, 3, 1),
        description="Employer Salary",
        amount=Decimal("80000.00"),
        type="credit",
        classification="income",
        category="Income",
        transaction_key="tx_salary_mar",
    )
    # 2. Expense: Rent ₹25,000 in March 2026
    t2 = Transaction(
        user_id=user_a.id,
        account_id=acc.id,
        date=dt.date(2026, 3, 2),
        description="Apartment Rent",
        amount=Decimal("25000.00"),
        type="debit",
        classification="expense",
        category="Rent",
        transaction_key="tx_rent_mar",
    )
    # 3. Expense: Groceries ₹5,000 in March 2026
    t3 = Transaction(
        user_id=user_a.id,
        account_id=acc.id,
        date=dt.date(2026, 3, 15),
        description="Nature Basket",
        amount=Decimal("5000.00"),
        type="debit",
        classification="expense",
        category="Food",
        transaction_key="tx_food_mar",
    )
    # 4. EXCLUDED: Transfer to savings ₹10,000 (transfer classification)
    t4 = Transaction(
        user_id=user_a.id,
        account_id=acc.id,
        date=dt.date(2026, 3, 10),
        description="Self Transfer to PPF",
        amount=Decimal("10000.00"),
        type="debit",
        classification="transfer",
        category="Transfers",
        transaction_key="tx_transfer_mar",
    )
    # 5. EXCLUDED: Overlap duplicate expense ₹25,000
    t5 = Transaction(
        user_id=user_a.id,
        account_id=acc.id,
        date=dt.date(2026, 3, 2),
        description="Apartment Rent",
        amount=Decimal("25000.00"),
        type="debit",
        classification="expense",
        category="Rent",
        transaction_key="tx_rent_mar_dup",
        import_metadata={"is_overlap": True},
    )
    # 6. Prior month: February 2026 (Income: ₹80,000, Expense: ₹20,000)
    t6 = Transaction(
        user_id=user_a.id,
        account_id=acc.id,
        date=dt.date(2026, 2, 1),
        description="Employer Salary Feb",
        amount=Decimal("80000.00"),
        type="credit",
        classification="income",
        category="Income",
        transaction_key="tx_salary_feb",
    )
    t7 = Transaction(
        user_id=user_a.id,
        account_id=acc.id,
        date=dt.date(2026, 2, 5),
        description="Apartment Rent Feb",
        amount=Decimal("20000.00"),
        type="debit",
        classification="expense",
        category="Rent",
        transaction_key="tx_rent_feb",
    )

    db_session.add_all([t1, t2, t3, t4, t5, t6, t7])
    db_session.commit()

    # Query all cash flow
    res = client.get("/analytics/cash-flow", headers=auth_headers_a)
    assert res.status_code == 200, res.text
    data = res.json()

    # Total Income: 80,000 (Feb) + 80,000 (Mar) = 160,000
    assert data["total_income"] == "160000.00"
    # Total Expenses: 20,000 (Feb) + 30,000 (Mar) = 50,000 (Transfer and Overlap excluded!)
    assert data["total_expenses"] == "50000.00"
    # Net Cash Flow: 160,000 - 50,000 = 110,000
    assert data["net_cash_flow"] == "110000.00"
    # Savings Rate: 110,000 / 160,000 = 68.75%
    assert data["savings_rate_pct"] == 68.75

    # Check monthly history
    months = {m["month"]: m for m in data["monthly_history"]}
    assert "2026-02" in months
    assert "2026-03" in months
    assert months["2026-03"]["income"] == "80000.00"
    assert months["2026-03"]["expenses"] == "30000.00"
    assert months["2026-03"]["net_cash_flow"] == "50000.00"

    # MoM changes between Feb and Mar:
    # Income: 80k -> 80k (0.0%)
    assert data["mom_income_change_pct"] == 0.0
    # Expense: 20k -> 30k (+50.0%)
    assert data["mom_expense_change_pct"] == 50.0

    # Top expenses contains Rent (25000) and Rent Feb (20000)
    assert len(data["top_expenses"]) >= 2
    assert data["top_expenses"][0]["amount"] == "25000.00"

    # Verified account summary
    assert len(data["accounts"]) == 1
    acc_summary = data["accounts"][0]
    assert acc_summary["is_reconciled"] is True
    # Opening 10000 + Credits (80000*2) - Debits (25k + 5k + 10k transfer + 20k feb) = 10k + 160k - 60k = 110,000
    assert acc_summary["calculated_balance"] is not None


def test_cash_flow_date_and_account_filters(client, auth_headers_a, user_a, db_session):
    """Verify that start_date, end_date, and account_id query filters work correctly."""
    acc1 = FinancialAccount(user_id=user_a.id, name="Acc 1", is_reconciled=True)
    acc2 = FinancialAccount(user_id=user_a.id, name="Acc 2", is_reconciled=True)
    db_session.add_all([acc1, acc2])
    db_session.flush()

    t1 = Transaction(
        user_id=user_a.id, account_id=acc1.id, date=dt.date(2026, 1, 10),
        amount=Decimal("1000.00"), type="debit", classification="expense", category="Food",
        description="Jan Food", transaction_key="k1",
    )
    t2 = Transaction(
        user_id=user_a.id, account_id=acc2.id, date=dt.date(2026, 2, 10),
        amount=Decimal("2000.00"), type="debit", classification="expense", category="Shopping",
        description="Feb Shop", transaction_key="k2",
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    # Filter by date range (only Jan)
    res_date = client.get("/analytics/cash-flow?start_date=2026-01-01&end_date=2026-01-31", headers=auth_headers_a)
    assert res_date.status_code == 200
    assert res_date.json()["total_expenses"] == "1000.00"

    # Filter by account (only Acc 2)
    res_acc = client.get(f"/analytics/cash-flow?account_id={acc2.id}", headers=auth_headers_a)
    assert res_acc.status_code == 200
    assert res_acc.json()["total_expenses"] == "2000.00"


# ---------------------------------------------------------------------------
# 2. Recurring Payments & Subscriptions Tests
# ---------------------------------------------------------------------------

def test_recurring_crud_and_manual_entry(client, auth_headers_a):
    """Verify creating, listing, updating, pausing, resuming, and deleting recurring payments."""
    payload = {
        "name": "Netflix Premium",
        "category": "Entertainment",
        "average_amount": "649.00",
        "frequency": "monthly",
        "next_expected_date": "2026-04-15",
        "notes": "4K streaming plan",
    }

    # 1. Create recurring payment
    res = client.post("/recurring", json=payload, headers=auth_headers_a)
    assert res.status_code == 201
    rec = res.json()
    assert rec["name"] == "Netflix Premium"
    assert rec["status"] == "confirmed"
    assert rec["average_amount"] == "649.00"
    rec_id = rec["id"]

    # 2. List recurring payments
    res_list = client.get("/recurring", headers=auth_headers_a)
    assert res_list.status_code == 200
    summary = res_list.json()
    assert summary["active_count"] == 1
    assert summary["total_monthly_commitment"] == "649.00"
    assert len(summary["items"]) == 1

    # 3. Update recurring payment
    res_upd = client.put(f"/recurring/{rec_id}", json={"average_amount": "799.00"}, headers=auth_headers_a)
    assert res_upd.status_code == 200
    assert res_upd.json()["average_amount"] == "799.00"

    # 4. Pause recurring payment
    res_pause = client.post(f"/recurring/{rec_id}/pause", headers=auth_headers_a)
    assert res_pause.status_code == 200
    assert res_pause.json()["status"] == "inactive"

    # Active count drops to 0
    res_list2 = client.get("/recurring", headers=auth_headers_a)
    assert res_list2.json()["active_count"] == 0

    # 5. Resume recurring payment
    res_resume = client.post(f"/recurring/{rec_id}/resume", headers=auth_headers_a)
    assert res_resume.status_code == 200
    assert res_resume.json()["status"] == "confirmed"

    # 6. Delete
    res_del = client.delete(f"/recurring/{rec_id}", headers=auth_headers_a)
    assert res_del.status_code == 204
    assert client.get(f"/recurring/{rec_id}", headers=auth_headers_a).status_code == 404


def test_recurring_auto_detection_scan(client, auth_headers_a, user_a, db_session):
    """Verify scanning normalized transactions to auto-detect recurring subscriptions."""
    # Seed transactions for SPOTIFY across 3 distinct months
    t1 = Transaction(
        user_id=user_a.id, date=dt.date(2026, 1, 15), description="SPOTIFY INDIA",
        amount=Decimal("119.00"), type="debit", classification="expense", category="Entertainment",
        transaction_key="tx_spot_1",
    )
    t2 = Transaction(
        user_id=user_a.id, date=dt.date(2026, 2, 15), description="SPOTIFY INDIA",
        amount=Decimal("119.00"), type="debit", classification="expense", category="Entertainment",
        transaction_key="tx_spot_2",
    )
    t3 = Transaction(
        user_id=user_a.id, date=dt.date(2026, 3, 15), description="SPOTIFY INDIA",
        amount=Decimal("119.00"), type="debit", classification="expense", category="Entertainment",
        transaction_key="tx_spot_3",
    )
    # One-off transaction (only 1 month) -> should NOT be detected
    t4 = Transaction(
        user_id=user_a.id, date=dt.date(2026, 3, 20), description="CROMA ELECTRONICS",
        amount=Decimal("4500.00"), type="debit", classification="expense", category="Shopping",
        transaction_key="tx_croma",
    )

    db_session.add_all([t1, t2, t3, t4])
    db_session.commit()

    # Trigger scan
    res = client.post("/recurring/scan", headers=auth_headers_a)
    assert res.status_code == 200
    scan_data = res.json()
    assert scan_data["new_detected"] == 1

    # Verify detected subscription
    res_list = client.get("/recurring", headers=auth_headers_a)
    assert res_list.status_code == 200
    data = res_list.json()
    assert data["detected_count"] == 1
    detected_item = data["items"][0]
    assert "SPOTIFY" in detected_item["name"]
    assert detected_item["status"] == "detected"
    assert detected_item["average_amount"] == "119.00"
    assert detected_item["occurrence_count"] == 3

    # Confirm subscription
    res_conf = client.post(f"/recurring/{detected_item['id']}/confirm", headers=auth_headers_a)
    assert res_conf.status_code == 200
    assert res_conf.json()["status"] == "confirmed"


# ---------------------------------------------------------------------------
# 3. Financial Alerts & Preferences Tests
# ---------------------------------------------------------------------------

def test_alert_generation_and_deduplication(client, auth_headers_a, user_a, db_session):
    """Verify deterministic alert generation, deduplication, read/dismiss actions, and preferences."""
    today = dt.date.today()

    # 1. Create a budget for this month that is exceeded
    budget = Budget(
        user_id=user_a.id,
        month=today.month,
        year=today.year,
        total_budget_limit=Decimal("5000.00"),
        warning_threshold=Decimal("80.00"),
    )
    db_session.add(budget)
    db_session.flush()

    # Add transaction exceeding budget: ₹6,500
    tx = Transaction(
        user_id=user_a.id,
        date=today,
        description="Big Shopping Spree",
        amount=Decimal("6500.00"),
        type="debit",
        classification="expense",
        category="Shopping",
        transaction_key="tx_big_spend",
    )
    # Add recurring bill due tomorrow
    rec = RecurringPayment(
        user_id=user_a.id,
        name="Internet Bill",
        average_amount=Decimal("999.00"),
        frequency="monthly",
        status="confirmed",
        next_expected_date=today + dt.timedelta(days=1),
    )
    db_session.add_all([tx, rec])
    db_session.commit()

    # Trigger alert evaluation
    res_eval = client.post("/alerts/evaluate", headers=auth_headers_a)
    assert res_eval.status_code == 200
    new_alerts = res_eval.json()["new_alerts_created"]
    assert new_alerts >= 2  # Budget exceeded + upcoming recurring bill + large expense

    # List alerts
    res_list = client.get("/alerts", headers=auth_headers_a)
    assert res_list.status_code == 200
    alerts = res_list.json()
    assert alerts["unread_count"] >= 2
    assert len(alerts["items"]) >= 2
    first_alert = alerts["items"][0]

    # Deduplication test: re-evaluating must NOT create duplicate alerts!
    res_eval2 = client.post("/alerts/evaluate", headers=auth_headers_a)
    assert res_eval2.json()["new_alerts_created"] == 0

    res_list2 = client.get("/alerts", headers=auth_headers_a)
    assert len(res_list2.json()["items"]) == len(alerts["items"])

    # Mark first alert as read
    res_read = client.post(f"/alerts/{first_alert['id']}/read", headers=auth_headers_a)
    assert res_read.status_code == 200
    assert res_read.json()["is_read"] is True

    # Dismiss alert
    res_dismiss = client.post(f"/alerts/{first_alert['id']}/dismiss", headers=auth_headers_a)
    assert res_dismiss.status_code == 200
    assert res_dismiss.json()["is_dismissed"] is True

    # Default list excludes dismissed alerts
    res_active = client.get("/alerts", headers=auth_headers_a)
    active_ids = [a["id"] for a in res_active.json()["items"]]
    assert first_alert["id"] not in active_ids

    # Update preferences: disable budget alerts
    pref_upd = client.put(
        "/alerts/preferences",
        json={"budget_alerts": False, "large_expense_threshold": "10000.00"},
        headers=auth_headers_a,
    )
    assert pref_upd.status_code == 200
    assert pref_upd.json()["budget_alerts"] is False
    assert pref_upd.json()["large_expense_threshold"] == "10000.00"


# ---------------------------------------------------------------------------
# 4. Multi-Tenant Authorization Tests
# ---------------------------------------------------------------------------

def test_multi_tenant_isolation_phase8(client, auth_headers_a, auth_headers_b, user_a, user_b, db_session):
    """Verify that User A and User B cannot access or modify each other's recurring payments or alerts."""
    rec_a = RecurringPayment(
        user_id=user_a.id,
        name="User A Gym",
        average_amount=Decimal("2000.00"),
        status="confirmed",
    )
    alert_a = FinancialAlert(
        user_id=user_a.id,
        alert_type="budget_warning",
        severity="warning",
        title="Alert for User A",
        message="A's private message",
        dedup_key="key_a_unique",
    )
    db_session.add_all([rec_a, alert_a])
    db_session.commit()

    # User B cannot access User A's recurring payment
    assert client.get(f"/recurring/{rec_a.id}", headers=auth_headers_b).status_code == 404
    assert client.put(f"/recurring/{rec_a.id}", json={"name": "Hacked"}, headers=auth_headers_b).status_code == 404
    assert client.delete(f"/recurring/{rec_a.id}", headers=auth_headers_b).status_code == 404

    # User B cannot read or dismiss User A's alert
    assert client.post(f"/alerts/{alert_a.id}/read", headers=auth_headers_b).status_code == 404
    assert client.post(f"/alerts/{alert_a.id}/dismiss", headers=auth_headers_b).status_code == 404

