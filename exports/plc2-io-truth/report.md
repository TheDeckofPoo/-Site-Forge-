# PLC2 I/O Truth — Acceptance Report

**Branch:** `feature/plc2-io-truth`  
**Generated:** 2026-09-13T04:09:56Z  
**Machine:** ORNCCP2  
**PASS declared:** **NO** — mapping fidelity not yet acceptable; this pass proves root causes before rewrite.

## FORTNAPLUS SEMANTICS

| Item | Result |
|------|--------|
| docs reviewed | ViewIO/FORTNADT, IOCard Interfaces, FastIO, Motor Startup Chains, Fulls/Jams/Fulljams, StartStopZones |
| authoritative relationships identified | See `docs/PLC2_FORTNAPLUS_IO_SEMANTICS.md` |

Key documented ownership signals: **word ownership by AC**, eipcfg adapters on this Machine, Conveyor.Machine_Name, Configio↔Conveyor words, Mtrchain/Jamzones Zone Owner. Forbidden: P-number→PLC heuristics.

## CONTROLLER SCOPE

| Metric | Value |
|--------|------:|
| correct local (vs finished `P###_Conv` set) | **47** (from foundation compare; LOCAL set = 59) |
| missed local | **11** (lettered finished AOIs + P2000) |
| incorrect local | **10** |
| unresolved (RUN mechanical) | **74** |
| LOCAL / EXTERNAL_REFERENCE / OUT_OF_SCOPE | **59 / 4 / 147** |

## I/O TREE

| Metric | Value |
|--------|-------|
| finished adapters/modules | CP2RIO*/CP3RIO* family (~40 modules) |
| generated | 39 modules (`T_1794_AENT_*` + Local/EN2T) |
| structural matches | catalog families overlap (AENT/IA16/IB16/OA8I/OB16P/L83E/EN2T) |
| missing/extra (by finished name) | name family differs — rack name ≠ ownership (`CP3RIO0` owned by PLC2 in finished) |

RUN contains `ORNCCP2-RTA-eipcfg.xml` — adapter names should be researched from eipcfg before inventing finished names.

## CP_I

| Metric | Finished | Generated (true) |
|--------|----------|------------------|
| real logical mappings | **159** | **12** |
| placeholders | **95** | **244** |
| rungs | **304** | ~264 (incl. placeholders) |
| exact/equivalent (tag+dir) | — | **11** equivalent overall |
| wrong / missing / extra | taxonomy: WRONG_ADAPTER **152**, WRONG_LOGICAL_DEVICE **141**, MISSING_RUN_RELATIONSHIP **101** | missing tag+dir **221**, extra **21** |

## CP_O

| Metric | Finished | Generated (true) |
|--------|----------|------------------|
| real logical mappings | **75** | **22** |
| placeholders | **179** | **122** |
| rungs | **304** | ~155 |

## Why foundation “256/144 real” looked too high

Foundation `_parse_iomap_mappings` counted **all** XIC/OTE rows as real, including `NO_PointPlaceholder`.  
**True generated REAL_LOGICAL_POINT = 12 I + 22 O.**  
PLC2 is **under-mapped**, not over-mapped, on real device points.

## TRANSPORT

| Metric | Value |
|--------|-------|
| false local devices | ~10 vs finished naming (investigate) |
| missing local devices | ~11 (lettered finished AOIs) |
| external boundaries | **YES** (1–4 compact) |
| full remote networks | **NO** |

## Biggest remaining semantic gap

Generator resolves Fortna words primarily via sparse EIPCSV `word_map`, while Greensboro PLC2 owned words live in **Configio.asc.ORNCCP2** (words 200/201/300…). Until Configio→adapter/slot resolution is the primary path for this site, mappings land on wrong adapters (`T_1794_*`) or become placeholders.

## Biggest remaining RUN-data gap

- Adapter **display names** (`CP2RIO0` vs eipcfg `1794-AENT-*` / generated `T_1794_AENT_*`) need a documented naming bridge from RUN, not finished copy.
- Finished AOI member paths (`CP2_CS.I.Start_PB`) are PLC-side; RUN has Fortna parts (`2PBSTART`) — reconstruction works for 15/20 traced mappings, but emit must use the evidence graph.

## Reverse-trace (required examples)

| Finished channel | Finished tag | Reconstructable from RUN |
|------------------|--------------|--------------------------|
| `CP2RIO0:I.Data[1].0` | `CP2_CS.I.Start_PB` | **YES** ← `2PBSTART` word 201 bit 0 |
| `CP2RIO0:I.Data[1].1` | `CP2_CS.I.Stop_PB` | **YES** ← `2PBSTOP` 201.1 |
| `CP2RIO0:I.Data[1].2` | `CP2_MCR1.I.ES_OK` | **YES** ← `2MCR1_AUX` 201.2 |
| `CP3RIO0:I.Data[7].0` | `P400_MS.I.Auxiliary_Forward` | **YES** ← `M400_AUX` 307.0 |

20 traces total; **15** reconstructable.

## Artifacts

- `docs/PLC2_FORTNAPLUS_IO_SEMANTICS.md`
- `docs/PLC2_IO_TRUTH_MODEL.md`
- `exports/plc2-io-truth/io_evidence_graph.json`
- `exports/plc2-io-truth/mapping_error_taxonomy.json`
- `exports/plc2-io-truth/controller_scope.json`
- `exports/plc2-io-truth/io_map_comparison.json`
- `exports/plc2-io-truth/transport_validation.json`
- `exports/plc2-io-truth/reverse_trace.json`
- `exports/plc2-io-truth/ORNCCP2_io_truth_candidate.L5X` (**diagnostic** — mapping rewrite deferred)
- `exports/studio-validation/ORNCCP2_io_truth_candidate.L5X`

## Non-goals this pass

- No IO_MAP emit rewrite in `fortna_autogen.py`
- No PLC4/PLC5/Sorter/WCS work
- No copying finished PLC values into generation
- **No PASS claim** on mapping fidelity
