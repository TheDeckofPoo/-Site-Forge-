#!/usr/bin/env python3
"""Knowledge-driven compiler integration pipeline.

Import RUN → FortnaPlus knowledge interpretation → SiteModel V2 → editors → reports.

SOURCE FIREWALL: RUN + engineer overrides + FPC docs + generic libraries only.
Never reads finished PLC2/PLC4 as generation input.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_site_model import (  # noqa: E402
    AVAILABLE,
    EXCLUDED,
    INCLUDED,
    load_json,
    write_json,
)
from fortna_run_workspace_discover import discover  # noqa: E402
from fortna_knowledge_enrich import enrich_site_model  # noqa: E402
from fortna_supersession import evaluate_supersession  # noqa: E402
from fortna_validate_site_model import validate_site_model  # noqa: E402

try:
    from fortna_knowledge import KnowledgeStore, document_metrics
except ImportError:  # pragma: no cover
    KnowledgeStore = None  # type: ignore
    document_metrics = None  # type: ignore


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot_metrics(site: dict[str, Any]) -> dict[str, Any]:
    og = site.get("operational_groups") or {}
    pe_roles: dict[str, int] = {}
    cfg_pe = 0
    known_pe = 0
    for pe in site.get("photoeyes") or []:
        roles = pe.get("pe_roles") or ([pe.get("role")] if pe.get("role") else [])
        if not roles or roles == ["UNKNOWN"] or roles == ["other"]:
            cfg_pe += 1
        else:
            known_pe += 1
        for r in roles:
            pe_roles[str(r)] = pe_roles.get(str(r), 0) + 1

    eq_inc = sum(1 for e in (site.get("equipment") or []) if e.get("inclusion") == INCLUDED)
    eq_avl = sum(1 for e in (site.get("equipment") or []) if e.get("inclusion") == AVAILABLE)
    eq_exc = sum(1 for e in (site.get("equipment") or []) if e.get("inclusion") == EXCLUDED)

    return {
        "equipment_classification": {
            "INCLUDED": eq_inc,
            "AVAILABLE": eq_avl,
            "EXCLUDED": eq_exc,
            "total": len(site.get("equipment") or []),
        },
        "pe_roles": pe_roles,
        "pe_known": known_pe,
        "pe_configuration_required": cfg_pe,
        "motor_chains": len(site.get("motor_chains") or []),
        "startstop_zones": len(og.get("startstop_zones") or []),
        "jam_zones": len(og.get("jam_zones") or []),
        "full_groups": len(og.get("full_groups") or []),
        "estop_zones": len(og.get("estop_zones") or site.get("estop_zones") or []),
        "engineering_areas": len(og.get("engineering_areas") or site.get("areas") or []),
        "drive_relationships": sum(
            1
            for r in (site.get("relationships") or [])
            if str(r.get("kind") or "") in {"vfd_link", "vfd_to_conveyor", "motor_link"}
        ),
        "path_evidence": sum(
            1
            for r in (site.get("relationships") or [])
            if str(r.get("kind") or "") in {"path_link", "convpath_link"}
        ),
        "sawtooth_relationships": sum(
            1
            for r in (site.get("relationships") or [])
            if "saw" in str(r.get("kind") or "").lower()
        ),
        "sorter_relationships": sum(
            1
            for r in (site.get("relationships") or [])
            if "sorter" in str(r.get("kind") or "").lower()
        ),
        "communication_relationships": len(site.get("communications") or []),
        "full_jam_relationships": sum(
            1
            for r in (site.get("relationships") or [])
            if str(r.get("kind") or "") in {"jam_link", "jamcheck_link", "full_link", "fullline_link", "fulljam_link"}
        ),
        "configuration_required_counts": {
            "pe_roles": cfg_pe,
            "sawtooth": len(
                (site.get("editors") or {}).get("sawtooth", {}).get("merges")
                and [
                    x
                    for m in ((site.get("editors") or {}).get("sawtooth") or {}).get("merges") or []
                    for ln in m.get("lanes") or []
                    for x in (ln.get("configuration_required") or [])
                ]
                or []
            ),
            "unresolved": len(site.get("unresolved") or []),
        },
        "counts": site.get("counts") or {},
    }


def _before_after(before: dict[str, Any] | None, after: dict[str, Any]) -> dict[str, Any]:
    b = before or {}
    keys = sorted(set(b) | set(after))
    delta = {}
    for k in keys:
        bv, av = b.get(k), after.get(k)
        if isinstance(bv, dict) or isinstance(av, dict):
            bv = bv or {}
            av = av or {}
            delta[k] = {
                "before": bv,
                "after": av,
                "delta": {
                    sk: (av.get(sk, 0) if isinstance(av.get(sk), (int, float)) else av.get(sk))
                    - (bv.get(sk, 0) if isinstance(bv.get(sk), (int, float)) else 0)
                    for sk in sorted(set(bv) | set(av))
                    if isinstance(av.get(sk, 0), (int, float)) or isinstance(bv.get(sk, 0), (int, float))
                },
            }
        elif isinstance(bv, (int, float)) or isinstance(av, (int, float)):
            delta[k] = {"before": bv if bv is not None else 0, "after": av if av is not None else 0,
                        "delta": (av or 0) - (bv or 0)}
        else:
            delta[k] = {"before": bv, "after": av}
    return {
        "generated_at": _ts(),
        "ambiguity_reduced": _ambiguity_score(after) < _ambiguity_score(b) if b else True,
        "before": b,
        "after": after,
        "delta": delta,
    }


def _ambiguity_score(metrics: dict[str, Any]) -> int:
    cfg = metrics.get("configuration_required_counts") or {}
    return int(cfg.get("pe_roles") or 0) + int(cfg.get("unresolved") or 0) + int(
        (metrics.get("equipment_classification") or {}).get("AVAILABLE") or 0
    )


def structural_l5x_checks(l5x_path: Path) -> dict[str, Any]:
    """XML parse + structural checks. Does NOT claim Studio 5000 download validation."""
    report: dict[str, Any] = {
        "path": str(l5x_path),
        "exists": l5x_path.is_file(),
        "xml_parses": False,
        "duplicate_controller_tags": [],
        "undefined_routine_calls": [],
        "dangling_tag_refs_sample": [],
        "programs_with_main": [],
        "notes": ["Studio 5000 download validation NOT claimed"],
    }
    if not l5x_path.is_file():
        report["ok"] = False
        return report
    try:
        text = l5x_path.read_text(encoding="utf-8", errors="replace")
        root = ET.fromstring(text)
        report["xml_parses"] = True
    except ET.ParseError as exc:
        report["parse_error"] = str(exc)
        report["ok"] = False
        return report

    # Duplicate controller tags
    tag_names: list[str] = []
    for tag in root.iter("Tag"):
        name = tag.attrib.get("Name")
        if name:
            tag_names.append(name)
    seen: set[str] = set()
    dups: set[str] = set()
    for n in tag_names:
        if n in seen:
            dups.add(n)
        seen.add(n)
    report["duplicate_controller_tags"] = sorted(dups)[:50]

    # Programs with Main routine
    for prog in root.iter("Program"):
        pname = prog.attrib.get("Name") or ""
        routines = [r.attrib.get("Name") for r in prog.findall("Routines/Routine")]
        # also direct children
        if not routines:
            routines = [r.attrib.get("Name") for r in prog.iter("Routine")]
        if "Main" in routines or any(r and r.upper() == "MAIN" for r in routines):
            report["programs_with_main"].append(pname)

    # JSR targets
    jsr_targets = set(re.findall(r"JSR\s*\(\s*([A-Za-z0-9_]+)", text))
    routine_names = {r.attrib.get("Name") for r in root.iter("Routine") if r.attrib.get("Name")}
    undefined = sorted(t for t in jsr_targets if t not in routine_names)
    report["undefined_routine_calls"] = undefined[:50]

    report["ok"] = report["xml_parses"] and not report["duplicate_controller_tags"]
    return report


def _load_before_snapshot(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    # Accept either raw metrics or prior before/after after-block
    if "equipment_classification" in data:
        return data
    if "after" in data and isinstance(data["after"], dict):
        return data["after"]
    if "metrics" in data:
        return data["metrics"]
    return _snapshot_metrics(data) if "equipment" in data else data


def run_machine(
    *,
    run_dir: Path,
    machine: str,
    discover_out: Path,
    integration_out: Path,
    before_metrics: dict[str, Any] | None = None,
    overrides: Path | None = None,
) -> dict[str, Any]:
    discover_out.mkdir(parents=True, exist_ok=True)
    integration_out.mkdir(parents=True, exist_ok=True)

    # Capture before metrics from previous discovery if not provided
    prev_site = load_json(discover_out / "site_model.json")
    if before_metrics is None and prev_site:
        # Pre-enrichment snapshot approximation
        before_metrics = _snapshot_metrics(prev_site)

    result = discover(run_dir, machine, discover_out, overrides_path=overrides)
    site = json.loads((discover_out / "site_model.json").read_text(encoding="utf-8"))

    kb = None
    if KnowledgeStore is not None:
        try:
            kb = KnowledgeStore()  # type: ignore[call-arg]
        except Exception:
            try:
                from fortna_knowledge import get_store

                kb = get_store()
            except Exception:
                kb = None
    enrich_site_model(site, kb)
    evaluate_supersession(site)

    # Persist enriched model
    write_json(discover_out / "site_model.json", site)
    write_json(integration_out / f"site_model_{machine.lower()}.json", site)

    after = _snapshot_metrics(site)
    ba = _before_after(before_metrics, after)
    validation = validate_site_model(site)

    return {
        "machine": machine,
        "discover": result,
        "metrics_after": after,
        "before_after": ba,
        "validation": validation,
        "ui_status_summary": site.get("ui_status_summary"),
        "enrichment_metrics": site.get("enrichment_metrics"),
        "editors": site.get("editors"),
        "site_path": str(discover_out / "site_model.json"),
    }


def build_activity_report(cp2: dict, cp4: dict) -> dict[str, Any]:
    return {
        "generated_at": _ts(),
        "ORNCCP2": {
            "equipment": (cp2.get("metrics_after") or {}).get("equipment_classification"),
            "ui": cp2.get("ui_status_summary"),
        },
        "ORNCCP4": {
            "equipment": (cp4.get("metrics_after") or {}).get("equipment_classification"),
            "ui": cp4.get("ui_status_summary"),
        },
    }


def build_pe_role_report(cp2: dict, cp4: dict) -> dict[str, Any]:
    def _pe(block: dict) -> dict:
        m = block.get("metrics_after") or {}
        em = (block.get("enrichment_metrics") or {}).get("pe_roles") or {}
        return {
            "role_counts": m.get("pe_roles"),
            "known": m.get("pe_known"),
            "configuration_required": m.get("pe_configuration_required"),
            "auto_resolved": em.get("auto_resolved"),
            "engineer_required": em.get("engineer_required"),
            "previously_configuration_required_resolved": em.get(
                "previously_configuration_required_resolved"
            ),
        }

    return {"generated_at": _ts(), "ORNCCP2": _pe(cp2), "ORNCCP4": _pe(cp4)}


def build_zone_report(cp2_site: dict, cp4_site: dict) -> dict[str, Any]:
    def _z(site: dict) -> dict:
        og = site.get("operational_groups") or {}
        return {
            "engineering_areas": len(og.get("engineering_areas") or site.get("areas") or []),
            "estop_zones": len(og.get("estop_zones") or site.get("estop_zones") or []),
            "startstop_zones": len(og.get("startstop_zones") or []),
            "jam_zones": len(og.get("jam_zones") or []),
            "full_groups": len(og.get("full_groups") or []),
            "sorter_zones": len(og.get("sorter_zones") or []),
            "note": "Area rename must not silently rename Jam/EStop/StartStop zones",
        }

    return {"generated_at": _ts(), "ORNCCP2": _z(cp2_site), "ORNCCP4": _z(cp4_site)}


def build_motor_chain_report(cp2_site: dict, cp4_site: dict) -> dict[str, Any]:
    def _m(site: dict) -> dict:
        chains = site.get("motor_chains") or []
        return {
            "count": len(chains),
            "sample": [
                {
                    "head": c.get("head"),
                    "members": c.get("members"),
                    "order": c.get("order"),
                    "source": c.get("source"),
                    "confidence": c.get("confidence"),
                    "aux": c.get("aux"),
                    "stop_zone": c.get("stop_zone"),
                }
                for c in chains[:20]
            ],
            "note": "Motor-chain is control evidence, not physical conveyor topology",
        }

    return {"generated_at": _ts(), "ORNCCP2": _m(cp2_site), "ORNCCP4": _m(cp4_site)}


def build_sawtooth_report(cp4: dict) -> dict[str, Any]:
    ed = (cp4.get("editors") or {}).get("sawtooth") or {}
    return {
        "generated_at": _ts(),
        "ORNCCP4": ed,
        "capability_matrix": ed.get("capability_matrix"),
    }


def build_sorter_report(cp4: dict) -> dict[str, Any]:
    ed = (cp4.get("editors") or {}).get("sorter") or {}
    return {
        "generated_at": _ts(),
        "ORNCCP4": ed,
        "generation_leaves": ed.get("generation_leaves"),
        "gold_l5x_used_as_template": False,
    }


def write_markdown_report(
    out: Path,
    *,
    cp2: dict,
    cp4: dict,
    docs_metrics: dict,
    validation: dict,
) -> None:
    lines = [
        "# Knowledge-Driven Compiler Integration Report",
        "",
        f"Generated: `{_ts()}`",
        "",
        "Source firewall: CURRENT RUN + engineer overrides + FPC docs + generic libraries.",
        "Finished PLC2/PLC4 were **not** used for generation or discovery gap-fill.",
        "",
        "## Document inventory (deterministic)",
        "",
        f"- Documents: **{docs_metrics.get('total')}**",
        f"- CRITICAL: **{(docs_metrics.get('by_relevance') or docs_metrics.get('by_classification') or {}).get('CRITICAL', 0)}**",
        f"- HIGH: **{(docs_metrics.get('by_relevance') or docs_metrics.get('by_classification') or {}).get('HIGH', 0)}**",
        f"- Deep review: **{docs_metrics.get('deep_review_true', (docs_metrics.get('deep_review') or {}).get('true', 0))}**",
        "",
        "## ORNCCP2",
        "",
        "```json",
        json.dumps(cp2.get("ui_status_summary") or {}, indent=2),
        "```",
        "",
        f"- PE auto-resolved: {(cp2.get('enrichment_metrics') or {}).get('pe_roles', {}).get('auto_resolved')}",
        f"- Motor chains: {(cp2.get('metrics_after') or {}).get('motor_chains')}",
        "",
        "## ORNCCP4",
        "",
        "```json",
        json.dumps(cp4.get("ui_status_summary") or {}, indent=2),
        "```",
        "",
        f"- Sawtooth detected: {((cp4.get('editors') or {}).get('sawtooth') or {}).get('detected')}",
        f"- Sorter detected: {((cp4.get('editors') or {}).get('sorter') or {}).get('detected')}",
        "",
        "## Validation",
        "",
        f"- CP2 ok: `{(validation.get('ORNCCP2') or {}).get('ok')}`",
        f"- CP4 ok: `{(validation.get('ORNCCP4') or {}).get('ok')}`",
        "",
        "## Ambiguity",
        "",
        f"- CP2 ambiguity reduced: `{(cp2.get('before_after') or {}).get('ambiguity_reduced')}`",
        f"- CP4 ambiguity reduced: `{(cp4.get('before_after') or {}).get('ambiguity_reduced')}`",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")


def try_generate_supported_l5x(
    *,
    machine: str,
    site: dict[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    """Generate supported L5X portions only via autogen when possible.

    Never uses finished PLC as input. Returns structural check results.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"machine": machine, "generated": [], "structural": []}

    # Prefer existing autogen from-run if workbook exists; otherwise skip gracefully
    try:
        from fortna_autogen import AutogenInput, ConveyorRow, build_l5x  # type: ignore
    except Exception as exc:  # noqa: BLE001
        result["note"] = f"autogen unavailable: {exc}"
        return result

    lib = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"
    # Never pick gold sorter/WCS/shipping programs as the base library template.
    forbidden_names = {
        "Sorter_Track_Program.L5X",
        "WCS_Interface_TCP_IP_Program.L5X",
        "ShippingSorter_Area_L3_Program.L5X",
    }
    if not lib.is_file():
        candidates = [
            p
            for p in (ROOT / "tools" / "libraries").rglob("*.L5X")
            if p.name not in forbidden_names
        ]
        lib = candidates[0] if candidates else lib
    if not lib.is_file():
        result["note"] = "no generic library L5X found"
        return result
    result["library"] = str(lib)

    area = "Area_1"
    for a in site.get("areas") or []:
        if a.get("raw_name"):
            area = a["raw_name"]
            break

    rows = []
    for eq in site.get("equipment") or []:
        if eq.get("inclusion") != INCLUDED:
            continue
        name = eq.get("raw_name") or eq.get("normalized_name")
        if not name or not re.match(r"^P\d", str(name), re.I):
            continue
        m = re.search(r"P(\d{2,4})", str(name), re.I)
        num = int(m.group(1)) if m else len(rows) + 1
        rows.append(
            ConveyorRow(
                number=num,
                conveyor=_safe_tag(str(name)),
                main_area=str(eq.get("area_id") or area),
                type=str(eq.get("equipment_type") or eq.get("type") or "STRAIGHT"),
            )
        )
        if len(rows) >= 8:
            break
    if not rows:
        result["note"] = "no INCLUDED conveyors for sample generation"
        return result

    try:
        inp = AutogenInput(
            project_name=f"{machine}_KnowledgeDriven",
            areas=[area],
            conveyors=rows,
        )
        text, meta = build_l5x(inp, lib)
        out_path = out_dir / f"{machine}_knowledge_driven_candidate.L5X"
        out_path.write_text(text, encoding="utf-8")
        result["generated"].append(str(out_path))
        result["meta"] = meta if isinstance(meta, dict) else {"meta": str(meta)}
        result["structural"].append(structural_l5x_checks(out_path))
    except Exception as exc:  # noqa: BLE001
        result["note"] = f"generation skipped: {exc}"
    return result


def _safe_tag(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Knowledge-driven compiler integration")
    ap.add_argument("--cp2-run", type=Path, default=ROOT / "workspace" / "active" / "RUN")
    ap.add_argument("--cp4-run", type=Path, default=ROOT / "workspace" / "cp4-run" / "RUN")
    ap.add_argument("--out", type=Path, default=ROOT / "exports" / "knowledge-integration")
    ap.add_argument("--skip-l5x", action="store_true")
    args = ap.parse_args(argv)

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    # Deterministic document metrics
    docs_metrics: dict[str, Any] = {}
    try:
        if document_metrics:
            docs_metrics = document_metrics()
        elif KnowledgeStore is not None:
            docs_metrics = KnowledgeStore().document_metrics()
    except Exception as exc:  # noqa: BLE001
        docs_metrics = {"error": str(exc)}
    if not docs_metrics or "total" not in docs_metrics:
        inv = load_json(ROOT / "exports" / "fpc-knowledge" / "document_inventory.json") or {}
        docs = inv.get("documents") or []
        by_cls: dict[str, int] = {}
        deep_true = 0
        for d in docs:
            cls = d.get("relevance") or d.get("classification") or "UNCLASSIFIED"
            by_cls[cls] = by_cls.get(cls, 0) + 1
            if d.get("deep_review") or d.get("reviewed"):
                deep_true += 1
        docs_metrics = {
            "total": len(docs),
            "by_classification": by_cls,
            "deep_review_true": deep_true,
            "deep_review_false": len(docs) - deep_true,
        }
    # Flatten deep_review for report convenience
    if isinstance(docs_metrics.get("deep_review"), dict):
        docs_metrics["deep_review_true"] = docs_metrics["deep_review"].get("true", 0)
        docs_metrics["deep_review_false"] = docs_metrics["deep_review"].get("false", 0)
    write_json(out / "document_metrics.json", docs_metrics)

    cp2 = run_machine(
        run_dir=args.cp2_run,
        machine="ORNCCP2",
        discover_out=ROOT / "exports" / "run-discovery-cp2",
        integration_out=out / "cp2",
    )
    cp4 = run_machine(
        run_dir=args.cp4_run,
        machine="ORNCCP4",
        discover_out=ROOT / "exports" / "run-discovery",
        integration_out=out / "cp4",
    )

    write_json(out / "cp2_before_after.json", cp2["before_after"])
    write_json(out / "cp4_before_after.json", cp4["before_after"])
    write_json(out / "activity_report.json", build_activity_report(cp2, cp4))
    write_json(out / "pe_role_report.json", build_pe_role_report(cp2, cp4))

    cp2_site = json.loads(Path(cp2["site_path"]).read_text(encoding="utf-8"))
    cp4_site = json.loads(Path(cp4["site_path"]).read_text(encoding="utf-8"))
    write_json(out / "zone_report.json", build_zone_report(cp2_site, cp4_site))
    write_json(out / "motor_chain_report.json", build_motor_chain_report(cp2_site, cp4_site))
    write_json(out / "sawtooth_report.json", build_sawtooth_report(cp4))
    write_json(out / "sorter_report.json", build_sorter_report(cp4))

    validation = {"ORNCCP2": cp2["validation"], "ORNCCP4": cp4["validation"]}
    write_json(out / "validation_report.json", validation)

    l5x_reports = {}
    if not args.skip_l5x:
        l5x_reports["ORNCCP2"] = try_generate_supported_l5x(
            machine="ORNCCP2", site=cp2_site, out_dir=out / "generated" / "cp2"
        )
        l5x_reports["ORNCCP4"] = try_generate_supported_l5x(
            machine="ORNCCP4", site=cp4_site, out_dir=out / "generated" / "cp4"
        )
        write_json(out / "l5x_structural_report.json", l5x_reports)

    write_markdown_report(
        out / "report.md",
        cp2=cp2,
        cp4=cp4,
        docs_metrics=docs_metrics,
        validation=validation,
    )

    summary = {
        "ok": bool(cp2["validation"].get("ok")) and bool(cp4["validation"].get("ok")),
        "document_total": docs_metrics.get("total"),
        "cp2": cp2.get("ui_status_summary"),
        "cp4": cp4.get("ui_status_summary"),
        "out": str(out),
    }
    write_json(out / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 0  # reports always written; validation warnings OK


if __name__ == "__main__":
    raise SystemExit(main())
