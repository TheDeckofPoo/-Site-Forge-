#!/usr/bin/env python3
"""MSCRENOPICK I/O correctness proof — unique canonical devices + pre-build escalation.

Returns UNIQUE counts (not source-row counts), dual PASS/FAIL metrics, AI/Relay
health, and CURRENT promotion YES/NO under the 85% + critical-residual gate.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))
os.chdir(REPO)
os.environ["FORTNA_PRISM_DISABLE"] = "1"
os.environ["SITEFORGE_ESCALATION"] = "1"

OUT = REPO / "exports" / "delivery_gate_20261002"
OUT.mkdir(parents=True, exist_ok=True)
SUMMARY = OUT / "mscrenopick_io_correctness_proof.json"
LEDGER_DIR = OUT / "mscrenopick_io_correctness_ledger"


def main() -> int:
    from fortna_io_prebuild_escalation import (
        probe_escalation_services,
        run_prebuild_io_escalation,
    )
    from fortna_run_io_source_ledger import (
        build_canonical_device_ledger,
        build_source_evidence_ledger,
        write_canonical_ledger_artifacts,
        write_ledger_artifacts,
        reconcile_ledger,
    )

    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True
    ).strip()

    run_cands = list((REPO / "workspace" / "active").rglob("project.cfg"))
    if not run_cands:
        SUMMARY.write_text(
            json.dumps({"error": "no active RUN", "git_sha": git_sha}, indent=2),
            encoding="utf-8",
        )
        return 2
    run_dir = run_cands[0].parent
    map_csv = None
    builds = REPO / "workspace" / ".internal" / "builds"
    if builds.is_dir():
        for p in sorted(builds.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            cand = p / "physical_io_map.csv"
            if cand.is_file():
                map_csv = cand
                break

    summary: dict = {
        "phase": "MSCRENOPICK_IO_CORRECTNESS_PROOF",
        "git_sha": git_sha,
        "run_dir": str(run_dir),
        "physical_io_map_csv": str(map_csv) if map_csv else "",
        "root_cause_prior": (
            "Conservation alone treated evidence rows as devices and awarded "
            "false engineering coverage from REVIEW_REQUIRED / CSV self-accounting."
        ),
    }

    evidence = build_source_evidence_ledger(run_dir, "MSCRENOPICK")
    recon = reconcile_ledger(
        evidence,
        physical_io_map_csv=map_csv,
        machine="MSCRENOPICK",
    )
    write_ledger_artifacts(recon, LEDGER_DIR, stem="SOURCE_EVIDENCE_LEDGER")

    canon = build_canonical_device_ledger(
        evidence,
        machine="MSCRENOPICK",
        run_dir=run_dir,
        physical_io_map_csv=map_csv,
    )

    health = probe_escalation_services()
    summary["ai_api"] = {
        "available": "YES" if (health.get("ai_api") or {}).get("available") else "NO",
        "model": (health.get("ai_api") or {}).get("model"),
        "provider": (health.get("ai_api") or {}).get("provider"),
        "latency_ms": (health.get("ai_api") or {}).get("elapsed_ms"),
    }
    summary["relay"] = {
        "available": "YES" if (health.get("relay") or {}).get("available") else "NO",
        "model": (health.get("relay") or {}).get("model"),
        "latency_ms": (health.get("relay") or {}).get("elapsed_ms"),
        "status": (health.get("relay") or {}).get("status"),
    }
    if health.get("escalation_service_unavailable"):
        summary["escalation_service_unavailable"] = True
        summary["code"] = "ESCALATION_SERVICE_UNAVAILABLE"

    esc = run_prebuild_io_escalation(
        canon, machine="MSCRENOPICK", run_dir=run_dir, health=health
    )
    write_canonical_ledger_artifacts(canon, LEDGER_DIR)

    def _dev(name: str) -> dict:
        d = next(
            (x for x in (canon.get("devices") or []) if str(x.get("canonical_name") or "").upper() == name),
            None,
        )
        if not d:
            return {"canonical_device": name, "final_status": "ABSENT"}
        trace = d.get("escalation_trace") or {}
        return {
            "canonical_device": d.get("canonical_name"),
            "physical_or_internal": (
                "INTERNAL"
                if str(d.get("final_status") or "") == "INTERNAL_LOGICAL"
                or str(d.get("evidence_class") or "") == "INTERNAL_LOGICAL"
                else "PHYSICAL"
            ),
            "device_type": d.get("device_type"),
            "equipment_class": d.get("equipment_class"),
            "evidence_class": d.get("evidence_class"),
            "ownership": d.get("ownership"),
            "final_status": d.get("final_status"),
            "physical_endpoint": d.get("physical_endpoint") or "",
            "word": d.get("word"),
            "bit": d.get("bit"),
            "deterministic_code": d.get("deterministic_code"),
            "reason": d.get("reason"),
            "source_evidence_count": d.get("source_evidence_count"),
            "ai_conclusion": {
                "called": trace.get("ai_api_called"),
                "validation": trace.get("ai_validation"),
                "result_classification": (
                    ((trace.get("ai_result") or {}).get("response") or {}).get("classification")
                    if isinstance(trace.get("ai_result"), dict)
                    else None
                ),
            },
            "relay_conclusion": {
                "called": trace.get("relay_called"),
                "validation": trace.get("relay_validation"),
            },
            "cluster_id": trace.get("cluster_id"),
            "engineer_confirmation": d.get("engineer_confirmation"),
            "escalation_trace": {
                "ai_api_called": trace.get("ai_api_called"),
                "relay_called": trace.get("relay_called"),
                "final_classification": trace.get("final_classification"),
                "engineer_confirmation_required": trace.get(
                    "engineer_confirmation_required"
                ),
                "why_ai_not_called": trace.get("why_ai_not_called"),
                "why_relay_not_called": trace.get("why_relay_not_called"),
                "cluster_id": trace.get("cluster_id"),
                "knowledge_base_evidence": trace.get("knowledge_base_evidence"),
            },
        }

    # Workbench surface proof (list + confirm path exercised separately in proof extras)
    from fortna_io_review_workbench import build_workbench

    workbench = build_workbench(machine="MSCRENOPICK", run_dir=run_dir, include_escalation=False)

    local_named = [
        d
        for d in (canon.get("devices") or [])
        if d.get("ownership") != "FOREIGN"
        and d.get("final_status") != "FOREIGN_CONTROLLER"
        and d.get("final_status") != "INTERNAL_LOGICAL"
        and d.get("device_type") not in {"PHYSICAL_CHANNEL", "INTERNAL_LOGICAL"}
        and d.get("evidence_class") != "INTERNAL_LOGICAL"
    ]
    mapped_local = [d for d in local_named if d.get("final_status") == "MAPPED"]
    unmapped_local = [d for d in local_named if d.get("final_status") != "MAPPED"]

    eng = canon.get("engineer_confirmations") or {}
    summary.update(
        {
            "raw_source_observations": canon.get("raw_source_observations")
            or canon.get("source_evidence_rows"),
            "internal_logical_observations_excluded": canon.get(
                "unique_internal_logical"
            )
            or 0,
            "source_evidence_rows": canon.get("source_evidence_rows"),
            "unique_physical_devices": canon.get("unique_physical_devices"),
            "unique_physical_candidates": canon.get("unique_physical_candidates"),
            "proven_physical_spares": canon.get("proven_physical_spares")
            or canon.get("unique_spare"),
            "foreign_devices": canon.get("unique_foreign"),
            "mapped_physical_devices": canon.get("unique_mapped"),
            "review_physical_devices": canon.get("unique_review"),
            "unsupported_physical_devices": canon.get("unique_unsupported"),
            "unproven_channel_occupancy": canon.get("unproven_channel_occupancy"),
            "unique_foreign_devices": canon.get("unique_foreign"),
            "unique_local_devices": canon.get("unique_local"),
            "unique_aliases": canon.get("unique_aliases"),
            "unique_mapped": canon.get("unique_mapped"),
            "unique_review": canon.get("unique_review"),
            "unique_unsupported": canon.get("unique_unsupported"),
            "unique_spare": canon.get("unique_spare"),
            "unique_engineer_confirmed": canon.get("unique_engineer_confirmed"),
            # THREE SEPARATE METRICS — do not combine
            "SOURCE_CONSERVATION_PCT": canon.get("SOURCE_CONSERVATION_PCT"),
            "PHYSICAL_DEVICE_RESOLUTION_PCT": canon.get(
                "PHYSICAL_DEVICE_RESOLUTION_PCT"
            ),
            "GENERATED_PHYSICAL_IO_PCT": canon.get("GENERATED_PHYSICAL_IO_PCT"),
            # Back-compat aliases
            "LOCAL_DEVICE_RESOLUTION_PCT": canon.get("PHYSICAL_DEVICE_RESOLUTION_PCT"),
            "GENERATED_IO_COVERAGE_PCT": canon.get("GENERATED_PHYSICAL_IO_PCT"),
            "PUSHBUTTONS": {
                "PB6_JR": _dev("PB6_JR"),
                "SS13P7": _dev("SS13P7"),
                "SS13P9": _dev("SS13P9"),
            },
            "SAFETY": canon.get("safety"),
            "GENERATED_L5X": {
                "mapped_local_physical_devices": len(mapped_local),
                "unmapped_local_physical_devices": len(unmapped_local),
                "coverage_pct": round(
                    100.0 * len(mapped_local) / max(1, len(local_named)), 2
                ),
                "note": "from canonical ledger vs latest physical_io_map; full regen may differ",
            },
            "SOURCE_CONSERVATION": "PASS" if canon.get("source_conservation_ok") else "FAIL",
            "ENGINEERING_RESOLUTION": (
                "PASS" if canon.get("engineering_resolution_ok") else "FAIL"
            ),
            "ARTIFACT_AUDIT": "NOT_RUN_IN_THIS_PROOF",
            "CURRENT_PROMOTION": (
                "YES"
                if canon.get("source_conservation_ok")
                and canon.get("engineering_resolution_ok")
                else "NO"
            ),
            "critical_unresolved_Safety_PB_count": canon.get("critical_unresolved_count"),
            "critical_unresolved": canon.get("critical_unresolved"),
            "ai_escalation": {
                "available": summary["ai_api"]["available"],
                "number_of_io_ambiguity_calls": esc.get("ai_calls"),
                "cluster_ai_calls": esc.get("cluster_ai_calls"),
                "clusters_formed": esc.get("clusters_formed"),
                "resolved_count": esc.get("ai_resolved"),
                "unresolved_count": esc.get("ai_unresolved"),
            },
            "relay_escalation": {
                "available": summary["relay"]["available"],
                "number_of_io_ambiguity_calls": esc.get("relay_calls"),
                "cluster_relay_calls": esc.get("cluster_relay_calls"),
                "resolved_count": esc.get("relay_resolved"),
                "unresolved_count": esc.get("relay_unresolved"),
            },
            "engineer_confirmation": {
                "requested_count": esc.get("engineer_confirm_required"),
                "confirmed_count": eng.get("applied")
                or canon.get("unique_engineer_confirmed")
                or 0,
                "remaining_count": esc.get("engineer_confirm_required"),
                "store": eng.get("store_path"),
            },
            "engineering_review_workbench": {
                "ok": workbench.get("ok"),
                "review_count": workbench.get("review_count"),
                "critical_review_count": workbench.get("critical_review_count"),
                "editable_count": sum(
                    1 for i in (workbench.get("items") or []) if i.get("editable")
                ),
                "sample_items": [
                    i.get("canonical_name") for i in (workbench.get("items") or [])[:8]
                ],
                "confirmations_path": workbench.get("confirmations_path"),
            },
            "prebuild_escalation_stats": {
                k: esc.get(k)
                for k in (
                    "candidates",
                    "clusters_formed",
                    "cluster_ai_calls",
                    "cluster_relay_calls",
                    "ai_calls",
                    "ai_resolved",
                    "relay_calls",
                    "relay_resolved",
                    "engineer_confirm_required",
                    "skipped_service_unavailable",
                )
            },
            "artifacts": str(LEDGER_DIR),
            "fake_spare_inflation_rejected": True,
            "note_metrics": "SOURCE_CONSERVATION_PCT / PHYSICAL_DEVICE_RESOLUTION_PCT / GENERATED_PHYSICAL_IO_PCT are separate — do not combine",
        }
    )

    # Honest gate: do not claim CURRENT without engineering resolution
    summary["proof_pass_conservation"] = summary["SOURCE_CONSERVATION"] == "PASS"
    summary["proof_pass_engineering"] = summary["ENGINEERING_RESOLUTION"] == "PASS"
    summary["warden_ready_requires_push"] = True

    SUMMARY.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "SOURCE_CONSERVATION": summary["SOURCE_CONSERVATION"],
                "SOURCE_CONSERVATION_PCT": summary["SOURCE_CONSERVATION_PCT"],
                "PHYSICAL_DEVICE_RESOLUTION_PCT": summary[
                    "PHYSICAL_DEVICE_RESOLUTION_PCT"
                ],
                "GENERATED_PHYSICAL_IO_PCT": summary["GENERATED_PHYSICAL_IO_PCT"],
                "ENGINEERING_RESOLUTION": summary["ENGINEERING_RESOLUTION"],
                "CURRENT_PROMOTION": summary["CURRENT_PROMOTION"],
                "unique_physical_devices": summary["unique_physical_devices"],
                "proven_physical_spares": summary["proven_physical_spares"],
                "unproven_channel_occupancy": summary["unproven_channel_occupancy"],
                "unique_review": summary["unique_review"],
                "critical_unresolved": summary["critical_unresolved_Safety_PB_count"],
                "clusters_formed": summary["ai_escalation"].get("clusters_formed"),
                "ai_calls": summary["ai_escalation"]["number_of_io_ambiguity_calls"],
                "relay_calls": summary["relay_escalation"]["number_of_io_ambiguity_calls"],
                "workbench_review_count": summary["engineering_review_workbench"][
                    "review_count"
                ],
                "PB6_JR": summary["PUSHBUTTONS"]["PB6_JR"]["final_status"],
                "summary": str(SUMMARY),
            },
            indent=2,
        )
    )
    return 0 if summary["SOURCE_CONSERVATION"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
