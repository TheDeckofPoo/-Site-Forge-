#!/usr/bin/env python3
"""PLC2 RUN-only topology accounting + blind merge enumeration.

Freeze BEFORE comparing finished PLCs.
No invented connections. Unknown stays unresolved.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402
from fortna_run_physical_layout import build_transport_graph  # noqa: E402


def _rows(run: Path, table: str) -> list[dict]:
    fortna = run / "FORTNA"
    for cand in (fortna / f"{table}.asc", fortna / table):
        if cand.is_file():
            try:
                _, rows = read_asc(cand)
                return list(rows or [])
            except Exception:
                return []
    # Some tables use Machine suffix
    for p in fortna.glob(f"{table}.asc*"):
        try:
            _, rows = read_asc(p)
            return list(rows or [])
        except Exception:
            continue
    return []


def main() -> int:
    run = ROOT / "workspace/_plc2_run_peek/RUN"
    machine = "ORNCCP2"
    if not (run / "project.cfg").is_file():
        print("MISSING PLC2 RUN", run)
        return 1

    g = build_transport_graph(run, machine)
    metrics = g.get("metrics") or {}
    area = (g.get("areas") or [{}])[0]
    nodes = area.get("nodes") or []
    wires = area.get("wires") or []

    total = len(nodes)
    ext = [n for n in nodes if n.get("externalReference") or n.get("scopeClass") == "EXTERNAL_REFERENCE"]
    local = [n for n in nodes if n not in ext]

    # Component classification from metrics
    comps = metrics.get("component_summary") or []
    connected_ids = set()
    for w in wires:
        connected_ids.add(w.get("from"))
        connected_ids.add(w.get("to"))
    for n in nodes:
        ds = str(n.get("downstream") or "").strip()
        if ds:
            connected_ids.add(n.get("id"))

    connected = [n for n in local if n.get("id") in connected_ids]
    unresolved = [
        n
        for n in local
        if n.get("id") not in connected_ids and not (n.get("downstream") or "").strip()
    ]

    # Merge-resolved: nodes that participate in a merge (asMerge or inbound count>=2)
    merge_nodes = [n for n in nodes if n.get("asMerge") or n.get("mergeDetected")]

    print("=" * 70)
    print("TOPOLOGY ACCOUNTING (PLC2 RUN)")
    print("=" * 70)
    print(f"TOTAL RUN CONVEYORS:     {total}")
    print(f"CONNECTED (wired/ds):    {len(connected)}")
    print(f"EXTERNAL REFERENCE:      {len(ext)}")
    print(f"MERGE-RESOLVED (nodes):  {len(merge_nodes)}")
    print(f"UNRESOLVED TOPOLOGY:     {len(unresolved)}")
    print(
        f"CHECKSUM ok={total == len(connected) + len(ext) + len([n for n in unresolved if n not in ext]) + len([n for n in local if n not in connected and n not in unresolved])}"
    )
    # Cleaner identity partition for local:
    local_connected = len([n for n in local if n.get("id") in connected_ids])
    local_unresolved = len(local) - local_connected
    print(f"LOCAL connected={local_connected} unresolved={local_unresolved} ext={len(ext)}")
    print(f"IDENTITY: TOTAL={total} = LOCAL({len(local)})+EXT({len(ext)}) = {len(local)+len(ext)}")
    print(f"CONNECTED COMPONENTS: {metrics.get('connected_components')} PRIMARY={metrics.get('primary_component_size')} ISLANDS={metrics.get('island_components')}")

    print("\n--- EXTERNAL REFERENCE sample ---")
    for n in ext[:12]:
        print(f"  {n.get('conveyorTag')} scope={n.get('scopeClass')} ds={n.get('downstream')!r}")

    print("\n--- UNRESOLVED LOCAL (no wire, no downstream) ---")
    for n in unresolved[:20]:
        amb = n.get("ambiguousInbound") or []
        print(
            f"  {n.get('conveyorTag')} type={n.get('equipmentType')} "
            f"amb={[(a.get('from'), a.get('distance'), a.get('classification')) for a in amb[:2]]}"
        )

    # Focus P226 and nearby islands
    print("\n--- FOCUS ISLANDS (P226 and singletons with CURVE/nearby) ---")
    for tag in ("P226", "P222", "P229", "P215", "P408"):
        n = next((x for x in nodes if x.get("conveyorTag") == tag), None)
        if not n:
            print(f"  {tag}: NOT IN GRAPH")
            continue
        print(
            f"  {tag}: type={n.get('equipmentType')} kind={n.get('kind')} "
            f"scope={n.get('scopeClass')} ext={n.get('externalReference')} "
            f"ds={n.get('downstream')!r} wired={n.get('id') in connected_ids} "
            f"amb={n.get('ambiguousInbound')}"
        )

    # Blind merge tables
    print("\n" + "=" * 70)
    print("BLIND MERGE ENUMERATION (PLC2 RUN ONLY)")
    print("=" * 70)
    tables = [
        "MergeBoss",
        "MergeInputs",
        "MergeNotBusy",
        "MergeRoute",
        "MergeRunOutputs",
        "MergeStopOutputs",
        "Merges",
        "SimpleMerge",
        "ZipperMerge",
        "Mtrchain",
    ]
    table_rows = {t: _rows(run, t) for t in tables}
    for t, rows in table_rows.items():
        print(f"  {t}: {len(rows)} rows")

    boss = table_rows.get("MergeBoss") or []
    inputs = table_rows.get("MergeInputs") or []
    # Index inputs by merge id if possible
    def _key(r: dict, *names: str) -> str:
        for n in names:
            v = r.get(n)
            if v is not None and str(v).strip():
                return str(v).strip()
        return ""

    inputs_by_merge: dict[str, list[dict]] = defaultdict(list)
    for r in inputs:
        mid = _key(r, "Merge", "Merge_Name", "Name", "Boss", "MergeBoss")
        if mid:
            inputs_by_merge[mid.upper()].append(r)

    print(f"\nMergeBoss entities: {len(boss)}")
    report_rows = []
    for i, r in enumerate(boss):
        mid = _key(r, "Name", "Merge", "Merge_Name", "ID") or f"BOSS_{i}"
        lane1 = _key(r, "Lane1", "Lane_1", "Input1", "In1", "Conv1")
        lane2 = _key(r, "Lane2", "Lane_2", "Input2", "In2", "Conv2")
        out = _key(r, "Output", "Out", "Discharge", "Section", "ConvOut")
        area = _key(r, "Area", "Main_Area")
        pe = _key(r, "PE", "Photoeye", "JamPE")
        insp = inputs_by_merge.get(mid.upper()) or []
        if not lane1 and len(insp) >= 1:
            lane1 = _key(insp[0], "Conveyor", "Conv", "Name", "Lane")
        if not lane2 and len(insp) >= 2:
            lane2 = _key(insp[1], "Conveyor", "Conv", "Name", "Lane")
        unresolved = []
        if not lane1:
            unresolved.append("lane1")
        if not lane2:
            unresolved.append("lane2")
        if not out:
            unresolved.append("output")
        classification = "CANDIDATE"
        if lane1 and lane2 and out:
            classification = "PROVEN_STRUCTURE"
        elif lane1 or lane2:
            classification = "PARTIAL"
        else:
            classification = "UNRESOLVED"
        row = {
            "merge_id": mid,
            "lane1": lane1,
            "lane2": lane2,
            "output": out,
            "area": area,
            "pe": pe,
            "input_rows": len(insp),
            "classification": classification,
            "unresolved": unresolved,
            "raw_keys": sorted({k for k in r.keys() if k}),
        }
        report_rows.append(row)
        print(
            f"  [{classification}] {mid}: L1={lane1 or '—'} L2={lane2 or '—'} "
            f"OUT={out or '—'} unresolved={unresolved or '—'}"
        )

    out_dir = ROOT / "exports/plc2-merge-discovery"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "machine": machine,
        "topology": {
            "total": total,
            "local": len(local),
            "connected_local": local_connected,
            "unresolved_local": local_unresolved,
            "external_reference": len(ext),
            "merge_nodes": len(merge_nodes),
            "connected_components": metrics.get("connected_components"),
            "primary_component_size": metrics.get("primary_component_size"),
            "island_components": metrics.get("island_components"),
            "component_summary": comps,
            "external_tags": [n.get("conveyorTag") for n in ext if isinstance(n, dict)],
            "unresolved_tags": [
                n.get("conveyorTag") for n in unresolved if isinstance(n, dict)
            ],
        },
        "merge_tables": {t: len(rows) for t, rows in table_rows.items()},
        "merge_boss": report_rows,
    }
    (out_dir / "BLIND_TOPOLOGY_MERGE_ACCOUNTING.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print("\nWrote", out_dir / "BLIND_TOPOLOGY_MERGE_ACCOUNTING.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
