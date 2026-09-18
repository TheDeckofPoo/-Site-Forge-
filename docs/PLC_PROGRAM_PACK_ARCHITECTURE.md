# PLC Program Pack Architecture (Gates J / K / L)

**Branch:** `feature/plc2-transport-fidelity`  
**Purpose:** Map canonical Site Forge models → reusable PLC **program packs**. Architecture-first — **no compiler implementation** in this checkpoint.

Related:
- [`docs/evidence/SORTER_TRACK_PROGRAM_PACK.md`](evidence/SORTER_TRACK_PROGRAM_PACK.md)
- [`docs/evidence/WCS_PROGRAM_PACK.md`](evidence/WCS_PROGRAM_PACK.md)
- [`docs/evidence/LOGICAL_SIGNAL_MODEL.md`](evidence/LOGICAL_SIGNAL_MODEL.md)
- [`docs/evidence/FORTNAPLUS_OBJECT_TAXONOMY.md`](evidence/FORTNAPLUS_OBJECT_TAXONOMY.md)
- [`docs/evidence/FORTNAPLUS_CONTROL_GRAPH.md`](evidence/FORTNAPLUS_CONTROL_GRAPH.md)
- [`docs/evidence/STARTSTOP_JAM_PLC_MAPPING.md`](evidence/STARTSTOP_JAM_PLC_MAPPING.md)
- [`docs/TASK_PROGRAM_ARCHITECTURE.md`](TASK_PROGRAM_ARCHITECTURE.md)
- [`config/program_packs/`](../config/program_packs/)

Finished / gold L5X files are **validation oracles only**.

---

## Model → pack map

```
TransportModel ──► Area_*_Fast / Area_*_Slow / Area_*_L1 / Area_*_L2   (+ merge leaves)
MergeModel     ──► Merge AOI wiring inside Fast / dedicated Sawtooth_Merge pack
SafetyModel    ──► ES (+ future safety zone packs)
SorterModel    ──► Sorter_Track (+ optional ShippingSorter_Area_L3 leaves)
WCSModel       ──► WCS_Interface_TCP_IP   [optional — not sorter-mandatory]
HardwareIOModel► IO_MAP / module tags / Configio endpoints
LogicalSignalModel ──┐
StartStopModel ──────┼─► referenced by Transport / Safety / Sorter packs
JamZoneModel ────────┘      (Jamzones, StartStopZones, Mtrchain logical refs, enables)
FortnaEngineeringGraph ─► semantic overlay on CP3 (architecture; builder NOT_STARTED)
        │
        ▼
   PLC PROGRAM PACKS (canonical-model consumers)
```

---

## Gate K — Greenfield + Brownfield invariant

> **PLC compilers consume canonical models only.**  
> They must **not** care whether a fact originated from RUN discovery or engineer assignment.

| Origin | Confidence | Compiler behavior |
|--------|------------|-------------------|
| RUN PROVEN / DERIVED | PROVEN / DERIVED | May auto-populate when pack rules allow |
| ENGINEER_ASSIGNED | ENGINEER_ASSIGNED | Same emit path as PROVEN once in effective model |
| INVALID / absent | — | Leave absent — never fabricate |
| REVIEW_REQUIRED / UNKNOWN | — | Block or stub per pack validation — never guess |

Brownfield import and greenfield drawing both land in the same effective model before emit.

---

## Gate K — Canonical model dependency matrix

| Canonical model | Status | Consumed by packs | Depends on | Notes |
|-----------------|--------|-------------------|------------|-------|
| **LogicalSignalModel** | **MODEL_DEFINED** | Transport, Safety, Sorter (when present) | CP3 SELECTION edges; Conveyor catalog; timemenu; taxonomy | INVALID = absent; Type=INVALID Conveyor rows remain valid targets. Compiler wiring **NOT_STARTED**. |
| **StartStopModel** | **MODEL_DEFINED** (docs/contracts) | Transport Slow/Fast area packs; Safety (ownership) | StartStopZones; Jamzones.`StartStopZone`; LogicalSignalModel | StartStop ≠ Engineering Area. PLC shape: Area_UDT / CS_UDT (**oracle**). |
| **JamZoneModel** | **MODEL_DEFINED** (docs/contracts) | Transport Slow (`Slow_Jam`); Safety enable combine | Jamzones; Jamcheck; CombinedJamZones; LogicalSignalModel | Enable/Latch/Jammed/buttons/timer/owner via CP3. |
| **FortnaEngineeringGraph** | **ARCHITECTURE_DEFINED** | Future model builders | CP3 (no fork) | Semantic edges only when Fortna-proven; else `generic_reference`. |
| TransportModel | existing / frozen PLC2 path | Area_* packs | Parts geometry; Mtrchain (**do not rewrite**) | Mechanical Types only for belt emit |
| MergeModel | partial | Fast / Sawtooth_Merge | MergeBoss / MergeInputs | |
| SafetyModel | partial | ES | devices + ENGINEER_ASSIGNED membership | |
| HardwareIOModel | existing / partial | IO_MAP | Configio | |
| SorterModel | proposed | Sorter_Track | RUN sorter tables + LogicalSignalModel | Pack readiness **MORE_EVIDENCE_REQUIRED**; compiler **NOT_STARTED** |
| WCSModel | proposed | WCS_Interface_TCP_IP | engineer endpoint; optional Sorter | Pack readiness **MORE_EVIDENCE_REQUIRED**; compiler **NOT_STARTED**; optional |

Contracts:

- `config/program_packs/logical_signal_model.json`
- `config/program_packs/fortnaplus_object_taxonomy.json`
- `config/program_packs/fortnaplus_control_graph_contract.json`
- [`docs/evidence/STARTSTOP_JAM_PLC_MAPPING.md`](evidence/STARTSTOP_JAM_PLC_MAPPING.md)

---

## Pack catalog

### 1. Transport / Area equipment pack

| | |
|--|--|
| **Status** | **existing** (CP4 transport path; frozen for PLC2) |
| **INPUT MODEL** | TransportModel, MergeModel, LogicalSignalModel (jam/enable refs), HardwareIOModel |
| **GENERATED PROGRAM** | `Area_*_Fast`, `Area_*_Slow`, `Area_*_L1`, `Area_*_L2` |
| **TASK/RATE** | fast_equipment / slow_equipment / config_l1 / config_l2 (rates from platform/library — not Greensboro literals) |
| **ROUTINES** | Conv_Fast, Conv_PE, Conv_Full, Conv_Merge, Conv_Flt, Conv_Jam, Area_*, timers ST, … |
| **DEPENDENCIES** | Fast_Conv, Slow_Flt, Slow_Jam, PE_Logic, Full_PE, Merge_* AOIs |
| **AUTO-POPULATED** | Conveyor mechanical P-tags with I/O proof; merge lanes when PROVEN |
| **ENGINEER-REQUIRED** | Ambiguous release IO, safety membership, non-RUN geometry |
| **VALIDATION** | Transport freeze gates; no Type=INVALID logical rows as belts |

### 2. Merge pack (incl. Sawtooth)

| | |
|--|--|
| **Status** | **partial** (2-to-1 existing; Sawtooth library pack exists, site-coupled) |
| **INPUT MODEL** | MergeModel |
| **GENERATED PROGRAM** | merge AOIs in Fast and/or `Sawtooth_Merge` |
| **TASK/RATE** | tracking or fast_equipment per merge class |
| **ROUTINES** | library-defined |
| **DEPENDENCIES** | Merge_2to1 / Sawtooth library |
| **AUTO-POPULATED** | MergeBoss / MergeInputs when PROVEN |
| **ENGINEER-REQUIRED** | HS sawtooth timing, lane release when REVIEW |
| **VALIDATION** | No finished-PLC rate hardcodes as discovery |

### 3. Safety pack (ES)

| | |
|--|--|
| **Status** | **partial** (ES structural reference; membership often ENGINEER_ASSIGNED) |
| **INPUT MODEL** | SafetyModel, LogicalSignalModel |
| **GENERATED PROGRAM** | `ES` |
| **TASK/RATE** | safety (~20 ms oracle example) |
| **ROUTINES** | per-zone Safe_Logic / Safe_PI |
| **DEPENDENCIES** | ES UDTs / zone AOIs |
| **AUTO-POPULATED** | device existence when RUN-proven |
| **ENGINEER-REQUIRED** | zone membership |
| **VALIDATION** | Never invent chirality / membership |

### 4. Sorter_Track pack

| | |
|--|--|
| **Status** | **proposed** (architecture READY docs; emit NOT_STARTED) |
| **INPUT MODEL** | SorterModel, LogicalSignalModel, optional WCSModel |
| **GENERATED PROGRAM** | `Sorter_Track` |
| **TASK/RATE** | tracking (oracle example 5 ms) |
| **ROUTINES** | Main, Encoder, Track_*, Divert_*, Scanner, Wave_Divert, … (see sorter contract) |
| **DEPENDENCIES** | sealed TRK_/Enc_ AOI library; Token/Divert UDTs |
| **AUTO-POPULATED** | sorter identity, encoder, scan/divert topology when PROVEN |
| **ENGINEER-REQUIRED** | divert IO, offsets/triggers, wave/rate, gridlock |
| **VALIDATION** | no gold-pack clone; divert trigger NOT_SUPPORTED until generic timing contract |
| **Readiness** | **MORE_EVIDENCE_REQUIRED** — see sorter contract |

### 5. WCS pack

| | |
|--|--|
| **Status** | **proposed** (architecture from PLC4+PLC5; emit NOT_STARTED) |
| **INPUT MODEL** | WCSModel, optional SorterModel |
| **GENERATED PROGRAM** | `WCS_Interface_TCP_IP` |
| **TASK/RATE** | wcs (oracle example 10 ms) |
| **ROUTINES** | INIT, TCP server, FIFO, routers, Decision*/Heartbeat SBRs |
| **DEPENDENCIES** | WCS message UDTs; optional Token/Divert tags |
| **AUTO-POPULATED** | none for TCP endpoint from RUN alone |
| **ENGINEER-REQUIRED** | endpoint, framing, decision points, enables |
| **VALIDATION** | optional pack; never auto-include from sorter discovery |
| **Readiness** | **MORE_EVIDENCE_REQUIRED** — see WCS contract |

### 6. Hardware I/O pack

| | |
|--|--|
| **Status** | **existing / partial** (IO_MAP path) |
| **INPUT MODEL** | HardwareIOModel (Configio, modules) |
| **GENERATED PROGRAM** | `IO_MAP` (+ module tags) |
| **TASK/RATE** | tracking / with IO scan (oracle scheduling varies — PLC5 RTfinished leaves IO_MAP unscheduled) |
| **ROUTINES** | map routines |
| **DEPENDENCIES** | hardware catalog |
| **AUTO-POPULATED** | Configio PROVEN endpoints |
| **ENGINEER-REQUIRED** | unresolved aliases |
| **VALIDATION** | physical endpoint identity never fuzzy-collapsed |

### 7. LogicalSignalModel (cross-cutting — not a Studio program)

| | |
|--|--|
| **Status** | **proposed** (model defined; taxonomy + control graph contracts added) |
| **INPUT MODEL** | Jamzones, Mtrchain, StartStopZones, timemenu, Conveyor catalog refs |
| **GENERATED PROGRAM** | none directly — consumed by Transport / Safety / Sorter packs |
| **TASK/RATE** | n/a |
| **ROUTINES** | n/a |
| **DEPENDENCIES** | CP3 resolver (already covers Jamzones + Mtrchain SELECTION fields); object taxonomy; FortnaEngineeringGraph overlay when built |
| **AUTO-POPULATED** | RESOLVED CP3 edges; ENGINEER_ASSIGNED overrides |
| **ENGINEER-REQUIRED** | INVALID slots the engineer intentionally fills |
| **VALIDATION** | INVALID stays absent; Type=INVALID Conveyor rows remain valid logical targets |
| **Readiness** | **MODEL_DEFINED** — compiler wiring **NOT_STARTED** |

### 7b. StartStopModel (cross-cutting — not a Studio program)

| | |
|--|--|
| **Status** | **proposed** (docs/contracts this checkpoint) |
| **INPUT MODEL** | StartStopZones; Jamzones.`StartStopZone`; ownership; request flags |
| **GENERATED PROGRAM** | none directly — shapes Area_* start/stop / CS wiring via Transport pack |
| **DEPENDENCIES** | LogicalSignalModel; Machine ownership |
| **AUTO-POPULATED** | Active StartStopZones rows + Jamzones membership when PROVEN |
| **ENGINEER-REQUIRED** | Area program naming / membership when StartStop≠Area |
| **VALIDATION** | Do not rename Jam/ES/StartStop catalogs when Area renames |
| **Readiness** | **MODEL_DEFINED** — compiler wiring **NOT_STARTED** |

### 7c. JamZoneModel (cross-cutting — not a Studio program)

| | |
|--|--|
| **Status** | **proposed** (docs/contracts this checkpoint) |
| **INPUT MODEL** | Jamzones; Jamcheck; CombinedJamZones; LogicalSignalModel enable/latch/jam/buttons/timer |
| **GENERATED PROGRAM** | none directly — consumed by Area_*_Slow (`Slow_Jam`) / enable combine |
| **DEPENDENCIES** | LogicalSignalModel; StartStopModel (island link); CP3 |
| **AUTO-POPULATED** | RESOLVED Jamzones/Jamcheck edges when PROVEN |
| **ENGINEER-REQUIRED** | Combined enable device list when not RUN-complete |
| **VALIDATION** | INVALID selections stay absent; oracle PLC mapping is validation-only |
| **Readiness** | **MODEL_DEFINED** — compiler wiring **NOT_STARTED** |

### 8. Platform packs (Sys / System / HMI / PLC_Fast)

| | |
|--|--|
| **Status** | **existing** (gold Sys/System libraries) |
| **INPUT MODEL** | site/platform config |
| **GENERATED PROGRAM** | Sys, System, HMI, PLC_Fast |
| **TASK/RATE** | system / hmi / fast |
| **AUTO-POPULATED** | constants / NTP when included |
| **ENGINEER-REQUIRED** | HMI faceplates often CONFIGURATION_REQUIRED |

### 9. ShippingSorter / Redroom L3 leaves

| | |
|--|--|
| **Status** | **partial** (gold L3 pack = oracle only) |
| **INPUT MODEL** | SorterModel + area transport |
| **GENERATED PROGRAM** | `*_Area_L3` when generic pack exists |
| **VALIDATION** | L3 only with generic library — no silent monolith |

---

## Gate L — Readiness verdicts

| Pack / model | Verdict | Why |
|--------------|---------|-----|
| **LogicalSignalModel** | **MODEL_DEFINED** | Field→menu classes + taxonomy proven; emit **NOT_STARTED** |
| **StartStopModel** | **MODEL_DEFINED** | RUN schema + oracle Area/CS mapping documented; emit **NOT_STARTED** |
| **JamZoneModel** | **MODEL_DEFINED** | Jamzones/Jamcheck + Slow_Jam oracle mapping documented; emit **NOT_STARTED** |
| **SORTER_TRACK** | **MORE_EVIDENCE_REQUIRED** | Routine architecture proven, but generic AOI/parameter library + divert timing contract incomplete; gold pack is site-fixed |
| **WCS** | **MORE_EVIDENCE_REQUIRED** | Routine architecture stable PLC4/PLC5, but message schema + endpoint authority not pack-ready; must stay optional |

Compilers: **NOT_STARTED** for Sorter_Track / WCS / LogicalSignal / StartStop / JamZone emit paths. Do not mark COMPLETE. Do not emit hollow programs. Do not build Sorter/WCS compilers in this checkpoint.

---

## Anti-cheat

- No production site-specific decision logic (`ORNCCP5`, `P504`, `ENC504`, …) inside compilers.
- Site names may appear in docs/fixtures/contracts only as **validation-oracle examples**.
- Do not promote finished L5X or gold packs to RUN discovery authority.
