# Production library provenance inventory (PD-0038)

Updated for PLC2 freeze blocker correction. Finished Greensboro controller
context exports are validation oracles unless independent evidence proves they
are approved generic Fortna library artifacts.

| File | Classification | Action | Controller / notes |
|------|----------------|--------|-------------------|
| `OReilly_Library_v3.L5X` | `APPROVED_GENERIC_HOST` | KEEP (host pack) | `Library` — primary production AOI/UDT host |
| `OReilly_Library_v3.L5X` → `Slow_Flt` AOI | `FINISHED_SITE_DERIVED_SUSPECT` | REVIEW_REQUIRED | Vendor=FORTNA SignatureID present in finished Greensboro controllers; **no independent Fortna source proven**. Capability stamped REVIEW until independent source exists. Do not treat as approved generic solely because it ships inside the host pack. |
| `validation_oracles/Slow_Flt_AOI.L5X` | `FINISHED_SITE_DERIVED` | QUARANTINED | Was overlay `SiteForge_AOI_Library`; same finished Slow_Flt lineage — not a second independent source |
| `validation_oracles/AOI_SNTP_QUERY_AOI.L5X` | `FINISHED_SITE_DERIVED` | QUARANTINED | `ORLY_Greensboro_NC_PLC2` |
| `validation_oracles/Enc_Routine_ST.L5X` | `FINISHED_SITE_DERIVED` | QUARANTINED | `ORLY_Greensboro_NC_PLC5` |
| `validation_oracles/TRK_Divert_WaveFunction_AOI.L5X` | `FINISHED_SITE_DERIVED` | QUARANTINED | `ORLY_Greensboro_NC_PLC5` |
| `validation_oracles/Sorter_Track_Program.L5X` | `FINISHED_SITE_DERIVED` | QUARANTINED | `ORLY_Greensboro_NC_PLC5` |
| `validation_oracles/WCS_Interface_TCP_IP_Program.L5X` | `FINISHED_SITE_DERIVED` | QUARANTINED | `ORLY_Greensboro_NC_PLC5` |
| `validation_oracles/ShippingSorter_Area_L3_Program.L5X` | `FINISHED_SITE_DERIVED` | QUARANTINED | `ORLY_Greensboro_NC_PLC5` |
| `validation_oracles/Sawtooth_Merge_Program.L5X` | `FINISHED_SITE_DERIVED` | QUARANTINED | `ORLY_Greensboro_NC_PLC4` |
| `validation_oracles/Sawtooth_Merge_DataTypes.L5X` | `UNKNOWN_FINISHED_DERIVED` | QUARANTINED | Companion UDT fragment — **not** generic by rename |
| `validation_oracles/Sys_Program.L5X` | `FINISHED_SITE_DERIVED` | QUARANTINED | `ORLY_Greensboro_NC_PLC5` |
| `validation_oracles/System_Program.L5X` | `FINISHED_SITE_DERIVED` | QUARANTINED | `ORLY_Greensboro_NC_PLC2` |
| `validation_oracles/IO_MAP_Program.L5X` | `FINISHED_SITE_DERIVED` | QUARANTINED | `ORLY_Greensboro_NC_PLC5` |

## Policy

- Production Autogen `--library` allowlist: `OReilly_Library_v3.L5X` only (PD-0041).
- Production Autogen must not load `validation_oracles/` under any flag.
- Missing / contaminated capabilities → `REVIEW_REQUIRED` (do not reconstruct finished implementations).
- Slow_Flt: host pack still contains the AOI definition for Studio continuity, but provenance is **not** approved-generic; freeze reports must not claim otherwise.
- GATE P: Autogen default emits `NOP();` + REVIEW comment for Slow_Flt rungs when provenance is `FINISHED_SITE_DERIVED_SUSPECT`. Real `Slow_Flt(...)` emit requires `FORTNA_SLOW_FLT_APPROVED_GENERIC=1` (independent approved-generic opt-in). Do not treat finished Brownsburg/Greensboro L5X as production Slow_Flt source.
