# CP2 — Generic FortnaPlus RUN Data Loader

Standalone archaeology. **Not** wired into production Site Forge.

CP1 baseline (frozen): `bedcb7a`

## Boundary

```
.mnu schema/runtime (CP1)
        ↓
CP2 generic ASC/ROM file selection + typed records
        ↓
(future) CP3 reference resolver
```

CP2 understands **storage**. It does **not** decide engineering meaning.

## FortnaPlus file precedence (SOURCE_PROVEN — `amenu.c`)

1. `Table.rom.<MACHINE>`
2. `Table.rom`
3. `Table.asc.<MACHINE>`
4. `Table.asc`

## CP2 supported physical formats

- **Decoded:** `.asc` / `.asc.<MACHINE>` (latin-1 text, `~` or quoted-comma rows)
- **Detected but not decoded:** `.rom` / `.rom.<MACHINE>`

If a higher-precedence `.rom` exists, CP2 reports `UNSUPPORTED_ROM` and does **not**
silently load ASC while claiming FortnaPlus selected ASC.

## Typed model

- `FortnaTable` / `FortnaRecord` / `FortnaValue`
- Every value keeps: menu, record index, column index/name, datatype raw+name,
  raw ASC text, typed value (when proven), physical file, schema origin, provenance.

Selection / MENU_COLUMN_ROW values remain raw tokens for CP3.

## ASC datatype conversions (SOURCE_PROVEN — `amenu.c` load switch)

| Datatype | ASC conversion |
|----------|----------------|
| STRING / TIMESTAMP | string copy |
| BOOLEAN_INTEGER / BOOLEAN_AS_BUTTON | `Y`/`y` → true, else false |
| INTEGER family | `sscanf %d` / `%ld` |
| HEXADECIMAL_INT | `sscanf %x` |
| OCTINT | `sscanf %o` |
| FORTNA_ONLY_INT | `strtol` base 2 |
| DOUBLE / FEET_INCHES / DOUBLE_AS_TIME_ELAPSED | `sscanf %lf` (ASC path; not UI `calc_feetinch`) |
| SELECTION / SELECTION_UNIQUE / MENU_COLUMN_ROW | preserve raw text |

## Tools

- `tools/scripts/fortna_run_loader.py`
- Artifact: `artifacts/fortna-run-typed-records.json`
