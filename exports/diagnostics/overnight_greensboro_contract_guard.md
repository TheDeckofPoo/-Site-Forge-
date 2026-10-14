# Phase 0 — Greensboro Contract Version Guard

**Authority:** CURRENT APPROVED LIBRARY (OReilly_Library_v3) WINS.

| Type/AOI | Library | PLC2 | PLC4 | PLC5 | Variant |
|---|---|---|---|---|---|
| CS_UDT | 13 | 13 | 13 | 13 | OK |
| Slow_ControlStation | None | None | None | None | OK |
| AOI_SNTP_QUERY | None | None | None | None | OK |
| SKT_UDP_DATA | 7 | 7 | 7 | 7 | OK |
| Comm_UDT | 6 | 6 | 5 | 6 | LAYOUT_DIFFERS_LIBRARY_WINS |
| CommDiag_UDT | None | None | 4 | None | LIBRARY_ABSENT_FINISHED_PRESENT |
| PE_Logic | None | None | None | None | OK |
| Enc_UDT | 14 | 14 | 14 | 14 | OK |
| Area_UDT | 18 | 18 | 18 | 15 | LAYOUT_DIFFERS_LIBRARY_WINS |

## Notes
- **Comm_UDT**: LAYOUT_DIFFERS_LIBRARY_WINS — PLC4: member layout differs from library (6 vs 5 members)
- **CommDiag_UDT**: LIBRARY_ABSENT_FINISHED_PRESENT — CURRENT APPROVED LIBRARY WINS — do not transplant
- **Area_UDT**: LAYOUT_DIFFERS_LIBRARY_WINS — PLC5: member layout differs from library (18 vs 15 members)

## NTP
- Library AOI_SNTP_QUERY: True
- PLC2/4/5 AOI_SNTP_QUERY call present: False/True/False
- Do NOT copy Greensboro SNTP_SERVER_ADDRESS hostname/IP.

## Sorter structural oracle (names only)
- PLC4 sorter-like programs: [('Sorter_Track', ['Divert_Lane_Status', 'Divert_Rate_Limit', 'Encoder', 'Main', 'Response_Time', 'Scanner', 'Track_Divert_Confirm', 'Track_Divert_Package']), ('CityCounter_Area_L3', ['Conv_Name', 'Conv_Track', 'Conv_Track_Offset', 'Induct_Token', 'Main_Routine', 'Reason_Code', 'Scanner']), ('Sorter_Track', ['Divert_Lane_Status', 'Divert_Rate_Limit', 'Encoder', 'Main', 'Response_Time', 'Scanner', 'Track_Divert_Confirm', 'Track_Divert_Package'])]
- PLC5 sorter-like programs: [('ShippingSorter_Area_Area_Fast', ['Main_Routine', 'Conv_Fast', 'Conv_Full', 'Conv_PE']), ('ShippingSorter_Area_Area_Slow', ['Main_Routine', 'Area_Logic', 'Area_PI', 'Control_Station', 'Conv_Flt', 'Conv_Jam', 'Conv_PI']), ('ShippingSorter_Area_Area_L1', ['Main_Routine', 'Area', 'Conv']), ('ShippingSorter_Area_Area_L2', ['Main_Routine', 'Conv_Speed', 'FullTime', 'PETime']), ('ShippingSorter_Area_Area_L3', ['Main_Routine']), ('Redroom_Area_Area_L3', ['Main_Routine'])]

Full JSON: overnight_greensboro_contract_guard.json