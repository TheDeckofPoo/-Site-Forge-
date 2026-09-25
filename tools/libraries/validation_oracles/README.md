# Validation oracles (not production)

Finished-site controller program exports quarantined for Warden / parity validation only.

**Never** load these files from production Autogen / compiler paths.

| File | Origin | Role |
|------|--------|------|
| `Sys_Program.L5X` | Greensboro PLC5 finished export | Validation oracle only |
| `System_Program.L5X` | Greensboro PLC2 finished export | Validation oracle only |
| `IO_MAP_Program.L5X` | Greensboro PLC5 finished export | Validation oracle only (PD-0036) |
| `AOI_SNTP_QUERY_AOI.L5X` | Greensboro PLC2 AOI fragment | Validation oracle only (PD-0038) |
| `Enc_Routine_ST.L5X` | Greensboro PLC5 | Validation oracle only (PD-0038) |
| `TRK_Divert_WaveFunction_AOI.L5X` | Greensboro PLC5 | Validation oracle only (PD-0038) |
| `Sorter_Track_Program.L5X` | Greensboro PLC5 | Validation oracle only (PD-0038) |
| `WCS_Interface_TCP_IP_Program.L5X` | Greensboro PLC5 | Validation oracle only (PD-0038) |
| `ShippingSorter_Area_L3_Program.L5X` | Greensboro PLC5 | Validation oracle only (PD-0038) |
| `Sawtooth_Merge_Program.L5X` | Greensboro PLC4 | Validation oracle only (PD-0038) |

See also `../PRODUCTION_LIBRARY_PROVENANCE.md`.

Production System program emission uses:

- active RUN (RIO / device inventory)
- `tools/libraries/OReilly_Library_v3.L5X` (generic AOIs / UDTs)
- `tools/libraries/CommDiag_UDT.L5X` (generic datatype contract)
- engineer intent

If NTP / System_Logic cannot be derived from those sources, Autogen emits `REVIEW_REQUIRED` stubs — it must not cookie-cut these quarantined packs.
