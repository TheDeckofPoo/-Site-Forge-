#!/usr/bin/env python3
"""Schema IR for FortnaPlus menus (fortna.mnu / project.mnu).

Parses the RUN's canonical ``FORTNA/fortna.mnu`` (and ``PROJECT/project.mnu``
when present) into a compact IR:

  table, field, datatype, SELECTION/SELECTION_UNIQUE, target table, fingerprint

Does NOT glob ``fortna (1).mnu`` copies — only the RUN paths (or an explicit
tools-knowledge canonical path once).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fortna_mnu_runtime import DATATYPE_NAMES, SELECTION, SELECTION_UNIQUE
from fortna_mnu_schema import parse_mnu_file

ROOT = Path(__file__).resolve().parents[2]

# Optional once-path for tools knowledge when a RUN has no fortna.mnu.
KNOWLEDGE_CANONICAL_FORTNA_MNU = ROOT / "workspace" / "_virgin_orindy" / "RUN" / "FORTNA" / "fortna.mnu"


@dataclass
class SchemaFieldIR:
    table: str
    field: str
    datatype: int | None
    datatype_name: str | None
    is_selection: bool
    is_selection_unique: bool
    target_table: str | None
    raw_list: str
    raw_datasource: str
    line: int | None = None
    origin: str = "FORTNA"


@dataclass
class SchemaTableIR:
    table: str
    origin: str
    source_file: str
    fields: list[SchemaFieldIR] = field(default_factory=list)
    selection_edges: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SchemaIR:
    kind: str
    version: int
    sources: list[dict[str, Any]]
    tables: dict[str, SchemaTableIR]
    selection_edges: list[dict[str, Any]]
    fingerprint: str
    notes: list[str] = field(default_factory=list)


def _datatype_int(raw: str) -> int | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return int(text, 10)
    except ValueError:
        return None


def resolve_mnu_paths(run_dir: Path | str | None = None) -> dict[str, Path | None]:
    """Pick canonical fortna.mnu / project.mnu for a RUN (no copy globs)."""
    notes_paths: dict[str, Path | None] = {"fortna": None, "project": None}
    if run_dir is not None:
        run_dir = Path(run_dir)
        fortna = run_dir / "FORTNA" / "fortna.mnu"
        project = run_dir / "PROJECT" / "project.mnu"
        if fortna.is_file():
            notes_paths["fortna"] = fortna
        if project.is_file():
            notes_paths["project"] = project
    if notes_paths["fortna"] is None and KNOWLEDGE_CANONICAL_FORTNA_MNU.is_file():
        notes_paths["fortna"] = KNOWLEDGE_CANONICAL_FORTNA_MNU
    return notes_paths


def _field_ir(table: str, origin: str, f: Any) -> SchemaFieldIR:
    dtype = _datatype_int(f.rawDatatype)
    dtype_name = DATATYPE_NAMES.get(dtype) if dtype is not None else None
    target = (f.listReference or "").strip() or None
    is_sel = dtype == SELECTION
    is_sel_u = dtype == SELECTION_UNIQUE
    return SchemaFieldIR(
        table=table,
        field=f.name,
        datatype=dtype,
        datatype_name=dtype_name,
        is_selection=is_sel,
        is_selection_unique=is_sel_u,
        target_table=target if (is_sel or is_sel_u) else (target if target else None),
        raw_list=f.rawList or "",
        raw_datasource=f.rawDataSource or "",
        line=(f.provenance or {}).get("line"),
        origin=origin,
    )


def _fingerprint(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_schema_ir(run_dir: Path | str | None = None) -> SchemaIR:
    """Parse canonical mnu files into Schema IR."""
    paths = resolve_mnu_paths(run_dir)
    notes: list[str] = []
    sources: list[dict[str, Any]] = []
    tables: dict[str, SchemaTableIR] = {}
    edges: list[dict[str, Any]] = []

    for origin, path in (("FORTNA", paths["fortna"]), ("PROJECT", paths["project"])):
        if path is None:
            notes.append(f"missing_{origin.lower()}_mnu")
            continue
        schema = parse_mnu_file(path, origin=origin)
        sources.append(
            {
                "origin": origin,
                "path": str(path),
                "definitions": schema.stats.get("definitions"),
                "fields": schema.stats.get("fields"),
            }
        )
        for d in schema.definitions:
            tir = tables.get(d.name)
            if tir is None:
                tir = SchemaTableIR(
                    table=d.name,
                    origin=origin,
                    source_file=str(path),
                )
                tables[d.name] = tir
            elif tir.origin != origin:
                notes.append(f"table_collision:{d.name}:{tir.origin}+{origin}")
            for f in d.fields:
                fir = _field_ir(d.name, origin, f)
                tir.fields.append(fir)
                if fir.is_selection or fir.is_selection_unique:
                    edge = {
                        "table": fir.table,
                        "field": fir.field,
                        "datatype": fir.datatype,
                        "datatype_name": fir.datatype_name,
                        "target_table": fir.target_table,
                        "origin": origin,
                        "line": fir.line,
                    }
                    tir.selection_edges.append(edge)
                    edges.append(edge)

    fp_payload = {
        "sources": sources,
        "edges": [
            {
                "table": e["table"],
                "field": e["field"],
                "datatype": e["datatype"],
                "target_table": e["target_table"],
            }
            for e in edges
        ],
        "tables": sorted(tables),
    }
    return SchemaIR(
        kind="FortnaSchemaIR",
        version=1,
        sources=sources,
        tables=tables,
        selection_edges=edges,
        fingerprint=_fingerprint(fp_payload),
        notes=notes,
    )


def schema_ir_to_dict(ir: SchemaIR) -> dict[str, Any]:
    tables_out: dict[str, Any] = {}
    for name, tir in sorted(ir.tables.items()):
        tables_out[name] = {
            "table": tir.table,
            "origin": tir.origin,
            "source_file": tir.source_file,
            "fields": [asdict(f) for f in tir.fields],
            "selection_edges": list(tir.selection_edges),
        }
    return {
        "kind": ir.kind,
        "version": ir.version,
        "sources": ir.sources,
        "tables": tables_out,
        "selection_edges": ir.selection_edges,
        "fingerprint": ir.fingerprint,
        "notes": ir.notes,
    }


def selection_edge_index(ir: SchemaIR) -> dict[str, list[dict[str, Any]]]:
    """Map source table → selection edges (for machine closure walks)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for e in ir.selection_edges:
        out.setdefault(e["table"], []).append(e)
    return out


__all__ = [
    "KNOWLEDGE_CANONICAL_FORTNA_MNU",
    "SchemaFieldIR",
    "SchemaIR",
    "SchemaTableIR",
    "build_schema_ir",
    "resolve_mnu_paths",
    "schema_ir_to_dict",
    "selection_edge_index",
]
