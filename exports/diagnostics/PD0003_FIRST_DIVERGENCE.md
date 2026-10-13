# PD-0003 FIRST DIVERGENCE — Fast_Conv vs Safety emit

**BASE SHA:** `a935a22a86f93dceb0f3910d9f5c8f506a0c1a27`  
**GOLD L5X:** `MSCRENOPICK_2026_10_13_1725.L5X`  
**SHA256:** `64cce43d57ee20fdaaa309021a0b6c6d81623e23c8dafbb39181a5ace6dcb0fa`  
**Branch:** `feature/io-generator-truth-cleanup`  
**Status:** DIAGNOSIS ONLY — no production repair in this step

---

## Observed coexistence (same L5X)

| Fact | Evidence |
|---|---|
| Conv_Fast entirely NOP | 29× `NOP();` with PD-0003 comment; 0× `Fast_Conv(` |
| Safety emit succeeds | `Area_Test1_ESZone1_Safe_Logic`, `Area_Test1_ESZone1_Safe_PI` |
| Members emitted | ESPB2, ESPB24, ESPB32, ESLS2 |
| Area_UDT | `Area_Test1` present |

---

## Workbook / binding state (Curtis live project)

| Object | Value |
|---|---|
| Transport Area | `MSCRENOPICK_Area` (29 conveyors) |
| Conveyor `safety_zone` | **all 29** → `MSCRENOPICK_ESZone1` |
| `MSCRENOPICK_ESZone1` members | **none** (omitted incomplete) |
| Engineer Safety zone | `Area_Test1_ESZone1` |
| Engineer Area | `Area_Test1` / plc_symbol `Area_Test1` |
| Zone members | ESPB2, ESPB24, ESPB32, ESLS2 |
| Zone conveyors | **[]** |

---

## Trace (stage by stage)

```
RUN / Transport
  → conveyors.main_area = MSCRENOPICK_Area
  → conveyors.safety_zone = MSCRENOPICK_ESZone1
Engineer Safety Apply
  → Area_Test1_ESZone1 members=4, area=Area_Test1, conveyors=[]
ES compiler
  → PI-writer zones = {Area_Test1_ESZone1}  (members+area)
  → MSCRENOPICK_ESZone1 omitted (no members)
Rebind (fortna_autogen ~6600)
  → bind conveyor→writer zone only if:
       (a) conveyor ∈ zone.conveyors  → FAIL (empty)
    or (b) conveyor.area == zone.area → FAIL (MSCRENOPICK_Area ≠ Area_Test1)
Fast_Conv scrub (_scrub_motion_safety_zone_refs)
  → requires item.safety_zone ∈ _pi_writer_zones
  → MSCRENOPICK_ESZone1 ∉ writers → NOP + PD-0003
```

---

## Answers A–E

**A. What does Fast_Conv require for Safety ready?**  
`item["safety_zone"]` must be in `_pi_writer_zones` — a SafetyZoneIR with **members + area** that will emit Safe_PI (not a legacy `{Area}_Safe` invent).

**B. Where is that property produced?**  
Early `build_safety_zone_irs` in `fortna_autogen.build_l5x` (~6542–6593), then used by `_scrub_motion_safety_zone_refs` (~6706).

**C. Is Safety producing equivalent truth under another name?**  
Yes — `Area_Test1_ESZone1` **is** a PI-writer zone and emits Safe_Logic/Safe_PI. It is a **different Area identity** than the conveyors’ Transport Area / safety_zone.

**D. Failure class**  
**AREA_IDENTITY_MISMATCH / MISSING_CONVEYOR↔SAFETY FK**  
Not: naming typo on `_Safe`, stale SHA, or missing invent of `_Safe`.  
PD-0003 withholding for `MSCRENOPICK_ESZone1`-bound conveyors is **truthful**.

**E. Why Safe_Logic/Safe_PI can emit while Fast_Conv says unresolved?**  
ES emit is **zone-centric** (ready zones with members).  
Fast_Conv scrub is **conveyor-centric** (each conveyor’s `safety_zone` must be a PI-writer).  
Those sets currently do not intersect for the 29 Transport conveyors.

---

## Required invariant (mission) vs current truth

> If an operational Area has a persisted Safety zone accepted by the Safety generator,  
> Transport and Fast_Conv must consume the same canonical Safety identity.

Current project has **two Areas**:
- `Area_Test1` — has accepted Safety, **zero conveyors**
- `MSCRENOPICK_Area` — has 29 conveyors, Safety zone shell **without members**

Auto-binding `Area_Test1_ESZone1` onto `MSCRENOPICK_Area` conveyors would **invent** a cross-Area Safety FK the engineer did not persist. That violates “no invented physical/Safety facts” unless product policy explicitly says project-level Safety covers all Areas.

---

## STOP — GENERATOR_CONTRACT_GAP (policy)

**Question for Curtis/Gilfoyle (smallest controls question):**

When engineer Safety members are assigned on `Area_Test1_ESZone1` but all Transport conveyors remain on `MSCRENOPICK_Area` / `MSCRENOPICK_ESZone1`, should Site Forge:

1. **Keep PD-0003 withhold** (current truthful behavior) until conveyors are linked to a member-bearing zone / Area, or  
2. **Define a generic rebind rule** (e.g. sole operational PI-writer zone in project covers unresolved Transport shells), with explicit engineer confirmation?

Until that policy is answered, **do not patch Fast_Conv** and **do not invent `_Safe`**.

---

## Files / code pointers

- `tools/scripts/fortna_autogen.py` `_pi_writer_zones` ~6542  
- rebind ~6600–6652  
- `_scrub_motion_safety_zone_refs` ~6706–6749  
- Gold evidence: `exports/diagnostics/gold_baseline_20261013_1725/`  
- Probe JSON: `exports/diagnostics/overnight_io_pd0003_probe.json`
