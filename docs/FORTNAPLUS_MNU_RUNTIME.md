# FortnaPlus `.mnu` Runtime Archaeology

Standalone archaeology documentation. **Not** wired into production Site Forge.

This document upgrades the earlier DLIST-name graph with **SOURCE_PROVEN** FortnaPlus
runtime semantics from `fmenu.h` / `fmenu.c` / `amenu.c`.

## Pipeline

```
.mnu schema (fortna.mnu + project.mnu)
        ↓
runtime menu metadata (mnuparms / column arrays)
        ↓
ASC records (Table.asc.<AC_NAME> else Table.asc)
        ↓
find_data_source() → STATIC / DYNAMIC / UNRESOLVED
        ↓
resolved relationship graph (+ reverse lookup)
```

## Runtime metadata (SOURCE_PROVEN)

From `fmenu.h`:

### Menu level

- `mnuparms[]` — `MNUPARMREC` (`mnuname`, `type`, `arrays`, `pointermemb`, `mycurr`,
  `datarec`, `vertp`, `mymaxcurr`, `broadcast`, `menudispmax`, `filtered`, `disptype`,
  `nobox`, `flags`, …)
- `mnuitems[]` — column count per menu
- `menudata[]` — loaded record values

### Column level

`datatype[][]`, `datalen[][]`, `datalow[][]`, `datahigh[][]`, `dataselect[][]`,
`datasecure[][]`, `datahide[][]`, `datafont[][]`, `dataxcord[][]`, `dataycord[][]`,
`datarealtype[][]`, `dataorder[][]`, `datafg[][]`, `databg[][]`, `datahfg[][]`,
`datahbg[][]`, `datasource[][]`, `datadisplen[][]`, `dataspace[][]`, `datastring[][]`,
`dataselhide[][]`, `datasqlclause[][]`

### `.mnu` header ↔ runtime map

Field header tokens (`DTYPE`, `DLIST`, `DSRC`, …) are read by `amenu.c`/`fmenu.c`
into the arrays above. Archaeology convenience names:

| `.mnu` token | Runtime array | Status |
|---|---|---|
| `DTYPE` | `datatype` | SOURCE_PROVEN |
| `DLEN` | `datalen` | SOURCE_PROVEN |
| `DLOW` / `DHIGH` | `datalow` / `datahigh` | SOURCE_PROVEN |
| `DLIST` | becomes `dataselect` menu index via `menu_info()` | SOURCE_PROVEN |
| `DSRC` | `datasource` (column index; `0` = unused) | SOURCE_PROVEN |

## Datatype constants (SOURCE_PROVEN — `fmenu.h`)

Decoder emits both `datatypeRaw` and `datatypeName`.

Notable values: `STRING=0`, `INTEGER=1`, … `SELECTION=20`, `SELECTION_UNIQUE=21`,
`MENU_COLUMN_ROW=25`, `MENU_TITLE_LINE=250`, `DATABASE_LINE=260`.

Unknown numeric codes remain unnamed (`datatypeName: null`).

## `find_data_source()` in plain English (SOURCE_PROVEN — `fmenu.c`)

For menu `a`, column `cur`, record `rec`:

1. Look at `datasource[a][cur]`.
2. If it is a **valid column index** (`> 0` and within `mnuitems[a]`),
   and that source column is **`SELECTION_UNIQUE`**,
   and that source column’s `dataselect` is **`MenuMenu`**,
   then this field is **dynamic**:
   - Read the integer currently stored in that datasource column for record `rec`.
   - If that value is **`> 0`**, it **is** the target menu index.
   - If it is **`≤ 0`**, fall back to the field’s normal `dataselect[a][cur]`.
3. Otherwise the field is **static**: use `dataselect[a][cur]`.

Archaeology resolution modes:

| Mode | Meaning |
|---|---|
| `STATIC` | Target menu comes from `dataselect` / DLIST |
| `DYNAMIC` | Target menu comes from another column’s record value (MenuMenu selection) |
| `UNRESOLVED` | Dynamic schema needs a record value that is missing/invalid, or datasource column is invalid — **no guess** |

## ASC resolution (SOURCE_PROVEN load order in `amenu.c`)

Observed open order in `amenu.c`:

1. `Table.rom.<MACHINE>`
2. `Table.rom`
3. `Table.asc.<MACHINE>`
4. `Table.asc`

This archaeology tool’s helper (task contract) reports:

1. `Table.asc.<AC_NAME>` if present
2. else `Table.asc`

and records the **physical file** used. No silent precedence.

## What a relationship is (and is not)

A resolved edge means:

> schema (+ optional ASC cell) proves a selection reference from
> `sourceMenu.sourceColumn[@record]` → `targetMenu[@record]`

It does **not** automatically mean:

- physical conveyor adjacency
- Safety zone membership
- merge release identity
- commissioning-complete topology

## Earlier archaeology vs runtime upgrade

Previous DLIST-name graph treated every non-blank `DLIST` as a named cross-table edge.

After runtime semantics:

- Edges carry `datatypeRaw/Name`, `dataselectRaw`, `datasourceRaw`, `resolutionMode`
- Dynamic fields (e.g. `Parameters.Data` with `PopupMenu` → `MenuMenu`) are distinguished
- Unresolved dynamic cases stay unresolved until ASC/record evidence exists

## Still UNKNOWN / DATA_OBSERVED

| Item | Status |
|---|---|
| Exact mapping of every short menu-header token (`TY`, `TX`, `LOC`, …) to `MNUPARMREC` fields | DATA_OBSERVED / partial |
| Full meaning of non-selection datatypes in commissioning | UNKNOWN |
| Whether every SELECTION is equipment connectivity | UNKNOWN (explicitly not claimed) |
| `.rom` vs `.asc` precedence policy for Site Forge production | SOURCE_PROVEN in FortnaPlus; Site Forge not wired |

## Tools

- `tools/scripts/fortna_mnu_schema.py` — `.mnu` parse / version diff / ASC path helper
- `tools/scripts/fortna_mnu_runtime.py` — runtime catalog, `find_data_source`, ASC load, graph
- Artifacts: `artifacts/mnu-runtime-relationships.json`
