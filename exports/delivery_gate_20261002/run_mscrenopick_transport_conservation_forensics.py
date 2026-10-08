#!/usr/bin/env python3
"""MSCRENOPICK transport conservation forensics (diagnostic only).

Accounts every conveyor discovered by fortna_run_physical_layout.build_transport_graph
into exactly one class:

  generated | foreign | not_transport_equipment | withheld | review | missing_defect

Invariant: discovered == sum(class counts). Routine placeholder/NOP quality is reported
separately (NOP-only routines are NOT complete generation).

Does NOT modify fortna_autogen.py or production generators.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))
os.chdir(REPO)
os.environ.setdefault("FORTNA_PRISM_DISABLE", "1")

OUT = REPO / "exports" / "delivery_gate_20261002"
OUT.mkdir(parents=True, exist_ok=True)
JSON_OUT = OUT / "MSCRENOPICK_TRANSPORT_CONSERVATION.json"
TXT_OUT = OUT / "MSCRENOPICK_TRANSPORT_CONSERVATION.txt"

MACHINE = "MSCRENOPICK"
CLASSES = (
    "generated",
    "foreign",
    "not_transport_equipment",
    "withheld",
    "review",
    "missing_defect",
)

# Warden snapshot (input claim) — forensics compare against live discovery.
WARDEN_CLAIM = {
    "conveyors_in_graph": 53,
    "generated": 32,
    "conv_flt_nop_rungs": 32,
    "merges_withheld": 3,
    "conveyors_with_real_pe": 1,
    "notes": (
        "Conv_Flt / Control_Station / Stacklight placeholders; "
        "only 1 conveyor with real PE logic; 3 merges withheld."
    ),
}


def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.is_file() or p.is_dir():
            return p
    return None


def resolve_run_dir() -> Path:
    """Prefer sibling FortnaPlus active RUN when MSCRENOPICK; else local peek."""
    candidates = [
        REPO / "workspace" / "active" / "RUN",
        REPO.parent / "FortnaPlus" / "workspace" / "active" / "RUN",
        REPO
        / "workspace"
        / "_reno_peek"
        / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
        / "RUN",
        REPO.parent
        / "FortnaPlus"
        / "workspace"
        / "_reno_peek"
        / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
        / "RUN",
    ]
    for cand in candidates:
        cfg = cand / "project.cfg"
        if not cfg.is_file():
            continue
        try:
            txt = cfg.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"MACHINENAME\s*=\s*MSCRENOPICK", txt, re.I):
            return cand
    # Fall back to first existing RUN even if identity unknown.
    hit = _first_existing(candidates)
    if hit is None:
        raise FileNotFoundError("MSCRENOPICK RUN not found (active or _reno_peek)")
    return hit


def resolve_l5x() -> Path | None:
    cands: list[Path] = [
        REPO / "exports" / "current" / "MSCRENOPICK_2026_10_05_1711.L5X",
        REPO.parent
        / "FortnaPlus"
        / "exports"
        / "current"
        / "MSCRENOPICK_2026_10_05_1711.L5X",
    ]
    for base in (
        REPO.parent / "FortnaPlus" / "exports" / "current",
        REPO / "exports" / "current",
    ):
        if not base.is_dir():
            continue
        cands.extend(
            sorted(
                base.glob("MSCRENOPICK_*.L5X"),
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )
        )
    return _first_existing(cands)


def resolve_autogen_report() -> Path | None:
    builds = [
        REPO.parent / "FortnaPlus" / "workspace" / ".internal" / "builds",
        REPO / "workspace" / ".internal" / "builds",
    ]
    cands: list[Path] = []
    for base in builds:
        if not base.is_dir():
            continue
        for d in base.iterdir():
            if not d.is_dir():
                continue
            rep = d / "autogen_report.json"
            if not rep.is_file():
                continue
            # Prefer MSCRENOPICK builds (L5X or BUILD_ISSUES sibling).
            if any(d.glob("MSCRENOPICK*")) or "MSCRENOPICK" in d.name.upper():
                cands.append(rep)
    if not cands:
        return None
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    # Confirm controller in report when possible.
    for rep in cands:
        try:
            j = json.loads(rep.read_text(encoding="utf-8"))
        except Exception:
            continue
        proj = str(j.get("project") or j.get("controller") or "").upper()
        if "MSCRENOPICK" in proj or not proj:
            return rep
    return cands[0]


def resolve_build_issues() -> Path | None:
    return _first_existing(
        [
            REPO / "exports" / "current" / "MSCRENOPICK_BUILD_ISSUES.json",
            REPO.parent
            / "FortnaPlus"
            / "exports"
            / "current"
            / "MSCRENOPICK_BUILD_ISSUES.json",
        ]
    )


def graph_nodes(run_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from fortna_run_physical_layout import build_transport_graph

    graph = build_transport_graph(run_dir, MACHINE)
    nodes: list[dict[str, Any]] = []
    for area in graph.get("areas") or []:
        for n in area.get("nodes") or []:
            tag = str(n.get("conveyorTag") or n.get("label") or "").strip().upper()
            if not tag:
                continue
            nodes.append(dict(n, conveyorTag=tag))
    # Deduplicate by tag (first wins).
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for n in nodes:
        t = n["conveyorTag"]
        if t in seen:
            continue
        seen.add(t)
        uniq.append(n)
    return uniq, graph


def generated_conveyor_set(
    run_dir: Path, l5x: Path | None, report_path: Path | None
) -> tuple[set[str], dict[str, Any]]:
    """Union of load_from_run + L5X *_Conv + autogen_report generated list."""
    meta: dict[str, Any] = {"sources": []}
    tags: set[str] = set()

    # 1) load_from_run (discovery/generation plan)
    try:
        from fortna_autogen import load_from_run

        inp = load_from_run(run_dir)
        try:
            inp.machine = MACHINE
            inp.project_name = MACHINE
        except Exception:
            pass
        for c in inp.conveyors or []:
            t = str(getattr(c, "conveyor", None) or getattr(c, "name", None) or "")
            t = t.strip().upper()
            if t:
                tags.add(t)
        meta["sources"].append(
            {"kind": "load_from_run", "count": len(tags), "run_dir": str(run_dir)}
        )
        meta["load_from_run_count"] = len(tags)
        meta["merges_2to1"] = list(getattr(inp, "merges_2to1", None) or [])
    except Exception as ex:  # noqa: BLE001
        meta["load_from_run_error"] = str(ex)

    # 2) L5X AOI / tag evidence
    if l5x and l5x.is_file():
        text = l5x.read_text(encoding="utf-8", errors="replace")
        aoi = {m.upper() for m in re.findall(r'Name="(P\d{1,4}[A-Z0-9_]*)_Conv"', text)}
        tags |= aoi
        meta["sources"].append(
            {"kind": "l5x_conv_tags", "count": len(aoi), "path": str(l5x)}
        )
        meta["l5x_conv_count"] = len(aoi)
        meta["l5x_path"] = str(l5x)

    # 3) autogen_report
    if report_path and report_path.is_file():
        try:
            rep = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as ex:  # noqa: BLE001
            meta["autogen_report_error"] = str(ex)
            rep = {}
        lea = rep.get("local_equipment_accounting") or {}
        gen = {
            str(x).strip().upper()
            for x in (lea.get("generated_conveyors") or [])
            if str(x).strip()
        }
        if not gen:
            # Fall back to sample + count is incomplete; use LEA by_tag GENERATED_LOCAL.
            for t, info in (lea.get("by_tag") or {}).items():
                if (info or {}).get("classification") == "GENERATED_LOCAL":
                    gen.add(str(t).strip().upper())
        tags |= gen
        meta["sources"].append(
            {
                "kind": "autogen_report",
                "count": len(gen),
                "path": str(report_path),
                "conveyor_count": rep.get("conveyor_count"),
                "conveyors_with_real_pe": rep.get("conveyors_with_real_pe"),
                "merges_withheld_review": rep.get("merges_withheld_review"),
                "merges_withheld_count": rep.get("merges_withheld_count"),
            }
        )
        meta["autogen_report"] = {
            "path": str(report_path),
            "conveyor_count": rep.get("conveyor_count"),
            "conveyors_with_real_pe": rep.get("conveyors_with_real_pe"),
            "merges_withheld_review": list(rep.get("merges_withheld_review") or []),
            "merges_withheld_count": rep.get("merges_withheld_count"),
            "local_equipment_accounting_generated": sorted(gen),
        }
        meta["merges_withheld_review"] = list(rep.get("merges_withheld_review") or [])

    meta["generated_union_count"] = len(tags)
    return tags, meta


def withheld_lane_map(
    merges_withheld: list[str], merges_rows: list[dict] | None = None
) -> dict[str, str]:
    """Map conveyor tag → withheld merge name."""
    out: dict[str, str] = {}
    for name in merges_withheld or []:
        mname = str(name or "").strip()
        if not mname:
            continue
        for tok in re.findall(r"P\d{1,4}[A-Z0-9_]*", mname, flags=re.I):
            out[tok.upper()] = mname
    for m in merges_rows or []:
        if not isinstance(m, dict):
            continue
        mname = str(
            m.get("discovery_name") or m.get("name") or m.get("control_object") or ""
        ).strip()
        mcls = str(
            m.get("classification")
            or m.get("status")
            or m.get("sourceClassification")
            or ""
        ).strip().upper()
        is_withheld = mcls in {
            "REVIEW_REQUIRED",
            "REVIEW",
            "UNKNOWN",
            "UNRESOLVED",
            "CANDIDATE",
            "WITHHELD",
            "REVIEW_WITHHELD",
        } or (
            mname.upper() in {x.upper() for x in (merges_withheld or [])} if mname else False
        )
        if not is_withheld:
            continue
        for tok in re.findall(r"P\d{1,4}[A-Z0-9_]*", mname, flags=re.I):
            out.setdefault(tok.upper(), mname or "?")
    return out


def fidelity_index(run_dir: Path) -> dict[str, dict[str, Any]]:
    try:
        from fortna_run_equipment_fidelity import classify_run_equipment_fidelity

        fid = classify_run_equipment_fidelity(run_dir, MACHINE)
    except Exception as ex:  # noqa: BLE001
        return {"__error__": {"error": str(ex)}}
    out: dict[str, dict[str, Any]] = {}
    for row in fid.get("rows") or []:
        ident = str(row.get("identity") or "").strip().upper()
        if ident:
            out[ident] = row
    out["__meta__"] = {
        "counts": fid.get("counts"),
        "counts_total_retained": fid.get("counts_total_retained"),
        "local_active_tags": fid.get("local_active_tags"),
        "foreign_tags": fid.get("foreign_tags"),
    }
    return out


_NON_TRANSPORT_TYPES = frozenset(
    {
        "TITLE",
        "IMAGE",
        "LOGIN",
        "LOGOUT",
        "USER",
        "SYSTEM",
        "BEACON",
        "HORN",
        "ESTOP",
        "ES",
        "PB",
        "PUSHBUTTON",
    }
)


def classify_node(
    node: dict[str, Any],
    *,
    generated: set[str],
    withheld_lanes: dict[str, str],
    fidelity: dict[str, Any] | None,
) -> dict[str, Any]:
    tag = str(node.get("conveyorTag") or "").upper()
    eq_type = str(node.get("equipmentType") or "").strip().upper()
    scope = str(node.get("scopeClass") or "").strip().upper()
    plc_owned = bool(node.get("plcOwned", True))
    external = bool(node.get("externalReference")) or scope == "EXTERNAL_REFERENCE"
    fid = fidelity or {}
    fid_cls = str(fid.get("fidelity_class") or "").strip().upper()
    reasons_fid = list(fid.get("reasons") or [])

    rec: dict[str, Any] = {
        "tag": tag,
        "equipment_type": eq_type,
        "scope_class": scope or ("EXTERNAL_REFERENCE" if external else "LOCAL"),
        "plc_owned": plc_owned,
        "external_reference": external,
        "fidelity_class": fid_cls or None,
        "fidelity_reasons": reasons_fid,
        "machine_name": node.get("machineName") or fid.get("machine_name") or "",
    }

    # 1) Generated wins.
    if tag in generated:
        rec["classification"] = "generated"
        rec["reason"] = "present_in_generated_plan_or_l5x"
        return rec

    # 2) Explicit merge withhold (even if also EXTERNAL_REFERENCE).
    if tag in withheld_lanes:
        rec["classification"] = "withheld"
        rec["reason"] = f"merge_lane_of_review_withheld:{withheld_lanes[tag]}"
        rec["merge"] = withheld_lanes[tag]
        return rec

    # 3) Foreign / external non-owned.
    if fid_cls == "FOREIGN_EQUIPMENT":
        rec["classification"] = "foreign"
        rec["reason"] = "fidelity_FOREIGN_EQUIPMENT:" + ",".join(reasons_fid[:3])
        return rec
    foreign_reason = next(
        (r for r in reasons_fid if "foreign" in str(r).lower()),
        "",
    )
    if foreign_reason:
        rec["classification"] = "foreign"
        rec["reason"] = str(foreign_reason)
        return rec
    if external or not plc_owned:
        rec["classification"] = "foreign"
        rec["reason"] = "external_reference_display_neighbor_not_plc_owned"
        return rec

    # 4) Not transport equipment (graphical / non-conveyor types).
    if fid_cls == "TEMPLATE_GRAPHICAL_ONLY" or eq_type in _NON_TRANSPORT_TYPES:
        rec["classification"] = "not_transport_equipment"
        rec["reason"] = f"non_transport_type:{eq_type or fid_cls or 'UNKNOWN'}"
        return rec

    # 5) Should have been generated (local / plc-owned) but missing → defect.
    if plc_owned and scope != "EXTERNAL_REFERENCE":
        rec["classification"] = "missing_defect"
        rec["reason"] = "plc_owned_graph_node_absent_from_generated_set"
        return rec
    if fid_cls == "LOCAL_ACTIVE_EQUIPMENT":
        rec["classification"] = "missing_defect"
        rec["reason"] = "local_active_absent_from_generated_set"
        return rec

    # 6) Residual → review.
    rec["classification"] = "review"
    rec["reason"] = f"unresolved_ownership:{fid_cls or 'UNKNOWN'}"
    return rec


_LOGIC_RE = re.compile(
    r"\b(XIC|XIO|OTE|OTL|OTU|TON|TOF|OSR|JSR|MOV|EQU|NEQ|GEQ|LEQ|GRT|LES|ADD|SUB|MUL|DIV|CPT)\b",
    re.I,
)
_NOP_RE = re.compile(r"\bNOP\s*\(", re.I)


def routine_quality(l5x: Path | None) -> list[dict[str, Any]]:
    """Placeholder / NOP-only routine findings (separate from conveyor conservation)."""
    findings: list[dict[str, Any]] = []
    watch = (
        "Conv_Flt",
        "Control_Station",
        "Stacklight",
        "Conv_Jam",
        "Conv_Fast",
        "Conv_PE",
        "PE_Logic",
        "Merge",
    )
    if not l5x or not l5x.is_file():
        return [
            {
                "routine": r,
                "status": "L5X_MISSING",
                "note": "Cannot assess routine quality without L5X",
            }
            for r in watch
        ]

    text = l5x.read_text(encoding="utf-8", errors="replace")
    for rt in watch:
        m = re.search(rf'<Routine Name="{re.escape(rt)}"[\s\S]*?</Routine>', text)
        if not m:
            findings.append(
                {
                    "routine": rt,
                    "program_hint": "Area_*",
                    "present": False,
                    "rung_count": 0,
                    "nontrivial_rungs": 0,
                    "nop_only_rungs": 0,
                    "status": "ABSENT",
                    "complete": False,
                    "note": "Routine not present in L5X",
                }
            )
            continue
        body = m.group(0)
        # Bound to first matching routine occurrence (Area_Slow typically).
        rungs = re.findall(r"<Rung[\s\S]*?</Rung>", body)
        nontrivial = 0
        nop_only = 0
        emptyish = 0
        for r in rungs:
            has_logic = bool(_LOGIC_RE.search(r))
            has_nop = bool(_NOP_RE.search(r))
            if has_logic:
                nontrivial += 1
            elif has_nop:
                nop_only += 1
            else:
                emptyish += 1
        if nontrivial == 0 and (nop_only > 0 or len(rungs) == 0 or emptyish == len(rungs)):
            status = "PLACEHOLDER_NOP_ONLY" if nop_only else "EMPTY_OR_NO_LOGIC"
            complete = False
            note = (
                "Routine exists but is NOP-only / empty — NOT complete generation."
                if not complete
                else "ok"
            )
        else:
            status = "HAS_LOGIC"
            complete = True
            note = "Has non-NOP logic rungs"
        findings.append(
            {
                "routine": rt,
                "present": True,
                "rung_count": len(rungs),
                "nontrivial_rungs": nontrivial,
                "nop_only_rungs": nop_only,
                "empty_or_comment_rungs": emptyish,
                "status": status,
                "complete": complete,
                "note": note,
            }
        )
    return findings


def render_txt(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("MSCRENOPICK TRANSPORT CONSERVATION FORENSICS")
    lines.append("=" * 72)
    lines.append(f"generated_at: {payload.get('generated_at')}")
    lines.append(f"run_dir: {payload.get('run_dir')}")
    lines.append(f"l5x: {payload.get('l5x')}")
    lines.append(f"autogen_report: {(payload.get('generated_meta') or {}).get('autogen_report', {}).get('path')}")
    lines.append("")
    lines.append("DISCOVERY")
    lines.append("-" * 72)
    lines.append(
        f"conveyors_discovered (transport graph): {payload.get('discovered_count')}"
    )
    lines.append(
        f"generated_union (load_from_run ∪ L5X ∪ report): "
        f"{(payload.get('generated_meta') or {}).get('generated_union_count')}"
    )
    lines.append(
        f"53 accounted: {'YES' if payload.get('accounted_53') else 'NO'} "
        f"(discovered={payload.get('discovered_count')} "
        f"sum_classes={payload.get('classified_sum')} "
        f"conservation_ok={payload.get('conservation_ok')})"
    )
    lines.append("")
    lines.append("COUNTS BY CLASS")
    lines.append("-" * 72)
    counts = payload.get("counts") or {}
    for cls in CLASSES:
        lines.append(f"  {cls:28s} {counts.get(cls, 0)}")
    lines.append("")
    lines.append("WARDEN CLAIM VS OBSERVED")
    lines.append("-" * 72)
    wc = payload.get("warden_claim") or {}
    obs = payload.get("observed_vs_warden") or {}
    lines.append(
        f"  claim graph={wc.get('conveyors_in_graph')} generated={wc.get('generated')} "
        f"Conv_Flt_NOP={wc.get('conv_flt_nop_rungs')} merges_withheld={wc.get('merges_withheld')}"
    )
    lines.append(
        f"  observed graph={obs.get('discovered')} generated={obs.get('generated')} "
        f"Conv_Flt_NOP={obs.get('conv_flt_nop_rungs')} merges_withheld={obs.get('merges_withheld')}"
    )
    lines.append(f"  delta_generated_vs_warden_32: {obs.get('delta_generated_vs_warden')}")
    lines.append("")
    lines.append("TOP WITHHELD / MISSING / FOREIGN REASONS")
    lines.append("-" * 72)
    for row in payload.get("top_reasons") or []:
        lines.append(
            f"  [{row.get('classification')}] {row.get('tag')}: {row.get('reason')}"
        )
    if not payload.get("top_reasons"):
        lines.append("  (none)")
    lines.append("")
    lines.append("ROUTINE QUALITY (separate from conveyor conservation)")
    lines.append("-" * 72)
    lines.append(
        "NOTE: a routine that exists but is NOP-only is NOT complete."
    )
    for f in payload.get("routine_quality") or []:
        lines.append(
            f"  {f.get('routine')}: status={f.get('status')} "
            f"rungs={f.get('rung_count')} nontrivial={f.get('nontrivial_rungs')} "
            f"nop_only={f.get('nop_only_rungs')} complete={f.get('complete')}"
        )
    lines.append("")
    lines.append("PER-CONVEYOR CLASSIFICATIONS")
    lines.append("-" * 72)
    for row in payload.get("classifications") or []:
        lines.append(
            f"  {row.get('tag'):8s} {row.get('classification'):24s} {row.get('reason')}"
        )
    lines.append("")
    lines.append("HOW COUNTS ARE PRODUCED")
    lines.append("-" * 72)
    for line in payload.get("counting_notes") or []:
        lines.append(f"  - {line}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    run_dir = resolve_run_dir()
    l5x = resolve_l5x()
    report_path = resolve_autogen_report()
    issues_path = resolve_build_issues()

    nodes, graph = graph_nodes(run_dir)
    discovered_tags = [n["conveyorTag"] for n in nodes]
    discovered_count = len(discovered_tags)

    generated, gen_meta = generated_conveyor_set(run_dir, l5x, report_path)
    merges_withheld = list(gen_meta.get("merges_withheld_review") or [])
    if not merges_withheld and issues_path and issues_path.is_file():
        try:
            issues = json.loads(issues_path.read_text(encoding="utf-8"))
            for item in (issues.get("sections") or {}).get("WITHHELD FROM L5X") or []:
                if str(item.get("subsystem") or "").lower() == "merge":
                    merges_withheld.append(str(item.get("object/device") or ""))
        except Exception:
            pass
    withheld_lanes = withheld_lane_map(
        merges_withheld, list(gen_meta.get("merges_2to1") or [])
    )

    fid_idx = fidelity_index(run_dir)
    fid_meta = fid_idx.pop("__meta__", {})
    fid_err = fid_idx.pop("__error__", None)

    classifications: list[dict[str, Any]] = []
    for n in nodes:
        tag = n["conveyorTag"]
        classifications.append(
            classify_node(
                n,
                generated=generated,
                withheld_lanes=withheld_lanes,
                fidelity=fid_idx.get(tag),
            )
        )

    counts = Counter(r["classification"] for r in classifications)
    for cls in CLASSES:
        counts.setdefault(cls, 0)
    classified_sum = sum(counts[c] for c in CLASSES)
    conservation_ok = discovered_count == classified_sum == len(classifications)
    # Explicit "53 accounted" when discovery is the Warden graph size.
    accounted_53 = discovered_count == 53 and conservation_ok

    # Reason rollup for withheld / missing / foreign.
    interesting = [
        r
        for r in classifications
        if r["classification"] in {"withheld", "missing_defect", "foreign", "review"}
    ]
    reason_counter = Counter(
        (r["classification"], r.get("reason") or "") for r in interesting
    )
    top_reasons = []
    for (cls, reason), n in reason_counter.most_common(12):
        tags = sorted(
            r["tag"]
            for r in interesting
            if r["classification"] == cls and (r.get("reason") or "") == reason
        )
        top_reasons.append(
            {
                "classification": cls,
                "reason": reason,
                "count": n,
                "tags": tags,
                "tag": ",".join(tags[:8]),
            }
        )

    rq = routine_quality(l5x)
    conv_flt = next((x for x in rq if x.get("routine") == "Conv_Flt"), {})

    observed = {
        "discovered": discovered_count,
        "generated": int(counts.get("generated") or 0),
        "foreign": int(counts.get("foreign") or 0),
        "withheld": int(counts.get("withheld") or 0),
        "missing_defect": int(counts.get("missing_defect") or 0),
        "review": int(counts.get("review") or 0),
        "not_transport_equipment": int(counts.get("not_transport_equipment") or 0),
        "merges_withheld": len(list(dict.fromkeys(merges_withheld))),
        "merges_withheld_names": list(dict.fromkeys(merges_withheld)),
        "conv_flt_nop_rungs": conv_flt.get("nop_only_rungs"),
        "conveyors_with_real_pe": (gen_meta.get("autogen_report") or {}).get(
            "conveyors_with_real_pe"
        ),
        "delta_generated_vs_warden": int(counts.get("generated") or 0)
        - int(WARDEN_CLAIM["generated"]),
    }

    counting_notes = [
        "Discovery denominator = fortna_run_physical_layout.build_transport_graph(...).metrics.conveyors_discovered (graph area nodes).",
        "Generation set = union of fortna_autogen.load_from_run conveyors + L5X Name=\"P*_Conv\" tags + autogen_report local_equipment_accounting.generated_conveyors.",
        "EXTERNAL_REFERENCE / plcOwned=false graph neighbors are classified foreign (display-context, Apply must skip) unless an explicit merge withhold applies.",
        "Merge lanes listed in merges_withheld_review are classified withheld (not missing_defect).",
        "Routine NOP/placeholder quality is tracked under routine_quality and does NOT move a conveyor out of 'generated' — existence ≠ complete logic.",
        "Warden claimed generated=32 / Conv_Flt NOP=32; live MSCRENOPICK artifact currently shows generated≈47 with Conv_Flt NOP-only matching generated count.",
    ]

    payload: dict[str, Any] = {
        "title": "MSCRENOPICK_TRANSPORT_CONSERVATION",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": str(REPO),
        "machine": MACHINE,
        "run_dir": str(run_dir),
        "l5x": str(l5x) if l5x else None,
        "build_issues": str(issues_path) if issues_path else None,
        "graph_metrics": (graph.get("metrics") or {}),
        "discovered_count": discovered_count,
        "discovered_tags": discovered_tags,
        "generated_meta": gen_meta,
        "fidelity_meta": fid_meta,
        "fidelity_error": fid_err,
        "merges_withheld_review": list(dict.fromkeys(merges_withheld)),
        "withheld_lanes": withheld_lanes,
        "counts": {c: int(counts.get(c) or 0) for c in CLASSES},
        "classified_sum": classified_sum,
        "conservation_ok": conservation_ok,
        "accounted_53": accounted_53,
        "warden_claim": WARDEN_CLAIM,
        "observed_vs_warden": observed,
        "top_reasons": top_reasons,
        "classifications": classifications,
        "routine_quality": rq,
        "routine_quality_policy": (
            "A routine that exists but is NOP-only / placeholder is NOT complete. "
            "Reported separately from conveyor conservation classes."
        ),
        "counting_notes": counting_notes,
        "outputs": {"json": str(JSON_OUT), "txt": str(TXT_OUT)},
    }

    JSON_OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    TXT_OUT.write_text(render_txt(payload), encoding="utf-8")

    summary = {
        "json": str(JSON_OUT),
        "txt": str(TXT_OUT),
        "discovered": discovered_count,
        "accounted_53": "YES" if accounted_53 else "NO",
        "conservation_ok": conservation_ok,
        "counts": payload["counts"],
        "top_reasons": top_reasons[:8],
        "routine_quality": [
            {
                "routine": f.get("routine"),
                "status": f.get("status"),
                "nop_only_rungs": f.get("nop_only_rungs"),
                "complete": f.get("complete"),
            }
            for f in rq
            if f.get("routine") in {"Conv_Flt", "Control_Station", "Stacklight", "Merge"}
        ],
        "observed_vs_warden": observed,
    }
    print(json.dumps(summary, indent=2))
    return 0 if conservation_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
