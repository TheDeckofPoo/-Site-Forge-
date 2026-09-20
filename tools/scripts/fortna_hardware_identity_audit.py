#!/usr/bin/env python3
"""Four-site hardware identity + multi-key channel audit (no live API)."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_ai_failure_cluster import cluster_unresolved_claims  # noqa: E402
from fortna_ai_io_analyze import analyze  # noqa: E402
from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_hardware_identity import (  # noqa: E402
    build_hardware_identity_model,
    classify_host_xml_value,
    inventory_hardware_files,
)
from fortna_physical_word_resolver import build_physical_word_map  # noqa: E402

SITES = [
    ("ORINDYAC6", "ORINDYAC6", REPO_ROOT / "workspace" / "_virgin_orindy" / "RUN"),
    ("MSCATL_CP3", "MSCATL_CP3", REPO_ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"),
    (
        "MSCRENOPICK",
        "MSCRENOPICK",
        REPO_ROOT
        / "workspace"
        / "_reno_peek"
        / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
        / "RUN",
    ),
    ("ORDENCP3", "ORDENCP3", REPO_ROOT / "workspace" / "_ordencp3_peek" / "ORDENCP3" / "RUN"),
]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def analyze_multi_keys(pm: dict[str, Any]) -> dict[str, Any]:
    bwb = pm.get("by_word_bit") or {}
    by_ch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for k, v in bwb.items():
        if ":" not in k:
            continue
        ch = v.get("channel")
        if not ch:
            continue
        w, b = k.split(":", 1)
        try:
            lb = int(b)
        except ValueError:
            lb = -1
        by_ch[ch].append(
            {
                "key": k,
                "word": w,
                "logical_bit": lb,
                "half": v.get("bit_half"),
                "type": v.get("type"),
                "module_bit": v.get("bit"),
                "capacity": v.get("module_capacity"),
            }
        )
    cats: Counter[str] = Counter()
    examples: dict[str, list] = defaultdict(list)
    for ch, keys in by_ch.items():
        if len(keys) < 2:
            continue
        bits = [k["logical_bit"] for k in keys]
        words = {k["word"] for k in keys}
        if any(b > 15 for b in bits):
            cat = "G_out_of_domain_ge16_should_be_fixed"
        elif len(words) > 1:
            # same physical channel, different Fortna words
            types = {k["type"] for k in keys}
            if len(types) > 1:
                cat = "F_true_duplicate_or_bank_collision"
            else:
                cat = "C_configio_word_reuse_same_module"
        elif max(bits) - min(bits) >= 8 and any(k["half"] == "high" for k in keys) and any(
            k["half"] == "low" for k in keys
        ):
            cat = "B_low_high_half_same_channel_expected"
        elif len(set(bits)) > 1 and all(0 <= b <= 15 for b in bits):
            cat = "A_or_B_same_word_multi_logical_alias"
        else:
            cat = "G_audit_other"
        cats[cat] += 1
        if len(examples[cat]) < 4:
            examples[cat].append({"channel": ch, "keys": keys})
    return {
        "multi_channel_count": sum(1 for v in by_ch.values() if len(v) > 1),
        "categories": dict(cats),
        "examples": {k: v for k, v in examples.items()},
        "invariant_logical_bit_domain": not any(
            k["logical_bit"] > 15 for keys in by_ch.values() for k in keys
        ),
    }


def site_report(site: str, machine: str, run: Path) -> dict[str, Any]:
    if not (run / "project.cfg").is_file():
        return {"site": site, "run_available": False}
    inv = inventory_hardware_files(run, machine)
    hw = build_hardware_identity_model(run, machine)
    pm = build_physical_word_map(run, machine)
    multi = analyze_multi_keys(pm)
    evidence = build_evidence_bundle(run, machine, project=site)
    if site == "ORDENCP3":
        evidence["fixture_role"] = "alternate_evidence"
    clustered = cluster_unresolved_claims(
        evidence.get("raw_claims") or [], evidence=evidence
    )
    # IO numbers via analyze mock
    result = analyze(
        run,
        machine,
        project=site,
        mock_response={
            "project": site,
            "machine": machine,
            "claims": [],
            "unresolved": [],
            "warnings": ["offline"],
        },
        fixture_role="alternate_evidence" if site == "ORDENCP3" else "",
    )
    before = (result.get("evaluation") or {}).get("BEFORE_AI") or {}
    # hardware matrix
    matrix = []
    for ad in hw.get("adapters") or []:
        children = [
            m
            for m in hw.get("modules") or []
            if m.get("parent_canonical_id") == ad.get("canonical_id")
        ]
        matrix.append(
            {
                "canonical_id": ad.get("canonical_id"),
                "aliases": ad.get("aliases"),
                "catalog": ad.get("catalog_number"),
                "family": ad.get("adapter_family"),
                "ip": ad.get("ip_address"),
                "status": ad.get("status"),
                "child_count": len(children),
                "children": [
                    {
                        "slot": m.get("physical_slot"),
                        "catalog": m.get("catalog_number"),
                        "family": m.get("adapter_family"),
                        "direction": m.get("direction"),
                        "capacity": m.get("channel_capacity"),
                        "data_index": m.get("data_index"),
                        "aliases": m.get("aliases"),
                        "status": m.get("status"),
                    }
                    for m in children
                ],
            }
        )
    # enrichment quality
    unknown_fam = sum(
        1
        for c in evidence.get("raw_claims") or []
        if not c.get("adapter_family") or c.get("adapter_family") == "UNKNOWN"
    )
    unknown_cat = sum(
        1
        for c in evidence.get("raw_claims") or []
        if not c.get("module_catalog")
    )
    top = []
    for cl in (clustered.get("clusters") or [])[:12]:
        dims = cl.get("dimensions") or {}
        # enrich dims from representative claim
        rep = (cl.get("claims") or [{}])[0]
        full = next(
            (
                c
                for c in (evidence.get("raw_claims") or [])
                if c.get("claim_id") == rep.get("claim_id")
            ),
            {},
        )
        top.append(
            {
                "cluster_id": cl.get("cluster_id"),
                "count": cl.get("count"),
                "canonical_adapter": full.get("canonical_adapter_id"),
                "family": full.get("adapter_family") or dims.get("hardware_family"),
                "catalog": full.get("module_catalog") or dims.get("module_catalog"),
                "direction": full.get("direction") or dims.get("direction"),
                "configio_pattern": dims.get("configio_in_out") or dims.get("configio_lohi"),
                "failure_reason": dims.get("resolution_failure_reason"),
                "bit_pattern": dims.get("bit_encoding_class"),
                "representatives": [x.get("io_name") for x in (cl.get("claims") or [])[:5]],
            }
        )
    return {
        "site": site,
        "run_available": True,
        "inventory": inv,
        "host_xml_value": classify_host_xml_value(inv),
        "hardware_stats": hw.get("stats"),
        "hardware_conflicts": hw.get("conflicts"),
        "matrix": matrix,
        "multi_key_analysis": multi,
        "io": {
            "raw": before.get("raw_physical_claims"),
            "proven": before.get("proven"),
            "owner_conflict": before.get("owner_conflict"),
            "physical_resolution_failure": before.get("physical_resolution_failures"),
            "needs_resolution": before.get("needs_resolution"),
            "lost": before.get("lost_claims"),
            "duplicate": before.get("duplicate_accounting"),
            "conservation": before.get("conservation"),
            "evidence_status": before.get("evidence_status"),
            "hardware_identity_conflicts": evidence.get("hardware_identity_conflicts"),
        },
        "enrichment": {
            "claims": len(evidence.get("raw_claims") or []),
            "unknown_family": unknown_fam,
            "unknown_catalog": unknown_cat,
        },
        "failure_clusters": {
            "unresolved": clustered.get("input_claim_count"),
            "cluster_count": clustered.get("cluster_count"),
            "conservation": clustered.get("conservation"),
            "top_clusters": top,
        },
    }


def main() -> int:
    report = {
        "kind": "hardware_identity_audit",
        "generated_at": _ts(),
        "live_api_called": False,
        "evidence_precedence": [
            "eipcfg_xml",
            "eipmodules",
            "eip_adapters_csv_moduletype",
            "configio",
            "iocard",
            "hosts_alias",
            "human_name_alias",
        ],
        "flex_16ch_half_rule": (
            "When Low+High Configio exist, each half emits at most 8 logical bits "
            "(Low 0-7, High 8-15). Solo Low may use min(capacity,16). Never emit >15."
        ),
        "sites": [],
    }
    for site, machine, run in SITES:
        print(f"=== {site} ===", flush=True)
        rec = site_report(site, machine, run)
        report["sites"].append(rec)
        print(json.dumps({"site": site, "io": rec.get("io"), "clusters": (rec.get("failure_clusters") or {}).get("cluster_count"), "multi": (rec.get("multi_key_analysis") or {}).get("categories"), "host": (rec.get("host_xml_value") or {}).get("classification"), "enrich_unknown_fam": (rec.get("enrichment") or {}).get("unknown_family")}, indent=2), flush=True)
    out = REPO_ROOT / "exports" / "ai-io" / "audits" / "hardware_identity_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Slim matrices in main file — keep full in sidecar
    slim = json.loads(json.dumps(report))
    matrices = {}
    for s in slim["sites"]:
        matrices[s["site"]] = s.pop("matrix", [])
        s.pop("inventory", None)
    out.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    (out.parent / "hardware_matrix.json").write_text(json.dumps(matrices, indent=2), encoding="utf-8")
    print(f"Wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
