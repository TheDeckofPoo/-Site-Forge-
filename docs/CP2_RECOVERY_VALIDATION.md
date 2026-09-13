# CP2 Recovery Validation Build

**Branch:** `feature/cp2-recovery-validation`  
**Base:** `feature/io-regression-lock` @ `ede3f5d`  
**Purpose:** Fresh CP2 L5X through the Site Forge product path for Curtis Studio inspection.  
**No new features. I/O generator unchanged.**

## CP2 fresh build

| Field | Value |
|-------|-------|
| L5X path | `exports/studio-validation/ORNCCP2_recovery_validation.L5X` |
| SHA256 | `df09fa9e410b1ec098bf013b314bc7ac85578cb7e9ff4f0c6e139b8e51f843ce` |
| RUN | `20251016-0933-OReillyGreensboro-ORNCCP2-RUN.tar.gz` |
| Product chain | Import → discover → SiteModel → fresh workbook → `from-run --with-io-map` |
| Ready for Curtis Studio test | **YES** (static precheck only — **not** Studio PASS) |

## Modules

| Metric | Value | Baseline floor | Match |
|--------|-------|----------------|-------|
| Total L5X modules | **39** | 39 | **YES** |
| RUN modules (`load_from_run`) | **37** | 37 | **YES** |
| Word map entries | **27** | 27 | **YES** |
| Adapters / heads | **7** | — | Local `1756-L83E`, `CPXXENET1` `1756-EN2T`, `T_1794_AENT_1..5` `1794-AENT` |
| Child modules | **32** | — | `1794-IA16/A`, `1794-IB16/A`, `1794-OA8I/A`, `1794-OB16P/A` under AENT parents |

Catalog set: `1756-L83E`, `1756-EN2T`, `1794-AENT`, `1794-IA16/A`, `1794-IB16/A`, `1794-OA8I/A`, `1794-OB16P/A`.

## IO_MAP

| Metric | Value |
|--------|-------|
| Program present | **YES** |
| XIC/OTE mapping refs | **68** (baseline 68) |
| NOP-only | **NO** |
| Exact baseline mapping | **PASS** |

Exact check:

```
XIC(T_1794_AENT_1:I.Data[6].11)OTE(PE215_J.I.PE_Clear);
```

## Device relationships (representative)

| Kind | Example | Module / channel | Dir | OK |
|------|---------|------------------|-----|----|
| Exact baseline PE | `PE215_J.I.PE_Clear` | `T_1794_AENT_1:I.Data[6].11` | I | YES |
| Photoeye | `PE142_JF.I.PE_Clear` | `T_1794_AENT_4:I.Data[1].0` | I | YES |
| Jam/full PE | `PE148_JF`, `PE238_JF`, … | AENT_4 Data[1].* | I | YES |
| Control / digital out | `T_2WH`, `WH310` | `T_1794_AENT_1:O.Data[1].*` | O | YES |
| Motor / VFD | — | CP2 equipment profile reports **0 VFDs** on this RUN scope | N/A | N/A (expected) |

## Transport programs

| Item | Present |
|------|---------|
| Area Fast | `ORNCCP2_Area_Fast` |
| Area Slow | `ORNCCP2_Area_Slow` |
| Area L1 / L2 | YES |
| IO_MAP | YES |
| System / Sys | YES |
| PE devices / PE logic rungs (report) | 44 / 44 |
| Conveyors (report) | 35 |

Area **names** are not fidelity targets; Fast/Slow/PE/IO relationships are.

## Static precheck

- XML parses: **YES** (preflight `ok: true` with warnings)
- Warnings: `missing_main_routine` for programs whose main is named `Main_Routine` (preflight looks for `Main`) — **false positive**, not a Studio claim
- Studio PASS claimed: **NO**

Artifacts:

- `exports/cp2-recovery-validation/studio_precheck.json`
- `exports/cp2-recovery-validation/STUDIO_STATIC_PRECHECK.md`

## Historical baseline match

**PASS** — modules 39, word map 27, IO_MAP 68, exact `PE215_J` mapping identical to `exports/io-regression-lock/cp2_io_baseline.json`.

I/O regression lock tests: **13/13 PASS**.

## Curtis checklist

See `exports/studio-validation/CP2_RECOVERY_CHECKLIST.md`.

## STOP

No Sorter/WCS/Area-inference/UI/I-O-architecture work. Awaiting Curtis visual Studio confirmation.
