# Sorter_Track Program Pack (Gates B–D / F / H)

**Status:** `READY_TO_IMPLEMENT` for **Phase 1 hot emit** (pack definition v1) — compiler implementation still **`NOT_STARTED`**.  
**Oracles (validation only):**  
- PLC5: `C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_Greensboro_NC_PLC5_RTfinished.L5X`  
- PLC4: `C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_Greensboro_NC_PLC4 finished.L5X`  

**Machine-readable twin:** [`config/program_packs/sorter_track_contract.json`](../../config/program_packs/sorter_track_contract.json) (`pack_definition_version: 1`)  
**PLC4↔PLC5 diff:** [`PLC4_PLC5_SORTER_PROGRAM_PACK_DIFF.md`](PLC4_PLC5_SORTER_PROGRAM_PACK_DIFF.md) · [`config/program_packs/plc4_plc5_sorter_pack_diff.json`](../../config/program_packs/plc4_plc5_sorter_pack_diff.json)

Finished PLC is a **validation oracle only** — never a discovery source. Site identities below are labeled as validation-oracle examples.

---

## Phase 1 executable contract summary

| Item | Phase 1 rule |
|------|----------------|
| Pack include | Engineer/UI selects Sorter_Track — **never** silent auto-include from discovery alone as “complete” |
| Program | Emit `Sorter_Track` with Main routine name **`Main`** |
| Task | Bind `task_class=tracking` PERIODIC task; **rate/priority PARAMETERIZED** (PLC4/PLC5 oracle example 5 ms / pri 2 — **not** a universal hardcoded constant) |
| REQUIRED_STANDARD routines | Main, Encoder, Track_Pointer, Track_Induct_Package, Track_Manual_Destination, Scanner, Track_Package, Track_Lost_Package, Divert_Lane_Status, Track_Divert_Package, Wave_Divert, Divert_Rate_Limit, Track_Divert_Confirm, Track_Offset_Find, Response_Time |
| CONDITIONAL_STANDARD | `Gridlock_Prevention`, `RT_Virtual_Enc` — **omit unless enabled** (PLC5 has both; PLC4 has neither; gold has Gridlock only) |
| MODEL_EXPANDED | Encoder / tracking-path / divert / scan / exit instance rungs+tags via **FOR EACH** SorterModel — **never hardcode 32 or 16** |
| CUSTOM | Gridlock inhibit policy content when leaf enabled |
| UNKNOWN / NOT_SUPPORTED | Divert **trigger/offset value** synthesis from RUN alone (`Track_Offset_Find` = shell only) |
| AOI/UDT | Consume sealed Enc_*/TRK_* library + track UDT families — do **not** clone gold program |
| WCS boundary | **Separate optional pack**; sorter emits handshake tag surface only when `WCSModel.enabled` |
| Compiler | `compiler_implementation: NOT_STARTED` (parent implements against this contract) |

### Gaps still honest

1. Sealed AOI open-parameter packaging incomplete (partial open libs only).  
2. Offset/trigger counts remain engineer/commissioning.  
3. Gold `Sorter_Track_Program.L5X` is Greensboro-fixed — validation only.  
4. Raw `SrtZoneLane` row count ≠ divert emit count without model approval (oracle: 32 zone rows vs 16 `Track_Divert_UDT`).

---

## Gate E context (PLC5 oracle structure)

| Item | Value (oracle) | Class |
|------|----------------|-------|
| Controller | `ORLY_Greensboro_NC_PLC5` / 1756-L83E | SITE_CONFIGURATION |
| Programs | ES, HMI, IO_MAP, PLC_Fast, Redroom_Area_*, ShippingSorter_Area_*, **Sorter_Track**, Sys, System, **WCS_Interface_TCP_IP** | mix |
| Sorter_Track task | `P02_Track_5ms` PERIODIC Rate=5 Priority=2 | STANDARD_ARCHITECTURE (class=`tracking`; rate PARAMETERIZED) |
| WCS task | `P03_WCS_10ms` PERIODIC Rate=10 Priority=3 | OPTIONAL pack class=`wcs` |
| IO_MAP | Present but **not scheduled** on any task in this finished export | UNKNOWN / CUSTOM_ENGINEERING |

### Program classification (PLC5)

| Program | Class |
|---------|-------|
| Sorter_Track | STANDARD_ARCHITECTURE (reusable pack) |
| WCS_Interface_TCP_IP | OPTIONAL STANDARD_ARCHITECTURE |
| ShippingSorter_Area_* / Redroom_Area_* | EQUIPMENT_INSTANCE / SITE_CONFIGURATION |
| ES / Sys / System / HMI / PLC_Fast / IO_MAP | platform packs |

---

## Exact routine lists (oracles)

Main routine name: **`Main`**.

### PLC5 JSR order (17 routines)

1. Encoder → 2. Track_Pointer → 3. Track_Induct_Package → 4. Track_Manual_Destination → 5. Scanner → 6. Track_Package → 7. Track_Lost_Package → 8. Divert_Lane_Status → 9. Track_Divert_Package → 10. Wave_Divert → 11. Divert_Rate_Limit → 12. Track_Divert_Confirm → 13. Track_Offset_Find → 14. **Gridlock_Prevention** → 15. Response_Time → 16. **RT_Virtual_Enc**

### PLC4 JSR order (15 routines)

Same core through Track_Offset_Find → Response_Time. **No** Gridlock_Prevention, **no** RT_Virtual_Enc.  
PLC4 `P02` also schedules **Sawtooth_Merge** beside Sorter_Track.

### Gold pack

`tools/libraries/programs/Sorter_Track_Program.L5X`: PLC5 core + Gridlock; **missing** RT_Virtual_Enc. Greensboro-fixed — not a generic library.

| Routine | Type | Emit class | PLC4 rungs | PLC5 rungs |
|---------|------|------------|----------:|----------:|
| Main | RLL | REQUIRED_STANDARD | 15 | 17 |
| Encoder | RLL | REQUIRED_STANDARD + MODEL_EXPANDED | 1 | 10 |
| Track_Pointer | RLL | REQUIRED_STANDARD + MODEL_EXPANDED | 1 | 5 |
| Track_Induct_Package | RLL | REQUIRED_STANDARD + MODEL_EXPANDED | 2 | 2 |
| Track_Manual_Destination | RLL | REQUIRED_STANDARD | 2 | 2 |
| Scanner | RLL | REQUIRED_STANDARD + MODEL_EXPANDED | 8 | 8 |
| Track_Package | RLL | REQUIRED_STANDARD + MODEL_EXPANDED | 2 | 14 |
| Track_Lost_Package | RLL | REQUIRED_STANDARD + MODEL_EXPANDED | 1 | 5 |
| Divert_Lane_Status | RLL | REQUIRED_STANDARD + MODEL_EXPANDED | 7 | 56 |
| Track_Divert_Package | RLL | REQUIRED_STANDARD + MODEL_EXPANDED | 3 | 48 |
| Wave_Divert | RLL | REQUIRED_STANDARD + MODEL_EXPANDED | 1 | 16 |
| Divert_Rate_Limit | RLL | REQUIRED_STANDARD + MODEL_EXPANDED | 3 | 18 |
| Track_Divert_Confirm | RLL | REQUIRED_STANDARD + MODEL_EXPANDED | 1 | 1 |
| Track_Offset_Find | RLL | REQUIRED_STANDARD + MODEL_EXPANDED (shell; values NOT_SUPPORTED) | 5 | 24 |
| Gridlock_Prevention | RLL | CONDITIONAL_STANDARD / CUSTOM content | — | 9 |
| Response_Time | RLL | REQUIRED_STANDARD | 4 | 4 |
| RT_Virtual_Enc | ST | CONDITIONAL_STANDARD | — | yes |

Rung deltas are explained by encoder/path/divert **multiplicity** (see diff doc) — except optional-leaf presence and Sawtooth co-schedule.

---

## Multiplicity rules (Gate C)

```
FOR EACH sorter.encoder          → Encoder AOI cluster
FOR EACH tracking path           → Track_Pointer + Track_Package (+ transfers) + Lost_Package path
FOR EACH induct/decision point   → Track_Induct_* 
FOR EACH scan/decision group     → Token_SCN* + Track_Group_SCN* + Scanner handshake
FOR EACH approved divert instance→ Track_Divert_UDT/AOI + Wave + RateLimit + LaneStatus + OffsetFind shell
```

**Forbidden:** hardcoding divert counts (32, 16, …). Approve divert instances in SorterModel (IO/config) before expand.

Oracle check: PLC4 → 1 divert UDT (`P424_Divert1`); PLC5 → 16 divert UDTs; RUN zone lanes may be 32.

---

## Reusable PROGRAM CONTRACT (v1)

```
INPUT MODEL:
  SorterModel { sorters[], encoders[], scan_groups[], divert_instances[], induct_points[], tracking_paths[], exit_paths[] }
  LogicalSignalModel (enable/jam/latch refs)
  optional WCSModel (handshake only when enabled)

GENERATED PROGRAM: Sorter_Track
TASK CLASS: tracking  (rate/priority PARAMETERIZED; oracle example 5 ms — not universal law)
ROUTINES: REQUIRED_STANDARD list + CONDITIONAL_STANDARD when enabled
DEPENDENCIES: sealed Enc_*/TRK_* AOI library; Token/Track/Divert UDTs; optional WCS/Sawtooth packs
AUTO-POPULATED: structure/cardinality from SorterModel when PROVEN + approved divert instances
ENGINEER-REQUIRED: divert IO, approved divert set, offsets/triggers, wave/rate, optional gridlock policy
VALIDATION: no gold-pack clone; no hardcoded instance counts; divert trigger values NOT_SUPPORTED
PHASE1 HOT EMIT: shells + MODEL_EXPANDED slots; compiler_implementation NOT_STARTED until parent implements
```

---

## Sorter ↔ WCS interface (Gate H) — proven shared controller tags

Proven = identifier appears in **both** `Sorter_Track` and `WCS_Interface_TCP_IP` logic of the PLC5 oracle, and exists as a controller tag.

**Count: 34 controller-scoped shared roots** (16 are divert-instance UDTs).

Primary flows: decision request → decision response Destination → divert confirm (`O.Conf_MSG*`) → lost/recirc latches.

**Phase 1 WCS boundary recommendation:** keep WCS as a **separate optional pack**; do not auto-include from sorter discovery; when enabled, emit the handshake tag surface for WCS to consume.

---

## Readiness verdict

**SORTER_TRACK PACK: READY_TO_IMPLEMENT** (Phase 1 hot emit / pack_definition_version 1)

Meaning:
- Executable routine/task/expansion contract is specified from PLC4↔PLC5 archaeology.
- Parent may implement compiler against this contract.
- Full divert-trigger fidelity and sealed-AOI packaging gaps remain listed — do not claim COMPLETE generation.
- Do **not** emit hollow programs that pretend offsets/triggers are solved.
