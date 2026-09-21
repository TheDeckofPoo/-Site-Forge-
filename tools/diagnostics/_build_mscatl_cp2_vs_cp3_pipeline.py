#!/usr/bin/env python3
"""Build MSCATL_CP2 vs CP3 I/O pipeline + Flex bank-allocation audit diagnostics."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))
sys.path.insert(0, str(REPO / "tools"))

from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_asc import read_asc  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    _find_eipcfg,
    _find_eipmodules,
    _load_configio_rows,
    _load_eipmodules_rows,
    parse_eipcfg,
)


def _machine_entry(machine: str, run: Path) -> dict:
    fortna = run / "FORTNA"
    cfg = run / "project.cfg"
    mach_line = ""
    if cfg.is_file():
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if "MACHINE" in line.upper():
                mach_line = line.strip()
                break
    cfg_path = fortna / f"Configio.asc.{machine}"
    _, raw_cfg = read_asc(cfg_path)
    iface = Counter((r.get("Interface") or "").strip() for r in raw_cfg)
    mem = [
        r
        for r in raw_cfg
        if "MEM" in str(r.get("Interface") or "").upper()
        or str(r.get("Desc") or "").upper().startswith("MEM")
    ]
    loaded = _load_configio_rows(run, machine)
    eipm = _load_eipmodules_rows(run, machine)
    nonzero = sum(
        1
        for r in eipm
        if int(r.get("input_bank") or 0) or int(r.get("output_bank") or 0)
    )
    bank_pairs = Counter(
        f"{int(r.get('input_bank') or 0)}/{int(r.get('output_bank') or 0)}" for r in eipm
    )
    ev = build_evidence_bundle(run, machine, project=machine)
    raw = ev.get("raw_claims") or []
    disp = Counter(c.get("deterministic_disposition") for c in raw)
    pwr = PhysicalWordResolver(run, machine)
    words = (pwr.physical_map or {}).get("words") or {}
    unresolved = (ev.get("deterministic_resolver") or {}).get("unresolved_words") or []
    reasons = Counter(
        (u.get("reason") if isinstance(u, dict) else str(u)) for u in unresolved
    )
    topo = parse_eipcfg(run, machine)
    ads = topo.get("adapters") or []
    mod_n = sum(len(a.get("modules") or []) for a in ads)
    return {
        "active_machine_identity": machine,
        "project_cfg_machine_line": mach_line,
        "run_dir": str(run),
        "archive_note": (
            "inbox extract; MSCATL not present in PostgreSQL corpus.archives "
            "at audit time"
        ),
        "configio": {
            "path": str(cfg_path),
            "raw_row_count": len(raw_cfg),
            "interface_counts": dict(iface),
            "classified_physical_rta_loaded": len(loaded),
            "memory_or_mem_desc_rows": len(mem),
            "excluded_non_rta_reason": (
                "Interface filter keeps RTA*/empty; drops Memory"
            ),
        },
        "eipmodules": {
            "path": str(_find_eipmodules(run, machine) or ""),
            "row_count": len(eipm),
            "nonzero_bank_rows": nonzero,
            "zero_bank_rows": len(eipm) - nonzero,
            "bank_pair_counts": dict(bank_pairs),
        },
        "eipcfg": {
            "path": str(_find_eipcfg(run, machine) or ""),
            "adapter_count": len(ads),
            "module_count": mod_n,
            "adapters": [
                {
                    "rio": a.get("rio_name"),
                    "ip": a.get("targetip"),
                    "mods": len(a.get("modules") or []),
                }
                for a in ads
            ],
        },
        "raw_io_claims": {
            "physical_candidates": len(raw),
            "nonphysical_excluded": ev.get("nonphysical_claims_count"),
            "dispositions": dict(disp),
            "assigned": int(disp.get("ASSIGNED") or 0),
            "physical_resolution_failure": int(
                disp.get("physical_resolution_failure") or 0
            ),
        },
        "physical_word_resolver": {
            "resolved_words": len(words),
            "unresolved_word_count": len(unresolved),
            "unresolved_reasons": dict(reasons),
        },
        "gui_occupancy_proxy": {
            "note": (
                "HardwareIOModel channels come from resolved by_word_bit; "
                "zero resolved => empty channels / UNCLAIMED SPARE appearance"
            ),
            "resolved_word_map": len(words),
            "assigned_claims": int(disp.get("ASSIGNED") or 0),
        },
        "conservation_bundle": ev.get("conservation"),
        "evidence_status": ev.get("evidence_status"),
    }


def main() -> int:
    out_dir = REPO / "exports" / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "title": "MSCATL_CP2 vs MSCATL_CP3 I/O pipeline",
        "machines": {
            "MSCATL_CP2": _machine_entry(
                "MSCATL_CP2", REPO / "workspace/_mscatl_peek/MSCATL_CP2/RUN"
            ),
            "MSCATL_CP3": _machine_entry(
                "MSCATL_CP3", REPO / "workspace/_mscatl_peek/MSCATL_CP3/RUN"
            ),
        },
        "first_divergence": {
            "stage": (
                "PhysicalWordResolver / Configio.Bank → "
                "EIPModules.InputBank|OutputBank join"
            ),
            "predicate": "no_eipmodules_bank_match",
            "cp3": (
                "EIPModules banks populated (e.g. IA16 InputBank 4,6,8…) → "
                "configio_catalog_prefix_bank ASSIGNED"
            ),
            "cp2": (
                "EIPModules banks all 0 → every RTA word unresolved → "
                "605 physical_resolution_failure, 0 ASSIGNED"
            ),
            "not_claim_creation": (
                "CP2 creates 605 physical IoClaims; failure is resolution/"
                "binding, not missing Conveyor claims"
            ),
        },
        "postgresql": {
            "mscatl_archives_present": False,
            "note": (
                "corpus.archives has no MSCATL_* rows; evidence.io_claims for "
                "MSCATL_CP2 = 0. Live RUN peek shows claims+zero banks. "
                "Ingest gap vs claim construction."
            ),
            "related_zero_bank_example": (
                "NikeGolf/CP3 in PG also has all-zero EIPModules banks — "
                "recurring export dialect"
            ),
        },
        "bank_allocation_audit_summary": {
            "proposed_rule": (
                "sequential IB/OB from catalog size + slot order after AENT head"
            ),
            "racks_tested_populated_pg": 77,
            "support": 17,
            "counterexamples": 60,
            "production_promotion_justified": False,
            "decision": (
                "STOP at REVIEW_REQUIRED — do not invent CP2 endpoints "
                "via bank synthesis"
            ),
        },
        "why_prior_backtest_missed": {
            "reported_cp2": "ORNCCP2 (Greensboro PLC2 peek), NOT MSCATL_CP2",
            "metric": (
                "LOST_CLAIMS = resolved_not_emitted; when ASSIGNED=0, "
                "lost=0 is vacuous PASS"
            ),
            "denominator": "Stage-0 / discovery-failure gate was absent",
        },
    }
    (out_dir / "mscatl_cp2_vs_cp3_io_pipeline.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8"
    )

    bank = {
        "title": "1794 FLEX EIPModules bank allocation audit",
        "evidence_classes": [
            "RAW_RUN_EVIDENCE",
            "FORTNA_SOURCE_EVIDENCE",
            "INDEPENDENT_DERIVATION",
        ],
        "proposed_algorithm": {
            "description": (
                "After AENT head, allocate InputBank/OutputBank sequentially by "
                "module InputSize/OutputSize (catalog-inferred spans when sizes absent)"
            ),
            "ib_start": (
                "4 on first adapter, or head.input_bank+4 when head carries "
                "adapter input address"
            ),
            "ob_start": (
                "first observed nonzero OutputBank on rack (independent cursor)"
            ),
        },
        "corpus_pg_results": out["bank_allocation_audit_summary"],
        "local_run_evidence": {
            "MSCATL_CP3": (
                "populated banks — RAW_RUN_EVIDENCE supporting Configio.Bank join"
            ),
            "MSCATL_CP2": (
                "all banks 0 with InputSize present — RAW_RUN_EVIDENCE of "
                "zero-bank dialect"
            ),
        },
        "fortna_source_consumers": [
            "fortna_physical_word_resolver._enrich_adapters_with_eipmodules / "
            "configio_catalog_prefix_bank",
            "fortna_autogen._synthesize_point_io_banks "
            "(POINT 1734 only — explicitly skips FLEX)",
            "fortna_physical_word_resolver._synthesize_point_banks_from_adapter_addresses "
            "(POINT only)",
        ],
        "confidence": (
            "LOW for generalized Flex synthesis — 60/77 racks counterexample "
            "under tested rule"
        ),
        "production_promotion_justified": False,
    }
    (out_dir / "eipmodules_flex_bank_allocation_audit.json").write_text(
        json.dumps(bank, indent=2), encoding="utf-8"
    )

    lines = [
        "# MSCATL_CP2 vs MSCATL_CP3 I/O pipeline",
        "",
        "## First divergence",
        "",
        f"**Stage:** {out['first_divergence']['stage']}",
        "",
        f"**Predicate:** `{out['first_divergence']['predicate']}`",
        "",
        f"- CP3: {out['first_divergence']['cp3']}",
        f"- CP2: {out['first_divergence']['cp2']}",
        f"- Note: {out['first_divergence']['not_claim_creation']}",
        "",
    ]
    for m, e in out["machines"].items():
        lines += [
            f"## {m}",
            "",
            f"- Configio loaded physical rows: **{e['configio']['classified_physical_rta_loaded']}**",
            (
                f"- EIPModules rows: **{e['eipmodules']['row_count']}** "
                f"(nonzero banks **{e['eipmodules']['nonzero_bank_rows']}**)"
            ),
            (
                f"- eipcfg adapters: **{e['eipcfg']['adapter_count']}** / "
                f"modules **{e['eipcfg']['module_count']}**"
            ),
            f"- Physical IoClaims: **{e['raw_io_claims']['physical_candidates']}**",
            f"- ASSIGNED: **{e['raw_io_claims']['assigned']}**",
            (
                f"- physical_resolution_failure: "
                f"**{e['raw_io_claims']['physical_resolution_failure']}**"
            ),
            f"- Resolved words: **{e['physical_word_resolver']['resolved_words']}**",
            (
                f"- Unresolved reasons: "
                f"`{e['physical_word_resolver']['unresolved_reasons']}`"
            ),
            "",
        ]
    lines += [
        "## PostgreSQL",
        "",
        out["postgresql"]["note"],
        "",
        "## Bank allocation promotion",
        "",
        (
            f"- Racks tested: "
            f"{out['bank_allocation_audit_summary']['racks_tested_populated_pg']}"
        ),
        f"- Support: {out['bank_allocation_audit_summary']['support']}",
        (
            f"- Counterexamples: "
            f"{out['bank_allocation_audit_summary']['counterexamples']}"
        ),
        (
            f"- Production promotion justified: "
            f"**{out['bank_allocation_audit_summary']['production_promotion_justified']}**"
        ),
        f"- Decision: {out['bank_allocation_audit_summary']['decision']}",
        "",
        "## Why prior corpus backtest falsely passed",
        "",
        f"- Reported CP2 was **{out['why_prior_backtest_missed']['reported_cp2']}**",
        f"- {out['why_prior_backtest_missed']['metric']}",
        f"- {out['why_prior_backtest_missed']['denominator']}",
        "",
    ]
    (out_dir / "mscatl_cp2_vs_cp3_io_pipeline.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    (out_dir / "eipmodules_flex_bank_allocation_audit.md").write_text(
        "\n".join(
            [
                "# 1794 FLEX EIPModules bank allocation audit",
                "",
                "## Decision",
                "",
                "**Production promotion NOT justified.**",
                "",
                (
                    f"Populated PG racks tested: "
                    f"{out['bank_allocation_audit_summary']['racks_tested_populated_pg']}; "
                    f"support {out['bank_allocation_audit_summary']['support']}; "
                    f"counterexamples "
                    f"{out['bank_allocation_audit_summary']['counterexamples']}."
                ),
                "",
                "Do not invent MSCATL_CP2 endpoints via bank synthesis. "
                "Keep unresolved as REVIEW_REQUIRED / DISCOVERY_FAILURE.",
                "",
                "See JSON for algorithm details and Fortna source consumers.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    summary = {
        k: {
            "claims": v["raw_io_claims"]["physical_candidates"],
            "assigned": v["raw_io_claims"]["assigned"],
            "nonzero_banks": v["eipmodules"]["nonzero_bank_rows"],
            "unresolved_reasons": v["physical_word_resolver"]["unresolved_reasons"],
        }
        for k, v in out["machines"].items()
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
