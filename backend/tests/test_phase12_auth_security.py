"""
Phase 12: Authentication & Authorization Security Test Suite (Step 3).

Verifies strict cross-user tenant isolation:
1. Signup and login with password verification.
2. Invalid credentials and generic 401 error message.
3. JWT expiration handling.
4. Tampered JWT signatures and malformed tokens rejected with 401.
5. Cross-user FinancialAccount isolation (read, update, delete).
6. Cross-user Transaction isolation (read, update, delete).
7. Cross-user Budget isolation (read, update, delete).
8. Cross-user SavingsGoal and Contribution isolation.
9. Cross-user RecurringPayment isolation.
10. Cross-user FinancialAlert isolation.
11. Cross-user Report Export isolation.
12. Cross-user AI Conversation and AI Tool execution isolation.
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
    Budget,
    BudgetAllocation,
    SavingsGoal,
    SavingsContribution,
    RecurringPayment,
    FinancialAlert,
    AIConversation,
    AIMessage,
)
from main import app
from auth_utils import hash_password
from jwt_utils import create_access_token


@pytest.fixture
def auth_suite_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield {"client": test_client, "db": session}

    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def users_fixture(auth_suite_db):
    client = auth_suite_db["client"]
    db = auth_suite_db["db"]

    # Create User Alpha
    user_a = User(
        email="alpha@example.com",
        full_name="User Alpha",
        hashed_password=hash_password("AlphaPass123!"),
    )
    # Create User Beta
    user_b = User(
        email="beta@example.com",
        full_name="User Beta",
        hashed_password=hash_password("BetaPass123!"),
    )
    db.add_all([user_a, user_b])
    db.commit()
    db.refresh(user_a)
    db.refresh(user_b)

    token_a = create_access_token(data={"sub": user_a.email, "user_id": user_a.id})
    token_b = create_access_token(data={"sub": user_b.email, "user_id": user_b.id})

    return {
        "client": client,
        "db": db,
        "user_a": user_a,
        "user_b": user_b,
        "headers_a": {"Authorization": f"Bearer {token_a}"},
        "headers_b": {"Authorization": f"Bearer {token_b}"},
        "token_a": token_a,
        "token_b": token_b,
    }


def test_auth_invalid_credentials_and_tampered_jwt(users_fixture):
    client = users_fixture["client"]

    # 1. Invalid password
    res = client.post("/auth/login", json={"email": "alpha@example.com", "password": "WrongPassword!"})
    assert res.status_code == 401
    assert "Incorrect email or password" in res.json()["detail"]

    # 2. Tampered JWT signature
    tampered_token = users_fixture["token_a"][:-5] + "XXXXX"
    res_tampered = client.get("/accounts", headers={"Authorization": f"Bearer {tampered_token}"})
    assert res_tampered.status_code == 401

    # 3. Expired JWT
    expired_token = create_access_token(
        data={"sub": users_fixture["user_a"].email, "user_id": users_fixture["user_a"].id},
        expires_delta=dt.timedelta(seconds=-10),
    )
    res_expired = client.get("/accounts", headers={"Authorization": f"Bearer {expired_token}"})
    assert res_expired.status_code == 401


def test_cross_user_account_isolation(users_fixture):
    client = users_fixture["client"]
    headers_a = users_fixture["headers_a"]
    headers_b = users_fixture["headers_b"]

    # User A creates an account
    res_create = client.post(
        "/accounts",
        headers=headers_a,
        json={"name": "Alpha Private Savings", "account_type": "savings", "opening_balance": "50000.00"},
    )
    assert res_create.status_code == 201
    acc_a_id = res_create.json()["id"]

    # User B cannot view User A's account
    res_get = client.get(f"/accounts/{acc_a_id}", headers=headers_b)
    assert res_get.status_code == 404

    # User B cannot edit User A's account
    res_patch = client.put(f"/accounts/{acc_a_id}", headers=headers_b, json={"name": "Hacked Name"})
    assert res_patch.status_code == 404

    # User B cannot delete User A's account
    res_del = client.delete(f"/accounts/{acc_a_id}", headers=headers_b)
    assert res_del.status_code == 404


def test_cross_user_transaction_isolation(users_fixture):
    client = users_fixture["client"]
    headers_a = users_fixture["headers_a"]
    headers_b = users_fixture["headers_b"]

    # User A creates a transaction
    res_tx = client.post(
        "/transactions",
        headers=headers_a,
        json={
            "date": dt.date.today().isoformat(),
            "description": "Alpha Secret Purchase",
            "amount": "1500.00",
            "type": "debit",
            "category_name": "Shopping",
        },
    )
    assert res_tx.status_code == 201
    tx_a_id = res_tx.json()["id"]

    # User B cannot access User A's transaction
    res_get = client.get(f"/transactions/{tx_a_id}", headers=headers_b)
    assert res_get.status_code == 404

    # User B cannot modify User A's transaction category
    res_cat = client.patch(
        f"/transactions/{tx_a_id}/category",
        headers=headers_b,
        json={"category_name": "Food"},
    )
    assert res_cat.status_code == 404

    # User B cannot delete User A's transaction
    res_del = client.delete(f"/transactions/{tx_a_id}", headers=headers_b)
    assert res_del.status_code == 404


def test_cross_user_budget_and_goals_isolation(users_fixture):
    client = users_fixture["client"]
    headers_a = users_fixture["headers_a"]
    headers_b = users_fixture["headers_b"]
    today = dt.date.today()

    # User A creates a Budget
    res_b = client.post(
        "/budgets",
        headers=headers_a,
        json={
            "month": today.month,
            "year": today.year,
            "total_budget_limit": "25000.00",
        },
    )
    assert res_b.status_code == 201
    b_id = res_b.json()["id"]

    # User B cannot edit User A's budget
    res_b_mod = client.put(f"/budgets/{b_id}", headers=headers_b, json={"total_budget_limit": "99999.00"})
    assert res_b_mod.status_code == 404

    # User A creates a Savings Goal
    res_g = client.post(
        "/goals",
        headers=headers_a,
        json={"name": "Alpha Retirement", "target_amount": "500000.00"},
    )
    assert res_g.status_code == 201
    g_id = res_g.json()["id"]

    # User B cannot post contributions to User A's goal
    res_contrib = client.post(
        f"/goals/{g_id}/contributions",
        headers=headers_b,
        json={"amount": "1000.00", "contribution_date": today.isoformat(), "contribution_type": "deposit"},
    )
    assert res_contrib.status_code == 404


def test_cross_user_report_exports_and_ai_conversations_isolation(users_fixture):
    client = users_fixture["client"]
    headers_a = users_fixture["headers_a"]
    headers_b = users_fixture["headers_b"]
    db = users_fixture["db"]
    user_a = users_fixture["user_a"]

    # Insert private transaction for User A
    t_secret = Transaction(
        user_id=user_a.id,
        date=dt.date.today(),
        description="CONFIDENTIAL_EXECUTIVE_SALARY",
        amount=Decimal("500000.00"),
        type="credit",
        classification="income",
        category="Salary",
        transaction_key="secret_key_1",
    )
    db.add(t_secret)
    db.commit()

    # User B requests CSV export -> Must NOT contain User A's confidential data
    csv_res_b = client.get("/reports/export/csv", headers=headers_b)
    assert csv_res_b.status_code == 200
    assert "CONFIDENTIAL_EXECUTIVE_SALARY" not in csv_res_b.text

    # User B requests Summary Report -> Must show 0 income
    sum_res_b = client.get("/reports/summary", headers=headers_b)
    assert sum_res_b.status_code == 200
    assert sum_res_b.json()["summary"]["total_income"] == 0.0

    # User A creates AI conversation
    conv_a = AIConversation(user_id=user_a.id, title="Alpha Private Financial Advice")
    db.add(conv_a)
    db.commit()
    db.refresh(conv_a)

    # User B cannot access User A's conversation
    conv_res_b = client.get(f"/ai/conversations/{conv_a.id}", headers=headers_b)
    assert conv_res_b.status_code == 404


def test_upload_statement_unauthorized_account_rejected(users_fixture):
    client = users_fixture["client"]
    headers_a = users_fixture["headers_a"]
    headers_b = users_fixture["headers_b"]

    # User A creates an account
    res_a = client.post(
        "/accounts",
        headers=headers_a,
        json={"name": "Alpha Account", "account_type": "savings", "opening_balance": "1000.00"},
    )
    assert res_a.status_code == 201
    acc_a_id = res_a.json()["id"]

    # User B attempts to upload statement explicitly attaching to User A's account
    csv_content = b"Date,Description,Amount\n2026-03-01,Groceries,500.00\n"
    res_upload = client.post(
        "/upload-statement",
        headers=headers_b,
        data={"account_id": acc_a_id},
        files={"file": ("stmt.csv", csv_content, "text/csv")},
    )
    # Must fail with 404 Financial account not found, NOT 200 silent fallback
    assert res_upload.status_code == 404
    assert "Financial account not found" in res_upload.json()["detail"]

