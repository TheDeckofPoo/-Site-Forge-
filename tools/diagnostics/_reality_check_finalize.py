#!/usr/bin/env python3
"""Assemble Reality Scorecard + three blockers + top-level summary. Measurement only."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "exports" / "demo" / "siteforge-reality-check-v1"


def load(p: Path) -> dict:
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    demo_a = load(BASE / "MSCATL_CP3" / "io_scorecard.json")
    demo_a_ready = load(BASE / "MSCATL_CP3" / "build_readiness.json")
    demo_a_comp = load(BASE / "MSCATL_CP3" / "compiler_result.json")
    pass1 = load(BASE / "HARD_BLIND" / "PASS1" / "pass1_frozen_manifest.json")
    pass1_io = pass1.get("physical_io_snapshot") or {}
    pass1_ready = load(BASE / "HARD_BLIND" / "PASS1" / "build_readiness.json")
    pass2 = load(BASE / "HARD_BLIND" / "PASS2" / "pass2_manifest.json")
    comparison = load(BASE / "HARD_BLIND" / "PASS2" / "before_after_comparison.json")
    sel = load(BASE / "hard_site_selection.json")
    baseline = load(BASE / "baseline_manifest.json")

    a_actual = (demo_a.get("actual") or {})
    sha = (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    )

    scorecard_md = f"""# REALITY SCORECARD — Site Forge Reality Check V1

**Generated:** {datetime.now(timezone.utc).isoformat()}
**Baseline SHA:** `{baseline.get('git_sha')}`
**Measurement SHA (may equal baseline if no decoder commits):** `{sha}`

No marketing language. No inflated scores. Measurement only — blockers not fixed in this task.

| subsystem | Demo A (MSCATL_CP3) | Demo B Pass1 (FISHER_CC9) | what works now | what is incomplete | principal blocker | next engineering action |
|-----------|---------------------|---------------------------|----------------|--------------------|-------------------|-------------------------|
| RUN ingestion | PASS | PASS | Virgin RUN → evidence bundle | Odd TAR members (ABS_CARD) need selective extract | Windows extract edge cases | Keep selective extract; document GUI tar pack |
| source scoping | PASS | PASS | Active vs sibling machine sources | Sibling provenance UX in GUI | — | Surface scope badges in Hardware view |
| hardware topology | PASS (3 racks, 0 unplaced) | PASS/PARTIAL ({pass1_io.get('racks')} racks) | Rack discovery + AREA_RIO_N presentation aliases | Multi-family edge cases | Unplaced / odd network devices on hard sites | Harden rack discovery on Fisher-class sites |
| physical I/O | PASS 256/256 PROVEN, conservation PASS | PARTIAL {pass1_io.get('PROVEN')}/{pass1_io.get('raw')} PROVEN; {pass1_io.get('needs_resolution')} needs_resolution | Exact IP bridge + direction-aware banks | Unbound PHYSICAL_RESOLUTION_FAILURE families | Missing Fortna binding convention(s) for Fisher cluster | Investigate/promote deterministic rule after review |
| Transportation | PARTIAL | PARTIAL | Native merge discovery exists | Virgin merge presence gaps (Demo A missing P3012A) | Merge proven≠present in L5X | Transport/merge handoff fidelity task |
| Safety | REVIEW_REQUIRED | REVIEW_REQUIRED | Fail-safe virgin (no invented members) | Engineer Apply required for membership | Virgin Safety empty by design | Engineer Safety Apply workflow / discovery honesty |
| Sorter | NOT_APPLICABLE | NOT_APPLICABLE | — | Not in these controllers' focus | — | Leave until sorter site demo |
| VFD | NOT_IMPLEMENTED | NOT_IMPLEMENTED | — | No VFD reality path exercised | VFD contract incomplete | Separate VFD task when scheduled |
| canonical model | PARTIAL | PARTIAL | Machine closure + hardware model | Full-site twin readiness | Cross-subsystem handoff | Canonical model closure task |
| compiler | L5X generated; qual FAIL; PREFLIGHT_PASS | BLOCKED (skip-generate Pass1) | Can emit L5X + static preflight | Qual gates FAIL/REVIEW on virgin | Merge/Safety/provenance gates | Do not claim READY; fix gates after prioritization |
| GUI | PARTIAL (repro pack + instructions) | NOT_APPLICABLE | Electron launch + hardware view path | Automated screenshots not captured | Browse Archive needs tar.gz | Curtis opens Launch-SiteForge with packed tar |
| PostgreSQL | PASS | PASS | Knowledge vs current-site isolation proven | Rule coverage evaluator thin | — | Keep learning separate from site facts |
| provenance | PASS (5 traces) | PARTIAL | Binding + resolver traces | Readable GUI provenance panel | — | Wire traces into GUI |
| AI Investigator | N/A (not needed) | Pass2 live: status={pass2.get('sessions',[{}])[0].get('final_status') if pass2 else 'NOT_RUN'}; cost=${pass2.get('estimated_session_cost_usd') if pass2 else 'n/a'} | Structural-family investigation; CANDIDATE only | No auto-promote; shadow incomplete | Candidate≠production | Review candidate; shadow; then decide |
| qualification | FAIL overall (honest) | REVIEW/FAIL expected | Catches merge/Safety/provenance | Virgin full-site not green | Same as Transport/Safety | Use FAIL as roadmap, do not greenwash |

## Demo A headline

- matches prior accepted: **{demo_a.get('matches_prior_accepted')}**
- actual: raw={a_actual.get('raw_physical_claims')}, PROVEN={a_actual.get('PROVEN')}, needs_resolution={a_actual.get('needs_resolution')}, racks={a_actual.get('rack_count')}, conservation={a_actual.get('conservation')}
- readiness overall: **{demo_a_ready.get('overall')}**
- compiler: L5X={demo_a_comp.get('l5x_generated')}, preflight={demo_a_comp.get('preflight_status')}, qual={demo_a_comp.get('qualification_overall')}

## Demo B headline

- selected before decode: **{sel.get('decoder_outcome_known_at_selection') is False}** — {sel.get('selected',{}).get('machine')}
- Pass1: PROVEN={pass1_io.get('PROVEN')}, needs_resolution={pass1_io.get('needs_resolution')}, racks={pass1_io.get('racks')}, conservation={pass1_io.get('conservation')}
- Pass2: live_ai={pass2.get('live_ai_called')}, decoder_mutated={pass2.get('production_decoder_mutated')}, endpoints_assigned={pass2.get('ai_assigned_endpoints')}, cost_usd={pass2.get('estimated_session_cost_usd')}

## Candidate coverage (NOT resolved)

{json.dumps(comparison.get('candidate_potential_coverage_NOT_RESOLVED') or {}, indent=2)}
"""

    blockers = {
        "kind": "three_largest_blockers",
        "goal": "engineer selects RUN archive and Site Forge builds a trustworthy PLC",
        "ranked_by": "engineering_impact",
        "blockers": [
            {
                "rank": 1,
                "title": "Physical I/O unbound families on hard sites",
                "subsystem": "physical I/O",
                "observed_failure_gap": (
                    f"FISHER_CC9 Pass1: {pass1_io.get('needs_resolution')} / "
                    f"{pass1_io.get('raw')} claims PHYSICAL_RESOLUTION_FAILURE "
                    "(95 in one UNBOUND structural family) despite conservation PASS "
                    "and strong PROVEN majority."
                ),
                "why_blocks_one_click_build": (
                    "A trustworthy PLC cannot be emitted while nearly 10% of physical "
                    "claims lack deterministic binding; UNKNOWN/REVIEW must not be "
                    "silently assigned."
                ),
                "likely_next_task": (
                    "Review Pass2 CANDIDATE_RULE; run corpus shadow; implement "
                    "deterministic rule only after promotion gate — do not site-special-case Fisher."
                ),
                "evidence_artifact": "exports/demo/siteforge-reality-check-v1/HARD_BLIND/PASS1/unresolved_cluster_summary.json",
            },
            {
                "rank": 2,
                "title": "Virgin Transport/merge handoff gaps",
                "subsystem": "Transportation / compiler qualification",
                "observed_failure_gap": (
                    "MSCATL_CP3 virgin qualify FAIL: proven merge P3012A missing from "
                    "generated L5X present set (merge check FAIL) even with Hardware/I-O PASS."
                ),
                "why_blocks_one_click_build": (
                    "Hardware readiness is necessary but not sufficient; merge/transport "
                    "omissions produce incorrect or incomplete PLC programs."
                ),
                "likely_next_task": (
                    "Dedicated virgin merge presence / transport handoff fidelity task "
                    "using qualification FAIL evidence — do not greenwash Demo A."
                ),
                "evidence_artifact": "exports/demo/siteforge-reality-check-v1/MSCATL_CP3/qualification_virgin/qualification_report.json",
            },
            {
                "rank": 3,
                "title": "Safety + cross-subsystem compile readiness",
                "subsystem": "Safety / canonical model / compiler",
                "observed_failure_gap": (
                    "Virgin Safety remains REVIEW (no invented membership); final artifact "
                    "closure REVIEW (ES_NO_SAFE_ROUTINES); overall NOT READY TO COMPILE "
                    "for one-click trustworthy build."
                ),
                "why_blocks_one_click_build": (
                    "Without honest Safety membership + handoff into Autogen, compile "
                    "either invents unsafe logic or emits an incomplete fail-safe shell."
                ),
                "likely_next_task": (
                    "Engineer Safety Apply + membership persistence / handoff hardening; "
                    "keep virgin no-invent law."
                ),
                "evidence_artifact": "exports/demo/siteforge-reality-check-v1/MSCATL_CP3/build_readiness.json",
            },
        ],
        "do_not_fix_in_this_task": True,
        "recommended_next_engineering_task": (
            "Prioritize blocker #1 candidate review + shadow for the Fisher UNBOUND "
            "family OR blocker #2 virgin merge presence — Curtis/Gilfoyle choose; "
            "do not start both blindly."
        ),
    }

    (BASE / "REALITY_SCORECARD.md").write_text(scorecard_md + "\n", encoding="utf-8")
    (BASE / "THREE_LARGEST_BLOCKERS.json").write_text(
        json.dumps(blockers, indent=2) + "\n", encoding="utf-8"
    )
    (BASE / "THREE_LARGEST_BLOCKERS.md").write_text(
        "# Three largest blockers\n\n"
        + "\n".join(
            f"## {b['rank']}. {b['title']}\n\n"
            f"- subsystem: {b['subsystem']}\n"
            f"- gap: {b['observed_failure_gap']}\n"
            f"- why blocks: {b['why_blocks_one_click_build']}\n"
            f"- next: {b['likely_next_task']}\n"
            f"- evidence: `{b['evidence_artifact']}`\n"
            for b in blockers["blockers"]
        )
        + f"\n**Recommended next task:** {blockers['recommended_next_engineering_task']}\n",
        encoding="utf-8",
    )

    top = {
        "kind": "siteforge_reality_check_v1_return",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_sha": baseline.get("git_sha"),
        "demo_a": {
            "machine": "MSCATL_CP3",
            "matches_prior_accepted": demo_a.get("matches_prior_accepted"),
            "actual": a_actual,
            "readiness": demo_a_ready.get("overall"),
            "compiler": {
                "l5x_path": demo_a_comp.get("l5x_path"),
                "preflight": demo_a_comp.get("preflight_status"),
                "qualification_overall": demo_a_comp.get("qualification_overall"),
            },
        },
        "hard_blind": {
            "selection": sel.get("selected"),
            "selected_before_decode": sel.get("decoder_outcome_known_at_selection")
            is False,
            "pass1": pass1_io,
            "pass2": {
                "live_ai": pass2.get("live_ai_called"),
                "cost_usd": pass2.get("estimated_session_cost_usd"),
                "status": (pass2.get("sessions") or [{}])[0].get("final_status"),
                "rule": pass2.get("warehouse_rule_seeded"),
                "endpoints_assigned": pass2.get("ai_assigned_endpoints"),
                "decoder_mutated": pass2.get("production_decoder_mutated"),
            },
        },
        "artifacts_root": str(BASE),
    }
    (BASE / "RETURN_SUMMARY.json").write_text(
        json.dumps(top, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(top, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
