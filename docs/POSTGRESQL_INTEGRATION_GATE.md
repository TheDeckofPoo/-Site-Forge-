# PostgreSQL Integration Gate

**Status: PASS (local V1)**

| Field | Value |
|-------|-------|
| Date | 2026-09-20 |
| PostgreSQL | 18.6 |
| Alembic revision | `0001_warehouse_v1` |
| Extractor version | `warehouse_hw_io_v1.0.0` |
| Database | `siteforge` |
| Runtime role | `siteforge_app` |
| Credentials | local only (`config/local_database_url.txt` gitignored / env) — **never committed** |

## Checklist

| Step | Result |
|------|--------|
| psql version works | PASS (18.6) |
| PostgreSQL service running | PASS |
| siteforge database exists | PASS |
| siteforge_app role exists | PASS |
| SITEFORGE_DATABASE_URL configured locally | PASS (redacted) |
| alembic upgrade head | PASS |
| fixture ingest | PASS |
| idempotent UNCHANGED | PASS |
| --force REEXTRACTED | PASS |
| transaction rollback (injected failure) | PASS — no partial COMPLETE |
| current-site isolation | PASS |
| corpus-learning queries | PASS |
| full corpus sync | PASS — 65 INGESTED, 2 FAILED (non-RUN DATA) |
| Parquet export from live PG | PASS (archives/configio/eipmodules/io_claims; some JSON cols stringified) |
| DuckDB read snapshot | PASS (`archives.parquet` readable) |

## Live corpus counts (post-ingest)

| Table | Rows |
|-------|-----:|
| corpus.archives | 68 |
| archives COMPLETE | 67 |
| archives FAILED | 1 (injected rollback test) |
| evidence.configio_rows | 27,078 |
| evidence.io_claims | 52,251 |
| evidence.eipmodules | 2,312 |
| evidence.eipcfg_modules | 2,988 |
| evidence.eipmodule_types | 5,270 |
| evidence.adapter_bridges | 191 |
| evidence.conflicts | 312 |
| learning.dialect_observations | 102 |
| learning.rule_candidates | 3 |
| database size | ~87 MB |

## Rules seeded (METHOD, not site answers)

- `exact_adapter_ip_bridge` — PRODUCTION_RULE
- `direction_aware_bank_binding` — PRODUCTION_RULE
- `panel_catalog_numeric_alpha_low_a_slot` (CP8) — CANDIDATE_RULE (not promoted)

## Explicit non-claims

- CP8 physical High-half continuation is **not** PRODUCTION_RULE
- Cross-site warehouse rows are **not** current-site facts
- SQLite/in-memory tests remain UNIT_BACKEND_ONLY (separate from this gate)
- No cloud backup implemented — see `docs/CORPUS_WAREHOUSE_V1.md` pg_dump strategy

## Rollback / isolation evidence

| Test | Result |
|------|--------|
| Injected mid-archive write failure | ROLLBACK; archive not COMPLETE; no partial evidence rows |
| Current-site ATLA vs INDY | Zero cross-machine leakage via `CurrentSiteEvidenceRepository` |
| Archive without machine / machine without archive | Rejected by public interface |
| CorpusLearning cross-site dialects/hardware/rules | Allowed and verified |

## Corpus sync summary path

See `exports/learning/warehouse_live_sync_stdout.json` and CLI status output.

## Still not in V1

- Generic automated rule-coverage evaluator for all Stage-1 rules (UNKNOWN/NOT_EVALUATED OK)
- Cloud backup / continuous WAL archiving
- Arbitrary SQL console in production CLI
- Speculative index explosion (indexes follow V1 query needs in migration `0001`)
