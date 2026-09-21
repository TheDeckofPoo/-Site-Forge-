# Corpus Coverage Report

Generated: 2026-09-21T07:05:22.795677+00:00

- Connection: **CONNECTED**
- Alembic: `0003_dataset_roles`
- Database size: **103 MB**
- Archives complete: 72 (failed 1)
- Controllers: 63 · Projects: 33
- Roles assigned: 73 (100.0%)

## Dataset roles

- LEARNING: 59
- VALIDATION: 5
- HOLDOUT: 9

## Learning-eligible (LEARNING + VALIDATION only)

_HOLDOUT may be stored but must not feed rule discovery / structural derivation / AI dossiers / counterexamples / decoder decisions / production promotion justification._

- `archives`: 63
- `controllers`: 55
- `projects`: 32
- `configio_rows`: 24878
- `io_claims`: 50519
- `eipmodules`: 2137

## Warehouse table counts

- `corpus.archives`: 73
- `corpus.controllers`: 72
- `corpus.projects`: 33
- `corpus.source_files`: 5141
- `evidence.configio_rows`: 28678
- `evidence.io_claims`: 58331
- `evidence.eipmodules`: 2525
- `evidence.eipcfg_modules`: 3155
- `evidence.adapter_bridges`: 220
- `learning.field_tests`: 4
- `learning.failure_events`: 50
- `learning.structural_signatures`: 3
- `learning.unknown_clusters`: 8
- `learning.rule_candidates`: 6
- `learning.shadow_evaluations`: 1
- `learning.ai_investigations`: 1
- `learning.investigation_sessions`: 1

## Rule candidates

- total: 6
- `PRODUCTION_RULE`: 2
- `CANDIDATE_RULE`: 2
- `INSUFFICIENT_EVIDENCE`: 1
- `CANDIDATE`: 1

## Unknown clusters

- total: 8

- `uc_43ab3f8a58fefbfb` count=304 pattern=43ab3f8a58fefbfb
- `uc_ab2919d27fa5eba3` count=24 pattern=ab2919d27fa5eba3
- `uc_733bd7aa18c6504e` count=22 pattern=733bd7aa18c6504e
- `uc_f1f0701bca989e07` count=22 pattern=f1f0701bca989e07
- `uc_762280a9326c29af` count=20 pattern=762280a9326c29af
- `uc_72fa9c67611b604e` count=14 pattern=72fa9c67611b604e
- `uc_63e4896f30bb6cee` count=6 pattern=63e4896f30bb6cee
- `uc_0b6c5b92ec048132` count=2 pattern=0b6c5b92ec048132

## I/O conservation summary (warehouse counts)

- learning_eligible_configio_rows: 24878
- learning_eligible_io_claims: 50519
- learning_eligible_eipmodules: 2137
- note: Warehouse row counts for LEARNING+VALIDATION only; not a per-site conservation ledger.

## Notes

Coverage uses warehouse table counts and dataset_role only. No invented purpose / dialect / activity semantic classes.
