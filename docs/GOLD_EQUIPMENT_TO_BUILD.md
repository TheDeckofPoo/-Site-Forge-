# Gold PLC2 / PLC4 / PLC5 → Site Forge equipment patterns

Sites are not like-for-like. **Equipment is standard** (transport conveyor, 2:1 merge, sorter track, sawtooth). O'Reilly Green `*S.L5X` files are the pattern library; each new site (e.g. MSC Reno) supplies its own RUN tar(s) + PDFs.

## Pattern sources (Desktop `ORielly Green`)

| PLC role | Latest L5X | Equipment patterns |
|----------|------------|--------------------|
| **PLC2** transport + merges | `1 PLC2\ORLY_Greensboro_NC_PLC2s.L5X` (~3.8 MB) | Fast/Slow/PE + **4× Merge_2to1** + L2 Merge ST presets |
| **PLC4** sawtooth | `2 PLC4\ORLY_Greensboro_NC_PLC4S.L5X` (~8.0 MB) | Transport + **Sawtooth_Merge** program + 2× Merge_2to1 |
| **PLC5** sorter | `3 PLC5\ORLY_Greensboro_NC_PLC5S.L5X` (~7.7 MB) | Transport + merges + **Sorter_Track** / TRK_* / Enc_RIOCard |

Machine-readable scan: `docs/gold_plc245_inventory.json`.

**Note:** AOI *definitions* in these exports remain `EncodedData` (sealed). Call sites and program logic are fully readable and drive Site Forge scaffolds.

## AOI usage in gold (call sites)

| AOI | PLC2s | PLC4S | PLC5S |
|-----|-------|-------|-------|
| Fast_Conv / Slow_Flt / Slow_Jam | 57 / 57 / 57 | 58 / 58 / 57 | 78 / 65 / 65 |
| PE_Logic / Full_PE | 28 / 7 | 42 / 16 | 55 / 37 |
| **Merge_2to1** | **4** | **2** | **3** |
| Enc_RIOCard | 0 | 1 | 5 |
| TRK_Divert / WaveFunction | 0 | 1 / 1 | 16 / 16 |
| Sawtooth_Merge program | no | **yes** | no |
| Sorter_Track program | no | yes (light) | **yes** |

## Tar equipment → Site Forge actions

| Tar evidence | Build action |
|--------------|--------------|
| Conveyors (P###) | Fast/Slow + Conv_UDT |
| Photoeyes | PE_UDT + PE_Logic / Full_PE |
| VFD* | P###_VFD Motor_Starter_UDT + IO_MAP |
| ES table | ES_UDT |
| EIP adapters/modules | Module tree + IO_MAP |
| 2:1 merge UI / Merges.asc | Merge_2to1 + Conv_Merge + **Area_L2 Merge ST presets** |
| Sorter / SrtTrack / ENC | Sorter_Track pack |
| Sawtooth | Optional **Sawtooth_Merge** pack (not auto from tar yet) |

## Multi-controller sites (e.g. MSC Reno)

One RUN tar **per controller** → one L5X. Example Reno:

| Tar `MACHINENAME` | Output |
|-------------------|--------|
| MSCRENOPACK | `MSCRENO_MSCRENOPACK.L5X` |
| MSCRENOPICK | `MSCRENO_MSCRENOPICK.L5X` |
| MSCRENOSHIP | `MSCRENO_MSCRENOSHIP.L5X` |
| MSCRENOGNS | Skip (site/services; no PLC equipment dump) |

IO is scoped with `belongs_to_controller` + EIP word map — PACK does not own PICK IO.

## Runtime

`fortna_equipment_plan.py` → `inventory_and_plan(run_dir)`  
`fortna_autogen.load_from_run` attaches `equipment_plan`  
Generate writes `exports/.../equipment_plan.json`
