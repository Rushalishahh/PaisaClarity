# PaisaClarity Production Database Migration & Deployment Runbook

**Date**: 2026-11-12  
**Target Environment**: Production (Supabase PostgreSQL / Render FastAPI Backend)  
**Status**: PREPARATION & STAGING RUNBOOK (DO NOT EXECUTE AGAINST PRODUCTION WITHOUT USER APPROVAL)

---

## 1. Safety Principles & Pre-Flight Rules

> [!CAUTION]
> **Zero Production Modification Without Explicit Authorization**:
> This runbook is a verified deployment procedure. No command in this document may be run against the live Supabase production database or production hosting instances without explicit user consent.

- **Non-Destructive Guarantee**: Never run `alembic downgrade` against a production database containing user data unless preceded by a verified cold snapshot. Alembic downgrades drop tables and columns destructively.
- **Credential Safety**: Never hardcode production database URLs or secrets in scripts, terminal history, or configuration files. Always pass `DATABASE_URL` via environment variables.
- **Connection Isolation**: Ensure that maintenance tasks use direct connection pooling or standard port 5432 / pooler port 6543 with SSL enforced (`sslmode=require`).

---

## 2. Step-by-Step Production Migration Procedure

### Phase 1: Pre-Migration Discovery & Inspection

#### 1. Identify Current Production Alembic Revision
Before applying any migration, query the current database state:
```bash
# Set production connection string in current shell session only
export DATABASE_URL="postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres?sslmode=require"
export ALEMBIC_DATABASE_URL="$DATABASE_URL"

# Inspect current applied revision
cd backend
python -m alembic current
```
Expected output:
- If unmigrated: `(empty)` or initial revision.
- If migrated up to Phase 11: `b2c3d4e5f6a7 (head)` or earlier revision identifier.

#### 2. Inspect Target Heads and Pending Revisions
```bash
# Check Alembic revision tree
python -m alembic heads

# View pending migrations history
python -m alembic history --verbose
```

---

### Phase 2: Production Backup & Verification

#### 3. Create Full Production Database Backup
Before initiating any schema modifications or backfills:
```bash
# Create custom-format compressed binary dump
pg_dump "$DATABASE_URL" \
  --format=custom \
  --compress=9 \
  --blobs \
  --verbose \
  --file="paisaclarity_pre_phase13_backup_$(date +%Y%m%d_%H%M%S).dump"

# Also create a schema-only plain SQL dump for quick diff inspection
pg_dump "$DATABASE_URL" \
  --schema-only \
  --no-owner \
  --file="paisaclarity_pre_phase13_schema_$(date +%Y%m%d_%H%M%S).sql"
```

#### 4. Verify Backup Integrity
Verify the dump archive is non-empty and readable:
```bash
# List archive contents to confirm table definitions are present
pg_restore --list paisaclarity_pre_phase13_backup_*.dump | grep -E "TABLE DATA|TABLE"

# Confirm file size is greater than 0
ls -lh paisaclarity_pre_phase13_backup_*.dump
```

---

### Phase 3: Executing Database Migrations

#### 5. Apply Alembic Upgrade to Head
Run migrations in transactional mode:
```bash
cd backend
python -m alembic upgrade head
```
Expected output:
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
...
INFO  [alembic.runtime.migration] Running upgrade -> head
```

#### 6. Confirm Applied Schema Version
```bash
python -m alembic current
```
Must display the target head revision `b2c3d4e5f6a7` (or latest head).

---

### Phase 4: Historical Statement Backfill (If Needed)

#### 7. Execute Historical Statements Backfill
If pre-existing uploaded statements exist in the `statements` table that have not yet been normalized into the `transactions` table:
```bash
# Dry run verification first (if supported) or execute backfill script:
python scripts/backfill_historical_accounts.py
```
*Note*: The backfill script is idempotent. It uses `source_statement_id` and `source_row_index` to guarantee zero double-counting on repeated executions.

---

### Phase 5: Post-Migration Data Integrity Verification

#### 8. Verify Record Counts Across All Entities
Execute the following verification query using `psql` or Supabase SQL Editor:
```sql
SELECT 'users' AS table_name, count(*) AS count FROM users
UNION ALL
SELECT 'statements', count(*) FROM statements
UNION ALL
SELECT 'financial_accounts', count(*) FROM financial_accounts
UNION ALL
SELECT 'categories', count(*) FROM categories
UNION ALL
SELECT 'transactions', count(*) FROM transactions
UNION ALL
SELECT 'budgets', count(*) FROM budgets
UNION ALL
SELECT 'savings_goals', count(*) FROM savings_goals
UNION ALL
SELECT 'recurring_payments', count(*) FROM recurring_payments
UNION ALL
SELECT 'financial_alerts', count(*) FROM financial_alerts
UNION ALL
SELECT 'ai_conversations', count(*) FROM ai_conversations;
```

#### 9. Detect Duplicate Transactions
Verify that no duplicate statement ingestion occurred:
```sql
SELECT 
    source_statement_id, 
    source_row_index, 
    count(*) 
FROM transactions 
WHERE source_statement_id IS NOT NULL 
GROUP BY source_statement_id, source_row_index 
HAVING count(*) > 1;
```
*Expected result*: `0 rows returned`.

#### 10. Validate Account Balances & Net Worth Isolation
Verify that placeholder accounts ("Imported Statements") do NOT leak into verified balances:
```sql
-- 1. Check verified accounts
SELECT id, name, account_type, calculated_balance, is_reconciled, is_archived
FROM financial_accounts
WHERE is_reconciled = true AND account_type != 'imported';

-- 2. Check unreconciled placeholder accounts (must be excluded from net worth)
SELECT id, name, account_type, calculated_balance, is_reconciled
FROM financial_accounts
WHERE account_type = 'imported' OR is_reconciled = false;
```

---

## 3. Safe Rollback Protocol

If migration or deployment encounters an unrecoverable failure:

### A. Application Rollback
1. In Render / Cloud hosting dashboard, redeploy the previous stable build commit (`97e42f6` or `51724f2`).
2. Set `AUTO_CREATE_TABLES=false`.

### B. Database Rollback
> [!WARNING]
> Do NOT simply issue `alembic downgrade -1` on a populated database with active users, as foreign key constraints or column removals will destroy data created post-migration.

1. **Option 1 (Zero Data Loss on Migration Failure)**:
   If the migration transaction aborted midway, PostgreSQL transactional DDL will have rolled back changes automatically.
2. **Option 2 (Restoration from Verified Cold Backup)**:
   ```bash
   # Restore clean pre-migration snapshot
   pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" \
     paisaclarity_pre_phase13_backup_*.dump
   ```
3. Verify restored status:
   ```bash
   python -m alembic current
   ```
