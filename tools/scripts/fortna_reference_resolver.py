#!/usr/bin/env python3
"""CP3 — Generic FortnaPlus reference resolver (standalone archaeology).

Consumes frozen CP1 schema/runtime + CP2 typed RUN records.
Produces a Fortna relationship graph with forward/reverse lookup.

Does NOT:
  - rewrite CP1/CP2 semantics
  - invent engineering topology
  - use string-similarity matching
  - integrate into production Site Forge
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from fortna_mnu_runtime import (
    MENU_COLUMN_ROW,
    MENU_TITLE_LINE,
    SELECTION,
    SELECTION_UNIQUE,
    STRING,
    RuntimeCatalog,
    RuntimeColumn,
    RuntimeMenu,
    build_runtime_catalog,
    find_data_source,
)
from fortna_mnu_schema import parse_mnu_file
from fortna_run_loader import load_run

ROOT = Path(__file__).resolve().parents[2]

# Unresolved taxonomy (GATE C)
DYNAMIC_CAPABLE_SCHEMA = "DYNAMIC_CAPABLE_SCHEMA"
EMPTY_SOURCE_VALUE = "EMPTY_SOURCE_VALUE"
INVALID_DATASOURCE_COLUMN = "INVALID_DATASOURCE_COLUMN"
INVALID_DATASOURCE_VALUE = "INVALID_DATASOURCE_VALUE"
TARGET_MENU_MISSING = "TARGET_MENU_MISSING"
TARGET_COLUMN_MISSING = "TARGET_COLUMN_MISSING"
TARGET_RECORD_MISSING = "TARGET_RECORD_MISSING"
SOURCE_FILE_UNAVAILABLE = "SOURCE_FILE_UNAVAILABLE"
UNSUPPORTED_STORAGE_FORMAT = "UNSUPPORTED_STORAGE_FORMAT"
UNSUPPORTED_REFERENCE_FORM = "UNSUPPORTED_REFERENCE_FORM"
MALFORMED_VALUE = "MALFORMED_VALUE"
NON_REFERENCE_COLUMN = "NON_REFERENCE_COLUMN"  # internal skip, not counted as unresolved edge

EMPTY_TOKENS = {"", "INVALID", "N/A", "NONE", "N", " "}


@dataclass
class ReferenceEdge:
    sourceMenu: str
    sourceRecord: int | None
    sourceColumn: str
    sourceColumnIndex: int
    sourceRawValue: str | None
    sourcePhysicalFile: str | None
    datatypeRaw: int
    datatypeName: str | None
    dataselect: str | None
    datasource: int
    resolutionMode: str  # STATIC | DYNAMIC | FALLBACK_STATIC | UNRESOLVED
    targetMenu: str | None
    targetMenuIndex: int | None
    targetColumn: str | None
    targetColumnIndex: int | None
    targetRecord: int | None
    targetIdentity: str | None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    provenance: str = "SOURCE_PROVEN"
    status: str = "RESOLVED"  # RESOLVED | UNRESOLVED | CAPABILITY
    unresolvedReason: str | None = None
    scope: str = "RECORD"  # RECORD | SCHEMA_CAPABILITY


def _is_empty(raw: str | None) -> bool:
    if raw is None:
        return True
    return str(raw).strip().upper() in EMPTY_TOKENS or str(raw).strip() == ""


def _menu_name_to_index(catalog: RuntimeCatalog, raw: str | None) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.upper() in EMPTY_TOKENS:
        return 0
    if s.isdigit():
        return int(s)
    m = catalog.by_name.get(s)
    return m.index if m else None


def _name_column(menu: RuntimeMenu) -> RuntimeColumn | None:
    """SOURCE_PROVEN: selection identity compared to column index 1 STRING (amenu.c)."""
    if len(menu.columns) > 1 and menu.columns[1].datatypeRaw == STRING:
        return menu.columns[1]
    for c in menu.columns:
        if c.datatypeRaw == STRING and c.name.lower() in {"name", "io_name", "motor_name"}:
            return c
    for c in menu.columns:
        if c.datatypeRaw == STRING:
            return c
    return None


def _build_identity_index(
    catalog: RuntimeCatalog,
    tables_by_name: dict[str, dict[str, Any]],
) -> dict[str, dict[str, int]]:
    """menuName -> {identityString -> recordIndex}."""
    out: dict[str, dict[str, int]] = {}
    for mname, table in tables_by_name.items():
        menu = catalog.by_name.get(mname)
        if not menu:
            continue
        ncol = _name_column(menu)
        if not ncol:
            continue
        idx: dict[str, int] = {}
        for rec in table.get("records") or []:
            vals = {v["columnName"]: v for v in rec.get("values") or []}
            cell = vals.get(ncol.name)
            if not cell:
                continue
            raw = str(cell.get("rawText") or "").strip()
            if _is_empty(raw):
                continue
            idx.setdefault(raw, int(rec["recordIndex"]))
        out[mname] = idx
    return out


def _column_name_index(menu: RuntimeMenu) -> dict[str, int]:
    return {c.name: c.index for c in menu.columns if c.datatypeRaw != MENU_TITLE_LINE}


def resolve_table_references(
    catalog: RuntimeCatalog,
    table: dict[str, Any],
    *,
    identity_index: dict[str, dict[str, int]],
    include_schema_capabilities: bool = True,
) -> list[ReferenceEdge]:
    """Resolve all selection-like columns for one loaded CP2 table."""
    menu = catalog.by_name.get(table["menuName"])
    if not menu:
        return []
    edges: list[ReferenceEdge] = []
    phys = (table.get("physicalSelection") or {}).get("selectedPath")
    sel_kind = (table.get("physicalSelection") or {}).get("selectedKind")

    if sel_kind == "UNSUPPORTED_ROM":
        # Capability note only — cannot resolve records
        for col in menu.columns:
            if col.datatypeRaw not in (SELECTION, SELECTION_UNIQUE, MENU_COLUMN_ROW):
                continue
            if not (col.dataselectRaw or col.datasourceRaw):
                continue
            edges.append(
                ReferenceEdge(
                    sourceMenu=menu.mnuname,
                    sourceRecord=None,
                    sourceColumn=col.name,
                    sourceColumnIndex=col.index,
                    sourceRawValue=None,
                    sourcePhysicalFile=phys,
                    datatypeRaw=col.datatypeRaw,
                    datatypeName=col.datatypeName,
                    dataselect=col.dataselectRaw or None,
                    datasource=col.datasourceRaw,
                    resolutionMode="UNRESOLVED",
                    targetMenu=None,
                    targetMenuIndex=None,
                    targetColumn=None,
                    targetColumnIndex=None,
                    targetRecord=None,
                    targetIdentity=None,
                    evidence=[{"rule": "storage", "status": "SOURCE_PROVEN"}],
                    status="UNRESOLVED",
                    unresolvedReason=UNSUPPORTED_STORAGE_FORMAT,
                    scope="SCHEMA_CAPABILITY",
                )
            )
        return edges

    if sel_kind == "MISSING" or not table.get("stats", {}).get("loaded"):
        for col in menu.columns:
            if col.datatypeRaw not in (SELECTION, SELECTION_UNIQUE, MENU_COLUMN_ROW):
                continue
            if not (col.dataselectRaw or col.datasourceRaw):
                continue
            edges.append(
                ReferenceEdge(
                    sourceMenu=menu.mnuname,
                    sourceRecord=None,
                    sourceColumn=col.name,
                    sourceColumnIndex=col.index,
                    sourceRawValue=None,
                    sourcePhysicalFile=phys,
                    datatypeRaw=col.datatypeRaw,
                    datatypeName=col.datatypeName,
                    dataselect=col.dataselectRaw or None,
                    datasource=col.datasourceRaw,
                    resolutionMode="UNRESOLVED",
                    targetMenu=None,
                    targetMenuIndex=None,
                    targetColumn=None,
                    targetColumnIndex=None,
                    targetRecord=None,
                    targetIdentity=None,
                    evidence=[{"rule": "storage", "status": "SOURCE_PROVEN"}],
                    status="UNRESOLVED",
                    unresolvedReason=SOURCE_FILE_UNAVAILABLE,
                    scope="SCHEMA_CAPABILITY",
                )
            )
        return edges

    # Schema capability edges for dynamic-capable columns
    if include_schema_capabilities:
        for col in menu.columns:
            if col.datatypeRaw not in (SELECTION, SELECTION_UNIQUE, MENU_COLUMN_ROW):
                continue
            ds = col.datasourceRaw
            dyn = (
                ds > 0
                and ds < len(menu.columns)
                and menu.columns[ds].datatypeRaw == SELECTION_UNIQUE
                and catalog.menu_menu_index is not None
                and menu.columns[ds].dataselectMenuIndex == catalog.menu_menu_index
            )
            if not dyn:
                continue
            edges.append(
                ReferenceEdge(
                    sourceMenu=menu.mnuname,
                    sourceRecord=None,
                    sourceColumn=col.name,
                    sourceColumnIndex=col.index,
                    sourceRawValue=None,
                    sourcePhysicalFile=phys,
                    datatypeRaw=col.datatypeRaw,
                    datatypeName=col.datatypeName,
                    dataselect=col.dataselectRaw or None,
                    datasource=ds,
                    resolutionMode="UNRESOLVED",
                    targetMenu=None,
                    targetMenuIndex=None,
                    targetColumn=None,
                    targetColumnIndex=None,
                    targetRecord=None,
                    targetIdentity=None,
                    evidence=[
                        {
                            "rule": "find_data_source_dynamic_capable",
                            "status": "SOURCE_PROVEN",
                            "datasourceColumn": menu.columns[ds].name,
                        }
                    ],
                    status="CAPABILITY",
                    unresolvedReason=DYNAMIC_CAPABLE_SCHEMA,
                    scope="SCHEMA_CAPABILITY",
                )
            )

    # Record edges
    for rec in table.get("records") or []:
        vals = {v["columnName"]: v for v in rec.get("values") or []}
        rec_i = int(rec["recordIndex"])

        for col in menu.columns:
            if col.datatypeRaw not in (SELECTION, SELECTION_UNIQUE, MENU_COLUMN_ROW):
                continue
            if not (col.dataselectRaw or col.datasourceRaw):
                continue

            cell = vals.get(col.name)
            raw = str(cell.get("rawText") if cell else "")

            # Datasource record value for find_data_source
            ds_value: int | None = None
            ds = col.datasourceRaw
            dyn_capable = (
                ds > 0
                and ds < len(menu.columns)
                and menu.columns[ds].datatypeRaw == SELECTION_UNIQUE
                and catalog.menu_menu_index is not None
                and menu.columns[ds].dataselectMenuIndex == catalog.menu_menu_index
            )
            if dyn_capable:
                ds_col = menu.columns[ds]
                ds_cell = vals.get(ds_col.name)
                ds_raw = str(ds_cell.get("rawText") if ds_cell else "")
                mapped = _menu_name_to_index(catalog, ds_raw)
                if mapped is None and not _is_empty(ds_raw):
                    # Non-empty but unknown menu name
                    edges.append(
                        ReferenceEdge(
                            sourceMenu=menu.mnuname,
                            sourceRecord=rec_i,
                            sourceColumn=col.name,
                            sourceColumnIndex=col.index,
                            sourceRawValue=raw,
                            sourcePhysicalFile=phys,
                            datatypeRaw=col.datatypeRaw,
                            datatypeName=col.datatypeName,
                            dataselect=col.dataselectRaw or None,
                            datasource=ds,
                            resolutionMode="UNRESOLVED",
                            targetMenu=None,
                            targetMenuIndex=None,
                            targetColumn=None,
                            targetColumnIndex=None,
                            targetRecord=None,
                            targetIdentity=None,
                            evidence=[{"rule": "find_data_source", "status": "SOURCE_PROVEN"}],
                            status="UNRESOLVED",
                            unresolvedReason=INVALID_DATASOURCE_VALUE,
                            scope="RECORD",
                        )
                    )
                    continue
                ds_value = mapped if mapped is not None else 0

            if ds > 0 and not (ds < len(menu.columns)):
                edges.append(
                    ReferenceEdge(
                        sourceMenu=menu.mnuname,
                        sourceRecord=rec_i,
                        sourceColumn=col.name,
                        sourceColumnIndex=col.index,
                        sourceRawValue=raw,
                        sourcePhysicalFile=phys,
                        datatypeRaw=col.datatypeRaw,
                        datatypeName=col.datatypeName,
                        dataselect=col.dataselectRaw or None,
                        datasource=ds,
                        resolutionMode="UNRESOLVED",
                        targetMenu=None,
                        targetMenuIndex=None,
                        targetColumn=None,
                        targetColumnIndex=None,
                        targetRecord=None,
                        targetIdentity=None,
                        evidence=[{"rule": "find_data_source", "status": "SOURCE_PROVEN"}],
                        status="UNRESOLVED",
                        unresolvedReason=INVALID_DATASOURCE_COLUMN,
                        scope="RECORD",
                    )
                )
                continue

            fds = find_data_source(
                catalog, menu, col.index, datasource_record_value=ds_value
            )
            mode = fds.get("resolutionMode") or "UNRESOLVED"
            reason = fds.get("reason")
            target_menu = fds.get("targetMenu")
            target_idx = fds.get("targetMenuIndex")

            # Map CP1 unresolved schema reason → taxonomy for record path
            if mode == "UNRESOLVED" and reason == "invalid_datasource_column":
                tax = INVALID_DATASOURCE_COLUMN
            elif mode == "UNRESOLVED":
                tax = UNSUPPORTED_REFERENCE_FORM
            else:
                tax = None

            if mode == "STATIC" and reason == "dynamic_fallback_datasource_value_le_0":
                mode = "FALLBACK_STATIC"

            if _is_empty(raw):
                # Still emit edge so empty selection is visible, but mark empty
                edges.append(
                    ReferenceEdge(
                        sourceMenu=menu.mnuname,
                        sourceRecord=rec_i,
                        sourceColumn=col.name,
                        sourceColumnIndex=col.index,
                        sourceRawValue=raw,
                        sourcePhysicalFile=phys,
                        datatypeRaw=col.datatypeRaw,
                        datatypeName=col.datatypeName,
                        dataselect=col.dataselectRaw or None,
                        datasource=ds,
                        resolutionMode=mode if mode != "UNRESOLVED" else "STATIC",
                        targetMenu=target_menu,
                        targetMenuIndex=target_idx,
                        targetColumn=None,
                        targetColumnIndex=None,
                        targetRecord=None,
                        targetIdentity=None,
                        evidence=fds.get("evidence") or [],
                        status="UNRESOLVED",
                        unresolvedReason=EMPTY_SOURCE_VALUE,
                        scope="RECORD",
                    )
                )
                continue

            if mode == "UNRESOLVED" or tax:
                edges.append(
                    ReferenceEdge(
                        sourceMenu=menu.mnuname,
                        sourceRecord=rec_i,
                        sourceColumn=col.name,
                        sourceColumnIndex=col.index,
                        sourceRawValue=raw,
                        sourcePhysicalFile=phys,
                        datatypeRaw=col.datatypeRaw,
                        datatypeName=col.datatypeName,
                        dataselect=col.dataselectRaw or None,
                        datasource=ds,
                        resolutionMode="UNRESOLVED",
                        targetMenu=target_menu,
                        targetMenuIndex=target_idx,
                        targetColumn=None,
                        targetColumnIndex=None,
                        targetRecord=None,
                        targetIdentity=None,
                        evidence=fds.get("evidence") or [],
                        status="UNRESOLVED",
                        unresolvedReason=tax or UNSUPPORTED_REFERENCE_FORM,
                        scope="RECORD",
                    )
                )
                continue

            if not target_menu:
                # dataselect blank and no dynamic target
                edges.append(
                    ReferenceEdge(
                        sourceMenu=menu.mnuname,
                        sourceRecord=rec_i,
                        sourceColumn=col.name,
                        sourceColumnIndex=col.index,
                        sourceRawValue=raw,
                        sourcePhysicalFile=phys,
                        datatypeRaw=col.datatypeRaw,
                        datatypeName=col.datatypeName,
                        dataselect=col.dataselectRaw or None,
                        datasource=ds,
                        resolutionMode=mode,
                        targetMenu=None,
                        targetMenuIndex=None,
                        targetColumn=None,
                        targetColumnIndex=None,
                        targetRecord=None,
                        targetIdentity=None,
                        evidence=fds.get("evidence") or [],
                        status="UNRESOLVED",
                        unresolvedReason=TARGET_MENU_MISSING,
                        scope="RECORD",
                    )
                )
                continue

            target_menu_obj = catalog.by_name.get(target_menu)
            if target_menu_obj is None:
                edges.append(
                    ReferenceEdge(
                        sourceMenu=menu.mnuname,
                        sourceRecord=rec_i,
                        sourceColumn=col.name,
                        sourceColumnIndex=col.index,
                        sourceRawValue=raw,
                        sourcePhysicalFile=phys,
                        datatypeRaw=col.datatypeRaw,
                        datatypeName=col.datatypeName,
                        dataselect=col.dataselectRaw or None,
                        datasource=ds,
                        resolutionMode=mode,
                        targetMenu=target_menu,
                        targetMenuIndex=target_idx,
                        targetColumn=None,
                        targetColumnIndex=None,
                        targetRecord=None,
                        targetIdentity=None,
                        evidence=fds.get("evidence") or [],
                        status="UNRESOLVED",
                        unresolvedReason=TARGET_MENU_MISSING,
                        scope="RECORD",
                    )
                )
                continue

            # MENU_COLUMN_ROW → resolve column name within target menu
            if col.datatypeRaw == MENU_COLUMN_ROW:
                colmap = _column_name_index(target_menu_obj)
                tci = colmap.get(raw.strip())
                if tci is None:
                    edges.append(
                        ReferenceEdge(
                            sourceMenu=menu.mnuname,
                            sourceRecord=rec_i,
                            sourceColumn=col.name,
                            sourceColumnIndex=col.index,
                            sourceRawValue=raw,
                            sourcePhysicalFile=phys,
                            datatypeRaw=col.datatypeRaw,
                            datatypeName=col.datatypeName,
                            dataselect=col.dataselectRaw or None,
                            datasource=ds,
                            resolutionMode=mode,
                            targetMenu=target_menu,
                            targetMenuIndex=target_idx,
                            targetColumn=None,
                            targetColumnIndex=None,
                            targetRecord=None,
                            targetIdentity=None,
                            evidence=fds.get("evidence") or [],
                            status="UNRESOLVED",
                            unresolvedReason=TARGET_COLUMN_MISSING,
                            scope="RECORD",
                        )
                    )
                else:
                    edges.append(
                        ReferenceEdge(
                            sourceMenu=menu.mnuname,
                            sourceRecord=rec_i,
                            sourceColumn=col.name,
                            sourceColumnIndex=col.index,
                            sourceRawValue=raw,
                            sourcePhysicalFile=phys,
                            datatypeRaw=col.datatypeRaw,
                            datatypeName=col.datatypeName,
                            dataselect=col.dataselectRaw or None,
                            datasource=ds,
                            resolutionMode=mode,
                            targetMenu=target_menu,
                            targetMenuIndex=target_idx,
                            targetColumn=raw.strip(),
                            targetColumnIndex=tci,
                            targetRecord=None,
                            targetIdentity=raw.strip(),
                            evidence=(fds.get("evidence") or [])
                            + [
                                {
                                    "rule": "MENU_COLUMN_ROW_name_match",
                                    "status": "SOURCE_PROVEN",
                                }
                            ],
                            status="RESOLVED",
                            unresolvedReason=None,
                            scope="RECORD",
                        )
                    )
                continue

            # SELECTION / SELECTION_UNIQUE → identity lookup in target menu
            ident = identity_index.get(target_menu, {})
            trec = ident.get(raw.strip())
            if trec is None:
                edges.append(
                    ReferenceEdge(
                        sourceMenu=menu.mnuname,
                        sourceRecord=rec_i,
                        sourceColumn=col.name,
                        sourceColumnIndex=col.index,
                        sourceRawValue=raw,
                        sourcePhysicalFile=phys,
                        datatypeRaw=col.datatypeRaw,
                        datatypeName=col.datatypeName,
                        dataselect=col.dataselectRaw or None,
                        datasource=ds,
                        resolutionMode=mode,
                        targetMenu=target_menu,
                        targetMenuIndex=target_idx,
                        targetColumn=_name_column(target_menu_obj).name
                        if _name_column(target_menu_obj)
                        else None,
                        targetColumnIndex=_name_column(target_menu_obj).index
                        if _name_column(target_menu_obj)
                        else None,
                        targetRecord=None,
                        targetIdentity=raw.strip(),
                        evidence=(fds.get("evidence") or [])
                        + [
                            {
                                "rule": "selection_identity_lookup",
                                "status": "SOURCE_PROVEN",
                            }
                        ],
                        status="UNRESOLVED",
                        unresolvedReason=TARGET_RECORD_MISSING,
                        scope="RECORD",
                    )
                )
            else:
                edges.append(
                    ReferenceEdge(
                        sourceMenu=menu.mnuname,
                        sourceRecord=rec_i,
                        sourceColumn=col.name,
                        sourceColumnIndex=col.index,
                        sourceRawValue=raw,
                        sourcePhysicalFile=phys,
                        datatypeRaw=col.datatypeRaw,
                        datatypeName=col.datatypeName,
                        dataselect=col.dataselectRaw or None,
                        datasource=ds,
                        resolutionMode=mode,
                        targetMenu=target_menu,
                        targetMenuIndex=target_idx,
                        targetColumn=_name_column(target_menu_obj).name
                        if _name_column(target_menu_obj)
                        else None,
                        targetColumnIndex=_name_column(target_menu_obj).index
                        if _name_column(target_menu_obj)
                        else None,
                        targetRecord=trec,
                        targetIdentity=raw.strip(),
                        evidence=(fds.get("evidence") or [])
                        + [
                            {
                                "rule": "selection_identity_lookup",
                                "status": "SOURCE_PROVEN",
                            }
                        ],
                        status="RESOLVED",
                        unresolvedReason=None,
                        scope="RECORD",
                    )
                )

    return edges


def build_reference_graph(
    *,
    fortna_mnu: Path,
    project_mnu: Path | None,
    run_dir: Path,
    ac_name: str,
) -> dict[str, Any]:
    fortna = parse_mnu_file(fortna_mnu, origin="FORTNA")
    schemas = [fortna]
    if project_mnu and Path(project_mnu).is_file():
        schemas.append(parse_mnu_file(project_mnu, origin="PROJECT"))
    catalog = build_runtime_catalog(*schemas)

    run_pack = load_run(
        fortna_mnu=fortna_mnu,
        project_mnu=project_mnu,
        run_dir=run_dir,
        ac_name=ac_name,
        only_menus=None,
    )
    tables_by_name = {t["menuName"]: t for t in run_pack["tables"]}
    identity_index = _build_identity_index(catalog, tables_by_name)

    edges: list[ReferenceEdge] = []
    for table in run_pack["tables"]:
        edges.extend(
            resolve_table_references(
                catalog, table, identity_index=identity_index, include_schema_capabilities=True
            )
        )

    # Forward list — keep all non-empty edges in artifact body.
    # EMPTY_SOURCE_VALUE edges are counted fully in taxonomy but omitted from the
    # relationships[] body to keep artifacts reviewable/pushable (often 300k+).
    # They are NOT hidden: statistics.unresolvedTaxonomy.EMPTY_SOURCE_VALUE is exact.
    forward = [
        asdict(e)
        for e in edges
        if not (e.scope == "RECORD" and e.unresolvedReason == EMPTY_SOURCE_VALUE)
    ]
    empty_source_edges = [
        e for e in edges if e.scope == "RECORD" and e.unresolvedReason == EMPTY_SOURCE_VALUE
    ]

    # Complete reverse index — NO omission for hot targets.
    # Empty-source edges do not contribute meaningful reverse identities.
    reverse: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in edges:
        if e.scope != "RECORD":
            continue
        if e.unresolvedReason == EMPTY_SOURCE_VALUE:
            continue
        if not e.targetMenu:
            key = "UNRESOLVED"
        elif e.targetRecord is not None:
            key = f"{e.targetMenu}#{e.targetRecord}"
        elif e.targetColumn:
            key = f"{e.targetMenu}.{e.targetColumn}"
        else:
            key = f"{e.targetMenu}"
        reverse[key].append(
            {
                "sourceMenu": e.sourceMenu,
                "sourceRecord": e.sourceRecord,
                "sourceColumn": e.sourceColumn,
                "sourceRawValue": e.sourceRawValue,
                "resolutionMode": e.resolutionMode,
                "status": e.status,
                "unresolvedReason": e.unresolvedReason,
                "targetIdentity": e.targetIdentity,
            }
        )

    # Stats
    record_edges = [e for e in edges if e.scope == "RECORD"]
    cap_edges = [e for e in edges if e.scope == "SCHEMA_CAPABILITY"]
    tax = Counter(
        e.unresolvedReason
        for e in edges
        if e.status in {"UNRESOLVED", "CAPABILITY"} and e.unresolvedReason
    )
    stats = {
        "schemaMenus": len(catalog.menus),
        "tablesLoaded": run_pack["summary"]["tablesLoaded"],
        "recordsLoaded": run_pack["summary"]["totalRecords"],
        "valuesLoaded": run_pack["summary"]["totalValues"],
        "machineSpecific": run_pack["summary"]["machineSpecificSelections"],
        "genericAsc": run_pack["summary"]["genericFallbacks"],
        "missingTables": run_pack["summary"]["missingTables"],
        "unsupportedRom": run_pack["summary"]["unsupportedRom"],
        "edgesTotal": len(edges),
        "edgesRecord": len(record_edges),
        "edgesSchemaCapability": len(cap_edges),
        "resolved": sum(1 for e in record_edges if e.status == "RESOLVED"),
        "unresolvedRecord": sum(1 for e in record_edges if e.status == "UNRESOLVED"),
        "static": sum(1 for e in record_edges if e.resolutionMode == "STATIC"),
        "dynamic": sum(1 for e in record_edges if e.resolutionMode == "DYNAMIC"),
        "fallbackStatic": sum(
            1 for e in record_edges if e.resolutionMode == "FALLBACK_STATIC"
        ),
        "unresolvedTaxonomy": dict(sorted(tax.items())),
        "reverseKeys": len(reverse),
        "relationshipsInArtifactBody": len(forward),
        "emptySourceEdgesOmittedFromBody": len(empty_source_edges),
        "cp2Summary": run_pack["summary"],
    }

    return {
        "kind": "FortnaReferenceGraph",
        "version": 1,
        "acName": ac_name,
        "runDir": str(run_dir),
        "statistics": stats,
        "relationships": forward,
        "reverseRelationships": {k: v for k, v in sorted(reverse.items())},
        "filePrecedence": run_pack.get("filePrecedence"),
        "notes": [
            "References are FortnaPlus selection relationships, not engineering topology.",
            "SCHEMA_CAPABILITY edges with DYNAMIC_CAPABLE_SCHEMA are not RUN defects.",
            "Reverse index is complete for non-empty references (no hot-target omission).",
            "EMPTY_SOURCE_VALUE edges are counted in unresolvedTaxonomy but omitted from "
            "relationships[] body to keep artifacts tractable; counts remain exact.",
        ],
    }


def extract_proofs(graph: dict[str, Any], *, site: str) -> dict[str, Any]:
    """Extract common proof slices for acceptance reports (generic queries)."""
    rels = graph.get("relationships") or []
    rev = graph.get("reverseRelationships") or {}

    def record_edges(menu: str, rec: int | None = None, col: str | None = None):
        out = []
        for e in rels:
            if e.get("scope") != "RECORD":
                continue
            if e.get("sourceMenu") != menu:
                continue
            if rec is not None and e.get("sourceRecord") != rec:
                continue
            if col is not None and e.get("sourceColumn") != col:
                continue
            out.append(e)
        return out

    # Find Mtrchain record where Motor_Name raw is M314
    m314_rec = None
    for e in record_edges("Mtrchain", col="Motor_Name"):
        if e.get("sourceRawValue") == "M314":
            m314_rec = e.get("sourceRecord")
            break
    # Also try Motor_Ndx
    if m314_rec is None:
        for e in record_edges("Mtrchain", col="Motor_Ndx"):
            if e.get("sourceRawValue") == "M314":
                m314_rec = e.get("sourceRecord")
                break

    m314 = {}
    if m314_rec is not None:
        for col in ("Motor_Ndx", "Motor_Chained1", "Motor_Aux", "Enabled", "Motor_Name"):
            xs = record_edges("Mtrchain", m314_rec, col)
            m314[col] = xs[0] if xs else None

    # MergeInputs by MergeBoss identity
    def merge_lanes(boss_name: str) -> list[dict[str, Any]]:
        lanes = []
        boss_edges = [
            e
            for e in record_edges("MergeInputs", col="MergeBoss")
            if e.get("sourceRawValue") == boss_name and e.get("status") == "RESOLVED"
        ]
        for be in boss_edges:
            rec = be.get("sourceRecord")
            lane = {"sourceRecord": rec, "MergeBoss": be}
            for col in ("Presense", "ReleaseIO", "LaneReadyInput1", "LaneReadyInput2"):
                xs = record_edges("MergeInputs", rec, col)
                lane[col] = xs[0] if xs else None
            lanes.append(lane)
        return lanes

    # Reverse helpers
    def rev_for_identity(menu: str, identity: str) -> dict[str, Any]:
        # Find target record index via a resolved edge pointing to that identity
        trec = None
        for e in rels:
            if (
                e.get("scope") == "RECORD"
                and e.get("targetMenu") == menu
                and e.get("targetIdentity") == identity
                and e.get("targetRecord") is not None
            ):
                trec = e["targetRecord"]
                break
        key = f"{menu}#{trec}" if trec is not None else None
        return {
            "identity": identity,
            "targetRecord": trec,
            "reverseKey": key,
            "inbound": rev.get(key, []) if key else [],
            "inboundCount": len(rev.get(key, [])) if key else 0,
        }

    # Dynamic samples
    dyn = [
        e
        for e in rels
        if e.get("scope") == "RECORD" and e.get("resolutionMode") == "DYNAMIC"
    ][:10]

    return {
        "site": site,
        "mtrchainM314": {"recordIndex": m314_rec, "columns": m314},
        "merge316": merge_lanes("MERGE_316_SPUR"),
        "merge324": merge_lanes("MERGE_324_SPUR"),
        "dynamicSamples": dyn,
        "reverseM314": rev_for_identity("Conveyor", "M314"),
        "reverseMerge316": rev_for_identity("MergeBoss", "MERGE_316_SPUR"),
        "jamcheckSamples": [
            e
            for e in rels
            if e.get("sourceMenu") == "Jamcheck"
            and e.get("scope") == "RECORD"
            and e.get("status") == "RESOLVED"
        ][:20],
        "estopSamples": [
            e
            for e in rels
            if e.get("sourceMenu") == "EStop"
            and e.get("scope") == "RECORD"
            and e.get("sourceColumn") in {"Part", "Error"}
            and e.get("status") == "RESOLVED"
        ][:20],
    }


def write_graph(graph: dict[str, Any], out_path: Path) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(graph, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    out_path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CP3 FortnaPlus reference resolver")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--fortna-mnu", default="")
    ap.add_argument("--project-mnu", default="")
    ap.add_argument("--ac-name", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--proofs-out", default="")
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    fortna = Path(args.fortna_mnu) if args.fortna_mnu else run_dir / "FORTNA" / "fortna.mnu"
    project = Path(args.project_mnu) if args.project_mnu else run_dir / "PROJECT" / "project.mnu"
    if not project.is_file():
        project = None

    graph = build_reference_graph(
        fortna_mnu=fortna,
        project_mnu=project,
        run_dir=run_dir,
        ac_name=args.ac_name,
    )
    digest = write_graph(graph, Path(args.out))
    st = graph["statistics"]
    print(
        f"CP3 {args.ac_name}: edges={st['edgesTotal']} record={st['edgesRecord']} "
        f"resolved={st['resolved']} unresolvedRecord={st['unresolvedRecord']} "
        f"static={st['static']} dynamic={st['dynamic']} fallback={st['fallbackStatic']} "
        f"capability={st['edgesSchemaCapability']}"
    )
    print("taxonomy", st["unresolvedTaxonomy"])
    print("sha256", digest)
    print("wrote", args.out)
    if args.proofs_out:
        proofs = extract_proofs(graph, site=args.ac_name)
        Path(args.proofs_out).write_text(
            json.dumps(proofs, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print("wrote", args.proofs_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
