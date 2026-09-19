# FortnaPlus Native Table Resolution

**Status:** Binding for machine-scoped ASC views  
**Branch:** `feature/plc2-transport-fidelity`  
**Native default:** `merge_table_rows(..., mode="native_shadow")`

---

## GATE 1 — Native ASC shadow precedence

FortnaPlus `amenu.c` `get_one_amenu` / `get_one_select` open order:

1. `Table.rom.<MACHINE>`
2. `Table.rom`
3. `Table.asc.<MACHINE>`
4. `Table.asc`

For ASC decode fidelity:

| Condition | Active rows | `source_scope` |
|-----------|-------------|----------------|
| `Table.asc.<MACHINE>` exists (non-empty) | **overlay only** | `machine_overlay` |
| no overlay | base `Table.asc` only | `base` |

**Do not** merge identities that are absent from an existing machine overlay
(`base_fallback` is not native behavior).

Optional same-identity field fill from base into empty overlay fields remains
allowed and is marked `provenance=RUN_DERIVED_HIGH_CONFIDENCE` (already
documented). That is field fill, not row import.

### Modes

| Mode | Behavior |
|------|----------|
| `native_shadow` (**default**) | Overlay shadows base; no absent-identity import |
| `legacy_union` (explicit opt-in) | Overlay wins collisions; base supplies absent identities as `base_fallback` |

API: `fortna_site_model.merge_table_rows(fortna, basename, machine, mode=...)`.

Tests: `tools/scripts/test_fortna_asc_native_shadow.py`.

---

## GATE 2 — Canonical resolver

Use these as the machine-scoped ASC API:

- `fortna_fortna_table_resolver.resolve_active_asc(fortna_dir, table_stem, machine)`
  → `{path, kind, rows, headers, fingerprint, merged_rows, ...}`
- `fortna_fortna_table_resolver.iter_active_tables(run_dir, machine)`
  → yields active tables including overlay-only `Table.asc.<MACHINE>`
- `fortna_asc.iter_asc_tables(run_dir, machine=...)` — optional machine arg
  discovers overlays with native shadow selection

Migrated to native default:

- `fortna_estop_model` → `resolve_active_asc`
- `fortna_run_workspace_discover` → `merge_table_rows` (native default)

### Paths that still bypass the resolver

Full grep-backed inventory: `exports/stabilization/fortnaplus_native_resolution.json`
→ `bypass_loaders.paths` (via `bypass_loaders_report()`). Snapshot count: **51**.

Notable bypasses (not exhaustive):

```
tools/scripts/apply_recipe.py
tools/diagnostics/diagnose_plc2_topology_merges.py
tools/scripts/fortna_autogen.py
tools/scripts/fortna_build_table_knowledge.py
tools/scripts/fortna_controller_scope.py
tools/scripts/fortna_conveyor_section_model.py
tools/scripts/fortna_cp2_completion_gate.py
tools/scripts/fortna_cp2_demo_closure.py
tools/scripts/fortna_cp2_ownership.py
tools/scripts/fortna_cp4_discovery.py
tools/diagnostics/fortna_cp4_pass1_self_audit.py
tools/scripts/fortna_io_extract.py
tools/scripts/fortna_mnu_runtime.py
tools/scripts/fortna_mnu_schema.py
tools/scripts/fortna_run_loader.py
tools/scripts/fortna_plc2_io_truth.py
```

Common patterns:

- Direct `read_asc(FORTNA/Table.asc)` without machine overlay
- `glob("*.asc*")` / `glob("Table.asc*")` concatenating overlays
- CP2 `resolve_physical_table_file` / archaeology `resolve_asc_path` (file pick
  only; not site-model merge)
- Autogen / CP4 discovery loaders that still open base Conveyor.asc alone

---

## GATE 3 — Schema IR

`fortna_schema_ir.build_schema_ir(run_dir)` parses:

- `RUN/FORTNA/fortna.mnu` (required when present)
- `RUN/PROJECT/project.mnu` (optional)

**Does not** glob `fortna (1).mnu` copies. If RUN lacks `fortna.mnu`, falls back
once to the tools-knowledge canonical path
(`workspace/_virgin_orindy/RUN/FORTNA/fortna.mnu`).

IR fields per selection column:

`table`, `field`, `datatype`, `datatype_name` (`SELECTION` / `SELECTION_UNIQUE`),
`target_table`, plus schema `fingerprint`.

---

## GATE 4 — MachineClosure

`fortna_machine_closure.build_machine_closure(run_dir, machine)`:

1. Start from `Machine` / target machine
2. Seed conveyors bound by `Conveyor.Machine_Name` and merges by `MergeBoss.Owner`
3. Walk schema edges over **active** tables (native resolver):
   `EStop.Part→Conveyor`, `MergeInputs`, `MergeRoute`, `Mtrchain`, `SawLane`, …

Each member:

```text
source_table, source_file, row_index, machine,
relationship_path, provenance, source_id
```

---

## GATE 5 — P406 contamination boundary

Fixture (ORINDYAC6):

- `Table.asc` → `{P136, P406, P600}`
- `Table.asc.ORINDYAC6` → `{P600}`

| Mode | Active set | P406? |
|------|------------|-------|
| `legacy_union` | `{P136, P406, P600}` | **yes** via `base_fallback` |
| `native_shadow` | `{P600}` | **no** |

**First contamination boundary:** `fortna_site_model.merge_table_rows` when
`mode="legacy_union"` (or any caller that unions base into an existing overlay).

Tests: `tools/scripts/test_fortna_p406_contamination.py`  
Export: `exports/stabilization/fortnaplus_native_resolution.json`

---

## GATE 6–7 — Native 2→1 merge vs Sawtooth

Ordinary merges come from `MergeBoss` → `MergeInputs` → `MergeRoute`
(`fortna_plc2_merge_discovery.discover_plc2_merges`). Geometry may validate but
must not override explicit Fortna relationships.

Sawtooth (`SawMerge` / `SawLane`) stays a separate pack — ordinary 2→1 merges
never imply `Sawtooth_Merge` inclusion.

ORINDYAC6 RUN-derived 600-series merge (finished PLC not consulted):

```text
MergeBoss:2-1 SERVO (Owner=ORINDYAC6)
  → MergeInputs LANE P542 CP6 / LANE P644 …
  → discharge P600
```

---

## GATE 8 — EStop.Part ownership ≠ Safety zone membership

`EStop.Part` is `SELECTION_UNIQUE → Conveyor`. Resolve Part through the
canonical resolver / MachineClosure to prove **machine ownership**.

- Device ownership: `PROVEN` when Part→Conveyor binds to target machine
- Zone membership: `REVIEW_REQUIRED` until engineer Assign+Apply
- Do **not** mint operational `{machine}_ESZone1` / `{Area}_ESZone1`
- Jamzones / Areas / Default Safety are not operational ES zones

---

## GATE 9 — Generation closure + provenance why

Generated site-specific PLC artifacts must trace to MachineClosure **or** an
explicit engineer decision whose parents do. Orphans are
`orphan_site_specific_artifact` (ERROR/REVIEW).

`fortna_autogen_provenance.py why --query P600_Merge` returns the Fortna
relationship path (native merge + MachineClosure).

---

## GATE 10 — StringFamily Decorated DATA

Studio-exported known-good L5X uses the **parent StringFamily type name** on
Decorated `DATA` (`String_20`, `Barcode_String`), even though DataTypeDef
declares `DATA` as `SINT[N]`. Serializer matches Studio export; do not
tag-name patch individual CP6 tags.

---

## Related

- `docs/FORTNAPLUS_MNU_RUNTIME.md` — ASC open order evidence
- `docs/RUN_TABLE_PRECEDENCE.md` — historical union notes (legacy_union)
- `docs/RUN_EVIDENCE_AUTHORITY.md`
