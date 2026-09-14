# ES Template Investigation — Site Forge vs PLC4/PLC5 Pattern

**Date:** 2026-09-14  
**Scope:** Read-only comparison of Site Forge E-stop (ES) generation against accepted PLC4/PLC5 pattern.  
**Oracle:** PLC4 / PLC5 finished L5X (not PLC2).  
**Explicit:** No ES compiler implementation was done in this investigation.

---

## 1. What Site Forge currently emits for ES

### Emitted today (partial scaffolding only)

| Artifact | Status | Where |
|----------|--------|--------|
| `ES` program | **Not emitted** | Generated L5X program lists are Area Fast/Slow/L1/L2 + Sys/IO_MAP/System — never `ES` |
| `{Area}_Safe` / `{ESZone}` tags (`ES_Zone_UDT`) | **Emitted** | Cloned from library `Main_Area_Safe` |
| `safety_zone` arg on `Fast_Conv` | **Emitted** | Metadata wire into conveyor AOIs |
| Default zone names | **Emitted (placeholder)** | `{AreaSans_Area}_ESZone1` inferred from Area list |
| `ES_SIL1_Cat1` / `ES_PI20` AOI defs | **Present in library only** | Encoded AOIs ship with `OReilly_Library_v3.L5X`; not called by generated logic |
| Device tags (`ES###`, `ESR`, `MCR`, `*_AOI`) | **Not generated as ES members** | No Safe_Logic/Safe_PI call sites |
| Task schedule for `ES` | **Missing** | No `ScheduledProgram Name="ES"` in current exports |

Evidence from current/autogen results:

- `exports/autogen/LATEST.json` programs: `ORNCCP2_Area_Slow/Fast/L1/L2`, `System`, `Sys`, `IO_MAP` — **no ES**
- `exports/current/` L5X: **no** `Program Name="ES"`, `Safe_Logic`, `Safe_PI`, or `ES_SIL1_Cat1(` call sites
- `docs/TASK_PROGRAM_ARCHITECTURE.md`: documents current Autogen emit as Area Fast/Slow/L1/L2 + Sys/IO_MAP — safety class is conceptual only
- `tools/libraries/programs/`: **no** `ES_Program.L5X` (unlike Sys, IO_MAP, Sawtooth_Merge, Sorter_Track)
- `OPTIONAL_PROGRAMS` / `ALWAYS_PROGRAMS` in `fortna_autogen.py`: **ES not listed**

### Related model / gate code (no L5X emit)

| Piece | Role | Generates ES logic? |
|-------|------|---------------------|
| `fortna_estop_model.py` `build_estop_model` | Devices / circuits / zones from `EStop.asc`; `safety_generation_gate` | **No** — blocks until membership proven |
| `fortna_site_model.py` `ensure_default_estop_zone` | Seeds `EStop_Zone_1`, `generation_allowed=False` | **No** |
| `fortna_cp5_blind_build.py` | `safety_zones` capability `generatable=False` | **No** |
| `fortna_area_ops.py` | Defaults `safety_zone` to `{Area}_ESZone1` when unset | Metadata only |
| `fortna_autogen.py` `load_from_run` | `safety_zones=[f"{a.replace('_Area','')}_ESZone1" for a in areas]` | **Infers zone from Area name** |

### Library template (not Site Forge generation)

`tools/libraries/OReilly_Library_v3.L5X` contains a **scaffold** `Program ES` with Excel-style names:

- Routines: `Main_Area_Safe_Logic`, `Main_Area_Safe_PI`, `Main_Routine`
- Calls: `ES_SIL1_Cat1(ES3000_AOI,…)`, `ES_PI20(Main_Area_Safe_ES_PI,Main_Area_Safe,…)`
- JSR: `JSR(Main_Area_Safe_PI,0)` / `JSR(Main_Area_Safe_Logic,0)`
- Naming uses `Main_Area_Safe` / `ES_Area`, **not** `{Area}_{ESZone}` pattern from finished PLC4/5

This template is **not** merged into Site Forge outputs today.

---

## 2. PLC4 / PLC5 reference pattern evidence

### Oracle files

| Controller | Path |
|------------|------|
| **PLC4** | `C:\Users\curtiskricke\Desktop\ORielly Green\2 PLC4\ORLY_Greensboro_NC_PLC4S.L5X` |
| **PLC5** | `C:\Users\curtiskricke\Desktop\ORielly Green\3 PLC5\ORLY_Greensboro_NC_PLC5S.L5X` |
| Inventory note | `docs/gold_plc245_inventory.json` lists both with program `"ES"` |
| Harvested rung (PLC4) | `exports/_sawtooth_rungs.txt` |

PLC2 finished (`workspace/validation/ORLY_GreensboroPLC2_NC_Finished.L5X`) has the same structural family but was **not** used as the pattern oracle per task.

### PLC5 — clean target match (preferred oracle)

**Program:** `ES` · **Main_Routine:**

```
JSR(Redroom_ESZone1_Safe_Logic,0);
JSR(ShippingSorter_ESZone1_Safe_Logic,0);
JSR(Redroom_ESZone1_Safe_PI,0);
JSR(ShippingSorter_ESZone1_Safe_PI,0);
```

→ Exactly **one Safe_Logic + one Safe_PI per Safety Zone**.

**Safe_Logic example** (`Redroom_ESZone1_Safe_Logic`):

```
ES_SIL1_Cat1(ES812_AOI,ES812,Redroom_Area,Redroom_ESZone1.PI.Reset,Redroom_ESZone1.PI.Silence);
```

(plus site-specific ESR high/low fault timer rungs — engineer/site logic beyond core SIL1 calls)

**Safe_PI example** (`Redroom_ESZone1_Safe_PI`):

```
ES_PI20(Redroom_ESZone1_ES_PI,Redroom_ESZone1,CP5_MCR1,CP5_ESR3,…,NO_ESLS,…);
XIC(Redroom_Area.Reset)OTE(Redroom_ESZone1.PI.Reset);
XIC(Redroom_Area.Silence)OTE(Redroom_ESZone1.PI.Silence);
XIC(Redroom_ESZone1_ES_PI.O_Silenced_Tripped)OTE(Redroom_ESZone1.PI.Silenced_Tripped);
```

(also `O_Tripped` → `PI.Tripped`, `O_ESPX_Not_OK` → `PI.ESPX_Not_OK` in PLC4; same family)

**ShippingSorter zone** packs 16 real devices into **one** `ES_PI20` (slots pad with `NO_ESLS`) — confirms finite-20 aggregator model; multi-aggregator-per-zone is architectural room, not exercised with a second AOI instance on these gold sites.

### PLC4 — same pattern, incomplete Main_Routine JSR set

**Zones / routines present:**

| Zone | Safe_Logic | Safe_PI | Main_Routine JSR Logic | Main_Routine JSR PI |
|------|------------|---------|------------------------|---------------------|
| `Sawtooth_ESZone1` | yes | yes | **yes** | **yes** |
| `SawtoothNewLane_ESZone1` | yes | yes | **yes** | **yes** |
| `Sawtooth_ESZone2` | yes | yes | **no** | **yes** |
| `ModuleA_ESZone1` | yes | yes | **no** | **yes** |
| `ModuleA_ESZone2` | yes | yes | **no** | **yes** |

**Example rung** (`SawtoothNewLane_ESZone1_Safe_Logic`):

```
ES_SIL1_Cat1(ES215_AOI,ES215,SawtoothNewLane_Area,SawtoothNewLane_ESZone1.PI.Reset,SawtoothNewLane_ESZone1.PI.Silence);
```

(from harvest `exports/_sawtooth_rungs.txt`; gold file also has CP8_MCR1 / ESR family members)

**Naming convention (accepted):**

- Routines: `{AreaPrefix}_{ESZone}_Safe_Logic` / `{AreaPrefix}_{ESZone}_Safe_PI`
- Aggregator tag: `{AreaPrefix}_{ESZone}_ES_PI` (`ES_PI20`)
- Zone UDT tag: `{AreaPrefix}_{ESZone}` (`ES_Zone_UDT`)
- Area source: `{Area}.Reset` / `{Area}.Silence` → `{ESZone}.PI.*`

**Membership note:** Multiple ES zones can share one Area (`ModuleA_ESZone1` + `ModuleA_ESZone2`; `Sawtooth_ESZone1` + `Sawtooth_ESZone2`). CityCounter Area exists on PLC4 **without** an ES zone pair — zones are **not** 1:1 with Areas and must not be inferred from Area name alone.

---

## 3. MATCH / PARTIAL / WRONG / MISSING vs target architecture

Target:

- Program `ES`
- Main_Routine: JSR one Safe_Logic + one Safe_PI per Safety Zone  
  `JSR(<Area>_<ESZone>_Safe_Logic,0)` / `JSR(<Area>_<ESZone>_Safe_PI,0)`
- Safe_Logic: one `ES_SIL1_Cat1` per proven E-stop/ESR/MCR member
- Safe_PI: aggregate via `ES_PI20` (multi-aggregator if >20)
- Mappings: Area.Reset/Silence → SZ.PI.*; ES_PI outputs → SZ.PI.*
- Model: `SafetyZone{name, area, members[], resetSource, silenceSource, aggregatorGroups[]}`
- Membership from proven RUN/config or engineer — **not** Area-name inference

| Target element | Verdict | Site Forge today |
|----------------|---------|------------------|
| Program `ES` | **MISSING** | Never emitted / scheduled |
| Main_Routine JSR per zone (Logic+PI) | **MISSING** | No ES routines at all |
| Routine names `{Area}_{ESZone}_Safe_*` | **MISSING** | Library scaffold uses `Main_Area_Safe_*` only |
| `ES_SIL1_Cat1` per zone member | **MISSING** | AOI def in library; zero generated call sites |
| `ES_PI20` aggregator(s) per zone | **MISSING** | AOI def in library; no `{SZ}_ES_PI` tags emitted |
| Area.Reset → SZ.PI.Reset | **MISSING** | No Safe_PI mapping rungs |
| Area.Silence → SZ.PI.Silence | **MISSING** | No Safe_PI mapping rungs |
| ES_PI outputs → SZ.PI.* | **MISSING** | No mapping rungs |
| `ES_Zone_UDT` zone tags | **PARTIAL** | Tags cloned for workbook/default zones; unused by ES logic |
| Fast_Conv safety_zone wiring | **PARTIAL** | Passes zone tag into conveyor AOI only |
| `SafetyZone` conceptual model | **PARTIAL** | `fortna_estop_model` has devices/zones/membership gate; no `aggregatorGroups`, no compiler IR |
| Membership from proven RUN/engineer | **PARTIAL** | Gate correctly blocks generation; defaults still invent `{Area}_ESZone1` |
| Membership **not** inferred from Area alone | **WRONG** | `load_from_run` + `fortna_area_ops` default `safety_zone` from Area name |
| Library ES scaffold as emit path | **WRONG** (if used as-is) | `Main_Area_Safe` / placeholder Inputs ≠ PLC4/5 `{Area}_{ESZone}` pattern |
| Multi `ES_PI20` per large zone | **MISSING** | No aggregator grouping logic (gold sites use one PI20 + `NO_ESLS` pad) |
| Safety task scheduling of `ES` | **MISSING** | Capability matrix marks safety zones non-generatable |

---

## 4. Exact compiler pieces required later

No ES compiler exists yet. Recommended pieces (names are proposed where unknown; existing hooks called out):

| Piece | Suggested location / existing hook | Responsibility |
|-------|-----------------------------------|----------------|
| SafetyZone IR | Extend `fortna_estop_model.py` (or new `fortna_es_compiler.py`) | `SafetyZone{name, area, members[], resetSource, silenceSource, aggregatorGroups[]}` |
| Membership resolver | `build_estop_model` + engineer workbook / site overrides | Proven RUN links or engineer assignment only; remove Area→ESZone default as generation truth |
| Generation gate | `safety_generation_allowed()` (exists) | Keep blocking until CONFIRMED/HIGH membership |
| ES program emitter | **New** — e.g. `emit_es_program()` in `fortna_autogen.py` or `fortna_es_compiler.py` | Build `Program ES` with Main_Routine + per-zone routines |
| Safe_Logic emitter | New | One `ES_SIL1_Cat1({dev}_AOI,{dev},{Area},{SZ}.PI.Reset,{SZ}.PI.Silence)` per member |
| Safe_PI emitter | New | Chunk members into `ES_PI20` groups (≤20); pad `NO_ESLS`; emit Reset/Silence/Tripped/Silenced_Tripped/ESPX_Not_OK maps |
| Tag factories | Extend `build_l5x` tag section | `{SZ}` (`ES_Zone_UDT`), `{SZ}_ES_PI` / `_ES_PI2…` (`ES_PI20`), `{dev}` + `{dev}_AOI` (`ES_SIL1_Cat1`), `NO_ESLS` |
| Optional program pack | `tools/libraries/programs/ES_Program.L5X` **or** fully synthetic emit | Prefer synthetic from IR (library scaffold naming is wrong) |
| Autogen wiring | `ALWAYS_PROGRAMS` / generate path / task schedule | Include `ES` when gate allows; `ScheduledProgram Name="ES"` on safety task |
| Capability matrix | `fortna_cp5_blind_build.py` / discovery contract | Flip `safety_zones` to generatable only when IR + gate pass |
| Area ops cleanup | `fortna_area_ops.py`, `load_from_run` | Stop treating `{Area}_ESZone1` as proven membership |

**Do not** treat PLC2-only quirks or library `Main_Area_Safe_*` names as the emit contract. Use PLC5 Main_Routine completeness + PLC4 multi-zone-per-area naming as the oracle.

---

## 5. Explicit investigation status

**No implementation was done in this investigation.**  
This document is evidence-only. No ES compiler, no program emit changes, no library renames, and no Site Forge code modifications were made.

---

## Key file paths

### Site Forge / Autogen
- `C:\Dev\worktree\FortnaPlus\tools\scripts\fortna_autogen.py`
- `C:\Dev\worktree\FortnaPlus\tools\scripts\fortna_estop_model.py`
- `C:\Dev\worktree\FortnaPlus\tools\scripts\fortna_site_model.py`
- `C:\Dev\worktree\FortnaPlus\tools\scripts\fortna_area_ops.py`
- `C:\Dev\worktree\FortnaPlus\tools\scripts\fortna_cp5_blind_build.py`
- `C:\Dev\worktree\FortnaPlus\tools\libraries\OReilly_Library_v3.L5X` (scaffold ES + AOIs)
- `C:\Dev\worktree\FortnaPlus\docs\TASK_PROGRAM_ARCHITECTURE.md`
- `C:\Dev\worktree\FortnaPlus\exports\autogen\LATEST.json`
- `C:\Dev\worktree\FortnaPlus\exports\_sawtooth_rungs.txt`

### PLC4 / PLC5 oracles
- `C:\Users\curtiskricke\Desktop\ORielly Green\2 PLC4\ORLY_Greensboro_NC_PLC4S.L5X`
- `C:\Users\curtiskricke\Desktop\ORielly Green\3 PLC5\ORLY_Greensboro_NC_PLC5S.L5X`
- `C:\Dev\worktree\FortnaPlus\docs\gold_plc245_inventory.json`

### Non-oracle (reference only)
- `C:\Dev\worktree\FortnaPlus\workspace\validation\ORLY_GreensboroPLC2_NC_Finished.L5X` (same pattern family; not the acceptance oracle)
