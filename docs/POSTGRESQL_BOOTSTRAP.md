# PostgreSQL Bootstrap (after server install)

**Do not commit passwords.** Curtis chooses the application password interactively.

Warehouse code reads **only** `SITEFORGE_DATABASE_URL` from the environment
(`tools/siteforge_warehouse/config.py`). Nothing in source or `alembic.ini` holds
credentials.

## 1. Create database and role

As a local PostgreSQL superuser (example using `psql`):

```sql
CREATE DATABASE siteforge;

CREATE ROLE siteforge_app LOGIN PASSWORD 'choose-a-strong-password-interactively';

GRANT CONNECT ON DATABASE siteforge TO siteforge_app;
```

Then connect to `siteforge` and grant schema rights after migrations create schemas,
or grant broadly for V1:

```sql
-- run while connected to database siteforge
GRANT USAGE, CREATE ON SCHEMA public TO siteforge_app;
-- After alembic upgrade head, also:
-- GRANT USAGE ON SCHEMA siteforge_meta, corpus, evidence, learning, qualification, app TO siteforge_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA siteforge_meta TO siteforge_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA corpus TO siteforge_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA evidence TO siteforge_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA learning TO siteforge_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA qualification TO siteforge_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO siteforge_app;
-- ALTER DEFAULT PRIVILEGES ...
```

Exact post-migration grants can be refined once schemas exist.

## 2. Configure local URL (gitignored)

PowerShell example for current session:

```powershell
$env:SITEFORGE_DATABASE_URL = "postgresql+psycopg://siteforge_app:YOUR_PASSWORD@localhost:5432/siteforge"
```

Or a local ignored `.env` — never commit `.env` or passwords.

Install Python deps if needed:

```powershell
pip install -r requirements-warehouse.txt
```

## 3. Migrate

From repo root:

```powershell
alembic -c alembic.ini upgrade head
```

This creates schemas `siteforge_meta`, `corpus`, `evidence`, `learning`,
`qualification`, `app` and Stage-1 tables (revision `0001_warehouse_v1`).

## 4. First sync

```powershell
python -m tools.siteforge_warehouse.cli status
python -m tools.siteforge_warehouse.cli sync --roots "<corpus-root>" --dry-run
```

Live ingest remains gated until `docs/POSTGRESQL_INTEGRATION_GATE.md` passes.
Dry-run staging and Parquet export work without PostgreSQL.

```powershell
python -m tools.siteforge_warehouse.cli export-parquet --out exports/learning/parquet
```

## Notes

- Runtime uses `siteforge_app`, not the postgres superuser.
- Raw customer TAR archives are never stored inside PostgreSQL as blobs; only
  SHA256 identity + normalized evidence rows.
- Archive identity is **SHA256 hex lowercase**.
- DuckDB is optional analytics only — not required for bootstrap.
