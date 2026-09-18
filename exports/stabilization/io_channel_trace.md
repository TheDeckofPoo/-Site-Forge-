# I/O Channel Trace — ORNCCP5

Generated: `2026-09-18T18:04:25Z`  
RUN: `C:\dev\worktree\FortnaPlus\workspace\cp5-run\RUN`

## Root cause (Gate 2 fix)

_configio_desc_claim treated PANEL-NODE / PANEL-CATALOG Desc (e.g. CP5-NODE51-1A, CP2-1794-IA16-3) as occupied; those forms are module topology addressing only. Unused bits on mapped modules are PROVEN_SPARE (CONFIGIO_MAPPED_UNUSED_BIT), not UNRESOLVED_OWNER.

## Summary

| Metric | Count |
|--------|------:|
| Channels | 712 |
| ASSIGNED | 406 |
| PROVEN_SPARE | 306 |
| ENGINEER_SPARE | 0 |
| UNRESOLVED_OWNER | 0 |
| UNKNOWN | 0 |
| Module audit failures | 0 |

### Owner sources

- `RUN_CONVEYOR`: 406
- `CONFIGIO_MAPPED_UNUSED_BIT`: 306

### Rejection reasons (UNRESOLVED only)

_none_

## Gate 3 — Single model

HardwareIOModel is the sole tree for Hardware UI; adapters/modules/channels in this trace are the same objects.

- adapters: **8**
- modules: **61**
- channels: **712**
- identity: `same_dict_tree`

## Gate 4 — Configio load

- path: `C:\dev\worktree\FortnaPlus\workspace\cp5-run\RUN\FORTNA\Configio.asc.ORNCCP5` (machine_specific)
- rows loaded: **400**
- Desc nonempty (topology): **112** / nonempty **119**
- Desc spare tokens: **1**
- Desc signal/other: **6**
- Conveyor rows / named: **6000** / **1428**

## Gate 1 — Manual end-to-end examples

### ASSIGNED example (e.g. 5MCR1 on word 500 bit 2)

- `CP5RIO0:O.Data[0].2` word `500` bit `2` → **ASSIGNED** owner `5MCR1` source `RUN_CONVEYOR` Desc `CP5-NODE51-1A`

### Formerly false-UNRESOLVED unused bit → PROVEN_SPARE

- `CP5RIO0:O.Data[0].0` word `500` bit `0` → **PROVEN_SPARE** source `CONFIGIO_MAPPED_UNUSED_BIT` Desc `CP5-NODE51-1A`

## Gate 5 — Module source-vs-UI audit

| RIO | Slot | Type | Expected | Named | Assigned | Unresolved | Spare | Missing | Audit |
|-----|-----:|------|--------:|------:|---------:|-----------:|------:|--------:|-------|
| CP5RIO0 | 1 | 1794-OA8I | 3 | 3 | 3 | 0 | 5 | 0 | PASS |
| CP5RIO0 | 2 | 1794-IA16 | 15 | 15 | 15 | 0 | 1 | 0 | PASS |
| CP5RIO0 | 3 | 1794-OA8I | 8 | 8 | 8 | 0 | 0 | 0 | PASS |
| CP5RIO0 | 4 | 1794-IA16 | 9 | 9 | 9 | 0 | 7 | 0 | PASS |
| CP5RIO0 | 5 | 1794-OA8I | 8 | 8 | 8 | 0 | 0 | 0 | PASS |
| CP5RIO0 | 6 | 1794-IA16 | 16 | 16 | 16 | 0 | 0 | 0 | PASS |
| CP5RIO0 | 7 | 1794-OA8I | 5 | 5 | 5 | 0 | 3 | 0 | PASS |
| CP5RIO0 | 8 | 1794-IA16 | 10 | 10 | 10 | 0 | 6 | 0 | PASS |
| CP5RIO1 | 1 | 1794-IA16 | 14 | 14 | 14 | 0 | 2 | 0 | PASS |
| CP5RIO1 | 2 | 1794-OA8I | 5 | 5 | 5 | 0 | 3 | 0 | PASS |
| CP5RIO1 | 3 | 1794-IA16 | 5 | 5 | 5 | 0 | 11 | 0 | PASS |
| CP5RIO1 | 4 | 1794-OA8I | 6 | 6 | 6 | 0 | 2 | 0 | PASS |
| CP5RIO1 | 5 | 1794-IA16 | 7 | 7 | 7 | 0 | 9 | 0 | PASS |
| CP5RIO1 | 6 | 1794-OA8I | 2 | 2 | 2 | 0 | 6 | 0 | PASS |
| CP5RIO1 | 7 | 1794-IA16 | 9 | 9 | 9 | 0 | 7 | 0 | PASS |
| CP5RIO2 | 1 | 1794-OB16P | 10 | 10 | 10 | 0 | 6 | 0 | PASS |
| CP5RIO2 | 2 | 1794-IB16 | 14 | 14 | 14 | 0 | 2 | 0 | PASS |
| CP5RIO2 | 3 | 1794-OB16P | 16 | 16 | 16 | 0 | 0 | 0 | PASS |
| CP5RIO2 | 4 | 1794-IB16 | 11 | 11 | 11 | 0 | 5 | 0 | PASS |
| CP5RIO2 | 5 | 1794-OB16P | 8 | 8 | 8 | 0 | 8 | 0 | PASS |
| CP5RIO2 | 6 | 1794-IB16 | 10 | 10 | 10 | 0 | 6 | 0 | PASS |
| CP5RIO3 | 1 | 1794-OA8I | 2 | 2 | 2 | 0 | 6 | 0 | PASS |
| CP5RIO3 | 2 | 1794-IA16 | 13 | 13 | 13 | 0 | 3 | 0 | PASS |
| CP5RIO3 | 3 | 1794-OA8I | 5 | 5 | 5 | 0 | 3 | 0 | PASS |
| CP5RIO3 | 4 | 1794-IA16 | 5 | 5 | 5 | 0 | 11 | 0 | PASS |
| CP5RIO3 | 5 | 1794-OA8I | 5 | 5 | 5 | 0 | 3 | 0 | PASS |
| CP5RIO3 | 6 | 1794-IA16 | 10 | 10 | 10 | 0 | 6 | 0 | PASS |
| CP5RIO3 | 7 | 1794-OA8I | 4 | 4 | 4 | 0 | 4 | 0 | PASS |
| CP5RIO3 | 8 | 1794-IA16 | 4 | 4 | 4 | 0 | 12 | 0 | PASS |
| CP6RIO0 | 1 | 1794-IA16 | 7 | 7 | 7 | 0 | 9 | 0 | PASS |
| CP6RIO0 | 2 | 1794-OA8I | 6 | 6 | 6 | 0 | 2 | 0 | PASS |
| CP6RIO0 | 3 | 1794-IA16 | 8 | 8 | 8 | 0 | 8 | 0 | PASS |
| CP6RIO0 | 4 | 1794-OA8I | 0 | 0 | 0 | 0 | 8 | 0 | PASS |
| CP6RIO0 | 5 | 1794-IA16 | 6 | 6 | 6 | 0 | 10 | 0 | PASS |
| CP6RIO1 | 1 | 1794-OB16P | 6 | 6 | 6 | 0 | 10 | 0 | PASS |
| CP6RIO1 | 2 | 1794-IB16 | 12 | 12 | 12 | 0 | 4 | 0 | PASS |
| CP6RIO1 | 3 | 1794-OB16P | 12 | 12 | 12 | 0 | 4 | 0 | PASS |
| CP6RIO1 | 4 | 1794-IB16 | 4 | 4 | 4 | 0 | 12 | 0 | PASS |
| CP6RIO1 | 5 | 1794-OB16P | 1 | 1 | 1 | 0 | 15 | 0 | PASS |
| CP6RIO2 | 1 | 1794-IA16 | 12 | 12 | 12 | 0 | 4 | 0 | PASS |
| CP6RIO2 | 2 | 1794-IA16 | 3 | 3 | 3 | 0 | 13 | 0 | PASS |
| CP6RIO2 | 3 | 1794-IA16 | 11 | 11 | 11 | 0 | 5 | 0 | PASS |
| CP6RIO2 | 4 | 1794-IA16 | 12 | 12 | 12 | 0 | 4 | 0 | PASS |
| CP6RIO2 | 5 | 1794-IA16 | 6 | 6 | 6 | 0 | 10 | 0 | PASS |
| CP6RIO2 | 6 | 1794-OA8I | 4 | 4 | 4 | 0 | 4 | 0 | PASS |
| CP6RIO2 | 7 | 1794-OA8I | 4 | 4 | 4 | 0 | 4 | 0 | PASS |
| CP6RIO2 | 8 | 1794-OA8I | 8 | 8 | 8 | 0 | 0 | 0 | PASS |
| CP7RIO0 | 1 | 1794-OA8I | 0 | 0 | 0 | 0 | 8 | 0 | PASS |
| CP7RIO0 | 2 | 1794-IB16 | 13 | 13 | 13 | 0 | 3 | 0 | PASS |
| CP7RIO0 | 3 | 1794-IB16 | 10 | 10 | 10 | 0 | 6 | 0 | PASS |
| CP7RIO0 | 4 | 1794-OB16P | 5 | 5 | 5 | 0 | 11 | 0 | PASS |
| CP7RIO0 | 5 | 1794-OB16P | 7 | 7 | 7 | 0 | 9 | 0 | PASS |
| CP7RIO0 | 6 | 1794-OB16P | 10 | 10 | 10 | 0 | 6 | 0 | PASS |

_Full per-channel records: `io_channel_trace.json` (712 channels)._
