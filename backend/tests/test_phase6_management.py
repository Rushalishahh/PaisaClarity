"""Comprehensive test suite for Phase 6: Transaction, Account, and Category Management."""

import datetime as dt
from decimal import Decimal
import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from models import User, FinancialAccount, Category, Transaction, Statement
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
# Account Management Tests
# ---------------------------------------------------------------------------

def test_account_crud_and_balance_calculation(client, auth_headers_a, user_a, db_session):
    # 1. Create Account
    res = client.post(
        "/accounts",
        headers=auth_headers_a,
        json={
            "name": "HDFC Salary",
            "account_type": "savings",
            "currency": "INR",
            "opening_balance": "5000.00",
            "masked_identifier": "XX9876",
        },
    )
    assert res.status_code == 201
    acc_data = res.json()
    acc_id = acc_data["id"]
    assert acc_data["name"] == "HDFC Salary"
    assert acc_data["opening_balance"] == "5000.00"
    assert acc_data["calculated_balance"] == "5000.00"
    assert acc_data["is_reconciled"] is True

    # 2. Add Transactions to verify calculated balance
    client.post(
        "/transactions",
        headers=auth_headers_a,
        json={
            "account_id": acc_id,
            "date": "2026-06-01",
            "description": "Salary Credit",
            "amount": "25000.00",
            "type": "credit",
            "category": "Income",
        },
    )
    client.post(
        "/transactions",
        headers=auth_headers_a,
        json={
            "account_id": acc_id,
            "date": "2026-06-02",
            "description": "Groceries Spend",
            "amount": "3000.00",
            "type": "debit",
            "category": "Groceries",
        },
    )

    # 3. Check calculated balance: 5000 + 25000 - 3000 = 27000
    res = client.get(f"/accounts/{acc_id}", headers=auth_headers_a)
    assert res.status_code == 200
    data = res.json()
    assert data["calculated_balance"] == "27000.00"
    assert data["transaction_count"] == 2

    # 4. Safe deletion restriction: cannot delete account with transactions
    del_res = client.delete(f"/accounts/{acc_id}", headers=auth_headers_a)
    assert del_res.status_code == 400
    assert "Cannot delete account" in del_res.json()["detail"]

    # 5. Archive Account
    arch_res = client.post(f"/accounts/{acc_id}/archive", headers=auth_headers_a)
    assert arch_res.status_code == 200
    assert arch_res.json()["is_archived"] is True

    # List default accounts excludes archived
    list_res = client.get("/accounts", headers=auth_headers_a)
    assert len(list_res.json()) == 0

    # List with include_archived=True includes it
    list_res_arch = client.get("/accounts?include_archived=true", headers=auth_headers_a)
    assert len(list_res_arch.json()) == 1


def test_unreconciled_imported_account_workflow(client, auth_headers_a, user_a, db_session):
    # Create imported placeholder account (as statement backfill does)
    acc = FinancialAccount(
        user_id=user_a.id,
        name="Imported Statements",
        account_type="imported",
        currency="INR",
        opening_balance=Decimal("0.00"),
        is_reconciled=False,
        is_archived=False,
    )
    db_session.add(acc)
    db_session.commit()
    db_session.refresh(acc)

    # Add transaction to it
    tx = Transaction(
        user_id=user_a.id,
        account_id=acc.id,
        date=dt.date(2026, 6, 1),
        description="Historical Swiggy",
        amount=Decimal("450.00"),
        type="debit",
        classification="expense",
        category="Food",
        transaction_key="key_swiggy_450",
    )
    db_session.add(tx)
    db_session.commit()

    # Verify calculated balance is None to avoid presenting unverified balance
    res = client.get(f"/accounts/{acc.id}", headers=auth_headers_a)
    assert res.status_code == 200
    assert res.json()["calculated_balance"] is None
    assert res.json()["is_reconciled"] is False

    # Workflow 1: Reconcile in place
    recon_res = client.post(
        f"/accounts/{acc.id}/reconcile",
        headers=auth_headers_a,
        json={"name": "SBI Savings Reconciled", "account_type": "savings", "masked_identifier": "XX4433"},
    )
    assert recon_res.status_code == 200
    recon_data = recon_res.json()
    assert recon_data["name"] == "SBI Savings Reconciled"
    assert recon_data["is_reconciled"] is True
    # Now that it's verified, calculated balance is available (0.00 - 450.00 = -450.00)
    assert recon_data["calculated_balance"] == "-450.00"


def test_account_reconcile_merge_workflow(client, auth_headers_a, user_a, db_session):
    # Create target verified account
    target = FinancialAccount(
        user_id=user_a.id,
        name="Main Checking",
        account_type="savings",
        opening_balance=Decimal("1000.00"),
        is_reconciled=True,
    )
    # Create imported placeholder account
    imported = FinancialAccount(
        user_id=user_a.id,
        name="Imported Statements",
        account_type="imported",
        is_reconciled=False,
    )
    db_session.add_all([target, imported])
    db_session.commit()

    tx = Transaction(
        user_id=user_a.id,
        account_id=imported.id,
        date=dt.date(2026, 6, 1),
        description="Coffee Spend",
        amount=Decimal("150.00"),
        type="debit",
        classification="expense",
        category="Food",
        transaction_key="key_coffee_150",
    )
    db_session.add(tx)
    db_session.commit()

    # Merge imported account into target
    merge_res = client.post(
        f"/accounts/{imported.id}/reconcile",
        headers=auth_headers_a,
        json={"merge_into_account_id": target.id},
    )
    assert merge_res.status_code == 200
    assert merge_res.json()["id"] == target.id

    # Verify transaction was reassigned to target
    db_session.refresh(tx)
    assert tx.account_id == target.id

    # Source account should be archived
    db_session.refresh(imported)
    assert imported.is_archived is True


# ---------------------------------------------------------------------------
# Category Management Tests
# ---------------------------------------------------------------------------

def test_category_management_and_synchronization(client, auth_headers_a, user_a, db_session):
    # 1. List Categories contains system categories
    cats_res = client.get("/categories", headers=auth_headers_a)
    assert cats_res.status_code == 200
    cat_names = [c["name"] for c in cats_res.json()]
    assert "Food" in cat_names
    assert "Transfers" in cat_names

    # 2. Create custom category
    custom_res = client.post(
        "/categories",
        headers=auth_headers_a,
        json={"name": "Dog Care", "category_type": "expense", "icon": "dog", "color": "#ffaa00"},
    )
    assert custom_res.status_code == 201
    custom_cat = custom_res.json()
    cat_id = custom_cat["id"]
    assert custom_cat["name"] == "Dog Care"

    # 3. Create a transaction using this custom category
    tx_res = client.post(
        "/transactions",
        headers=auth_headers_a,
        json={
            "date": "2026-06-10",
            "description": "Pet store vet checkup",
            "amount": "1200.00",
            "type": "debit",
            "category_id": cat_id,
        },
    )
    assert tx_res.status_code == 201
    tx_data = tx_res.json()
    assert tx_data["category_id"] == cat_id
    assert tx_data["category"] == "Dog Care"

    # 4. Rename custom category -> verify synchronized transaction category update
    rename_res = client.put(
        f"/categories/{cat_id}",
        headers=auth_headers_a,
        json={"name": "Pet Care"},
    )
    assert rename_res.status_code == 200
    assert rename_res.json()["name"] == "Pet Care"

    # Transaction category string must be synchronized to "Pet Care"
    tx_get = client.get(f"/transactions/{tx_data['id']}", headers=auth_headers_a)
    assert tx_get.status_code == 200
    assert tx_get.json()["category"] == "Pet Care"
    assert tx_get.json()["category_id"] == cat_id

    # 5. Prohibit modifying system category
    food_cat = db_session.query(Category).filter(Category.name == "Food").first()
    mod_sys = client.put(f"/categories/{food_cat.id}", headers=auth_headers_a, json={"name": "Fancy Food"})
    assert mod_sys.status_code == 403

    # 6. Prohibit deleting system category
    del_sys = client.delete(f"/categories/{food_cat.id}", headers=auth_headers_a)
    assert del_sys.status_code == 403

    # 7. Safe deletion of custom category: category_id set to None, text preserved
    del_custom = client.delete(f"/categories/{cat_id}", headers=auth_headers_a)
    assert del_custom.status_code == 200

    tx_after_del = client.get(f"/transactions/{tx_data['id']}", headers=auth_headers_a)
    assert tx_after_del.status_code == 200
    # category_id is set to None, but historical category string "Pet Care" is preserved!
    assert tx_after_del.json()["category_id"] is None
    assert tx_after_del.json()["category"] == "Pet Care"


# ---------------------------------------------------------------------------
# Transaction Management & Transfers Tests
# ---------------------------------------------------------------------------

def test_transaction_crud_filters_and_pagination(client, auth_headers_a, user_a, db_session):
    # Create Account
    acc = FinancialAccount(user_id=user_a.id, name="Cash", account_type="wallet", is_reconciled=True)
    db_session.add(acc)
    db_session.commit()

    # Create several transactions with different amounts, dates, categories
    dates = ["2026-06-01", "2026-06-05", "2026-06-10", "2026-06-15", "2026-06-20"]
    amounts = ["100.00", "500.00", "250.50", "1500.00", "3000.00"]
    cats = ["Food", "Transport", "Bills", "Shopping", "Food"]

    for d, a, c in zip(dates, amounts, cats):
        res = client.post(
            "/transactions",
            headers=auth_headers_a,
            json={
                "account_id": acc.id,
                "date": d,
                "description": f"Spend for {c} test",
                "merchant": "Test Merchant",
                "amount": a,
                "type": "debit",
                "category": c,
            },
        )
        assert res.status_code == 201

    # Test Pagination (page=1, page_size=2)
    paginated_res = client.get("/transactions?page=1&page_size=2", headers=auth_headers_a)
    assert paginated_res.status_code == 200
    data = paginated_res.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["pages"] == 3

    # Test Filter by Category
    food_res = client.get("/transactions?category=Food", headers=auth_headers_a)
    assert food_res.status_code == 200
    assert food_res.json()["total"] == 2

    # Test Filter by Date Range
    date_res = client.get("/transactions?start_date=2026-06-05&end_date=2026-06-15", headers=auth_headers_a)
    assert date_res.status_code == 200
    assert date_res.json()["total"] == 3

    # Test Search by description
    search_res = client.get("/transactions?search=Transport", headers=auth_headers_a)
    assert search_res.status_code == 200
    assert search_res.json()["total"] == 1

    # Test Sort by Amount desc
    sort_res = client.get("/transactions?sort_by=amount&sort_order=desc", headers=auth_headers_a)
    assert sort_res.status_code == 200
    items = sort_res.json()["items"]
    assert items[0]["amount"] == "3000.00"
    assert items[-1]["amount"] == "100.00"

    # Test Category Correction
    tx_id = items[0]["id"]
    patch_res = client.patch(
        f"/transactions/{tx_id}/category",
        headers=auth_headers_a,
        json={"category_name": "Entertainment"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["category"] == "Entertainment"


def test_paired_transfer_workflow(client, auth_headers_a, user_a, db_session):
    acc1 = FinancialAccount(user_id=user_a.id, name="Savings A", account_type="savings", is_reconciled=True)
    acc2 = FinancialAccount(user_id=user_a.id, name="Wallet B", account_type="wallet", is_reconciled=True)
    db_session.add_all([acc1, acc2])
    db_session.commit()

    # Create transfer of ₹2000 from Savings A to Wallet B
    transfer_res = client.post(
        "/transactions/transfer",
        headers=auth_headers_a,
        json={
            "from_account_id": acc1.id,
            "to_account_id": acc2.id,
            "date": "2026-06-15",
            "amount": "2000.00",
            "description": "ATM cash refill",
        },
    )
    assert transfer_res.status_code == 201
    t_data = transfer_res.json()
    group_id = t_data["transfer_group_id"]
    out_leg = t_data["outgoing_transaction"]
    in_leg = t_data["incoming_transaction"]

    assert out_leg["account_id"] == acc1.id
    assert out_leg["type"] == "debit"
    assert out_leg["classification"] == "transfer"
    assert out_leg["category"] == "Transfers"
    assert out_leg["amount"] == "2000.00"

    assert in_leg["account_id"] == acc2.id
    assert in_leg["type"] == "credit"
    assert in_leg["classification"] == "transfer"
    assert in_leg["category"] == "Transfers"
    assert in_leg["amount"] == "2000.00"

    assert out_leg["transfer_group_id"] == in_leg["transfer_group_id"] == group_id

    # Deleting one leg with delete_paired_transfer=True deletes both legs
    del_res = client.delete(f"/transactions/{out_leg['id']}?delete_paired_transfer=true", headers=auth_headers_a)
    assert del_res.status_code == 200

    # Confirm both legs are deleted
    assert client.get(f"/transactions/{out_leg['id']}", headers=auth_headers_a).status_code == 404
    assert client.get(f"/transactions/{in_leg['id']}", headers=auth_headers_a).status_code == 404


# ---------------------------------------------------------------------------
# Multi-Tenant Isolation Tests
# ---------------------------------------------------------------------------

def test_multi_tenant_authorization(client, auth_headers_a, auth_headers_b, user_a, user_b, db_session):
    # User A creates an account and transaction
    acc_a = FinancialAccount(user_id=user_a.id, name="Alpha Vault", account_type="savings", is_reconciled=True)
    db_session.add(acc_a)
    db_session.commit()

    tx_a = Transaction(
        user_id=user_a.id,
        account_id=acc_a.id,
        date=dt.date(2026, 6, 1),
        description="Alpha Secret Spend",
        amount=Decimal("999.00"),
        type="debit",
        classification="expense",
        category="Other",
        transaction_key="key_alpha_secret",
    )
    db_session.add(tx_a)
    db_session.commit()

    # User B attempts to access User A's account -> 404
    assert client.get(f"/accounts/{acc_a.id}", headers=auth_headers_b).status_code == 404
    assert client.put(f"/accounts/{acc_a.id}", headers=auth_headers_b, json={"name": "Hacked"}).status_code == 404
    assert client.delete(f"/accounts/{acc_a.id}", headers=auth_headers_b).status_code == 404

    # User B attempts to access User A's transaction -> 404
    assert client.get(f"/transactions/{tx_a.id}", headers=auth_headers_b).status_code == 404
    assert client.put(f"/transactions/{tx_a.id}", headers=auth_headers_b, json={"description": "Hacked"}).status_code == 404
    assert client.delete(f"/transactions/{tx_a.id}", headers=auth_headers_b).status_code == 404

    # User B cannot transfer using User A's account
    acc_b = FinancialAccount(user_id=user_b.id, name="Beta Account", account_type="savings", is_reconciled=True)
    db_session.add(acc_b)
    db_session.commit()

    illegal_transfer = client.post(
        "/transactions/transfer",
        headers=auth_headers_b,
        json={
            "from_account_id": acc_a.id,  # User A's account!
            "to_account_id": acc_b.id,
            "date": "2026-06-15",
            "amount": "100.00",
        },
    )
    assert illegal_transfer.status_code == 404


# ---------------------------------------------------------------------------
# Statement Ingestion, Overlapping Statements & Analytics Tests
# ---------------------------------------------------------------------------

def test_statement_ingest_creates_normalized_transactions_and_updates_analytics(
    client, auth_headers_a, user_a, db_session
):
    # Upload CSV statement with legitimate identical intra-file transactions
    csv_content = (
        "Date,Description,Amount,Type\n"
        "2026-06-01,SALARY CREDIT,50000.00,credit\n"
        "2026-06-02,SWIGGY BANGALORE,250.00,debit\n"
        "2026-06-02,SWIGGY BANGALORE,250.00,debit\n"  # legitimate duplicate purchase on same day!
        "2026-06-05,BESCOM ELECTRICITY BILL,1200.00,debit\n"
    )
    file_obj = io.BytesIO(csv_content.encode("utf-8"))

    res = client.post(
        "/upload-statement",
        headers=auth_headers_a,
        files={"file": ("statement_june.csv", file_obj, "text/csv")},
    )
    assert res.status_code == 200

    # Verify transactions table was automatically populated!
    txs_res = client.get("/transactions", headers=auth_headers_a)
    assert txs_res.status_code == 200
    items = txs_res.json()["items"]
    # All 4 rows (including both legitimate Swiggy purchases) must exist!
    assert len(items) == 4
    swiggy_txs = [t for t in items if "SWIGGY" in t["description"]]
    assert len(swiggy_txs) == 2

    # Check analytics reflects normalized transactions
    insights_res = client.get("/insights", headers=auth_headers_a)
    assert insights_res.status_code == 200
    insights = insights_res.json()["analysis"]
    # Total food spend should be 250 + 250 = 500
    assert insights["category_totals"].get("Food") == 500.0

    # User corrects category of BESCOM from Bills to Other
    bescom_tx = [t for t in items if "BESCOM" in t["description"]][0]
    client.patch(
        f"/transactions/{bescom_tx['id']}/category",
        headers=auth_headers_a,
        json={"category_name": "Entertainment"},
    )

    # Verify insights immediately reflects the category correction!
    updated_insights = client.get("/insights", headers=auth_headers_a).json()["analysis"]
    assert updated_insights["category_totals"].get("Entertainment") == 1200.0
    assert "Bills" not in updated_insights["category_totals"]


def test_overlapping_statement_duplicate_exclusion(client, auth_headers_a, user_a, db_session):
    # Upload Statement 1 (Jan 1 - Jan 15)
    csv1 = (
        "Date,Description,Amount,Type\n"
        "2026-01-05,RENT PAYMENT,15000.00,debit\n"
        "2026-01-10,STARBUCKS COFFEE,350.00,debit\n"
    )
    res1 = client.post(
        "/upload-statement",
        headers=auth_headers_a,
        files={"file": ("stmt1.csv", io.BytesIO(csv1.encode("utf-8")), "text/csv")},
    )
    assert res1.status_code == 200

    # Upload Statement 2 with overlapping transaction on 2026-01-10 and a new transaction on 2026-01-20
    csv2 = (
        "Date,Description,Amount,Type\n"
        "2026-01-10,STARBUCKS COFFEE,350.00,debit\n"  # duplicate of Statement 1!
        "2026-01-20,ZOMATO DINNER,800.00,debit\n"
    )
    res2 = client.post(
        "/upload-statement",
        headers=auth_headers_a,
        files={"file": ("stmt2.csv", io.BytesIO(csv2.encode("utf-8")), "text/csv")},
    )
    assert res2.status_code == 200

    # Check analytics: Starbucks (350) should NOT be double counted!
    # Total spend should be Rent (15000) + Starbucks (350) + Zomato (800) = 16150
    insights = client.get("/insights", headers=auth_headers_a).json()["analysis"]
    rent_spend = insights["category_totals"].get("Rent", 0)
    food_spend = insights["category_totals"].get("Food", 0)
    assert rent_spend == 15000.0
    assert food_spend == 1150.0  # 350 + 800 (NOT 350 + 350 + 800!)
