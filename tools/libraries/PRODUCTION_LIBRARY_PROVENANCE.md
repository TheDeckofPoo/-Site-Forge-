# Production library provenance inventory (PD-0038)

Generated for PLC5 blind-test quarantine prep. Finished Greensboro controller
context exports are validation oracles unless independent evidence proves they
are approved generic Fortna library artifacts.

| File | Classification | Action | Controller Name |
|------|----------------|--------|-----------------|
| `AOI_SNTP_QUERY_AOI.L5X` | FINISHED_SITE_DERIVED | QUARANTINE | `ORLY_Greensboro_NC_PLC2` |
| `Enc_Routine_ST.L5X` | FINISHED_SITE_DERIVED | QUARANTINE | `ORLY_Greensboro_NC_PLC5` |
| `OReilly_Library_v3.L5X` | APPROVED_GENERIC | KEEP | `Library` |
| `programs/Sawtooth_Merge_DataTypes.L5X` | UNKNOWN_CONTROLLER | REVIEW | `Sawtooth_Merge_DataTypes` |
| `programs/Sawtooth_Merge_Program.L5X` | FINISHED_SITE_DERIVED | QUARANTINE | `ORLY_Greensboro_NC_PLC4` |
| `programs/ShippingSorter_Area_L3_Program.L5X` | FINISHED_SITE_DERIVED | QUARANTINE | `ORLY_Greensboro_NC_PLC5` |
| `programs/Sorter_Track_Program.L5X` | FINISHED_SITE_DERIVED | QUARANTINE | `ORLY_Greensboro_NC_PLC5` |
| `programs/WCS_Interface_TCP_IP_Program.L5X` | FINISHED_SITE_DERIVED | QUARANTINE | `ORLY_Greensboro_NC_PLC5` |
| `Slow_Flt_AOI.L5X` | APPROVED_GENERIC | KEEP | `SiteForge_AOI_Library` |
| `TRK_Divert_WaveFunction_AOI.L5X` | FINISHED_SITE_DERIVED | QUARANTINE | `ORLY_Greensboro_NC_PLC5` |
| `validation_oracles/IO_MAP_Program.L5X` | VALIDATION_ORACLE | quarantined | `n/a` |
| `validation_oracles/Sys_Program.L5X` | VALIDATION_ORACLE | quarantined | `n/a` |
| `validation_oracles/System_Program.L5X` | VALIDATION_ORACLE | quarantined | `n/a` |

## Quarantine policy

- `VALIDATION_ORACLE` / `FINISHED_SITE_DERIVED` → `tools/libraries/validation_oracles/`
- Production Autogen must not load quarantined files under any flag
- Missing generic contracts → capability `REVIEW_REQUIRED`
