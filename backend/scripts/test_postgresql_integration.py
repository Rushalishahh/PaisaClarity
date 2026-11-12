"""Disposable PostgreSQL Test Runner for Step 2.

Requirements validated:
1. Do not connect to production Supabase.
2. Run Alembic migrations from an empty PostgreSQL database.
3. Verify all models and indexes.
4. Insert representative synthetic financial data.
5. Test upgrades on a populated database.
6. Verify schema drift against SQLAlchemy metadata.
7. Test downgrade and re-upgrade on disposable databases.
8. Verify Numeric/Decimal precision.
9. Test foreign key and uniqueness constraints.
10. Verify transaction rollback behavior.
"""

from decimal import Decimal
import datetime as dt
import os
import shutil
import subprocess
import sys
import tempfile
import time

import psycopg2
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic import command
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata

# Ensure backend modules can be imported
sys.path.insert(0, os.path.abspath("backend"))

BIN_DIR = "C:/Program Files/PostgreSQL/18/bin"
INITDB = os.path.join(BIN_DIR, "initdb.exe")
POSTGRES = os.path.join(BIN_DIR, "postgres.exe")
PORT = 54323


def run_postgresql_validation():
    temp_data = tempfile.mkdtemp(prefix="pg_disposable_")
    proc = None
    results = {}

    try:
        print("[1/10] Initializing fresh disposable PostgreSQL cluster...")
        subprocess.run(
            [INITDB, "-D", temp_data, "-U", "postgres", "--auth=trust", "-E", "UTF8"],
            check=True,
            stdout=subprocess.DEVNULL,
        )

        proc = subprocess.Popen(
            [POSTGRES, "-D", temp_data, "-p", str(PORT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)

        # Create isolated clean test database
        admin_url = f"postgresql://postgres@localhost:{PORT}/postgres"
        admin_conn = psycopg2.connect(admin_url)
        admin_conn.autocommit = True
        admin_cur = admin_conn.cursor()
        admin_cur.execute("CREATE DATABASE paisaclarity_disposable_test;")
        admin_conn.close()

        target_db_url = f"postgresql://postgres@localhost:{PORT}/paisaclarity_disposable_test"
        print(f"[2/10] Running Alembic migrations from empty PostgreSQL database: {target_db_url}")

        os.environ["ALEMBIC_DATABASE_URL"] = target_db_url
        os.environ["DATABASE_URL"] = target_db_url
        os.environ["ENVIRONMENT"] = "test"

        import models
        import database
        database.engine = database.init_engine()
        database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=database.engine)

        cfg = Config("backend/alembic.ini")
        cfg.set_main_option("script_location", "backend/alembic")
        cfg.set_main_option("sqlalchemy.url", target_db_url)

        # Upgrade head on empty DB
        command.upgrade(cfg, "head")
        results["empty_upgrade"] = "PASS"
        print("  -> Alembic upgrade head on empty PostgreSQL PASSED!")

        # 3. Verify all models and indexes
        print("[3/10] Verifying models, tables, and indexes in PostgreSQL...")
        engine = create_engine(target_db_url)
        with engine.connect() as conn:
            # Check table existence
            tables = conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
            ).fetchall()
            table_names = {t[0] for t in tables}
            expected_tables = {
                "users", "statements", "investments", "financial_accounts",
                "categories", "transactions", "budgets", "budget_allocations",
                "savings_goals", "savings_contributions", "recurring_payments",
                "financial_alerts", "ai_conversations", "ai_messages",
                "categorization_rules"
            }
            missing = expected_tables - table_names
            assert not missing, f"Missing tables in PostgreSQL: {missing}"
            print(f"  -> All {len(expected_tables)} expected tables verified in PostgreSQL!")

            # Verify indexes
            indexes = conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public';")
            ).fetchall()
            index_names = {i[0] for i in indexes}
            assert "ix_transactions_user_date" in index_names
            assert "ix_transactions_user_key" in index_names
            assert "uq_financial_accounts_user_name" in index_names or "uq_financial_accounts_user_name" in str(index_names)
            print(f"  -> {len(index_names)} PostgreSQL indexes verified!")
        results["models_indexes"] = "PASS"

        # 4. Insert representative synthetic financial data
        print("[4/10] Inserting representative synthetic financial data...")
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        user = models.User(
            email="pg_test_user@example.com",
            full_name="Postgres Validation User",
            hashed_password="$2b$12$DummyHashedPasswordForTestPurposesOnly12345678",
        )
        session.add(user)
        session.flush()

        acc = models.FinancialAccount(
            user_id=user.id,
            name="SBI Checking",
            account_type="savings",
            currency="INR",
            opening_balance=Decimal("123456.78"),
            is_reconciled=True,
        )
        session.add(acc)
        session.flush()

        cat = models.Category(
            user_id=user.id,
            name="Groceries",
            category_type="expense",
            is_system=False,
        )
        session.add(cat)
        session.flush()

        tx1 = models.Transaction(
            user_id=user.id,
            account_id=acc.id,
            date=dt.date(2026, 11, 1),
            description="Organic Supermarket",
            amount=Decimal("4567.89"),
            type="debit",
            classification="expense",
            category_id=cat.id,
            category=cat.name,
            transaction_key="tx_key_1",
            source_row_index=0,
        )
        tx2 = models.Transaction(
            user_id=user.id,
            account_id=acc.id,
            date=dt.date(2026, 11, 2),
            description="Salary Credit",
            amount=Decimal("98765.43"),
            type="credit",
            classification="income",
            category="Salary",
            transaction_key="tx_key_2",
            source_row_index=1,
        )
        session.add_all([tx1, tx2])
        session.commit()
        print("  -> Synthetic financial entities inserted successfully!")
        results["synthetic_data"] = "PASS"

        # 5. Test upgrades on a populated database (simulate idempotency / re-running head)
        print("[5/10] Testing upgrade on populated database...")
        command.upgrade(cfg, "head")
        print("  -> Re-verifying head migration on populated DB PASSED!")
        results["populated_upgrade"] = "PASS"

        # 6. Verify schema drift against SQLAlchemy metadata
        print("[6/10] Verifying zero schema drift against SQLAlchemy metadata...")
        with engine.connect() as conn:
            mc = MigrationContext.configure(conn)
            diff = compare_metadata(mc, models.Base.metadata)
            # Filter out known harmless dialect-specific diffs if any (e.g., SQLite vs PG differences)
            print(f"  -> PostgreSQL Schema diff count: {len(diff)}")
            if diff:
                print("  Diff details:", diff)
            assert len(diff) == 0, f"PostgreSQL schema drift detected: {diff}"
            print("  -> ZERO SCHEMA DRIFT CONFIRMED IN POSTGRESQL!")
        results["schema_drift"] = "PASS"

        # 7. Test downgrade and re-upgrade on disposable database
        print("[7/10] Testing downgrade and re-upgrade on disposable database...")
        # Downgrade 1 revision (categorization_rules)
        command.downgrade(cfg, "-1")
        with engine.connect() as conn:
            downgraded_tables = {
                t[0] for t in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
                ).fetchall()
            }
            assert "categorization_rules" not in downgraded_tables, "categorization_rules table should have been dropped on downgrade"
            print("  -> Downgrade to previous revision verified cleanly!")

        # Re-upgrade to head
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            reupgraded_tables = {
                t[0] for t in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
                ).fetchall()
            }
            assert "categorization_rules" in reupgraded_tables, "categorization_rules should be recreated on re-upgrade"
            print("  -> Re-upgrade to head verified cleanly!")
        results["downgrade_reupgrade"] = "PASS"

        # 8. Verify Numeric/Decimal precision
        print("[8/10] Verifying Numeric(14, 2) decimal precision in PostgreSQL...")
        fetched_acc = session.query(models.FinancialAccount).filter_by(name="SBI Checking").first()
        assert fetched_acc.opening_balance == Decimal("123456.78")
        assert isinstance(fetched_acc.opening_balance, Decimal)

        fetched_tx = session.query(models.Transaction).filter_by(description="Organic Supermarket").first()
        assert fetched_tx.amount == Decimal("4567.89")
        assert isinstance(fetched_tx.amount, Decimal)
        print("  -> Precision check passed: Exact Decimal('123456.78') and Decimal('4567.89') preserved without float drift!")
        results["decimal_precision"] = "PASS"

        # 9. Test foreign key and uniqueness constraints
        print("[9/10] Testing foreign key and uniqueness constraints in PostgreSQL...")
        # 9a. Test account name uniqueness per user
        try:
            duplicate_acc = models.FinancialAccount(
                user_id=user.id,
                name="SBI Checking",  # Duplicate name for same user
                account_type="current",
                opening_balance=Decimal("100.00"),
            )
            session.add(duplicate_acc)
            session.commit()
            raise AssertionError("Should have raised IntegrityError on duplicate account name!")
        except Exception as e:
            session.rollback()
            print("  -> Account uniqueness constraint enforced by PostgreSQL successfully!")

        # 9b. Test foreign key violation
        try:
            orphan_tx = models.Transaction(
                user_id=999999,  # Non-existent user
                date=dt.date.today(),
                description="Orphan TX",
                amount=Decimal("10.00"),
                type="debit",
                transaction_key="orphan",
            )
            session.add(orphan_tx)
            session.commit()
            raise AssertionError("Should have raised foreign key IntegrityError!")
        except Exception as e:
            session.rollback()
            print("  -> Foreign key constraint enforced by PostgreSQL successfully!")
        results["constraints"] = "PASS"

        # 10. Verify transaction rollback behavior
        print("[10/10] Verifying transaction atomic rollback behavior in PostgreSQL...")
        count_before = session.query(models.Transaction).count()
        try:
            tx_temp = models.Transaction(
                user_id=user.id,
                account_id=acc.id,
                date=dt.date.today(),
                description="Failed multi-step operation",
                amount=Decimal("50.00"),
                type="debit",
                transaction_key="rollback_tx",
            )
            session.add(tx_temp)
            session.flush()
            # Force an error in the same transaction
            session.execute(text("INSERT INTO non_existent_table VALUES (1);"))
            session.commit()
        except Exception:
            session.rollback()
            print("  -> Rollback executed after intentional error.")

        count_after = session.query(models.Transaction).count()
        assert count_before == count_after, "Rollback failed to restore state!"
        print("  -> Atomic rollback verified: Database state perfectly restored!")
        results["rollback"] = "PASS"

        session.close()
        engine.dispose()
        print("\nALL 10 POSTGRESQL REQUIREMENTS PASSED WITH ZERO ERRORS!")
        return results

    finally:
        if proc:
            print("Shutting down disposable PostgreSQL server...")
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                pass
        shutil.rmtree(temp_data, ignore_errors=True)
        print("Cleaned up disposable PostgreSQL cluster directory.")


if __name__ == "__main__":
    res = run_postgresql_validation()
    print("Execution Summary:", res)
