#!/usr/bin/env python3
"""CP2 — Generic FortnaPlus RUN / ASC data loader (standalone archaeology).

Sits between the frozen CP1 .mnu schema/runtime decoder and future CP3
reference resolution.

  .mnu → schema (CP1) → CP2 typed Fortna records

Does NOT:
  - interpret conveyors/merges/estops operationally
  - resolve selection targets (CP3)
  - integrate into production Site Forge

CP1 baseline (frozen): bedcb7a — do not rewrite CP1 semantics here.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from fortna_mnu_runtime import (
    DATATYPE_NAMES,
    MENU_TITLE_LINE,
    RuntimeCatalog,
    RuntimeColumn,
    RuntimeMenu,
    build_runtime_catalog,
    datatype_name,
)
from fortna_mnu_schema import parse_mnu_file

ROOT = Path(__file__).resolve().parents[2]

# SOURCE_PROVEN datatype ints from fmenu.h (via CP1 catalog)
STRING = 0
INTEGER = 1
LONG_INTEGER = 2
DOUBLE = 3
DOUBLE_AS_TIME_ELAPSED = 4
UNSIGNED_CHAR = 5
UNSIGNED_CHAR_AS_BOOLEAN = 6
LONG_INT_AS_TIME = 7
FORTNA_ONLY_INT = 8
FORTNA_ONLY_INT2 = 9
HEXADECIMAL_INT = 10
BOOLEAN_INTEGER = 11
OCTINT = 12
FEET_INCHES = 13
TIMESTAMP = 14
BLOB = 15
SELECTION = 20
SELECTION_UNIQUE = 21
MENU_COLUMN_ROW = 25
BOOLEAN_AS_BUTTON = 36
INTEGER_AS_BITSET = 37
INTEGER_AS_GAUGE = 35
INTEGER_AS_ROLESET = 38
DATABASE_LINE = 260

# ---------------------------------------------------------------------------
# File selection
# ---------------------------------------------------------------------------

# SOURCE_PROVEN FortnaPlus open order — amenu.c get_one_select / get_one_amenu:
FORTNAPLUS_FILE_PRECEDENCE = (
    "{table}.rom.{machine}",
    "{table}.rom",
    "{table}.asc.{machine}",
    "{table}.asc",
)

# CP2 currently decodes ASC text tables only. ROM is detected but not decoded.
CP2_SUPPORTED_SUFFIXES = (".asc",)


@dataclass
class PhysicalFileSelection:
    table: str
    acName: str
    searchDirs: list[str]
    fortnaPlusPrecedence: list[str]
    cp2SupportedFormats: list[str]
    candidates: list[dict[str, Any]]
    selectedPath: str | None
    selectedKind: str  # MACHINE_SPECIFIC_ASC | GENERIC_ASC | UNSUPPORTED_ROM | MISSING
    selectedReason: str
    provenance: str  # SOURCE_PROVEN / DATA_OBSERVED


def resolve_physical_table_file(
    table: str,
    *,
    directories: Iterable[Path],
    ac_name: str,
) -> PhysicalFileSelection:
    """Resolve which physical file FortnaPlus would prefer vs what CP2 can load.

    SOURCE_PROVEN precedence (amenu.c):
      Table.rom.<MACHINE> → Table.rom → Table.asc.<MACHINE> → Table.asc

    CP2 supported decode formats: ASC only.
    If a higher-precedence .rom exists, CP2 reports UNSUPPORTED_ROM and does
    NOT silently fall through to ASC while claiming FortnaPlus selected ASC.
    """
    table = str(table or "").strip()
    ac = str(ac_name or "").strip()
    dirs = [Path(d) for d in directories if Path(d).is_dir()]
    patterns = [
        (f"{table}.rom.{ac}", "ROM_MACHINE_SPECIFIC", True),
        (f"{table}.rom", "ROM_GENERIC", True),
        (f"{table}.asc.{ac}", "MACHINE_SPECIFIC_ASC", False),
        (f"{table}.asc", "GENERIC_ASC", False),
    ]
    candidates: list[dict[str, Any]] = []
    first_existing: dict[str, Any] | None = None
    first_supported: dict[str, Any] | None = None

    for directory in dirs:
        for fname, kind, is_rom in patterns:
            path = directory / fname
            exists = path.is_file()
            rec = {
                "path": str(path),
                "kind": kind,
                "exists": exists,
                "isRom": is_rom,
                "cp2Decodable": (not is_rom) and exists,
                "directory": str(directory),
            }
            candidates.append(rec)
            if exists and first_existing is None:
                first_existing = rec
            if exists and (not is_rom) and first_supported is None:
                # Only accept ASC if no higher-precedence existing ROM in same
                # FortnaPlus order across already-scanned candidates in this dir
                # — handled below globally.
                pass

    # Re-evaluate FortnaPlus winner across all candidates in precedence order
    # as listed (dirs outer, patterns inner — matches searching FORTNA then PROJECT).
    fortna_winner: dict[str, Any] | None = None
    for directory in dirs:
        for fname, kind, is_rom in patterns:
            path = directory / fname
            if path.is_file():
                fortna_winner = {
                    "path": str(path),
                    "kind": kind,
                    "exists": True,
                    "isRom": is_rom,
                    "cp2Decodable": not is_rom,
                    "directory": str(directory),
                }
                break
        if fortna_winner:
            break

    if fortna_winner is None:
        return PhysicalFileSelection(
            table=table,
            acName=ac,
            searchDirs=[str(d) for d in dirs],
            fortnaPlusPrecedence=list(FORTNAPLUS_FILE_PRECEDENCE),
            cp2SupportedFormats=list(CP2_SUPPORTED_SUFFIXES),
            candidates=candidates,
            selectedPath=None,
            selectedKind="MISSING",
            selectedReason="no_rom_or_asc_found_in_search_dirs",
            provenance="SOURCE_PROVEN",
        )

    if fortna_winner["isRom"]:
        return PhysicalFileSelection(
            table=table,
            acName=ac,
            searchDirs=[str(d) for d in dirs],
            fortnaPlusPrecedence=list(FORTNAPLUS_FILE_PRECEDENCE),
            cp2SupportedFormats=list(CP2_SUPPORTED_SUFFIXES),
            candidates=candidates,
            selectedPath=fortna_winner["path"],
            selectedKind="UNSUPPORTED_ROM",
            selectedReason=(
                "FortnaPlus would select this .rom first (amenu.c); "
                "CP2 does not yet decode .rom — not silently falling back to ASC"
            ),
            provenance="SOURCE_PROVEN",
        )

    kind = fortna_winner["kind"]
    reason = (
        "machine-specific ASC selected over generic ASC"
        if kind == "MACHINE_SPECIFIC_ASC"
        else "generic ASC selected (no higher-precedence rom/asc.machine present)"
    )
    return PhysicalFileSelection(
        table=table,
        acName=ac,
        searchDirs=[str(d) for d in dirs],
        fortnaPlusPrecedence=list(FORTNAPLUS_FILE_PRECEDENCE),
        cp2SupportedFormats=list(CP2_SUPPORTED_SUFFIXES),
        candidates=candidates,
        selectedPath=fortna_winner["path"],
        selectedKind=kind,
        selectedReason=reason,
        provenance="SOURCE_PROVEN",
    )


# ---------------------------------------------------------------------------
# ASC row splitting (DATA_OBSERVED from amenu.c + PLC2 RUN files)
# ---------------------------------------------------------------------------


def split_asc_row(line: str) -> list[str]:
    """Split one ASC record line into raw field strings.

    SOURCE_PROVEN separators in amenu.c:
      - quoted form: "value", ...
      - tilde form: value~

    DATA_OBSERVED: PLC2 ASC rows commonly end with a trailing `~`, which produces
    one empty cell via str.split. That trailing empty is not an extra field.
    """
    if "~" in line:
        cells = line.split("~")
        if len(cells) >= 2 and cells[-1] == "":
            cells = cells[:-1]
        return cells
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


def read_asc_raw(path: Path) -> dict[str, Any]:
    """Read ASC file preserving every data line (no silent truncate)."""
    path = Path(path)
    raw_bytes = path.read_bytes()
    text = raw_bytes.decode("latin-1", errors="replace")
    # Keep blank lines for diagnostics but records are non-empty lines after header
    all_lines = text.splitlines()
    if not all_lines:
        return {
            "path": str(path),
            "headerRaw": [],
            "headerNames": [],
            "dataLines": [],
            "encoding": "latin-1",
        }
    header_cells = split_asc_row(all_lines[0])
    header_names = [c.strip().strip('"') for c in header_cells]
    data_lines: list[dict[str, Any]] = []
    for i, line in enumerate(all_lines[1:], start=1):
        if line.strip() == "":
            continue
        cells = split_asc_row(line)
        data_lines.append(
            {
                "recordIndex": i,  # 1-based data row number in file order among non-empty
                "lineNumber": i + 1,  # file line number (header is 1)
                "rawLine": line,
                "rawCells": cells,
            }
        )
    # Re-number recordIndex strictly among retained data rows
    for i, rec in enumerate(data_lines, start=1):
        rec["recordIndex"] = i
    return {
        "path": str(path),
        "headerRaw": header_cells,
        "headerNames": header_names,
        "dataLines": data_lines,
        "encoding": "latin-1",
        "byteLength": len(raw_bytes),
    }


# ---------------------------------------------------------------------------
# Typed values
# ---------------------------------------------------------------------------


@dataclass
class FortnaValue:
    menuName: str
    recordIndex: int
    columnIndex: int
    columnName: str
    datatypeRaw: int
    datatypeName: str | None
    rawText: str
    typedValue: Any
    typedKind: str  # string|int|float|bool|selection_token|column_token|null|unsupported
    conversionStatus: str  # OK | EMPTY | UNSUPPORTED | FAILED
    conversionEvidence: str
    physicalFile: str
    schemaOrigin: str
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class FortnaRecord:
    menuName: str
    recordIndex: int
    values: list[FortnaValue]
    rawLine: str
    rawCellCount: int
    schemaColumnCount: int
    shapeStatus: str  # OK | SHORT | LONG | MISALIGNED
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    physicalFile: str = ""
    schemaOrigin: str = ""


@dataclass
class FortnaTable:
    menuName: str
    menuIndex: int
    schemaOrigin: str
    schemaSourceFile: str
    columns: list[dict[str, Any]]
    physicalSelection: dict[str, Any]
    records: list[FortnaRecord]
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


def convert_value(
    raw: str,
    *,
    datatype_raw: int,
    column_name: str,
) -> tuple[Any, str, str, str]:
    """Return (typedValue, typedKind, conversionStatus, evidence).

    Conversion rules SOURCE_PROVEN from amenu.c ASC load switch (approx lines 1078–1177).
    Selection-like types preserve raw text for CP3 (not resolved here).
    """
    text = raw if raw is not None else ""
    stripped = text.strip()
    dt = int(datatype_raw)
    name = datatype_name(dt) or f"UNKNOWN_{dt}"

    # Title / database sentinel columns are not ASC payload fields
    if dt in (MENU_TITLE_LINE, DATABASE_LINE):
        return None, "null", "OK", f"SOURCE_PROVEN:skip_non_payload_datatype:{name}"

    if dt in (STRING, TIMESTAMP, BLOB):
        # TIMESTAMP stored as string in ASC load (amenu.c)
        return text, "string", "OK", f"SOURCE_PROVEN:amenu_strncpy_string:{name}"

    if dt in (SELECTION, SELECTION_UNIQUE):
        return stripped, "selection_token", "OK", "SOURCE_PROVEN:preserve_raw_pending_CP3"

    if dt == MENU_COLUMN_ROW:
        return stripped, "column_token", "OK", "SOURCE_PROVEN:preserve_raw_pending_CP3"

    if dt in (BOOLEAN_INTEGER, BOOLEAN_AS_BUTTON):
        if stripped in {"Y", "y"}:
            return True, "bool", "OK", "SOURCE_PROVEN:amenu_Y_to_1"
        if stripped == "":
            return False, "bool", "EMPTY", "SOURCE_PROVEN:amenu_non_Y_to_0"
        return False, "bool", "OK", "SOURCE_PROVEN:amenu_non_Y_to_0"

    if stripped == "":
        return None, "null", "EMPTY", f"empty_raw:{name}"

    try:
        if dt == FORTNA_ONLY_INT:
            return int(stripped, 2), "int", "OK", "SOURCE_PROVEN:amenu_strtol_base2"
        if dt == INTEGER_AS_BITSET:
            return int(stripped, 2), "int", "OK", "SOURCE_PROVEN:amenu_strtoul_base2"
        if dt in (INTEGER, FORTNA_ONLY_INT2, INTEGER_AS_GAUGE, INTEGER_AS_ROLESET):
            return int(stripped, 10), "int", "OK", "SOURCE_PROVEN:amenu_sscanf_%d"
        if dt == LONG_INTEGER:
            return int(stripped, 10), "int", "OK", "SOURCE_PROVEN:amenu_sscanf_%ld"
        if dt == LONG_INT_AS_TIME:
            return int(stripped, 10), "int", "OK", "SOURCE_PROVEN:amenu_sscanf_time_as_%d"
        if dt == HEXADECIMAL_INT:
            return int(stripped, 16), "int", "OK", "SOURCE_PROVEN:amenu_sscanf_%x"
        if dt == OCTINT:
            return int(stripped, 8), "int", "OK", "SOURCE_PROVEN:amenu_sscanf_%o"
        if dt in (DOUBLE, DOUBLE_AS_TIME_ELAPSED, FEET_INCHES):
            # ASC path uses sscanf %lf even for FEET_INCHES (amenu.c) — not calc_feetinch
            return float(stripped), "float", "OK", "SOURCE_PROVEN:amenu_sscanf_%lf"
        if dt in (UNSIGNED_CHAR, UNSIGNED_CHAR_AS_BOOLEAN):
            return int(stripped, 10), "int", "OK", "SOURCE_PROVEN:amenu_sscanf_uchar_%d"
    except ValueError:
        return None, "null", "FAILED", f"SOURCE_PROVEN_rule_but_parse_failed:{name}"

    return None, "unsupported", "UNSUPPORTED", f"no_SOURCE_PROVEN_ASC_conversion:{name}"


# ---------------------------------------------------------------------------
# Table load
# ---------------------------------------------------------------------------


def _payload_columns(menu: RuntimeMenu) -> list[RuntimeColumn]:
    """Columns expected to appear in ASC (exclude title/database sentinels)."""
    return [c for c in menu.columns if c.datatypeRaw not in (MENU_TITLE_LINE, DATABASE_LINE)]


def load_fortna_table(
    menu: RuntimeMenu,
    *,
    directories: Iterable[Path],
    ac_name: str,
) -> FortnaTable:
    selection = resolve_physical_table_file(menu.mnuname, directories=directories, ac_name=ac_name)
    sel_dict = asdict(selection)
    diagnostics: list[dict[str, Any]] = []

    col_meta = [
        {
            "index": c.index,
            "name": c.name,
            "datatypeRaw": c.datatypeRaw,
            "datatypeName": c.datatypeName,
            "datalen": c.datalen,
            "isPayload": c.datatypeRaw not in (MENU_TITLE_LINE, DATABASE_LINE),
        }
        for c in menu.columns
    ]

    if selection.selectedKind == "MISSING":
        diagnostics.append(
            {
                "kind": "EXPECTED_ASC_MISSING",
                "menu": menu.mnuname,
                "detail": selection.selectedReason,
            }
        )
        return FortnaTable(
            menuName=menu.mnuname,
            menuIndex=menu.index,
            schemaOrigin=menu.origin,
            schemaSourceFile=menu.sourceFile,
            columns=col_meta,
            physicalSelection=sel_dict,
            records=[],
            diagnostics=diagnostics,
            stats={"recordCount": 0, "valueCount": 0, "loaded": False},
        )

    if selection.selectedKind == "UNSUPPORTED_ROM":
        diagnostics.append(
            {
                "kind": "UNSUPPORTED_ROM",
                "menu": menu.mnuname,
                "path": selection.selectedPath,
                "detail": selection.selectedReason,
            }
        )
        return FortnaTable(
            menuName=menu.mnuname,
            menuIndex=menu.index,
            schemaOrigin=menu.origin,
            schemaSourceFile=menu.sourceFile,
            columns=col_meta,
            physicalSelection=sel_dict,
            records=[],
            diagnostics=diagnostics,
            stats={"recordCount": 0, "valueCount": 0, "loaded": False},
        )

    assert selection.selectedPath
    raw = read_asc_raw(Path(selection.selectedPath))
    header_names = raw["headerNames"]
    payload_cols = _payload_columns(menu)

    # Map ASC header → schema column by name (DATA_OBSERVED: ASC omits title line)
    name_to_schema = {c.name: c for c in menu.columns}
    header_schema_cols: list[RuntimeColumn | None] = []
    for h in header_names:
        header_schema_cols.append(name_to_schema.get(h))

    # Header vs payload schema diagnostics
    payload_names = [c.name for c in payload_cols]
    missing_in_asc = [n for n in payload_names if n not in header_names]
    extra_in_asc = [h for h in header_names if h not in name_to_schema]
    if missing_in_asc:
        diagnostics.append(
            {
                "kind": "SCHEMA_COLUMNS_MISSING_FROM_ASC_HEADER",
                "menu": menu.mnuname,
                "columns": missing_in_asc[:40],
                "count": len(missing_in_asc),
            }
        )
    if extra_in_asc:
        diagnostics.append(
            {
                "kind": "ASC_HEADER_COLUMNS_NOT_IN_SCHEMA",
                "menu": menu.mnuname,
                "columns": extra_in_asc[:40],
                "count": len(extra_in_asc),
            }
        )

    records: list[FortnaRecord] = []
    for line_rec in raw["dataLines"]:
        cells: list[str] = list(line_rec["rawCells"])
        raw_cell_count = len(cells)
        expected = len(header_names)
        shape = "OK"
        rec_diags: list[dict[str, Any]] = []

        if raw_cell_count < expected:
            shape = "SHORT"
            rec_diags.append(
                {
                    "kind": "FIELD_COUNT_SHORT",
                    "rawCellCount": raw_cell_count,
                    "headerCount": expected,
                }
            )
            # Do not truncate — pad with empty for alignment while preserving rawCells
            cells = cells + [""] * (expected - raw_cell_count)
        elif raw_cell_count > expected:
            shape = "LONG"
            rec_diags.append(
                {
                    "kind": "FIELD_COUNT_LONG",
                    "rawCellCount": raw_cell_count,
                    "headerCount": expected,
                    "extraCells": cells[expected:],
                }
            )
            # Preserve extras in diagnostics; values use header-aligned prefix only
            cells_for_values = cells[:expected]
        else:
            cells_for_values = cells

        if shape == "SHORT":
            cells_for_values = cells

        values: list[FortnaValue] = []
        # Emit values for each schema payload column (by name lookup into ASC cells)
        header_index = {header_names[i]: i for i in range(len(header_names))}
        for col in menu.columns:
            if col.datatypeRaw in (MENU_TITLE_LINE, DATABASE_LINE):
                continue
            if col.name in header_index:
                raw_text = cells_for_values[header_index[col.name]]
                in_file = True
            else:
                raw_text = ""
                in_file = False
                rec_diags.append(
                    {
                        "kind": "COLUMN_ABSENT_FROM_ASC_ROW",
                        "column": col.name,
                        "columnIndex": col.index,
                    }
                )
            typed, kind, status, evid = convert_value(
                raw_text, datatype_raw=col.datatypeRaw, column_name=col.name
            )
            if status == "FAILED":
                rec_diags.append(
                    {
                        "kind": "CONVERSION_FAILED",
                        "column": col.name,
                        "datatypeRaw": col.datatypeRaw,
                        "rawText": raw_text,
                    }
                )
            if status == "UNSUPPORTED":
                rec_diags.append(
                    {
                        "kind": "UNSUPPORTED_DATATYPE_CONVERSION",
                        "column": col.name,
                        "datatypeRaw": col.datatypeRaw,
                        "datatypeName": col.datatypeName,
                        "rawText": raw_text,
                    }
                )
            values.append(
                FortnaValue(
                    menuName=menu.mnuname,
                    recordIndex=line_rec["recordIndex"],
                    columnIndex=col.index,
                    columnName=col.name,
                    datatypeRaw=col.datatypeRaw,
                    datatypeName=col.datatypeName,
                    rawText=raw_text,
                    typedValue=typed,
                    typedKind=kind,
                    conversionStatus=status,
                    conversionEvidence=evid,
                    physicalFile=selection.selectedPath or "",
                    schemaOrigin=menu.origin,
                    provenance={
                        "inPhysicalFile": in_file,
                        "schemaLine": col.line,
                        "fileLineNumber": line_rec["lineNumber"],
                    },
                )
            )

        records.append(
            FortnaRecord(
                menuName=menu.mnuname,
                recordIndex=line_rec["recordIndex"],
                values=values,
                rawLine=line_rec["rawLine"],
                rawCellCount=raw_cell_count,
                schemaColumnCount=len(payload_cols),
                shapeStatus=shape,
                diagnostics=rec_diags,
                physicalFile=selection.selectedPath or "",
                schemaOrigin=menu.origin,
            )
        )

    stats = {
        "recordCount": len(records),
        "valueCount": sum(len(r.values) for r in records),
        "shortRecords": sum(1 for r in records if r.shapeStatus == "SHORT"),
        "longRecords": sum(1 for r in records if r.shapeStatus == "LONG"),
        "conversionFailures": sum(
            1 for r in records for v in r.values if v.conversionStatus == "FAILED"
        ),
        "unsupportedConversions": sum(
            1 for r in records for v in r.values if v.conversionStatus == "UNSUPPORTED"
        ),
        "loaded": True,
        "headerColumnCount": len(header_names),
        "schemaPayloadColumnCount": len(payload_cols),
    }
    return FortnaTable(
        menuName=menu.mnuname,
        menuIndex=menu.index,
        schemaOrigin=menu.origin,
        schemaSourceFile=menu.sourceFile,
        columns=col_meta,
        physicalSelection=sel_dict,
        records=records,
        diagnostics=diagnostics,
        stats=stats,
    )


def classify_schema_only_menu(menu: RuntimeMenu) -> str | None:
    """Heuristic: UI-only menus often have TYPE that is not a persisted data table.

    We do NOT invent FortnaPlus rules here beyond DATA_OBSERVED: many menus have
    no ASC because they are UI/popups. CP2 reports SCHEMA_NO_PHYSICAL_TABLE when
    no file exists; caller may attach menu type for review.
    """
    return None


# ---------------------------------------------------------------------------
# RUN load
# ---------------------------------------------------------------------------


def load_run(
    *,
    fortna_mnu: Path,
    project_mnu: Path | None,
    run_dir: Path,
    ac_name: str,
    only_menus: Iterable[str] | None = None,
) -> dict[str, Any]:
    fortna = parse_mnu_file(fortna_mnu, origin="FORTNA")
    schemas = [fortna]
    if project_mnu and Path(project_mnu).is_file():
        schemas.append(parse_mnu_file(project_mnu, origin="PROJECT"))
    catalog = build_runtime_catalog(*schemas)

    run_dir = Path(run_dir)
    directories = [d for d in (run_dir / "FORTNA", run_dir / "PROJECT", run_dir) if d.is_dir()]

    only = set(only_menus) if only_menus else None
    tables: list[FortnaTable] = []
    global_diags: list[dict[str, Any]] = []

    for menu in catalog.menus:
        if only is not None and menu.mnuname not in only:
            continue
        table = load_fortna_table(menu, directories=directories, ac_name=ac_name)
        tables.append(table)
        if table.physicalSelection.get("selectedKind") == "MISSING":
            global_diags.append(
                {
                    "kind": "SCHEMA_DEFINITION_NO_PHYSICAL_TABLE",
                    "menu": menu.mnuname,
                    "menuType": menu.type,
                    "origin": menu.origin,
                    "note": (
                        "No .rom/.asc found. Not automatically a broken RUN — "
                        "many UI menus have no persisted ASC."
                    ),
                }
            )

    summary = _summarize(catalog, tables, global_diags)
    return {
        "kind": "FortnaRunTypedRecords",
        "version": 1,
        "acName": ac_name,
        "runDir": str(run_dir),
        "fortnaMnu": str(fortna_mnu),
        "projectMnu": str(project_mnu) if project_mnu else None,
        "filePrecedence": {
            "fortnaPlusSourceProven": list(FORTNAPLUS_FILE_PRECEDENCE),
            "cp2SupportedFormats": list(CP2_SUPPORTED_SUFFIXES),
            "evidence": "amenu.c opens rom.machine → rom → asc.machine → asc",
            "provenance": "SOURCE_PROVEN",
        },
        "summary": summary,
        "tables": [_table_to_json(t, compact_values=True) for t in tables],
        "diagnostics": global_diags,
        "semanticNotes": [
            "CP2 loads storage shape only — no engineering interpretation.",
            "Selection tokens preserved raw for CP3.",
            "FEET_INCHES ASC conversion uses sscanf %lf per amenu.c (not calc_feetinch UI parser).",
        ],
    }


def _table_to_json(table: FortnaTable, *, compact_values: bool = True) -> dict[str, Any]:
    records_out = []
    for rec in table.records:
        values_out = []
        for v in rec.values:
            values_out.append(
                {
                    "columnIndex": v.columnIndex,
                    "columnName": v.columnName,
                    "datatypeRaw": v.datatypeRaw,
                    "datatypeName": v.datatypeName,
                    "rawText": v.rawText,
                    "typedValue": v.typedValue,
                    "typedKind": v.typedKind,
                    "conversionStatus": v.conversionStatus,
                    "conversionEvidence": v.conversionEvidence,
                    "provenance": v.provenance,
                }
            )
        records_out.append(
            {
                "recordIndex": rec.recordIndex,
                "rawLine": rec.rawLine if not compact_values else None,
                "rawCellCount": rec.rawCellCount,
                "schemaColumnCount": rec.schemaColumnCount,
                "shapeStatus": rec.shapeStatus,
                "diagnostics": rec.diagnostics,
                "values": values_out,
            }
        )
    return {
        "menuName": table.menuName,
        "menuIndex": table.menuIndex,
        "schemaOrigin": table.schemaOrigin,
        "schemaSourceFile": table.schemaSourceFile,
        "columns": table.columns,
        "physicalSelection": table.physicalSelection,
        "stats": table.stats,
        "diagnostics": table.diagnostics,
        "records": records_out,
    }


def _summarize(
    catalog: RuntimeCatalog,
    tables: list[FortnaTable],
    global_diags: list[dict[str, Any]],
) -> dict[str, Any]:
    loaded = [t for t in tables if t.stats.get("loaded")]
    return {
        "schemaMenus": len(catalog.menus),
        "tablesAttempted": len(tables),
        "tablesLoaded": len(loaded),
        "totalRecords": sum(t.stats.get("recordCount", 0) for t in loaded),
        "totalValues": sum(t.stats.get("valueCount", 0) for t in loaded),
        "machineSpecificSelections": sum(
            1 for t in tables if t.physicalSelection.get("selectedKind") == "MACHINE_SPECIFIC_ASC"
        ),
        "genericFallbacks": sum(
            1 for t in tables if t.physicalSelection.get("selectedKind") == "GENERIC_ASC"
        ),
        "unsupportedRom": sum(
            1 for t in tables if t.physicalSelection.get("selectedKind") == "UNSUPPORTED_ROM"
        ),
        "missingTables": sum(
            1 for t in tables if t.physicalSelection.get("selectedKind") == "MISSING"
        ),
        "malformedShortRecords": sum(t.stats.get("shortRecords", 0) for t in loaded),
        "malformedLongRecords": sum(t.stats.get("longRecords", 0) for t in loaded),
        "conversionFailures": sum(t.stats.get("conversionFailures", 0) for t in loaded),
        "unsupportedDatatypeConversions": sum(
            t.stats.get("unsupportedConversions", 0) for t in loaded
        ),
        "schemaNoPhysicalTableDiagnostics": sum(
            1 for d in global_diags if d.get("kind") == "SCHEMA_DEFINITION_NO_PHYSICAL_TABLE"
        ),
    }


def get_record(table: FortnaTable, record_index: int) -> FortnaRecord | None:
    for rec in table.records:
        if rec.recordIndex == record_index:
            return rec
    return None


def get_value(record: FortnaRecord, column_name: str) -> FortnaValue | None:
    for v in record.values:
        if v.columnName == column_name:
            return v
    return None


# ---------------------------------------------------------------------------
# CLI / artifact
# ---------------------------------------------------------------------------


def build_cp2_artifact(
    *,
    run_dir: Path,
    ac_name: str,
    fortna_mnu: Path,
    project_mnu: Path | None,
    out_path: Path,
    focus_menus: list[str] | None = None,
) -> dict[str, Any]:
    """Build artifact. Full load of all menus can be large — default writes
    summary for all tables + full records for focus menus.
    """
    # Always load full catalog selections for summary; full records for focus set
    focus = focus_menus or [
        "Conveyor",
        "Mtrchain",
        "MergeBoss",
        "MergeInputs",
        "Jamcheck",
        "Jamzones",
        "EStop",
        "Machine",
        "Trigrset",
    ]

    # Pass 1: selection/stats for all menus (records loaded — required for complete counts)
    full = load_run(
        fortna_mnu=fortna_mnu,
        project_mnu=project_mnu,
        run_dir=run_dir,
        ac_name=ac_name,
        only_menus=None,
    )

    # Artifact keeps full records only for modest focus tables; large ones
    # (e.g. Conveyor) keep stats + selection + proof excerpts only.
    LARGE_FOCUS = {"Conveyor"}
    compact_tables = []
    focus_set = set(focus)
    proofs: dict[str, Any] = {}
    for t in full["tables"]:
        name = t["menuName"]
        if name in focus_set and name not in LARGE_FOCUS:
            compact_tables.append(t)
        else:
            compact_tables.append(
                {
                    "menuName": name,
                    "menuIndex": t["menuIndex"],
                    "schemaOrigin": t["schemaOrigin"],
                    "physicalSelection": {
                        k: t["physicalSelection"].get(k)
                        for k in (
                            "selectedPath",
                            "selectedKind",
                            "selectedReason",
                            "provenance",
                        )
                    },
                    "stats": t["stats"],
                    "diagnostics": t["diagnostics"],
                    "recordsOmitted": True,
                    "recordCount": t["stats"].get("recordCount", 0),
                    "focusLargeTable": name in LARGE_FOCUS,
                }
            )

    # Proofs
    by_name = {t["menuName"]: t for t in full["tables"]}
    for name in focus:
        t = by_name.get(name)
        if not t:
            proofs[name] = {"present": False}
            continue
        entry: dict[str, Any] = {
            "present": True,
            "physicalSelection": t["physicalSelection"],
            "stats": t["stats"],
        }
        if name == "Mtrchain":
            rec55 = next((r for r in t["records"] if r["recordIndex"] == 55), None)
            if rec55:
                vals = {v["columnName"]: v for v in rec55["values"]}
                entry["record55"] = {
                    k: {
                        "rawText": vals[k]["rawText"],
                        "typedValue": vals[k]["typedValue"],
                        "datatypeName": vals[k]["datatypeName"],
                    }
                    for k in (
                        "Motor_Name",
                        "Motor_Ndx",
                        "Motor_Chained1",
                        "Motor_Aux",
                        "Enabled",
                        "GoUntil",
                    )
                    if k in vals
                }
            # Motor_Chained4 beyond 25
            chained4 = []
            for r in t["records"]:
                v = next((x for x in r["values"] if x["columnName"] == "Motor_Chained4"), None)
                if not v:
                    continue
                raw = (v["rawText"] or "").strip().upper()
                if raw and raw not in {"INVALID", "N/A", "NONE", ""}:
                    chained4.append({"recordIndex": r["recordIndex"], "rawText": v["rawText"]})
            entry["motorChained4Populated"] = chained4[:10]
            entry["motorChained4PopulatedCount"] = len(chained4)
        proofs[name] = entry

    artifact = {
        "kind": "FortnaRunTypedRecordsArtifact",
        "version": 1,
        "summary": full["summary"],
        "filePrecedence": full["filePrecedence"],
        "focusProofs": proofs,
        "tables": compact_tables,
        "diagnostics": full["diagnostics"][:5000],
        "semanticNotes": full["semanticNotes"],
        "runDir": full["runDir"],
        "acName": full["acName"],
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return artifact


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CP2 generic FortnaPlus RUN loader")
    ap.add_argument("--run-dir", default=str(ROOT / "workspace/_plc2_run_peek/RUN"))
    ap.add_argument(
        "--fortna-mnu",
        default=str(ROOT / "workspace/_plc2_run_peek/RUN/FORTNA/fortna.mnu"),
    )
    ap.add_argument(
        "--project-mnu",
        default=str(ROOT / "workspace/_plc2_run_peek/RUN/PROJECT/project.mnu"),
    )
    ap.add_argument("--ac-name", default="ORNCCP2")
    ap.add_argument(
        "--out",
        default=str(ROOT / "artifacts/fortna-run-typed-records.json"),
    )
    args = ap.parse_args(argv)
    art = build_cp2_artifact(
        run_dir=Path(args.run_dir),
        ac_name=args.ac_name,
        fortna_mnu=Path(args.fortna_mnu),
        project_mnu=Path(args.project_mnu) if args.project_mnu else None,
        out_path=Path(args.out),
    )
    s = art["summary"]
    print(
        "CP2 summary: "
        f"schemaMenus={s['schemaMenus']} loaded={s['tablesLoaded']} "
        f"records={s['totalRecords']} values={s['totalValues']} "
        f"machineSpecific={s['machineSpecificSelections']} "
        f"generic={s['genericFallbacks']} missing={s['missingTables']} "
        f"unsupportedRom={s['unsupportedRom']} "
        f"short={s['malformedShortRecords']} long={s['malformedLongRecords']} "
        f"convFail={s['conversionFailures']} unsupportedDt={s['unsupportedDatatypeConversions']}"
    )
    m314 = (((art.get("focusProofs") or {}).get("Mtrchain") or {}).get("record55"))
    if m314:
        print(
            "M314 proof:",
            {k: v.get("rawText") for k, v in m314.items()},
        )
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
