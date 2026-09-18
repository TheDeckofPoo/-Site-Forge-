# FortnaPlus Object Taxonomy (Gate B)

**Branch:** `feature/plc2-transport-fidelity`  
**Machine-readable twin:** [`config/program_packs/fortnaplus_object_taxonomy.json`](../../config/program_packs/fortnaplus_object_taxonomy.json)  
**Status:** Documentation / contract only — no CP1–CP4 production code changes.

Finished / gold PLCs are **validation oracles only**.

---

## Purpose

Prove the taxonomy of **referenceable FortnaPlus objects**: anything a `SELECTION` / `SELECTION_UNIQUE` field may legally point at via `fortna.mnu` DLIST → `find_data_source()` → CP3 resolver → CP2 typed RUN records.

This taxonomy is the vocabulary for LogicalSignalModel, StartStopModel, JamZoneModel, and FortnaEngineeringGraph (Gate H).

---

## Provenance chain (do not skip)

```
fortna.mnu / project.mnu
    → CP1 schema metadata (DLIST / dataselect)
    → find_data_source()          [SOURCE_PROVEN]
    → CP2 typed RUN records
    → CP3 reference graph         [selection identity lookup]
    → RUN ASC tables
```

Evidence used:

| Source | Role |
|--------|------|
| `workspace/*/RUN/FORTNA/fortna.mnu` | Menu definitions + DLIST targets |
| `artifacts/mnu-relationships.json` | Forward DLIST inventory |
| `artifacts/mnu-schema.json` | Field-level DLIST for Jamzones / Conveyor / … |
| `tools/scripts/fortna_reference_resolver.py` | CP3 resolution + unresolved taxonomy |
| `artifacts/fortna-reference-graph-plc{2,4,5}.json` | Resolved edges (validation RUN examples) |
| `artifacts/fortna-run-typed-records.json` | CP2 typed records |
| RUN ASC: `Conveyor`, `Jamzones`, `StartStopZones`, `Mtrchain`, `timemenu`, … | Physical schema |
| [`LOGICAL_SIGNAL_MODEL.md`](LOGICAL_SIGNAL_MODEL.md) | Curtis clarification on logical refs |

---

## Critical INVALID semantics (two meanings — never conflate)

| Meaning | Where it appears | Effect |
|---------|------------------|--------|
| **A. Field-value `INVALID`** | A selection field’s raw token is the literal `INVALID` (or empty / N/A per resolver empty-tokens) | **Absent reference.** Keep ABSENT. Never invent a BOOL, Conveyor row, or timer. |
| **B. Conveyor row `Type=INVALID`** | A real `IO_Name` exists on a Conveyor catalog row whose `Type` column is `INVALID` | **Not a discard.** The row remains a valid **named object** (often logical/memory/internal, spare aux, PB pilot, MCR, etc.). Other tables may SELECTION-resolve to it. |

### Proof examples (validation RUN — labeled examples only)

Field-value absent (meaning A):

- `Jamzones.Reset Button = INVALID` on several active zones → no reset PB wired.
- `Mtrchain.Motor_Chained2..10 = INVALID` → empty chain slots.

Catalog row Type=INVALID but referenceable (meaning B):

- `ENABLE_SAWTOOTH`, `LATCH_SAWTOOTH`, `JAM_TAKEAWAY`, `MEM_CP4_8_START` — Conveyor `IO_Name` rows with `Type=INVALID`, yet CP3 RESOLVED from Jamzones Enable/Latch/Jammed/Start Button fields.
- CP3 sample: `Jamzones.Enable Bit` raw=`ENABLE_SAWTOOTH` → `Conveyor::ENABLE_SAWTOOTH` (RESOLVED, `SELECTION_UNIQUE`, `SOURCE_PROVEN`).

**Never:** treat Type=INVALID as “delete this Conveyor row from the reference catalog.”  
**Never:** treat field-value INVALID as “guess a nearby BOOL.”

---

## Taxonomy classes (referenceable objects)

Classes are **object kinds**, not Studio tag types. A single Conveyor menu hosts many classes discriminated by `Type` + usage.

| Class ID | Fortna menu / identity | Discriminator | Referenceable? | Notes |
|----------|------------------------|---------------|----------------|-------|
| `mechanical_conveyor` | Conveyor.`IO_Name` | Type ∈ {STRAIGHT, CURVE, BELT, ZEROPRESSURE, TRIANG, …} | YES | Transport geometry + motor chains |
| `motor_or_drive` | Conveyor.`IO_Name` | Type=MOTOR (and Drive/VFD naming) | YES | Mtrchain heads / indexes |
| `photoeye` | Conveyor.`IO_Name` | Type=PHOTOCELL | YES | Jamcheck / Fullline sensors |
| `pushbutton_or_prox` | Conveyor.`IO_Name` | Type=PROXPART (e.g. `1PBSTART`) | YES | Jamzones Start/Stop/Reset buttons |
| `beacon_or_annunciator` | Conveyor.`IO_Name` | Type=BEACON | YES | Horns/beacons as parts |
| `display_image_part` | Conveyor.`IO_Name` | Type=IMAGE | YES | Drawing-only; weak PLC emit |
| `logical_internal_signal` | Conveyor.`IO_Name` | Type=INVALID **with** usable identity used as Enable/Latch/Jam/MEM | YES | Universal catalog placeholder |
| `spare_or_placeholder_part` | Conveyor.`IO_Name` | IO_Name/Type placeholder (`INVALID`, SPARE, blank) | NO as target | Inactive / absent |
| `timer` | timemenu.`Timer_Name` | identity present | YES | Jamzones Start Stop Timer; Mtrchain timers |
| `machine_owner` | Machine identity | identity present | YES | Jamzones `Zone Owner `; Conveyor.`Machine_Name` |
| `start_stop_zone` | StartStopZones.`Zone Name` | active zone name | YES | Jamzones.`StartStopZone` |
| `jam_zone` | Jamzones.`Zone Name` | active zone name | YES | Jamcheck.`Zone`; Mtrchain.`Stop Zone` (DLIST→Jamzones) |
| `horn` | horns identity | identity present | YES | Mtrchain.`Horn` |
| `error_object` | Errors identity | identity present | YES | Jamcheck/Fulljam Error_Name |
| `merge_boss` / `merge_input` / `merge_route` | Merge* menus | active identities | YES | Transport merge model |
| `sorter_*` | Sorters / Srt* menus | when present on overlay | YES | Sorter packs — MORE_EVIDENCE_REQUIRED for emit |
| `encoder` | Encoders | identity present | YES | Sorter / tracking |
| `io_card` / `configio_point` | IOCard / Configio | identity present | YES | Hardware I/O pack |
| `absent_reference` | — | field token INVALID/empty | N/A | Explicit null selection |

### Conveyor Type inventory (validation RUN base `Conveyor.asc`)

Observed distinct `Type` values: `STRAIGHT`, `CURVE`, `BELT`, `ZEROPRESSURE`, `TRIANG`, `MOTOR`, `PHOTOCELL`, `PROXPART`, `BEACON`, `IMAGE`, `INVALID`.

`INVALID` is the **largest** population (logical + spare + aux catalog). Population size alone does not imply discard.

---

## Menus that are universal catalogs

| Menu | Role |
|------|------|
| **Conveyor** (`Parts_Menu` UI title in fortna.mnu) | Universal named-object catalog — belts, motors, PEs, PBs, beacons, **and** logical/memory placeholders |
| **timemenu** | Timer logical objects |
| **Machine** | Controller / process owner |
| **StartStopZones** | Start/stop island state-machine rows |
| **Jamzones** | Jam / start-stop zone control rows |
| **horns** | Horn objects |
| **Errors** | Error catalog |

---

## What is NOT a separate taxonomy class

- **Engineering Area** — often ENGINEER_ASSIGNED; not a reliable FortnaPlus MNUNAME on these RUNs (`Area` NOT_FOUND in DLIST inventory).
- **Finished-PLC BOOL / `*_MEM` name pattern** — never a discovery class. LogicalSignalModel consumes Fortna selection identities, not Studio archaeology.
- **Display-only canvas fields** (`entryCanvas`, `pathCanvas`, …) — presentation, not Fortna reference targets.

---

## Resolver unresolved taxonomy (CP3)

From `fortna_reference_resolver.py` / graph statistics (capability vs defect):

| Code | Meaning |
|------|---------|
| `EMPTY_SOURCE_VALUE` | Source field empty/INVALID — absent (expected) |
| `INVALID_DATASOURCE_COLUMN` / `TARGET_COLUMN_MISSING` | Schema/capability gap |
| `INVALID_DATASOURCE_VALUE` | Bad datasource value |
| `DYNAMIC_CAPABLE_SCHEMA` | Dynamic MenuMenu path without resolved instance |

These classify **edge resolution outcomes**, not Conveyor Type.

---

## Rules for downstream models

1. A reference is valid when CP3 status is RESOLVED to `(targetMenu, targetIdentity)` — **regardless of Conveyor.Type**.
2. Field-value INVALID → absent; do not coerce.
3. Transport belt emit may still filter to mechanical Types — that filter must **not** delete LogicalSignalModel targets.
4. Site names in examples (`ORNCCP2`, `ENABLE_SAWTOOTH`, …) are **labeled validation-oracle examples**, never production decision keys.

---

## Related

- [`LOGICAL_SIGNAL_MODEL.md`](LOGICAL_SIGNAL_MODEL.md)
- [`FORTNAPLUS_PARTS_MODEL.md`](FORTNAPLUS_PARTS_MODEL.md)
- [`FORTNAPLUS_CONTROL_GRAPH.md`](FORTNAPLUS_CONTROL_GRAPH.md)
- [`../FORTNAPLUS_REFERENCE_RESOLVER.md`](../FORTNAPLUS_REFERENCE_RESOLVER.md)
- [`../FORTNAPLUS_MNU_RELATIONSHIPS.md`](../FORTNAPLUS_MNU_RELATIONSHIPS.md)
- [`../RUN_EVIDENCE_AUTHORITY.md`](../RUN_EVIDENCE_AUTHORITY.md)
