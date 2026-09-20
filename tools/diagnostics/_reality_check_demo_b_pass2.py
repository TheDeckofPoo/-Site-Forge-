#!/usr/bin/env python3
"""Reality Check V1 — Demo B PASS 2 live AI Investigator (structural families).

Authorized for this hard challenge. Budget: target $0.50, hard stop $1.50.
Does NOT mutate production decoders. Does NOT assign endpoints.
Stores results as CANDIDATE_RULE only.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))

import fortna_ai_decoder_investigate as inv  # noqa: E402
from fortna_ai_decoder_investigate import (  # noqa: E402
    INVESTIGATOR_TOOLS,
    run_investigation,
)
from fortna_ai_readonly_tools import SiteForgeReadOnlyContext  # noqa: E402
from siteforge_warehouse.writer import PostgresWarehouseWriter  # noqa: E402

PASS1 = ROOT / "exports" / "demo" / "siteforge-reality-check-v1" / "HARD_BLIND" / "PASS1"
OUT = ROOT / "exports" / "demo" / "siteforge-reality-check-v1" / "HARD_BLIND" / "PASS2"
SEL = ROOT / "exports" / "demo" / "siteforge-reality-check-v1" / "hard_site_selection.json"
LOCATE = (
    ROOT
    / "exports"
    / "demo"
    / "siteforge-reality-check-v1"
    / "HARD_BLIND"
    / "run_locate.json"
)

HARD_BUDGET = 1.50
SYNTHESIS_TRIGGER = 1.20


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, str):
        path.write_text(obj if obj.endswith("\n") else obj + "\n", encoding="utf-8")
    else:
        path.write_text(
            json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )


def patch_budget() -> None:
    """Raise investigation budget for this authorized hard challenge (max $1.50)."""
    orig = inv.load_pricing

    def _load(model: str) -> dict[str, Any]:
        pricing = orig(model)
        snap = pricing["pricing_snapshot"]
        snap["investigation_session_budget_usd"] = HARD_BUDGET
        snap["synthesis_trigger_usd"] = SYNTHESIS_TRIGGER
        snap["budget_policy_note"] = (
            "Reality Check V1 hard blind: target $0.50 productive; "
            f"authorized hard stop ${HARD_BUDGET:.2f} for this challenge only."
        )
        return pricing

    inv.load_pricing = _load  # type: ignore[assignment]


def build_blind_packet(
    *,
    machine: str,
    project: str,
    archive_sha: str,
    cluster: dict,
    pass1_io: dict,
) -> dict[str, Any]:
    return {
        "investigation_id": f"REALITY_CHECK_V1_{machine}_CLUSTER_{cluster.get('cluster_key')}",
        "kind": "hard_blind_structural_family_packet",
        "machine": machine,
        "project": project,
        "archive_sha256": archive_sha,
        "question": (
            "What deterministic Fortna convention appears to explain this unresolved "
            "structural pattern? What evidence supports it? What contradicts it? "
            "Has the pattern occurred elsewhere in the corpus? What exact deterministic "
            "rule should Site Forge TEST? What would falsify the rule?\n\n"
            "You are NOT asked what PLC endpoint any claim should use. "
            "Return CANDIDATE_RULE / INSUFFICIENT_EVIDENCE / REJECTED_HYPOTHESIS only "
            "(via DecoderRuleCandidate status fields). No endpoint assignment."
        ),
        "problem_statement": (
            f"{machine} Pass1 left {pass1_io.get('needs_resolution')} claims needing "
            f"resolution (PROVEN={pass1_io.get('PROVEN')}, raw={pass1_io.get('raw')}, "
            f"conservation={pass1_io.get('conservation')}, racks={pass1_io.get('racks')}). "
            f"Primary structural family cluster_key={cluster.get('cluster_key')} "
            f"affects {cluster.get('claims_affected')} claims. "
            f"Signature={json.dumps(cluster.get('signature') or {}, sort_keys=True)}. "
            "Existing PRODUCTION_RULES exact_adapter_ip_bridge and "
            "direction_aware_bank_binding already apply where they can. "
            "Do not treat CANDIDATE_RULE panel_catalog_numeric_alpha_low_a_slot as truth. "
            "CURRENT_DECODER_OUTPUT traces are diagnostic only and cannot prove the rule "
            "they implement. REFERENCE_ORACLE / finished L5X forbidden."
        ),
        "site_summary": {
            "machine": machine,
            "project": project,
            "pass1": pass1_io,
            "cluster": {
                "cluster_key": cluster.get("cluster_key"),
                "claims_affected": cluster.get("claims_affected"),
                "signature": cluster.get("signature"),
                "claim_ids_sample": cluster.get("claim_ids_sample"),
            },
        },
        "constraints": [
            "AI investigates only; Site Forge verifies",
            "No endpoint assignment",
            "No Autogen / L5X / READY authority",
            "No production decoder mutation",
            "No auto-promotion",
            "Prefer aggregate read-only tools",
            "Work by structural family, not per I/O point",
            "PostgreSQL may supply structural corpus observations, not foreign site answers",
        ],
        "output_contract": {
            "type": "DecoderRuleCandidate",
            "allowed_status": [
                "CANDIDATE",
                "REVIEW_REQUIRED",
                "INSUFFICIENT_EVIDENCE",
            ],
            "forbidden_fields": [
                "physical_endpoint",
                "plc_channel",
                "ai_derived",
                "READY",
                "Autogen",
            ],
        },
        "available_read_only_tools": INVESTIGATOR_TOOLS,
        "evidence_rows": [],
        "configio_word_evidence": [],
    }


def map_status_to_warehouse(status: str) -> str:
    s = (status or "").upper()
    if s in {"CANDIDATE", "CANDIDATE_RULE", "REVIEW_REQUIRED"}:
        return "CANDIDATE_RULE"
    if s in {"REJECTED", "REJECTED_HYPOTHESIS"}:
        return "REJECTED_HYPOTHESIS"
    return "INSUFFICIENT_EVIDENCE"


def before_after(pass1_io: dict, candidate: dict | None, cluster: dict) -> dict:
    affected = int(cluster.get("claims_affected") or 0)
    status = str((candidate or {}).get("status") or "")
    could_cover = affected if status.upper() in {"CANDIDATE", "CANDIDATE_RULE", "REVIEW_REQUIRED"} else 0
    return {
        "kind": "before_after_investigation_comparison",
        "pass1_unchanged_production_counts": {
            "PROVEN": pass1_io.get("PROVEN"),
            "DERIVED": pass1_io.get("DERIVED"),
            "REVIEW_REQUIRED": pass1_io.get("REVIEW_REQUIRED"),
            "needs_resolution": pass1_io.get("needs_resolution"),
            "UNKNOWN": pass1_io.get("UNKNOWN"),
            "conservation": pass1_io.get("conservation"),
        },
        "candidate_potential_coverage_NOT_RESOLVED": {
            "cluster_key": cluster.get("cluster_key"),
            "claims_potentially_covered_if_promoted_later": could_cover,
            "candidate_status": status,
            "note": (
                "Do NOT call these claims resolved. Production counts remain Pass1 "
                "until rule promotion after review."
            ),
        },
    }


def main() -> int:
    patch_budget()
    sel = json.loads(SEL.read_text(encoding="utf-8"))
    locate = json.loads(LOCATE.read_text(encoding="utf-8"))
    frozen = json.loads((PASS1 / "pass1_frozen_manifest.json").read_text(encoding="utf-8"))
    clusters_doc = json.loads(
        (PASS1 / "unresolved_cluster_summary.json").read_text(encoding="utf-8")
    )
    machine = sel["selected"]["machine"]
    project = sel["selected"]["project"]
    archive_sha = sel["selected"]["archive_sha256"]
    run_dir = Path(locate["run_dir"])
    pass1_io = frozen["physical_io_snapshot"]
    clusters = clusters_doc.get("clusters") or []
    if not clusters:
        raise SystemExit("No unresolved clusters for Pass2")

    # Investigate largest cluster first
    primary = max(clusters, key=lambda c: int(c.get("claims_affected") or 0))
    OUT.mkdir(parents=True, exist_ok=True)
    session_dir = OUT / f"AI_{primary.get('cluster_key')}"
    blind = build_blind_packet(
        machine=machine,
        project=project,
        archive_sha=archive_sha,
        cluster=primary,
        pass1_io=pass1_io,
    )
    _write(OUT / "pass2_blind_packet_primary.json", blind)

    result = run_investigation(
        run_dir=run_dir,
        blind_packet=blind,
        out_dir=session_dir,
        machine=machine,
        project=project,
        investigation_id=blind["investigation_id"],
    )

    candidate = result.get("candidate") or {}
    usage = result.get("usage") or {}
    summary = result.get("summary") or {}
    cost = float(usage.get("estimated_session_cost_usd") or summary.get("estimated_session_cost_usd") or 0)

    # Proof AI did not assign endpoints
    cand_text = json.dumps(candidate, default=str)
    endpoint_hits = [
        k
        for k in (
            "physical_endpoint",
            "plc_channel",
            "ai_derived",
            '"READY"',
            "Autogen",
        )
        if k in cand_text
    ]

    # Store as CANDIDATE_RULE in PostgreSQL (METHOD metadata only)
    rule_key = (
        str(candidate.get("candidate_rule_name") or "").strip()
        or f"fisher_cc9_cluster_{primary.get('cluster_key')}"
    )
    rule_key = rule_key.lower().replace(" ", "_")[:120]
    wh_status = map_status_to_warehouse(str(candidate.get("status") or ""))
    writer = PostgresWarehouseWriter()
    writer.seed_rule_candidate(
        {
            "rule_id": rule_key,
            "rule_key": rule_key,
            "title": candidate.get("candidate_rule_name") or rule_key,
            "status": wh_status if wh_status == "CANDIDATE_RULE" else wh_status,
            "summary": candidate.get("candidate_rule_description") or "",
            "production_auto_promote": False,
            "related_forms": [primary.get("signature", {}).get("configio_form")],
            "related_modules": [],
            "evidence_tests": candidate.get("tests_required") or [],
            "honesty_notes": [
                "Reality Check V1 hard-blind Pass2 candidate — NOT production.",
                "No auto-promotion.",
                "Must not contain another site's physical endpoint as a reusable fact.",
            ],
            "meta": {
                "investigation_id": blind["investigation_id"],
                "cluster_key": primary.get("cluster_key"),
                "machine_context_only": machine,
                "claims_affected_context": primary.get("claims_affected"),
                "ai_status": candidate.get("status"),
                "estimated_session_cost_usd": cost,
            },
            "subsystem": "PHYSICAL_IO",
        }
    )

    comparison = before_after(pass1_io, candidate, primary)

    # Optional lightweight shadow note (no production mutation)
    shadow = {
        "kind": "SHADOW_CANDIDATE_OUTPUT",
        "performed": False,
        "reason": (
            "Full corpus shadow evaluator not run in this measurement pass; "
            "candidate stored for later shadow. Pass1 production counts unchanged."
        ),
        "candidate_rule_key": rule_key,
        "potential_claims_on_this_site_if_later_promoted": int(
            primary.get("claims_affected") or 0
        )
        if str(candidate.get("status") or "").upper()
        in {"CANDIDATE", "CANDIDATE_RULE", "REVIEW_REQUIRED"}
        else 0,
    }

    sessions = [
        {
            "investigation_id": blind["investigation_id"],
            "model": usage.get("model") or summary.get("model"),
            "estimated_session_cost_usd": cost,
            "hard_budget_usd": HARD_BUDGET,
            "tokens": usage.get("usage_totals") or summary.get("usage_totals"),
            "tool_calls": usage.get("tool_calls") or summary.get("tool_call_count"),
            "final_status": summary.get("final_status") or candidate.get("status"),
            "candidate_rule_name": candidate.get("candidate_rule_name"),
            "out_dir": str(session_dir),
            "endpoint_authority_hits": endpoint_hits,
            "ai_assigned_endpoints": False if not endpoint_hits else True,
        }
    ]

    md = f"""# AI Investigation Summary — Reality Check V1 Demo B PASS 2

**Machine:** `{machine}` (hard blind; selected before decoder outcome)
**Live AI:** YES (authorized)
**Production decoder mutated:** NO
**Endpoints assigned by AI:** {"NO" if not endpoint_hits else "FLAGGED — see hits"}

## Cluster

| Field | Value |
|-------|-------|
| cluster_key | `{primary.get('cluster_key')}` |
| claims_affected | {primary.get('claims_affected')} |
| signature failure | `{(primary.get('signature') or {}).get('failure_reason')}` |
| configio_form | `{(primary.get('signature') or {}).get('configio_form')}` |

## Session

| Field | Value |
|-------|-------|
| investigation_id | `{sessions[0]['investigation_id']}` |
| model | `{sessions[0]['model']}` |
| estimated cost USD | **{cost}** (hard budget {HARD_BUDGET}) |
| tool calls | {sessions[0]['tool_calls']} |
| final status | **{sessions[0]['final_status']}** |

## Candidate

- name: `{candidate.get('candidate_rule_name')}`
- description: {candidate.get('candidate_rule_description')}
- confidence: {candidate.get('confidence')}
- warehouse rule_key: `{rule_key}`
- warehouse status: `{wh_status}` (NOT promoted)

## Evidence / counterevidence (from candidate)

- observed_facts: {json.dumps(candidate.get('observed_facts') or [], default=str)[:2000]}
- supporting_examples: {json.dumps(candidate.get('supporting_examples') or [], default=str)[:1500]}
- counterexamples: {json.dumps(candidate.get('counterexamples') or [], default=str)[:1500]}
- ambiguities: {json.dumps(candidate.get('ambiguities') or [], default=str)[:1000]}

## Before / after (production counts UNCHANGED)

```json
{json.dumps(comparison, indent=2)}
```

## Notes

- Secondary clusters left for later if budget consumed by primary family.
- Shadow corpus evaluation: not fully executed; see shadow stub.
- Stopped for Curtis/Gilfoyle review — do not implement/promote from this pass alone.
"""

    _write(OUT / "AI_INVESTIGATION_SUMMARY.md", md)
    _write(OUT / "ai_sessions.json", {"sessions": sessions, "total_estimated_cost_usd": cost})
    _write(OUT / "ai_candidate.json", candidate)
    _write(OUT / "before_after_comparison.json", comparison)
    _write(OUT / "shadow_evaluation.json", shadow)
    _write(
        OUT / "pass2_manifest.json",
        {
            "kind": "demo_b_pass2_manifest",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "machine": machine,
            "archive_sha256": archive_sha,
            "live_ai_called": True,
            "production_decoder_mutated": False,
            "ai_assigned_endpoints": bool(endpoint_hits),
            "endpoint_hits": endpoint_hits,
            "estimated_session_cost_usd": cost,
            "hard_budget_usd": HARD_BUDGET,
            "warehouse_rule_seeded": rule_key,
            "warehouse_status": wh_status,
            "pass1_frozen_hashes_untouched": True,
            "sessions": sessions,
        },
    )
    print(
        json.dumps(
            {
                "out": str(OUT),
                "cost_usd": cost,
                "status": sessions[0]["final_status"],
                "rule_key": rule_key,
                "endpoint_hits": endpoint_hits,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
