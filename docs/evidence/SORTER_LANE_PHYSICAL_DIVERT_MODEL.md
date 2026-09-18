# Sorter Lane ↔ Physical Divert Model (GATE 3 + GATE 4)

**Machine:** `ORNCCP5`  
**Generated:** `2026-09-18T15:35:15.634076+00:00`  
**Source of truth:** RUN `SrtZoneLane` ⋈ `Outpoints` (finished PLC is validation only)

---

## GATE 3 — Confirm PE semantics

Confirm PE = divert verification photoeye that proves the carton physically entered the destination after the divert fired (Track_Divert_Confirm / Outpoints verify path).

| Item | Value |
|------|-------|
| Primary RUN field | `Outpoints.Verify I/O Name` |
| Join | `SrtZoneLane.Lane == Outpoints.Outpoint Name` |
| Proven when | Verify I/O Name is meaningful, not INVALID, and distinct from Outpoint I/O Name (solenoid / SSV). Sites often mirror SSV into Verify — that is NOT a PE. |
| PLC5 proven Confirm PE | **0** / 32 |
| PLC5 derived Confirm PE | **0** |
| Engineer selection required | **32** lanes |

### Not Confirm PE

- Outpoints.Outpoint I/O Name (divert solenoid / SSV)
- SrtZoneLane.FullClearTimer / Outpoints.Full_Clr_Timer_Name (timer object names — PE tokens are hints only, never proof)
- Verify I/O Name when equal to Outpoint I/O Name
- Name similarity between timer strings and Conveyor PE inventory alone

### UI policy

- When DERIVED/PROVEN candidate exists: `Derived/Proven: <PE> [Accept] [Change]`
- When no candidate: `empty Select (Confirm PE…) only`
- Acceptance: `ENGINEER_ACCEPTED — never falsify PROVEN`

Artifact: `exports/stabilization/plc5_divert_confirm_pe_audit.json`

---

## GATE 4 — 32 DestinationLanes → 16 PhysicalDiverts

**Hypothesis:** One physical sorter divert commonly services two destination lanes (field engineering).

**Classification:** `STRONGLY_SUPPORTED`

Not a PROVEN schema FK. Do not hardcode physical_diverts=lanes/2.

| Count | Value |
|-------|------:|
| Destination lane records | **32** |
| Unique physical outputs (SSV) | **32** |
| Unique physical divert mechanisms | **16** |
| Lanes per physical divert | **2** |
| Unresolved mappings | **0** |
| Finished oracle Track_Divert_UDT (validation) | **16** |

### Grouping keys (derived from Fortna relationships — not `/2`)

- **shared_FullClearTimer** (`STRONGLY_SUPPORTED_RUN_FIELD`): 16 timers · size histogram {2: 16}
- **shared_SSV_family** (`STRONGLY_SUPPORTED_CORROBORATING_PATTERN`): 16 families · size histogram {2: 16}
- **consecutive_HostZone_within_timer** (`SUPPORTING`): 16/16 timer groups consecutive
- **SrtZoneLane.Name** (`SUPPORTING_INCOMPLETE`): 15 names · size histogram {2: 14, 4: 1}
- **TwoSidedShoe / RightSideDivert** (`DOES_NOT_SUPPORT_AT_THIS_SITE`): ORNCCP5 enabled rows are TwoSidedShoe=N, RightSideDivert=N
- **Outpoints.Number of Diverts** (`UNUSABLE`): 0 on all 32 destination lanes

### Proposed model

- **DestinationLane** = one enabled SrtZoneLane row (unique Lane + HostZone + Outpoint I/O)
- **PhysicalDivert** = grouping of DestinationLanes that share FullClearTimer (and, on ORNCCP5, one SSV family + consecutive HostZones)
- **Relationship** = PhysicalDivert → one or more DestinationLanes (ORNCCP5: exactly 2)
- **Emit policy** = Phase 1 continues DestinationLane multiplicity (32). Do not collapse to 16 Track_Divert instances until library/schema elevates grouping to PROVEN. Do not hardcode /2.

### Phase-1 action

Leave divert_count at DestinationLane multiplicity (32 on ORNCCP5). Document PhysicalDivert as STRONGLY_SUPPORTED diagnostic model only.

Artifact: `exports/stabilization/plc5_lane_divert_relationship.json`

