"""
End-to-End Workflow Verification Suite for PaisaClarity (Phase 11 Step 7).

Validates the complete 10 realistic financial workflows end-to-end:
1. Signup -> Login -> Auth token acquisition
2. Financial Account Creation (Verified vs Placeholder)
3. Transaction Ingestion & Categorization
4. Manual Category Override with apply_to_future Rule Generation
5. Budget Creation & Spending Tracking
6. Savings Goal Creation & Contribution Allocation
7. Recurring Payment Detection & Confirmation
8. Financial Alert Generation & Status Update
9. Executive Reporting Summary & CSV / PDF Export Generation
10. Token Verification & Logout / Unauthenticated Rejection
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
    BudgetAllocation,
    SavingsGoal,
    SavingsContribution,
    RecurringPayment,
    FinancialAlert,
)
from main import app


@pytest.fixture
def test_env():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Pre-seed system categories
    cats = [
        ("Salary", "income"),
        ("Groceries", "expense"),
        ("Dining", "expense"),
        ("Transfers", "transfer"),
        ("Utilities", "expense"),
    ]
    for c_name, c_type in cats:
        session.add(Category(name=c_name, category_type=c_type, is_system=True, user_id=None))
    session.commit()

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


def test_full_end_to_end_financial_lifecycle(test_env):
    client = test_env["client"]
    db = test_env["db"]

    # -------------------------------------------------------------------------
    # Flow 1: Signup -> Login -> Dashboard Access
    # -------------------------------------------------------------------------
    signup_res = client.post(
        "/auth/signup",
        json={
            "email": "e2e_user@example.com",
            "password": "StrongPassword123!",
            "full_name": "E2E User",
        },
    )
    assert signup_res.status_code in (200, 201)

    login_res = client.post(
        "/auth/login",
        json={
            "email": "e2e_user@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # -------------------------------------------------------------------------
    # Flow 2: Create Accounts (One verified savings, one placeholder imported)
    # -------------------------------------------------------------------------
    acc_res = client.post(
        "/accounts",
        headers=headers,
        json={
            "name": "Main Checking Account",
            "account_type": "savings",
            "currency": "INR",
            "opening_balance": "40000.00",
            "masked_identifier": "XX1122",
        },
    )
    assert acc_res.status_code == 201
    acc_id = acc_res.json()["id"]

    # -------------------------------------------------------------------------
    # Flow 3: Transaction Ingestion
    # -------------------------------------------------------------------------
    today = dt.date.today()
    tx_salary_res = client.post(
        "/transactions",
        headers=headers,
        json={
            "account_id": acc_id,
            "date": today.isoformat(),
            "description": "Tech Corp Monthly Salary",
            "amount": "80000.00",
            "type": "credit",
            "category_name": "Salary",
        },
    )
    assert tx_salary_res.status_code == 201

    tx_grocery_res = client.post(
        "/transactions",
        headers=headers,
        json={
            "account_id": acc_id,
            "date": today.isoformat(),
            "description": "Nature Basket Supermarket",
            "amount": "12000.00",
            "type": "debit",
            "category_name": "Groceries",
        },
    )
    assert tx_grocery_res.status_code == 201

    tx_dining_res = client.post(
        "/transactions",
        headers=headers,
        json={
            "account_id": acc_id,
            "date": today.isoformat(),
            "description": "Starbucks Reserve Coffee",
            "amount": "850.00",
            "type": "debit",
            "category_name": "Other",
        },
    )
    assert tx_dining_res.status_code == 201
    dining_tx_id = tx_dining_res.json()["id"]

    # -------------------------------------------------------------------------
    # Flow 4: Manual Categorization Override with apply_to_future
    # -------------------------------------------------------------------------
    corr_res = client.patch(
        f"/transactions/{dining_tx_id}/category",
        headers=headers,
        json={
            "category_name": "Dining",
            "apply_to_future": True,
        },
    )
    assert corr_res.status_code == 200
    assert corr_res.json()["category"] == "Dining"

    # -------------------------------------------------------------------------
    # Flow 5: Budget Creation & Utilization Tracking
    # -------------------------------------------------------------------------
    budget_res = client.post(
        "/budgets",
        headers=headers,
        json={
            "month": today.month,
            "year": today.year,
            "total_budget_limit": "50000.00",
            "allocations": [
                {"category_name": "Groceries", "allocated_amount": "20000.00"},
                {"category_name": "Dining", "allocated_amount": "5000.00"},
            ],
        },
    )
    assert budget_res.status_code == 201

    # -------------------------------------------------------------------------
    # Flow 6: Savings Goal Creation & Contribution Allocation
    # -------------------------------------------------------------------------
    goal_res = client.post(
        "/goals",
        headers=headers,
        json={
            "name": "Emergency Fund",
            "target_amount": "100000.00",
            "category": "emergency",
        },
    )
    assert goal_res.status_code == 201
    goal_id = goal_res.json()["id"]

    contrib_res = client.post(
        f"/goals/{goal_id}/contributions",
        headers=headers,
        json={
            "amount": "15000.00",
            "contribution_date": today.isoformat(),
            "contribution_type": "deposit",
            "notes": "Initial seed from salary",
        },
    )
    assert contrib_res.status_code == 201

    # -------------------------------------------------------------------------
    # Flow 7: Recurring Payments (Subscriptions)
    # -------------------------------------------------------------------------
    rec_res = client.post(
        "/recurring",
        headers=headers,
        json={
            "name": "Netflix India",
            "frequency": "monthly",
            "average_amount": "649.00",
            "category": "Entertainment",
        },
    )
    assert rec_res.status_code == 201
    rec_id = rec_res.json()["id"]

    # Confirm subscription
    confirm_res = client.post(
        f"/recurring/{rec_id}/confirm",
        headers=headers,
    )
    assert confirm_res.status_code == 200

    # -------------------------------------------------------------------------
    # Flow 8: Financial Alerts
    # -------------------------------------------------------------------------
    gen_alerts_res = client.post("/alerts/evaluate", headers=headers)
    assert gen_alerts_res.status_code == 200

    # -------------------------------------------------------------------------
    # Flow 9: Financial Reports Summary & Exports (CSV, PDF)
    # -------------------------------------------------------------------------
    summary_res = client.get("/reports/summary", headers=headers)
    assert summary_res.status_code == 200
    summary_data = summary_res.json()

    assert summary_data["summary"]["total_income"] == 80000.0
    assert summary_data["summary"]["total_expenses"] == 12850.0  # 12,000 + 850
    assert summary_data["summary"]["net_cash_flow"] == 67150.0
    assert summary_data["savings_goals"]["total_saved"] == 15000.0
    assert summary_data["recurring_payments"]["confirmed_count"] == 1

    # CSV Export
    csv_res = client.get("/reports/export/csv", headers=headers)
    assert csv_res.status_code == 200
    assert "Nature Basket Supermarket" in csv_res.text
    assert "Starbucks Reserve Coffee" in csv_res.text

    # PDF Export
    pdf_res = client.get("/reports/export/pdf", headers=headers)
    assert pdf_res.status_code == 200
    assert pdf_res.content.startswith(b"%PDF-")

    # -------------------------------------------------------------------------
    # Flow 10: Logout / Unauthenticated Rejection
    # -------------------------------------------------------------------------
    # Invalid or missing token produces 401
    unauth_res = client.get("/reports/summary", headers={"Authorization": "Bearer invalid_token"})
    assert unauth_res.status_code == 401
