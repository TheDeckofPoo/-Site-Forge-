# Safety Baseline

Separate three concerns:

| Concern | Meaning |
|---------|---------|
| **Discovery** | RUN finds Safety-relevant devices (ES, ESR, MCR, ESLS, …) |
| **Membership** | Which devices belong to which Safety Zone |
| **Execution architecture** | How Program ES is structured and scheduled |

---

## Discovery

RUN / Safety tables / Conveyor IO can populate Device Inventory.

Unassigned devices are **valid**. They remain **UNASSIGNED / REVIEW_REQUIRED**.  
They must **not** block unrelated Transport/System PLC generation.  
They must **never** become accidentally permissive (`ES_OK = TRUE` by omission).

---

## Membership

Default: **ENGINEER_ASSIGNED** via Safety Build.

Do **not** infer membership from:

- numeric proximity  
- device/conveyor name similarity  
- drawing proximity  
- finished PLC  

Workflow:

1. Select devices in Device Inventory  
2. **Assign Selected → Zone** (or Assign Devices… wizard)  
3. Confirmation / immediate UI update  
4. **Apply Safety** to persist  
5. Autogen consumes `safety_build.zones[].members`

Fortna panel names like `4ES` map to Studio-legal tags (`CP4_ES`) at emit time — membership identity is preserved, tag legality enforced.

Reproduce: `python tools/scripts/test_safety_membership_handoff.py` · `test_live_canonical_handoff.py`

---

## Canonical handoff

```
Safety UI
  → SavedCanonical (workbook.safety_build)
  → EffectiveModel / IR (build_safety_zone_irs)
  → AutogenInput
  → PLC compiler
  → L5X
```

**Known field failure (fixed `60e62eb`):** empty `conveyors[]` early-return skipped `safety_build` → ORNCCP2 defaults.  
Do not reintroduce early-return before Safety Apply.

---

## Execution architecture (accepted series pattern)

| Element | Role |
|---------|------|
| Task `P01_Safety_20ms` | Schedules Program ES |
| Program `ES` | Safety execution pack |
| `Main_Routine` | JSR per ready zone |
| `<Zone>_Safe_Logic` | ES_SIL1_Cat1 per member |
| `<Zone>_Safe_PI` | ES_PI20 aggregation + PI maps |
| Required AOIs | ES_SIL1_Cat1, ES_PI20 (when members emit) |

**Shell vs complete:** NOP-only Main_Routine is fail-safe when membership unresolved — **not** Safety commissioning complete.

Reproduce: `python tools/scripts/test_es_compiler.py`

---

## Partial Safety

Configured zones with members may emit Safe_Logic/Safe_PI while other devices remain unassigned.  
Project buildability ≠ Safety commissioning completeness.
