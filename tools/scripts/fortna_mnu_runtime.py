#!/usr/bin/env python3
"""FortnaPlus .mnu runtime archaeology — SOURCE_PROVEN selection resolution.

Standalone tooling only. Does NOT wire into production Site Forge.

Source evidence (copied into repo archaeology docs, not production):
  Desktop FortnaPlus files: fmenu.h, fmenu.c::find_data_source, amenu.c ASC load.

Provenance tags:
  SOURCE_PROVEN  — demonstrated by FortnaPlus C source
  DATA_OBSERVED  — repeatable in supplied RUN/.mnu data, not claimed as runtime law
  UNKNOWN        — not yet known
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fortna_mnu_schema import (
    MnuDefinition,
    MnuSchema,
    combine_schemas,
    parse_mnu_file,
    resolve_asc_path,
    unquote,
)

ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# SOURCE_PROVEN datatype constants — fmenu.h
# ---------------------------------------------------------------------------

DATATYPE_NAMES: dict[int, str] = {
    0: "STRING",
    1: "INTEGER",
    2: "LONG_INTEGER",
    3: "DOUBLE",
    4: "DOUBLE_AS_TIME_ELAPSED",
    5: "UNSIGNED_CHAR",
    6: "UNSIGNED_CHAR_AS_BOOLEAN",
    7: "LONG_INT_AS_TIME",
    8: "FORTNA_ONLY_INT",
    9: "FORTNA_ONLY_INT2",
    10: "HEXADECIMAL_INT",
    11: "BOOLEAN_INTEGER",
    12: "OCTINT",
    13: "FEET_INCHES",
    14: "TIMESTAMP",
    15: "BLOB",
    20: "SELECTION",
    21: "SELECTION_UNIQUE",
    25: "MENU_COLUMN_ROW",
    30: "GO_MENU",
    31: "GO_SQL",
    33: "GO_PROCEDURE",
    34: "DO_PROCEDURE_ONCE",
    35: "INTEGER_AS_GAUGE",
    36: "BOOLEAN_AS_BUTTON",
    37: "INTEGER_AS_BITSET",
    38: "INTEGER_AS_ROLESET",
    40: "LOAD_DDS_WINDOW",
    41: "EXECUTE_EXTERNAL",
    250: "MENU_TITLE_LINE",
    260: "DATABASE_LINE",
}

SELECTION = 20
SELECTION_UNIQUE = 21
MENU_COLUMN_ROW = 25
MENU_TITLE_LINE = 250
STRING = 0

# .mnu field header token → runtime array name (SOURCE_PROVEN: fmenu.h + amenu.c sscanf)
FIELD_HEADER_TO_RUNTIME: dict[str, str] = {
    "COLNAME": "mnu",  # column name strings
    "DTYPE": "datatype",
    "DLEN": "datalen",
    "DLOW": "datalow",
    "DHIGH": "datahigh",
    "DLIST": "dataselect",  # name resolved to menu index at load via menu_info()
    "DSECR": "datasecure",
    "DHIDE": "datahide",
    "DFONT": "datafont",
    "DX": "dataxcord",
    "DY": "dataycord",
    "DRTYPE": "datarealtype",
    "DORD": "dataorder",
    "DFG": "datafg",
    "DBG": "databg",
    "DHFG": "datahfg",
    "DHBG": "datahbg",
    "DSRC": "datasource",
    "DDLEN": "datadisplen",
    "DSPACE": "dataspace",
    "DSTRING": "datastring",
    "DSELHIDE": "dataselhide",
    "DSQLCLS": "datasqlclause",
}

# .mnu menu header token → MNUPARMREC field (SOURCE_PROVEN: fmenu.h typedef)
MENU_HEADER_TO_MNUPARM: dict[str, str] = {
    "MNUNAME": "mnuname",
    "ROW": "mrow",
    "COL": "mcol",
    "FG": "mfg",
    "BG": "mbg",
    "HFG": "mhfg",
    "HBG": "mhbg",
    "TY": "type",  # DATA_OBSERVED mapping of short header → type; see notes
    "TYPE": "type",
    "#RECS": "arrays",
    "FONT": "font",
    "CURR": "mycurr",
    "MXCR": "mymaxcurr",
    "DREC": "datarec",
    "VERP": "vertp",
    "BRODCAST": "broadcast",
    "DISPMAX": "menudispmax",
    "FILTERED": "filtered",
    "DSTYPE": "disptype",
    "NOBOX": "nobox",
    "FLAGS": "flags",
    "LOC": "pointermemb",  # DATA_OBSERVED: LOC aligns with pointermemb usage in loaders
}

SEMANTIC_RULES: list[dict[str, str]] = [
    {
        "id": "datatype_constants",
        "status": "SOURCE_PROVEN",
        "evidence": "fmenu.h datatype #define block",
    },
    {
        "id": "column_metadata_arrays",
        "status": "SOURCE_PROVEN",
        "evidence": "fmenu.h extern datatype[][], dataselect[][], datasource[][], …",
    },
    {
        "id": "mnuparmrec_struct",
        "status": "SOURCE_PROVEN",
        "evidence": "fmenu.h typedef struct MNUPARMREC",
    },
    {
        "id": "find_data_source",
        "status": "SOURCE_PROVEN",
        "evidence": "fmenu.c::find_data_source(int a, int cur, int rec)",
    },
    {
        "id": "dlist_to_dataselect_via_menu_info",
        "status": "SOURCE_PROVEN",
        "evidence": "fmenu.c load path: tempselect → menu_info() → dataselect[a][b]",
    },
    {
        "id": "asc_machine_specific_then_generic",
        "status": "SOURCE_PROVEN",
        "evidence": "amenu.c opens Table.asc.<MACHINE> then Table.asc (also tries .rom variants first)",
    },
    {
        "id": "selection_value_matches_target_name_column",
        "status": "SOURCE_PROVEN",
        "evidence": "amenu.c SELECTION/SELECTION_UNIQUE load compares ASC token to MNUSTR(target, 1, d)",
    },
    {
        "id": "header_TY_means_type",
        "status": "DATA_OBSERVED",
        "evidence": "short header token TY co-occurs with TYPE values; not uniquely proven vs prstart fields",
    },
    {
        "id": "header_LOC_means_pointermemb",
        "status": "DATA_OBSERVED",
        "evidence": "LOC numeric slot used like pointermemb in archaeology mapping; confirm against full loader",
    },
]


def datatype_name(raw: int | str | None) -> str | None:
    try:
        v = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return DATATYPE_NAMES.get(v)


def _as_int(raw: Any, default: int = 0) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Runtime menu model built from parsed .mnu
# ---------------------------------------------------------------------------


@dataclass
class RuntimeColumn:
    index: int
    name: str
    datatypeRaw: int
    datatypeName: str | None
    datalen: int
    datalow: int
    datahigh: int
    dataselectRaw: str  # DLIST string from .mnu
    dataselectMenuIndex: int | None  # resolved via menu name index, or None
    datasourceRaw: int  # DSRC integer column index
    datasecure: int
    datahide: int
    datafont: int
    dataxcord: int
    dataycord: int
    datarealtype: int
    dataorder: int
    datafg: int
    databg: int
    datahfg: int
    datahbg: int
    datadisplen: int
    dataspace: int
    datastring: str
    dataselhide: int
    datasqlclause: int
    line: int | None = None


@dataclass
class RuntimeMenu:
    index: int
    mnuname: str
    origin: str
    sourceFile: str
    mnuparm: dict[str, Any]
    columns: list[RuntimeColumn]
    arrays: int  # #RECS capacity from menu header
    type: int


@dataclass
class RuntimeCatalog:
    menus: list[RuntimeMenu]
    by_name: dict[str, RuntimeMenu]
    by_index: dict[int, RuntimeMenu]
    menu_menu_index: int | None  # index of MenuMenu if present
    semanticRules: list[dict[str, str]] = field(default_factory=lambda: list(SEMANTIC_RULES))


def build_runtime_catalog(*schemas: MnuSchema) -> RuntimeCatalog:
    """Map parsed .mnu definitions into runtime-shaped menu/column metadata."""
    # Stable index order: FORTNA menus first (as FortnaPlus loads), then PROJECT.
    menus: list[RuntimeMenu] = []
    for schema in schemas:
        for d in schema.definitions:
            menus.append(_definition_to_runtime_menu(d, schema, index=len(menus)))

    by_name: dict[str, RuntimeMenu] = {}
    for m in menus:
        # First wins for name lookup (FORTNA before PROJECT if that order was passed)
        by_name.setdefault(m.mnuname, m)

    # Resolve dataselectRaw → menu index
    for m in menus:
        for col in m.columns:
            name = (col.dataselectRaw or "").strip()
            if not name:
                col.dataselectMenuIndex = 0
                continue
            target = by_name.get(name)
            col.dataselectMenuIndex = target.index if target else None

    menu_menu = by_name.get("MenuMenu")
    return RuntimeCatalog(
        menus=menus,
        by_name=by_name,
        by_index={m.index: m for m in menus},
        menu_menu_index=menu_menu.index if menu_menu else None,
    )


def _definition_to_runtime_menu(d: MnuDefinition, schema: MnuSchema, *, index: int) -> RuntimeMenu:
    mnuparm: dict[str, Any] = {"mnuname": d.name}
    for hdr, runtime_name in MENU_HEADER_TO_MNUPARM.items():
        if hdr in d.rawMetadata:
            raw = d.rawMetadata[hdr]
            if runtime_name == "mnuname":
                mnuparm[runtime_name] = unquote(raw)
            elif runtime_name == "flags":
                mnuparm[runtime_name] = raw
            else:
                mnuparm[runtime_name] = _as_int(raw, 0)
    # Preserve unmapped menu header keys as raw
    for hdr, raw in d.rawMetadata.items():
        if hdr not in MENU_HEADER_TO_MNUPARM:
            mnuparm[f"raw_{hdr}"] = raw

    columns: list[RuntimeColumn] = []
    for i, f in enumerate(d.fields):
        dt = _as_int(f.rawDatatype, -1)
        meta = f.rawMetadata or {}
        columns.append(
            RuntimeColumn(
                index=i,
                name=f.name,
                datatypeRaw=dt,
                datatypeName=datatype_name(dt),
                datalen=_as_int(f.rawLength),
                datalow=_as_int(f.rawLow),
                datahigh=_as_int(f.rawHigh),
                dataselectRaw=(f.rawList or "").strip(),
                dataselectMenuIndex=None,
                datasourceRaw=_as_int(f.rawDataSource, 0),
                datasecure=_as_int(meta.get("DSECR", 0)),
                datahide=_as_int(meta.get("DHIDE", 0)),
                datafont=_as_int(meta.get("DFONT", 0)),
                dataxcord=_as_int(meta.get("DX", 0)),
                dataycord=_as_int(meta.get("DY", 0)),
                datarealtype=_as_int(meta.get("DRTYPE", 0)),
                dataorder=_as_int(meta.get("DORD", 0)),
                datafg=_as_int(meta.get("DFG", 0)),
                databg=_as_int(meta.get("DBG", 0)),
                datahfg=_as_int(meta.get("DHFG", 0)),
                datahbg=_as_int(meta.get("DHBG", 0)),
                datadisplen=_as_int(meta.get("DDLEN", 0)),
                dataspace=_as_int(meta.get("DSPACE", 0)),
                datastring=unquote(meta.get("DSTRING", "")),
                dataselhide=_as_int(meta.get("DSELHIDE", 0)),
                datasqlclause=_as_int(meta.get("DSQLCLS", 0)),
                line=(f.provenance or {}).get("line"),
            )
        )

    return RuntimeMenu(
        index=index,
        mnuname=d.name,
        origin=schema.origin,
        sourceFile=schema.sourceFile,
        mnuparm=mnuparm,
        columns=columns,
        arrays=_as_int(d.rawMetadata.get("#RECS", 0)),
        type=_as_int(d.rawMetadata.get("TYPE", d.rawMetadata.get("TY", 0))),
    )


# ---------------------------------------------------------------------------
# find_data_source — SOURCE_PROVEN from fmenu.c
# ---------------------------------------------------------------------------


def find_data_source(
    catalog: RuntimeCatalog,
    menu: RuntimeMenu | str | int,
    column: int,
    *,
    datasource_record_value: int | None = None,
) -> dict[str, Any]:
    """Standalone equivalent of fmenu.c::find_data_source(a, cur, rec).

    SOURCE_PROVEN algorithm:
      if datasource[menu][column] > 0
         and mnuitems[menu] >= datasource[menu][column]
         and datatype[menu][datasource_col] == SELECTION_UNIQUE
         and dataselect[menu][datasource_col] == MenuMenu
      then:
         if record_value_at_datasource_col > 0:
             select = that value   # menu index
         else:
             select = dataselect[menu][column]
      else:
         select = dataselect[menu][column]

    When ASC/record data is unavailable, dynamic branch is UNRESOLVED rather than guessed.
    """
    m = _resolve_menu(catalog, menu)
    evidence = [
        {
            "rule": "find_data_source",
            "status": "SOURCE_PROVEN",
            "evidence": "fmenu.c::find_data_source",
        }
    ]
    if m is None:
        return {
            "ok": False,
            "resolutionMode": "UNRESOLVED",
            "reason": "unknown_menu",
            "targetMenuIndex": None,
            "targetMenu": None,
            "evidence": evidence,
        }
    if column < 0 or column >= len(m.columns):
        return {
            "ok": False,
            "resolutionMode": "UNRESOLVED",
            "reason": "invalid_column",
            "targetMenuIndex": None,
            "targetMenu": None,
            "evidence": evidence,
        }

    col = m.columns[column]
    static_idx = col.dataselectMenuIndex
    static_name = col.dataselectRaw or None
    mnuitems = len(m.columns)
    ds = col.datasourceRaw

    dynamic_ok = (
        ds > 0
        and mnuitems >= ds
        and ds < mnuitems
        and m.columns[ds].datatypeRaw == SELECTION_UNIQUE
        and catalog.menu_menu_index is not None
        and m.columns[ds].dataselectMenuIndex == catalog.menu_menu_index
    )

    if not dynamic_ok:
        if ds > 0 and not (mnuitems >= ds and ds < mnuitems):
            return {
                "ok": False,
                "resolutionMode": "UNRESOLVED",
                "reason": "invalid_datasource_column",
                "datasourceRaw": ds,
                "targetMenuIndex": static_idx,
                "targetMenu": static_name,
                "evidence": evidence
                + [{"rule": "invalid_datasource", "status": "SOURCE_PROVEN"}],
            }
        return {
            "ok": static_idx is not None or not static_name,
            "resolutionMode": "STATIC",
            "reason": "no_dynamic_datasource",
            "datasourceRaw": ds,
            "dataselectRaw": static_name,
            "targetMenuIndex": static_idx,
            "targetMenu": (
                catalog.by_index[static_idx].mnuname
                if static_idx is not None and static_idx in catalog.by_index
                else static_name
            ),
            "evidence": evidence,
        }

    # Dynamic path available in schema
    if datasource_record_value is None:
        return {
            "ok": False,
            "resolutionMode": "UNRESOLVED",
            "reason": "dynamic_schema_but_record_value_unavailable",
            "datasourceRaw": ds,
            "datasourceColumn": m.columns[ds].name,
            "dataselectRaw": static_name,
            "fallbackTargetMenuIndex": static_idx,
            "fallbackTargetMenu": static_name,
            "targetMenuIndex": None,
            "targetMenu": None,
            "evidence": evidence
            + [
                {
                    "rule": "dynamic_requires_record",
                    "status": "SOURCE_PROVEN",
                    "note": "MNUINT(pointermemb, datasource_col, rec) needed",
                }
            ],
        }

    if datasource_record_value > 0:
        tgt = catalog.by_index.get(datasource_record_value)
        return {
            "ok": tgt is not None,
            "resolutionMode": "DYNAMIC",
            "reason": "datasource_record_value_gt_0",
            "datasourceRaw": ds,
            "datasourceColumn": m.columns[ds].name,
            "datasourceRecordValue": datasource_record_value,
            "targetMenuIndex": datasource_record_value,
            "targetMenu": tgt.mnuname if tgt else None,
            "evidence": evidence,
        }

    # fallback to static dataselect
    return {
        "ok": static_idx is not None or not static_name,
        "resolutionMode": "STATIC",
        "reason": "dynamic_fallback_datasource_value_le_0",
        "datasourceRaw": ds,
        "datasourceColumn": m.columns[ds].name,
        "datasourceRecordValue": datasource_record_value,
        "dataselectRaw": static_name,
        "targetMenuIndex": static_idx,
        "targetMenu": (
            catalog.by_index[static_idx].mnuname
            if static_idx is not None and static_idx in catalog.by_index
            else static_name
        ),
        "evidence": evidence,
    }


def _resolve_menu(catalog: RuntimeCatalog, menu: RuntimeMenu | str | int) -> RuntimeMenu | None:
    if isinstance(menu, RuntimeMenu):
        return menu
    if isinstance(menu, int):
        return catalog.by_index.get(menu)
    return catalog.by_name.get(str(menu))


# ---------------------------------------------------------------------------
# ASC loading
# ---------------------------------------------------------------------------


def parse_asc_file(path: Path) -> dict[str, Any]:
    """Parse a Fortna ASC table file (tilde or quoted-comma forms).

    DATA_OBSERVED separators from amenu.c load + supplied RUN files.
    """
    path = Path(path)
    text = path.read_bytes().decode("latin-1", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip() != ""]
    if not lines:
        return {"path": str(path), "columns": [], "records": []}

    header = _split_asc_row(lines[0])
    # Strip surrounding quotes from header names
    columns = [c.strip().strip('"') for c in header]
    records: list[dict[str, Any]] = []
    for i, line in enumerate(lines[1:], start=1):
        cells = _split_asc_row(line)
        # Pad/truncate to header width
        if len(cells) < len(columns):
            cells = cells + [""] * (len(columns) - len(cells))
        elif len(cells) > len(columns):
            cells = cells[: len(columns)]
        row = {columns[j]: cells[j] for j in range(len(columns))}
        row["_recordIndex"] = i  # 1-based data row index (0 often unused in runtime)
        records.append(row)
    return {"path": str(path), "columns": columns, "records": records}


def _split_asc_row(line: str) -> list[str]:
    if "~" in line:
        return line.split("~")
    # quoted CSV-ish: "a","b", c
    if line.lstrip().startswith('"'):
        parts: list[str] = []
        i = 0
        n = len(line)
        while i < n:
            if line[i] == '"':
                j = i + 1
                while j < n and line[j] != '"':
                    j += 1
                parts.append(line[i + 1 : j])
                i = j + 1
                while i < n and line[i] in " ,\t":
                    i += 1
            else:
                j = i
                while j < n and line[j] != ",":
                    j += 1
                parts.append(line[i:j].strip())
                i = j + 1
        return parts
    return [p.strip() for p in line.split(",")]


def load_run_tables(
    catalog: RuntimeCatalog,
    run_dir: Path | str,
    *,
    ac_name: str,
) -> dict[str, Any]:
    """Load ASC tables for menus in catalog using machine-specific resolution."""
    run_dir = Path(run_dir)
    search_dirs = []
    for sub in ("FORTNA", "PROJECT", ""):
        d = run_dir / sub if sub else run_dir
        if d.is_dir():
            search_dirs.append(d)

    tables: dict[str, Any] = {}
    diagnostics: list[dict[str, Any]] = []

    for menu in catalog.menus:
        chosen = None
        resolution = None
        for d in search_dirs:
            resolution = resolve_asc_path(menu.mnuname, directory=d, ac_name=ac_name)
            if resolution.get("chosen"):
                chosen = Path(resolution["chosen"])
                break
        if not chosen:
            diagnostics.append(
                {
                    "kind": "ASC_MISSING",
                    "menu": menu.mnuname,
                    "acName": ac_name,
                    "searched": [str(x) for x in search_dirs],
                }
            )
            continue
        parsed = parse_asc_file(chosen)
        tables[menu.mnuname] = {
            "menu": menu.mnuname,
            "menuIndex": menu.index,
            "origin": menu.origin,
            "physicalFile": str(chosen),
            "chosenKind": resolution.get("chosenKind") if resolution else None,
            "columns": parsed["columns"],
            "recordCount": len(parsed["records"]),
            "records": parsed["records"],
        }
    return {"tables": tables, "diagnostics": diagnostics, "acName": ac_name}


# ---------------------------------------------------------------------------
# Relationship graph
# ---------------------------------------------------------------------------


def _name_column_key(menu: RuntimeMenu, table: dict[str, Any] | None) -> str | None:
    """Prefer runtime column index 1 STRING name; else first ASC header."""
    if len(menu.columns) > 1 and menu.columns[1].datatypeRaw == STRING:
        # ASC header may use the column name from .mnu
        return menu.columns[1].name
    if table and table.get("columns"):
        # skip obvious title
        for c in table["columns"]:
            if c and c.lower() not in {"", "name"}:
                # still prefer literal 'Name' variants
                pass
        for prefer in ("Name", "IO_Name", "Motor_Name", "Desc", "Parameter Name"):
            if prefer in (table.get("columns") or []):
                return prefer
        return table["columns"][0]
    return None


def _is_dynamic_capable(catalog: RuntimeCatalog, menu: RuntimeMenu, col: RuntimeColumn) -> bool:
    ds = col.datasourceRaw
    return (
        ds > 0
        and ds < len(menu.columns)
        and menu.columns[ds].datatypeRaw == SELECTION_UNIQUE
        and catalog.menu_menu_index is not None
        and menu.columns[ds].dataselectMenuIndex == catalog.menu_menu_index
    )


def build_relationship_graph(
    catalog: RuntimeCatalog,
    tables: dict[str, Any] | None = None,
    *,
    max_records_per_table: int = 250,
) -> dict[str, Any]:
    """Build STATIC/DYNAMIC/UNRESOLVED relationship edges from schema (+ optional ASC).

    Emits:
      - one schema-level edge per selection-capable column
      - per-record edges for loaded ASC tables (capped by max_records_per_table)
    """
    tables = tables or {}
    relationships: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    unknown_dtypes: set[int] = set()

    # Pre-index target name → record for each loaded table
    name_index: dict[str, dict[str, int]] = {}
    for mname, table in tables.items():
        menu = catalog.by_name.get(mname)
        if not menu:
            continue
        key = _name_column_key(menu, table)
        idx: dict[str, int] = {}
        if key:
            for rec in table["records"]:
                val = str(rec.get(key, "")).strip()
                if val and val.upper() not in {"INVALID", "N/A", "NONE"}:
                    idx.setdefault(val, int(rec["_recordIndex"]))
        name_index[mname] = idx

    for menu in catalog.menus:
        table = tables.get(menu.mnuname)
        for col in menu.columns:
            if col.datatypeRaw == MENU_TITLE_LINE:
                continue
            if col.datatypeRaw not in (SELECTION, SELECTION_UNIQUE, MENU_COLUMN_ROW):
                if col.datatypeName is None and col.datatypeRaw >= 0:
                    unknown_dtypes.add(col.datatypeRaw)
                continue
            if not (col.dataselectRaw or col.datasourceRaw):
                continue

            schema_res = find_data_source(catalog, menu, col.index, datasource_record_value=None)
            # Schema-level edge (always)
            schema_edge = _make_edge(
                menu,
                col,
                schema_res,
                sourceRecord=None,
                targetRecord=None,
                targetName=None,
            )
            schema_edge["scope"] = "SCHEMA"
            relationships.append(schema_edge)

            if not table:
                continue

            ds_col_name = (
                menu.columns[col.datasourceRaw].name
                if _is_dynamic_capable(catalog, menu, col)
                else None
            )
            recs = table["records"][: max(0, max_records_per_table)]
            if len(table["records"]) > max_records_per_table:
                diagnostics.append(
                    {
                        "kind": "RECORD_EXPANSION_CAPPED",
                        "menu": menu.mnuname,
                        "column": col.name,
                        "recordCount": table["recordCount"],
                        "cappedAt": max_records_per_table,
                    }
                )

            for rec in recs:
                cell = str(rec.get(col.name, "")).strip()
                if cell.upper() in {"INVALID", "N/A", "NONE", ""} and not ds_col_name:
                    continue

                ds_value: int | None = None
                if ds_col_name:
                    raw_ds = str(rec.get(ds_col_name, "")).strip()
                    mapped = _menu_name_to_index(catalog, raw_ds)
                    # SOURCE_PROVEN: value > 0 uses dynamic menu; else fallback (0)
                    ds_value = mapped if mapped is not None else 0

                res = find_data_source(
                    catalog,
                    menu,
                    col.index,
                    datasource_record_value=ds_value,
                )
                target_menu = res.get("targetMenu")
                target_record = None
                target_name = cell or None
                if target_menu and cell and cell.upper() not in {"INVALID", "", "N/A", "NONE", "N"}:
                    target_record = name_index.get(target_menu, {}).get(cell)
                    if target_record is None:
                        diagnostics.append(
                            {
                                "kind": "UNRESOLVED_TARGET_RECORD",
                                "sourceMenu": menu.mnuname,
                                "sourceColumn": col.name,
                                "sourceRecord": rec["_recordIndex"],
                                "targetMenu": target_menu,
                                "targetName": cell,
                            }
                        )
                elif res.get("resolutionMode") == "UNRESOLVED":
                    diagnostics.append(
                        {
                            "kind": "UNRESOLVED_TARGET_MENU",
                            "sourceMenu": menu.mnuname,
                            "sourceColumn": col.name,
                            "sourceRecord": rec["_recordIndex"],
                            "reason": res.get("reason"),
                        }
                    )

                edge = _make_edge(
                    menu,
                    col,
                    res,
                    sourceRecord=rec["_recordIndex"],
                    targetRecord=target_record,
                    targetName=target_name,
                )
                edge["scope"] = "RECORD"
                relationships.append(edge)

    reverse: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in relationships:
        if e.get("scope") == "SCHEMA":
            continue
        key = e.get("targetMenu") or "UNRESOLVED"
        if e.get("targetRecord") is not None:
            key = f"{key}#{e['targetRecord']}"
        reverse[key].append(
            {
                "sourceMenu": e["sourceMenu"],
                "sourceColumn": e["sourceColumn"],
                "sourceRecord": e.get("sourceRecord"),
                "resolutionMode": e["resolutionMode"],
                "targetName": e.get("targetName"),
            }
        )

    stats = {
        "menus": len(catalog.menus),
        "columns": sum(len(m.columns) for m in catalog.menus),
        "tablesLoaded": len(tables),
        "recordsLoaded": sum(t.get("recordCount", 0) for t in tables.values()),
        "relationships": len(relationships),
        "schemaRelationships": sum(1 for e in relationships if e.get("scope") == "SCHEMA"),
        "recordRelationships": sum(1 for e in relationships if e.get("scope") == "RECORD"),
        "static": sum(1 for e in relationships if e["resolutionMode"] == "STATIC"),
        "dynamic": sum(1 for e in relationships if e["resolutionMode"] == "DYNAMIC"),
        "unresolved": sum(1 for e in relationships if e["resolutionMode"] == "UNRESOLVED"),
        "unknownDatatypeValues": sorted(unknown_dtypes),
        "diagnosticCount": len(diagnostics),
        "maxRecordsPerTable": max_records_per_table,
    }
    return {
        "kind": "MnuRuntimeRelationshipGraph",
        "version": 1,
        "relationships": relationships,
        "reverseRelationships": {k: v for k, v in sorted(reverse.items())},
        "diagnostics": diagnostics,
        "statistics": stats,
        "semanticRules": SEMANTIC_RULES,
    }


def _menu_name_to_index(catalog: RuntimeCatalog, raw: str) -> int | None:
    if not raw or raw.upper() in {"INVALID", "N/A", "NONE", "N", "0"}:
        return 0 if raw == "0" else None
    # numeric menu index?
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    m = catalog.by_name.get(raw)
    return m.index if m else None


def _make_edge(
    menu: RuntimeMenu,
    col: RuntimeColumn,
    res: dict[str, Any],
    *,
    sourceRecord: int | None,
    targetRecord: int | None,
    targetName: str | None,
) -> dict[str, Any]:
    return {
        "sourceMenu": menu.mnuname,
        "sourceMenuIndex": menu.index,
        "sourceColumn": col.name,
        "sourceColumnIndex": col.index,
        "sourceRecord": sourceRecord,
        "datatypeRaw": col.datatypeRaw,
        "datatypeName": col.datatypeName,
        "dataselectRaw": col.dataselectRaw,
        "datasourceRaw": col.datasourceRaw,
        "resolutionMode": res.get("resolutionMode"),
        "targetMenu": res.get("targetMenu"),
        "targetMenuIndex": res.get("targetMenuIndex"),
        "targetRecord": targetRecord,
        "targetName": targetName,
        "evidence": res.get("evidence") or [],
        "reason": res.get("reason"),
    }


# ---------------------------------------------------------------------------
# Artifact builder / CLI
# ---------------------------------------------------------------------------


def build_runtime_artifact(
    *,
    fortna_mnu: Path,
    project_mnu: Path | None,
    run_dir: Path | None,
    ac_name: str,
    out_path: Path,
    max_records_per_table: int = 50,
) -> dict[str, Any]:
    fortna = parse_mnu_file(fortna_mnu, origin="FORTNA")
    schemas = [fortna]
    project = None
    if project_mnu and Path(project_mnu).is_file():
        project = parse_mnu_file(project_mnu, origin="PROJECT")
        schemas.append(project)

    catalog = build_runtime_catalog(*schemas)
    table_pack = {"tables": {}, "diagnostics": [], "acName": ac_name}
    if run_dir and Path(run_dir).is_dir():
        table_pack = load_run_tables(catalog, run_dir, ac_name=ac_name)

    graph = build_relationship_graph(
        catalog,
        table_pack["tables"],
        max_records_per_table=max_records_per_table,
    )

    menus_out = []
    for m in catalog.menus:
        sel_cols = [
            c
            for c in m.columns
            if c.datatypeRaw in (SELECTION, SELECTION_UNIQUE, MENU_COLUMN_ROW)
            or c.datasourceRaw
        ]
        menus_out.append(
            {
                "index": m.index,
                "mnuname": m.mnuname,
                "origin": m.origin,
                "sourceFile": m.sourceFile,
                "mnuparm": {
                    k: m.mnuparm.get(k)
                    for k in (
                        "mnuname",
                        "type",
                        "arrays",
                        "pointermemb",
                        "mycurr",
                        "datarec",
                        "vertp",
                        "mymaxcurr",
                        "broadcast",
                        "menudispmax",
                        "filtered",
                        "disptype",
                        "nobox",
                        "flags",
                    )
                    if k in m.mnuparm
                },
                "columnCount": len(m.columns),
                "selectionColumns": [
                    {
                        "index": c.index,
                        "name": c.name,
                        "datatypeRaw": c.datatypeRaw,
                        "datatypeName": c.datatypeName,
                        "datalen": c.datalen,
                        "datalow": c.datalow,
                        "datahigh": c.datahigh,
                        "dataselectRaw": c.dataselectRaw,
                        "dataselectMenuIndex": c.dataselectMenuIndex,
                        "datasourceRaw": c.datasourceRaw,
                        "line": c.line,
                    }
                    for c in sel_cols
                ],
            }
        )

    tables_out = [
        {
            "menu": t["menu"],
            "menuIndex": t["menuIndex"],
            "origin": t["origin"],
            "physicalFile": t["physicalFile"],
            "chosenKind": t["chosenKind"],
            "columns": t["columns"],
            "recordCount": t["recordCount"],
        }
        for t in table_pack["tables"].values()
    ]

    # Keep artifact diffable/usable: schema edges + capped record edges.
    # Reverse index only for keys with ≤ 50 inbound edges (full reverse regenerable).
    reverse_compact = {
        k: v
        for k, v in graph["reverseRelationships"].items()
        if len(v) <= 50
    }
    artifact = {
        "kind": "MnuRuntimeArchaeology",
        "version": 1,
        "menus": menus_out,
        "tables": tables_out,
        "relationships": graph["relationships"],
        "reverseRelationships": reverse_compact,
        "reverseRelationshipsOmittedKeys": sum(
            1 for v in graph["reverseRelationships"].values() if len(v) > 50
        ),
        "diagnostics": (table_pack["diagnostics"] + graph["diagnostics"])[:5000],
        "statistics": {
            **graph["statistics"],
            "sourceProvenRules": sum(1 for r in SEMANTIC_RULES if r["status"] == "SOURCE_PROVEN"),
            "dataObservedRules": sum(1 for r in SEMANTIC_RULES if r["status"] == "DATA_OBSERVED"),
            "unknownRules": sum(1 for r in SEMANTIC_RULES if r["status"] == "UNKNOWN"),
        },
        "semanticRules": SEMANTIC_RULES,
        "fieldHeaderToRuntime": FIELD_HEADER_TO_RUNTIME,
        "menuHeaderToMnuparm": MENU_HEADER_TO_MNUPARM,
        "datatypeNames": {str(k): v for k, v in sorted(DATATYPE_NAMES.items())},
        "combinedOwnership": {
            k: combine_schemas(schemas)[k]
            for k in (
                "kind",
                "version",
                "origins",
                "definitionCount",
                "uniqueDefinitionNames",
                "collisionCount",
                "precedencePolicy",
                "collisions",
            )
        },
        "notes": [
            "Selection relationships are schema/data references, not physical topology.",
            "rom.* ASC fallbacks exist in amenu.c but this artifact uses asc.<AC>/asc per task rule.",
            "Record expansion is capped (maxRecordsPerTable) to keep artifacts reviewable.",
        ],
    }

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Relationships can be huge with full ASC — write compact stats-heavy default
    # Keep relationships but cap reverse map already sorted.
    out_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return artifact


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fortna .mnu runtime archaeology decoder")
    ap.add_argument(
        "--fortna-mnu",
        default=str(ROOT / "workspace/_plc2_run_peek/RUN/FORTNA/fortna.mnu"),
    )
    ap.add_argument(
        "--project-mnu",
        default=str(ROOT / "workspace/_plc2_run_peek/RUN/PROJECT/project.mnu"),
    )
    ap.add_argument(
        "--run-dir",
        default=str(ROOT / "workspace/_plc2_run_peek/RUN"),
    )
    ap.add_argument("--ac-name", default="ORNCCP2")
    ap.add_argument(
        "--out",
        default=str(ROOT / "artifacts/mnu-runtime-relationships.json"),
    )
    ap.add_argument("--skip-asc", action="store_true")
    ap.add_argument("--max-records", type=int, default=50)
    args = ap.parse_args(argv)

    run_dir = None if args.skip_asc else Path(args.run_dir)
    art = build_runtime_artifact(
        fortna_mnu=Path(args.fortna_mnu),
        project_mnu=Path(args.project_mnu) if args.project_mnu else None,
        run_dir=run_dir if run_dir and run_dir.is_dir() else None,
        ac_name=args.ac_name,
        out_path=Path(args.out),
        max_records_per_table=args.max_records,
    )
    st = art["statistics"]
    print(
        f"menus={st['menus']} columns={st['columns']} tables={st['tablesLoaded']} "
        f"records={st['recordsLoaded']} rels={st['relationships']} "
        f"static={st['static']} dynamic={st['dynamic']} unresolved={st['unresolved']}"
    )
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
