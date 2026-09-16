# CP3 — Generic FortnaPlus Reference Resolver

Standalone archaeology. **Not** wired into production Site Forge.

Frozen baselines:
- CP1: `bedcb7a`
- CP2: `83dc7bb`

## Pipeline

```
CP1 .mnu schema/runtime
        ↓
CP2 typed RUN records
        ↓
CP3 generic reference resolver
        ↓
Fortna relationship graph (+ complete reverse index)
```

## What CP3 resolves

Using SOURCE_PROVEN `find_data_source()` + selection identity lookup:

- `SELECTION` / `SELECTION_UNIQUE` → target menu + target record (by name column)
- `MENU_COLUMN_ROW` → target menu + target column
- dynamic datasource via `MenuMenu`
- static fallback when datasource record value ≤ 0
- unresolved taxonomy (capability vs RUN defect)

## What CP3 does **not** do

- physical conveyor topology
- Safety-zone membership
- merge lane = release conveyor engineering identity
- production Site Forge integration

## Harness

```powershell
python tools/scripts/fortna_decoder_acceptance.py --out-dir artifacts
```

Artifacts:
- `artifacts/fortna-reference-graph-plc2.json`
- `artifacts/fortna-reference-graph-plc4.json`
- `artifacts/fortna-reference-graph-plc5.json`
- `artifacts/fortna-decoder-cross-site-report.json`
