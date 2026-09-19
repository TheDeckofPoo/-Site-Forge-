# Site Forge Qualification Runner

**Script:** `tools/scripts/fortna_qualification_runner.py`  
**Purpose:** Isolated virgin / replay / reference qualification of a Site Forge
build for one machine. Catches cross-subsystem handoff regressions (especially
Safety membership wiped by Sorter/Transport Apply) before field L5X import.

## Source-of-truth rules

| Input | Allowed? |
|-------|----------|
| RUN extract | Yes — discovery + generation |
| Engineer workbook (`safety_build`, `sorter_build`, transport) | Replay mode only |
| Approved generic libraries | Yes — Autogen |
| Reference / finished L5X | **Post-generation oracle only** |

Reference L5X is **never** read during discovery or generation.

## CLI

### Qualify

```bash
python tools/scripts/fortna_qualification_runner.py qualify \
  --run-dir <RUN> --machine <MACHINE> \
  [--project-workbook <json>] \
  [--reference-l5x <path>] \
  [--out <dir>] \
  [--mode virgin|replay|reference] \
  [--sanitized] \
  [--fail-on-review] \
  [--skip-generate]
```

### Compare two qualification dirs

```bash
python tools/scripts/fortna_qualification_runner.py compare \
  --a <qual_dir> --b <qual_dir> --out <dir>
```

## Modes

| Mode | Behavior |
|------|----------|
| **virgin** | Fresh temp workspace = copy of RUN + **empty** workbook. Discovery only; **does not invent Safety members**. Seeds native merges / sorter hints from RUN. |
| **replay** | Loads engineer workbook (`safety_build`, `sorter_build`, transport). Snapshots Safety after Apply and after Sorter Apply when present. |
| **reference** | Builds independently like virgin/replay, then compares generated L5X to `--reference-l5x` **after** generation only. |

Every qualify run copies the RUN into a temp workspace and writes a fresh
workbook. Prior site workbook state is never inherited.

## Handoff snapshots

Written to `handoff_snapshots.json`:

- `after_run_import`
- `machine_closure`
- `transport_model`
- `safety_before_apply`
- `safety_after_apply` (replay)
- `safety_after_sorter_apply` (replay + sorter_build)
- `sorter_model`
- `autogen_input_summary`
- `generation_manifest`

### CROSS_SUBSYSTEM_STATE_REGRESSION

If Safety operational members after Apply **> 0** and members presented to
Autogen **== 0** → **FAIL** (`CROSS_SUBSYSTEM_STATE_REGRESSION`).

This is the Safety × Sorter dual-state wipe class of field failure.

## Checks (PASS / REVIEW / FAIL)

| Subsystem | Notes |
|-----------|-------|
| Table resolution / machine closure | Native-shadow active tables + MachineClosure |
| Equipment inventory | Autogen conveyor count from RUN |
| Safety | Default/Unassigned operational refs = FAIL; membership persistence; virgin invent = FAIL |
| Transport | Native merge discovery summary |
| Sorter | Stale `P506` / `P508` / `P509` / `P510` tags in final L5X = FAIL unless RUN proves those hosts |
| Merge | Native P600-class proven merges vs presence in L5X |
| L5X structure + orphan scan | Studio structure + provenance orphan site-specific artifacts |
| Provenance coverage | Thin classification counts |

## Outputs

Default directory:

```text
exports/qualification/<site>/<timestamp>/
```

Artifacts:

- `qualification_report.md` — dashboard PASS/REVIEW/FAIL first
- `qualification_report.json`
- `provenance.json` (optional thin)
- `generation_manifest.json`
- `active_tables.json`
- `machine_closure.json`
- `handoff_snapshots.json`
- `final_artifact_validation.json`
- generated L5X under `generated/` when Autogen succeeds

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | PASS, or REVIEW when `--fail-on-review` is not set |
| 1 | FAIL (or compare detected regression) |
| 2 | REVIEW with `--fail-on-review` |

## Sanitized mode

`--sanitized` keeps counts / fingerprints / names / results only — no raw ASC
row dumps or L5X bodies in JSON artifacts.

## Pragmatic Autogen

When `tools/libraries/OReilly_Library_v3.L5X` is present, qualify calls native
`fortna_autogen.generate` after applying the workbook. Use `--skip-generate`
for discovery + handoff-only runs (fast CI / acceptance).

Virgin Autogen simulation: `load_from_run` + optional workbook JSON (empty in
virgin mode) — no Electron UI required.

## Examples

### Virgin ORINDYAC6 (discovery + handoffs)

```bash
python tools/scripts/fortna_qualification_runner.py qualify \
  --run-dir workspace/_virgin_orindy/RUN \
  --machine ORINDYAC6 \
  --mode virgin \
  --skip-generate \
  --sanitized
```

### Replay engineer workbook

```bash
python tools/scripts/fortna_qualification_runner.py qualify \
  --run-dir workspace/_virgin_orindy/RUN \
  --machine ORINDYAC6 \
  --mode replay \
  --project-workbook workspace/autogen_workbook.json \
  --out exports/qualification/ORINDYAC6/replay-check
```

### Reference oracle (after generate)

```bash
python tools/scripts/fortna_qualification_runner.py qualify \
  --run-dir workspace/_virgin_orindy/RUN \
  --machine ORINDYAC6 \
  --mode reference \
  --reference-l5x path/to/finished_oracle.L5X
```

### Compare two quals for Safety wipe

```bash
python tools/scripts/fortna_qualification_runner.py compare \
  --a exports/qualification/ORINDYAC6/run_a \
  --b exports/qualification/ORINDYAC6/run_b \
  --out exports/qualification/ORINDYAC6/compare_ab
```

## Tests

```bash
python -m unittest tests.acceptance.test_qualification_runner -v
```

Covers:

1. Virgin ORINDYAC6 produces report files
2. Compare detects Safety member regression between synthetic snapshots
3. Reference L5X is not read during discovery

## Integration map

| Concern | Module |
|---------|--------|
| Site discovery | `fortna_run_workspace_discover` / `fortna_sorter_discovery` |
| MachineClosure | `fortna_machine_closure` |
| Native merges | `fortna_plc2_merge_discovery` |
| Table mode | `fortna_site_model` `native_shadow` via `fortna_fortna_table_resolver` |
| Autogen | `fortna_autogen` (`load_from_run` / `generate`) + `fortna_workbook` |
| Provenance / orphans | `fortna_autogen_provenance` |
| L5X structure | `fortna_l5x_studio_structure` |
