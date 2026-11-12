"""Comprehensive test suite for Phase 7: Budget Management and Savings Goals."""

import datetime as dt
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from models import User, Category, Transaction, Budget, BudgetAllocation, SavingsGoal, SavingsContribution
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
        ("Shopping", "expense"),
        ("Rent", "expense"),
        ("Travel", "expense"),
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
        email="usera@example.com",
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
        email="userb@example.com",
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
# Budget Management Tests
# ---------------------------------------------------------------------------

def test_budget_crud_and_uniqueness(client, auth_headers_a, user_a):
    """Verify creating, reading, updating, and deleting monthly budgets."""
    payload = {
        "month": 4,
        "year": 2026,
        "total_budget_limit": "50000.00",
        "warning_threshold": "80.00",
        "allocations": [
            {"category_name": "Food", "allocated_amount": "15000.00", "notes": "Groceries and dining"},
            {"category_name": "Utilities", "allocated_amount": "10000.00"},
        ],
    }

    # 1. Create budget
    res = client.post("/budgets", json=payload, headers=auth_headers_a)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["month"] == 4
    assert data["year"] == 2026
    assert data["total_budget_limit"] == "50000.00"
    assert data["total_allocated"] == "25000.00"
    assert len(data["allocations"]) == 2
    budget_id = data["id"]

    # 2. Duplicate budget for same month/year is rejected with 409
    res_dup = client.post("/budgets", json=payload, headers=auth_headers_a)
    assert res_dup.status_code == 409

    # 3. List budgets
    res_list = client.get("/budgets", headers=auth_headers_a)
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1
    assert res_list.json()[0]["id"] == budget_id

    # 4. Get budget by id
    res_get = client.get(f"/budgets/{budget_id}", headers=auth_headers_a)
    assert res_get.status_code == 200
    assert res_get.json()["id"] == budget_id

    # 5. Update budget
    update_payload = {
        "total_budget_limit": "60000.00",
        "warning_threshold": "85.00",
        "allocations": [
            {"category_name": "Food", "allocated_amount": "20000.00"},
            {"category_name": "Utilities", "allocated_amount": "12000.00"},
            {"category_name": "Shopping", "allocated_amount": "8000.00"},
        ],
    }
    res_upd = client.put(f"/budgets/{budget_id}", json=update_payload, headers=auth_headers_a)
    assert res_upd.status_code == 200
    upd_data = res_upd.json()
    assert upd_data["total_budget_limit"] == "60000.00"
    assert upd_data["total_allocated"] == "40000.00"
    assert len(upd_data["allocations"]) == 3

    # 6. Delete budget
    res_del = client.delete(f"/budgets/{budget_id}", headers=auth_headers_a)
    assert res_del.status_code == 204

    # Verify deleted
    res_gone = client.get(f"/budgets/{budget_id}", headers=auth_headers_a)
    assert res_gone.status_code == 404


def test_budget_spending_and_warning_detection(client, auth_headers_a, user_a, db_session):
    """Verify actual spending aggregation, warning threshold, and over-budget detection."""
    # Create budget for March 2026
    budget = Budget(
        user_id=user_a.id,
        month=3,
        year=2026,
        total_budget_limit=Decimal("30000.00"),
        warning_threshold=Decimal("80.00"),
    )
    db_session.add(budget)
    db_session.flush()

    alloc_food = BudgetAllocation(
        budget_id=budget.id,
        category_name="Food",
        allocated_amount=Decimal("10000.00"),
    )
    alloc_utils = BudgetAllocation(
        budget_id=budget.id,
        category_name="Utilities",
        allocated_amount=Decimal("5000.00"),
    )
    db_session.add_all([alloc_food, alloc_utils])

    # Add transactions:
    # 1. Food: ₹8,500 on March 10 (85% -> warning threshold 80% met!)
    tx1 = Transaction(
        user_id=user_a.id,
        date=dt.date(2026, 3, 10),
        description="Supermarket",
        amount=Decimal("8500.00"),
        type="debit",
        classification="expense",
        category="Food",
        transaction_key="tx_key_1",
        import_metadata={"is_overlap": False},
    )
    # 2. Utilities: ₹6,000 on March 15 (120% -> exceeded!)
    tx2 = Transaction(
        user_id=user_a.id,
        date=dt.date(2026, 3, 15),
        description="Electricity bill",
        amount=Decimal("6000.00"),
        type="debit",
        classification="expense",
        category="Utilities",
        transaction_key="tx_key_2",
        import_metadata={"is_overlap": False},
    )
    # 3. Unbudgeted expense: ₹2,000 Shopping on March 20
    tx3 = Transaction(
        user_id=user_a.id,
        date=dt.date(2026, 3, 20),
        description="Clothes store",
        amount=Decimal("2000.00"),
        type="debit",
        classification="expense",
        category="Shopping",
        transaction_key="tx_key_3",
        import_metadata={"is_overlap": False},
    )
    # 4. EXCLUDED: Salary income (₹50,000)
    tx4 = Transaction(
        user_id=user_a.id,
        date=dt.date(2026, 3, 1),
        description="Salary",
        amount=Decimal("50000.00"),
        type="credit",
        classification="income",
        category="Income",
        transaction_key="tx_key_4",
        import_metadata={"is_overlap": False},
    )
    # 5. EXCLUDED: Bank transfer (₹5,000)
    tx5 = Transaction(
        user_id=user_a.id,
        date=dt.date(2026, 3, 5),
        description="Transfer to savings",
        amount=Decimal("5000.00"),
        type="debit",
        classification="transfer",
        category="Transfers",
        transaction_key="tx_key_5",
        import_metadata={"is_overlap": False},
    )
    # 6. EXCLUDED: Overlap duplicate expense (₹4,000)
    tx6 = Transaction(
        user_id=user_a.id,
        date=dt.date(2026, 3, 12),
        description="Duplicate food",
        amount=Decimal("4000.00"),
        type="debit",
        classification="expense",
        category="Food",
        transaction_key="tx_key_6",
        import_metadata={"is_overlap": True},
    )
    # 7. EXCLUDED: Transaction in February (prior month)
    tx7 = Transaction(
        user_id=user_a.id,
        date=dt.date(2026, 2, 28),
        description="Prior month dinner",
        amount=Decimal("3000.00"),
        type="debit",
        classification="expense",
        category="Food",
        transaction_key="tx_key_7",
        import_metadata={"is_overlap": False},
    )

    db_session.add_all([tx1, tx2, tx3, tx4, tx5, tx6, tx7])
    db_session.commit()

    # Query budget details
    res = client.get(f"/budgets/{budget.id}", headers=auth_headers_a)
    assert res.status_code == 200
    data = res.json()

    # Total spent must be tx1 + tx2 + tx3 = 8500 + 6000 + 2000 = 16500.00
    assert data["total_spent"] == "16500.00"
    assert data["total_remaining"] == "13500.00"  # 30000 - 16500
    assert data["overall_utilization_pct"] == 55.0
    assert data["overall_is_exceeded"] is False

    allocs = {a["category_name"]: a for a in data["allocations"]}
    # Food allocation: 8500 / 10000 = 85% -> is_warning is True, is_exceeded is False
    assert allocs["Food"]["actual_spent"] == "8500.00"
    assert allocs["Food"]["remaining"] == "1500.00"
    assert allocs["Food"]["utilization_pct"] == 85.0
    assert allocs["Food"]["is_warning"] is True
    assert allocs["Food"]["is_exceeded"] is False

    # Utilities allocation: 6000 / 5000 = 120% -> is_warning is False, is_exceeded is True
    assert allocs["Utilities"]["actual_spent"] == "6000.00"
    assert allocs["Utilities"]["remaining"] == "-1000.00"
    assert allocs["Utilities"]["utilization_pct"] == 120.0
    assert allocs["Utilities"]["is_warning"] is False
    assert allocs["Utilities"]["is_exceeded"] is True


def test_budget_multi_tenant_isolation(client, auth_headers_a, auth_headers_b, user_a, user_b):
    """Verify that users cannot see or modify each other's budgets."""
    payload = {
        "month": 5,
        "year": 2026,
        "total_budget_limit": "25000.00",
        "allocations": [{"category_name": "Food", "allocated_amount": "10000.00"}],
    }

    # User A creates budget
    res_a = client.post("/budgets", json=payload, headers=auth_headers_a)
    assert res_a.status_code == 201
    budget_id = res_a.json()["id"]

    # User B cannot access User A's budget
    res_b_get = client.get(f"/budgets/{budget_id}", headers=auth_headers_b)
    assert res_b_get.status_code == 404

    # User B cannot update User A's budget
    res_b_upd = client.put(f"/budgets/{budget_id}", json={"total_budget_limit": "99999.00"}, headers=auth_headers_b)
    assert res_b_upd.status_code == 404

    # User B cannot delete User A's budget
    res_b_del = client.delete(f"/budgets/{budget_id}", headers=auth_headers_b)
    assert res_b_del.status_code == 404

    # User B can create their own budget for the same month/year
    res_b_create = client.post("/budgets", json=payload, headers=auth_headers_b)
    assert res_b_create.status_code == 201
    assert res_b_create.json()["id"] != budget_id


# ---------------------------------------------------------------------------
# Savings Goals Tests
# ---------------------------------------------------------------------------

def test_savings_goals_crud_and_ledger(client, auth_headers_a, user_a):
    """Verify creating savings goals and managing deposit/withdrawal ledger."""
    # Target in 10 months
    today = dt.date.today()
    target_date = (today.replace(day=1) + dt.timedelta(days=300)).isoformat()

    payload = {
        "name": "Emergency Fund",
        "target_amount": "100000.00",
        "target_date": target_date,
        "category": "Emergency",
        "notes": "6 months of living expenses",
    }

    # 1. Create goal
    res = client.post("/goals", json=payload, headers=auth_headers_a)
    assert res.status_code == 201
    goal = res.json()
    assert goal["name"] == "Emergency Fund"
    assert goal["target_amount"] == "100000.00"
    assert goal["total_saved"] == "0.00"
    assert goal["remaining_target"] == "100000.00"
    assert goal["completion_pct"] == 0.0
    assert goal["is_completed"] is False
    assert goal["monthly_savings_needed"] is not None
    goal_id = goal["id"]

    # 2. Add first deposit: ₹30,000
    dep1 = {
        "amount": "30000.00",
        "contribution_date": today.isoformat(),
        "contribution_type": "deposit",
        "notes": "Initial deposit",
    }
    res_dep1 = client.post(f"/goals/{goal_id}/contributions", json=dep1, headers=auth_headers_a)
    assert res_dep1.status_code == 201
    c1_id = res_dep1.json()["id"]

    # Check goal state
    res_g1 = client.get(f"/goals/{goal_id}", headers=auth_headers_a)
    assert res_g1.json()["total_saved"] == "30000.00"
    assert res_g1.json()["remaining_target"] == "70000.00"
    assert res_g1.json()["completion_pct"] == 30.0
    assert len(res_g1.json()["contributions"]) == 1

    # 3. Add second deposit: ₹20,000
    dep2 = {
        "amount": "20000.00",
        "contribution_date": today.isoformat(),
        "contribution_type": "deposit",
    }
    res_dep2 = client.post(f"/goals/{goal_id}/contributions", json=dep2, headers=auth_headers_a)
    assert res_dep2.status_code == 201

    # Total saved is now 50,000
    res_g2 = client.get(f"/goals/{goal_id}", headers=auth_headers_a)
    assert res_g2.json()["total_saved"] == "50000.00"
    assert res_g2.json()["completion_pct"] == 50.0

    # 4. Valid withdrawal: ₹10,000
    w1 = {
        "amount": "10000.00",
        "contribution_date": today.isoformat(),
        "contribution_type": "withdrawal",
        "notes": "Car repair expense",
    }
    res_w1 = client.post(f"/goals/{goal_id}/contributions", json=w1, headers=auth_headers_a)
    assert res_w1.status_code == 201
    w1_id = res_w1.json()["id"]

    # Total saved is now 40,000
    res_g3 = client.get(f"/goals/{goal_id}", headers=auth_headers_a)
    assert res_g3.json()["total_saved"] == "40000.00"
    assert res_g3.json()["remaining_target"] == "60000.00"
    assert res_g3.json()["completion_pct"] == 40.0

    # 5. Over-withdrawal prevention: Attempt to withdraw ₹50,000 when balance is 40,000
    w_bad = {
        "amount": "50000.00",
        "contribution_date": today.isoformat(),
        "contribution_type": "withdrawal",
    }
    res_w_bad = client.post(f"/goals/{goal_id}/contributions", json=w_bad, headers=auth_headers_a)
    assert res_w_bad.status_code == 400
    assert "exceeds current saved balance" in res_w_bad.json()["detail"]

    # 6. Delete withdrawal restores balance
    res_del_w = client.delete(f"/goals/{goal_id}/contributions/{w1_id}", headers=auth_headers_a)
    assert res_del_w.status_code == 204
    res_restored = client.get(f"/goals/{goal_id}", headers=auth_headers_a)
    assert res_restored.json()["total_saved"] == "50000.00"

    # 7. Archive and unarchive goal
    res_arch = client.post(f"/goals/{goal_id}/archive", headers=auth_headers_a)
    assert res_arch.status_code == 200
    assert res_arch.json()["is_archived"] is True

    # List default excludes archived
    res_list_active = client.get("/goals", headers=auth_headers_a)
    assert len(res_list_active.json()) == 0

    # List with include_archived=true includes it
    res_list_all = client.get("/goals?include_archived=true", headers=auth_headers_a)
    assert len(res_list_all.json()) == 1

    # Unarchive
    res_unarch = client.post(f"/goals/{goal_id}/unarchive", headers=auth_headers_a)
    assert res_unarch.status_code == 200
    assert res_unarch.json()["is_archived"] is False

    # 8. Delete goal
    res_del_g = client.delete(f"/goals/{goal_id}", headers=auth_headers_a)
    assert res_del_g.status_code == 204
    assert client.get(f"/goals/{goal_id}", headers=auth_headers_a).status_code == 404


def test_savings_goal_multi_tenant_isolation(client, auth_headers_a, auth_headers_b, user_a, user_b):
    """Verify cross-user isolation for savings goals and contributions."""
    payload = {
        "name": "New Laptop",
        "target_amount": "80000.00",
    }

    res_a = client.post("/goals", json=payload, headers=auth_headers_a)
    assert res_a.status_code == 201
    goal_id = res_a.json()["id"]

    # User B cannot access or contribute to User A's goal
    assert client.get(f"/goals/{goal_id}", headers=auth_headers_b).status_code == 404
    assert client.post(f"/goals/{goal_id}/contributions", json={"amount": "5000.00", "contribution_date": "2026-03-01"}, headers=auth_headers_b).status_code == 404
    assert client.delete(f"/goals/{goal_id}", headers=auth_headers_b).status_code == 404
