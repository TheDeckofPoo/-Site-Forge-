#!/usr/bin/env python3
"""Diagnose PLC2 blind-discovery â†’ workbook â†’ L5X merge pipeline fidelity.

Loads frozen blind discovery (exports/plc2-merge-discovery), workbook
merges_2to1, and latest autogen L5X Merge_2to1 call sites. Prints one row per
discovered merge with omit_reason heuristics from fortna_transport_graph /
fortna_autogen filters.

Usage:
  python tools/diagnostics/diagnose_plc2_merge_pipeline.py
  python tools/diagnostics/diagnose_plc2_merge_pipeline.py --out exports/plc2-merge-discovery/PIPELINE_DIAGNOSTIC.md
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DISCOVERY_DIR = ROOT / "exports" / "plc2-merge-discovery"
WORKBOOK_PATH = ROOT / "workspace" / "autogen_workbook.json"
DEFAULT_OUT = DISCOVERY_DIR / "PIPELINE_DIAGNOSTIC.md"

# Pipeline drop reasons (from fortna_transport_graph.py / fortna_autogen.py)
PIPELINE_NOTES = [
    "transport_graph.analyze: topology merges require asMerge|mergeConfirmed AND >=2 inbound wires",
    "transport_graph.analyze: conv_merge palette nodes always count; non-merge nodes need the flag",
    "transport_graph.to_autogen_merges_2to1: emits all lane counts; lanes>2 kept as config-only",
    "transport_graph.apply: transport_build_graph merges dropped when discharge not in graph tag_area",
    "fortna_autogen emit: only merges_2to1 from workbook; lanes>2 skipped (codegen TBD)",
    "fortna_autogen emit: merge must resolve a name (name|merge|discharge) and area match (or blank area)",
    "discovery is frozen evidence only â€” not auto-seeded into workbook/Apply",
]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _boss_num(text: str | None) -> str:
    raw = str(text or "").strip().upper()
    if not raw:
        return ""
    m = re.search(r"(?:MERGE[_-]?|P|TOPOLOGY_P?)(\d{2,4})", raw, re.I)
    if m:
        return m.group(1)
    m = re.search(r"(\d{2,4})", raw)
    return m.group(1) if m else ""


def _norm_tag(text: str | None) -> str:
    return str(text or "").strip().upper()


def _strip_merge_suffix(text: str | None) -> str:
    t = _norm_tag(text)
    if t.endswith("_MERGE"):
        t = t[: -len("_MERGE")]
    return t


def find_discovery_report(discovery_dir: Path) -> tuple[Path | None, dict[str, Any]]:
    """Pick latest JSON under discovery_dir that carries merges + classification/PROVEN."""
    if not discovery_dir.is_dir():
        return None, {}
    candidates: list[tuple[float, Path, dict[str, Any]]] = []
    for path in discovery_dir.glob("*.json"):
        data = _load_json(path)
        if not isinstance(data, dict):
            continue
        merges = data.get("merges")
        if not isinstance(merges, list) or not merges:
            # Also accept top-level classifications bag
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "PROVEN" not in text and "classification" not in text:
                continue
            continue
        has_class = any(
            isinstance(m, dict) and (m.get("classification") or "PROVEN" in json.dumps(m))
            for m in merges
        )
        if not has_class and "PROVEN" not in path.read_text(encoding="utf-8", errors="ignore"):
            continue
        candidates.append((path.stat().st_mtime, path, data))
    if not candidates:
        # Fallback: blind_report.json even if empty merges
        fallback = discovery_dir / "blind_report.json"
        data = _load_json(fallback) or {}
        return (fallback if fallback.is_file() else None), data if isinstance(data, dict) else {}
    candidates.sort(key=lambda t: t[0], reverse=True)
    _, path, data = candidates[0]
    return path, data


def find_latest_l5x(roots: list[Path]) -> Path | None:
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        found.extend(root.glob("*.L5X"))
        found.extend(root.glob("*.l5x"))
    if not found:
        return None
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found[0]


def parse_l5x_merge_calls(l5x_path: Path | None) -> list[dict[str, str]]:
    """Extract Merge_2to1( call sites from L5X text."""
    if not l5x_path or not l5x_path.is_file():
        return []
    text = l5x_path.read_text(encoding="utf-8", errors="ignore")
    # Merge_2to1(Tag, conv_a, conv_b, conv_out, ...)
    pat = re.compile(
        r"Merge_2to1\(\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)",
        re.I,
    )
    out: list[dict[str, str]] = []
    for m in pat.finditer(text):
        tag, a, b, discharge = m.group(1), m.group(2), m.group(3), m.group(4)
        out.append(
            {
                "merge_tag": tag,
                "name": _strip_merge_suffix(tag),
                "lane_a": a[:-5] if a.upper().endswith("_CONV") else a,
                "lane_b": b[:-5] if b.upper().endswith("_CONV") else b,
                "discharge": discharge[:-5]
                if discharge.upper().endswith("_CONV")
                else discharge,
            }
        )
    return out


def workbook_merge_keys(row: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for field in ("name", "discharge", "merge"):
        v = _strip_merge_suffix(row.get(field))
        if v:
            keys.add(v)
        bn = _boss_num(row.get(field))
        if bn:
            keys.add(bn)
            keys.add(f"P{bn}")
    for field in ("lane_a", "lane_b", "lane_c"):
        v = _norm_tag(row.get(field))
        if v:
            keys.add(v)
    return {k for k in keys if k}


def discovery_merge_keys(m: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for field in ("name", "downstream", "mainLane", "inductLane", "mergeSection1", "mergeSection2", "mergeSection3"):
        v = _strip_merge_suffix(m.get(field))
        if v:
            keys.add(v)
    bn = _boss_num(m.get("bossNumber") or m.get("name"))
    if bn:
        keys.add(bn)
        keys.add(f"P{bn}")
        keys.add(f"MERGE_{bn}")
    return {k for k in keys if k}


def evidence_summary(m: dict[str, Any], limit: int = 6) -> str:
    kinds: list[str] = []
    seen: set[str] = set()
    for ev in m.get("evidence") or []:
        if not isinstance(ev, dict):
            continue
        kind = str(ev.get("kind") or "").strip()
        if not kind or kind in seen:
            continue
        seen.add(kind)
        kinds.append(kind)
        if len(kinds) >= limit:
            break
    n = len(m.get("evidence") or [])
    if not kinds:
        return f"{n} facts"
    return f"{n} facts: " + ", ".join(kinds)


def match_row(keys: set[str], rows: list[dict[str, Any]], key_fn) -> dict[str, Any] | None:
    if not keys:
        return None
    best = None
    best_score = 0
    for row in rows:
        rk = key_fn(row)
        score = len(keys & rk)
        # Prefer boss/discharge identity hits
        if score > best_score:
            best = row
            best_score = score
    return best if best_score > 0 else None


def match_l5x(keys: set[str], calls: list[dict[str, str]]) -> dict[str, str] | None:
    if not keys:
        return None
    for call in calls:
        ck = {
            _norm_tag(call.get("name")),
            _norm_tag(call.get("discharge")),
            _norm_tag(call.get("merge_tag")),
            _strip_merge_suffix(call.get("merge_tag")),
            _boss_num(call.get("name")),
            _boss_num(call.get("discharge")),
            f"P{_boss_num(call.get('name'))}" if _boss_num(call.get("name")) else "",
        }
        ck = {c for c in ck if c}
        if keys & ck:
            return call
    return None


def omit_reason(
    m: dict[str, Any],
    *,
    in_workbook: bool,
    wb_row: dict[str, Any] | None,
    in_l5x: bool,
    workbook_present: bool,
    workbook_merge_count: int,
) -> str:
    """Heuristic omit reason from known apply/emit filters (not discovery retune)."""
    if in_l5x:
        return ""
    cls = str(m.get("classification") or "").upper()
    num_inputs = m.get("numInputs")
    try:
        num_inputs_i = int(num_inputs) if num_inputs is not None else 2
    except (TypeError, ValueError):
        num_inputs_i = 2
    lanes = m.get("lanes") if isinstance(m.get("lanes"), list) else None
    lane_count = len(lanes) if lanes is not None else num_inputs_i

    if cls and cls not in {"PROVEN", "CANDIDATE"}:
        return f"classification={cls} (apply/emit consume confirmed 2:1 only via workbook)"
    if num_inputs_i != 2 and lane_count != 2:
        return f"not_2_lane (numInputs={num_inputs_i}; autogen emit skips lanes>2)"
    if not workbook_present:
        return "workbook_missing"
    if workbook_merge_count == 0:
        return (
            "not_in_workbook (merges_2to1 empty â€” discovery not auto-applied; "
            "transport_graph only emits asMerge|mergeConfirmed with >=2 inbound wires)"
        )
    if not in_workbook:
        ds = _norm_tag(m.get("downstream"))
        return (
            f"not_in_workbook (no merges_2to1 row matching boss/downstream={ds or 'â€”'}; "
            "graph Apply requires asMerge|mergeConfirmed + >=2 inbound, "
            "then discharge must remain in tag_area)"
        )
    # In workbook but not L5X
    assert wb_row is not None
    try:
        wb_lanes = int(wb_row.get("lanes") or wb_row.get("lane_count") or 2)
    except (TypeError, ValueError):
        wb_lanes = 2
    if wb_lanes > 2:
        return "in_workbook_but_lanes>2 (autogen emit skips; config-only)"
    name = str(wb_row.get("name") or wb_row.get("merge") or wb_row.get("discharge") or "").strip()
    if not name:
        return "in_workbook_but_no_name (autogen emit requires name|merge|discharge)"
    area = str(wb_row.get("area") or "").strip()
    if area:
        return (
            f"in_workbook_not_in_l5x (check area filter area={area!r} vs emitted areas; "
            "or Program pack / rebuild stale)"
        )
    return "in_workbook_not_in_l5x (blank area should emit; rebuild may be stale or export skipped merges)"


def diagnose(
    discovery_dir: Path = DISCOVERY_DIR,
    workbook_path: Path = WORKBOOK_PATH,
    l5x_roots: list[Path] | None = None,
) -> dict[str, Any]:
    disc_path, report = find_discovery_report(discovery_dir)
    merges = [m for m in (report.get("merges") or []) if isinstance(m, dict)]

    wb = _load_json(workbook_path) if workbook_path.is_file() else None
    workbook_present = isinstance(wb, dict)
    wb_merges = [
        m for m in ((wb or {}).get("merges_2to1") or [])
        if isinstance(m, dict)
    ] if workbook_present else []

    roots = l5x_roots or [ROOT / "exports" / "current", ROOT / "exports" / "autogen"]
    l5x_path = find_latest_l5x(roots)
    l5x_calls = parse_l5x_merge_calls(l5x_path)

    rows: list[dict[str, Any]] = []
    for m in merges:
        keys = discovery_merge_keys(m)
        wb_row = match_row(keys, wb_merges, workbook_merge_keys)
        l5x_hit = match_l5x(keys, l5x_calls)
        in_wb = wb_row is not None
        in_l5x = l5x_hit is not None
        reason = omit_reason(
            m,
            in_workbook=in_wb,
            wb_row=wb_row,
            in_l5x=in_l5x,
            workbook_present=workbook_present,
            workbook_merge_count=len(wb_merges),
        )
        sections = "/".join(
            str(m.get(k) or "â€”")
            for k in ("mergeSection1", "mergeSection2", "mergeSection3")
        )
        rows.append(
            {
                "id": m.get("name") or m.get("downstream") or "?",
                "classification": m.get("classification") or "",
                "type": m.get("type") or "Merge_2to1",
                "main": m.get("mainLane") or "",
                "induct": m.get("inductLane") or "",
                "sections": sections,
                "downstream": m.get("downstream") or "",
                "area": m.get("area") if m.get("area") is not None else "",
                "evidence": evidence_summary(m),
                "in_workbook": in_wb,
                "in_l5x": in_l5x,
                "omit_reason": reason,
                "workbook_name": (wb_row or {}).get("name") if wb_row else "",
                "l5x_tag": (l5x_hit or {}).get("merge_tag") if l5x_hit else "",
                "bossNumber": m.get("bossNumber") or _boss_num(m.get("name")),
                "confidence": m.get("confidence") or "",
            }
        )

    return {
        "generated_at": _utc(),
        "discovery_path": str(disc_path) if disc_path else "",
        "discovery_counts": report.get("counts") or {},
        "workbook_path": str(workbook_path) if workbook_present else "",
        "workbook_merges_2to1_count": len(wb_merges),
        "l5x_path": str(l5x_path) if l5x_path else "",
        "l5x_merge_2to1_call_sites": len(l5x_calls),
        "l5x_calls": l5x_calls,
        "pipeline_notes": PIPELINE_NOTES,
        "rows": rows,
    }


def render_markdown(diag: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# PLC2 Merge Pipeline Diagnostic")
    lines.append("")
    lines.append(f"- Generated: `{diag.get('generated_at')}`")
    lines.append(f"- Discovery: `{diag.get('discovery_path') or 'â€”'}`")
    counts = diag.get("discovery_counts") or {}
    if counts:
        lines.append(
            f"- Discovery counts: proven={counts.get('proven', 'â€”')} "
            f"candidate={counts.get('candidate', 'â€”')} "
            f"unresolved={counts.get('unresolved', 'â€”')} "
            f"total={counts.get('total', 'â€”')}"
        )
    lines.append(
        f"- Workbook: `{diag.get('workbook_path') or 'â€”'}` "
        f"(merges_2to1={diag.get('workbook_merges_2to1_count', 0)})"
    )
    lines.append(
        f"- L5X: `{diag.get('l5x_path') or 'â€”'}` "
        f"(Merge_2to1 call sites={diag.get('l5x_merge_2to1_call_sites', 0)})"
    )
    lines.append("")
    lines.append("## Why merges get dropped (code filters)")
    lines.append("")
    for note in diag.get("pipeline_notes") or []:
        lines.append(f"- {note}")
    lines.append("")
    lines.append("## Diagnostic table")
    lines.append("")
    lines.append(
        "| id | class | type | main | induct | sections | downstream | area | "
        "evidence | in_wb? | in_l5x? | omit_reason |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in diag.get("rows") or []:
        def cell(v: Any, n: int = 40) -> str:
            s = str(v if v is not None else "").replace("|", "\\|").replace("\n", " ")
            return s if len(s) <= n else s[: n - 1] + "â€¦"

        lines.append(
            "| "
            + " | ".join(
                [
                    cell(r.get("id"), 28),
                    cell(r.get("classification"), 12),
                    cell(r.get("type"), 12),
                    cell(r.get("main"), 16),
                    cell(r.get("induct"), 16),
                    cell(r.get("sections"), 28),
                    cell(r.get("downstream"), 16),
                    cell(r.get("area") if r.get("area") != "" else "â€”", 12),
                    cell(r.get("evidence"), 48),
                    "yes" if r.get("in_workbook") else "no",
                    "yes" if r.get("in_l5x") else "no",
                    cell(r.get("omit_reason") or "â€”", 80),
                ]
            )
            + " |"
        )
    if not (diag.get("rows") or []):
        lines.append("| â€” | â€” | â€” | â€” | â€” | â€” | â€” | â€” | no discovery merges | â€” | â€” | â€” |")
    lines.append("")
    lines.append("## L5X call sites")
    lines.append("")
    calls = diag.get("l5x_calls") or []
    if not calls:
        lines.append("- (none)")
    else:
        for c in calls:
            lines.append(
                f"- `{c.get('merge_tag')}`: {c.get('lane_a')} / {c.get('lane_b')} â†’ {c.get('discharge')}"
            )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    rows = diag.get("rows") or []
    n = len(rows)
    n_prov = sum(1 for r in rows if str(r.get("classification")).upper() == "PROVEN")
    n_wb = sum(1 for r in rows if r.get("in_workbook"))
    n_l5x = sum(1 for r in rows if r.get("in_l5x"))
    n_omit = sum(1 for r in rows if r.get("omit_reason"))
    lines.append(f"- Discovered merges: **{n}** (PROVEN={n_prov})")
    lines.append(f"- In workbook: **{n_wb}**")
    lines.append(f"- In L5X: **{n_l5x}**")
    lines.append(f"- With omit_reason: **{n_omit}**")
    lines.append("")
    return "\n".join(lines)


def print_table(diag: dict[str, Any]) -> None:
    rows = diag.get("rows") or []
    hdr = (
        f"{'id':28} {'class':10} {'main':12} {'induct':12} {'down':12} "
        f"{'wb':3} {'l5x':3} omit_reason"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{str(r.get('id') or '')[:28]:28} "
            f"{str(r.get('classification') or '')[:10]:10} "
            f"{str(r.get('main') or '')[:12]:12} "
            f"{str(r.get('induct') or '')[:12]:12} "
            f"{str(r.get('downstream') or '')[:12]:12} "
            f"{'Y' if r.get('in_workbook') else 'N':3} "
            f"{'Y' if r.get('in_l5x') else 'N':3} "
            f"{r.get('omit_reason') or 'â€”'}"
        )
    print()
    print(
        f"discovery={diag.get('discovery_path')} | "
        f"workbook_merges={diag.get('workbook_merges_2to1_count')} | "
        f"l5x_calls={diag.get('l5x_merge_2to1_call_sites')} | "
        f"l5x={diag.get('l5x_path')}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Diagnose PLC2 merge discoveryâ†’workbookâ†’L5X pipeline")
    ap.add_argument("--discovery-dir", type=Path, default=DISCOVERY_DIR)
    ap.add_argument("--workbook", type=Path, default=WORKBOOK_PATH)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    diag = diagnose(args.discovery_dir, args.workbook)
    md = render_markdown(diag)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    # Sidecar JSON for tooling
    json_path = out_path.with_suffix(".json")
    json_path.write_text(json.dumps(diag, indent=2), encoding="utf-8")

    print_table(diag)
    print(f"Wrote {out_path}")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
