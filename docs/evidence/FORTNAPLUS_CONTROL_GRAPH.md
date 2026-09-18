# FortnaEngineeringGraph — Control Relationship Architecture (Gate H)

**Branch:** `feature/plc2-transport-fidelity`  
**Machine-readable twin:** [`config/program_packs/fortnaplus_control_graph_contract.json`](../../config/program_packs/fortnaplus_control_graph_contract.json)  
**Status:** Architecture on **top of CP3** — do **not** fork CP3. Documentation / contract only.

Finished / gold PLCs are **validation oracles only**.

---

## Placement in the stack

```
CP1 .mnu schema/runtime
        ↓
CP2 typed RUN records
        ↓
CP3 generic reference resolver     ← KEEP AS-IS (edges = menu.field → menu.identity)
        ↓
FortnaEngineeringGraph (this gate) ← semantic overlay / classification
        ↓
Canonical models (LogicalSignalModel, StartStopModel, JamZoneModel, TransportModel, …)
        ↓
PLC program packs
```

CP3 answers: *what does this SELECTION resolve to?*  
FortnaEngineeringGraph answers: *what engineering meaning does that edge carry — when Fortna proves it?*

---

## Design rules

1. **Do not fork CP3.** Consume CP3 RESOLVED / EMPTY / unresolved taxonomy edges.
2. **Semantic edge types ONLY where Fortna proves meaning** via:
   - `fortna.mnu` DLIST target menu + field name semantics, and/or
   - FPC training docs aligned to those fields, and/or
   - Stable multi-table patterns already accepted in-repo (e.g. Jamzones↔StartStopZones).
3. Otherwise emit **`generic_reference`** (CP3 selection identity only).
4. Field-value `INVALID` → no edge (absent). Conveyor `Type=INVALID` does **not** invalidate an edge.
5. No production site-specific decision logic. Site names in examples are labeled validation-oracle examples.

---

## Node kinds

Nodes are `(menu, identity)` pairs from the Gate B taxonomy, plus schema-only capability nodes when needed.

Primary control nodes:

| Node kind | Menu |
|-----------|------|
| `part` / conveyor-family | Conveyor |
| `timer` | timemenu |
| `machine` | Machine |
| `start_stop_zone` | StartStopZones |
| `jam_zone` | Jamzones |
| `horn` | horns |
| `error` | Errors |
| `jam_check` | Jamcheck |
| `motor_chain` | Mtrchain (row identity = Motor_Name) |
| `merge_*` | MergeBoss / MergeInputs / … |
| `encoder` / `sorter_*` | Encoders / Sorters / … |

---

## Edge type catalog

### A. Generic (always available from CP3)

| Edge type | When |
|-----------|------|
| `generic_reference` | CP3 RESOLVED SELECTION / SELECTION_UNIQUE / MENU_COLUMN_ROW without a stronger proven semantic label |
| `absent_selection` | Explicit INVALID/empty — recorded as non-edge or ABSENT marker; never fabricated |

### B. Semantic — PROVEN for control model

| Edge type | Source → Target | Proof |
|-----------|-----------------|-------|
| `jamzone_latch_signal` | Jamzones.`Latch Bit` → Conveyor | DLIST→Conveyor; FPC-StartStopZones (latch = zone running) |
| `jamzone_jammed_signal` | Jamzones.`Jammed Bit` → Conveyor | DLIST→Conveyor |
| `jamzone_enable_signal` | Jamzones.`Enable Bit` → Conveyor | DLIST→Conveyor; CombinedJamZones training |
| `jamzone_start_button` | Jamzones.`Start Button` → Conveyor | DLIST→Conveyor |
| `jamzone_stop_button` | Jamzones.`Stop Button` → Conveyor | DLIST→Conveyor |
| `jamzone_reset_button` | Jamzones.`Reset Button` → Conveyor | DLIST→Conveyor; INVALID = absent |
| `jamzone_start_stop_timer` | Jamzones.`Start Stop Timer` → timemenu | DLIST→timemenu |
| `jamzone_owner` | Jamzones.`Zone Owner ` → Machine | DLIST→Machine (note trailing space in schema name) |
| `jamzone_in_start_stop_zone` | Jamzones.`StartStopZone` → StartStopZones | DLIST→StartStopZones; bidirectional documented with StartStopZones |
| `jamcheck_in_jamzone` | Jamcheck.`Zone` → Jamzones | DLIST→Jamzones |
| `jamcheck_sensor` | Jamcheck.`Sensor_Name` → Conveyor | DLIST→Conveyor |
| `jamcheck_conveyor` | Jamcheck.`Conveyor_Name` → Conveyor | DLIST→Conveyor |
| `jamcheck_owner` | Jamcheck.`Jam_Owner` → Machine | DLIST→Machine |
| `mtrchain_member` | Mtrchain.`Motor_Chained1..10` → Conveyor | DLIST→Conveyor; INVALID slot = absent |
| `mtrchain_motor_index` | Mtrchain.`Motor_Ndx` → Conveyor | DLIST→Conveyor |
| `mtrchain_aux` | Mtrchain.`Motor_Aux` → Conveyor | DLIST→Conveyor; training links latch↔aux |
| `mtrchain_enabled` | Mtrchain.`Enabled` → Conveyor | DLIST→Conveyor |
| `mtrchain_timer` | Mtrchain.`Timer_Name` / `RUN Timer_Name` → timemenu | DLIST→timemenu |
| `mtrchain_horn` | Mtrchain.`Horn` → horns | DLIST→horns |
| `mtrchain_stop_zone` | Mtrchain.`Stop Zone` → **Jamzones** | **fortna.mnu DLIST → Jamzones** (not StartStopZones) |
| `part_machine_owner` | Conveyor.`Machine_Name` → Machine | DLIST→Machine |
| `combined_jam_enable` | CombinedJamZones → Jamzones | Documented relationship when table present |

### C. Explicitly NOT promoted to semantic (remain generic or out of scope)

| Candidate | Why not semantic yet |
|-----------|----------------------|
| Name-similar `ENABLE_*` ↔ Area_HMI.Enable | Finished-PLC shape is oracle; no RUN proof of tag emission |
| Engineering Area ↔ StartStopZones | Area often ENGINEER_ASSIGNED; many-to-many; StartStop ≠ Area |
| Physical conveyor successor / adjacency | Geometry candidates ≠ Fortna SELECTION edges |
| Sorter divert timing | MORE_EVIDENCE_REQUIRED |

---

## Overlay algorithm (conceptual)

For each CP3 relationship edge:

1. If status ≠ RESOLVED → map to unresolved taxonomy / `absent_selection`; stop.  
2. Look up `(sourceMenu, sourceColumn, targetMenu)` in the semantic catalog above.  
3. If match → emit semantic edge type + retain CP3 provenance.  
4. Else → emit `generic_reference` with same endpoints.  
5. Classify target node using Gate B taxonomy (Conveyor.Type, menu, usage).  
6. Never invent endpoints.

---

## Relationship to existing docs

| Doc | Role |
|-----|------|
| [`../FORTNAPLUS_RELATIONSHIP_MODEL.md`](../FORTNAPLUS_RELATIONSHIP_MODEL.md) | Broader EXPLICIT/DOCUMENTED/DERIVED/OPTIONAL inventory |
| [`LOGICAL_SIGNAL_MODEL.md`](LOGICAL_SIGNAL_MODEL.md) | Field→target class matrices for Jamzones/Mtrchain |
| [`FORTNAPLUS_OBJECT_TAXONOMY.md`](FORTNAPLUS_OBJECT_TAXONOMY.md) | Node class vocabulary |
| CP3 graphs | Concrete RESOLVED instances |

Gate H does not replace the relationship model doc; it defines the **control-plane semantic overlay** compilers may consume later.

---

## Readiness

| Item | Status |
|------|--------|
| Architecture / edge catalog | **DEFINED** (this doc + JSON contract) |
| Graph builder implementation | **NOT_STARTED** |
| CP3 changes | **FORBIDDEN** this checkpoint |
| Sorter/WCS semantic edges | **MORE_EVIDENCE_REQUIRED** |

---

## Related

- [`STARTSTOP_JAM_PLC_MAPPING.md`](STARTSTOP_JAM_PLC_MAPPING.md) — PLC oracle mapping (Gate L)
- [`../PLC_PROGRAM_PACK_ARCHITECTURE.md`](../PLC_PROGRAM_PACK_ARCHITECTURE.md)
- [`../FORTNAPLUS_REFERENCE_RESOLVER.md`](../FORTNAPLUS_REFERENCE_RESOLVER.md)
