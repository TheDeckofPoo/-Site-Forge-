# PostgreSQL Warehouse Health

Generated: 2026-09-21T07:05:22.502090+00:00

- Connection: **CONNECTED**
- Server: 18.6
- Database: `siteforge`
- Size: **103 MB**
- Alembic: `0003_dataset_roles`
- Archives complete: 72 (failed 1)
- Controllers: 63 · Projects: 33
- AI recorded cost: $0.00

## Counts

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

## Largest tables

| schema | table | est_rows | total | data | index |
| --- | --- | ---: | --- | --- | --- |
| evidence | configio_rows | 28278 | 37 MB | 34 MB | 3200 kB |
| evidence | io_claims | 57208 | 35 MB | 29 MB | 6128 kB |
| evidence | eipmodule_types | 5670 | 10 MB | 9944 kB | 712 kB |
| evidence | eipmodules | 2413 | 5024 kB | 4648 kB | 336 kB |
| corpus | source_files | 5141 | 2264 kB | 1608 kB | 616 kB |
| evidence | eipcfg_modules | 3089 | 2008 kB | 1568 kB | 400 kB |
| evidence | conflicts | 312 | 320 kB | 200 kB | 88 kB |
| evidence | eipcfg_adapters | 309 | 272 kB | 152 kB | 88 kB |
| evidence | eipadapters | 210 | 232 kB | 128 kB | 72 kB |
| evidence | adapter_bridges | 210 | 192 kB | 88 kB | 72 kB |
| learning | failure_events | -1 | 192 kB | 64 kB | 96 kB |
| evidence | machine_source_scopes | 148 | 144 kB | 48 kB | 64 kB |
| corpus | archives | 73 | 136 kB | 64 kB | 32 kB |
| corpus | controllers | 49 | 96 kB | 16 kB | 48 kB |
| learning | dialect_observations | 114 | 88 kB | 24 kB | 32 kB |
| learning | investigation_sessions | -1 | 80 kB | 8192 bytes | 16 kB |
| learning | unknown_clusters | -1 | 64 kB | 16 kB | 16 kB |
| learning | structural_signatures | -1 | 64 kB | 16 kB | 16 kB |
| learning | field_tests | -1 | 64 kB | 8192 bytes | 48 kB |
| corpus | projects | -1 | 48 kB | 8192 bytes | 32 kB |
| siteforge_meta | schema_info | -1 | 48 kB | 8192 bytes | 32 kB |
| learning | ai_investigations | -1 | 48 kB | 8192 bytes | 32 kB |
| learning | shadow_evaluations | -1 | 48 kB | 8192 bytes | 32 kB |
| learning | rule_coverage | -1 | 32 kB | 0 bytes | 24 kB |
| learning | rule_candidates | -1 | 32 kB | 8192 bytes | 16 kB |

## Dataset roles

- LEARNING: 59
- HOLDOUT: 9
- VALIDATION: 5