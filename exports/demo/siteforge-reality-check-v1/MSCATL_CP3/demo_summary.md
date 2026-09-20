# Demo A — MSCATL_CP3 Reality Check

**Git SHA:** `25b0752d5c364e04b7cd3ee2b0e34a96524a6d24`
**RUN:** `C:\dev\worktree\FortnaPlus\workspace\_mscatl_peek\MSCATL_CP3\RUN`
**Virgin recompute:** YES

## Physical I/O scorecard

| Metric | Expected | Actual | Delta |
|--------|---------:|-------:|------:|
| raw physical claims | 256 | 256 | 0 |
| PROVEN | 256 | 256 | 0 |
| needs_resolution | 0 | 0 | 0 |
| racks | 3 | 3 | 0 |
| conservation | PASS | PASS | match=True |

**Matches prior accepted expectation:** True

Also: ASSIGNED=256, DERIVED=0,
REVIEW_REQUIRED=0, UNKNOWN=0,
duplicate_channels=0,
unplaced_modules=0.

## Build readiness

**Overall: HARDWARE_IO_READY__FULL_SITE_PARTIAL**

See `build_readiness.md`.

## Compiler

- Qualification overall: `FAIL`
- L5X generated: True
- L5X path: `exports/demo/siteforge-reality-check-v1/MSCATL_CP3/generated/MSCATL_CP3_SiteForge.L5X`
- Preflight: `PREFLIGHT_PASS`
- Studio import: `NOT_PERFORMED`

## GUI reproduction

1. From repo root, optionally pack RUN: create/import MSCATL_CP3 tar.gz via Site Forge Browse Archive
   (or copy peek RUN content into a temp tar and import).
2. Launch: `desktop\Launch-SiteForge.bat`
3. Open Hardware / I-O view — expect 3× AREA_RIO provisional racks from canonical model.
4. Do **not** load finished L5X as discovery input.

Exact CLI measurement (already run):

```powershell
python tools/diagnostics/_reality_check_demo_a.py
python tools/scripts/fortna_hardware_io_model.py --run-dir workspace/_mscatl_peek/MSCATL_CP3/RUN --machine MSCATL_CP3 --out exports/demo/siteforge-reality-check-v1/MSCATL_CP3/hardware_io_model.json
```
