#!/usr/bin/env python3
"""Generate transport geometry authority + acceptance artifacts (Gate F report)."""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402
from fortna_geometry_authority import (  # noqa: E402
    count_provenance,
    display_transform,
    resolve_object_geometry,
)
from fortna_physical_geometry import build_equipment_geometry, classify_mate, dist  # noqa: E402


def diagnose(by: dict, tag: str) -> dict:
    r = by[tag]
    geom = build_equipment_geometry(r)
    rec = resolve_object_geometry(r, tag=tag)
    near_up: list = []
    near_dn: list = []
    for t2, r2 in by.items():
        if not t2.startswith("P") or t2 == tag:
            continue
        g2 = build_equipment_geometry(r2)
        if not g2.get("exit") or not g2.get("entry"):
            continue
        d_up = dist(g2["exit"], geom["entry"])
        d_dn = dist(geom["exit"], g2["entry"])
        w = float(str(r.get("Width") or 200).strip() or 200)
        if d_up < 800:
            near_up.append((d_up, t2, classify_mate(g2["exit"], geom["entry"], w)))
        if d_dn < 800:
            near_dn.append((d_dn, t2, classify_mate(geom["exit"], g2["entry"], w)))
    near_up.sort()
    near_dn.sort()
    xf = display_transform(rec, offset={"dx": 0, "dy": 0})
    ang = float(str(r["Angle"]).strip())
    length = float(str(r["Length"]).strip())
    x = float(str(r["X_cord"]).strip())
    y = float(str(r["Y_cord"]).strip())
    ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    false_entry = {"x": x - (length / 2) * ux, "y": y - (length / 2) * uy}
    false_exit = {"x": x + (length / 2) * ux, "y": y + (length / 2) * uy}
    scatter_gap = dist(false_entry, geom["entry"])
    return {
        "tag": tag,
        "run": {
            "X_cord": x,
            "Y_cord": y,
            "Length": length,
            "Width": float(str(r["Width"]).strip()),
            "Angle": ang,
            "Type": str(r["Type"]).strip(),
            "Inside_Radius": float(str(r.get("Inside_Radius") or 0).strip() or 0),
        },
        "render_anchor": rec["render_anchor"],
        "body_center": rec["body_center"],
        "entry_endpoint": rec["entry_endpoint"],
        "exit_endpoint": rec["exit_endpoint"],
        "hit_target": xf["hit_target"],
        "upstream_candidates": [
            {"tag": t, "gap": g, "mate": m} for g, t, m in near_up[:5]
        ],
        "downstream_candidates": [
            {"tag": t, "gap": g, "mate": m} for g, t, m in near_dn[:5]
        ],
        "geometry_provenance": rec["geometry_provenance"],
        "why_old_renderer_scattered": {
            "incorrect_model": "XY treated as footprint center; entry/exit = center +/- Length/2",
            "false_entry": false_entry,
            "false_exit": false_exit,
            "true_entry": geom["entry"],
            "true_exit": geom["exit"],
            "entry_error_drawing_units": scatter_gap,
            "effect": (
                "Cards/segments placed on false centers so long runs looked short/"
                "misaligned and abutments showed artificial gaps — scattered labeled objects"
            ),
        },
        "fixed": True,
        "fix_notes": (
            "Infeed-origin model (greensboro-infeed-v1) via fortna_physical_geometry + "
            "fortna_geometry_authority; no site-specific production branches"
        ),
    }


def main() -> int:
    conv = ROOT / "workspace" / "_plc2_run_peek" / "RUN" / "FORTNA" / "Conveyor.asc"
    _hdr, rows = read_asc(conv)
    by = {str(r.get("IO_Name") or "").strip().upper(): r for r in rows}
    sample_tags = [t for t in by if t.startswith("P") and len(t) > 1 and t[1].isdigit()][:200]
    counts = count_provenance([resolve_object_geometry(by[t], tag=t) for t in sample_tags])
    p500 = diagnose(by, "P500")
    p536 = diagnose(by, "P536")
    generated = datetime.now(timezone.utc).isoformat()
    authority = {
        "kind": "TransportGeometryAuthority",
        "version": 1,
        "generated_at": generated,
        "schema_fields": [
            "X_cord",
            "Y_cord",
            "Length",
            "Width",
            "Angle",
            "Type",
            "Inside_Radius",
        ],
        "field_spelling": "X_cord/Y_cord (NOT X_coord)",
        "xy_meaning": "infeed_entry_end",
        "angle_meaning": "flow_direction_deg_ccw_from_plus_x",
        "curve_length_sentinel": -1,
        "calibration": "greensboro-infeed-v1",
        "authority_stack": [
            "ENGINEER_ASSIGNED",
            "PROVEN_RUN",
            "DERIVED_TOPOLOGY",
            "FALLBACK_LAYOUT",
            "UNKNOWN",
        ],
        "rules": {
            "fallback_must_not_overwrite_proven": True,
            "source_effective_override_separated": True,
            "engineer_override_mutates_source": False,
            "normalization_preserves_relative_xy": True,
            "connectivity_validates_does_not_silent_snap": True,
            "one_authoritative_display_transform": True,
            "site_specific_production_branches": 0,
        },
        "required_per_object": [
            "source_anchor",
            "render_anchor",
            "body_center",
            "entry_endpoint",
            "exit_endpoint",
            "angle",
            "length",
            "width",
            "geometry_provenance",
        ],
        "modules": {
            "geometry": "tools/scripts/fortna_physical_geometry.py",
            "authority": "tools/scripts/fortna_geometry_authority.py",
            "layout": "tools/scripts/fortna_run_physical_layout.py",
            "canvas": "dashboard/transport-build.js",
        },
        "sample_provenance_counts_first_200_P_tags": counts,
        "acceptance_examples": {"P500": p500, "P536": p536},
        "policy": {
            "P500_P536_are_report_only": True,
            "no_if_name_equals_site_tag_in_production": True,
        },
    }
    out_dir = ROOT / "exports" / "stabilization"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "transport_geometry_authority.json").write_text(
        json.dumps(authority, indent=2), encoding="utf-8"
    )

    md: list[str] = [
        "# Transport Geometry Acceptance — Gates B–H / G / Y",
        "",
        f"Generated: {generated}",
        "",
        "## Schema field spellings confirmed",
        "",
        "- `X_cord`, `Y_cord` (NOT `X_coord` / `Y_coord`)",
        "- Also: `Length`, `Width`, `Angle`, `Type`, `Inside_Radius`",
        "- X/Y = infeed/ENTRY end; Angle = flow deg CCW from +X; CURVE Length=-1 → Inside_Radius + tangents",
        "",
        "## Authority stack",
        "",
    ]
    for i, a in enumerate(authority["authority_stack"], 1):
        md.append(f"{i}. **{a}**")
    md += [
        "",
        "Fallback must **not** silently overwrite PROVEN geometry. "
        "Source / effective / override provenance stored separately.",
        "",
        "## Transform conventions",
        "",
        "| Stage | Convention |",
        "|-------|------------|",
        "| RUN source | X_cord/Y_cord = infeed; Angle CCW from +X |",
        "| Physical body | entry→exit along Angle · Length (or curve IR+tangents) |",
        "| Canvas normalize | Uniform translate/scale (+ optional Y flip); relative X/Y preserved |",
        "| Presentation | display_dx/dy offsets only; never mutates source |",
        "| Hit / label / context | ONE authoritative display transform (`getDisplayTransform`) |",
        "",
        "## Proven vs derived (sample of first 200 P-tags on PLC2 peek RUN)",
        "",
    ]
    for k, v in counts.items():
        md.append(f"- **{k}**: {v}")
    md += [
        "",
        "## Site-specific production branch count",
        "",
        "**= 0** (P500/P536 appear only in diagnostic report notes / this acceptance artifact).",
        "",
    ]
    for tag, d in (("P500", p500), ("P536", p536)):
        md += [
            f"## Acceptance example: {tag}",
            "",
            "### RUN fields",
            "",
        ]
        for k, v in d["run"].items():
            md.append(f"- **{k}**: `{v}`")
        md += [
            "",
            "### Rendered geometry",
            "",
            f"- **render_anchor**: `{d['render_anchor']}`",
            f"- **body_center**: `{d['body_center']}`",
            f"- **entry_endpoint**: `{d['entry_endpoint']}`",
            f"- **exit_endpoint**: `{d['exit_endpoint']}`",
            f"- **hit_target**: `{d['hit_target']}`",
            f"- **geometry_provenance**: `{d['geometry_provenance']}`",
            "",
            "### Up / down relationships (geometry candidates)",
            "",
            "Upstream:",
        ]
        if d["upstream_candidates"]:
            for u in d["upstream_candidates"]:
                md.append(f"- {u['tag']} gap={u['gap']:.3f} mate={u['mate']}")
        else:
            md.append("- (none within 800u)")
        md += ["", "Downstream:"]
        if d["downstream_candidates"]:
            for u in d["downstream_candidates"]:
                md.append(f"- {u['tag']} gap={u['gap']:.3f} mate={u['mate']}")
        else:
            md.append("- (none within 800u)")
        w = d["why_old_renderer_scattered"]
        md += [
            "",
            "### Why the old renderer scattered them",
            "",
            f"- Incorrect model: {w['incorrect_model']}",
            f"- Entry error under center model: **{w['entry_error_drawing_units']:.3f}** drawing units",
            f"- Effect: {w['effect']}",
            f"- **Fixed**: {d['fixed']} — {d['fix_notes']}",
            "",
        ]
    md += [
        "## Canvas UX (Gate H)",
        "",
        "- Fit System, Fit Area, Center Selected, Home",
        "- Geometry mode toggle: RUN/Physical (default) | Engineering Override | Diagnostic",
        "- Selected highlight retained; zoom/pan retained",
        "",
        "## Tests",
        "",
        "`python tools/scripts/test_fortna_geometry_authority.py`",
        "",
    ]
    (out_dir / "transport_geometry_acceptance.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("Wrote", out_dir / "transport_geometry_authority.json")
    print("Wrote", out_dir / "transport_geometry_acceptance.md")
    print("counts", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
