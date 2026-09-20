# Corpus Warehouse V1 — PostgreSQL Primary

**Status:** Stage-1 foundation implemented under `tools/siteforge_warehouse/`.  
**Primary store:** PostgreSQL.  
**Optional sidecar:** DuckDB (analytics only; not required for ingest or current-site queries).

Offline / dry-run paths work with **no live PostgreSQL**. Live ingest is gated by
`docs/POSTGRESQL_INTEGRATION_GATE.md`.

## Architecture laws

1. **PostgreSQL is the primary persistent warehouse.** DuckDB may read exports or
   replicas later; it is never the system of record.
2. **No live PostgreSQL required for development.** Discovery, extract, validate,
   dry-run sync, and Parquet export run offline.
3. **CURRENT SITE EVIDENCE vs CROSS-SITE KNOWLEDGE isolation**
   - `CurrentSiteEvidenceRepository` — every method requires `archive_sha256` + `machine`.
   - `CorpusLearningRepository` — cross-corpus patterns only (dialects, clusters, rules).
   - Never answer a current-site UI/decoder question from cross-site aggregates alone.
4. **Archive SHA256 (lowercase hex) is primary archive identity.** Filenames are hints.
5. **No credentials in source.** `SITEFORGE_DATABASE_URL` from environment only.
6. **No production decoder changes.** Extractors must not call `PhysicalWordResolver`.
7. **Reuse** `fortna_asc`, `fortna_evidence_purity`, `fortna_machine_source_scope`, and
   `siteforge_learning` classifiers where possible.

## Package layout

| Path | Role |
|------|------|
| `tools/siteforge_warehouse/` | Warehouse package |
| `EXTRACTOR_VERSION` | `warehouse_hw_io_v1.0.0` |
| `config.py` | `SITEFORGE_DATABASE_URL`, corpus roots |
| `ids.py` | `fact_uid()` / archive SHA normalize |
| `models.py` | SQLAlchemy 2.x schemas |
| `repository.py` | Abstract interfaces + `WarehouseNotConfigured` |
| `postgres_repository.py` | Postgres + in-memory (`UNIT_BACKEND_ONLY`) |
| `staging.py` | `ArchiveEvidenceBundle` + `validate_bundle()` |
| `extract.py` | `build_bundle_from_run_dir()` |
| `sync.py` | discover / plan / dry-run |
| `parquet_export.py` | Staging → Parquet |
| `cli.py` | `sync`, `status`, `export-parquet` |
| `alembic/` | Migrations (`0001_warehouse_v1_foundation`) |

## Schemas

| Schema | Purpose |
|--------|---------|
| `siteforge_meta` | schema_info, extractor_versions, sync_runs |
| `corpus` | archives, projects, controllers, source_files |
| `evidence` | configio_rows, eipmodules, eipadapters, eipmodule_types, eipcfg_*, io_claims, conflicts, machine_source_scopes, adapter_bridges |
| `learning` | dialect_observations, unknown_clusters, rule_candidates, rule_coverage, rule_counterexamples, investigation_sessions, provenance_edges |
| `qualification` | qualification_runs, qualification_results |
| `app` | settings (GUI / session reserved) |

## Birth-certificate columns (every evidence fact)

- `archive_sha256`
- `project`
- `machine`
- `source_path`
- `source_row_index`
- `machine_scope` (`ACTIVE_MACHINE_SOURCE` / `SIBLING_MACHINE_SOURCE` / …)
- `evidence_class` (`RAW_RUN_EVIDENCE` / `INDEPENDENT_DERIVATION` / `CURRENT_DECODER_OUTPUT` / …)
- `extractor_version`

Raw table rows are labeled **`RAW_RUN_EVIDENCE`**.  
Purpose / dialect annotations are **`INDEPENDENT_DERIVATION`**.  
`CURRENT_DECODER_OUTPUT` must never independently prove a rule about that decoder
(see `tools/scripts/fortna_evidence_purity.py`).

## Contamination boundaries

```
┌────────────────────────────┐     ┌─────────────────────────────┐
│ CurrentSiteEvidenceRepo    │     │ CorpusLearningRepository    │
│ archive_sha256 + machine   │     │ cross-corpus patterns       │
│ configio / eip / claims /  │     │ dialects / clusters / rules │
│ source_files               │     │ hardware catalog counts     │
└────────────▲───────────────┘     └──────────────▲──────────────┘
             │                                    │
             │ never merge                        │ never substitute
             │ into learning proof                │ for site evidence
             │ without purity gate                │
```

- In-memory unit backends (`UNIT_BACKEND_ONLY`) must filter by archive+machine and
  never return other archives’ rows.
- CP8 seed (`seed_cp8_candidate_status()`) is **CANDIDATE_RULE only** — never
  auto-promoted to production.

## CLI (offline-capable)

```powershell
python -m tools.siteforge_warehouse.cli status
python -m tools.siteforge_warehouse.cli sync --roots "<corpus-root>" --dry-run
python -m tools.siteforge_warehouse.cli export-parquet --out exports/learning/parquet
```

Corpus roots resolve from (merged):

1. `--roots`
2. `SITEFORGE_CORPUS_ROOTS` (`os.pathsep`-separated)
3. `config/local_corpus_roots.txt` (gitignored)

Supports `*.tar.gz` and RUN directories with `project.cfg`. Existing extracts under
`exports/learning/_extract` and workspace peeks are usable as RUN dirs.

## Local storage (not Git)

- Warehouse DB dumps: `*.dump` (gitignored)
- Suggested local root: `workspace/corpus_warehouse/` (gitignored)
- Parquet exports: `exports/learning/parquet/*.parquet` (gitignored; keep `.gitkeep`)
- `config/local_database_url.txt` (gitignored; password)

## Backup / rebuild philosophy (V1)

| Layer | Role | Rebuildable? |
|-------|------|--------------|
| **RAW TAR corpus** | Source evidence (authority for physical bytes) | N/A — preserve originals |
| **PostgreSQL normalized evidence** | Archives, Configio, EIP*, I/O claims, scopes, conflicts | **Yes** — regenerate from TAR + extractor |
| **Human-approved engineering knowledge** | Approved rule metadata, engineer assignments, investigation decisions | **No** — backup separately |

PostgreSQL is a **rebuildable normalized warehouse + accumulated approved knowledge**,
not a substitute for the TAR corpus. Do **not** store raw TAR blobs in PostgreSQL.

### V1 `pg_dump` strategy (local only; no cloud backup in this task)

```powershell
# Logical dump (credentials via env / prompt — never commit)
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -U siteforge_app -d siteforge -F c -f workspace/corpus_warehouse/siteforge_YYYYMMDD.dump
```

Recommended cadence for V1 local work:

1. After first successful full corpus ingest
2. After seeding / approving rule metadata
3. Before destructive schema experiments

Restore is a rebuild aid — RAW TARs remain the evidence authority for normalized rows.
Cloud / off-box backup is **out of scope** for V1.

Parquet exports are **analytics snapshots**, not authority.

## Dependencies

See `requirements-warehouse.txt` (repo has no root `requirements.txt`):

- `psycopg[binary]>=3.3`, `SQLAlchemy>=2.0`, `Alembic>=1.20`
- `pyarrow`, `pandas`, `hypothesis`, `pytest`, `networkx`
- `duckdb` optional (commented)

## Related docs

- `docs/POSTGRESQL_BOOTSTRAP.md` — interactive DB/role setup (no passwords committed)
- `docs/POSTGRESQL_INTEGRATION_GATE.md` — live PostgreSQL acceptance checklist
