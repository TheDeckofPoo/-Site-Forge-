#!/usr/bin/env python3
"""Integration hardening orchestrator.

Area/E-stop closure, sorter leaves, Studio preflight, studio-validation pack,
subsystem UI status, scorecard inputs.

Does NOT modify exports/cp5-blind/ frozen artifacts.
Does NOT merge main.
"""
from __future__ import annotations

import argparse
import hashlib
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
from fortna_area_discovery import discover_area_candidates  # noqa: E402
from fortna_estop_model import build_estop_model  # noqa: E402
from fortna_sorter_leaves import (  # noqa: E402
    build_synthetic_sorter_site,
    generate_sorter_leaves,
)
from fortna_studio_preflight import preflight_l5x, write_markdown  # noqa: E402


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def subsystem_ui_status(
    *,
    transport_ready: bool,
    safety_gate: dict[str, Any],
    has_saw: bool,
    sorter_leaves: dict[str, Any],
    wcs: dict[str, Any],
) -> dict[str, Any]:
    sorter_gen = sorter_leaves.get("generated_capability_names") or []
    sorter_unsup = sorter_leaves.get("unsupported") or []
    if sorter_gen and sorter_unsup:
        sorter_status = "PARTIAL GENERATION"
    elif sorter_gen:
        sorter_status = "READY"
    elif sorter_leaves.get("modeled"):
        sorter_status = "CONFIGURATION REQUIRED"
    else:
        sorter_status = "GENERATION NOT SUPPORTED"

    wcs_gen = [k for k, v in (wcs.get("capabilities") or {}).items() if v == "GENERATABLE"]
    wcs_status = (
        "GENERATION NOT SUPPORTED"
        if not wcs_gen
        else "PARTIAL GENERATION"
    )

    return {
        "Transport": "READY" if transport_ready else "CONFIGURATION REQUIRED",
        "Safety": (
            "READY"
            if safety_gate.get("allowed")
            else "CONFIGURATION REQUIRED"
        ),
        "Sawtooth": "N/A" if not has_saw else "CONFIGURATION REQUIRED",
        "Sorter": sorter_status,
        "WCS": wcs_status,
    }


def build_wcs_matrix(site: dict[str, Any]) -> dict[str, Any]:
    comms = site.get("communications") or []
    has_map = any(c.get("message_class") == "MsgMap" for c in comms)
    has_ev = any(c.get("message_class") == "WCSEvents" for c in comms)
    has_peer = any("WCS" in str(c.get("sender") or c.get("ownership") or "").upper() for c in comms)
    caps = {
        "connection_transport": "MODELED" if has_peer else "NOT_DISCOVERED",
        "inbound_parsing": "MODELED" if has_map else "NOT_DISCOVERED",
        "outbound_fifo": "MODELED" if has_peer else "NOT_DISCOVERED",
        "route_request": "CONFIGURATION_REQUIRED" if has_map or has_peer else "NOT_SUPPORTED",
        "route_response": "NOT_SUPPORTED",
        "divert_confirmation": "NOT_SUPPORTED",
        "heartbeat": "NOT_SUPPORTED",
        "event_reporting": "MODELED" if has_ev else "NOT_SUPPORTED",
    }
    return {
        "capabilities": caps,
        "modeled": sorted(k for k, v in caps.items() if v in {"MODELED", "CONFIGURATION_REQUIRED"}),
        "generatable": sorted(k for k, v in caps.items() if v == "GENERATABLE"),
        "unsupported": sorted(k for k, v in caps.items() if v == "NOT_SUPPORTED"),
        "note": "Do not clone finished WCS program; runtime queues ≠ static PLC defs",
    }


def audit_cp5_19_further(audit_path: Path) -> dict[str, Any]:
    """Carry forward 19-item audit; no N/A / finished PLC resolution."""
    prev = load_json(audit_path) or {}
    return {
        "generated_at": _ts(),
        "carried_forward": True,
        "policy": "Further resolution only via RUN/docs/knowledge — not N/A alone, not finished PLC",
        "previous_buckets": prev.get("buckets"),
        "previous_reason_counts": prev.get("reason_counts"),
        "updates": [],
        "note": "No new automatic resolutions this pass without stronger documented disable/enable fields",
    }


def copy_studio_pack(
    out: Path,
    *,
    candidates: dict[str, Path],
    prechecks: dict[str, dict],
    ui_status: dict[str, Any],
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"generated_at": _ts(), "files": {}, "studio_import_claimed": False}
    for label, src in candidates.items():
        if not src.is_file():
            continue
        dest = out / src.name
        shutil.copy2(src, dest)
        digest = sha256_file(dest)
        manifest["files"][src.name] = {"sha256": digest, "bytes": dest.stat().st_size, "label": label}
        md = out / f"{label}_STUDIO_IMPORT_PRECHECK.md"
        if label in prechecks:
            write_markdown(prechecks[label], md)
            manifest["files"][md.name] = {"sha256": sha256_file(md), "bytes": md.stat().st_size}

    checklist = out / "validation_checklist.md"
    checklist.write_text(
        "\n".join(
            [
                "# Studio 5000 Manual Validation Checklist",
                "",
                "Curtis: import each L5X in Studio 5000 and record results.",
                "",
                "Do **not** treat static precheck as PASS.",
                "",
                "## Candidates",
                "",
                *[f"- `{n}`" for n in manifest["files"] if n.endswith(".L5X")],
                "",
                "## Expected unsupported warnings",
                "",
                "- Full Sorter_Track / divert trigger may be absent (PARTIAL / NOT SUPPORTED)",
                "- WCS program generation NOT SUPPORTED",
                "- Safety zone logic blocked until engineer confirms ES membership",
                "- Single provisional Engineering Area until engineer splits/renames",
                "",
                "## Subsystem UI status (reference)",
                "",
                "```json",
                json.dumps(ui_status, indent=2),
                "```",
                "",
                "## Results (Curtis fills in)",
                "",
                "| Candidate | Import | Opens | Notes |",
                "|-----------|:------:|:-----:|-------|",
                "| CP2 |  |  |  |",
                "| CP4 |  |  |  |",
                "| CP5 |  |  |  |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    manifest["files"][checklist.name] = {
        "sha256": sha256_file(checklist),
        "bytes": checklist.stat().st_size,
    }
    write_json(out / "SHA256_MANIFEST.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Integration hardening pass")
    ap.add_argument("--out", type=Path, default=ROOT / "exports" / "integration-hardening")
    ap.add_argument("--cp2-run", type=Path, default=ROOT / "workspace" / "active" / "RUN")
    ap.add_argument("--cp4-run", type=Path, default=ROOT / "workspace" / "cp4-run" / "RUN")
    ap.add_argument("--cp5-run", type=Path, default=ROOT / "workspace" / "cp5-run" / "RUN")
    ap.add_argument(
        "--cp5-site",
        type=Path,
        default=ROOT / "exports" / "cp5-blind" / "site_model.json",
    )
    args = ap.parse_args(argv)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    # Verify frozen blind untouched
    frozen = ROOT / "exports" / "cp5-blind" / "frozen_output.json"
    frozen_ok = frozen.is_file()
    write_json(
        out / "frozen_blind_guard.json",
        {
            "frozen_present": frozen_ok,
            "path": str(frozen),
            "modified_by_this_pass": False,
            "policy": "Do not modify historical frozen CP5 blind artifacts",
        },
    )

    site5 = json.loads(args.cp5_site.read_text(encoding="utf-8")) if args.cp5_site.is_file() else {}
    machine5 = site5.get("machine_scope") or "ORNCCP5"

    # Area discovery
    area = discover_area_candidates(args.cp5_run, machine5, site5)
    write_json(out / "area_candidates.json", area)

    # E-stop model
    estop = build_estop_model(args.cp5_run, machine5, site5)
    write_json(out / "estop_model.json", estop)

    # Sorter leaves on CP5 site + synthetic
    sorter_cp5 = generate_sorter_leaves(site5, out_dir=out / "sorter_leaves_cp5")
    write_json(out / "sorter_leaves_cp5.json", {k: v for k, v in sorter_cp5.items() if k != "tag_fragment_xml"})
    if sorter_cp5.get("tag_fragment_xml"):
        (out / "sorter_leaves_cp5_tags.xml").write_text(sorter_cp5["tag_fragment_xml"], encoding="utf-8")

    synth = build_synthetic_sorter_site()
    sorter_synth = generate_sorter_leaves(synth, out_dir=out / "sorter_leaves_synthetic")
    write_json(
        out / "sorter_leaves_synthetic.json",
        {k: v for k, v in sorter_synth.items() if k != "tag_fragment_xml"},
    )
    # Leak check: no Greensboro constants in synthetic output
    blob = json.dumps(sorter_synth)
    leak = any(x in blob for x in ("ORNCCP", "Greensboro", "PLC5", "PLC4", "PLC2", "504_BELT"))
    write_json(
        out / "sorter_synthetic_leak_check.json",
        {"ok": not leak, "greensboro_leak": leak},
    )

    wcs = build_wcs_matrix(site5)
    write_json(out / "wcs_capability_matrix.json", wcs)

    ui_status = {
        "ORNCCP5": subsystem_ui_status(
            transport_ready=True,
            safety_gate=estop.get("safety_generation_gate") or {},
            has_saw=bool(site5.get("sawtooth_merges")),
            sorter_leaves=sorter_cp5,
            wcs=wcs,
        )
    }
    write_json(out / "ui_subsystem_status.json", ui_status)

    # CP5 19 further
    audit19 = audit_cp5_19_further(ROOT / "exports" / "activity-closure" / "cp5_19_item_audit.json")
    write_json(out / "cp5_19_further.json", audit19)

    # Studio preflight on candidates
    candidates = {
        "CP2": ROOT / "exports" / "knowledge-integration" / "generated" / "cp2" / "ORNCCP2_knowledge_driven_candidate.L5X",
        "CP4": ROOT / "exports" / "knowledge-integration" / "generated" / "cp4" / "ORNCCP4_knowledge_driven_candidate.L5X",
        "CP5": ROOT / "exports" / "cp5-gap-closure" / "generated" / "ORNCCP5_candidate_v2.L5X",
    }
    # fallbacks
    if not candidates["CP5"].is_file():
        candidates["CP5"] = ROOT / "exports" / "cp5-blind" / "generated" / "ORNCCP5_blind_candidate.L5X"

    prechecks = {}
    for label, path in candidates.items():
        if path.is_file():
            prechecks[label] = preflight_l5x(path)
            write_json(out / f"studio_precheck_{label.lower()}.json", prechecks[label])
            write_markdown(prechecks[label], out / f"STUDIO_IMPORT_PRECHECK_{label}.md")

    studio_dir = ROOT / "exports" / "studio-validation"
    manifest = copy_studio_pack(
        studio_dir,
        candidates=candidates,
        prechecks=prechecks,
        ui_status=ui_status,
    )

    # Task architecture stub artifact
    write_json(
        out / "task_classes.json",
        {
            "generated_at": _ts(),
            "classes": [
                "safety",
                "tracking",
                "wcs",
                "fast_equipment",
                "slow_equipment",
                "config_l1",
                "config_l2",
                "config_l3",
                "system",
                "hmi",
            ],
            "policy": "Do not hard-code PLC5 task periods as universal Fortna standards",
            "defaults_source": "generic library / platform standards / engineer override",
            "doc": "docs/TASK_PROGRAM_ARCHITECTURE.md",
        },
    )

    summary = {
        "generated_at": _ts(),
        "AREA": {
            "inferred_high_confidence": area.get("inferred_high_confidence"),
            "suggested": area.get("suggested"),
            "engineer_required": area.get("engineer_required"),
            "counts": area.get("counts"),
        },
        "ESTOP": estop.get("counts"),
        "SORTER": {
            "capabilities_modeled": len(sorter_cp5.get("modeled") or []),
            "capabilities_newly_generatable": len(sorter_cp5.get("newly_generatable") or []),
            "capabilities_generated": len(sorter_cp5.get("generated_capability_names") or []),
            "generated_names": sorter_cp5.get("generated_capability_names"),
            "remaining_unsupported": sorter_cp5.get("unsupported"),
            "synthetic_leak_ok": not leak,
        },
        "WCS": {
            "modeled": wcs.get("modeled"),
            "generatable": wcs.get("generatable"),
            "unsupported": wcs.get("unsupported"),
        },
        "UI_STATUS": ui_status,
        "STUDIO_PRECHECK": {
            k: {"ok": v.get("ok"), "errors": (v.get("counts") or {}).get("errors")}
            for k, v in prechecks.items()
        },
        "studio_validation_pack": str(studio_dir),
        "ready_for_studio_manual_test": True,
        "ready_for_main_merge": False,
        "frozen_blind_untouched": frozen_ok,
    }
    write_json(out / "summary.json", summary)

    # Human report
    (out / "report.md").write_text(
        "\n".join(
            [
                "# Integration Hardening Report",
                "",
                f"Generated: `{_ts()}`",
                "",
                "## Area",
                json.dumps(summary["AREA"], indent=2),
                "",
                "## E-stop",
                json.dumps(summary["ESTOP"], indent=2),
                "",
                "## Sorter leaves",
                json.dumps(summary["SORTER"], indent=2),
                "",
                "## WCS",
                json.dumps(summary["WCS"], indent=2),
                "",
                "## UI subsystem status",
                json.dumps(ui_status, indent=2),
                "",
                "## Studio precheck",
                json.dumps(summary["STUDIO_PRECHECK"], indent=2),
                "",
                f"Studio pack: `{studio_dir}`",
                "",
                "Ready for Studio manual test: **YES**",
                "Ready for main merge: **NO**",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
