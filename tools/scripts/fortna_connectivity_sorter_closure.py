#!/usr/bin/env python3
"""Connectivity + sorter closure orchestrator.

Engineer-defined Areas/EStop defaults, connectivity fidelity validation,
sorter divert/token/offset/readiness research, studio pack refresh.

Finished PLC = validation only. Does not modify exports/cp5-blind/.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_site_model import load_json, write_json  # noqa: E402
from fortna_connectivity_validate import (  # noqa: E402
    compare_graphs,
    graph_from_l5x,
    graph_from_site_model,
    classify_transport_identity,
)
from fortna_sorter_divert_research import (  # noqa: E402
    build_token_model,
    divert_readiness_model,
    research_divert_map,
    research_track_offset,
)
from fortna_sorter_leaves import generate_sorter_leaves  # noqa: E402
from fortna_studio_preflight import preflight_l5x, write_markdown  # noqa: E402
from fortna_estop_model import build_estop_model  # noqa: E402
from fortna_site_model import ensure_default_area, ensure_default_estop_zone, SiteModel  # noqa: E402


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


ANSWER_SHEETS = {
    "CP2": Path(r"C:\Users\curtiskricke\Desktop\Autogen\ORLY_Greensboro_NC_PLC2.L5X"),
    "CP4": Path(r"C:\Users\curtiskricke\Desktop\Autogen\ORLY_Greensboro_NC_PLC4.L5X"),
    "CP5": Path(r"C:\Users\curtiskricke\Desktop\Autogen\ORLY_Greensboro_NC_PLC5.L5X"),
}

# Alternate common locations
for label, p in list(ANSWER_SHEETS.items()):
    if not p.is_file():
        alt = Path(r"C:\Users\curtiskricke\Desktop\Autogen") / f"ORLY_Greensboro_NC_{label}.L5X"
        if alt.is_file():
            ANSWER_SHEETS[label] = alt


def _load_site(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def apply_defaults_to_site(site: dict[str, Any]) -> dict[str, Any]:
    """Apply Area_1 + EStop_Zone_1 engineer defaults on a site dict copy."""
    m = SiteModel(
        machine_scope=site.get("machine_scope") or "",
        run_dir=str(site.get("run_dir") or ""),
        areas=list(site.get("areas") or []),
        equipment=list(site.get("equipment") or []),
        estop_zones=list(site.get("estop_zones") or []),
        operational_groups=dict(site.get("operational_groups") or {}),
        relationships=list(site.get("relationships") or []),
        photoeyes=list(site.get("photoeyes") or []),
        motors=list(site.get("motors") or []),
        vfds=list(site.get("vfds") or []),
        encoders=list(site.get("encoders") or []),
        sorters=list(site.get("sorters") or []),
        sawtooth_merges=list(site.get("sawtooth_merges") or []),
        scanners=list(site.get("scanners") or []),
        communications=list(site.get("communications") or []),
    )
    # Seed estop devices from legacy list for default zone assignment
    if not (m.operational_groups or {}).get("estop_devices") and m.estop_zones:
        m.operational_groups = dict(m.operational_groups or {})
        m.operational_groups["estop_devices"] = [
            {**z, "kind": "EStopDevice", "name": z.get("raw_name") or z.get("normalized_name")}
            for z in m.estop_zones
        ]
    ensure_default_area(m)
    ensure_default_estop_zone(m)
    out = m.to_dict()
    # preserve scanners etc.
    out["scanners"] = site.get("scanners") or out.get("scanners") or []
    out["editors"] = site.get("editors") or {}
    return out


def validate_pair(
    label: str,
    site: dict[str, Any],
    generated: Path | None,
    answer: Path | None,
) -> dict[str, Any]:
    site_g = graph_from_site_model(site)
    gen_g = graph_from_l5x(generated) if generated and generated.is_file() else {"nodes": [], "edges": []}
    cmp = compare_graphs(site_g, gen_g)
    report = {
        "label": label,
        "machine": site.get("machine_scope"),
        "site_vs_generated": {
            "precision": cmp["precision"],
            "recall": cmp["recall"],
            "endpoint_coverage": cmp.get("endpoint_coverage"),
            "expected_edges": cmp["expected_edges"],
            "actual_edges": cmp["actual_edges"],
            "expected_nodes": cmp.get("expected_nodes"),
            "nodes_present_in_both": cmp.get("nodes_present_in_both"),
            "correct": cmp["correctly_generated"],
            "missing": cmp["missing"],
            "extra": cmp["extra"],
            "wrong_target": cmp["wrong_target"],
            "by_class": cmp["by_class"],
            "note": cmp.get("note"),
        },
        "transport_identity": classify_transport_identity(site),
        "answer_sheet_used_for_generation": False,
    }
    if answer and answer.is_file():
        ans_g = graph_from_l5x(answer)
        report["answer_sheet_path"] = str(answer)
        report["answer_vs_generated"] = compare_graphs(ans_g, gen_g)
        # Identity compare: answer tag nodes that look like equipment
        ans_names = {n for n in ans_g.get("nodes") or [] if n.startswith("P")}
        report["transport_identity_vs_answer"] = classify_transport_identity(site, ans_names)
    return report


def sawtooth_connectivity(site: dict[str, Any], answer: Path | None) -> dict[str, Any]:
    merges = site.get("sawtooth_merges") or []
    rels = []
    for m in merges:
        name = m.get("raw_name") or m.get("normalized_name")
        if m.get("motor_io"):
            rels.append({"class": "MOTOR_OF", "from": m["motor_io"], "to": name, "kind": "saw_merge.motor"})
        if m.get("encoder"):
            rels.append({"class": "ENCODER_OF", "from": m["encoder"], "to": name, "kind": "saw_merge.encoder"})
        for ln in m.get("lanes") or []:
            if not isinstance(ln, dict):
                continue
            lname = ln.get("name")
            if ln.get("photoeye"):
                rels.append({"class": "PE_OF", "from": ln["photoeye"], "to": lname or name, "kind": "saw_lane.pe"})
            if ln.get("drive") or ln.get("vfd"):
                rels.append(
                    {
                        "class": "VFD_OF",
                        "from": ln.get("drive") or ln.get("vfd"),
                        "to": lname or name,
                        "kind": "saw_lane.vfd",
                    }
                )
            if ln.get("conveyor"):
                rels.append(
                    {
                        "class": "MEMBER_OF_MERGE",
                        "from": ln["conveyor"],
                        "to": name,
                        "kind": "saw_lane.conveyor",
                    }
                )
    expected = {"edges": rels, "nodes": []}
    # Compare to site relationship graph filtered to saw kinds
    site_g = graph_from_site_model(site)
    saw_edges = [e for e in site_g["edges"] if e["class"] in {"MEMBER_OF_MERGE", "PE_OF", "VFD_OF", "ENCODER_OF", "MOTOR_OF"}]
    cmp = compare_graphs(expected, {"edges": saw_edges})
    out = {
        "merges": len(merges),
        "expected_lane_device_edges": len(rels),
        "precision": cmp["precision"],
        "recall": cmp["recall"],
        "correct": cmp["correctly_generated"],
        "missing": cmp["missing"],
        "samples": cmp["samples"],
        "ignore_area_names": True,
        "answer_sheet_path": str(answer) if answer and answer.is_file() else None,
        "note": "Area naming differences ignored; focus lane/PE/VFD/encoder/merge relationships",
    }
    return out


def refresh_studio_pack(out_studio: Path, candidates: dict[str, Path], checklists: dict[str, Any]) -> dict[str, Any]:
    out_studio.mkdir(parents=True, exist_ok=True)
    import hashlib

    def sha(p: Path) -> str:
        h = hashlib.sha256()
        h.update(p.read_bytes())
        return h.hexdigest()

    manifest = {"generated_at": _ts(), "files": {}, "studio_import_claimed": False}
    for label, src in candidates.items():
        if not src.is_file():
            continue
        dest = out_studio / src.name
        shutil.copy2(src, dest)
        manifest["files"][dest.name] = {"sha256": sha(dest), "bytes": dest.stat().st_size, "label": label}
        pre = preflight_l5x(dest)
        write_json(out_studio / f"{label}_precheck.json", pre)
        write_markdown(pre, out_studio / f"{label}_STUDIO_IMPORT_PRECHECK.md")
        cl = checklists.get(label) or {}
        (out_studio / f"{label}_curtis_checklist.md").write_text(
            "\n".join(
                [
                    f"# Curtis checklist — {label}",
                    "",
                    f"- Studio imports? ",
                    f"- Controller verifies? ",
                    f"- Missing AOIs? ",
                    f"- Missing data types? ",
                    f"- Missing modules? ",
                    f"- Invalid tags? ",
                    f"- Invalid rung syntax? ",
                    "",
                    "## Subsystem relationship checks",
                    "",
                    f"- transport relationships: precision={cl.get('precision')} recall={cl.get('recall')}",
                    f"- PE / VFD / encoder / merge / sorter — see connectivity report",
                    "",
                    "Static precheck is **not** Studio PASS.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    (out_studio / "validation_checklist.md").write_text(
        "\n".join(
            [
                "# Studio Validation Pack",
                "",
                "Import each L5X in Studio 5000. Area/zone **names** may differ from finished PLC.",
                "Judge **equipment identity and control connections** first.",
                "",
                "## Files",
                "",
                *[f"- `{n}`" for n in manifest["files"]],
                "",
            ]
        ),
        encoding="utf-8",
    )
    write_json(out_studio / "SHA256_MANIFEST.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Connectivity + sorter closure")
    ap.add_argument("--out", type=Path, default=ROOT / "exports" / "connectivity-validation")
    ap.add_argument("--sorter-out", type=Path, default=ROOT / "exports" / "sorter-research")
    args = ap.parse_args(argv)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    sorter_out: Path = args.sorter_out
    sorter_out.mkdir(parents=True, exist_ok=True)

    sites = {
        "CP2": _load_site(ROOT / "exports" / "run-discovery-cp2" / "site_model.json"),
        "CP4": _load_site(ROOT / "exports" / "run-discovery" / "site_model.json"),
        "CP5": _load_site(ROOT / "exports" / "cp5-blind" / "site_model.json"),
    }
    gens = {
        "CP2": ROOT / "exports" / "knowledge-integration" / "generated" / "cp2" / "ORNCCP2_knowledge_driven_candidate.L5X",
        "CP4": ROOT / "exports" / "knowledge-integration" / "generated" / "cp4" / "ORNCCP4_knowledge_driven_candidate.L5X",
        "CP5": ROOT / "exports" / "cp5-gap-closure" / "generated" / "ORNCCP5_candidate_v2.L5X",
    }

    # Apply engineer defaults on working copies
    defaults_report = {}
    for label, site in list(sites.items()):
        if not site:
            continue
        updated = apply_defaults_to_site(site)
        sites[label] = updated
        write_json(out / f"{label.lower()}_site_with_defaults.json", updated)
        defaults_report[label] = {
            "area_1": any((a.get("raw_name") == "Area_1") for a in updated.get("areas") or []),
            "equipment_in_area_1": sum(
                1 for e in updated.get("equipment") or [] if e.get("area_id") == "Area_1"
            ),
            "estop_zone_1": any(
                (z.get("raw_name") == "EStop_Zone_1" or z.get("name") == "EStop_Zone_1")
                for z in (updated.get("operational_groups") or {}).get("estop_zones_operational")
                or updated.get("estop_zones")
                or []
            ),
            "estop_devices": len((updated.get("operational_groups") or {}).get("estop_devices") or []),
        }
    write_json(out / "engineer_defaults_report.json", defaults_report)

    # Connectivity reports
    connectivity = {}
    for label, site in sites.items():
        if not site:
            continue
        rep = validate_pair(label, site, gens.get(label), ANSWER_SHEETS.get(label))
        connectivity[label] = rep
        write_json(out / f"{label.lower()}_connectivity.json", rep)
    write_json(out / "summary_connectivity.json", {
        k: {
            "precision": (v.get("site_vs_generated") or {}).get("precision"),
            "recall": (v.get("site_vs_generated") or {}).get("recall"),
            "endpoint_coverage": (v.get("site_vs_generated") or {}).get("endpoint_coverage"),
            "expected_edges": (v.get("site_vs_generated") or {}).get("expected_edges"),
            "nodes_present_in_both": (v.get("site_vs_generated") or {}).get("nodes_present_in_both"),
        }
        for k, v in connectivity.items()
    })

    # Sawtooth CP4
    saw = sawtooth_connectivity(sites.get("CP4") or {}, ANSWER_SHEETS.get("CP4"))
    write_json(out / "cp4_sawtooth.json", saw)

    # Sorter research (CP5 RUN)
    cp5_run = ROOT / "workspace" / "cp5-run" / "RUN"
    divert = research_divert_map(cp5_run, "ORNCCP5")
    write_json(sorter_out / "divert_map.json", divert)
    offsets = research_track_offset(cp5_run, "ORNCCP5", divert)
    write_json(sorter_out / "track_offset_model.json", offsets)
    tokens = build_token_model(sites.get("CP5"))
    write_json(sorter_out / "token_model.json", tokens)
    readiness = divert_readiness_model(divert, sites.get("CP5"))
    write_json(sorter_out / "divert_readiness.json", readiness)

    # Sorter leaves reassessment
    leaves = generate_sorter_leaves(sites.get("CP5") or {}, out_dir=sorter_out / "leaves")
    write_json(sorter_out / "sorter_leaves_status.json", {k: v for k, v in leaves.items() if k != "tag_fragment_xml"})

    # WCS plan order
    wcs = {
        "order": [
            "message_schema",
            "route_request",
            "route_response",
            "confirmation_event",
            "transport_fifo",
            "heartbeat",
        ],
        "status": {
            "message_schema": "MODELED",
            "route_request": "CONFIGURATION_REQUIRED",
            "route_response": "NOT_SUPPORTED",
            "confirmation_event": "NOT_SUPPORTED",
            "transport_fifo": "NOT_SUPPORTED",
            "heartbeat": "NOT_SUPPORTED",
        },
        "sources": ["Machine", "MsgMap", "MsgWCS", "MsgTrack", "WCSEvents"],
        "note": "Do not clone finished PLC5 WCS_Interface_TCP_IP",
    }
    write_json(out / "wcs_plan.json", wcs)

    # Studio pack refresh
    checklists = {
        k: {
            "precision": (connectivity.get(k) or {}).get("site_vs_generated", {}).get("precision"),
            "recall": (connectivity.get(k) or {}).get("site_vs_generated", {}).get("recall"),
        }
        for k in ("CP2", "CP4", "CP5")
    }
    manifest = refresh_studio_pack(ROOT / "exports" / "studio-validation", gens, checklists)

    # Workflow proof artifact for Area/EStop
    workflow = {
        "AREA": {
            "default_area_created": all(v.get("area_1") for v in defaults_report.values()) if defaults_report else False,
            "rename": "supported via fortna_area_ops.rename_area",
            "create": "supported via fortna_area_ops.create_area",
            "move_equipment": "supported via fortna_area_ops.move_equipment",
            "regenerate": "supported via generate_area_l5x_snippet / Autogen main_area",
            "auto_inference_required": False,
        },
        "ESTOP": {
            "devices_discovered": defaults_report.get("CP5", {}).get("estop_devices"),
            "default_zone": "EStop_Zone_1",
            "split_zones": "engineer create/rename/move via SiteModel ops",
            "conveyor_assignment": "engineer assigns equipment controlled by zone",
            "regenerate": "after engineer confirms membership (safety gate)",
            "auto_reconstruction_required": False,
        },
    }
    write_json(out / "engineer_workflow.json", workflow)

    summary = {
        "generated_at": _ts(),
        "AREA": workflow["AREA"],
        "ESTOP": workflow["ESTOP"],
        "CONNECTIVITY": {
            k: {
                "precision": (connectivity.get(k) or {}).get("site_vs_generated", {}).get("precision"),
                "recall": (connectivity.get(k) or {}).get("site_vs_generated", {}).get("recall"),
                "endpoint_coverage": (connectivity.get(k) or {}).get("site_vs_generated", {}).get("endpoint_coverage"),
            }
            for k in ("CP2", "CP4", "CP5")
        },
        "SAWTOOTH": {
            "lane_device_relationship_precision": saw.get("precision"),
            "lane_device_relationship_recall": saw.get("recall"),
            "merges": saw.get("merges"),
        },
        "SORTER": {
            "encoder": "GENERATED" if "encoder_speed" in (leaves.get("generated_capability_names") or []) else "MODELED",
            "induct": "GENERATED" if "induct_detection" in (leaves.get("generated_capability_names") or []) else "MODELED",
            "scanner": "GENERATED" if "scanner_association" in (leaves.get("generated_capability_names") or []) else "MODELED",
            "token": tokens.get("generation_state"),
            "track_offset": "CONFIGURATION_REQUIRED",
            "divert_map": divert.get("counts"),
            "readiness": readiness.get("counts"),
            "trigger": "NOT_SUPPORTED",
        },
        "WCS": wcs["status"],
        "STUDIO_PACK": {
            "path": str(ROOT / "exports" / "studio-validation"),
            "files": list(manifest.get("files") or {}),
            "CP2_ready": gens["CP2"].is_file(),
            "CP4_ready": gens["CP4"].is_file(),
            "CP5_ready": gens["CP5"].is_file(),
        },
        "ready_for_architecture_review": True,
        "ready_for_main_merge": False,
    }
    write_json(out / "summary.json", summary)
    (out / "report.md").write_text(
        "# Connectivity + Sorter Closure Report\n\n```json\n"
        + json.dumps(summary, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
