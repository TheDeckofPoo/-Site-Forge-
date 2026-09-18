# PLC5 Sorter Blind RUN Auto-Build Foundation

**Generated:** 2026-09-17  
**Scope:** Canonical SorterModel + UI populate + Apply persistence  
**Firewall:** Finished PLC L5X / Greensboro gold packs are reference-only — not generation input.  
**PLC GENERATION:** **NOT_STARTED / REVIEW** — no Sorter_Track L5X emit in this checkpoint.

## Principle

```
RUN → fortna_sorter_discovery / run_workspace_discover
    → SorterModel (PROVEN / DERIVED / REVIEW_REQUIRED)
    → Sorter Build UI
    → Apply Sorter → workbook.sorter_build (Safety-style merge)
    → Autogen later (generic library path required)
```

No CP1–CP4 rewrite. No finished-PLC answer sheet copied into discovery.  
No `machine == "ORNCCP5"` branches in production discovery code.

## Counts (workspace/cp5-run/RUN · ORNCCP5)

| Item | Count | Authority |
|------|------:|-----------|
| Active sorters (`Sorters.asc`) | **5** | PROVEN |
| Encoders linked (`ENC504`…`ENC510`) | **5** | PROVEN |
| App control (`SHIP_SORTER`) | **1** | PROVEN |
| Scan bosses (`SrtScanBoss`) | **1** | PROVEN |
| Divert / zone lanes (`SrtZoneLane`) | **32** | topology PROVEN |
| Tracking path stubs (per sorter encoder) | **5** | encoder PROVEN · conveyor UNKNOWN |
| Divert output IO (`Outpoints`⋈`SrtZoneLane.Lane`) | 32 | **PROVEN** (LaneEnableSignal still INVALID) |

### Sorter names discovered (not hardcoded)

- `504_BELT` → `ENC504`
- `506_SHIP_SORTER` → `ENC506`
- `508_SHIP_SORTER` → `ENC508`
- `509_SHIP_SORTER` → `ENC509`
- `510_SHIP_SORTER` → `ENC510`

### Cross-check PLC2

| Site | Active sorters |
|------|---------------:|
| ORNCCP5 (`workspace/cp5-run/RUN`) | **5** |
| ORNCCP2 (`workspace/_plc2_run_peek/RUN`) | **0** |

## Field authority

| Fact | Class |
|------|-------|
| Sorter existence / identity | PROVEN (`Sorters`) |
| Encoder link + ticks/FPM | PROVEN (`Sorters` + `Encoders`) |
| App control / scan boss | PROVEN (`SrtAppControl`, `SrtScanBoss`) |
| Divert lane topology (lane / host zone / app) | PROVEN (`SrtZoneLane`) |
| Divert **output IO** | REVIEW_REQUIRED when INVALID / blank |
| Tracking conveyor chain | UNKNOWN (not invented from name tokens) |
| Coarse sorter type (shoe/ship) | REVIEW_REQUIRED |
| PLC Sorter_Track generation | **NOT_STARTED** |

## UI / Apply

- Sorter Build panel lists discovered sorters with **PROVEN / DERIVED / REVIEW** badges.
- Divert rows render from `SrtZoneLane` (topology + REVIEW on output IO).
- Tracking stubs populate from proven encoder links; conveyor/PE left for engineer.
- **Apply sorter → Autogen** merges into `workbook.sorter_build` without hollowing Transport / Safety (same merge pattern as Safety Apply).

## Tooling

| Script | Role |
|--------|------|
| `tools/scripts/fortna_sorter_discovery.py` | Inventory + `build_canonical_sorter_model` |
| `tools/scripts/fortna_run_workspace_discover.py` | SiteModel + editors.sorter + encoders without Sawtooth |
| `tools/scripts/fortna_knowledge_enrich.py` | `build_sorter_editor_v2` carries divert/tracking/authority |
| `tools/scripts/test_plc5_sorter_discovery.py` | Asserts 5 on CP5, 0 on PLC2, no ORNCCP5 hardcode |

## Generation status

| Capability | Status |
|------------|--------|
| Canonical SorterModel | **DONE** (foundation) |
| UI populate from discovery | **DONE** |
| Apply → `workbook.sorter_build` | **DONE** (merge persist) |
| Sorter_Track / divert PLC emit | **NOT_STARTED** — gold pack is site-fixed; stop here |

## Test

```text
python tools/scripts/test_plc5_sorter_discovery.py
```
