# Demo A — GUI reproduction (MSCATL_CP3)

Curtis should see Site Forge itself, not only JSON.

## Launch

```powershell
cd C:\dev\worktree\FortnaPlus\desktop
.\Launch-SiteForge.bat
```

(or `Launch-Electron.ps1`)

## Load virgin MSCATL_CP3 RUN

Electron Browse Archive expects a `.tar.gz` (not a bare RUN directory).

### Option A — import existing Desktop TAR (if present)

Look for:

`C:\Users\curtiskricke\Desktop\MSC ATL\20260813-1428-MSCATL-MSCATL_CP3-RUN.tar.gz`

In Site Forge: **Browse Archive** / drop the tar.gz on I/O & Prints.

### Option B — pack the peek RUN then import

```powershell
cd C:\dev\worktree\FortnaPlus
python -c "import tarfile; from pathlib import Path; src=Path('workspace/_mscatl_peek/MSCATL_CP3'); out=Path('exports/demo/siteforge-reality-check-v1/MSCATL_CP3/MSCATL_CP3_peek_RUN.tar.gz');
tf=tarfile.open(out,'w:gz');
for p in (src/'RUN').rglob('*'):
  if p.is_file() and 'ABS_CARD' not in p.name.upper() and 'KTX_' not in p.name.upper():
    tf.add(p, arcname=str(Path('RUN')/p.relative_to(src/'RUN')).replace('\\\\','/'))
tf.close(); print(out, out.stat().st_size)"
```

Then Browse Archive → that tar.gz.

## What to look at

1. **Hardware / racks** — expect three provisional `AREA_RIO_N` racks (presentation aliases), each with adapter catalog, IP, slots/modules from the canonical model (not hardcoded Atlanta UI).
2. **I/O assignments** — physical claims scorecard region if shown; backend measurement already recorded 256 PROVEN / 0 unresolved / conservation PASS.
3. **Build readiness / compile** — virgin qualify overall was **FAIL** (merge P3012A missing + Safety REVIEW). Hardware/I-O PASS ≠ full-site READY.
4. Do **not** load finished L5X as discovery input.

## Screenshots

Automated Electron screenshots were not captured in this measurement pass.
Please capture locally if desired:

- `01_run_loaded.png`
- `02_hardware_racks.png`
- `03_io_assignments.png`
- `04_provenance.png` (if available)
- `05_build_readiness.png`
- `06_build_result.png`

Place under `exports/demo/siteforge-reality-check-v1/MSCATL_CP3/screenshots/`.

## Measurement already frozen (CLI)

```powershell
python tools/diagnostics/_reality_check_demo_a.py
```

Artifacts: `exports/demo/siteforge-reality-check-v1/MSCATL_CP3/`
