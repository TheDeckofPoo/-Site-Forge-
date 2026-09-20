# Corpus Warehouse V1 — Design Only

**Status:** design document only. Do **not** build the warehouse in this task.  
DuckDB / PyArrow / Pandas / Hypothesis / pytest / NetworkX are available on Curtis’s machine for the **next** task after CP8 independent proof closes.

## Goals

- Immutable, queryable inventory of FortnaPlus RUN evidence across many archives
- Separate **physical site / project** from **controller / machine** from **archive**
- Preserve provenance and evidence-purity class on every fact
- **No TAR contents in Git** — only hashes, paths, and derived tables under a local warehouse root

## Proposed immutable tables

| Table | Purpose |
|-------|---------|
| `archives` | SHA256, filename, class (RUN/COMM/UNKNOWN), size, discovered path |
| `controllers` | project, machine, archive_sha, role hints |
| `source_files` | path within archive, kind, machine_scope |
| `configio_rows` | word, bank, lohi, in_out, desc, interface, purpose, dialect |
| `eipmodules` | adapter, type, slot, input_bank, output_bank |
| `eipadapters` | name, target_ip |
| `eipcfg_adapters` | name, targetip, machine_scope |
| `eipcfg_modules` | adapter, slot, type, name |
| `hardware_types` | from EIPModuleType (sizes, banks flags) |
| `io_claims` | conveyor/device word+bit, io_name |
| `decoder_results` | claim → channel, assign_how, confidence (**CURRENT_DECODER_OUTPUT**) |
| `conflicts` | alias mismatches, type conflicts, bank collisions |
| `dialect_observations` | form, structural hash, counts |
| `rule_candidates` | DecoderRuleCandidate + purity status |
| `rule_coverage` | controller × rule cell status |
| `provenance_edges` | from_id → to_id, relation, evidence_class |

## Required columns on every fact row

- `archive_sha256`
- `project`
- `machine`
- `source_path`
- `source_row_index` (where applicable)
- `machine_scope` (`ACTIVE_MACHINE_SOURCE` / `SIBLING_MACHINE_SOURCE` / …)
- `evidence_class` (`RAW_RUN_EVIDENCE` / `INDEPENDENT_DERIVATION` / `CURRENT_DECODER_OUTPUT` / …)
- `extractor_version`

## Evidence-purity classes

See `tools/scripts/fortna_evidence_purity.py`.

**Hard rule:** `CURRENT_DECODER_OUTPUT` must never independently prove a rule about that same decoder behavior.

## Out of scope for V1 build (next task)

- Full extract/ingest pipeline
- GUI warehouse browser
- Automatic rule promotion from warehouse queries

## Local storage (not Git)

Suggested root: `workspace/corpus_warehouse/` (gitignored)  
Inputs: `SITEFORGE_CORPUS_ROOTS` / `config/local_corpus_roots.txt` / CLI `--roots`
