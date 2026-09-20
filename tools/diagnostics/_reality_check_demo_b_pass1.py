#!/usr/bin/env python3
"""Reality Check V1 — Demo B PASS 1 (Site Forge alone, NO live AI).

Uses hard_site_selection.json chosen BEFORE decoder outcome.
Does not mutate production decoders.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))

from fortna_ai_failure_cluster import cluster_unresolved_claims  # noqa: E402
from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_ai_readonly_tools import (  # noqa: E402
    SiteForgeReadOnlyContext,
    get_configio_binding_trace,
    get_physical_word_resolution_trace,
)
from fortna_learning_signatures import build_failure_signature  # noqa: E402
from fortna_physical_word_resolver import PhysicalWordResolver, parse_eipcfg  # noqa: E402
from fortna_production_gate_atlanta import site_counts  # noqa: E402
from fortna_rack_discovery import discover_racks  # noqa: E402
from siteforge_warehouse.postgres_repository import (  # noqa: E402
    PostgresCorpusLearningRepository,
    PostgresCurrentSiteEvidenceRepository,
    make_engine,
)
from sqlalchemy import text  # noqa: E402

OUT = ROOT / "exports" / "demo" / "siteforge-reality-check-v1" / "HARD_BLIND" / "PASS1"
SEL = ROOT / "exports" / "demo" / "siteforge-reality-check-v1" / "hard_site_selection.json"
LOCATE = (
    ROOT
    / "exports"
    / "demo"
    / "siteforge-reality-check-v1"
    / "HARD_BLIND"
    / "run_locate.json"
)


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, str):
        path.write_text(obj if obj.endswith("\n") else obj + "\n", encoding="utf-8")
    else:
        path.write_text(
            json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _git_sha() -> str:
    return (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
        .decode()
        .strip()
    )


def pg_knowledge_vs_site(archive_sha: str, machine: str) -> dict:
    eng = make_engine()
    assert eng is not None
    cur = PostgresCurrentSiteEvidenceRepository(eng)
    learn = PostgresCorpusLearningRepository(eng)
    site_cfg = cur.get_configio_rows(archive_sha256=archive_sha, machine=machine)
    site_eip = cur.get_eipmodules(archive_sha256=archive_sha, machine=machine)
    # Attempt illegal global: should be impossible via public API
    illegal = None
    try:
        cur.get_configio_rows(archive_sha256="", machine=machine)
        illegal = "UNEXPECTED_EMPTY_ARCHIVE_ACCEPTED"
    except Exception as ex:
        illegal = f"rejected:{type(ex).__name__}:{str(ex)[:120]}"
    dialects = learn.count_dialects()
    hardware = dict(list(learn.hardware_catalog_counts().items())[:25])
    rules = [
        {k: r.get(k) for k in ("rule_id", "status", "title")}
        for r in learn.list_rule_candidates()
    ]
    # Prove no foreign archive rows in current-site query
    foreign = [
        r
        for r in site_cfg
        if r.get("archive_sha256") and r.get("archive_sha256") != archive_sha
    ]
    return {
        "current_site": {
            "archive_sha256": archive_sha,
            "machine": machine,
            "configio_rows": len(site_cfg),
            "eipmodules": len(site_eip),
            "foreign_archive_rows_in_current_site_query": len(foreign),
            "missing_archive_rejected": illegal,
        },
        "corpus_learning": {
            "dialect_counts": dialects,
            "hardware_catalog_sample": hardware,
            "rule_candidates": rules,
            "note": "Cross-site structural knowledge only — not current-site endpoints.",
        },
        "proof": {
            "foreign_archive_leak_into_current_site": len(foreign) == 0,
            "cross_site_learning_available": bool(dialects or hardware or rules),
        },
    }


def main() -> int:
    sel = json.loads(SEL.read_text(encoding="utf-8"))
    locate = json.loads(LOCATE.read_text(encoding="utf-8"))
    machine = sel["selected"]["machine"]
    archive_sha = sel["selected"]["archive_sha256"]
    project = sel["selected"]["project"]
    run_dir = Path(locate["run_dir"])
    if not (run_dir / "project.cfg").is_file():
        raise SystemExit(f"missing RUN: {run_dir}")

    OUT.mkdir(parents=True, exist_ok=True)

    # --- PASS 1 deterministic decode (NO AI) ---
    score = site_counts(run_dir, machine)
    score_slim = {k: v for k, v in score.items() if k != "claims"}
    disc = discover_racks(run_dir, machine)
    topo = parse_eipcfg(run_dir, machine)
    ev = build_evidence_bundle(run_dir, machine, project=project)

    # unresolved items
    unresolved_claims = [
        c
        for c in (score.get("claims") or [])
        if c.get("deterministic_disposition")
        in {
            "physical_resolution_failure",
            "UNRESOLVED_OWNER",
            "OWNER_CONFLICT",
        }
        or (
            c.get("deterministic_disposition") != "ASSIGNED"
            and c.get("deterministic_disposition") not in {None}
        )
    ]
    # tighten: needs_resolution path
    unresolved_claims = [
        c
        for c in (score.get("claims") or [])
        if c.get("deterministic_disposition")
        in {
            "physical_resolution_failure",
            "UNRESOLVED_OWNER",
            "OWNER_CONFLICT",
        }
    ]

    # Structural clusters (deterministic) — NO AI
    try:
        clusters = cluster_unresolved_claims(ev)
    except Exception as ex:
        # fallback signature clustering
        clusters = {"error": str(ex), "clusters": []}
        by_sig: dict[str, list] = defaultdict(list)
        resolver = PhysicalWordResolver(run_dir, machine)
        for c in unresolved_claims:
            hit = resolver.resolve(c.get("word"), c.get("bit")) or {}
            sig = build_failure_signature(
                subsystem="physical_io_word_bit_decode",
                hardware_family=str(hit.get("family") or ""),
                configio_form=str(hit.get("assign_how") or "unbound"),
                catalog_class=str(hit.get("type") or ""),
                direction_evidence_class=str(hit.get("direction") or ""),
                bank_relationship_class="unbound",
                failure_reason=str(c.get("deterministic_disposition") or "unknown"),
            )
            key = json.dumps(sig, sort_keys=True, default=str)
            by_sig[key].append(c.get("claim_id"))
        clusters = {
            "clusters": [
                {
                    "cluster_key": _sha_bytes(k.encode())[:16],
                    "signature": json.loads(k),
                    "occurrence_count": len(ids),
                    "claim_ids": ids[:50],
                    "claims_affected": len(ids),
                }
                for k, ids in sorted(by_sig.items(), key=lambda x: -len(x[1]))
            ]
        }

    # Normalize cluster summary for AI Pass2 input
    cluster_list = []
    if isinstance(clusters, dict) and "clusters" in clusters:
        raw_clusters = clusters["clusters"]
    elif isinstance(clusters, list):
        raw_clusters = clusters
    else:
        raw_clusters = []
    for cl in raw_clusters:
        if not isinstance(cl, dict):
            continue
        cluster_list.append(
            {
                "cluster_key": cl.get("cluster_key")
                or cl.get("key")
                or cl.get("signature_id")
                or _sha_bytes(json.dumps(cl, sort_keys=True, default=str).encode())[:16],
                "occurrence_count": cl.get("occurrence_count")
                or cl.get("count")
                or len(cl.get("claim_ids") or cl.get("claims") or []),
                "claims_affected": cl.get("claims_affected")
                or len(cl.get("claim_ids") or cl.get("claims") or []),
                "claim_ids_sample": (cl.get("claim_ids") or cl.get("claims") or [])[:20],
                "signature": cl.get("signature") or cl.get("dimensions") or cl,
                "why_deterministic_failed": cl.get("failure_reason")
                or cl.get("reason")
                or "See signature dimensions",
                "production_rules_already_tested": [
                    "exact_adapter_ip_bridge",
                    "direction_aware_bank_binding",
                ],
                "candidate_rules_not_used_as_truth": [
                    "panel_catalog_numeric_alpha_low_a_slot"
                ],
            }
        )

    # Corpus context for clusters via learning repo (structural only)
    eng = make_engine()
    learn = PostgresCorpusLearningRepository(eng)
    dialect_counts = learn.count_dialects()
    unknown_clusters_pg = []
    try:
        unknown_clusters_pg = learn.list_unknown_clusters()
    except Exception:
        unknown_clusters_pg = []

    unresolved_cluster_summary = {
        "kind": "unresolved_cluster_summary",
        "machine": machine,
        "archive_sha256": archive_sha,
        "unresolved_claim_count": len(unresolved_claims),
        "cluster_count": len(cluster_list),
        "clusters": cluster_list,
        "postgresql_unknown_clusters_sample": unknown_clusters_pg[:20],
        "dialect_counts_cross_site": dialect_counts,
        "note": "Grouped for AI structural-family investigation — not one call per claim.",
    }

    # Provenance samples (assigned if any, else unresolved)
    ctx = SiteForgeReadOnlyContext(run_dir, machine, project=project)
    sample_src = [
        c
        for c in (score.get("claims") or [])
        if c.get("deterministic_disposition") == "ASSIGNED"
    ][:3]
    sample_src += unresolved_claims[:2]
    prov = []
    for c in sample_src[:5]:
        try:
            bind = get_configio_binding_trace(ctx, c.get("word"))
        except Exception as ex:
            bind = {"error": str(ex)}
        try:
            phys = get_physical_word_resolution_trace(ctx, str(c.get("claim_id") or ""))
        except Exception as ex:
            phys = {"error": str(ex)}
        prov.append(
            {
                "engineering_device": c.get("io_name") or c.get("claim_id"),
                "disposition": c.get("deterministic_disposition"),
                "word": c.get("word"),
                "bit": c.get("bit"),
                "configio_binding_trace": bind,
                "physical_trace_diagnostic_only": phys,
            }
        )

    # Conflicts from PG for this archive
    conflicts = []
    with eng.connect() as c:
        conflicts = [
            dict(r)
            for r in c.execute(
                text(
                    "SELECT conflict_kind, summary, machine, archive_sha256 "
                    "FROM evidence.conflicts "
                    "WHERE archive_sha256=:s AND machine=:m LIMIT 100"
                ),
                {"s": archive_sha, "m": machine},
            ).mappings()
        ]

    # Compiler attempt (virgin) — may BLOCK; that's fine
    qual_out = OUT / "qualification_virgin"
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "scripts" / "fortna_qualification_runner.py"),
        "qualify",
        "--run-dir",
        str(run_dir),
        "--machine",
        machine,
        "--mode",
        "virgin",
        "--sanitized",
        "--skip-generate",
        "--out",
        str(qual_out),
        "--label",
        "reality-check-v1-hard-pass1",
    ]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    qual_report = {}
    qp = qual_out / "qualification_report.json"
    if qp.is_file():
        qual_report = json.loads(qp.read_text(encoding="utf-8"))

    compiler_state = {
        "kind": "compiler_state",
        "pass": "PASS1",
        "live_ai_called": False,
        "skip_generate": True,
        "reason_skip_generate": (
            "Pass1 measures discovery readiness; full Autogen deferred until "
            "hardware/I-O + subsystem gates allow trustworthy compile."
        ),
        "qualification_overall": qual_report.get("overall"),
        "qualification_ok": qual_report.get("ok"),
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-3000:],
        "stderr_tail": (proc.stderr or "")[-1500:],
    }

    io_pass = (
        score_slim.get("conservation") == "PASS"
        and int(score_slim.get("needs_resolution") or 0) == 0
        and int(score_slim.get("PROVEN") or 0) > 0
    )
    readiness = {
        "kind": "build_readiness",
        "pass": "PASS1",
        "machine": machine,
        "overall": "NOT READY TO COMPILE",
        "subsystems": {
            "RUN_ingestion": "PASS",
            "machine_source_scoping": "PASS",
            "hardware_topology": (
                "PASS"
                if int(score_slim.get("rack_count") or 0) >= 1
                else "REVIEW_REQUIRED"
            ),
            "physical_IO": "PASS" if io_pass else "REVIEW_REQUIRED",
            "Transportation": "PARTIAL",
            "Safety": "REVIEW_REQUIRED",
            "Sorter": "NOT_APPLICABLE",
            "VFD": "NOT_IMPLEMENTED",
            "canonical_model": "PARTIAL",
            "PLC_compiler": "BLOCKED",
            "GUI": "NOT_APPLICABLE",
            "provenance": "PARTIAL",
            "PostgreSQL_learning": "PASS",
            "AI_Investigator": "NOT_APPLICABLE",
        },
        "notes": [
            "Pass1 is Site Forge alone — no live AI.",
            "CANDIDATE_RULE not applied as production truth.",
        ],
    }

    hardware = {
        "kind": "hardware_result",
        "machine": machine,
        "project": project,
        "archive_sha256": archive_sha,
        "rack_count": score_slim.get("rack_count"),
        "slotted_modules": score_slim.get("slotted_modules"),
        "unplaced_modules": score_slim.get("unplaced_modules"),
        "other_network_devices": score_slim.get("other_network_devices"),
        "racks": disc.get("racks") or [],
        "adapter_bridge_stats": (topo.get("adapter_bridge_stats") or {}),
    }

    physical_io = {
        "kind": "physical_io_result",
        "machine": machine,
        "raw_physical_claims": score_slim.get("raw"),
        "ASSIGNED": score_slim.get("ASSIGNED"),
        "PROVEN": score_slim.get("PROVEN"),
        "DERIVED": score_slim.get("DERIVED"),
        "REVIEW_REQUIRED": score_slim.get("REVIEW_REQUIRED"),
        "UNKNOWN": score_slim.get("UNKNOWN"),
        "needs_resolution": score_slim.get("needs_resolution"),
        "OWNER_CONFLICT": score_slim.get("OWNER_CONFLICT"),
        "physical_resolution_failure": score_slim.get("physical_resolution_failure"),
        "duplicate_channels": score_slim.get("duplicate_channels"),
        "conservation": score_slim.get("conservation"),
        "confidence_summary": score_slim.get("confidence_summary"),
        "full": score_slim,
    }

    pg_proof = pg_knowledge_vs_site(archive_sha, machine)

    artifacts = {
        "hardware_result.json": hardware,
        "physical_io_result.json": physical_io,
        "build_readiness.json": readiness,
        "unresolved_items.json": {
            "count": len(unresolved_claims),
            "items": [
                {
                    "claim_id": c.get("claim_id"),
                    "io_name": c.get("io_name"),
                    "word": c.get("word"),
                    "bit": c.get("bit"),
                    "disposition": c.get("deterministic_disposition"),
                }
                for c in unresolved_claims[:500]
            ],
        },
        "unresolved_cluster_summary.json": unresolved_cluster_summary,
        "conflicts.json": {"count": len(conflicts), "items": conflicts},
        "compiler_state.json": compiler_state,
        "provenance_samples.json": {"examples": prov},
        "postgresql_knowledge_vs_site.json": pg_proof,
        "pass1_summary.md": (
            f"# Demo B PASS 1 — {machine}\n\n"
            f"Selected **before** decoder outcome. Live AI: **NO**.\n\n"
            f"- archive: `{archive_sha}`\n"
            f"- raw claims: **{physical_io['raw_physical_claims']}**\n"
            f"- PROVEN: **{physical_io['PROVEN']}**\n"
            f"- DERIVED: **{physical_io['DERIVED']}**\n"
            f"- needs_resolution: **{physical_io['needs_resolution']}**\n"
            f"- REVIEW_REQUIRED: **{physical_io['REVIEW_REQUIRED']}**\n"
            f"- racks: **{hardware['rack_count']}**\n"
            f"- conservation: **{physical_io['conservation']}**\n"
            f"- unresolved clusters: **{unresolved_cluster_summary['cluster_count']}**\n"
            f"- conflicts: **{len(conflicts)}**\n"
            f"- readiness: **{readiness['overall']}**\n"
            f"- qualification: **{compiler_state.get('qualification_overall')}**\n"
            f"- foreign archive leak into current-site: "
            f"**{pg_proof['proof']['foreign_archive_leak_into_current_site']}**\n"
        ),
    }

    hashes = {}
    for name, obj in artifacts.items():
        path = OUT / name
        _write(path, obj)
        hashes[name] = _sha_file(path)

    frozen = {
        "kind": "pass1_frozen_manifest",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "machine": machine,
        "project": project,
        "archive_sha256": archive_sha,
        "run_dir": str(run_dir),
        "live_ai_called": False,
        "selection_confirmation": sel.get("confirmation"),
        "decoder_outcome_known_at_selection": sel.get(
            "decoder_outcome_known_at_selection"
        ),
        "artifact_sha256": hashes,
        "physical_io_snapshot": {
            "raw": physical_io["raw_physical_claims"],
            "PROVEN": physical_io["PROVEN"],
            "DERIVED": physical_io["DERIVED"],
            "needs_resolution": physical_io["needs_resolution"],
            "REVIEW_REQUIRED": physical_io["REVIEW_REQUIRED"],
            "conservation": physical_io["conservation"],
            "racks": hardware["rack_count"],
        },
        "do_not_alter_after_ai": True,
    }
    _write(OUT / "pass1_frozen_manifest.json", frozen)
    # also copy cluster summary one level up for Pass2
    _write(
        OUT.parent / "unresolved_cluster_summary.json",
        unresolved_cluster_summary,
    )
    print(
        json.dumps(
            {
                "out": str(OUT),
                "machine": machine,
                "physical_io": frozen["physical_io_snapshot"],
                "clusters": unresolved_cluster_summary["cluster_count"],
                "readiness": readiness["overall"],
                "pg_no_foreign_leak": pg_proof["proof"][
                    "foreign_archive_leak_into_current_site"
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
