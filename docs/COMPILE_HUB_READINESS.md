# Compile Hub Readiness + Apply-per-tab

**Status:** Active UX contract  
**Scope:** `dashboard/index.html`, `dashboard/fortna-plus.js`, `dashboard/subsystem-status.js`

---

## States

Each Compile hub card shows one of:

| State | Meaning |
|-------|---------|
| **NOT DETECTED** | No RUN evidence / no graph / subsystem absent |
| **DETECTED — REVIEW REQUIRED** | Evidence present; engineer must review and **Apply** on that tab (or unresolved fields remain) |
| **READY FOR AUTOGEN** | Tab Apply succeeded; safe to include in Export L5X |
| **CHANGED SINCE LAST APPLY** | Edited after Apply — re-Apply before Export |
| **ERROR / BLOCKED** | Hard gate (e.g. IO_MAP generate failure, sorter GENERATION NOT SUPPORTED) |

When **READY**, the card shows the **applied** timestamp.  
When **REVIEW REQUIRED**, unresolved counts are shown when known.

Cards: **Hardware / IO · Transportation · Sawtooth · Sorter · System / Core**

---

## Apply-per-tab workflow

```
Import RUN (I/O & Prints)
    ↓
Hardware / System → READY (mandatory packs)
    ↓
Transport Build → Apply (#tb-apply-autogen) → Transportation READY
Sawtooth Merge  → Apply (#btn-saw-save)     → Sawtooth READY
Sorter Build    → Apply (#btn-sorter-save)  → Sorter READY (when supported)
    ↓
Compile hub all required cards READY
    ↓
Export L5X Package
```

- Hub buttons **Apply Transport Build → workbook** and **Save workbook** live under **Advanced** only.
- **Save workbook to disk** is under Autogen **Advanced / Development**.
- Program pack checkboxes are not part of the normal flow (Advanced overrides only).

---

## How readiness is computed

Stored on `autogenState.readiness = { hardware, transport, sawtooth, sorter, system }`  
each `{ status, appliedAt, unresolved, detail, dirty }`.

| Card | DETECTED when | READY when |
|------|---------------|------------|
| Hardware / IO | RUN / workbook loaded | RUN loaded and last generate did not fail with IO_MAP/VFD errors |
| Transportation | Transport graph, transport workbook rows, merges, or conveyors | `#tb-apply-autogen` (or hub Advanced Apply) succeeded; not dirty |
| Sawtooth | SiteModel / editor has collector or lanes | Apply with zero `configuration_required`; not dirty |
| Sorter | Sorter evidence on SiteModel / editor | Apply with zero unresolved and not `NOT_SUPPORTED`; not dirty |
| System / Core | RUN loaded | Always READY after import (Sys · Device Comms · System Logic · System · IO_MAP forced on) |

Edits after Apply set `dirty` → **CHANGED SINCE LAST APPLY**.

---

## Program pack inclusion (evidence-driven)

**Always included:** Sys, Device Comms + NTP, System Logic, System, IO_MAP  
(`includeIoMap = true`, `noSys = false` — Advanced checkboxes cannot turn them off at generate).

| Pack | Included when |
|------|----------------|
| Sawtooth_Merge | Sawtooth card **READY** |
| Sorter_Track | Sorter card **READY** (no new sorter/WCS generation beyond pack include) |
| Merges | Present in workbook after Transport Apply |
| ShippingSorter / WCS | **NOT DETECTED / NOT SUPPORTED** unless SiteModel proves support (or Advanced override) |

---

## Build PLC preflight (PARTIAL BUILD CONTRACT)

On **Export L5X Package** (`runAutogenGenerate` / `autogenBuildPreflight`):

```
FOUND ≠ CONFIGURED ≠ INCLUDED ≠ GENERATED
UNASSIGNED ≠ ERROR ≠ INCLUDED ≠ GENERATED ≠ SAFE
```

| Hub status | Blocks Export? |
|------------|----------------|
| READY | No |
| REVIEW REQUIRED | **No** (soft review — Build ALLOWED) |
| NOT DETECTED | No |
| CHANGED SINCE LAST APPLY | Soft review (warn; does not hard-block like ERROR) |
| ERROR on mandatory (System/Hardware) or **INCLUDED** (Applied) pack | **Yes** |
| Safety ERROR (emit exception) | **Yes** |
| Safety REVIEW (unassigned devices / shell) | **No** |

### Incremental commissioning example

```
Transportation     READY              (small Area Applied)
Safety             REVIEW REQUIRED    (many devices unassigned)
Saw/Merge          NOT DETECTED/REVIEW (found, not Applied)
Sorter             NOT DETECTED
Hardware/I/O       READY
System             READY

BUILD PLC: ALLOWED
```

Report must still state Safety commissioning is incomplete (`COMMISSIONING READY = NO`).

Full contract: `exports/stabilization/partial_build_contract.md`  
Fixture: `tools/scripts/test_partial_build_acceptance.py`  
Offline index: `exports/stabilization/README.md`

---

## Related

- `exports/stabilization/partial_build_contract.md` — product law  
- `docs/REGRESSION_MANIFEST.md` — permanent tests  
- `docs/UX_PRINCIPLES.md` — Simple by default / Advanced when needed  
- `docs/UI_SUBSYSTEM_STATUS.md` — Legacy export status vocabulary  
- `docs/TRANSPORT_AUTOGEN_FROZEN.md` — Transport compiler freeze (UI Apply only here)
