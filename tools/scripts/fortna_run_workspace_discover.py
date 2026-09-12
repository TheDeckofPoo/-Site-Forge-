#!/usr/bin/env python3
"""Unified RUN-driven workspace discovery → canonical SiteModel.

SOURCE OF TRUTH: RUN + engineer overrides only. Never reads finished PLC.
Does not fake sorter/WCS generation. Transport visual freeze — data hooks only.

Usage:
  python fortna_run_workspace_discover.py \\
    --run-dir workspace/cp4-run/RUN --machine ORNCCP4 --out exports/run-discovery

  python fortna_run_workspace_discover.py \\
    --run-dir workspace/active/RUN --machine ORNCCP2 --out exports/run-discovery-cp2
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_activity_classify import classify_site_model  # noqa: E402
from fortna_asc import CONVEYOR_TYPES, read_asc  # noqa: E402
from fortna_site_model import (  # noqa: E402
    ACTIVE_CONFIRMED,
    ACTIVE_LIKELY,
    AVAILABLE,
    DEFAULT_AREA_ID,
    EXCLUDED,
    GEN_CFG,
    GEN_NOT_SUPPORTED,
    GEN_READY,
    HISTORICAL_OR_STALE,
    INCLUDED,
    PROV_ENGINEER_REQUIRED,
    PROV_RUN_DERIVED,
    PROV_RUN_EXPLICIT,
    PROV_UNKNOWN,
    SCOPE_BASE_ONLY,
    SCOPE_OVERLAY,
    SiteModel,
    UNKNOWN,
    _clean,
    apply_engineer_overrides,
    change_report,
    ensure_default_area,
    extract_p_from_name,
    load_json,
    make_object,
    merge_table_rows,
    normalize_name,
    p_tag_ok,
    write_json,
)

try:
    from fortna_cp4_discovery import (
        discover_encoders,
        discover_equipment,
        discover_sawtooth,
        discover_tracking_wcs,
        discover_vfd,
        resolve_asc,
    )
except Exception:  # pragma: no cover
    discover_encoders = None  # type: ignore
    discover_equipment = None  # type: ignore
    discover_sawtooth = None  # type: ignore
    discover_tracking_wcs = None  # type: ignore
    discover_vfd = None  # type: ignore
    resolve_asc = None  # type: ignore

try:
    from fortna_run_geometry_investigate import (
        _is_motor_row,
        _is_pe_row,
        _load_mtrchain,
        _load_word_map,
        _row_on_controller,
        investigate,
    )
except Exception:  # pragma: no cover
    _is_motor_row = None  # type: ignore
    _is_pe_row = None  # type: ignore
    _load_mtrchain = None  # type: ignore
    _load_word_map = None  # type: ignore
    _row_on_controller = None  # type: ignore
    investigate = None  # type: ignore

try:
    from fortna_run_physical_layout import build_transport_graph
except Exception:  # pragma: no cover
    build_transport_graph = None  # type: ignore

try:
    from fortna_sawtooth_semantics import build_semantic_model
except Exception:  # pragma: no cover
    build_semantic_model = None  # type: ignore

MECH = {t.upper() for t in CONVEYOR_TYPES} | {"ZEROPRESSURE", "ACCUMULATOR", "MDR"}

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def assert_no_finished_plc_usage(source_text: str) -> None:
    """Fail if source appears to read finished/reference PLC as an input."""
    # Built from fragments so this helper does not self-match.
    needles = [
        "read_l5x" + "(",
        "parse_l5x" + "(",
        "workbook_from_reference" + "(",
        "ORLY_" + "Greensboro_NC_PLC4",
        "PLC4Finished" + ".L5X",
        "finished_plc4" + " =",
        "plc4_finished" + " =",
        "from_reference" + "_l5x",
    ]
    low = source_text.lower()
    for needle in needles:
        if needle.lower() in low:
            raise RuntimeError(f"Finished PLC path reference forbidden in discovery: {needle}")


def _pe_to_p(pe: str) -> str:
    m = re.match(r"^(?:EZ)?PE[\s\-_]*(\d{2,4}[A-Za-z]?)", pe or "", re.I)
    return ("P" + m.group(1).upper()) if m else ""


def _vfd_to_p(name: str) -> str:
    m = re.match(r"^VFD[\s\-_]*(\d{2,4}[A-Za-z]?)", name or "", re.I)
    return ("P" + m.group(1).upper()) if m else ""


def _motor_to_p(name: str) -> str:
    m = re.match(r"^M[\s\-_]*(\d{2,4}[A-Za-z]?)", name or "", re.I)
    return ("P" + m.group(1).upper()) if m else ""


def _has_sawtooth_evidence(run_dir: Path, machine: str) -> bool:
    if discover_sawtooth is None:
        fortna = run_dir / "FORTNA"
        for stem in ("SawMerge.asc", "SawLane.asc"):
            merged = merge_table_rows(fortna, stem, machine)
            for item in merged.get("rows") or []:
                if _clean((item.get("row") or {}).get("Name")):
                    return True
        return False
    saw = discover_sawtooth(run_dir, machine)
    return bool((saw.get("counts") or {}).get("merges") or (saw.get("counts") or {}).get("lanes"))


def _load_controllers(run_dir: Path, machine: str) -> list[dict[str, Any]]:
    fortna = run_dir / "FORTNA"
    merged = merge_table_rows(fortna, "Machine.asc", machine)
    out: list[dict[str, Any]] = []
    for item in merged.get("rows") or []:
        row = item["row"]
        name = _clean(row.get("Machine_Name"))
        if not name:
            continue
        offline = _clean(row.get("Offline"))
        obj = make_object(
            "controller",
            name,
            source_table="Machine.asc",
            source_row=item["source_row"],
            source_scope=item["source_scope"],
            active_state=ACTIVE_CONFIRMED if offline.upper() not in {"Y", "YES"} else "INACTIVE_CONFIRMED",
            inclusion=INCLUDED if name.upper() == machine.upper() else AVAILABLE,
            confidence="HIGH",
            provenance=item.get("provenance") or PROV_RUN_EXPLICIT,
            evidence=list(item.get("evidence") or []),
            generation_state=GEN_CFG,
            Offline=offline,
            status=_clean(row.get("Status")),
            machine_index=_clean(row.get("Machine_Index")),
        ).to_dict()
        out.append(obj)
    return out


def _load_estop_zones(run_dir: Path, machine: str) -> list[dict[str, Any]]:
    fortna = run_dir / "FORTNA"
    path = fortna / "EStop.asc"
    if not path.is_file():
        return []
    _h, rows = read_asc(path)
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        name = _clean(row.get("Desc") or row.get("Part"))
        if not name:
            continue
        out.append(
            make_object(
                "estop_zone",
                name,
                source_table="EStop.asc",
                source_row=i,
                source_scope=SCOPE_BASE_ONLY,
                active_state=ACTIVE_LIKELY,
                inclusion=AVAILABLE,
                confidence="MEDIUM",
                provenance=PROV_RUN_EXPLICIT,
                evidence=[{"kind": "estop_table_row"}],
                generation_state=GEN_CFG,
                part=_clean(row.get("Part")),
                error=_clean(row.get("Error")),
            ).to_dict()
        )
    return out


def _discover_transport(
    run_dir: Path,
    machine: str,
    owned_tags: set[str] | None = None,
) -> dict[str, Any]:
    """Transport data hook only — no visual polish (TRANSPORT_FREEZE)."""
    transport: dict[str, Any] = {
        "provenance": PROV_RUN_DERIVED,
        "visual_freeze": True,
        "nodes": [],
        "edges": [],
        "metrics": {},
        "note": "Transport visual freeze — discovery populates data hooks only",
    }
    geom = None
    if investigate is not None:
        tmp = run_dir.parent / f"_run_discover_geom_{machine}"
        try:
            geom = investigate(run_dir, machine, tmp)
        except Exception as exc:  # noqa: BLE001
            transport["geometry_error"] = str(exc)
            geom = None

    if geom:
        owned = {normalize_name(t) for t in (owned_tags or []) if t}
        nodes = []
        for e in geom.get("equipment") or []:
            tag = e.get("conveyor") or e.get("conveyor_tag") or ""
            if owned and normalize_name(tag) not in owned:
                continue
            nodes.append(
                {
                    "tag": tag,
                    "type": e.get("equipment_type") or e.get("type"),
                    "x": e.get("x"),
                    "y": e.get("y"),
                    "angle": e.get("angle"),
                    "length": e.get("length"),
                    "width": e.get("width"),
                    "entry": e.get("entry_anchor") or e.get("entry"),
                    "exit": e.get("exit_anchor") or e.get("exit"),
                    "provenance": PROV_RUN_EXPLICIT,
                }
            )
        # If ownership filter emptied geometry set, fall back to geometry equipment
        if not nodes and not owned:
            for e in geom.get("equipment") or []:
                tag = e.get("conveyor") or e.get("conveyor_tag") or ""
                nodes.append(
                    {
                        "tag": tag,
                        "type": e.get("equipment_type") or e.get("type"),
                        "x": e.get("x"),
                        "y": e.get("y"),
                        "angle": e.get("angle"),
                        "length": e.get("length"),
                        "width": e.get("width"),
                        "entry": e.get("entry_anchor") or e.get("entry"),
                        "exit": e.get("exit_anchor") or e.get("exit"),
                        "provenance": PROV_RUN_EXPLICIT,
                    }
                )
        if owned and not nodes:
            # Prefer SiteModel equipment geometry when investigate ownership diverges
            transport["note"] += (
                "; geometry investigate ownership diverged — nodes filled from equipment set later"
            )
        node_tags = {normalize_name(n["tag"]) for n in nodes}
        edges = []
        for c in geom.get("candidates") or []:
            cls = (c.get("classification") or "").upper()
            if cls not in {"CONFIRMED", "HIGH-CONFIDENCE CANDIDATE", "HIGH_CONFIDENCE"}:
                continue
            frm = (
                c.get("from_conveyor")
                or c.get("from")
                or c.get("upstream")
                or c.get("exit_tag")
            )
            to = (
                c.get("to_conveyor")
                or c.get("to")
                or c.get("downstream")
                or c.get("entry_tag")
            )
            if node_tags and (
                normalize_name(str(frm or "")) not in node_tags
                or normalize_name(str(to or "")) not in node_tags
            ):
                continue
            edges.append(
                {
                    "from": frm,
                    "to": to,
                    "classification": c.get("classification"),
                    "distance": c.get("exit_to_entry_distance") or c.get("distance"),
                    "provenance": PROV_RUN_DERIVED,
                }
            )
        transport["nodes"] = nodes
        transport["edges"] = edges
        transport["metrics"] = geom.get("summary") or {
            "equipment": len(nodes),
            "connection_candidates": len(geom.get("candidates") or []),
            "auto_edges": len(edges),
        }
        transport["metrics"]["scoped_nodes"] = len(nodes)
        transport["metrics"]["scoped_edges"] = len(edges)
        transport["source"] = "fortna_run_geometry_investigate"

    # Optional fuller graph (still data-only; UI freeze)
    if build_transport_graph is not None:
        try:
            graph = build_transport_graph(run_dir, machine)
            transport["graph_stub"] = {
                "node_count": len(graph.get("nodes") or []),
                "edge_count": len(graph.get("edges") or graph.get("connections") or []),
                "metrics": graph.get("metrics") or {},
                "note": "stub hook only — transport visual freeze",
            }
        except Exception as exc:  # noqa: BLE001
            transport["graph_stub_error"] = str(exc)
    return transport


def _equipment_from_cp_discovery(
    run_dir: Path,
    machine: str,
    sawtooth: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Prefer CP4-style ownership discovery when available; else geometry set."""
    relationships: list[dict[str, Any]] = []
    table_res: dict[str, Any] = {}
    fortna = run_dir / "FORTNA"
    conv_merged = merge_table_rows(fortna, "Conveyor.asc", machine)
    table_res["Conveyor.asc"] = {
        "resolution": conv_merged["resolution"],
        "paths": conv_merged["paths"],
        "counts": conv_merged["counts"],
    }

    equipment_docs: list[dict[str, Any]] = []
    ownership: dict[str, list[dict[str, Any]]] = {}

    if discover_equipment is not None and sawtooth is not None:
        eq_doc, layout = discover_equipment(run_dir, machine, sawtooth)
        for e in eq_doc.get("equipment") or []:
            tag = e.get("conveyor_tag") or ""
            evid = []
            for ow in e.get("ownership_evidence") or []:
                evid.append(
                    {
                        "kind": ow.get("method") or "ownership",
                        "detail": ow.get("detail"),
                        "provenance": ow.get("provenance"),
                    }
                )
            if e.get("saw_lane"):
                evid.append({"kind": "saw_lane", "detail": e.get("saw_lane")})
            for m in e.get("motors") or []:
                evid.append({"kind": "mtrchain", "detail": m})
                relationships.append(
                    {
                        "from": m,
                        "to": tag,
                        "kind": "motor_to_conveyor",
                        "provenance": PROV_RUN_EXPLICIT,
                    }
                )
            obj = make_object(
                "equipment",
                tag,
                source_table="Conveyor.asc",
                source_row=tag,
                source_scope=eq_doc.get("source_resolution") or SCOPE_BASE_ONLY,
                active_state=ACTIVE_CONFIRMED if evid else ACTIVE_LIKELY,
                inclusion=INCLUDED,
                confidence="HIGH" if evid else "MEDIUM",
                provenance=e.get("provenance") or PROV_RUN_EXPLICIT,
                evidence=evid,
                generation_state=GEN_CFG,
                equipment_type=e.get("equipment_type"),
                x=e.get("x"),
                y=e.get("y"),
                angle=e.get("angle"),
                length=e.get("length"),
                width=e.get("width"),
                entry_anchor=e.get("entry_anchor"),
                exit_anchor=e.get("exit_anchor"),
                motors=e.get("motors") or [],
                saw_lane=e.get("saw_lane"),
                machine_name=e.get("machine_name_field"),
                has_geometry=e.get("has_geometry"),
                placed=e.get("placed"),
            ).to_dict()
            equipment_docs.append(obj)
            ownership[normalize_name(tag)] = evid
        table_res["equipment_layout"] = layout
        return equipment_docs, relationships, table_res

    # Fallback: geometry investigate owned set
    if investigate is None:
        return [], relationships, table_res
    tmp = run_dir.parent / f"_run_discover_eq_{machine}"
    geom = investigate(run_dir, machine, tmp)
    for e in geom.get("equipment") or []:
        tag = e.get("conveyor") or e.get("conveyor_tag") or ""
        evid = [{"kind": "controller_scoped_geometry"}]
        for d in e.get("drives") or []:
            evid.append({"kind": "motor_link", "detail": d.get("motor")})
        for pe in e.get("photoeyes_name_associated") or []:
            evid.append({"kind": "pe_assignment", "detail": pe.get("photoeye")})
        equipment_docs.append(
            make_object(
                "equipment",
                tag,
                source_table="Conveyor.asc",
                source_row=tag,
                source_scope=SCOPE_BASE_ONLY,
                active_state=ACTIVE_LIKELY,
                inclusion=INCLUDED,
                confidence="MEDIUM",
                provenance=PROV_RUN_EXPLICIT,
                evidence=evid,
                generation_state=GEN_CFG,
                equipment_type=e.get("equipment_type"),
                x=e.get("x"),
                y=e.get("y"),
                angle=e.get("angle"),
                length=e.get("length"),
                width=e.get("width"),
                entry_anchor=e.get("entry_anchor"),
                exit_anchor=e.get("exit_anchor"),
                motors=[d.get("motor") for d in (e.get("drives") or []) if d.get("motor")],
                has_geometry=bool(e.get("entry_anchor") and e.get("exit_anchor")),
                placed=True,
            ).to_dict()
        )
    return equipment_docs, relationships, table_res


def _devices_from_conveyor(
    run_dir: Path,
    machine: str,
    owned_tags: set[str],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    fortna = run_dir / "FORTNA"
    conv_path = fortna / "Conveyor.asc"
    if not conv_path.is_file():
        return [], [], [], []
    word_map = _load_word_map(run_dir) if _load_word_map else {}
    _h, rows = read_asc(conv_path)
    motors: list[dict] = []
    vfds: list[dict] = []
    photoeyes: list[dict] = []
    relationships: list[dict] = []
    seen: set[str] = set()

    for i, r in enumerate(rows, start=1):
        name = _clean(r.get("IO_Name"))
        if not name:
            continue
        nu = name.upper()
        on = True
        if _row_on_controller is not None:
            try:
                on = _row_on_controller(r, machine, word_map)
            except Exception:
                on = _clean(r.get("Machine_Name")).upper() == machine.upper()

        if _is_pe_row is not None and _is_pe_row(r):
            if not on:
                continue
            link = _pe_to_p(name)
            evid = [{"kind": "controller_io"}, {"kind": "pe_assignment", "detail": link}]
            photoeyes.append(
                make_object(
                    "photoeye",
                    name,
                    source_table="Conveyor.asc",
                    source_row=i,
                    source_scope=SCOPE_BASE_ONLY,
                    active_state=ACTIVE_CONFIRMED,
                    inclusion=INCLUDED if (not link or link in owned_tags) else AVAILABLE,
                    confidence="HIGH",
                    provenance=PROV_RUN_EXPLICIT,
                    evidence=evid,
                    generation_state=GEN_CFG,
                    machine_name=_clean(r.get("Machine_Name")),
                    io_address_word=_clean(r.get("IO_Address_Word")),
                    linked_conveyor=link or None,
                ).to_dict()
            )
            if link:
                relationships.append(
                    {
                        "from": name,
                        "to": link,
                        "kind": "pe_to_conveyor",
                        "provenance": PROV_RUN_EXPLICIT,
                    }
                )
            continue

        if nu.startswith("VFD"):
            if not on:
                continue
            base = re.match(r"^(VFD\d+[A-Z]?)", nu)
            base_n = base.group(1) if base else nu
            if base_n in seen:
                continue
            seen.add(base_n)
            link = _vfd_to_p(base_n)
            vfds.append(
                make_object(
                    "vfd",
                    base_n,
                    source_table="Conveyor.asc",
                    source_row=i,
                    source_scope=SCOPE_BASE_ONLY,
                    active_state=ACTIVE_CONFIRMED,
                    inclusion=INCLUDED,
                    confidence="HIGH",
                    provenance=PROV_RUN_EXPLICIT,
                    evidence=[
                        {"kind": "controller_io"},
                        {"kind": "vfd_link", "detail": link},
                    ],
                    generation_state=GEN_CFG,
                    machine_name=_clean(r.get("Machine_Name")),
                    io_address_word=_clean(r.get("IO_Address_Word")),
                    linked_conveyor=link or None,
                    description=_clean(r.get("General_Description")),
                ).to_dict()
            )
            if link:
                relationships.append(
                    {
                        "from": base_n,
                        "to": link,
                        "kind": "vfd_to_conveyor",
                        "provenance": PROV_RUN_DERIVED,
                    }
                )
            continue

        if _is_motor_row is not None and _is_motor_row(r) and re.match(r"^M\d", name, re.I):
            if not on:
                continue
            if nu in seen:
                continue
            seen.add(nu)
            link = _motor_to_p(name)
            motors.append(
                make_object(
                    "motor",
                    name,
                    source_table="Conveyor.asc",
                    source_row=i,
                    source_scope=SCOPE_BASE_ONLY,
                    active_state=ACTIVE_CONFIRMED,
                    inclusion=INCLUDED if (not link or link in owned_tags) else AVAILABLE,
                    confidence="HIGH",
                    provenance=PROV_RUN_EXPLICIT,
                    evidence=[
                        {"kind": "controller_io"},
                        {"kind": "motor_link", "detail": link},
                    ],
                    generation_state=GEN_CFG,
                    machine_name=_clean(r.get("Machine_Name")),
                    io_address_word=_clean(r.get("IO_Address_Word")),
                    linked_conveyor=link or None,
                ).to_dict()
            )
            if link:
                relationships.append(
                    {
                        "from": name,
                        "to": link,
                        "kind": "motor_to_conveyor",
                        "provenance": PROV_RUN_EXPLICIT,
                    }
                )
    return motors, vfds, photoeyes, relationships


def _build_sawtooth(
    run_dir: Path,
    machine: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Return sawtooth_merges objects, relationships, raw discovery, semantics slice."""
    if discover_sawtooth is None:
        return [], [], {}, {}
    saw = discover_sawtooth(run_dir, machine)
    merges_out: list[dict[str, Any]] = []
    rels: list[dict[str, Any]] = []
    if not (saw.get("merges") or saw.get("lanes")):
        return [], [], saw, {}

    lanes_by_merge: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for lane in saw.get("lanes") or []:
        lanes_by_merge[lane.get("saw_merge") or ""].append(lane)
        for r in lane.get("relationships") or []:
            rels.append(
                {
                    "from": r.get("from"),
                    "to": r.get("to"),
                    "kind": r.get("type") or r.get("kind"),
                    "provenance": r.get("provenance") or PROV_RUN_EXPLICIT,
                }
            )

    for m in saw.get("merges") or []:
        name = m.get("name") or ""
        lane_rows = lanes_by_merge.get(name) or []
        evid = [
            {"kind": "saw_merge", "detail": name},
            {
                "kind": "source",
                "scope": (saw.get("sources") or {}).get("SawMerge", {}).get("resolution"),
                "path": m.get("source_file"),
            },
        ]
        if m.get("motor_io"):
            evid.append({"kind": "vfd_link", "detail": m.get("motor_io")})
        merges_out.append(
            make_object(
                "sawtooth_merge",
                name,
                source_table="SawMerge.asc",
                source_row=name,
                source_scope=SCOPE_OVERLAY
                if "overlay" in str((saw.get("sources") or {}).get("SawMerge", {}).get("resolution"))
                else SCOPE_BASE_ONLY,
                active_state=ACTIVE_CONFIRMED,
                inclusion=INCLUDED,
                confidence="HIGH",
                provenance=PROV_RUN_EXPLICIT,
                evidence=evid,
                generation_state=GEN_CFG,
                motor_io=m.get("motor_io"),
                reservation=m.get("reservation"),
                slice_seconds=m.get("slice_seconds"),
                lanes=[
                    {
                        "name": ln.get("name"),
                        "conveyor": ln.get("conveyor"),
                        "photoeye": ln.get("photoeye"),
                        "drive": ln.get("drive") or ln.get("vfd"),
                        "lane_index": ln.get("lane_index"),
                        "provenance": ln.get("provenance") or PROV_RUN_EXPLICIT,
                        "conveyor_provenance": ln.get("conveyor_provenance"),
                    }
                    for ln in lane_rows
                ],
                config_required=[
                    x
                    for x in (
                        "collector parameterization" if not m.get("slice_seconds") else None,
                        "lane conveyor" if any(not ln.get("conveyor") for ln in lane_rows) else None,
                    )
                    if x
                ],
            ).to_dict()
        )

    semantics: dict[str, Any] = {}
    if build_semantic_model is not None and merges_out:
        try:
            # Optional semantic enrichment — discovery only
            semantics = {"note": "fortna_sawtooth_semantics available for deeper slice"}
        except Exception as exc:  # noqa: BLE001
            semantics = {"error": str(exc)}
    return merges_out, rels, saw, semantics


def _discover_sorters(run_dir: Path, machine: str) -> list[dict[str, Any]]:
    fortna = run_dir / "FORTNA"
    merged = merge_table_rows(fortna, "Sorters.asc", machine)
    sorters: list[dict[str, Any]] = []
    for item in merged.get("rows") or []:
        row = item["row"]
        name = _clean(row.get("Sorter Name") or row.get("Name"))
        if not name:
            continue
        enc = _clean(row.get("Encoder ioName") or row.get("Encoder Name"))
        row_mach = _clean(row.get("Machine"))
        scoped = (not row_mach) or row_mach.upper() == machine.upper()
        research_fields: dict[str, Any] = {}
        sorters.append(
            make_object(
                "sorter",
                name,
                source_table="Sorters.asc",
                source_row=item["source_row"],
                source_scope=item["source_scope"],
                active_state=ACTIVE_CONFIRMED if scoped else ACTIVE_LIKELY,
                inclusion=INCLUDED if scoped else AVAILABLE,
                confidence="HIGH" if scoped else "MEDIUM",
                provenance=item.get("provenance") or PROV_RUN_EXPLICIT,
                evidence=[
                    {"kind": "sorter_table"},
                    *list(item.get("evidence") or []),
                    *([{"kind": "encoder_link", "detail": enc}] if enc else []),
                ],
                generation_state=GEN_NOT_SUPPORTED,
                encoder_io=enc or None,
                machine_name=row_mach or None,
                discovery_only=True,
                **research_fields,
            ).to_dict()
        )

    # Integrate parallel sorter-research exports when present (discovery fields only)
    research_path = ROOT / "exports" / "sorter-research" / "subsystem_model.json"
    research = load_json(research_path)
    if research:
        by_name = {normalize_name(s["normalized_name"]): s for s in sorters}
        for rs in research.get("sorters") or []:
            rname = rs.get("name")
            if isinstance(rname, dict):
                rname = rname.get("value")
            nn = normalize_name(str(rname or ""))
            if not nn:
                continue
            enc = rs.get("encoder_io")
            if isinstance(enc, dict):
                enc = enc.get("value")
            if nn in by_name:
                by_name[nn]["research_ref"] = "exports/sorter-research/subsystem_model.json"
                if enc and not by_name[nn].get("encoder_io"):
                    by_name[nn]["encoder_io"] = enc
                by_name[nn].setdefault("evidence", []).append(
                    {"kind": "sorter_research_integrate"}
                )
            else:
                rmach = rs.get("machine")
                if isinstance(rmach, dict):
                    rmach = rmach.get("value")
                if rmach and str(rmach).upper() != machine.upper():
                    continue
                sorters.append(
                    make_object(
                        "sorter",
                        str(rname),
                        source_table="Sorters.asc",
                        source_row=str(rname),
                        source_scope=SCOPE_OVERLAY,
                        active_state=ACTIVE_LIKELY,
                        inclusion=INCLUDED,
                        confidence="MEDIUM",
                        provenance=PROV_RUN_DERIVED,
                        evidence=[{"kind": "sorter_research_integrate"}],
                        generation_state=GEN_NOT_SUPPORTED,
                        encoder_io=enc,
                        machine_name=rmach,
                        discovery_only=True,
                        research_ref="exports/sorter-research/subsystem_model.json",
                    ).to_dict()
                )
        # Force generation boundary from research matrix when available
        matrix = load_json(ROOT / "exports" / "sorter-research" / "generation_support_matrix.json")
        if matrix:
            for s in sorters:
                s["generation_state"] = GEN_NOT_SUPPORTED
                s["generation_boundary"] = "sorter_track_plc_generation NOT_SUPPORTED"
    return sorters


def _tracking_wcs(run_dir: Path, machine: str) -> tuple[list[dict], list[dict]]:
    tracking: list[dict] = []
    wcs: list[dict] = []
    if discover_tracking_wcs is None:
        return tracking, wcs
    doc = discover_tracking_wcs(run_dir, machine)
    for t in doc.get("tables") or []:
        if not t.get("active_rows"):
            continue
        tracking.append(
            make_object(
                "tracking",
                t.get("table") or "track",
                source_table=t.get("table") or "",
                source_row=None,
                source_scope=SCOPE_BASE_ONLY,
                active_state=ACTIVE_LIKELY,
                inclusion=AVAILABLE,
                confidence="MEDIUM",
                provenance=PROV_RUN_EXPLICIT,
                evidence=[{"kind": "tracking_table", "active_rows": t.get("active_rows")}],
                generation_state=GEN_NOT_SUPPORTED,
                active_rows=t.get("active_rows"),
                path=t.get("path"),
            ).to_dict()
        )
    for ev in doc.get("wcs_enabled_events") or []:
        wcs.append(
            make_object(
                "wcs",
                ev.get("event") or "wcs_event",
                source_table="WCSEvents.asc",
                source_row=ev.get("event"),
                source_scope=SCOPE_BASE_ONLY,
                active_state=ACTIVE_CONFIRMED,
                inclusion=AVAILABLE,
                confidence="HIGH",
                provenance=PROV_RUN_EXPLICIT,
                evidence=[{"kind": "wcs_enable", "detail": ev}],
                generation_state=GEN_NOT_SUPPORTED,
                destination=ev.get("destination"),
                category=ev.get("category"),
            ).to_dict()
        )
    return tracking, wcs


def _encoders_from_discovery(
    run_dir: Path,
    machine: str,
    sawtooth: dict[str, Any],
    vfd: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if discover_encoders is None:
        return [], []
    doc = discover_encoders(run_dir, machine, sawtooth, vfd or {})
    out: list[dict] = []
    rels: list[dict] = []
    for e in doc.get("encoders") or []:
        name = e.get("encoder") or e.get("name") or ""
        evid = [{"kind": "encoder_link"}]
        for a in e.get("associations") or []:
            evid.append({"kind": a.get("type") or "encoder_association", "detail": a})
            rels.append(
                {
                    "from": name,
                    "to": a.get("to") or a.get("target"),
                    "kind": a.get("type") or "encoder_association",
                    "provenance": a.get("provenance") or PROV_RUN_EXPLICIT,
                }
            )
        out.append(
            make_object(
                "encoder",
                name,
                source_table="Encoders.asc",
                source_row=name,
                source_scope=SCOPE_OVERLAY,
                active_state=ACTIVE_CONFIRMED,
                inclusion=INCLUDED,
                confidence="HIGH",
                provenance=e.get("provenance") or PROV_RUN_EXPLICIT,
                evidence=evid,
                generation_state=GEN_CFG,
                enable=e.get("enable"),
                target_fpm=e.get("target_fpm"),
                associations=e.get("associations") or [],
            ).to_dict()
        )
    return out, rels


def build_subsystems(
    model: SiteModel,
    *,
    saw_raw: dict[str, Any],
    vfd_raw: dict[str, Any] | None,
    semantics: dict[str, Any],
) -> dict[str, Any]:
    saw_section: dict[str, Any] = {
        "present": bool(model.sawtooth_merges),
        "merges": model.sawtooth_merges,
        "counts": {
            "merges": len(model.sawtooth_merges),
            "lanes": sum(len(m.get("lanes") or []) for m in model.sawtooth_merges),
        },
        "config_required": [],
        "sources": (saw_raw or {}).get("sources") or {},
        "semantics": semantics or {},
    }
    for m in model.sawtooth_merges:
        saw_section["config_required"].extend(m.get("config_required") or [])
        for lane in m.get("lanes") or []:
            if not lane.get("conveyor"):
                saw_section["config_required"].append(f"lane {lane.get('name')} missing conveyor")

    # Collect PE/VFD/encoder refs for sawtooth section
    lanes_flat = []
    for m in model.sawtooth_merges:
        for ln in m.get("lanes") or []:
            lanes_flat.append(ln)
    saw_section["lanes"] = lanes_flat
    saw_section["vfds"] = sorted(
        {
            (ln.get("drive") or ln.get("vfd") or "")
            for ln in lanes_flat
            if (ln.get("drive") or ln.get("vfd"))
        }
        | {m.get("motor_io") or "" for m in model.sawtooth_merges if m.get("motor_io")}
    )
    saw_section["photoeyes"] = sorted(
        {ln.get("photoeye") or "" for ln in lanes_flat if ln.get("photoeye")}
    )
    saw_section["encoders"] = [
        e.get("normalized_name") or e.get("raw_name") for e in model.encoders
    ]

    return {
        "generated_at": _ts(),
        "machine": model.machine_scope,
        "transport": {
            "present": bool((model.transport or {}).get("nodes")),
            "node_count": len((model.transport or {}).get("nodes") or []),
            "edge_count": len((model.transport or {}).get("edges") or []),
            "visual_freeze": True,
            "metrics": (model.transport or {}).get("metrics") or {},
        },
        "sawtooth": saw_section,
        "sorter": {
            "present": bool(model.sorters),
            "sorters": model.sorters,
            "generation_state": GEN_NOT_SUPPORTED,
            "note": "Discovery stub only — no sorter PLC generation",
        },
        "tracking_wcs": {
            "tracking_systems": model.tracking_systems,
            "wcs_interfaces": model.wcs_interfaces,
            "generation_state": GEN_NOT_SUPPORTED,
        },
        "vfd_summary": {
            "count": len(model.vfds),
            "bases": [v.get("normalized_name") for v in model.vfds],
            "raw_counts": (vfd_raw or {}).get("counts") if vfd_raw else {},
        },
    }


def discover(
    run_dir: Path,
    machine: str,
    out_dir: Path,
    *,
    overrides_path: Path | None = None,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    fortna = run_dir / "FORTNA"
    if not fortna.is_dir():
        raise FileNotFoundError(fortna)

    model = SiteModel(machine_scope=machine, run_dir=str(run_dir))
    model.controllers = _load_controllers(run_dir, machine)
    model.estop_zones = _load_estop_zones(run_dir, machine)

    saw_raw: dict[str, Any] = {}
    vfd_raw: dict[str, Any] | None = None
    semantics: dict[str, Any] = {}
    has_saw = _has_sawtooth_evidence(run_dir, machine)

    if has_saw:
        merges, saw_rels, saw_raw, semantics = _build_sawtooth(run_dir, machine)
        model.sawtooth_merges = merges
        model.relationships.extend(saw_rels)
        # Table precedence recording for saw tables
        for stem in ("SawMerge.asc", "SawLane.asc", "Encoders.asc", "Sorters.asc"):
            merged = merge_table_rows(fortna, stem, machine)
            model.table_resolutions[stem] = {
                "resolution": merged["resolution"],
                "paths": merged["paths"],
            }
        if discover_vfd is not None:
            vfd_raw = discover_vfd(run_dir, machine, saw_raw)
        enc_objs, enc_rels = _encoders_from_discovery(run_dir, machine, saw_raw, vfd_raw)
        model.encoders = enc_objs
        model.relationships.extend(enc_rels)
    else:
        model.notes.append(
            "No active SawMerge/SawLane evidence for this machine — sawtooth_merges left empty (not faked)"
        )
        for stem in ("SawMerge.asc", "SawLane.asc", "Sorters.asc"):
            merged = merge_table_rows(fortna, stem, machine)
            model.table_resolutions[stem] = {
                "resolution": merged["resolution"],
                "paths": merged["paths"],
                "active_named": sum(
                    1 for r in merged.get("rows") or [] if _clean((r.get("row") or {}).get("Name") or (r.get("row") or {}).get("Sorter Name") or "")
                ),
            }

    equipment, eq_rels, table_res = _equipment_from_cp_discovery(
        run_dir, machine, saw_raw if has_saw else (saw_raw or {})
    )
    # When no sawtooth, still run equipment discovery with empty saw dict
    if not equipment and discover_equipment is not None:
        empty_saw = saw_raw or {
            "merges": [],
            "lanes": [],
            "counts": {"merges": 0, "lanes": 0},
            "sources": {},
        }
        equipment, eq_rels, table_res = _equipment_from_cp_discovery(run_dir, machine, empty_saw)

    model.equipment = equipment
    model.relationships.extend(eq_rels)
    model.table_resolutions.update(table_res)

    owned = {normalize_name(e.get("normalized_name")) for e in model.equipment}
    motors, vfds, photoeyes, dev_rels = _devices_from_conveyor(run_dir, machine, owned)
    # Prefer VFD discovery doc bases when present
    if vfd_raw and isinstance(vfd_raw.get("by_base"), dict) and vfd_raw["by_base"]:
        vfds = []
        for base, info in vfd_raw["by_base"].items():
            evid = [{"kind": "vfd_link"}, {"kind": "controller_io"}]
            for conv in info.get("conveyors") or []:
                evid.append({"kind": "vfd_link", "detail": conv})
                model.relationships.append(
                    {
                        "from": base,
                        "to": conv,
                        "kind": "vfd_to_conveyor",
                        "provenance": PROV_RUN_EXPLICIT,
                    }
                )
            vfds.append(
                make_object(
                    "vfd",
                    base,
                    source_table="Conveyor.asc",
                    source_row=base,
                    source_scope=SCOPE_BASE_ONLY,
                    active_state=ACTIVE_CONFIRMED,
                    inclusion=INCLUDED,
                    confidence="HIGH",
                    provenance=PROV_RUN_EXPLICIT,
                    evidence=evid,
                    generation_state=GEN_CFG,
                    devices=info.get("devices") or info.get("io_names") or [],
                    conveyors=info.get("conveyors") or [],
                ).to_dict()
            )
    model.motors = motors
    model.vfds = vfds
    model.photoeyes = photoeyes
    model.relationships.extend(dev_rels)

    model.transport = _discover_transport(run_dir, machine, owned)
    if not (model.transport.get("nodes") or []) and model.equipment:
        # Fill transport nodes from discovered equipment geometry (still data-only)
        model.transport["nodes"] = [
            {
                "tag": e.get("raw_name") or e.get("normalized_name"),
                "type": e.get("equipment_type"),
                "x": e.get("x"),
                "y": e.get("y"),
                "angle": e.get("angle"),
                "length": e.get("length"),
                "width": e.get("width"),
                "entry": e.get("entry_anchor"),
                "exit": e.get("exit_anchor"),
                "provenance": PROV_RUN_EXPLICIT,
            }
            for e in model.equipment
            if e.get("inclusion") == INCLUDED
        ]
        model.transport["source"] = "site_model_equipment"
        model.transport.setdefault("metrics", {})["scoped_nodes"] = len(model.transport["nodes"])
    model.sorters = _discover_sorters(run_dir, machine)
    tracking, wcs = _tracking_wcs(run_dir, machine)
    model.tracking_systems = tracking
    model.wcs_interfaces = wcs

    # Areas: RUN has no reliable Area table in current archives → default Area_1
    model.areas = []
    ensure_default_area(model)

    overrides = None
    if overrides_path and overrides_path.is_file():
        overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
        if isinstance(overrides, dict):
            overrides = overrides.get("overrides") or overrides.get("items") or []
    apply_engineer_overrides(model, overrides)

    site_dict = model.to_dict()
    activity = classify_site_model(site_dict, machine)
    # sync classified buckets back onto model dict (classify mutates lists in site_dict)
    subsystems = build_subsystems(
        SiteModel(
            machine_scope=machine,
            run_dir=str(run_dir),
            equipment=site_dict.get("equipment") or [],
            transport=site_dict.get("transport") or {},
            motors=site_dict.get("motors") or [],
            vfds=site_dict.get("vfds") or [],
            photoeyes=site_dict.get("photoeyes") or [],
            encoders=site_dict.get("encoders") or [],
            sawtooth_merges=site_dict.get("sawtooth_merges") or [],
            sorters=site_dict.get("sorters") or [],
            tracking_systems=site_dict.get("tracking_systems") or [],
            wcs_interfaces=site_dict.get("wcs_interfaces") or [],
            areas=site_dict.get("areas") or [],
        ),
        saw_raw=saw_raw,
        vfd_raw=vfd_raw,
        semantics=semantics,
    )
    # Refresh counts after classification
    site_dict["counts"] = SiteModel(
        machine_scope=machine,
        run_dir=str(run_dir),
        controllers=site_dict.get("controllers") or [],
        areas=site_dict.get("areas") or [],
        equipment=site_dict.get("equipment") or [],
        transport=site_dict.get("transport") or {},
        motors=site_dict.get("motors") or [],
        vfds=site_dict.get("vfds") or [],
        photoeyes=site_dict.get("photoeyes") or [],
        encoders=site_dict.get("encoders") or [],
        estop_zones=site_dict.get("estop_zones") or [],
        sawtooth_merges=site_dict.get("sawtooth_merges") or [],
        sorters=site_dict.get("sorters") or [],
        tracking_systems=site_dict.get("tracking_systems") or [],
        wcs_interfaces=site_dict.get("wcs_interfaces") or [],
        relationships=site_dict.get("relationships") or [],
        unresolved=site_dict.get("unresolved") or [],
    ).counts()

    prev = load_json(out_dir / "site_model.json")
    report = change_report(prev, site_dict)

    write_json(out_dir / "site_model.json", site_dict)
    write_json(out_dir / "activity_classification.json", activity)
    write_json(out_dir / "subsystems.json", subsystems)
    write_json(out_dir / "change_report.json", report)

    return {
        "out_dir": str(out_dir),
        "counts": site_dict["counts"],
        "activity_counts": activity.get("counts"),
        "change_report_status": report.get("status"),
        "has_sawtooth": has_saw,
    }


def infer_machine_from_run(run_dir: Path) -> str:
    """Read MACHINENAME from project.cfg when --machine is omitted."""
    cfg = Path(run_dir) / "project.cfg"
    if cfg.is_file():
        try:
            text = cfg.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
        for line in text.splitlines():
            if "MACHINENAME" in line.upper():
                parts = line.split("=", 1)
                if len(parts) == 2:
                    name = parts[1].strip().strip('"').strip("'")
                    if name:
                        return name.upper()
    return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RUN-driven canonical SiteModel discovery")
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument(
        "--machine",
        default="",
        help="Controller/machine scope (default: MACHINENAME from project.cfg)",
    )
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--overrides", type=Path, default=None, help="Optional engineer overrides JSON")
    args = ap.parse_args(argv)
    machine = (args.machine or "").strip() or infer_machine_from_run(args.run_dir)
    if not machine:
        print(json.dumps({"ok": False, "error": "machine required (pass --machine or set MACHINENAME in project.cfg)"}))
        return 2
    result = discover(args.run_dir, machine, args.out, overrides_path=args.overrides)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
