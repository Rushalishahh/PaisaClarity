# Production Alembic Migrations Transition Plan

This document outlines the safe, step-by-step procedure for transitioning PaisaClarity's production database (Supabase PostgreSQL) to an Alembic-only migration workflow, deprecating automatic table creation (`Base.metadata.create_all`).

---

## 1. Context & Motivation

Historically, PaisaClarity executed `Base.metadata.create_all(bind=engine)` inside the FastAPI lifespan startup hook. While convenient in early development, runtime `create_all()` has significant drawbacks in production:
- It creates missing tables, but **never** modifies existing columns, alters types, adds foreign keys, or handles column drops.
- Multiple web workers or rolling dyno deployments on Render can run concurrent DDL statements, risking lock contention.
- In Phase 7, table auto-creation was gated behind `AUTO_CREATE_TABLES` (default `true`). Setting `AUTO_CREATE_TABLES=false` ensures that database schema evolution is exclusively managed by versioned Alembic migrations.

---

## 2. Step 1: Pre-Flight Verification & Backup (MANDATORY)

Before running any migration commands against production:

1. **Create a Full Database Backup**:
   - In the **Supabase Dashboard**: Navigate to **Project Settings $\rightarrow$ Database $\rightarrow$ Backups** and trigger a manual backup snapshot.
   - Or via `pg_dump` CLI:
     ```bash
     pg_dump "$DATABASE_URL" -F c -b -v -f "paisaclarity_pre_alembic_backup_$(date +%Y%m%d_%H%M%S).dump"
     ```
2. **Verify Schema Drift Locally First**:
   - Our drift check on a fresh database confirmed that applying all 4 migrations (`525414a64ddd` $\rightarrow$ `a80c775079b1` $\rightarrow$ `70eb4e4a3876` $\rightarrow$ `c3f9a1d2b7e4`) matches SQLAlchemy's `Base.metadata` with **zero schema drift**.

---

## 3. Step 2: Determine Current Production Database State

Connect to the production database via `psql` or the Supabase SQL Editor and check if the `alembic_version` table exists and what revision it holds:

```sql
-- Check if alembic_version table exists
SELECT EXISTS (
    SELECT 1 FROM information_schema.tables 
    WHERE table_name = 'alembic_version'
);

-- If it exists, inspect the recorded version
SELECT version_num FROM alembic_version;

-- Check which tables are already present in the public schema
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
```

---

## 4. Step 3: Choose the Transition Path

Depending on the output from Step 2, choose either **Path A** or **Path B**:

### Path A: Tables exist in production, but `alembic_version` is missing or out of sync (`stamp head`)
If `users`, `statements`, and `investments` already exist in production because `create_all` created them, running `alembic upgrade head` would fail with `relation "users" already exists`.
- **Appropriate Action**: Stamp the existing schema without executing DDL:
  ```bash
  # Marks the database as being at the latest migration (c3f9a1d2b7e4)
  alembic stamp head
  ```
- **When to use**: Whenever production schema matches the models, but Alembic tracking metadata was never initialized.

### Path B: Fresh or partially migrated database (`upgrade head`)
If `alembic_version` is present and points to an earlier revision (e.g. `70eb4e4a3876`), or if targeting a brand new database:
- **Appropriate Action**: Execute pending migration scripts:
  ```bash
  alembic upgrade head
  ```
- **When to use**: Whenever pending migration steps need to execute real DDL (e.g., adding `start_date` to `investments`).

---

## 5. Step 4: Confirm Schema & Model Alignment (No Drift)

After stamping or upgrading, run Alembic's autogenerate comparison against the target database into a dry-run check to confirm that the database matches the code models completely:

```bash
alembic check
```
*(Or generate a dry-run diff: `alembic revision --autogenerate -m "drift_check"`; inspect the file to ensure the `upgrade()` body is empty, then delete the dry-run file).*

---

## 6. Step 5: Rollback Procedure

If a migration fails or causes unexpected downtime:
1. **Alembic Downgrade**:
   Every migration in `backend/alembic/versions/` implements a reversible `downgrade()` function:
   ```bash
   # Revert the most recent migration
   alembic downgrade -1

   # Or revert to a specific revision
   alembic downgrade <previous_revision_id>
   ```
2. **Database Snapshot Restore**:
   If schema corruption or data loss occurs, restore the snapshot created in Step 1:
   - In Supabase: Restore snapshot from **Database $\rightarrow$ Backups**.
   - Or via `pg_restore`:
     ```bash
     pg_restore -d "$DATABASE_URL" -c -v "paisaclarity_pre_alembic_backup.dump"
     ```
3. **Emergency Fallback**:
   Temporarily re-enable `AUTO_CREATE_TABLES=true` on Render until the issue is investigated.

---

## 7. Step 6: Order of Operations on Render

To switch production to Alembic-only without downtime, choose the execution method that fits your Render hosting plan:

### Migration Execution Options

#### Option A: Run Locally Against Production (Recommended for Free Tier)
Because Render's native "Pre-Deploy Command" is a paid-tier feature, running migrations from a secure local terminal against Supabase is the safest, most controllable free-tier approach:
1. Ensure you have taken a full backup in Supabase (**Database $\rightarrow$ Backups**).
2. Set your production `DATABASE_URL` in a temporary, local-only terminal session (never commit it):
   ```bash
   cd backend
   # Windows PowerShell:
   $env:DATABASE_URL="postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres"
   alembic stamp head   # or `alembic upgrade head` if applying pending migrations
   $env:DATABASE_URL=""
   ```
3. Test readiness probe: `https://paisa-clarity-api.onrender.com/health/ready`.

#### Option B: Chain into Render Build Command (Free-Tier Compatible)
Render's **Build Command** runs on every deploy across all tiers (including Free):
1. In **Render Dashboard $\rightarrow$ Settings $\rightarrow$ Build & Deploy**:
2. Update **Build Command** to:
   ```bash
   pip install -r backend/requirements.txt && cd backend && alembic upgrade head
   ```
   *Note: This runs during image build before the new service instance boots.*

#### Option C: Native Pre-Deploy Command (Render Paid Plans Only)
> **Note**: Render Pre-Deploy commands are **only available on paid instance types** (Starter, Standard, Pro). If you are on the Render Free Tier, this option is disabled in your dashboard.
1. In **Render Dashboard $\rightarrow$ Settings $\rightarrow$ Build & Deploy**:
2. Set **Pre-Deploy Command** to:
   ```bash
   cd backend && alembic upgrade head
   ```

---

### Final Step: Disable Runtime DDL on Render
Once the database schema is confirmed up to date and tracked by Alembic:
1. In **Render Dashboard $\rightarrow$ Environment**:
   Add or update:
   ```
   AUTO_CREATE_TABLES=false
   ```
2. Deploy the service. The backend boots cleanly without running DDL at startup.
