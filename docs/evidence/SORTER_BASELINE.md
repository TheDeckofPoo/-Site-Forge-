# Sorter Baseline

Separate:

| Stream | Role |
|--------|------|
| **RUN-DERIVED DISCOVERY** | What the decoder finds blindly |
| **FINISHED PLC VALIDATION** | Architecture oracle after blind build |

Finished PLC5 is **never** a discovery source.

### Training docs + validation oracles

- FPC meaning: `FPC-Sorter-Control-Module.docx`, `FPC-Shifter-And-Sorter-Configuration.docx`, `FPC-SorterConfigurationChecklist.docx`  
  (Desktop: `C:\Users\curtiskricke\Desktop\Fortna Plus` · Repo: `docs/training/`)  
- Finished PLC5 architecture oracle (local):  
  `C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_Greensboro_NC_PLC5_RTfinished.L5X`  
- Catalog: [`EXTERNAL_REFERENCE_MATERIALS.md`](EXTERNAL_REFERENCE_MATERIALS.md)

---

## Cross-site discovery (blind)

| Site | Active sorters | Notes |
|------|---------------:|-------|
| PLC2 / ORNCCP2 | **0** | Schemas may exist; overlay empty |
| PLC4 / ORNCCP4 | **2** | e.g. SAWTOOTH_MERGE, CITY_LANE — divert IO often REVIEW |
| PLC5 / ORNCCP5 | **5** | Acceptance target below |

Reproduce: `python tools/scripts/test_plc5_sorter_discovery.py`

### PLC5 acceptance targets (discover — do not hardcode)

From `Sorters.asc.ORNCCP5` (machine overlay):

| Sorter Name | Encoder | Timer |
|-------------|---------|-------|
| 504_BELT | ENC504 | tmENC504 |
| 506_SHIP_SORTER | ENC506 | tmENC506 |
| 508_SHIP_SORTER | ENC508 | tmENC508 |
| 509_SHIP_SORTER | ENC509 | tmENC509 |
| 510_SHIP_SORTER | ENC510 | tmENC510 |

Also: `SrtAppControl` SHIP_SORTER / VFD504_EN; `SrtScanBoss`; `SrtZoneLane` active lanes.

Report: `exports/stabilization/plc5_sorter_autobuild_report.md`

---

## Generic tables

| Table | Role | Class |
|-------|------|-------|
| Sorters | Identity + encoder + machine | STATIC |
| SrtAppControl | App / motor policy | STATIC |
| SrtScanBoss | Scan topology | STATIC |
| SrtZoneLane | Divert lane topology | STATIC (assignment) |
| Encoders | Scale / enable | STATIC |
| SrtTrack* / SrtDevice* | Runtime activity | DYNAMIC — not divert map |

---

## Field authority (summary)

| Field | Primary | Fallback |
|-------|---------|----------|
| Sorter identity | Sorters.Name + Machine | UNKNOWN |
| Type class (shoe/ship) | — (name DERIVED) | REVIEW_REQUIRED |
| Encoder | Sorters.Encoder ioName → Encoders | REVIEW |
| Divert lane / HostZone | SrtZoneLane | REVIEW |
| Divert **output IO** | — (often INVALID) | ENGINEER / REVIEW |
| Induct conveyor chain | — | UNKNOWN |
| Track offset / divert trigger | — | UNKNOWN / NOT_SUPPORTED |
| Motor | SorterCnvMtr when valid | REVIEW |

Full archaeology: `exports/stabilization/sorter_evidence_inventory.md`  
Canonical model: `exports/stabilization/sorter_canonical_model_report.md`

---

## PLC generation status

**NOT STARTED / REVIEW** — Sorter_Track L5X emit is not claimed complete.  
Apply Sorter may persist `workbook.sorter_build` for later generic library path.

Gold `Sorter_Track_Program.L5X` = validation/oracle only.
