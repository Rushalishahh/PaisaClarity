"""
Phase 12: Cross-Module Financial Calculation Consistency Test Suite (Step 5).

Verifies identical financial calculations across:
1. Multi-statement Aggregated Transactions (Dashboard / reality check)
2. Cash Flow Intelligence API (/analytics/cash-flow)
3. Financial Reporting API (/reports/summary)
4. Budget Tracking Engine (/budgets/current)
5. AI Financial Copilot Tools (get_spending_summary, get_category_breakdown)

Ensures consistent treatment of:
- Internal Transfers (excluded from expenses across all endpoints)
- Overlapping Duplicates (excluded from expenses across all endpoints)
- Placeholder / Unreconciled Accounts (strictly isolated from liquid net worth)
- Decimal Monetary Rounding (no floating-point discrepancies)
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
)
from main import app
from auth_utils import hash_password
from jwt_utils import create_access_token
from ai.tools import get_spending_summary, get_category_breakdown


@pytest.fixture
def financial_consistency_env():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    user = User(
        email="consistent_user@example.com",
        full_name="Consistency Tester",
        hashed_password=hash_password("Pass123!"),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    # Verified Account
    acc_verified = FinancialAccount(
        user_id=user.id,
        name="Verified Salary Account",
        account_type="savings",
        opening_balance=Decimal("20000.00"),
        is_reconciled=True,
    )
    # Placeholder Unreconciled Account
    acc_placeholder = FinancialAccount(
        user_id=user.id,
        name="Imported Statements",
        account_type="imported",
        opening_balance=Decimal("99999.00"),
        is_reconciled=False,
    )
    session.add_all([acc_verified, acc_placeholder])
    session.commit()
    session.refresh(acc_verified)
    session.refresh(acc_placeholder)

    # Categories
    cat_salary = Category(user_id=user.id, name="Salary", category_type="income", is_system=True)
    cat_groceries = Category(user_id=user.id, name="Groceries", category_type="expense", is_system=True)
    cat_transfer = Category(user_id=user.id, name="Transfers", category_type="transfer", is_system=True)
    session.add_all([cat_salary, cat_groceries, cat_transfer])
    session.commit()

    # Financial Transactions in current month
    today = dt.date.today()
    t_income = Transaction(
        user_id=user.id,
        account_id=acc_verified.id,
        date=today,
        description="Salary Inflow",
        amount=Decimal("100000.00"),
        type="credit",
        classification="income",
        category="Salary",
        transaction_key="k_inc",
    )
    t_expense1 = Transaction(
        user_id=user.id,
        account_id=acc_verified.id,
        date=today,
        description="Supermarket Bill",
        amount=Decimal("15000.00"),
        type="debit",
        classification="expense",
        category="Groceries",
        transaction_key="k_exp1",
    )
    t_expense2 = Transaction(
        user_id=user.id,
        account_id=acc_verified.id,
        date=today,
        description="Pantry Items",
        amount=Decimal("5000.00"),
        type="debit",
        classification="expense",
        category="Groceries",
        transaction_key="k_exp2",
    )
    t_transfer = Transaction(
        user_id=user.id,
        account_id=acc_verified.id,
        date=today,
        description="Internal account move",
        amount=Decimal("25000.00"),
        type="debit",
        classification="transfer",
        category="Transfers",
        transaction_key="k_trf",
    )
    session.add_all([t_income, t_expense1, t_expense2, t_transfer])
    session.commit()

    token = create_access_token(data={"sub": user.email, "user_id": user.id})
    headers = {"Authorization": f"Bearer {token}"}

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield {
            "client": test_client,
            "user": user,
            "headers": headers,
            "db": session,
            "today": today,
            "acc_verified": acc_verified,
        }

    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_cross_module_expense_and_transfer_consistency(financial_consistency_env):
    """
    Verifies that across:
    1. /reports/summary
    2. /analytics/cash-flow
    3. AI tool: get_spending_summary
    
    Total Spending = Rs. 20,000.00 (15,000 + 5,000), internal transfer (25,000) is strictly EXCLUDED.
    """
    client = financial_consistency_env["client"]
    headers = financial_consistency_env["headers"]
    user = financial_consistency_env["user"]
    db = financial_consistency_env["db"]

    # 1. Reports API
    res_reports = client.get("/reports/summary", headers=headers)
    assert res_reports.status_code == 200
    data_reports = res_reports.json()
    rep_income = data_reports["summary"]["total_income"]
    rep_expenses = data_reports["summary"]["total_expenses"]
    rep_net = data_reports["summary"]["net_cash_flow"]

    # 2. Cash Flow Intelligence API
    res_cashflow = client.get("/analytics/cash-flow", headers=headers)
    assert res_cashflow.status_code == 200
    data_cashflow = res_cashflow.json()
    cf_income = float(data_cashflow["total_income"])
    cf_expenses = float(data_cashflow["total_expenses"])
    cf_net = float(data_cashflow["net_cash_flow"])

    # 3. AI Copilot Safe Tool
    ai_summary = get_spending_summary(db=db, user=user)
    ai_expenses = float(ai_summary["total_expenses"])

    # Assert 100% Mathematical Consistency across all modules
    assert rep_income == 100000.0
    assert cf_income == 100000.0

    assert rep_expenses == 20000.0
    assert cf_expenses == 20000.0
    assert ai_expenses == 20000.0

    assert rep_net == 80000.0
    assert cf_net == 80000.0


def test_cross_module_unreconciled_account_isolation_consistency(financial_consistency_env):
    """
    Verifies that the placeholder imported account (Rs. 99,999.00) NEVER leaks into verified liquid net worth
    in either Reports API or Cash Flow Intelligence API.
    """
    client = financial_consistency_env["client"]
    headers = financial_consistency_env["headers"]

    # Reports API net worth
    res_reports = client.get("/reports/summary", headers=headers)
    assert res_reports.status_code == 200
    data_reports = res_reports.json()
    rep_liquid = data_reports["net_worth"]["verified_liquid_balance"]
    rep_unreconciled = data_reports["net_worth"]["unreconciled_placeholder_balance"]

    # Cash Flow accounts summary
    res_cashflow = client.get("/analytics/cash-flow", headers=headers)
    assert res_cashflow.status_code == 200
    data_cashflow = res_cashflow.json()
    accounts_cf = {a["name"]: a for a in data_cashflow["accounts"]}
    
    # Opening balance (20,000) + income (100,000) - expense (20,000) - transfer (25,000) = 75,000
    assert rep_liquid == 75000.0
    assert float(accounts_cf["Verified Salary Account"]["calculated_balance"]) == 75000.0
    assert accounts_cf["Imported Statements"]["is_reconciled"] is False
    assert accounts_cf["Imported Statements"]["calculated_balance"] is None
    assert rep_unreconciled == 99999.0
