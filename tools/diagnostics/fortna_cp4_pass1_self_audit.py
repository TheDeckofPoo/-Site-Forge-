#!/usr/bin/env python3
"""CP4 Pass 1 self-audit — RUN/discovery evidence only (no finished PLC4).

Produces:
  exports/cp4-pass1/conveyor_realization_audit.json|.md
  exports/cp4-pass1/sawtooth_template_parameter_map.json

Reconciles discovery mechanical count (76) vs generated conveyors (80).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402
from fortna_run_geometry_investigate import (  # noqa: E402
    _clean,
    _is_mech_conveyor,
    _load_word_map,
    _row_on_controller,
)

CLASSES = {
    "RUN_MECHANICAL",
    "RUN_LOGICAL",
    "DERIVED_ALIAS",
    "GENERATED_HELPER",
    "DUPLICATE",
    "UNKNOWN",
}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".md":
        path.write_text(str(payload), encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def conveyor_asc_index(run_dir: Path) -> dict[str, dict[str, Any]]:
    headers, rows = read_asc(run_dir / "FORTNA" / "Conveyor.asc")
    word_map = _load_word_map(run_dir)
    by: dict[str, dict[str, Any]] = {}
    for i, r in enumerate(rows):
        name = _clean(r.get("IO_Name")).upper()
        if not name or name in by:
            continue
        by[name] = {
            "source_table": "FORTNA/Conveyor.asc",
            "source_row_index": i,
            "io_name": name,
            "type": _clean(r.get("Type")).upper(),
            "machine_name": _clean(r.get("Machine_Name")),
            "io_address_word": _clean(r.get("IO_Address_Word")),
            "in_motor_chain": _clean(r.get("In Motor Chain")),
            "x": _clean(r.get("X_cord")),
            "y": _clean(r.get("Y_cord")),
            "length": _clean(r.get("Length")),
            "is_mechanical": bool(_is_mech_conveyor(r)),
            "on_controller_ornccp4": bool(_row_on_controller(r, "ORNCCP4", word_map)),
            "general_description": _clean(r.get("General_Description")),
        }
    return by


def classify_identity(
    tag: str,
    *,
    in_discovery: bool,
    asc: dict | None,
    prefix_parent: str | None,
) -> tuple[str, str, str]:
    """Return (class, mechanical_or_logical, reason)."""
    if in_discovery and asc and asc.get("is_mechanical"):
        return (
            "RUN_MECHANICAL",
            "mechanical",
            "Present in frozen cp4-discovery mechanical equipment set",
        )
    if in_discovery:
        return (
            "RUN_LOGICAL",
            "logical",
            "Present in discovery but not classified mechanical",
        )
    # Not in discovery but generated
    if asc and asc.get("is_mechanical"):
        if prefix_parent:
            return (
                "DERIVED_ALIAS",
                "mechanical_asc_row_not_cp4_owned",
                f"Conveyor.asc mechanical row exists but discovery excluded it; "
                f"Pass1 kept it from load_from_run via prefix linkage to {prefix_parent} "
                f"(Machine_Name={asc.get('machine_name')!r}, IO_Address_Word={asc.get('io_address_word')!r}, "
                f"on_controller={asc.get('on_controller_ornccp4')})",
            )
        return (
            "UNKNOWN",
            "mechanical_asc_row_not_in_discovery",
            "Mechanical ASC row generated but not in discovery set; ownership path unclear",
        )
    if tag.startswith("P") and re.match(r"^P\d+", tag):
        return ("GENERATED_HELPER", "logical", "Generated helper / non-discovery identity")
    return ("UNKNOWN", "unknown", "No RUN/discovery classification")


def find_prefix_parent(tag: str, discovery_tags: set[str]) -> str | None:
    """If tag is a longer form of a discovery P-tag (P1200 vs P120), return parent."""
    # Prefer longest discovery tag that is a proper prefix of tag
    parents = [
        d
        for d in discovery_tags
        if tag != d and tag.startswith(d) and len(tag) > len(d)
    ]
    if not parents:
        return None
    parents.sort(key=len, reverse=True)
    return parents[0]


def audit_conveyors(
    *,
    discovery_dir: Path,
    pass1_dir: Path,
    run_dir: Path,
) -> dict[str, Any]:
    disc_eq = load_json(discovery_dir / "equipment.json")
    site = load_json(discovery_dir / "site_model.json")
    prov = load_json(pass1_dir / "conveyor_provenance.json")
    asc_idx = conveyor_asc_index(run_dir)

    disc_tags = {
        (e.get("conveyor_tag") or e.get("tag") or "").upper()
        for e in (disc_eq.get("equipment") or [])
        if (e.get("conveyor_tag") or e.get("tag"))
    }
    disc_by = {
        (e.get("conveyor_tag") or e.get("tag") or "").upper(): e
        for e in (disc_eq.get("equipment") or [])
        if (e.get("conveyor_tag") or e.get("tag"))
    }
    gen_tags = [
        (c.get("conveyor") or "").upper()
        for c in (prov.get("conveyors") or [])
        if c.get("conveyor")
    ]
    gen_set = set(gen_tags)

    rows = []
    for tag in sorted(gen_set | disc_tags):
        asc = asc_idx.get(tag)
        in_disc = tag in disc_tags
        generated = tag in gen_set
        parent = None if in_disc else find_prefix_parent(tag, disc_tags)
        cls, mech_log, reason = classify_identity(
            tag, in_discovery=in_disc, asc=asc, prefix_parent=parent
        )
        disc_id = None
        if in_disc:
            de = disc_by[tag]
            disc_id = {
                "conveyor_tag": de.get("conveyor_tag"),
                "equipment_type": de.get("equipment_type"),
                "ownership_provenance": de.get("ownership_provenance"),
                "has_geometry": de.get("has_geometry"),
            }
        rows.append(
            {
                "conveyor": tag,
                "source_table": (asc or {}).get("source_table") or ("discovery" if in_disc else None),
                "source_row": {
                    "index": (asc or {}).get("source_row_index"),
                    "type": (asc or {}).get("type"),
                    "machine_name": (asc or {}).get("machine_name"),
                    "io_address_word": (asc or {}).get("io_address_word"),
                    "in_motor_chain": (asc or {}).get("in_motor_chain"),
                    "on_controller_ornccp4": (asc or {}).get("on_controller_ornccp4"),
                }
                if asc
                else None,
                "source_evidence": reason,
                "discovery_equipment_identity": disc_id,
                "mechanical_or_logical": mech_log,
                "generated": generated,
                "in_discovery_mechanical": in_disc,
                "classification": cls,
                "prefix_parent_suspect": parent,
                "provenance": "RUN_EXPLICIT"
                if in_disc
                else ("RUN_DERIVED" if parent else "UNKNOWN"),
                "reason": reason
                if generated
                else "In discovery but not present in Pass1 generated set",
            }
        )

    extras = sorted(gen_set - disc_tags)
    missing = sorted(disc_tags - gen_set)
    class_counts = Counter(r["classification"] for r in rows if r["generated"])

    # Equation
    n_disc = len(disc_tags)
    n_gen = len(gen_set)
    legitimate_non_mech = [
        r
        for r in rows
        if r["generated"]
        and not r["in_discovery_mechanical"]
        and r["classification"] in {"RUN_LOGICAL", "GENERATED_HELPER"}
    ]
    # DERIVED_ALIAS extras are NOT legitimate additions
    unjustified = [
        r
        for r in rows
        if r["generated"]
        and not r["in_discovery_mechanical"]
        and r["classification"] in {"DERIVED_ALIAS", "DUPLICATE", "UNKNOWN"}
    ]
    excluded_non_conveyor = 0  # none removed from discovery mechanical set

    equation = {
        "discovery_mechanical": n_disc,
        "plus_legitimate_non_mechanical_generated": len(legitimate_non_mech),
        "minus_excluded_non_conveyor_mechanical": excluded_non_conveyor,
        "equals_expected": n_disc + len(legitimate_non_mech) - excluded_non_conveyor,
        "actual_generated": n_gen,
        "delta": n_gen - (n_disc + len(legitimate_non_mech) - excluded_non_conveyor),
        "unjustified_extras": [r["conveyor"] for r in unjustified],
        "proven": (n_disc + len(legitimate_non_mech) - excluded_non_conveyor) == n_gen
        and not unjustified,
    }

    acceptance = {
        "generated_conveyor_set_accepted": bool(equation["proven"]),
        "verdict": "ACCEPTED" if equation["proven"] else "NOT_ACCEPTED",
        "explanation": (
            "76 discovery mechanical + 0 legitimate non-mechanical helpers = 76, "
            f"but Pass1 generated {n_gen}. Extras {extras} are DERIVED_ALIAS "
            "inclusions from load_from_run prefix linkage (e.g. P120 → P1200), "
            "not legitimate CP4-owned discovery entities. Equation not proven."
            if not equation["proven"]
            else "Equation proven from RUN/discovery evidence."
        ),
    }

    return {
        "generated_at": _ts(),
        "finished_plc4_inspected": False,
        "source_of_truth": "CP4 RUN + exports/cp4-discovery only",
        "counts": {
            "discovery_mechanical": n_disc,
            "site_model_conveyors": len(site.get("conveyors") or []),
            "generated": n_gen,
            "extras_generated_not_in_discovery": extras,
            "discovery_missing_from_generated": missing,
            "by_classification_generated": dict(class_counts),
        },
        "equation": equation,
        "acceptance": acceptance,
        "conveyors": rows,
    }


def render_audit_md(audit: dict) -> str:
    eq = audit["equation"]
    acc = audit["acceptance"]
    lines = [
        "# CP4 Pass 1 — Conveyor Realization Audit",
        "",
        f"Generated: {audit['generated_at']}",
        "",
        "**Finished PLC4 inspected: NO**",
        "",
        "## Headline",
        "",
        f"- Discovery mechanical equipment: **{audit['counts']['discovery_mechanical']}**",
        f"- Pass1 generated conveyors: **{audit['counts']['generated']}**",
        f"- Extras (generated ∉ discovery): `{audit['counts']['extras_generated_not_in_discovery']}`",
        f"- Acceptance: **{acc['verdict']}**",
        "",
        "## Reconciliation equation",
        "",
        "```",
        f"{eq['discovery_mechanical']} discovered mechanical",
        f"+ {eq['plus_legitimate_non_mechanical_generated']} legitimate non-mechanical generated",
        f"- {eq['minus_excluded_non_conveyor_mechanical']} excluded/non-conveyor mechanical",
        f"= {eq['equals_expected']} expected",
        f"actual generated = {eq['actual_generated']}",
        f"delta = {eq['delta']}",
        f"proven = {eq['proven']}",
        "```",
        "",
        acc["explanation"],
        "",
        "## Why the four extras exist (RUN evidence)",
        "",
        "P1200, P1202, P1206, P1208 are **mechanical** rows in `Conveyor.asc` "
        "(STRAIGHT/BELT with X/Y/Length), but:",
        "",
        "- `Machine_Name` blank",
        "- `IO_Address_Word=6000` (placeholder — not on ORNCCP4 EIP map)",
        "- `belongs_to_controller` / discovery ownership → **excluded** from the frozen 76",
        "- Pass1 `load_from_run` still emitted them because linked-conveyor matching "
        "uses prefix rules against owned `P120` (VFD120-linked, in discovery)",
        "- `merge_discovery_conveyors` then **kept** all load_from_run rows plus discovery",
        "",
        "Classification: **DERIVED_ALIAS** (not legitimate CP4 discovery entities).",
        "",
        "Do **not** remove/add equipment solely to force 76=80. Fix ownership/merge "
        "rules in a later pass if desired; this audit only explains the delta.",
        "",
        "## Classification counts (generated)",
        "",
    ]
    for k, v in sorted((audit["counts"]["by_classification_generated"] or {}).items()):
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Per-conveyor (generated only)", "", "| Conveyor | Class | In discovery | Reason |", "|---|---|---|---|"]
    for r in audit["conveyors"]:
        if not r["generated"]:
            continue
        reason = (r.get("reason") or "").replace("|", "/")
        lines.append(
            f"| {r['conveyor']} | {r['classification']} | "
            f"{'Y' if r['in_discovery_mechanical'] else 'N'} | {reason[:120]} |"
        )
    lines.append("")
    return "\n".join(lines)


def audit_sawtooth_template(template_path: Path, sawtooth_discovery: dict) -> dict[str, Any]:
    text = template_path.read_text(encoding="utf-8", errors="replace")
    # Collect site-ish symbols from Name="..." attributes and ST identifiers
    names = set(re.findall(r'\bName="([^"]+)"', text))
    # Also bare MRG414_ / P###_ tokens in content
    tokens = set(re.findall(r"\b(?:MRG|P|PE|EZPE|ENC|VFD)\d+[A-Z0-9_]*\b", text, flags=re.I))
    symbols = sorted(names | tokens, key=str.upper)

    lane_convs = {str(l.get("conveyor") or "").upper() for l in (sawtooth_discovery.get("lanes") or [])}
    lane_pes = {str(l.get("photoeye") or "").upper() for l in (sawtooth_discovery.get("lanes") or [])}
    lane_drives = {
        str(l.get("drive") or l.get("vfd") or "").upper()
        for l in (sawtooth_discovery.get("lanes") or [])
    }
    merge = (sawtooth_discovery.get("merges") or [{}])[0]
    motor_io = str(merge.get("motor_io") or "").upper()

    items = []
    for sym in symbols:
        su = sym.upper()
        # Skip XML noise / tiny names
        if su in {"MAIN_ROUTINE", "PROGRAM", "CONTROLLER", "FALSE", "TRUE"} or len(su) < 3:
            continue
        classification = "GENERIC_KEEP"
        reason = "Looks like generic control / AOI plumbing"
        action = "keep"

        if su.startswith("MRG414") or su.startswith("MRG"):
            classification = "PARAMETERIZE_FROM_RUN"
            reason = f"Collector-prefixed symbol; RUN merge motor_io={motor_io} implies collector family — retarget map required"
            action = "parameterize"
        elif re.match(r"^P\d+", su) and ("_CONV" in su or su.endswith("_ENC") or "SAWMERGE" in su or "_HMI" in su):
            base = re.match(r"^(P\d+[A-Z]?)", su)
            base_t = base.group(1) if base else su
            if base_t in lane_convs or base_t in {"P414", "P418"}:
                classification = "PARAMETERIZE_FROM_RUN"
                reason = f"Site conveyor/HMI/enc tag in pack; map from RUN lane/collector evidence ({base_t})"
            else:
                classification = "ENGINEER_CONFIG_REQUIRED"
                reason = f"Pack conveyor-like tag {base_t} not in current RUN lane set — confirm keep/remove/retarget"
            action = "parameterize"
        elif re.match(r"^(PE|EZPE)\d+", su):
            if su in lane_pes or su.replace("EZ", "") in lane_pes:
                classification = "PARAMETERIZE_FROM_RUN"
                reason = "Lane PE present in RUN SawLane — retarget to discovery PE tags"
            else:
                classification = "ENGINEER_CONFIG_REQUIRED"
                reason = "Pack PE not listed on current RUN saw lanes — confirm"
            action = "parameterize"
        elif re.match(r"^VFD\d+", su):
            classification = "PARAMETERIZE_FROM_RUN"
            reason = "VFD symbol — bind from explicit RUN VFD/SawLane mappings"
            action = "parameterize"
        elif re.match(r"^ENC\d+", su) or su.endswith("_ENC"):
            classification = "PARAMETERIZE_FROM_RUN"
            reason = "Encoder symbol — bind ENC414/ENC424 from discovery"
            action = "parameterize"
        elif "ORLY_GREENSBORO" in su or "PLC4" in su:
            classification = "PARAMETERIZE_FROM_RUN"
            reason = "Site/controller name residue from gold pack"
            action = "parameterize"
        elif su.startswith("ENABLE_") or su.startswith("USE_"):
            classification = "ENGINEER_CONFIG_REQUIRED"
            reason = "Feature enable flag — engineer/site configuration"
            action = "configure"
        elif su.startswith("AOI_") or su in {"SLOW_FLT", "FAST_CONV"}:
            classification = "GENERIC_KEEP"
            reason = "Generic AOI / library reference"
            action = "keep"

        # Never claim REMOVE without engineer review in this audit-only pass
        if classification == "REMOVE":
            action = "remove"

        items.append(
            {
                "symbol": sym,
                "classification": classification,
                "action": action,
                "reason": reason,
            }
        )

    by_class = Counter(i["classification"] for i in items)
    return {
        "generated_at": _ts(),
        "finished_plc4_inspected": False,
        "template_path": str(template_path.relative_to(ROOT)),
        "claim": "Sawtooth program pack is NOT claimed correctly generated — parameterization pending",
        "run_sawtooth_lanes": [
            {
                "name": l.get("name"),
                "conveyor": l.get("conveyor"),
                "photoeye": l.get("photoeye"),
                "drive": l.get("drive") or l.get("vfd"),
            }
            for l in (sawtooth_discovery.get("lanes") or [])
        ],
        "run_merge": merge,
        "counts": {"symbols_inventoried": len(items), "by_classification": dict(by_class)},
        "symbols": items,
        "notes": [
            "Do not implement retargeting in this audit pass.",
            "PARAMETERIZE_FROM_RUN items need an explicit rename/bind map from discovery.",
            "GENERIC_KEEP items stay as library/control plumbing.",
            "ENGINEER_CONFIG_REQUIRED items need human confirmation before generation claims correctness.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CP4 Pass1 self-audit (no finished PLC4)")
    ap.add_argument("--discovery", default="exports/cp4-discovery")
    ap.add_argument("--pass1", default="exports/cp4-pass1")
    ap.add_argument("--run-dir", default="workspace/cp4-run/RUN")
    args = ap.parse_args(argv)

    discovery = Path(args.discovery)
    if not discovery.is_absolute():
        discovery = ROOT / discovery
    pass1 = Path(args.pass1)
    if not pass1.is_absolute():
        pass1 = ROOT / pass1
    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir

    audit = audit_conveyors(discovery_dir=discovery, pass1_dir=pass1, run_dir=run_dir)
    _write(pass1 / "conveyor_realization_audit.json", audit)
    _write(pass1 / "conveyor_realization_audit.md", render_audit_md(audit))

    saw = load_json(discovery / "sawtooth.json")
    tmpl = ROOT / "tools" / "libraries" / "programs" / "Sawtooth_Merge_Program.L5X"
    smap = audit_sawtooth_template(tmpl, saw)
    _write(pass1 / "sawtooth_template_parameter_map.json", smap)

    print(
        json.dumps(
            {
                "acceptance": audit["acceptance"]["verdict"],
                "equation": audit["equation"],
                "extras": audit["counts"]["extras_generated_not_in_discovery"],
                "sawtooth_symbols": smap["counts"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
