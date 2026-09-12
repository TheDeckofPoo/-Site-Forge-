# RUN Discovery Model (Canonical SiteModel)

**Status:** Binding for RUN-driven workspace foundation  
**Branch:** `feature/run-driven-workspace`  
**Source of truth:** Imported RUN + engineer overrides only — finished PLC never populates this model.

---

## Purpose

Produce a controller-scoped **canonical SiteModel** from a RUN tree so Transport, Sawtooth, Sorter (stub), and later generation gates share one inventory with explicit provenance, activity, and inclusion.

---

## SiteModel shape

```text
SiteModel
  machine_scope          # requested controller (e.g. ORNCCP4)
  controllers[]          # Machine.asc* inventory for the RUN
  areas[]                # RUN areas when reliable; else default Area_1
  equipment[]            # mechanical conveyors (P-tags)
  transport              # geometry + connection candidates (visual freeze: data only)
  motors[] / vfds[] / photoeyes[] / encoders[]
  estop_zones[]
  sawtooth_merges[]      # populated only when SawMerge/SawLane evidence exists
  sorters[]              # discovery stub only — generation NOT_SUPPORTED
  tracking_systems[] / wcs_interfaces[]
  relationships[]
  unresolved[]
```

Every first-class object carries:

| Field | Meaning |
|-------|---------|
| `canonical_id` | Stable id within this SiteModel (`kind:normalized_name`) |
| `source_table` | Logical table stem (e.g. `SawLane.asc`) |
| `source_row` | 1-based row or name key |
| `source_scope` | `controller_overlay` \| `base_fallback` \| `base_only` \| `historical` \| `engineer` |
| `raw_name` / `normalized_name` | As read / uppercased identity |
| `active_state` | See activity classifier |
| `inclusion` | `INCLUDED` \| `AVAILABLE` \| `EXCLUDED` |
| `confidence` | `HIGH` \| `MEDIUM` \| `LOW` \| `UNKNOWN` |
| `provenance` | `RUN_EXPLICIT` \| `RUN_DERIVED` \| `ENGINEER_CONFIGURED` \| `ENGINEER_CONFIGURED_REQUIRED` \| `UNKNOWN` |
| `evidence[]` | Structured facts supporting activity/inclusion |
| `engineer_override` | Optional override blob (null until set) |
| `generation_state` | `READY` \| `CONFIGURATION_REQUIRED` \| `NOT_SUPPORTED` \| `EXCLUDED` |
| `area_id` / `es_zone_id` | When known; otherwise null |

---

## Inclusion semantics

| Value | Meaning |
|-------|---------|
| **INCLUDED** | In machine scope, active enough for this workspace pass, and not overridden out |
| **AVAILABLE** | Present in RUN / related, but not selected for this controller build (other machine, candidate, etc.) |
| **EXCLUDED** | Inactive confirmed, historical/stale, or engineer-excluded |

Rules:

- Inactive / historical objects are **never** `INCLUDED`.
- Explicit RUN relationships (SawLane→conveyor, Mtrchain, PE/VFD ownership) beat P-number ordering.
- Engineer override, when present, wins over classifier defaults and must be recorded in `engineer_override` + evidence.

---

## Activity states

| State | Typical evidence |
|-------|------------------|
| `ACTIVE_CONFIRMED` | Controller overlay row + I/O / enable / ownership links |
| `ACTIVE_LIKELY` | Controller-scoped presence without full I/O proof |
| `INACTIVE_CONFIRMED` | Explicit offline / disabled / empty overlay replacing base |
| `HISTORICAL_OR_STALE` | `old.*` tables or superseded by overlay identity |
| `CANDIDATE` | Referenced weakly (geometry neighbor, numbering only) |
| `UNKNOWN` | Insufficient evidence |

Row order in ASC is **supporting** evidence only — never identity and never sole proof of activity.

---

## Default area

RUN trees in this program often lack a reliable Area table for the controller.

When no reliable area can be taken from RUN:

1. Create **`Area_1`**
2. Mark provenance **`ENGINEER_CONFIGURED_REQUIRED`**
3. Place **INCLUDED** equipment under `Area_1`
4. Do **not** claim `Area_1` came from RUN

---

## Sawtooth / Sorter / WCS

- **Sawtooth:** If `SawMerge` / `SawLane` (after table precedence) have active named rows → populate `sawtooth_merges[]` and `subsystems.json` sawtooth section from existing discovery helpers. No separate Discover button required.
- **Sorter:** If sorter tables have named rows → `sorters[]` discovery-only stubs with `generation_state=NOT_SUPPORTED` or `CONFIGURATION_REQUIRED`. Do not fake sorter PLC generation. Integrate `exports/sorter-research` when present.
- **Tracking / WCS:** Inventory only; `generation_state=NOT_SUPPORTED`.

---

## Engineer override + reimport

1. Overrides live beside the SiteModel (or embedded per-object `engineer_override`).
2. On RUN reimport, recompute discovery, then **re-apply** overrides by `canonical_id` / `normalized_name`.
3. Conflicts (override target missing after reimport) go to `unresolved[]` with `kind=override_orphan`.
4. Change report (`change_report.json`) diffs previous vs new SiteModel counts and identity sets.

---

## Forbidden

- Finished / reference PLC paths as discovery inputs
- Greensboro site hardcoding
- Inventing sorter or WCS generation
- Treating P-number order as topology or activity proof
- Claiming default `Area_1` is RUN-derived

---

## Related

- `docs/RUN_TABLE_PRECEDENCE.md`
- `docs/SOURCE_OF_TRUTH_POLICY.md`
- `tools/scripts/fortna_run_workspace_discover.py`
