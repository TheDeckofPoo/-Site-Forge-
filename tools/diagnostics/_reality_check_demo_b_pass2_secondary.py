#!/usr/bin/env python3
"""Investigate secondary unresolved cluster (OWNER_CONFLICT, 2 claims)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "diagnostics"))

from _reality_check_demo_b_pass2 import (  # noqa: E402
    HARD_BUDGET,
    LOCATE,
    OUT,
    PASS1,
    SEL,
    build_blind_packet,
    map_status_to_warehouse,
    patch_budget,
)
from fortna_ai_decoder_investigate import run_investigation  # noqa: E402
from siteforge_warehouse.writer import PostgresWarehouseWriter  # noqa: E402


def main() -> int:
    patch_budget()
    sel = json.loads(SEL.read_text(encoding="utf-8"))
    locate = json.loads(LOCATE.read_text(encoding="utf-8"))
    frozen = json.loads((PASS1 / "pass1_frozen_manifest.json").read_text(encoding="utf-8"))
    clusters = json.loads(
        (PASS1 / "unresolved_cluster_summary.json").read_text(encoding="utf-8")
    )["clusters"]
    secondary = min(clusters, key=lambda c: int(c.get("claims_affected") or 0))
    machine = sel["selected"]["machine"]
    project = sel["selected"]["project"]
    archive_sha = sel["selected"]["archive_sha256"]
    blind = build_blind_packet(
        machine=machine,
        project=project,
        archive_sha=archive_sha,
        cluster=secondary,
        pass1_io=frozen["physical_io_snapshot"],
    )
    out = OUT / f"AI_{secondary.get('cluster_key')}"
    print("investigating", secondary.get("cluster_key"), secondary.get("claims_affected"))
    res = run_investigation(
        run_dir=Path(locate["run_dir"]),
        blind_packet=blind,
        out_dir=out,
        machine=machine,
        project=project,
        investigation_id=blind["investigation_id"],
    )
    cand = res.get("candidate") or {}
    usage = res.get("usage") or {}
    summary = res.get("summary") or {}
    cost = float(usage.get("estimated_session_cost_usd") or 0)
    status = str(summary.get("final_status") or cand.get("status") or "")
    key = (
        str(cand.get("candidate_rule_name") or f"fisher_owner_conflict_{secondary.get('cluster_key')}")
        .lower()
        .replace(" ", "_")[:120]
    )
    PostgresWarehouseWriter().seed_rule_candidate(
        {
            "rule_id": key,
            "rule_key": key,
            "title": cand.get("candidate_rule_name") or key,
            "status": map_status_to_warehouse(status),
            "summary": cand.get("candidate_rule_description") or "",
            "production_auto_promote": False,
            "honesty_notes": [
                "Pass2 secondary OWNER_CONFLICT cluster",
                "NOT production",
            ],
            "meta": {
                "investigation_id": blind["investigation_id"],
                "cluster_key": secondary.get("cluster_key"),
                "ai_status": status,
                "cost": cost,
            },
        }
    )
    manifest_path = OUT / "pass2_manifest.json"
    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    man.setdefault("sessions", []).append(
        {
            "investigation_id": blind["investigation_id"],
            "model": usage.get("model"),
            "estimated_session_cost_usd": cost,
            "hard_budget_usd": HARD_BUDGET,
            "final_status": status,
            "candidate_rule_name": cand.get("candidate_rule_name"),
            "out_dir": str(out),
            "ai_assigned_endpoints": False,
        }
    )
    total = round(
        sum(float(s.get("estimated_session_cost_usd") or 0) for s in man["sessions"]),
        6,
    )
    man["estimated_session_cost_usd"] = total
    man["total_estimated_cost_usd"] = total
    man["secondary_rule_seeded"] = key
    manifest_path.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    # append to summary md
    summary_md = OUT / "AI_INVESTIGATION_SUMMARY.md"
    with summary_md.open("a", encoding="utf-8") as f:
        f.write(
            f"\n## Secondary cluster `{secondary.get('cluster_key')}`\n\n"
            f"- claims: {secondary.get('claims_affected')}\n"
            f"- status: **{status}**\n"
            f"- cost USD: **{cost}**\n"
            f"- candidate: `{cand.get('candidate_rule_name')}`\n"
            f"- warehouse: `{key}` / `{map_status_to_warehouse(status)}`\n"
        )
    print(json.dumps({"cost": cost, "status": status, "rule": key, "total_cost": total}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
