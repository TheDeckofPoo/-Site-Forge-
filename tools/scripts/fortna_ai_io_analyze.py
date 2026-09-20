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
from fortna_ai_io_validate import validate_ai_response  # noqa: E402


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
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    evidence = build_evidence_bundle(run_dir, machine, project=project)
    out_dir = evidence_out_dir(evidence.get("project") or project or "", machine)
    out_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = out_dir / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (out_dir / "raw_claims.json").write_text(
        json.dumps({"claims": evidence.get("raw_claims") or [], "count": len(evidence.get("raw_claims") or [])}, indent=2),
        encoding="utf-8",
    )

    before = {
        "raw_claims": len(evidence.get("raw_claims") or []),
        "deterministic_assigned": (evidence.get("conservation_counts") or {}).get("deterministic_assigned"),
        "deterministic_unresolved": (evidence.get("conservation_counts") or {}).get("deterministic_unresolved"),
        "conflict_channels": (evidence.get("conservation_counts") or {}).get("conflict_channels"),
        "unresolved_points": len(evidence.get("unresolved_points") or []),
    }

    ai_result = call_openai_resolver(
        evidence,
        analyze_all=analyze_all,
        mock_response=mock_response,
    )
    (out_dir / "ai_response.json").write_text(json.dumps(ai_result, indent=2), encoding="utf-8")

    validated = {
        "ok": False,
        "raw_claims": before["raw_claims"],
        "ai_proposed": 0,
        "ai_validator_accepted": 0,
        "ai_validator_rejected": 0,
        "ai_validator_review": 0,
        "lost_claims": 0,
        "accepted": [],
        "review_required": [],
        "rejected": [],
    }
    if ai_result.get("ok") and isinstance(ai_result.get("response"), dict):
        validated = validate_ai_response(ai_result["response"], evidence, run_dir=run_dir)
    elif not ai_result.get("ok"):
        validated["warnings"] = [ai_result.get("error") or "AI unavailable"]

    (out_dir / "validated.json").write_text(json.dumps(validated, indent=2), encoding="utf-8")

    after = {
        "raw_claims": before["raw_claims"],
        "deterministic_assigned": before["deterministic_assigned"],
        "ai_validated_derived": validated.get("ai_validator_accepted") or 0,
        "review_required": (validated.get("ai_validator_review") or 0)
        + (before.get("deterministic_unresolved") or 0),
        "lost_claims": validated.get("lost_claims") or 0,
        "final_assigned_or_derived": int(before.get("deterministic_assigned") or 0)
        + int(validated.get("ai_validator_accepted") or 0),
    }
    conservation_ok = after["lost_claims"] == 0

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
            "raw_claims": after["raw_claims"],
            "deterministically_proven": before["deterministic_assigned"],
            "ai_validated_derived": after["ai_validated_derived"],
            "review_required": after["review_required"],
            "lost": after["lost_claims"],
            "conservation": "PASS" if conservation_ok else "FAIL",
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
