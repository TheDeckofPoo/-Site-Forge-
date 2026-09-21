# Corpus I/O conservation backtest

Generated: `2026-09-21T02:21:58.334107+00:00`

Primary invariant: **LOST CLAIMS = 0** (resolved physical claims must not silently become placeholders).

## Aggregate

| Controller | claims | specialized | generic_bool | placeholders | lost | mute | status |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `MSCATL_CP3` | 256 | 149 | 106 | 49 | 0 | SPARE70207 | **PASS** |
| `ORINDYAC6` | 245 | 167 | 78 | 91 | 0 | — | **PASS** |
| `ORNCCP2` | 249 | 220 | 29 | 151 | 0 | — | **PASS** |
| `ORNCCP4` | 272 | 229 | 43 | 160 | 0 | — | **PASS** |
| `ORNCCP5` | 411 | 307 | 104 | 301 | 0 | — | **PASS** |
| `ORDENCP3` | 0 | 0 | 0 | 0 | 0 | — | **NO_PHYSICAL_CLAIMS** |
| `MSCRENOPICK` | 115 | 86 | 29 | 17 | 0 | — | **PASS** |
| `MSCRENOPACK` | 720 | 416 | 468 | 346 | 0 | — | **PASS** |
| `MSCRENOSHIP` | 244 | 167 | 115 | 122 | 0 | — | **PASS** |
| `PMARTOTW_AC1` | 0 | 0 | 0 | 0 | 0 | — | **NO_PHYSICAL_CLAIMS** |
| `RESPICK` | 0 | 0 | 0 | 0 | 0 | — | **NO_PHYSICAL_CLAIMS** |

- Applicable controllers: **8** · LOST=0: **8** · FAIL: **0**
- All applicable LOST=0: **True**

## Atlanta expectation check

- claims=256 (expect ~256) · specialized=149 (expect ~149) · generic_bool=106 (expect ~106) · lost=0 (expect 0) · mute=['SPARE70207']
- match_expected: **True**

## Method

- Claim authority: `build_evidence_bundle` raw physical claims
- Emit path: `load_from_run` → `build_l5x` (IO_MAP + placeholders; no gold Excel)
- Counters from autogen report: specialized / generic_bool / placeholders / `io_map_lost_claims_count`
- Virgin sites measured only — not tuned

## PostgreSQL

- Corpus reachable: 67 complete / 68 archives
- Artifact store: PG reachable (corpus.archives=68) but no diagnostics artifact table; JSON/MD on disk are sufficient

## Errors / skips

_None._

