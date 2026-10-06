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
        return {
            "canonical_device": d.get("canonical_name"),
            "ownership": d.get("ownership"),
            "final_status": d.get("final_status"),
            "physical_endpoint": d.get("physical_endpoint") or "",
            "word": d.get("word"),
            "bit": d.get("bit"),
            "deterministic_code": d.get("deterministic_code"),
            "reason": d.get("reason"),
            "source_evidence_count": d.get("source_evidence_count"),
            "escalation_trace": {
                "ai_api_called": (d.get("escalation_trace") or {}).get("ai_api_called"),
                "relay_called": (d.get("escalation_trace") or {}).get("relay_called"),
                "final_classification": (d.get("escalation_trace") or {}).get(
                    "final_classification"
                ),
                "engineer_confirmation_required": (d.get("escalation_trace") or {}).get(
                    "engineer_confirmation_required"
                ),
                "why_ai_not_called": (d.get("escalation_trace") or {}).get("why_ai_not_called"),
                "why_relay_not_called": (d.get("escalation_trace") or {}).get(
                    "why_relay_not_called"
                ),
            },
        }

    local_named = [
        d
        for d in (canon.get("devices") or [])
        if d.get("ownership") != "FOREIGN"
        and d.get("final_status") != "FOREIGN_CONTROLLER"
        and d.get("device_type") != "PHYSICAL_CHANNEL"
    ]
    mapped_local = [d for d in local_named if d.get("final_status") == "MAPPED"]
    unmapped_local = [d for d in local_named if d.get("final_status") != "MAPPED"]

    eng = canon.get("engineer_confirmations") or {}
    summary.update(
        {
            "source_evidence_rows": canon.get("source_evidence_rows"),
            "unique_physical_candidates": canon.get("unique_physical_candidates"),
            "unique_foreign_devices": canon.get("unique_foreign"),
            "unique_local_devices": canon.get("unique_local"),
            "unique_aliases": canon.get("unique_aliases"),
            "unique_mapped": canon.get("unique_mapped"),
            "unique_review": canon.get("unique_review"),
            "unique_unsupported": canon.get("unique_unsupported"),
            "unique_spare": canon.get("unique_spare"),
            "unique_engineer_confirmed": canon.get("unique_engineer_confirmed"),
            "LOCAL_DEVICE_RESOLUTION_PCT": canon.get("device_resolution_coverage_pct"),
            "GENERATED_IO_COVERAGE_PCT": canon.get("generated_io_coverage_pct"),
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
                "resolved_count": esc.get("ai_resolved"),
                "unresolved_count": esc.get("ai_unresolved"),
            },
            "relay_escalation": {
                "available": summary["relay"]["available"],
                "number_of_io_ambiguity_calls": esc.get("relay_calls"),
                "resolved_count": esc.get("relay_resolved"),
                "unresolved_count": esc.get("relay_unresolved"),
            },
            "engineer_confirmation": {
                "requested_count": esc.get("engineer_confirm_required"),
                "confirmed_count": eng.get("applied") or canon.get("unique_engineer_confirmed") or 0,
                "remaining_count": esc.get("engineer_confirm_required"),
                "store": eng.get("store_path"),
            },
            "prebuild_escalation_stats": {
                k: esc.get(k)
                for k in (
                    "candidates",
                    "ai_calls",
                    "ai_resolved",
                    "relay_calls",
                    "relay_resolved",
                    "engineer_confirm_required",
                    "skipped_service_unavailable",
                )
            },
            "artifacts": str(LEDGER_DIR),
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
                "ENGINEERING_RESOLUTION": summary["ENGINEERING_RESOLUTION"],
                "CURRENT_PROMOTION": summary["CURRENT_PROMOTION"],
                "LOCAL_DEVICE_RESOLUTION_PCT": summary["LOCAL_DEVICE_RESOLUTION_PCT"],
                "unique_local": summary["unique_local_devices"],
                "unique_review": summary["unique_review"],
                "critical_unresolved": summary["critical_unresolved_Safety_PB_count"],
                "ai_calls": summary["ai_escalation"]["number_of_io_ambiguity_calls"],
                "relay_calls": summary["relay_escalation"]["number_of_io_ambiguity_calls"],
                "PB6_JR": summary["PUSHBUTTONS"]["PB6_JR"]["final_status"],
                "summary": str(SUMMARY),
            },
            indent=2,
        )
    )
    return 0 if summary["SOURCE_CONSERVATION"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
