# PostgreSQL Integration Gate

**Status:** `NOT_YET_EXECUTED` until Curtis installs/configures PostgreSQL Server.

This gate is **future acceptance**. Passing warehouse unit/dry-run tests offline
does **not** pass this gate.

Warehouse package: `tools/siteforge_warehouse/`  
Extractor: `warehouse_hw_io_v1.0.0`  
Migration: `0001_warehouse_v1` (`alembic -c alembic.ini upgrade head`)

## Prerequisites

1. `psql --version` works
2. PostgreSQL service running
3. Database `siteforge` exists
4. Role `siteforge_app` exists (not superuser for runtime)
5. Local (gitignored) `SITEFORGE_DATABASE_URL` configured, e.g.
   `postgresql+psycopg://siteforge_app:***@localhost:5432/siteforge`

See `docs/POSTGRESQL_BOOTSTRAP.md` for interactive setup (no committed passwords).

## Acceptance steps

| Step | Command / check | Required result |
|------|-----------------|-----------------|
| 1 | `psql --version` | Server client available |
| 2 | Service running | Accepts connections |
| 3 | DB + role | `siteforge` / `siteforge_app` |
| 4 | Env | `SITEFORGE_DATABASE_URL` set locally |
| 5 | `alembic -c alembic.ini upgrade head` | PASS (schemas + Stage-1 tables) |
| 6 | Sync small fixture | PASS |
| 7 | Transaction rollback test | Failed ingest leaves no COMPLETE archive |
| 8 | Current-site isolation test | Cross-site query impossible via CurrentSiteEvidenceRepository |
| 9 | Full corpus ingest | PASS |
| 10 | Parquet export | PASS |

## Explicit non-claims

- Offline SQLAlchemy/Alembic compile tests ≠ PostgreSQL integration PASS
- SQLite / in-memory unit backend (`UNIT_BACKEND_ONLY`) ≠ PostgreSQL qualification
- Dry-run sync ≠ warehouse populated
- DuckDB sidecar (if used) ≠ primary warehouse

## Contamination check (required with step 8)

- `CurrentSiteEvidenceRepository.get_*` raises `ValueError` without `archive_sha256` or `machine`
- Query for archive A never returns rows from archive B
- Learning aggregates never substitute for current-site evidence in UI/decoder paths

## After gate passes

Record:

- date
- PostgreSQL version
- alembic head revision
- corpus sync summary artifact path
