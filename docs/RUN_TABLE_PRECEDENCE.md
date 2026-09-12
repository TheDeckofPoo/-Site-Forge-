# RUN Table Precedence

**Status:** Binding for discovery / site model  
**Branch:** `feature/run-driven-workspace`  
**Finished PLC:** never used

---

## Problem

FortnaPlus RUN trees often contain both:

| Path pattern | Role |
|--------------|------|
| `FORTNA/Table.asc` | Base / shared table |
| `FORTNA/Table.asc.<CONTROLLER>` | Controller-scoped overlay (e.g. `.ORNCCP4`) |

Blindly concatenating duplicates creates stale/superseded equipment and wrong I/O.

---

## Precedence rules

1. **Controller overlay wins for identity collisions** when discovering for that controller.  
   Same logical row key (typically `Name` / `IO_Name`) → use overlay values; record `source_scope=controller_overlay`.

2. **Base table supplies rows absent from overlay** → `source_scope=base_fallback`.

3. **Overlay-only rows** → `source_scope=controller_overlay` (supplemental).

4. **Do not merge field-by-field from both** unless a field is empty in the winner and filled in the loser — and then mark `provenance=RUN_DERIVED_HIGH_CONFIDENCE` with both sources in `evidence[]`.

5. **Machine_Name / EIP word map** may further filter which overlay applies; they do not invent rows.

6. **`old.Table.asc*`** and similarly prefixed archives are **historical** by default → activity `HISTORICAL_OR_STALE` unless referenced by an active controller-scoped relationship.

---

## Logical row key

Prefer, in order:

1. Primary name column (`IO_Name`, `Name`, `Encoder Name`, …)
2. Else `(table, source_row_index)` for anonymous placeholders (`n/a`, `INVALID`)

Never use physical file order alone as identity.

---

## Discovery recording

Every SiteModel object must store:

```text
source_table      e.g. SawLane.asc
source_scope      controller_overlay | base_fallback | base_only | historical
source_row        1-based or key
```

---

## Tests

`test_run_driven_workspace.py` includes a synthetic precedence case:

- base defines device A and B  
- overlay redefines A and adds C  
- discovery for that controller → A from overlay, B from base, C from overlay  

---

## Related

- `docs/RUN_DISCOVERY_MODEL.md`
- `docs/SOURCE_OF_TRUTH_POLICY.md`
