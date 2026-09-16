# FortnaPlus `.mnu` Schema (Proven Grammar)
Archaeology checkpoint. This document records only what the supplied `fortna.mnu` / `project.mnu` files prove. Unknown column semantics remain unknown.

See also **`docs/FORTNAPLUS_MNU_RUNTIME.md`** for SOURCE_PROVEN FortnaPlus runtime
semantics (`find_data_source`, datatype constants, ASC selection resolution).
## Files analyzed
- `workspace\_plc2_run_peek\RUN\FORTNA\fortna.mnu` · origin=FORTNA · definitions=493 · fields=8827 · lines=9814 · bytes=1191828
- `workspace\_reno_peek\20260813-1132-MSCRENO-MSCRENOPACK-RUN\RUN\FORTNA\fortna.mnu` · origin=FORTNA · definitions=495 · fields=8837 · lines=9828 · bytes=1193377
- `workspace\_reno_peek\20260813-1132-MSCRENO-MSCRENOPICK-RUN\RUN\FORTNA\fortna.mnu` · origin=FORTNA · definitions=495 · fields=8837 · lines=9828 · bytes=1193374
- `workspace\_reno_peek\20260813-1132-MSCRENO-MSCRENOSHIP-RUN\RUN\FORTNA\fortna.mnu` · origin=FORTNA · definitions=495 · fields=8837 · lines=9828 · bytes=1193375
- `workspace\active_rio_audit\RUN\FORTNA\fortna.mnu` · origin=FORTNA · definitions=493 · fields=8827 · lines=9814 · bytes=1191832
- `workspace\cp4-run\RUN\FORTNA\fortna.mnu` · origin=FORTNA · definitions=493 · fields=8827 · lines=9814 · bytes=1191826
- `workspace\cp5-run\RUN\FORTNA\fortna.mnu` · origin=FORTNA · definitions=493 · fields=8827 · lines=9814 · bytes=1191831
- `workspace\_plc2_run_peek\RUN\PROJECT\project.mnu` · origin=PROJECT · definitions=194 · fields=2868 · lines=3257 · bytes=392137

## Proven top-level grammar
1. Line 1 is a dual header split by the literal token `***`.
2. Tokens left of `***` name **menu/definition** columns.
3. Tokens right of `***` name **field/column** columns.
4. A **definition** begins on a row whose token count equals the menu-column count and whose final token matches `[01]{16}` (the `FLAGS` column).
5. Subsequent non-blank rows are **fields** until a blank line.
6. Blank lines separate definition blocks.
7. Encoding observed: Latin-1 / LF.

### Menu columns (from file header)

```
MNUNAME ROW COL FG BG HFG HBG TY TX TYPE #RECS LOC FONT CURR MXCR DREC VERP BRODCAST DISPMAX FILTERED DSTYPE NOBOX FLAGS
```

### Field columns (from file header)

```
COLNAME DTYPE DLEN DLOW DHIGH DLIST DSECR DHIDE DFONT DX DY DRTYPE DORD DFG DBG DHFG DHBG DSRC DDLEN DSPACE DSTRING DSELHIDE DSQLCLS
```

## Convenience raw field mapping
For readability the decoder exposes these header names as convenience fields without asserting application datatype meaning:

| Convenience | Header token |
|---|---|
| `name` | `COLNAME` / `MNUNAME` |
| `rawDatatype` | `DTYPE` |
| `rawLength` | `DLEN` |
| `rawLow` | `DLOW` |
| `rawHigh` | `DHIGH` |
| `rawList` | `DLIST` |
| `rawDataSource` | `DSRC` |

## Cross-table name evidence
When `DLIST` is a non-blank quoted string, the decoder records `listReference = <unquoted DLIST>`.
If that string equals an `MNUNAME` present in the loaded schema(s), `resolved=true`.

**SOURCE_PROVEN (runtime upgrade):** FortnaPlus loads `DLIST` into a temporary select
string and, for selection datatypes, resolves it with `menu_info()` into
`dataselect[menu][column]` (a menu index). `DSRC` is the `datasource[][]` column
index used by `find_data_source()`. See `docs/FORTNAPLUS_MNU_RUNTIME.md`.

**Still not asserted:** that every selection is physical equipment connectivity or
PLC tag ownership.

## FORTNA vs PROJECT combination
Combined unique definition names: **687**.
Name collisions across origins (reported, not auto-resolved): **0**.

Policy: `NONE_APPLIED_REPORT_ONLY` — both copies are retained with provenance.

## Multi-version fortna.mnu summary
- Definitions union: 495
- Common to all versions: 493
- Identical (vs baseline): 353
- Changed (vs baseline): 140
- Added/removed: 2
- Reference change events: 0

## Machine-specific ASC resolution (documented helper only)
Developer-provided rule (not wired into production):

```
if Table.asc.<AC_NAME> exists:
    use Table.asc.<AC_NAME>
else:
    use Table.asc
```

Implemented as `resolve_asc_path()` in `tools/scripts/fortna_mnu_schema.py` with unit tests. Not integrated into Site Forge production loaders.

## What remains UNKNOWN
- Meaning of numeric `DTYPE`, `DLEN`, `DLOW`, `DHIGH`, `DSRC`, and other menu/field metadata columns beyond their header names.
- Whether `DLIST` is always a definition reference, a pick-list name, or both.
- FortnaPlus runtime precedence between colliding `fortna.mnu` and `project.mnu` definitions (collisions reported only).
