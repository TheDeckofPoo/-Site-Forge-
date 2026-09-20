#!/usr/bin/env python3
"""Failure clustering for AI decoder investigation.

Groups unresolved physical I/O claims by shared decoding characteristics so
256 unresolved claims become a handful of pattern investigations — not 256
prompts. Every claim_id appears in exactly one cluster (conservation).
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any


CLUSTER_DIMENSIONS = (
    "machine",
    "adapter",
    "hardware_family",
    "module_catalog",
    "direction",
    "configio_interface",
    "configio_bank",
    "configio_lohi",
    "configio_in_out",
    "fortna_word_band",
    "resolution_failure_reason",
    "ownership_conflict_type",
    "bit_encoding_class",
)


def _word_band(word: Any) -> str:
    try:
        w = int(float(str(word).strip()))
    except (TypeError, ValueError):
        return "non_numeric"
    if w >= 6000:
        return "virtual_ge_6000"
    if 1000 <= w < 1200:
        return "1xxx_point"
    if 600 <= w < 700:
        return "6xx_flex"
    if 500 <= w < 600:
        return "5xx"
    return f"band_{(w // 100) * 100}"


def _bit_encoding_class(bit: Any) -> str:
    """Classify Fortna bit encoding for clustering."""
    s = str(bit or "").strip()
    try:
        v = int(float(s))
    except (TypeError, ValueError):
        return "unparseable"
    if 0 <= v <= 3:
        return "low_nibble_0_3"
    if 4 <= v <= 7:
        return "low_nibble_4_7"
    if 8 <= v <= 11 or 10 <= v <= 13:
        return "high_half_8_13_or_10_13"
    if 12 <= v <= 17:
        return "high_extended_12_17"
    return f"other_{v}"


def _cluster_key(dims: dict[str, Any]) -> str:
    raw = "|".join(f"{k}={dims.get(k) or ''}" for k in CLUSTER_DIMENSIONS)
    return "fc_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def build_claim_cluster_dims(
    claim: dict[str, Any],
    *,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive clustering dimensions for one physical claim."""
    evidence = evidence or {}
    word = claim.get("word") or claim.get("fortna_word")
    bit = claim.get("bit") or claim.get("fortna_bit")
    disp = str(
        claim.get("deterministic_disposition")
        or claim.get("disposition")
        or "physical_resolution_failure"
    )
    # Configio lookup from evidence when present
    cfg_iface = cfg_bank = cfg_lohi = cfg_inout = ""
    try:
        w_i = int(float(str(word)))
    except (TypeError, ValueError):
        w_i = None
    for row in evidence.get("configio") or []:
        try:
            if int(row.get("Octal_Word") if "Octal_Word" in row else row.get("octal_word")) != w_i:
                continue
        except (TypeError, ValueError):
            continue
        # Prefer Low for bit<8 else High — soft hint only
        lohi = str(row.get("LoHi") or row.get("lohi") or "")
        cfg_iface = str(row.get("Interface") or row.get("interface") or cfg_iface)
        cfg_inout = str(row.get("In_Out") or row.get("in_out") or cfg_inout)
        cfg_bank = str(row.get("Bank") if row.get("Bank") is not None else row.get("bank") or cfg_bank)
        cfg_lohi = lohi or cfg_lohi

    adapter = str(claim.get("adapter") or claim.get("rio_name") or "")
    family = str(claim.get("family") or claim.get("hardware_family") or "")
    catalog = str(claim.get("module_catalog") or claim.get("catalog") or claim.get("type") or "")
    direction = str(claim.get("direction") or "")

    conflict_type = ""
    if disp == "OWNER_CONFLICT":
        conflict_type = str(claim.get("conflict_type") or "OWNER_CONFLICT")
    fail_reason = ""
    if disp == "physical_resolution_failure":
        fail_reason = str(claim.get("evidence") or claim.get("class_reason") or "no_channel")

    return {
        "machine": str(claim.get("machine") or evidence.get("machine") or ""),
        "adapter": adapter,
        "hardware_family": family,
        "module_catalog": catalog,
        "direction": direction,
        "configio_interface": cfg_iface,
        "configio_bank": cfg_bank,
        "configio_lohi": cfg_lohi,
        "configio_in_out": cfg_inout,
        "fortna_word_band": _word_band(word),
        "resolution_failure_reason": fail_reason or disp,
        "ownership_conflict_type": conflict_type,
        "bit_encoding_class": _bit_encoding_class(bit),
    }


def cluster_unresolved_claims(
    claims: list[dict[str, Any]],
    *,
    evidence: dict[str, Any] | None = None,
    only_needing_resolution: bool = True,
) -> dict[str, Any]:
    """Cluster claims. Every input claim_id appears in exactly one cluster."""
    evidence = evidence or {}
    needing = {
        "UNRESOLVED_OWNER",
        "OWNER_CONFLICT",
        "physical_resolution_failure",
    }
    selected: list[dict[str, Any]] = []
    for c in claims:
        disp = str(c.get("deterministic_disposition") or c.get("disposition") or "")
        if only_needing_resolution and disp not in needing:
            continue
        if not c.get("claim_id"):
            continue
        selected.append(c)

    buckets: dict[str, dict[str, Any]] = {}
    claim_to_cluster: dict[str, str] = {}

    for c in selected:
        dims = build_claim_cluster_dims(c, evidence=evidence)
        cid = _cluster_key(dims)
        if cid not in buckets:
            buckets[cid] = {
                "cluster_id": cid,
                "dimensions": dims,
                "claim_ids": [],
                "claims": [],
                "count": 0,
            }
        buckets[cid]["claim_ids"].append(c["claim_id"])
        buckets[cid]["claims"].append(
            {
                "claim_id": c["claim_id"],
                "io_name": c.get("io_name") or c.get("name"),
                "word": c.get("word") or c.get("fortna_word"),
                "bit": c.get("bit") or c.get("fortna_bit"),
                "disposition": c.get("deterministic_disposition") or c.get("disposition"),
            }
        )
        buckets[cid]["count"] += 1
        claim_to_cluster[c["claim_id"]] = cid

    # Conservation: every selected claim in exactly one cluster
    selected_ids = [c["claim_id"] for c in selected]
    clustered_ids = list(claim_to_cluster.keys())
    lost = sorted(set(selected_ids) - set(clustered_ids))
    # Duplicates: claim in multiple clusters
    seen: set[str] = set()
    dup: list[str] = []
    for cid, cl in buckets.items():
        for claim_id in cl["claim_ids"]:
            if claim_id in seen:
                dup.append(claim_id)
            seen.add(claim_id)

    clusters = sorted(buckets.values(), key=lambda x: (-x["count"], x["cluster_id"]))
    return {
        "ok": len(lost) == 0 and len(dup) == 0,
        "input_claim_count": len(selected),
        "cluster_count": len(clusters),
        "clusters": clusters,
        "claim_to_cluster": claim_to_cluster,
        "lost_claim_ids": lost,
        "duplicate_claim_ids": sorted(set(dup)),
        "conservation": "PASS" if len(lost) == 0 and len(dup) == 0 else "FAIL",
        "dimensions_used": list(CLUSTER_DIMENSIONS),
    }


def main() -> int:
    import argparse
    from pathlib import Path

    from fortna_ai_io_evidence import build_evidence_bundle

    ap = argparse.ArgumentParser(description="Cluster unresolved physical I/O claims")
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--machine", required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    evidence = build_evidence_bundle(args.run_dir, args.machine)
    result = cluster_unresolved_claims(evidence.get("raw_claims") or [], evidence=evidence)
    out = args.out
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "input_claim_count": result["input_claim_count"],
                "cluster_count": result["cluster_count"],
                "conservation": result["conservation"],
                "lost": len(result["lost_claim_ids"]),
                "duplicates": len(result["duplicate_claim_ids"]),
            },
            indent=2,
        )
    )
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
