# VFD_FLT → Motor_Starter_UDT.Flt.Overload semantics

**Status:** PRESERVE mapping from commit `8d44f9b`  
**Audit date:** 2026-09-13  
**Firewall:** finished PLC is validation only

## Mapping (generic rule)

```
VFD###_FLT / HAS FAULTED  →  P###_VFD.Flt.Overload
```

Implemented in `fortna_autogen._vfd_ms_member` (`FLT` / `FAULT` / `FAULTED` / …).

## Evidence

### Library UDT (`OReilly_Library_v3.L5X`)

`Motor_Starter_Flt` members:

| Member | Role |
|--------|------|
| `Overload` | Primary discrete fault BOOL (library doc: Motor Overload Fault) |
| `Contactor` | Separate contactor-fault BOOL |

There is **no** `Flt.Faulted` / `Flt.HasFaulted` member. The faceplate fault latch for motors and VFDs sharing `Motor_Starter_UDT` is `Flt.Overload`.

### RUN (CP4 `Conveyor.asc`)

| Field | Example |
|-------|---------|
| `IO_Name` | `VFD118_FLT`, `VFD216_FLT`, … |
| `General_Description` | `VFD118 HAS FAULTED` |
| `Type` | often `INVALID` (not usable for member selection) |

So the semantic label in RUN is **HAS FAULTED**, not a typed “overload relay” enum. The library UDT collapses that discrete fault feedback onto the single primary fault member `Flt.Overload`.

### Contactor fault

Only map to `Flt.Contactor` when the Fortna suffix is explicitly contactor-fault shaped (`CONT_FLT`, `CONTACTOR_FLT`, …). Do **not** invent bare BOOLs for IO_MAP validation.

## Verdict

**Keep** `VFD###_FLT` → `P###_VFD.Flt.Overload`.

Cross-table evidence + library datatype semantics agree: HAS FAULTED is the discrete VFD fault point, and `Flt.Overload` is the UDT’s primary fault member. Differing finished-PLC layouts are validation-only and do not override this generic rule unless Fortna docs define a different member.
