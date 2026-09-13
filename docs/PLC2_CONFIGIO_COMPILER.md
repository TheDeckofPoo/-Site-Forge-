# PLC2 Configio-Primary Compiler

**Generated:** 2026-09-13T04:36:15.954250+00:00
**Machine:** ORNCCP2
**Policy:** RUN tables are the generation source. Finished PLC2 is validation/oracle only.

## What changed

- New `tools/scripts/fortna_physical_word_resolver.py` — Configio Desc
  `PANEL-CATALOG-INDEX` + eipcfg modules → `CPxRIOn:I/O.Data[s].b`
- `fortna_autogen.py` `load_from_run` merges physical `io_word_map` for all
  Configio-owned words and renames adapters using Configio panel prefixes
  (CP2/CP3 RUN evidence — **not** a hard-coded `201→CP2RIO0` dict)
- Device members: `*PBSTART` → `CPn_CS.I.Start_PB`, `M###_AUX` →
  `P###_MS.I.Auxiliary_Forward`, PE/ES patterns preserved

## Data index scheme

1794 bridged: Data[slot-1] when slot>0 (head=slot0); proven by 2PBSTART word201→Data[1] with eipcfg IA16-3 slot=2

## Physical map stats

- Adapters / RIO names: `['CP2RIO0', 'CP2RIO1', 'CP3RIO0', 'CP3RIO1', 'CP3RIO2']`
- Words resolved: **32** (unresolved 0)
- Word 201 bit0 → `CP2RIO0:I.Data[1].0` (provenance `configio_desc_name+sequential`)
- Word 307 bit0 → `CP3RIO0:I.Data[7].0` (provenance `configio_panel_sequential`)

## Before / after (REAL logical mappings)

| Metric | Before | After | Finished |
|--------|-------:|------:|---------:|
| Real inputs | 12 | **147** | 159 |
| Real outputs | 22 | **78** | 75 |
| WRONG_ADAPTER | 152 | **19** | — |

- Exact channel+tag matches: 173
- Equivalent tag+direction matches: 173
- Generated adapters: `['CP2RIO0', 'CP2RIO1', 'CP3RIO0', 'CP3RIO1', 'CP3RIO2']`

## Reverse-trace

- Finished real mappings: 234
- Traced: 75 (target ≥75)
- Reconstructable from RUN: 54

## Taxonomy counts

- `WRONG_WORD`: 0
- `WRONG_BANK`: 0
- `WRONG_ADAPTER`: 19
- `WRONG_SLOT`: 1
- `WRONG_BIT`: 1
- `WRONG_DIRECTION`: 0
- `WRONG_LOGICAL_DEVICE`: 67
- `WRONG_CONTROLLER_SCOPE`: 4
- `STALE_RECORD_USED`: 0
- `UNSUPPORTED_POINT_TYPE`: 0
- `PLACEHOLDER_SHOULD_BE_USED`: 0
- `MISSING_RUN_RELATIONSHIP`: 40

## Artifacts

- `exports/plc2-configio-compiler/physical_word_map.json`
- `exports/plc2-configio-compiler/ORNCCP2_configio_candidate.L5X`
- `exports/studio-validation/ORNCCP2_configio_candidate.L5X`
- `exports/plc2-configio-compiler/io_map_comparison.json`
- `exports/plc2-configio-compiler/reverse_trace.json`
- `exports/plc2-configio-compiler/transport/transport_overview.png`
- `exports/plc2-configio-compiler/report.json`

## Related

- `docs/PLC2_IO_TRUTH_MODEL.md`
- `docs/PLC2_FORTNAPLUS_IO_SEMANTICS.md`

