#!/usr/bin/env python3
"""Orchestrate AI I/O analyze: evidence → OpenAI → validate → evaluation report.

Advisory sidecar. Default does NOT feed the compiler.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_ai_io_evidence import build_evidence_bundle, evidence_out_dir  # noqa: E402
from fortna_ai_io_resolver import api_key_available, call_openai_resolver  # noqa: E402
from fortna_ai_io_validate import (  # noqa: E402
    compute_claim_conservation,
    enrich_conservation_with_readiness,
    validate_ai_response,
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def analyze(
    run_dir: Path | str,
    machine: str,
    *,
    project: str = "",
    analyze_all: bool = False,
    mock_response: dict[str, Any] | None = None,
    use_for_build: bool = False,
    fixture_role: str = "",
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    evidence = build_evidence_bundle(run_dir, machine, project=project)
    if fixture_role:
        evidence["fixture_role"] = fixture_role
    out_dir = evidence_out_dir(evidence.get("project") or project or "", machine)
    out_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = out_dir / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (out_dir / "raw_claims.json").write_text(
        json.dumps({"claims": evidence.get("raw_claims") or [], "count": len(evidence.get("raw_claims") or [])}, indent=2),
        encoding="utf-8",
    )

    cc = evidence.get("conservation_counts") or {}
    before_cons = enrich_conservation_with_readiness(
        compute_claim_conservation(evidence),
        configio_words=int(cc.get("configio_words") or 0),
        nonphysical_excluded=int(cc.get("nonphysical_excluded") or 0),
        fixture_role=str(evidence.get("fixture_role") or ""),
    )
    before = {
        "raw_physical_claims": before_cons["raw_physical_claims"],
        "raw_claims": before_cons["raw_physical_claims"],
        "accounted_claims": before_cons["accounted_claims"],
        "lost_claims": before_cons["lost_claims"],
        "duplicate_accounting": before_cons["duplicate_accounting"],
        "deterministic_assigned": before_cons.get("assigned", cc.get("deterministic_assigned")),
        "proven": before_cons.get("proven"),
        "deterministic_unresolved": (before_cons.get("counts") or {}).get(
            "UNRESOLVED_OWNER", cc.get("deterministic_unresolved")
        ),
        "deterministic_conflicts": (before_cons.get("counts") or {}).get(
            "OWNER_CONFLICT", cc.get("deterministic_conflicts")
        ),
        "owner_conflict": (before_cons.get("counts") or {}).get("OWNER_CONFLICT"),
        "physical_resolution_failures": (before_cons.get("counts") or {}).get(
            "physical_resolution_failure", cc.get("physical_resolution_failures")
        ),
        "ai_review_required": 0,
        "needs_resolution": before_cons["needs_resolution"],
        "conflict_channels": cc.get("conflict_channels"),
        "unresolved_points": len(evidence.get("unresolved_points") or []),
        "nonphysical_excluded": cc.get("nonphysical_excluded"),
        "conservation": before_cons["conservation"],
        "evidence_status": before_cons["evidence_status"],
        "counts": before_cons["counts"],
    }

    ai_result = call_openai_resolver(
        evidence,
        analyze_all=analyze_all,
        mock_response=mock_response,
    )
    (out_dir / "ai_response.json").write_text(json.dumps(ai_result, indent=2), encoding="utf-8")

    if ai_result.get("ok") and isinstance(ai_result.get("response"), dict):
        validated = validate_ai_response(ai_result["response"], evidence, run_dir=run_dir)
    else:
        # AI unavailable / malformed — deterministic conservation still computed
        validated = {
            "ok": True,
            "raw_claims": before["raw_physical_claims"],
            "ai_proposed": 0,
            "ai_validator_accepted": 0,
            "ai_validator_rejected": 0,
            "ai_validator_review": 0,
            "accepted": [],
            "review_required": [],
            "rejected": [],
            "warnings": [ai_result.get("error") or "AI unavailable"],
        }
        cons = enrich_conservation_with_readiness(
            compute_claim_conservation(evidence),
            configio_words=int(cc.get("configio_words") or 0),
            nonphysical_excluded=int(cc.get("nonphysical_excluded") or 0),
            fixture_role=str(evidence.get("fixture_role") or ""),
        )
        validated["lost_claims"] = cons["lost_claims"]
        validated["duplicate_accounting"] = cons["duplicate_accounting"]
        validated["accounted_claims"] = cons["accounted_claims"]
        validated["conservation"] = cons
        validated["conservation_ok"] = cons["ok"]
        validated["needs_resolution"] = cons["needs_resolution"]
        validated["evidence_status"] = cons["evidence_status"]

    (out_dir / "validated.json").write_text(json.dumps(validated, indent=2), encoding="utf-8")

    after_cons_raw = validated.get("conservation") or compute_claim_conservation(
        evidence,
        accepted=validated.get("accepted") or [],
        review_required=validated.get("review_required") or [],
        rejected=validated.get("rejected") or [],
    )
    after_cons = enrich_conservation_with_readiness(
        after_cons_raw,
        configio_words=int(cc.get("configio_words") or 0),
        nonphysical_excluded=int(cc.get("nonphysical_excluded") or 0),
        fixture_role=str(evidence.get("fixture_role") or ""),
    )
    after_counts = after_cons.get("counts") or {}
    needs = int(after_cons.get("needs_resolution") or 0)
    after = {
        "raw_physical_claims": after_cons.get("raw_physical_claims"),
        "raw_claims": after_cons.get("raw_physical_claims"),
        "accounted_claims": after_cons.get("accounted_claims"),
        "lost_claims": after_cons.get("lost_claims"),
        "duplicate_accounting": after_cons.get("duplicate_accounting"),
        "deterministic_assigned": after_counts.get("ASSIGNED"),
        "proven": after_cons.get("proven"),
        "deterministic_unresolved": after_counts.get("UNRESOLVED_OWNER"),
        "deterministic_conflicts": after_counts.get("OWNER_CONFLICT"),
        "owner_conflict": after_counts.get("OWNER_CONFLICT"),
        "physical_resolution_failures": after_counts.get("physical_resolution_failure"),
        "ai_validated_derived": after_counts.get("ai_derived")
        or validated.get("ai_validator_accepted")
        or 0,
        "ai_review_required": after_counts.get("ai_review_required")
        or validated.get("ai_validator_review")
        or 0,
        # needs_resolution includes phys_fail — REVIEW IS NOT PASS
        "needs_resolution": needs,
        "review_required": needs,
        "final_assigned_or_derived": int(after_counts.get("ASSIGNED") or 0)
        + int(after_counts.get("ai_derived") or 0),
        "conservation": after_cons.get("conservation"),
        "evidence_status": after_cons.get("evidence_status"),
        "counts": after_counts,
    }
    conservation_ok = (
        bool(after_cons.get("ok"))
        and after["lost_claims"] == 0
        and after.get("duplicate_accounting", 0) == 0
    )

    evaluation = {
        "kind": "ai_io_evaluation",
        "version": 1,
        "generated_at": _ts(),
        "project": evidence.get("project"),
        "machine": machine,
        "BEFORE_AI": before,
        "AFTER_AI": after,
        "ai_proposed": validated.get("ai_proposed"),
        "ai_validator_accepted": validated.get("ai_validator_accepted"),
        "ai_validator_rejected": validated.get("ai_validator_rejected"),
        "ai_validator_review": validated.get("ai_validator_review"),
        "lost_claims": after["lost_claims"],
        "duplicate_accounting": after.get("duplicate_accounting"),
        "accounted_claims": after.get("accounted_claims"),
        "needs_resolution": needs,
        "evidence_status": after.get("evidence_status"),
        "conservation_ok": conservation_ok,
        "token_usage": ai_result.get("usage") or {},
        "api_latency_ms": ai_result.get("latency_ms"),
        "model": ai_result.get("model"),
        "ai_ok": bool(ai_result.get("ok")),
        "ai_error": ai_result.get("error"),
        "use_for_build": bool(use_for_build),
        "compiler_advisory_only": not bool(use_for_build),
        "paths": {
            "evidence": str(evidence_path),
            "validated": str(out_dir / "validated.json"),
            "ai_response": str(out_dir / "ai_response.json"),
        },
    }
    (out_dir / "evaluation.json").write_text(json.dumps(evaluation, indent=2), encoding="utf-8")

    # Last-result stamp for Electron
    last = {
        "ok": True,
        "generated_at": _ts(),
        "machine": machine,
        "summary": {
            "raw_claims": after["raw_physical_claims"],
            "accounted_claims": after["accounted_claims"],
            "deterministically_proven": after.get("deterministic_assigned"),
            "proven": after.get("proven"),
            "ai_validated_derived": after["ai_validated_derived"],
            "needs_resolution": needs,
            "review_required": needs,
            "owner_conflict": after.get("owner_conflict"),
            "physical_resolution_failures": after.get("physical_resolution_failures"),
            "lost": after["lost_claims"],
            "duplicate_accounting": after.get("duplicate_accounting"),
            "conservation": "PASS" if conservation_ok else "FAIL",
            "evidence_status": after.get("evidence_status"),
        },
        "accepted": validated.get("accepted") or [],
        "review_required_items": validated.get("review_required") or [],
        "rejected": validated.get("rejected") or [],
        "evaluation": evaluation,
        "api_available": api_key_available(),
        "use_for_build": bool(use_for_build),
    }
    (out_dir / "last_result.json").write_text(json.dumps(last, indent=2), encoding="utf-8")
    # Also stamp workspace-level last result for IPC get
    last_root = REPO_ROOT / "exports" / "ai-io" / "last_result.json"
    last_root.parent.mkdir(parents=True, exist_ok=True)
    last_root.write_text(json.dumps(last, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "out_dir": str(out_dir),
        "summary": last["summary"],
        "api_available": api_key_available(),
        "ai_ok": bool(ai_result.get("ok")),
        "ai_error": ai_result.get("error"),
        "evaluation": evaluation,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AI I/O analyze orchestrator")
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--machine", required=True)
    ap.add_argument("--project", default="")
    ap.add_argument("--analyze-all", action="store_true")
    ap.add_argument("--mock", type=Path, default=None)
    ap.add_argument("--use-for-build", action="store_true", help="Dev opt-in; default OFF")
    ap.add_argument("--check-api", action="store_true", help="Only report API key availability")
    args = ap.parse_args(argv)
    if args.check_api:
        print(json.dumps({"ok": True, "api_available": api_key_available()}, indent=2))
        return 0
    mock = json.loads(args.mock.read_text(encoding="utf-8")) if args.mock else None
    result = analyze(
        args.run_dir,
        args.machine,
        project=args.project,
        analyze_all=args.analyze_all,
        mock_response=mock,
        use_for_build=args.use_for_build,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
