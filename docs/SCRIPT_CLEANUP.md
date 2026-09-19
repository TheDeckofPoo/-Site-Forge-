# Script Cleanup Manifest

**Cleanup commit parent baseline:** `68f63611511845e4614adae765db37f874a3623a`

## Before → After

| Metric | Before | After |
|--------|-------:|------:|
| `tools/scripts/**/*.py` | 271 | 125 |
| `tools/scripts/*.py` (top-level) | ~249 | 114 |
| `tools/scripts/test_*.py` | 109 | **0** |
| `tools/scripts/_emergency_*.py` | 20 (untracked) | **0** |
| `tools/diagnostics/*.py` | 0 | 15 |
| `tests/**/test_*.py` | 0 | 110 |

## Actions

- **DELETED:** 20 untracked `_emergency_*` + 3 tracked archaeology (`fortna_curve_validation.py`, `fortna_physical_runs.py`, `fortna_spiral_area_analysis.py`)
- **MOVED tests:** 109 `.py` + 2 `.js` → `tests/<area>/`
- **MOVED diagnostics:** 14 reusable tools → `tools/diagnostics/`
- **KEPT in scripts:** production entrypoints + core/compiler/decoder (including diagnostics imported by CP2 gates: `fortna_l5x_compare.py`, `fortna_physical_overlap_audit.py`)
- **REVIEW left in place:** 9–10 modules with insufficient delete evidence (see machine manifest)

## Policy going forward

- New tests → `tests/<area>/`
- New diagnostics → `tools/diagnostics/`
- Do not commit `_tmp_*` / `_emergency_*` under `tools/scripts/`
- Hygiene gate: `tests/regression/test_scripts_hygiene.py`
- Git history is the archive — no junk `archive/` folder
- Core modules were **not** consolidated

Machine-readable detail: `exports/stabilization/script_cleanup_manifest.json`
