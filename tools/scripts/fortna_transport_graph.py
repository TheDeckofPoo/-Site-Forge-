#!/usr/bin/env python3
"""Transport Build graph POC — validate / summarize Node-RED style JSON.

Does NOT emit a full Studio L5X yet. Produces a markdown + JSON report that
maps conveyors, devices, wires, and merges so we can wire fortna_autogen later.

Also emits an Autogen-ready fragment (`merges_2to1`) shaped like Greensboro PLC2
call sites (lane_a / lane_b / discharge / hold_mode=runhold). Sealed AOIs stay
untouched — this only feeds call-site wiring into fortna_autogen.

Usage:
  python fortna_transport_graph.py --graph path/to/graph.json --out exports/transport-poc
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
            # PLC2 convention: port0 ≈ main (lane_a), port1 ≈ induct (lane_b)
            lane_a = ""
            lane_b = ""
            pe_a = ""
            pe_b = ""
            if inbound:
                lane_a = (inbound[0].get("from_tag") or "").strip()
                src0 = None
                # Prefer resolving PE from the source conveyor node via wire port
                for n in area.get("nodes") or []:
                    if (n.get("conveyorTag") or "").strip() == lane_a or n.get("id") == inbound[0].get("from_tag"):
                        src0 = n
                        break
                pe_a = _first_pe_on_node(src0)
            if len(inbound) >= 2:
                lane_b = (inbound[1].get("from_tag") or "").strip()
                src1 = None
                for n in area.get("nodes") or []:
                    if (n.get("conveyorTag") or "").strip() == lane_b or n.get("id") == inbound[1].get("from_tag"):
                        src1 = n
                        break
                pe_b = _first_pe_on_node(src1)

            # Merge instance name: prefer discharge (P316 → P316_Merge in autogen)
            name = discharge or (m.get("label") or "Merge").replace(" ", "_")
            if name.lower().endswith("_merge"):
                name = name[: -len("_merge")]

            row = {
                "name": name,
                "area": area_name,
                "lanes": lanes,
                "lane_a": lane_a,
                "lane_b": lane_b,
                "discharge": discharge or name,
                "pe_a": pe_a,
                "pe_b": pe_b,
                "jam_pe": "",
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
    args = ap.parse_args(argv)

    if args.stdin:
        graph = json.load(sys.stdin)
    elif args.graph:
        graph = json.loads(args.graph.read_text(encoding="utf-8-sig"))
    else:
        ap.error("Provide --graph or --stdin")

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
