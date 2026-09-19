#!/usr/bin/env python3
"""Audit generic Sawtooth_Merge_Program.L5X — routine graph + control-model evidence.

Inputs (allowed):
  - tools/libraries/programs/Sawtooth_Merge_Program.L5X
  - optional RUN tables for cross-evidence notes

Does NOT read finished PLC4. Does NOT mutate the L5X.
"""
from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACK = ROOT / "tools" / "libraries" / "programs" / "Sawtooth_Merge_Program.L5X"
DEFAULT_OUT = ROOT / "exports" / "cp4-semantics"

ROUTINE_PURPOSE: dict[str, str] = {
    "Main_Routine": "Program entry; schedules Conv_* and gated tracking/reservation JSRs",
    "Conv_PE": "Photoeye / conveyor PE processing (RLL; pack may be empty stub)",
    "Conv_Enc": "Encoder processing (RLL; pack may be empty stub)",
    "Conv_Fast": "Fast-task conveyor processing (RLL; pack may be empty stub)",
    "RT_DeltaDist_NoGapStore": "Collector delta-distance tracking without gap-store belts",
    "RT_IO_Map_NoGapStore": "IO mapping for no-gap-store collector path",
    "RT_CollTrackMain": "Collector tracking main; inits hist/PE cal/lane merge capture/resv/lane control",
    "RT_CollTrackInit": "Initialize collector tracking structures",
    "RT_CollResetCounts": "Reset collector tracking counters",
    "RT_CollTrackHist": "Collector tracking history maintenance",
    "RT_CollPeTrackCal": "Collision / collector PE track calibration",
    "RT_CollLaneMergeCapture": "Capture lane-to-collector merge point offsets",
    "RT_LaneOffsetFind": "Find / apply lane PE offsets on collector",
    "RT_CollTrackResvMngr": "Reservation manager — search/reserve/clear/check slots at merge point",
    "SR_CollTrackSrchSlot": "Search free reservation slot on collector",
    "SR_CollTrackRsrvSlot": "Reserve a collector slot for a lane",
    "SR_CollTrackClrSlot": "Clear a reserved collector slot",
    "SR_CollTrackSlotAtMrgPnt": "Evaluate slot arriving at merge point",
    "SR_CollTrackChkSlot": "Validate reserved slot still valid",
    "SR_LaneCntrl": "Per-lane release / hold / slug-build control state machine",
}

# Observed lane-control modes / RUN SawState vocabulary (library uses diLaneMode ints).
LANE_MODE_NOTES = {
    0: "Idle / inactive (library default zero)",
    1: "Mode 1 observed in library comments/data — confirm vs SR_LaneCntrl",
    2: "Mode 2 heavily present in pack tag seed data (active/tracking-ish)",
}

RUN_SAW_STATES = ["ERROR", "IDLE", "HOLDING", "WAITING", "RELEASING", "HANGING"]
HS_SAW_STATES = [
    "Stopped",
    "Wait PE On",
    "Wait Resrv",
    "Feed Slow",
    "Feed Fast",
    "Wait PE Off Slow",
    "Wait PE Off Fast",
]

TAG_REF_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\b")
JSR_RE = re.compile(r"JSR\(\s*([A-Za-z_][A-Za-z0-9_]*)", re.I)
TIMER_RE = re.compile(r"\b(tm[A-Za-z0-9_]+|TON|TOF|RTO|CTU|CTD)\b", re.I)
AOI_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\(", re.I)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def parse_program_l5x(path: Path) -> dict[str, Any]:
    """Parse Sawtooth program L5X into tags + routines + raw logic text."""
    # ElementTree on full file; CDATA preserved as text.
    tree = ET.parse(path)
    root = tree.getroot()

    tags: list[dict[str, Any]] = []
    for el in root.iter():
        if _local(el.tag) != "Tag":
            continue
        name = el.attrib.get("Name")
        if not name:
            continue
        tags.append(
            {
                "name": name,
                "datatype": el.attrib.get("DataType") or "",
                "tag_type": el.attrib.get("TagType") or "",
                "dimensions": el.attrib.get("Dimensions") or "",
                "usage": el.attrib.get("Usage") or "",
                "radix": el.attrib.get("Radix") or "",
                "external_access": el.attrib.get("ExternalAccess") or "",
                "constant": el.attrib.get("Constant") or "",
            }
        )

    routines: dict[str, dict[str, Any]] = {}
    for el in root.iter():
        if _local(el.tag) != "Routine":
            continue
        name = el.attrib.get("Name")
        if not name:
            continue
        rtype = el.attrib.get("Type") or ""
        logic_chunks: list[str] = []
        # RLL rungs
        for rung in el.iter():
            if _local(rung.tag) == "Text" and rung.text:
                logic_chunks.append(rung.text.strip())
            elif _local(rung.tag) == "STContent" and rung.text:
                logic_chunks.append(rung.text.strip())
        # Some exports put ST in CDATA under Line
        for line in el.iter():
            if _local(line.tag) == "Line" and line.text:
                logic_chunks.append(line.text.strip())
        # Fallback: any Direct descendant CDATA-ish text already captured;
        # also gather comment descriptions
        comments: list[str] = []
        for c in el.iter():
            if _local(c.tag) in {"Description", "Comment"} and (c.text or "").strip():
                comments.append(c.text.strip())
        routines[name] = {
            "name": name,
            "type": rtype,
            "logic_text": "\n".join(logic_chunks),
            "comments": comments[:40],
            "rung_or_line_count": len(logic_chunks),
        }

    program_name = None
    main_routine = None
    for el in root.iter():
        if _local(el.tag) == "Program":
            program_name = el.attrib.get("Name")
            main_routine = el.attrib.get("MainRoutineName")
            break

    return {
        "path": str(path),
        "program_name": program_name,
        "main_routine": main_routine,
        "tags": tags,
        "routines": routines,
    }


def _extract_calls(logic: str) -> list[str]:
    return sorted(set(JSR_RE.findall(logic or "")))


def _tag_names(tags: list[dict[str, Any]]) -> set[str]:
    return {t["name"] for t in tags}


def _refs_in_logic(logic: str, known_tags: set[str]) -> tuple[set[str], set[str]]:
    """Return (reads_approx, writes_approx) — heuristic from ST/RLL text."""
    reads: set[str] = set()
    writes: set[str] = set()
    if not logic:
        return reads, writes
    # ST assignments
    for m in re.finditer(
        r"([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*:=",
        logic,
    ):
        root = m.group(1).split(".", 1)[0]
        if root in known_tags:
            writes.add(root)
    # RLL OTE/OTL/OTU/MOV dest rough
    for m in re.finditer(
        r"(?:OTE|OTL|OTU|OSR|OSF)\(\s*([A-Za-z_][A-Za-z0-9_\.]*)",
        logic,
        re.I,
    ):
        root = m.group(1).split(".", 1)[0]
        if root in known_tags:
            writes.add(root)
    for m in re.finditer(
        r"MOV\(\s*[^,]+,\s*([A-Za-z_][A-Za-z0-9_\.]*)",
        logic,
        re.I,
    ):
        root = m.group(1).split(".", 1)[0]
        if root in known_tags:
            writes.add(root)
    # Any known tag mention counts as read if not already write-only context
    for m in TAG_REF_RE.finditer(logic):
        root = m.group(1).split(".", 1)[0]
        if root in known_tags:
            reads.add(root)
    # reads include writes for dependency completeness; separate later
    return reads, writes


def _timers_counters(logic: str) -> list[str]:
    found = sorted(set(TIMER_RE.findall(logic or "")))
    return found


def _aoi_like(logic: str, known_routines: set[str], known_tags: set[str]) -> list[str]:
    """Heuristic AOI / function-block style calls (exclude JSR targets & keywords)."""
    skip = {
        "IF",
        "THEN",
        "ELSE",
        "ELSIF",
        "END_IF",
        "FOR",
        "END_FOR",
        "CASE",
        "OF",
        "END_CASE",
        "WHILE",
        "END_WHILE",
        "REPEAT",
        "UNTIL",
        "EXIT",
        "RETURN",
        "JSR",
        "SBR",
        "RET",
        "XIC",
        "XIO",
        "OTE",
        "OTL",
        "OTU",
        "ONS",
        "OSR",
        "OSF",
        "MOV",
        "COP",
        "CPS",
        "CLR",
        "TON",
        "TOF",
        "RTO",
        "CTU",
        "CTD",
        "RES",
        "ADD",
        "SUB",
        "MUL",
        "DIV",
        "MOD",
        "AND",
        "OR",
        "XOR",
        "NOT",
        "EQU",
        "NEQ",
        "LES",
        "LEQ",
        "GRT",
        "GEQ",
        "LIM",
        "MEQ",
        "TRUNC",
        "ABS",
        "SQRT",
        "LN",
        "LOG",
        "DEG",
        "RAD",
        "SIN",
        "COS",
        "TAN",
        "ASN",
        "ACS",
        "ATN",
        "SIZE",
        "FIND",
        "INSERT",
        "DELETE",
        "MID",
        "CONCAT",
        "BOOL",
        "DINT",
        "REAL",
        "STRING",
        "TRUE",
        "FALSE",
    }
    out = set()
    for name in AOI_RE.findall(logic or ""):
        if name.upper() in skip:
            continue
        if name in known_routines:
            continue
        if name in known_tags:
            continue
        if name.startswith("SR_") or name.startswith("RT_"):
            continue
        out.add(name)
    return sorted(out)


def build_routine_graph(parsed: dict[str, Any]) -> dict[str, Any]:
    routines = parsed["routines"]
    known_tags = _tag_names(parsed["tags"])
    known_rt = set(routines)
    called_by: dict[str, set[str]] = defaultdict(set)
    nodes: list[dict[str, Any]] = []

    for name, r in routines.items():
        logic = r.get("logic_text") or ""
        calls = _extract_calls(logic)
        for c in calls:
            called_by[c].add(name)
        reads, writes = _refs_in_logic(logic, known_tags)
        timers = _timers_counters(logic)
        aois = _aoi_like(logic, known_rt, known_tags)
        # External deps: tag refs that look like IO / cross-program but not defined here
        # (within program tags only — unresolved = referenced but missing)
        mentioned = reads | writes
        unresolved_ext = sorted(
            t
            for t in mentioned
            if t not in known_tags and re.match(r"^(P|PE|EZPE|VFD|ENC|MRG)\d", t)
        )
        nodes.append(
            {
                "routine": name,
                "type": r.get("type"),
                "purpose": ROUTINE_PURPOSE.get(name, "See library logic / comments"),
                "called_by": [],  # fill after
                "calls": calls,
                "tags_read": sorted(reads - writes)[:200],
                "tags_written": sorted(writes)[:200],
                "tags_touched_count": len(mentioned),
                "timers_counters": timers[:80],
                "aoi_or_fb_like": aois[:40],
                "inputs_outputs_heuristic": {
                    "enable_gates": sorted(
                        t
                        for t in mentioned
                        if t.startswith("Enable_") or t.startswith("Use_")
                    ),
                    "lane_pe": sorted(t for t in mentioned if re.match(r"^PE\d", t)),
                    "full_eyes": sorted(t for t in mentioned if t.startswith("EZPE")),
                    "conveyors": sorted(t for t in mentioned if t.endswith("_Conv")),
                    "drives": sorted(t for t in mentioned if t.startswith("VFD")),
                    "merge_structs": sorted(
                        t for t in mentioned if t.startswith("MRG")
                    )[:60],
                },
                "unresolved_external_deps": unresolved_ext,
                "rung_or_line_count": r.get("rung_or_line_count"),
                "comment_samples": (r.get("comments") or [])[:8],
            }
        )

    for n in nodes:
        n["called_by"] = sorted(called_by.get(n["routine"], set()))

    # Orphans / entry
    entry = parsed.get("main_routine") or "Main_Routine"
    unreachable = [
        n["routine"]
        for n in nodes
        if n["routine"] != entry and not n["called_by"] and n["routine"] not in {entry}
    ]

    # Tag role summary
    tag_roles = summarize_tag_roles(parsed["tags"])

    return {
        "generated_at": _ts(),
        "source": parsed["path"],
        "program_name": parsed.get("program_name"),
        "main_routine": entry,
        "routine_count": len(nodes),
        "tag_count": len(parsed["tags"]),
        "call_graph": {
            "entry": entry,
            "unreachable_or_unreferenced": unreachable,
            "edges": [
                {"from": n["routine"], "to": c}
                for n in nodes
                for c in n["calls"]
            ],
        },
        "routines": sorted(nodes, key=lambda x: x["routine"]),
        "tag_role_summary": tag_roles,
        "control_model_seeds": extract_control_model_seeds(parsed),
        "notes": [
            "Tag read/write sets are heuristic from ST := and RLL OTE/MOV patterns.",
            "AOI detection is name-heuristic; true AOI instances may live in controller, not this program export.",
            "Finished PLC4 was not read.",
        ],
    }


def summarize_tag_roles(tags: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[str]] = defaultdict(list)
    for t in tags:
        n = t["name"]
        dt = t.get("datatype") or ""
        if n.startswith("EZPE"):
            buckets["full_eye_pe_udt"].append(n)
        elif re.match(r"^PE\d", n):
            buckets["photoeyes"].append(n)
        elif n.endswith("_Conv"):
            buckets["conveyor_udt"].append(n)
        elif n.endswith("_Enc"):
            buckets["encoder_udt"].append(n)
        elif n.endswith("_SawMerge_HMI"):
            buckets["hmi"].append(n)
        elif n.startswith("VFD"):
            buckets["vfd"].append(n)
        elif n.startswith("ENC"):
            buckets["encoder"].append(n)
        elif n.startswith("Enable_") or n.startswith("Use_"):
            buckets["feature_enables"].append(n)
        elif n.startswith("MRG"):
            buckets["merge_control"].append(n)
        elif dt:
            buckets[f"datatype:{dt}"].append(n)
        else:
            buckets["other"].append(n)
    return {k: {"count": len(v), "symbols": sorted(v)[:80]} for k, v in sorted(buckets.items())}


def extract_control_model_seeds(parsed: dict[str, Any]) -> dict[str, Any]:
    """Pull actual state/sequence vocabulary from library + known RUN tables."""
    logic_all = "\n".join(
        (r.get("logic_text") or "") for r in parsed["routines"].values()
    )
    # dig for mode / state identifiers in ST
    mode_refs = sorted(
        set(
            re.findall(
                r"\b(diLaneMode|diLaneModePrev|diLaneWaitingMask|xLaneWaiting|"
                r"xLaneRelease|xLaneHold|xReserve|Reserve|Slug|Waiting|Releasing|"
                r"Holding|Hanging|Idle|Stopped|FeedSlow|FeedFast)\b",
                logic_all,
                re.I,
            )
        )
    )
    lane_cntrl = parsed["routines"].get("SR_LaneCntrl", {})
    resv = parsed["routines"].get("RT_CollTrackResvMngr", {})
    main = parsed["routines"].get("Main_Routine", {})
    return {
        "run_saw_state_vocab": RUN_SAW_STATES,
        "run_hs_saw_state_vocab": HS_SAW_STATES,
        "library_mode_signal_hits": mode_refs,
        "feature_gates_in_main": sorted(
            set(
                re.findall(
                    r"\b(Enable_[A-Za-z0-9_]+|Use_[A-Za-z0-9_]+)\b",
                    main.get("logic_text") or "",
                )
            )
        ),
        "lane_control_routine": {
            "name": "SR_LaneCntrl",
            "type": lane_cntrl.get("type"),
            "line_count": lane_cntrl.get("rung_or_line_count"),
            "purpose": ROUTINE_PURPOSE["SR_LaneCntrl"],
        },
        "reservation_manager_routine": {
            "name": "RT_CollTrackResvMngr",
            "type": resv.get("type"),
            "line_count": resv.get("rung_or_line_count"),
            "calls": _extract_calls(resv.get("logic_text") or ""),
            "purpose": ROUTINE_PURPOSE["RT_CollTrackResvMngr"],
        },
        "lane_mode_seed_notes": LANE_MODE_NOTES,
        "library_lane_modes_documented": {
            0: "Stopped",
            1: "Startup, Merge any possible parcels on Power Turn and Inject conveyor",
            2: "Normal",
            3: "Manual/Maint",
        },
        "library_collector_modes_documented": {
            0: "Collector conveyor Not Running in AUTO Mode",
            1: "Startup Mode, running out Collector",
            2: "Startup Mode, waiting for all lanes to complete their merge",
            3: "Normal Mode",
        },
        "ezpe_full_role": (
            "RT_IO_Map_NoGapStore uses EZPE*.Full to select HMI ReleaseLengthFull vs ReleaseLength "
            "per lane index when gap-store belts are not used"
        ),
        "confidence": "high for documented numeric modes; medium for RUN pState↔diLaneMode mapping",
    }


def graph_to_markdown(graph: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Sawtooth Merge — Routine Dependency Graph")
    lines.append("")
    lines.append(f"Generated: `{graph.get('generated_at')}`")
    lines.append(f"Source: `{graph.get('source')}`")
    lines.append(f"Program: **{graph.get('program_name')}**")
    lines.append(f"Main routine: **{graph.get('main_routine')}**")
    lines.append(
        f"Routines: **{graph.get('routine_count')}** · Tags: **{graph.get('tag_count')}**"
    )
    lines.append("")
    lines.append("## Call graph (entry → …)")
    lines.append("")
    edges = graph.get("call_graph", {}).get("edges") or []
    by_from: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        by_from[e["from"]].append(e["to"])

    lines.append("```")
    entry = graph.get("main_routine") or "Main_Routine"

    def render(node: str, indent: int = 0, stack: tuple[str, ...] = ()) -> None:
        pad = "  " * indent
        cycle = "  [cycle]" if node in stack else ""
        lines.append(f"{pad}- {node}{cycle}")
        if node in stack:
            return
        for k in sorted(set(by_from.get(node, []))):
            render(k, indent + 1, stack + (node,))

    render(entry)
    lines.append("```")
    lines.append("")
    unreach = graph.get("call_graph", {}).get("unreachable_or_unreferenced") or []
    if unreach:
        lines.append("### Unreferenced by JSR chain")
        for u in unreach:
            lines.append(f"- `{u}`")
        lines.append("")

    lines.append("## Routines")
    lines.append("")
    for r in graph.get("routines") or []:
        lines.append(f"### `{r['routine']}` ({r.get('type')})")
        lines.append("")
        lines.append(f"- **Purpose:** {r.get('purpose')}")
        lines.append(
            f"- **Called by:** {', '.join(f'`{x}`' for x in r.get('called_by') or []) or '—'}"
        )
        lines.append(
            f"- **Calls:** {', '.join(f'`{x}`' for x in r.get('calls') or []) or '—'}"
        )
        lines.append(f"- **Logic units:** {r.get('rung_or_line_count')}")
        io = r.get("inputs_outputs_heuristic") or {}
        for k, v in io.items():
            if v:
                lines.append(
                    f"- **{k}:** {', '.join(f'`{x}`' for x in v[:20])}"
                    + (" …" if len(v) > 20 else "")
                )
        tw = r.get("tags_written") or []
        if tw:
            lines.append(
                f"- **Writes (sample):** {', '.join(f'`{x}`' for x in tw[:15])}"
                + (" …" if len(tw) > 15 else "")
            )
        tr = r.get("tags_read") or []
        if tr:
            lines.append(
                f"- **Reads (sample):** {', '.join(f'`{x}`' for x in tr[:15])}"
                + (" …" if len(tr) > 15 else "")
            )
        tm = r.get("timers_counters") or []
        if tm:
            lines.append(f"- **Timers/counters tokens:** {', '.join(f'`{x}`' for x in tm[:20])}")
        ao = r.get("aoi_or_fb_like") or []
        if ao:
            lines.append(f"- **AOI/FB-like:** {', '.join(f'`{x}`' for x in ao)}")
        ue = r.get("unresolved_external_deps") or []
        if ue:
            lines.append(
                f"- **Unresolved external deps:** {', '.join(f'`{x}`' for x in ue)}"
            )
        lines.append("")

    seeds = graph.get("control_model_seeds") or {}
    lines.append("## Control-model seeds")
    lines.append("")
    lines.append(
        f"- RUN SawState vocab: {', '.join(f'`{s}`' for s in seeds.get('run_saw_state_vocab') or [])}"
    )
    lines.append(
        f"- RUN HSSawState vocab: {', '.join(f'`{s}`' for s in seeds.get('run_hs_saw_state_vocab') or [])}"
    )
    lines.append(
        f"- Main feature gates: {', '.join(f'`{s}`' for s in seeds.get('feature_gates_in_main') or [])}"
    )
    lines.append(f"- Confidence: {seeds.get('confidence')}")
    lines.append("")
    lines.append("## Tag role summary")
    lines.append("")
    for role, info in (graph.get("tag_role_summary") or {}).items():
        lines.append(f"- **{role}** ({info.get('count')}): "
                      + ", ".join(f"`{s}`" for s in (info.get("symbols") or [])[:12])
                      + (" …" if (info.get("count") or 0) > 12 else ""))
    lines.append("")
    lines.append("Finished PLC4 was not used.")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    parsed = parse_program_l5x(args.pack)
    graph = build_routine_graph(parsed)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "sawtooth_routine_graph.json", graph)
    (out / "sawtooth_routine_graph.md").write_text(
        graph_to_markdown(graph), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "routines": graph["routine_count"],
                "tags": graph["tag_count"],
                "out": str(out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
