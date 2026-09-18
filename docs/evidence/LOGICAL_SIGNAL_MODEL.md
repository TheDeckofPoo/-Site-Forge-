# Logical / Memory Signal Model (Gate I — Curtis clarification)

**Machine-readable twin:** [`config/program_packs/logical_signal_model.json`](../../config/program_packs/logical_signal_model.json)

**Production preservation:** [`tools/scripts/fortna_control_model.py`](../../tools/scripts/fortna_control_model.py) → workbook `control_build`  
(`LogicalSignalModel` + `StartStopModel` + `JamZoneModel` + `FortnaEngineeringGraph`).  
`Conveyor.Type=INVALID` on a named row may be `LOGICAL_SIGNAL` (survive). Field value `INVALID` = absent.

## What Curtis means

FortnaPlus table fields such as Jam_Zones **Jammed Bit**, **Enable Bit**, **Start/Stop/Reset Button**, and Motor_Chains **Motor_Name** / **Timer_Name** / **Motor_Chained\*** are **named logical references** selectable inside FortnaPlus UI fields.

They are **not** “whatever BOOL happens to exist in a finished PLC.”  
They are **SELECTION / SELECTION_UNIQUE** values whose datasource is proven by `fortna.mnu` → `find_data_source()` → CP3 resolver.

`INVALID` is an **explicit absent reference**. Never fabricate a BOOL, never invent a Conveyor row, never infer from `*_MEM` / `CR####` name patterns alone.

---

## Provenance chain (do not skip)

```
fortna.mnu / project.mnu
    → CP1 schema metadata (DLIST / dataselect)
    → find_data_source()          [SOURCE_PROVEN]
    → CP2 typed RUN records
    → CP3 reference graph         [selection identity lookup]
    → RUN ASC tables (Jamzones, Mtrchain, Conveyor, timemenu, …)
```

Evidence already in-repo:
- `artifacts/mnu-relationships.json` (forward DLIST targets)
- `artifacts/fortna-reference-graph-plc{2,4,5}.json` (resolved edges)
- `docs/FORTNAPLUS_MNU_RELATIONSHIPS.md`
- `docs/FORTNAPLUS_REFERENCE_RESOLVER.md`
- `docs/FORTNAPLUS_TABLE_REFERENCE.md`

---

## Critical model fact

The Fortna **`Conveyor` menu/table is a universal named-object catalog**, not “belts only.”

CP4 transportation adapter already states this (`fortna_semantics/transportation.py`): objects may be display parts, motors, PEs, **or logical/memory placeholders**.

Many Jam_Zones logical refs resolve to Conveyor identities whose **`Type=INVALID`** (e.g. `ENABLE_SAWTOOTH`, `LATCH_SAWTOOTH`, `MEM_CP4_8_START`).  
That Type value means “not a mechanical conveyor drawing type” — **not** “reference is void.”  
Void/absent is the literal selection **`INVALID`**.

| Concept | Meaning |
|---------|---------|
| Selection `INVALID` | Explicit absent — keep as absent |
| Conveyor row with `Type=INVALID` but real `IO_Name` | Logical/internal/memory (or spare) **named object** — still a valid reference target |
| Conveyor row `Type=MOTOR` / `PHOTOCELL` / `STRAIGHT` / … | Physical or device-class object |
| `timemenu` identity | Timer logical object |
| `Machine` identity | Controller/owner |
| `StartStopZones` identity | Zone state-machine row |
| `horns` identity | Horn object |

---

## Jam_Zones field → target class matrix

Schema source: `fortna.mnu` Jamzones DLIST (also `artifacts/mnu-relationships.json`).  
Resolved examples: `artifacts/fortna-reference-graph-plc5.json` (Jamzones edges).

| UI / ASC field | Schema target menu | Target class | Example values (validation RUN) | Notes |
|----------------|--------------------|--------------|----------------------------------|-------|
| Latch Bit | **Conveyor** | logical/internal (often Type=INVALID) or device | `LATCH_SAWTOOTH`, `LATCH_TAKEAWAY` | CP3 RESOLVED → Conveyor |
| Jammed Bit | **Conveyor** | logical/internal | `JAM_SAWTOOTH`, `JAM_CITY_COUNTER` | CP3 RESOLVED → Conveyor |
| Start Stop Timer | **timemenu** | timer | `tmStartStop_SAWTOOTH` | CP3 RESOLVED → timemenu |
| Zone Owner | **Machine** | machine/owner | `ORNCCP4`, `ORNCCP5` | trailing space in schema name `Zone Owner ` |
| Enable Bit | **Conveyor** | logical/internal | `ENABLE_SAWTOOTH`, `ENABLE_CP1_ACCUM` | UI examples like `CP3_ENABLE` are the same class |
| Start Button | **Conveyor** | logical/memory **or** physical PB | `MEM_CP4_8_START`, `SAWTOOTH_START_MEM_BIT`, `1PBSTART` | Type may be INVALID (mem) or PROXPART/STRAIGHT (PB) |
| Stop Button | **Conveyor** | logical/memory **or** physical PB | `MEM_CP4_8_STOP`, `1PBSTOP` | same |
| Reset Button | **Conveyor** | physical PB, logical, or **INVALID** | `PB406_JR`, `SORTER_PB_RESET`, **`INVALID`** | INVALID = explicit absent |
| StartStopZone | **StartStopZones** | zone state machine | `SHIPPING AREA`, `SAWTOOTH, CITY, DANCE` | |
| Start/Stop Request Flag | (numeric/flag fields) | commissioning / runtime | — | not DLIST selections |

**INACTIVE / spare Jamzones rows** use `Zone Name=INVALID` and field selections `INVALID` — treat entire row inactive; do not promote.

---

## Motor_Chains (Mtrchain) field → target class matrix

| UI / ASC field | Schema target menu | Target class | Example values | Notes |
|----------------|--------------------|--------------|----------------|-------|
| Motor_Name | row identity (Conveyor-family name) | motor device **or** logical head | `M116` (Type=MOTOR); logical heads may be Type=INVALID | Identity column; UI may show names like `VFD####_STOP` on other sites |
| Motor_Ndx | **Conveyor** | motor / index object | `M116`, `VFD414` | DLIST → Conveyor |
| Timer_Name | **timemenu** | timer | `tmLATCH_4CR2_ACCUM`, `tmM206` | |
| RUN Timer_Name | **timemenu** | timer | `tmRUN_tmM206` | |
| Motor_Chained1..10 | **Conveyor** | physical conveyor, SSV/hold, or **INVALID** | `P116`, `SSVEZPE212_P1`, `INVALID` | INVALID = empty slot |
| Motor_Aux | **Conveyor** | aux / latch logical or motor aux | `M209_AUX`, `LATCH_BIN_MERGE` | |
| Enabled | **Conveyor** | enable ref | `M116_AUX`, `VFD414_AUX` | |
| GoUntil | **Conveyor** | go-until ref or INVALID | | |
| Horn | **horns** | horn object | `CP5 & WH816 HORN`, `NO HORN` | |
| Heater Bit | **Conveyor** | heater ref | | |
| Heater Error | **Errors** | error object | | |
| Stop Zone | **Jamzones** | jam zone ref | | |

Curtis UI examples (`Motor_Name=VFD1542_STOP`, chains `P1542/CR1541/M228/SSV226/INVALID`) match this **class model**; those exact names are not required to exist on Greensboro PLC5 RUN.

---

## Does CP3 already cover these fields?

**YES** for schema + resolution:
- Jamzones: Latch Bit, Jammed Bit, Start Stop Timer, Zone Owner, Enable Bit, Start/Stop/Reset Button, StartStopZone — all present as CP3 edges with `datatypeName=SELECTION_UNIQUE`, `provenance=SOURCE_PROVEN` when values resolve.
- Mtrchain: Motor_Ndx, Timer_Name, RUN Timer_Name, Motor_Chained*, Motor_Aux, Enabled, Horn, Stop Zone, etc.

**Partial** for product semantics:
- CP4 `jam.py` adapter currently focuses on **Jamcheck** columns, not a first-class Jamzones logical-signal object model.
- CP4 `mtrchain.py` keeps chained/aux refs but does not classify Conveyor targets into physical vs logical/memory vs timer.
- No production CP1–CP4 change is made here — this doc defines the model for later packs.

---

## Does the current compiler lose non-physical references?

**Yes, on the SiteModel → Autogen equipment path — risk is real:**

1. `fortna_knowledge.py` inactive rules can treat Conveyor `Type=INVALID` as **INACTIVE** when table knowledge says so — that drops logical catalog rows from “active equipment.”
2. `fortna_sitemodel_to_autogen.py` `disposition_for_equipment` labels non-`P###` / non-mechanical types as `NOT_MECHANICAL_CONVEYOR` or `UNSUPPORTED_TYPE` — correct for belt emit, **wrong if Jam_Zones/Mtrchain logical refs must round-trip**.
3. Transport freeze correctly refuses to invent adjacency from these names — good.
4. CP3/CP4 transportation adapter **retains** Conveyor-family identities including logical ones when they appear as reference targets — good for evidence, not yet wired into a LogicalSignalModel emit path.

**Rule for future compilers:** consume **LogicalSignalModel** references as opaque named targets (menu+identity). Never require `Type∈{STRAIGHT,CURVE,…}` for a Jam/Mtrchain selection to be valid. Never replace `INVALID` with a guessed BOOL.

---

## Greenfield / brownfield (Gate K preview)

LogicalSignalModel entries may originate from RUN **or** engineer assignment. Downstream PLC program packs must not branch on origin — only on whether the canonical reference is PROVEN / ENGINEER_ASSIGNED vs INVALID / UNKNOWN.
