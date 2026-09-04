#!/usr/bin/env python3
"""Transport Build graph → Autogen workbook helpers.

Visual graph is the source of truth when prints are weak/missing:
  - Transport *areas* (renameable) → workbook conveyor main_area + area list
  - Simple conveyors → Fast/Slow call sites by area (existing Autogen)
  - Merges → merges_2to1 (Greensboro PLC2 shape); merge owns *discharge* area

Does NOT rewrite sealed AOIs. Apply patches the Autogen workbook only.

Usage:
  python fortna_transport_graph.py --graph path/to/graph.json --out exports/transport-poc
  python fortna_transport_graph.py --graph graph.json --apply-workbook workspace/autogen_workbook.json
  python fortna_transport_graph.py --stdin  < graph.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def _is_conveyor_tag(name: str) -> bool:
    n = (name or "").strip()
    if not re.match(r"^P\d{2,4}[A-Za-z0-9_]*$", n, re.I):
        return False
    if re.search(r"_(AUX|FLT|OK|RUN)$", n, re.I):
        return False
    return True


def _first_pe_on_node(node: dict | None) -> str:
    """Return first photoeye tag attached to a conveyor node, else ''."""
    if not node:
        return ""
    for d in node.get("devices") or []:
        kind = (d.get("kind") or "").lower()
        tag = (d.get("tag") or d.get("name") or "").strip()
        if kind == "photoeye" and tag:
            return tag
        if tag and re.search(r"PE", tag, re.I):
            return tag
    return ""


def _port_sort_key(port: str) -> int:
    m = re.search(r"(\d+)$", port or "")
    return int(m.group(1)) if m else 0


def to_autogen_merges_2to1(result: dict) -> list[dict]:
    """Map graph merges → fortna_autogen merges_2to1 workbook rows (PLC2 shape).

    Gold PLC2 keys: name, area, lane_a, lane_b, discharge, pe_a, pe_b, jam_pe,
    hold_mode=runhold (BOOL RunHold tags). 3:1+ kept with lanes>2 for later.
    """
    rows: list[dict] = []
    for area in result.get("areas") or []:
        area_name = (area.get("name") or "").strip() or "Transport"
        for m in area.get("merges") or []:
            lanes = int(m.get("lanes") or 2)
            discharge = (m.get("discharge") or "").strip()
            inbound = sorted(m.get("inbound") or [], key=lambda ib: _port_sort_key(ib.get("port") or ""))
            # PLC2 convention: port0 ≈ main (lane_a), port1 ≈ induct (lane_b), port2 ≈ lane_c
            lane_a = ""
            lane_b = ""
            lane_c = ""
            pe_a = ""
            pe_b = ""
            pe_c = ""

            def _src_for_inbound(ib: dict) -> dict | None:
                tag = (ib.get("from_tag") or "").strip()
                for n in area.get("nodes") or []:
                    if (n.get("conveyorTag") or "").strip() == tag or n.get("id") == ib.get("from_tag"):
                        return n
                return None

            if inbound:
                lane_a = (inbound[0].get("from_tag") or "").strip()
                pe_a = _first_pe_on_node(_src_for_inbound(inbound[0]))
            if len(inbound) >= 2:
                lane_b = (inbound[1].get("from_tag") or "").strip()
                pe_b = _first_pe_on_node(_src_for_inbound(inbound[1]))
            if len(inbound) >= 3:
                lane_c = (inbound[2].get("from_tag") or "").strip()
                pe_c = _first_pe_on_node(_src_for_inbound(inbound[2]))

            # Merge instance name: prefer discharge (P316 → P316_Merge in autogen)
            name = discharge or (m.get("label") or "Merge").replace(" ", "_")
            if name.lower().endswith("_merge"):
                name = name[: -len("_merge")]

            # Inspector / wizard PE overrides win over auto-from-device
            pe_a = (m.get("pe_a") or "").strip() or pe_a
            pe_b = (m.get("pe_b") or "").strip() or pe_b
            pe_c = (m.get("pe_c") or "").strip() or pe_c
            jam_pe = (m.get("jam_pe") or "").strip()
            # Placeholder area = canvas area; Apply remaps to discharge conveyor area
            row = {
                "name": name,
                "area": area_name,
                "lanes": lanes,
                "lane_a": lane_a,
                "lane_b": lane_b,
                "lane_c": lane_c,
                "discharge": discharge or name,
                "pe_a": pe_a,
                "pe_b": pe_b,
                "pe_c": pe_c,
                "jam_pe": jam_pe,
                "allow_undefined_pe": bool(m.get("allow_undefined_pe")),
                "hold_mode": "runhold",  # Greensboro PLC2 / PLC4 pattern
                "source": "transport_build_graph",
                "suggested_aoi": m.get("suggested_aoi") or ("Merge_2to1" if lanes == 2 else f"Merge_{lanes}to1_config"),
            }
            if lanes > 2:
                # Extra inbound lanes kept for future 3:1 AOI; Autogen emit skips >2 today
                row["extra_lanes"] = [
                    (ib.get("from_tag") or "").strip()
                    for ib in inbound[2:]
                    if (ib.get("from_tag") or "").strip()
                ]
            rows.append(row)
    return rows


def _tag_to_graph_area(graph: dict) -> tuple[dict[str, str], list[str]]:
    """Map P### → Transport Build area name (node placement).

    Returns (map, duplicate_warnings). A tag should live in one area only;
    if repeated, the last area wins and we warn.
    """
    out: dict[str, str] = {}
    dupes: list[str] = []
    for area in graph.get("areas") or []:
        aname = (area.get("name") or "").strip() or "Transport"
        for n in area.get("nodes") or []:
            kind = n.get("kind") or ""
            if not kind.startswith("conv_"):
                continue
            tag = (n.get("conveyorTag") or "").strip()
            if not tag:
                continue
            key = tag.upper()
            if key in out and out[key] != aname:
                dupes.append(f"{tag} in both “{out[key]}” and “{aname}” — using “{aname}”")
            out[key] = aname
    return out, dupes


def _safety_for_area(area_name: str) -> str:
    base = (area_name or "Transport").replace("_Area", "").strip() or "Transport"
    return f"{base}_ESZone1"


def _rebuild_workbook_areas(workbook: dict) -> None:
    """Refresh workbook.areas + options.areas from conveyor main_area values."""
    conveyors = workbook.get("conveyors") or []
    areas: list[dict] = []
    seen: set[str] = set()
    for row in conveyors:
        if row.get("include") is False:
            continue
        name = (row.get("main_area") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        areas.append({
            "name": name,
            "safety_zone": (row.get("safety_zone") or _safety_for_area(name)),
            "conveyor_count": 0,
        })
    for a in areas:
        a["conveyor_count"] = sum(
            1
            for r in conveyors
            if (r.get("main_area") or "") == a["name"] and r.get("include", True)
        )
    workbook["areas"] = areas
    opts = workbook.get("options") if isinstance(workbook.get("options"), dict) else {}
    area_opts = list(opts.get("areas") or [])
    for a in areas:
        if a["name"] not in area_opts:
            area_opts.append(a["name"])
    opts["areas"] = area_opts
    # Safety dropdown
    safety_opts = list(opts.get("safety_zones") or [])
    for a in areas:
        s = a.get("safety_zone") or _safety_for_area(a["name"])
        if s not in safety_opts:
            safety_opts.append(s)
    opts["safety_zones"] = safety_opts
    workbook["options"] = opts


def _stub_conveyor(tag: str, main_area: str) -> dict:
    """Minimal workbook row when graph binds a P### not yet in RUN workbook."""
    return {
        "number": 0,
        "include": True,
        "conveyor": tag,
        "main_area": main_area,
        "safety_zone": _safety_for_area(main_area),
        "type": "Transport with MS",
        "template": "Transport",
        "drive": "MS",
        "exit_pe_tag": "",
        "add_pe_tag": "",
        "jam_pe_tags": [],
        "full_pe_tags": [],
        "product_pe_tags": [],
        "all_pe_tags": [],
        "exit_pe_opt": "",
        "jam_opt": "",
        "full_opt": "",
        "downstream": "",
        "motor_starter": "Yes",
        "espc": "",
        "control_station": "",
        "power_supply": "",
        "source": "transport_build_graph",
        "edited": True,
        "notes": "Created from Transport Build (not in RUN workbook yet)",
        "transport_build": True,
    }


def apply_graph_to_workbook(graph: dict, workbook: dict | None = None) -> dict:
    """Patch Autogen workbook from Transport Build graph.

    - Every bound conveyor (straight / curve / merge discharge) gets
      main_area = the Transport area tab it lives on (renameable).
    - New area names appear in workbook.areas / options.areas.
    - Merges upsert into merges_2to1; merge.area = discharge conveyor's area.
    - Simple transport needs no merge rows — Autogen Fast/Slow follows main_area.
    """
    wb = dict(workbook or {})
    if "conveyors" not in wb or not isinstance(wb.get("conveyors"), list):
        wb["conveyors"] = []
    if "options" not in wb or not isinstance(wb.get("options"), dict):
        wb["options"] = {}

    result = analyze(graph)
    tag_area, dupe_warnings = _tag_to_graph_area(graph)

    by_name: dict[str, dict] = {}
    for row in wb["conveyors"]:
        key = str(row.get("conveyor") or "").strip().upper()
        if key:
            by_name[key] = row

    updated_tags: list[str] = []
    created_tags: list[str] = []
    unbound = 0
    # Wire exit → entrance means destination is downstream of source (Fast_Conv IO_Downstream_Conv)
    downstream_by_tag: dict[str, str] = {}
    for area in graph.get("areas") or []:
        by_id = {n.get("id"): n for n in (area.get("nodes") or []) if n.get("id")}
        for w in area.get("wires") or []:
            src = by_id.get(w.get("from"))
            dst = by_id.get(w.get("to"))
            if not src or not dst:
                continue
            src_tag = (src.get("conveyorTag") or "").strip()
            dst_tag = (dst.get("conveyorTag") or "").strip()
            if src_tag and dst_tag:
                downstream_by_tag[src_tag.upper()] = dst_tag
        for n in area.get("nodes") or []:
            if not str(n.get("kind") or "").startswith("conv_"):
                continue
            if not (n.get("conveyorTag") or "").strip():
                unbound += 1

    def _infer_pe_roles(tag: str) -> list[str]:
        """Fortna suffix defaults: _P → exit+jam, _J → jam, _F → full."""
        u = (tag or "").strip().upper()
        if not u:
            return ["exit"]
        if re.search(r"_F\d*$|_FULL|FULL", u) and "_JF" not in u and "_FDJ" not in u:
            return ["full"]
        if re.search(r"_J\d*$|_JAM|JAM|_JF|_FDJ", u):
            return ["jam"]
        if re.search(r"_P\d*$|_P$|PRODUCT|PRESENT|DISCHARGE", u):
            return ["exit", "jam"]
        return ["exit"]

    def _pes_from_node(node: dict) -> dict:
        """Collect PE device tags on a conveyor node for Autogen PE wiring.

        Prefer engineer-selected device.roles (exit/add/jam/full, multi-select).
        Fall back to Fortna suffix (_P/_J/_F) when roles are missing.
        """
        product: list[str] = []
        jam: list[str] = []
        full: list[str] = []
        add: list[str] = []
        exit_candidates: list[str] = []
        for d in node.get("devices") or []:
            if (d.get("kind") or "").lower() != "photoeye":
                continue
            tag = (d.get("tag") or d.get("name") or "").strip()
            if not tag:
                continue
            raw_roles = d.get("roles")
            if isinstance(raw_roles, list) and raw_roles:
                roles = {
                    str(r).strip().lower()
                    for r in raw_roles
                    if str(r).strip()
                }
            else:
                roles = set(_infer_pe_roles(tag))
            if "exit" in roles:
                exit_candidates.append(tag)
                if tag not in product:
                    product.append(tag)
            if "add" in roles and tag not in add:
                add.append(tag)
            if "jam" in roles and tag not in jam:
                jam.append(tag)
            if "full" in roles and tag not in full:
                full.append(tag)
        # Merge AOI PE fields also count as product placeholders when set
        for k in ("pe_a", "pe_b", "pe_c"):
            t = (node.get(k) or "").strip()
            if t and t not in product:
                product.append(t)
        # Fast_Conv exit prefers explicit exit role; fall back so stubs still wire a PE
        exit_pe = (
            exit_candidates[0]
            if exit_candidates
            else (product[0] if product else (jam[0] if jam else (full[0] if full else "")))
        )
        add_pe = add[0] if add else ""
        return {
            "exit_pe_tag": exit_pe,
            "add_pe_tag": add_pe,
            "product_pe_tags": product,
            "jam_pe_tags": jam,
            "full_pe_tags": full,
            "all_pe_tags": list(dict.fromkeys(product + jam + full + add)),
        }

    def _node_for_tag(tag_u: str) -> dict | None:
        for area in graph.get("areas") or []:
            for n in area.get("nodes") or []:
                if (n.get("conveyorTag") or "").strip().upper() == tag_u:
                    return n
        return None

    for tag_u, aname in sorted(tag_area.items()):
        node = _node_for_tag(tag_u)
        display = ((node.get("conveyorTag") if node else "") or tag_u).strip()
        safety = _safety_for_area(aname)
        pe_fields = _pes_from_node(node or {})
        if tag_u in by_name:
            row = by_name[tag_u]
            row["main_area"] = aname
            row["safety_zone"] = safety
            row["edited"] = True
            row["transport_build"] = True
            if row.get("include") is False:
                row["include"] = True
            # Prefer Transport Build PE attachments when present (union, don't wipe RUN PEs)
            if pe_fields["exit_pe_tag"] and not (row.get("exit_pe_tag") or "").strip():
                row["exit_pe_tag"] = pe_fields["exit_pe_tag"]
            if pe_fields.get("add_pe_tag") and not (row.get("add_pe_tag") or "").strip():
                row["add_pe_tag"] = pe_fields["add_pe_tag"]
            for k in ("product_pe_tags", "jam_pe_tags", "full_pe_tags", "all_pe_tags"):
                if not pe_fields.get(k):
                    continue
                prev = [str(x).strip() for x in (row.get(k) or []) if str(x).strip()]
                row[k] = list(dict.fromkeys(prev + list(pe_fields[k])))
            if pe_fields.get("all_pe_tags"):
                row["all_pe_tags"] = list(
                    dict.fromkeys(
                        list(row.get("product_pe_tags") or [])
                        + list(row.get("jam_pe_tags") or [])
                        + list(row.get("full_pe_tags") or [])
                    )
                )
            # Transport wire graph owns downstream when connected
            if tag_u in downstream_by_tag:
                row["downstream"] = downstream_by_tag[tag_u]
            updated_tags.append(display)
        else:
            stub = _stub_conveyor(display, aname)
            stub.update(pe_fields)
            if tag_u in downstream_by_tag:
                stub["downstream"] = downstream_by_tag[tag_u]
            wb["conveyors"].append(stub)
            by_name[tag_u] = stub
            created_tags.append(display)

    # Renumber stubs / keep order stable
    for i, row in enumerate(wb["conveyors"], start=1):
        row["number"] = i

    _rebuild_workbook_areas(wb)
    # Ensure every Transport Build area name appears even before all P### are bound
    existing_area_names = {
        str(a.get("name") or "").strip()
        for a in (wb.get("areas") or [])
        if a.get("name")
    }
    for area in graph.get("areas") or []:
        aname = (area.get("name") or "").strip()
        if not aname or aname in existing_area_names:
            continue
        wb.setdefault("areas", []).append({
            "name": aname,
            "safety_zone": _safety_for_area(aname),
            "conveyor_count": 0,
        })
        existing_area_names.add(aname)
        opts = wb.get("options") if isinstance(wb.get("options"), dict) else {}
        area_opts = list(opts.get("areas") or [])
        if aname not in area_opts:
            area_opts.append(aname)
        opts["areas"] = area_opts
        wb["options"] = opts

    # Buildable PE names from workbook (same set Autogen will emit)
    buildable_pe: set[str] = set()
    for p in (wb.get("options") or {}).get("exit_pe") or []:
        if p:
            buildable_pe.add(str(p).strip().upper())
    for row in wb.get("conveyors") or []:
        for key in ("exit_pe_tag",):
            if row.get(key):
                buildable_pe.add(str(row[key]).strip().upper())
        for key in ("jam_pe_tags", "product_pe_tags", "full_pe_tags", "all_pe_tags", "exit_pe_choices"):
            for p in row.get(key) or []:
                if p:
                    buildable_pe.add(str(p).strip().upper())
    for row in wb.get("io_points") or wb.get("io") or []:
        dt = str(row.get("device_type") or "").lower()
        name = str(row.get("device") or row.get("device_name") or row.get("fortna_name") or "").strip()
        if name and ("photo" in dt or "pe" == dt or re.search(r"PE", name, re.I)):
            buildable_pe.add(name.upper())

    # Merges: ownership = discharge conveyor area (PLC2-like)
    incoming = result.get("merges_2to1") or []
    for m in incoming:
        d = (m.get("discharge") or m.get("name") or "").strip().upper()
        if d and d in tag_area:
            m["area"] = tag_area[d]
        elif d and d in by_name:
            m["area"] = (by_name[d].get("main_area") or m.get("area") or "").strip()
        # Drop PE refs that won't exist unless override says create them
        if not m.get("allow_undefined_pe"):
            for pk in ("pe_a", "pe_b", "pe_c", "jam_pe"):
                raw = (m.get(pk) or "").strip()
                if raw and raw.upper() not in buildable_pe and raw.upper() != "NO_PE":
                    m[pk] = ""  # → NO_PE at emit

    existing = list(wb.get("merges_2to1") or [])
    by_key: dict[str, dict] = {}
    no_key: list[dict] = []
    for m in existing:
        key = str(m.get("name") or m.get("discharge") or "").strip().upper()
        if key:
            by_key[key] = dict(m)
        else:
            no_key.append(dict(m))

    applied_merges: list[dict] = []
    for raw in incoming:
        row = dict(raw)
        key = str(row.get("name") or row.get("discharge") or "").strip().upper()
        if key and key in by_key:
            by_key[key].update(row)
            applied_merges.append(by_key[key])
        elif key:
            by_key[key] = row
            applied_merges.append(row)
        else:
            no_key.append(row)
            applied_merges.append(row)

    incoming_keys = {
        str(m.get("name") or m.get("discharge") or "").strip().upper()
        for m in incoming
        if str(m.get("name") or m.get("discharge") or "").strip()
    }
    # Drop Transport merges whose discharge/lanes were cleared (no longer bound)
    final_merges: list[dict] = []
    merges_removed: list[str] = []
    for m in [*by_key.values(), *no_key]:
        key = str(m.get("name") or m.get("discharge") or "").strip().upper()
        src = str(m.get("source") or "")
        if src == "transport_build_graph":
            if key not in incoming_keys:
                if key:
                    merges_removed.append(key)
                continue
            discharge = str(m.get("discharge") or key).strip().upper()
            if discharge and discharge not in tag_area:
                merges_removed.append(key or discharge)
                continue
        final_merges.append(m)
    wb["merges_2to1"] = final_merges

    # Prefer graph area names first (what the engineer just defined), then leftovers
    graph_area_names = []
    seen_ga: set[str] = set()
    for area in graph.get("areas") or []:
        n = (area.get("name") or "").strip()
        if n and n not in seen_ga:
            seen_ga.add(n)
            graph_area_names.append(n)
    graph_area_set = set(graph_area_names) | set(tag_area.values())

    def _default_main_area() -> str:
        counts: dict[str, int] = {}
        for r in wb.get("conveyors") or []:
            a = (r.get("main_area") or "").strip()
            if not a or a in graph_area_set:
                continue
            if r.get("transport_build") or r.get("source") == "transport_build_graph":
                continue
            counts[a] = counts.get(a, 0) + 1
        if counts:
            return max(counts, key=counts.get)
        for a in wb.get("areas") or []:
            name = (a.get("name") if isinstance(a, dict) else str(a)).strip()
            if name and name not in graph_area_set:
                return name
        return "MSCRENOSHIP_Area"

    default_area = _default_main_area()
    default_safety = _safety_for_area(default_area)
    removed_tags: list[str] = []
    restored_tags: list[str] = []
    kept_rows: list[dict] = []
    for row in wb.get("conveyors") or []:
        key = str(row.get("conveyor") or "").strip().upper()
        display = str(row.get("conveyor") or "").strip()
        if key and key in tag_area:
            kept_rows.append(row)
            continue
        is_stub = (
            row.get("source") == "transport_build_graph"
            or (row.get("transport_build") and row.get("source") != "run")
        )
        was_transport = bool(
            row.get("transport_build")
            or row.get("source") == "transport_build_graph"
            or (row.get("main_area") or "").strip() in graph_area_set
        )
        if not was_transport:
            kept_rows.append(row)
            continue
        # Cleared / unbound: stubs leave the workbook; RUN rows return to site area
        if is_stub and row.get("source") == "transport_build_graph":
            removed_tags.append(display or key)
            continue
        row["main_area"] = default_area
        row["safety_zone"] = default_safety
        row["transport_build"] = False
        if row.get("source") == "transport_build_graph":
            row["source"] = "run"
        restored_tags.append(display or key)
        kept_rows.append(row)

    wb["conveyors"] = kept_rows
    for i, row in enumerate(wb["conveyors"], start=1):
        row["number"] = i
    _rebuild_workbook_areas(wb)

    area_names = [a.get("name") for a in (wb.get("areas") or []) if a.get("name")]
    return {
        "ok": True,
        "workbook": wb,
        "analysis": result,
        "areas_applied": area_names,
        "graph_areas": graph_area_names,
        "conveyors_updated": updated_tags,
        "conveyors_created": created_tags,
        "conveyors_removed": removed_tags,
        "conveyors_restored": restored_tags,
        "merges_applied": applied_merges,
        "merges_removed": merges_removed,
        "merges_total": len(wb["merges_2to1"]),
        "unbound_nodes": unbound,
        "duplicate_tag_warnings": dupe_warnings,
        "summary": (
            f"{len(graph_area_names)} Transport area(s) → "
            f"{len(updated_tags)} conveyor update(s), "
            f"{len(created_tags)} new row(s), "
            f"{len(removed_tags)} removed, "
            f"{len(applied_merges)} merge(s)"
        ),
        "note": (
            "Simple transport uses Fast/Slow by main_area (no merge required). "
            "Clear a P### tag and Apply to drop that conveyor from the Transport area L5X. "
            "Merges need Program pack · Merge ON; merge owns discharge area."
        ),
    }


def analyze(graph: dict) -> dict:
    areas_out = []
    totals = {
        "areas": 0,
        "nodes": 0,
        "wires": 0,
        "merges": 0,
        "devices": 0,
        "unbound_conveyors": 0,
        "untagged_devices": 0,
        "issues": [],
    }

    for area in graph.get("areas") or []:
        nodes = area.get("nodes") or []
        wires = area.get("wires") or []
        by_id = {n.get("id"): n for n in nodes if n.get("id")}
        merges = []
        convs = []
        for n in nodes:
            kind = n.get("kind") or ""
            if kind.startswith("conv_"):
                convs.append(n)
                totals["nodes"] += 1
                tag = (n.get("conveyorTag") or "").strip()
                if not tag:
                    totals["unbound_conveyors"] += 1
                    totals["issues"].append(
                        f"{area.get('name')}: node {n.get('label') or n.get('id')} has no P### tag"
                    )
                elif not _is_conveyor_tag(tag):
                    totals["issues"].append(
                        f"{area.get('name')}: {tag!r} is not a P### conveyor tag"
                    )
                if kind == "conv_merge":
                    totals["merges"] += 1
                    merges.append({
                        "id": n.get("id"),
                        "label": n.get("label"),
                        "lanes": int(n.get("inPorts") or 2),
                        "discharge": tag or None,
                        "rotation": int(n.get("rotation") or 0),
                        "pe_a": (n.get("pe_a") or "").strip(),
                        "pe_b": (n.get("pe_b") or "").strip(),
                        "pe_c": (n.get("pe_c") or "").strip(),
                        "jam_pe": (n.get("jam_pe") or "").strip(),
                        "allow_undefined_pe": bool(n.get("allow_undefined_pe")),
                    })
            for d in n.get("devices") or []:
                totals["devices"] += 1
                if not (d.get("tag") or d.get("name")):
                    totals["untagged_devices"] += 1

        # Wire integrity
        for w in wires:
            totals["wires"] += 1
            if w.get("from") not in by_id or w.get("to") not in by_id:
                totals["issues"].append(
                    f"{area.get('name')}: dangling wire {w.get('id')}"
                )

        # Suggested merge AOI shape (gold Merge_2to1 when lanes==2)
        merge_plan = []
        for m in merges:
            lanes = m["lanes"]
            aoi = "Merge_2to1" if lanes == 2 else f"Merge_{lanes}to1_config"
            inbound = []
            for w in wires:
                if w.get("to") == m["id"]:
                    src = by_id.get(w.get("from")) or {}
                    inbound.append({
                        "port": w.get("toPort") or "in",
                        "from_tag": (src.get("conveyorTag") or src.get("label") or src.get("id")),
                    })
            merge_plan.append({
                **m,
                "suggested_aoi": aoi,
                "inbound": inbound,
                "note": (
                    "Use gold Merge_2to1 + Area_L2 ST presets when lanes=2; "
                    "3:1 stays config-only until AOI pack is confirmed."
                    if lanes >= 3
                    else "Maps to existing fortna_autogen merges_2to1 workbook shape."
                ),
            })

        areas_out.append({
            "id": area.get("id"),
            "name": area.get("name"),
            "conveyor_count": len(convs),
            "wire_count": len(wires),
            "merges": merge_plan,
            "nodes": [
                {
                    "id": n.get("id"),
                    "kind": n.get("kind"),
                    "label": n.get("label"),
                    "conveyorTag": n.get("conveyorTag") or "",
                    "rotation": int(n.get("rotation") or 0),
                    "inPorts": n.get("inPorts"),
                    "motorCount": n.get("motorCount"),
                    "motors": [
                        str(t).strip()
                        for t in (n.get("motors") or [])
                        if str(t).strip()
                    ]
                    if (n.get("kind") or "") == "conv_spiral"
                    else [],
                    "devices": [
                        {
                            "kind": d.get("kind"),
                            "tag": d.get("tag") or d.get("name") or "",
                        }
                        for d in (n.get("devices") or [])
                    ],
                }
                for n in convs
            ],
            "wires": [
                {
                    "from": w.get("from"),
                    "to": w.get("to"),
                    "toPort": w.get("toPort") or "in",
                }
                for w in wires
            ],
        })
        totals["areas"] += 1

    merges_2to1 = to_autogen_merges_2to1({"areas": areas_out})
    return {
        "ok": True,
        "poc": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": totals,
        "areas": areas_out,
        "merges_2to1": merges_2to1,
        "next_steps": [
            "Bind every conveyor node to a P### tag from the RUN.",
            "Tag motors as M### / VFD### only; ENC* for encoders; PE*/EZPE* for eyes.",
            "2:1 merges → Autogen merges_2to1 (PLC2 runhold). Import fragment into PLC Autogen workbook.",
            "Keep sealed Fast_Conv / Slow_* / Merge_2to1 AOIs; only wire call sites.",
            "Full L5X emit from this graph is Phase 2b (IO map + transport focus).",
        ],
    }


def write_report(result: dict, out_dir: Path) -> tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = out_dir / f"transport_graph_poc_{stamp}.json"
    md_path = out_dir / f"transport_graph_poc_{stamp}.md"
    merges_path = out_dir / f"transport_autogen_merges_{stamp}.json"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    merges_fragment = {
        "source": "transport_build_graph",
        "gold_pattern": "Greensboro PLC2 Merge_2to1 + Area_L2 ST presets",
        "generated_at": result.get("generated_at"),
        "merges_2to1": result.get("merges_2to1") or [],
        "note": (
            "Drop/merge this list into the Site Forge Autogen workbook "
            "(inp.merges_2to1). AOIs stay sealed — call-site wiring only."
        ),
    }
    merges_path.write_text(json.dumps(merges_fragment, indent=2), encoding="utf-8")

    t = result["totals"]
    lines = [
        f"# Transport Build POC report ({result['generated_at']})",
        "",
        f"- Areas: **{t['areas']}**",
        f"- Conveyor nodes: **{t['nodes']}**",
        f"- Merges: **{t['merges']}**",
        f"- Wires: **{t['wires']}**",
        f"- Devices: **{t['devices']}**",
        f"- Unbound conveyors: **{t['unbound_conveyors']}**",
        f"- Untagged devices: **{t['untagged_devices']}**",
        f"- Autogen merges_2to1 rows: **{len(result.get('merges_2to1') or [])}**",
        "",
        "## Issues",
    ]
    if t["issues"]:
        lines.extend(f"- {i}" for i in t["issues"])
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Areas")
    for a in result["areas"]:
        lines.append(f"### {a.get('name')}")
        lines.append(f"- Conveyors: {a['conveyor_count']}, wires: {a['wire_count']}")
        for m in a.get("merges") or []:
            lines.append(
                f"- Merge **{m.get('label')}** lanes={m.get('lanes')} "
                f"AOI=`{m.get('suggested_aoi')}` discharge=`{m.get('discharge')}`"
            )
            for ib in m.get("inbound") or []:
                lines.append(f"  - {ib.get('port')}: `{ib.get('from_tag')}`")
        lines.append("")
    lines.append("## Autogen merges_2to1 (PLC2 shape)")
    for row in result.get("merges_2to1") or []:
        lines.append(
            f"- `{row.get('name')}` area=`{row.get('area')}` "
            f"lanes={row.get('lanes')} "
            f"{row.get('lane_a')} + {row.get('lane_b')} → {row.get('discharge')} "
            f"hold=`{row.get('hold_mode')}`"
        )
    if not (result.get("merges_2to1") or []):
        lines.append("- (none yet — drop a Merge and wire two entrances)")
    lines.append("")
    lines.append(f"Fragment file: `{merges_path.name}`")
    lines.append("")
    lines.append("## Next steps")
    lines.extend(f"1. {s}" for s in result.get("next_steps") or [])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path, merges_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", type=Path, help="Path to Transport Build Export JSON")
    ap.add_argument("--stdin", action="store_true", help="Read graph JSON from stdin")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("exports/transport-poc"),
        help="Output directory for report files",
    )
    ap.add_argument(
        "--apply-workbook",
        type=Path,
        help="Patch this Autogen workbook JSON with graph areas + merges (writes in place)",
    )
    args = ap.parse_args(argv)

    if args.stdin:
        graph = json.load(sys.stdin)
    elif args.graph:
        graph = json.loads(args.graph.read_text(encoding="utf-8-sig"))
    else:
        ap.error("Provide --graph or --stdin")

    # Apply path: areas + simple transport main_area + merges → workbook
    if args.apply_workbook:
        wb_path = args.apply_workbook
        existing = None
        if wb_path.is_file():
            try:
                existing = json.loads(wb_path.read_text(encoding="utf-8-sig"))
            except Exception:
                existing = None
        applied = apply_graph_to_workbook(graph, existing)
        wb_path.parent.mkdir(parents=True, exist_ok=True)
        wb_path.write_text(json.dumps(applied["workbook"], indent=2), encoding="utf-8")
        # Still write POC report alongside when --out given
        result = applied.get("analysis") or analyze(graph)
        json_path, md_path, merges_path = write_report(result, args.out)
        print(
            json.dumps(
                {
                    "ok": True,
                    "summary": applied["summary"],
                    "workbook_path": str(wb_path),
                    "areas_applied": applied["areas_applied"],
                    "graph_areas": applied.get("graph_areas") or [],
                    "conveyors_updated": applied["conveyors_updated"],
                    "conveyors_created": applied["conveyors_created"],
                    "conveyors_removed": applied.get("conveyors_removed") or [],
                    "conveyors_restored": applied.get("conveyors_restored") or [],
                    "merges_applied_count": len(applied["merges_applied"]),
                    "merges_removed": applied.get("merges_removed") or [],
                    "merges_total": applied["merges_total"],
                    "merges_2to1": applied["workbook"].get("merges_2to1") or [],
                    "unbound_nodes": applied["unbound_nodes"],
                    "duplicate_tag_warnings": applied.get("duplicate_tag_warnings") or [],
                    "report_path": str(md_path),
                    "json_path": str(json_path),
                    "autogen_merges_path": str(merges_path),
                    "note": applied["note"],
                }
            )
        )
        return 0

    result = analyze(graph)
    json_path, md_path, merges_path = write_report(result, args.out)
    n_merges = len(result.get("merges_2to1") or [])
    summary = (
        f"{result['totals']['areas']} areas, "
        f"{result['totals']['nodes']} conveyors, "
        f"{result['totals']['merges']} merges → {n_merges} Autogen rows, "
        f"{len(result['totals']['issues'] or [])} issues"
    )
    print(
        json.dumps(
            {
                "ok": True,
                "summary": summary,
                "report_path": str(md_path),
                "json_path": str(json_path),
                "autogen_merges_path": str(merges_path),
                "merges_2to1_count": n_merges,
                "totals": result["totals"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
