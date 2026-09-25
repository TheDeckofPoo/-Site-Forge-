# Validation oracles (not production)

Finished-site controller program exports quarantined for Warden / parity validation only.

**Never** load these files from production Autogen / compiler paths.

| File | Origin | Role |
|------|--------|------|
| `Sys_Program.L5X` | Greensboro PLC5 finished export | Validation oracle only |
| `System_Program.L5X` | Greensboro PLC2 finished export | Validation oracle only |
| `IO_MAP_Program.L5X` | Greensboro PLC5 finished export | Validation oracle only (PD-0036) |

Production System program emission uses:

- active RUN (RIO / device inventory)
- `tools/libraries/OReilly_Library_v3.L5X` (generic AOIs / UDTs)
- `tools/libraries/CommDiag_UDT.L5X` (generic datatype contract)
- engineer intent

If NTP / System_Logic cannot be derived from those sources, Autogen emits `REVIEW_REQUIRED` stubs — it must not cookie-cut these quarantined packs.
