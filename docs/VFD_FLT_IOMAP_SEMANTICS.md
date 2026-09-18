# VFD_FLT → Motor_Starter_UDT.Flt.PS_Flt semantics

**Status:** PRESERVE mapping implemented in `fortna_autogen._vfd_ms_member`  
**Audit date:** 2026-09-18 (reconciled to library datatype)  
**Firewall:** finished PLC is validation only

## Mapping (generic rule)

```
VFD###_FLT / HAS FAULTED  →  P###_VFD.Flt.PS_Flt
```

Implemented in `fortna_autogen._vfd_ms_member` (`FLT` / `FAULT` / `FAULTED` / …).

## Evidence

### Library UDT (`OReilly_Library_v3.L5X`)

`Motor_Starter_UDT.Flt` resolves to **`PS_Fault`**, members:

| Member | Role |
|--------|------|
| `PS_Flt` | Primary discrete fault BOOL |
| `PS_FltTmr` | Fault timer |

There is a separate datatype `Motor_Starter_Flt` with `Overload` / `Contactor` in the library, but that is **not** what `Motor_Starter_UDT.Flt` points at. IO_MAP must use `.Flt.PS_Flt`.

### RUN (CP4 `Conveyor.asc`)

| Field | Example |
|-------|---------|
| `IO_Name` | `VFD118_FLT`, `VFD216_FLT`, … |
| `General_Description` | `VFD118 HAS FAULTED` |
| `Type` | often blank / `INVALID` (not usable for member selection) |

So the semantic label in RUN is **HAS FAULTED**, not a typed “overload relay” enum. The discrete fault feedback maps onto `Flt.PS_Flt`.

### Contactor fault

Only map to contactor-shaped members when the Fortna suffix is explicitly contactor-fault shaped (`CONT_FLT`, `CONTACTOR_FLT`, …). Do **not** invent bare BOOLs for IO_MAP validation.

## Verdict

**Keep** `VFD###_FLT` → `P###_VFD.Flt.PS_Flt`.

Cross-table evidence + library datatype semantics agree: HAS FAULTED is the discrete VFD fault point, and `Flt.PS_Flt` is the UDT’s primary fault member on `Motor_Starter_UDT`.
