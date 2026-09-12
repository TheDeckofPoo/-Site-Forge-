# CP4 Pass 1 — Conveyor Realization Audit

Generated: 2026-09-12T07:23:26.430584+00:00

**Finished PLC4 inspected: NO**

## Headline

- Discovery mechanical equipment: **76**
- Pass1 generated conveyors: **80**
- Extras (generated ∉ discovery): `['P1200', 'P1202', 'P1206', 'P1208']`
- Acceptance: **NOT_ACCEPTED**

## Reconciliation equation

```
76 discovered mechanical
+ 0 legitimate non-mechanical generated
- 0 excluded/non-conveyor mechanical
= 76 expected
actual generated = 80
delta = 4
proven = False
```

76 discovery mechanical + 0 legitimate non-mechanical helpers = 76, but Pass1 generated 80. Extras ['P1200', 'P1202', 'P1206', 'P1208'] are DERIVED_ALIAS inclusions from load_from_run prefix linkage (e.g. P120 → P1200), not legitimate CP4-owned discovery entities. Equation not proven.

## Why the four extras exist (RUN evidence)

P1200, P1202, P1206, P1208 are **mechanical** rows in `Conveyor.asc` (STRAIGHT/BELT with X/Y/Length), but:

- `Machine_Name` blank
- `IO_Address_Word=6000` (placeholder — not on ORNCCP4 EIP map)
- `belongs_to_controller` / discovery ownership → **excluded** from the frozen 76
- Pass1 `load_from_run` still emitted them because linked-conveyor matching uses prefix rules against owned `P120` (VFD120-linked, in discovery)
- `merge_discovery_conveyors` then **kept** all load_from_run rows plus discovery

Classification: **DERIVED_ALIAS** (not legitimate CP4 discovery entities).

Do **not** remove/add equipment solely to force 76=80. Fix ownership/merge rules in a later pass if desired; this audit only explains the delta.

## Classification counts (generated)

- `DERIVED_ALIAS`: 4
- `RUN_MECHANICAL`: 76

## Per-conveyor (generated only)

| Conveyor | Class | In discovery | Reason |
|---|---|---|---|
| P100 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P100A | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P102 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P104 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P106 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P108 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P110 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P112 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P114 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P116 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P118 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P120 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P1200 | DERIVED_ALIAS | N | Conveyor.asc mechanical row exists but discovery excluded it; Pass1 kept it from load_from_run via prefix linkage to P12 |
| P1202 | DERIVED_ALIAS | N | Conveyor.asc mechanical row exists but discovery excluded it; Pass1 kept it from load_from_run via prefix linkage to P12 |
| P1206 | DERIVED_ALIAS | N | Conveyor.asc mechanical row exists but discovery excluded it; Pass1 kept it from load_from_run via prefix linkage to P12 |
| P1208 | DERIVED_ALIAS | N | Conveyor.asc mechanical row exists but discovery excluded it; Pass1 kept it from load_from_run via prefix linkage to P12 |
| P200 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P200A | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P202 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P204 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P206 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P208 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P209 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P210 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P211 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P212 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P213 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P214 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P215 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P216 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P217 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P218 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P219 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P219A | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P226 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P229 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P231 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P231A | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P300 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P300A | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P302 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P304 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P305 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P306 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P308 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P408 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P410 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P412 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P414 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P416 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P418 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P420 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P422 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P424 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P424A | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P426 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P428 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P430 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P432 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P434 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P436 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P438 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P446 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P447 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P448 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P450 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P452 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P454 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P456 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P462 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P818 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P820 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P822 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P824 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P826 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P828 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P830 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P832 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P834 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
| P836 | RUN_MECHANICAL | Y | Present in frozen cp4-discovery mechanical equipment set |
