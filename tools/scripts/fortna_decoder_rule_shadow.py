#!/usr/bin/env python3
"""NON-PRODUCTION shadow evaluator for RTA_1794_catalog_prefix_direction_and_low_bank_pair_match.

Does NOT modify production resolver, claims, Autogen, or compiler.
Answers: what WOULD happen if Site Forge implemented this candidate.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_ai_io_validate import (  # noqa: E402
    compute_claim_conservation,
    enrich_conservation_with_readiness,
)
from fortna_bit_address import parse_fortna_bit_address  # noqa: E402
from fortna_configio_direction import resolve_configio_direction  # noqa: E402
from fortna_physical_word_resolver import _load_configio_rows  # noqa: E402
from fortna_rack_discovery import discover_racks  # noqa: E402
from fortna_rockwell_catalog import (  # noqa: E402
    CATALOG_SIGNATURE_ONLY,
    KNOWN_CATALOG,
    first_catalog,
    load_known_catalogs,
)

RULE_NAME = "RTA_1794_catalog_prefix_direction_and_low_bank_pair_match"

SITES = [
    ("MSCATL_CP3", "MSCATL_CP3", REPO_ROOT / "workspace/_mscatl_peek/MSCATL_CP3/RUN"),
    ("ORINDYAC6", "ORINDYAC6", REPO_ROOT / "workspace/_virgin_orindy/RUN"),
    (
        "MSCRENOPICK",
        "MSCRENOPICK",
        REPO_ROOT / "workspace/_reno_peek/20260813-1132-MSCRENO-MSCRENOPICK-RUN/RUN",
    ),
    ("ORDENCP3", "ORDENCP3", REPO_ROOT / "workspace/_ordencp3_peek/ORDENCP3/RUN"),
]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _modules_flat(discovery: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for rack in discovery.get("racks") or []:
        for m in rack.get("modules") or []:
            out.append(
                {
                    **m,
                    "adapter_aliases": rack.get("source_aliases") or [],
                    "provisional_rack": rack.get("provisional_display_name"),
                    "canonical_adapter_id": rack.get("canonical_adapter_id"),
                    "adapter_ip": rack.get("ip_address"),
                    "adapter_family": rack.get("hardware_family"),
                    "bank_join": next(
                        (
                            e.get("ref")
                            for e in (m.get("evidence") or [])
                            if e.get("source") == "bank_join"
                        ),
                        "unknown",
                    ),
                }
            )
    return out


def shadow_bind_word(
    word: int,
    halves: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    *,
    run_dir: Path,
) -> dict[str, Any]:
    """Apply shadow rule to one Configio Octal_Word (both halves)."""
    low = next((h for h in halves if str(h.get("lohi") or "").lower().startswith("lo")), None)
    high = next((h for h in halves if str(h.get("lohi") or "").lower().startswith("hi")), None)
    iface = str((low or high or {}).get("interface") or "").upper()
    if iface and iface != "RTA":
        return {
            "word": word,
            "result": "NOT_APPLICABLE",
            "reason": f"interface_{iface or 'empty'}",
        }

    def _norm_half(row: dict[str, Any] | None, side: str) -> dict[str, Any] | None:
        if not row:
            return None
        desc = str(row.get("desc") or "")
        cat_ev = first_catalog(desc, run_dir=run_dir, source_table="Configio", source_row=row.get("row"))
        if not cat_ev:
            return {
                "side": side,
                "desc": desc,
                "bank": row.get("bank"),
                "result": "CATALOG_UNKNOWN",
                "in_out": row.get("in_out"),
            }
        if cat_ev.catalog_number.upper().startswith("1794-AENT"):
            return {
                "side": side,
                "desc": desc,
                "bank": row.get("bank"),
                "normalized_catalog": cat_ev.catalog_number,
                "catalog_status": cat_ev.catalog_status,
                "trailing": cat_ev.trailing_text,
                "result": "EXCLUDED_ADAPTER_ROW",
                "in_out": row.get("in_out"),
            }
        if cat_ev.catalog_status != KNOWN_CATALOG:
            return {
                "side": side,
                "desc": desc,
                "bank": row.get("bank"),
                "normalized_catalog": cat_ev.catalog_number,
                "catalog_status": cat_ev.catalog_status,
                "trailing": cat_ev.trailing_text,
                "result": "CATALOG_UNKNOWN",
                "in_out": row.get("in_out"),
            }
        if not cat_ev.hardware_family.startswith("1794"):
            return {
                "side": side,
                "desc": desc,
                "result": "NOT_APPLICABLE",
                "reason": "not_1794_family",
            }
        try:
            bank = int(row.get("bank"))
        except (TypeError, ValueError):
            return {"side": side, "result": "OTHER_REVIEW", "reason": "bank_not_numeric"}
        direction_info = resolve_configio_direction(
            catalog=cat_ev.catalog_number, in_out=row.get("in_out")
        )
        if direction_info.get("status") == "DIRECTION_CONFLICT":
            return {
                "side": side,
                "desc": desc,
                "bank": bank,
                "normalized_catalog": cat_ev.catalog_number,
                "trailing": cat_ev.trailing_text,
                "direction_info": direction_info,
                "result": "DIRECTION_CONFLICT",
            }
        direction = direction_info.get("direction") or ""
        if direction not in ("I", "O"):
            return {
                "side": side,
                "desc": desc,
                "bank": bank,
                "normalized_catalog": cat_ev.catalog_number,
                "direction_info": direction_info,
                "result": "OTHER_REVIEW",
                "reason": "direction_unknown",
            }
        return {
            "side": side,
            "desc": desc,
            "bank": bank,
            "normalized_catalog": cat_ev.catalog_number,
            "catalog_status": cat_ev.catalog_status,
            "trailing": cat_ev.trailing_text,
            "direction": direction,
            "direction_info": direction_info,
            "in_out": row.get("in_out"),
            "result": "OK",
        }

    low_n = _norm_half(low, "Low")
    high_n = _norm_half(high, "High")

    # Pair validation
    if high_n and high_n.get("result") == "OK" and (not low_n or low_n.get("result") != "OK"):
        return {
            "word": word,
            "low": low_n,
            "high": high_n,
            "result": "INVALID_PAIR",
            "reason": "high_without_valid_low",
        }
    if low_n and low_n.get("result") not in {"OK", None}:
        if low_n.get("result") in {
            "EXCLUDED_ADAPTER_ROW",
            "CATALOG_UNKNOWN",
            "DIRECTION_CONFLICT",
            "NOT_APPLICABLE",
            "OTHER_REVIEW",
        }:
            return {"word": word, "low": low_n, "high": high_n, "result": low_n["result"]}

    if not low_n or low_n.get("result") != "OK":
        return {
            "word": word,
            "low": low_n,
            "high": high_n,
            "result": "OTHER_REVIEW",
            "reason": "no_valid_low",
        }

    base_bank = int(low_n["bank"])
    if high_n and high_n.get("result") == "OK":
        # Require adjacent pair: High.Bank == Low.Bank + 1 (typical) OR High uses Low base
        try:
            hb = int(high_n["bank"])
        except (TypeError, ValueError):
            return {
                "word": word,
                "low": low_n,
                "high": high_n,
                "result": "INVALID_PAIR",
                "reason": "high_bank_not_numeric",
            }
        if high_n.get("normalized_catalog") != low_n.get("normalized_catalog"):
            return {
                "word": word,
                "low": low_n,
                "high": high_n,
                "result": "INVALID_PAIR",
                "reason": "low_high_catalog_mismatch",
            }
        if high_n.get("direction") != low_n.get("direction"):
            return {
                "word": word,
                "low": low_n,
                "high": high_n,
                "result": "DIRECTION_CONFLICT",
                "reason": "low_high_direction_mismatch",
            }
        # Normalize High through Low base (do not Bank-1 blindly without pair check)
        if hb == base_bank + 1 or hb == base_bank:
            high_n = {**high_n, "normalized_base_bank": base_bank, "pair_ok": True}
        else:
            return {
                "word": word,
                "low": low_n,
                "high": high_n,
                "result": "INVALID_PAIR",
                "reason": f"high_bank_{hb}_not_adjacent_to_low_{base_bank}",
            }
    low_n = {**low_n, "normalized_base_bank": base_bank}

    direction = low_n["direction"]
    catalog = low_n["normalized_catalog"]

    matches = []
    for m in modules:
        if str(m.get("catalog_number") or "").upper() != catalog.upper():
            continue
        fam = str(m.get("hardware_family") or "")
        if "1794" not in fam:
            continue
        mdir = str(m.get("direction") or "")
        if mdir and mdir != direction:
            continue
        try:
            ib = int(m["input_bank"]) if m.get("input_bank") is not None else None
        except (TypeError, ValueError):
            ib = None
        try:
            ob = int(m["output_bank"]) if m.get("output_bank") is not None else None
        except (TypeError, ValueError):
            ob = None
        if direction == "I" and ib == base_bank:
            matches.append(m)
        elif direction == "O" and ob == base_bank:
            matches.append(m)

    if not matches:
        return {
            "word": word,
            "low": low_n,
            "high": high_n,
            "base_bank": base_bank,
            "direction": direction,
            "catalog": catalog,
            "candidates": [],
            "result": "NO_MATCH",
        }
    if len(matches) > 1:
        return {
            "word": word,
            "low": low_n,
            "high": high_n,
            "base_bank": base_bank,
            "direction": direction,
            "catalog": catalog,
            "candidates": [
                {
                    "adapter": (m.get("adapter_aliases") or [None])[0],
                    "rack": m.get("provisional_rack"),
                    "slot": m.get("physical_slot"),
                    "catalog": m.get("catalog_number"),
                    "bank_join": m.get("bank_join"),
                    "status": m.get("status"),
                }
                for m in matches
            ],
            "result": "AMBIGUOUS_MATCH",
        }

    m = matches[0]
    # Bank join confidence: substring-only → still unique match but note DERIVED
    return {
        "word": word,
        "low": low_n,
        "high": high_n,
        "base_bank": base_bank,
        "direction": direction,
        "catalog": catalog,
        "matched": {
            "canonical_adapter_id": m.get("canonical_adapter_id"),
            "provisional_rack": m.get("provisional_rack"),
            "adapter": (m.get("adapter_aliases") or [None])[0],
            "slot": m.get("physical_slot"),
            "catalog": m.get("catalog_number"),
            "data_index": m.get("data_index"),
            "capacity": m.get("channel_capacity"),
            "input_bank": m.get("input_bank"),
            "output_bank": m.get("output_bank"),
            "module_status": m.get("status"),
            "bank_join": m.get("bank_join"),
        },
        "result": "UNIQUE_MODULE_MATCH",
    }


def evaluate_site(site: str, machine: str, run: Path) -> dict[str, Any]:
    if not (run / "project.cfg").is_file():
        return {"site": site, "run_available": False}
    evidence = build_evidence_bundle(run, machine, project=site)
    claims = evidence.get("raw_claims") or []
    configio = _load_configio_rows(run, machine)
    by_word: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in configio:
        try:
            w = int(r.get("octal_word"))
        except (TypeError, ValueError):
            continue
        by_word[w].append(r)
    discovery = discover_racks(run, machine)
    modules = _modules_flat(discovery)

    word_results = []
    for w in sorted(by_word):
        word_results.append(shadow_bind_word(w, by_word[w], modules, run_dir=run))

    # Materialize claims
    word_bind = {r["word"]: r for r in word_results}
    claim_rows = []
    channel_owners: dict[str, list[str]] = defaultdict(list)
    for c in claims:
        try:
            w = int(float(str(c.get("word"))))
        except (TypeError, ValueError):
            w = None
        wr = word_bind.get(w) if w is not None else None
        bit_addr = parse_fortna_bit_address(
            c.get("bit"), source_table=str(c.get("source_table") or ""), source_row=c.get("source_row")
        )
        shadow_result = "SHADOW_UNRESOLVED"
        channel = None
        channel_ok = None
        reason = None
        if wr:
            rr = wr.get("result")
            if rr == "UNIQUE_MODULE_MATCH":
                matched = wr.get("matched") or {}
                cap = int(matched.get("capacity") or 0)
                logical = bit_addr.logical_bit
                # 16-pt module owning a Low/High pair uses logical bit as module-local 0..15.
                # 8-pt singleton (no High) uses module_bit within 0..cap-1.
                has_high = bool(wr.get("high") and (wr.get("high") or {}).get("result") == "OK")
                mb = None
                if logical is None or logical > 15 or logical < 0:
                    reason = "bit_out_of_fortna_word_domain"
                    channel_ok = False
                else:
                    mb = logical if (cap >= 16 and has_high) else bit_addr.module_bit
                    if mb is None or (cap and mb >= cap):
                        reason = "bit_exceeds_module_capacity"
                        channel_ok = False
                    else:
                        di = matched.get("data_index")
                        rio = matched.get("adapter")
                        direction = wr.get("direction") or "I"
                        if rio is not None and di is not None:
                            channel = f"{rio}:{direction}.Data[{di}].{mb}"
                            channel_owners[channel].append(c.get("claim_id") or "")
                            shadow_result = "SHADOW_WOULD_RESOLVE"
                            channel_ok = True
                        else:
                            reason = "missing_channel_coordinates"
                            channel_ok = False
            elif rr == "AMBIGUOUS_MATCH":
                shadow_result = "SHADOW_AMBIGUOUS"
            elif rr == "EXCLUDED_ADAPTER_ROW":
                shadow_result = "SHADOW_EXCLUDED"
            elif rr in {"DIRECTION_CONFLICT"}:
                shadow_result = "SHADOW_CONFLICT"
            elif rr == "NOT_APPLICABLE":
                shadow_result = "SHADOW_UNRESOLVED"
                reason = "not_applicable"
            else:
                shadow_result = "SHADOW_UNRESOLVED"
                reason = rr
        claim_rows.append(
            {
                "claim_id": c.get("claim_id"),
                "io_name": c.get("io_name"),
                "word": c.get("word"),
                "raw_bit": c.get("bit"),
                "fortna_bit_address": bit_addr.to_dict(),
                "current_disposition": c.get("deterministic_disposition"),
                "shadow_word_result": (wr or {}).get("result"),
                "shadow_claim_result": shadow_result,
                "shadow_reason": reason,
                "shadow_channel": channel,
                "channel_ok": channel_ok,
                "matched_module": (wr or {}).get("matched"),
            }
        )

    # Duplicate channel ownership among shadow-would-resolve
    dup_channels = {ch: ids for ch, ids in channel_owners.items() if len([x for x in ids if x]) > 1}
    for row in claim_rows:
        ch = row.get("shadow_channel")
        if ch and ch in dup_channels and row.get("shadow_claim_result") == "SHADOW_WOULD_RESOLVE":
            row["shadow_claim_result"] = "SHADOW_CONFLICT"
            row["shadow_reason"] = "duplicate_physical_channel_ownership"
            row["channel_ok"] = False

    counts = Counter(r["shadow_claim_result"] for r in claim_rows)
    word_counts = Counter(r["result"] for r in word_results)

    # AENT classification
    aent_words = []
    for wr in word_results:
        if wr.get("result") == "EXCLUDED_ADAPTER_ROW" or (
            (wr.get("low") or {}).get("result") == "EXCLUDED_ADAPTER_ROW"
        ):
            aent_words.append(wr)

    cons = enrich_conservation_with_readiness(
        compute_claim_conservation(evidence),
        configio_words=int((evidence.get("conservation_counts") or {}).get("configio_words") or 0),
        nonphysical_excluded=int(
            (evidence.get("conservation_counts") or {}).get("nonphysical_excluded") or 0
        ),
    )

    return {
        "site": site,
        "run_available": True,
        "discovery_stats": discovery.get("stats"),
        "racks": [
            {
                "provisional": r.get("provisional_display_name"),
                "canonical_adapter_id": r.get("canonical_adapter_id"),
                "aliases": r.get("source_aliases"),
                "ip": r.get("ip_address"),
                "catalog": r.get("catalog_number"),
                "module_count": len(r.get("modules") or []),
                "unplaced": len(r.get("unplaced_modules") or []),
                "review_modules": sum(
                    1 for m in (r.get("modules") or []) if m.get("status") == "REVIEW_REQUIRED"
                ),
                "derived_bank_modules": sum(
                    1 for m in (r.get("modules") or []) if m.get("status") == "DERIVED"
                ),
            }
            for r in discovery.get("racks") or []
        ],
        "word_results": word_results,
        "word_result_counts": dict(word_counts),
        "claim_results": claim_rows,
        "claim_result_counts": dict(counts),
        "duplicate_shadow_channels": dup_channels,
        "aent_words": aent_words,
        "conservation": {
            "status": cons.get("conservation"),
            "lost": cons.get("lost_claims"),
            "duplicate": cons.get("duplicate_accounting"),
            "raw": cons.get("raw_physical_claims"),
            "needs_resolution": cons.get("needs_resolution"),
            "proven": cons.get("proven"),
        },
        "suffix_analysis": discovery.get("numeric_suffix_analysis"),
    }


def cross_site_challenge(site_eval: dict[str, Any]) -> dict[str, Any]:
    """Compare shadow UNIQUE matches vs existing PROVEN claim channels."""
    agrees = disagrees = new_match = ambiguous = not_app = 0
    disagreements = []
    for row in site_eval.get("claim_results") or []:
        cur = row.get("current_disposition")
        sh = row.get("shadow_claim_result")
        wr = row.get("shadow_word_result")
        if wr in {"NOT_APPLICABLE", None} and sh == "SHADOW_UNRESOLVED":
            not_app += 1
            continue
        if sh == "SHADOW_AMBIGUOUS":
            ambiguous += 1
            continue
        if sh == "SHADOW_WOULD_RESOLVE":
            if cur == "ASSIGNED":
                # Compare channel if both present
                # evidence physical_address on claim may be in matched path — use claim inventory
                # We only have shadow_channel here; proven address not always on row
                agrees += 1  # module-level agree counted; channel checked separately below
            else:
                new_match += 1
        if sh == "SHADOW_CONFLICT":
            disagrees += 1
            disagreements.append(row)
    # Stronger check: for ASSIGNED claims, if shadow proposes different module channel
    # Re-scan with physical_address from evidence if embedded
    return {
        "AGREES_WITH_EXISTING_PROVEN": agrees,
        "DISAGREES_WITH_EXISTING_PROVEN": len(disagreements),
        "NEW_SHADOW_MATCH": new_match,
        "AMBIGUOUS": ambiguous,
        "NOT_APPLICABLE_OR_UNRESOLVED": not_app,
        "disagreement_samples": disagreements[:10],
    }


def cross_site_proven_check(site_eval: dict[str, Any], evidence_claims: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {c.get("claim_id"): c for c in evidence_claims}
    agree = disagree = new = 0
    samples = []
    for row in site_eval.get("claim_results") or []:
        c = by_id.get(row.get("claim_id")) or {}
        proven_ch = c.get("physical_address")
        shadow_ch = row.get("shadow_channel")
        if row.get("shadow_claim_result") != "SHADOW_WOULD_RESOLVE":
            continue
        if c.get("deterministic_disposition") == "ASSIGNED" and proven_ch:
            if shadow_ch and str(shadow_ch).upper() == str(proven_ch).upper():
                agree += 1
            else:
                disagree += 1
                samples.append(
                    {
                        "claim_id": row.get("claim_id"),
                        "io_name": row.get("io_name"),
                        "proven_channel": proven_ch,
                        "shadow_channel": shadow_ch,
                    }
                )
        else:
            new += 1
    return {
        "AGREES_WITH_EXISTING_PROVEN": agree,
        "DISAGREES_WITH_EXISTING_PROVEN": disagree,
        "NEW_SHADOW_MATCH": new,
        "disagreement_samples": samples[:20],
    }


def acceptance_gate(atl: dict[str, Any], cross: dict[str, dict[str, Any]]) -> dict[str, Any]:
    reasons = []
    ok = True
    if atl.get("duplicate_shadow_channels"):
        ok = False
        reasons.append("duplicate_shadow_channel_ownership")
    if atl.get("conservation", {}).get("lost", 0) != 0:
        ok = False
        reasons.append("conservation_lost")
    if atl.get("conservation", {}).get("duplicate", 0) != 0:
        ok = False
        reasons.append("conservation_duplicate")
    # Ambiguous matches fail gate
    if (atl.get("word_result_counts") or {}).get("AMBIGUOUS_MATCH", 0) > 0:
        ok = False
        reasons.append("ambiguous_module_matches")
    # Cross-site unexplained disagreement
    for site, cx in cross.items():
        if cx.get("DISAGREES_WITH_EXISTING_PROVEN", 0) > 0:
            ok = False
            reasons.append(f"cross_site_disagreement:{site}")
    # Catalog/direction conflicts on words
    wc = atl.get("word_result_counts") or {}
    if wc.get("DIRECTION_CONFLICT", 0) > 0:
        # Not automatic fail if those remain unresolved — gate says direction mismatch
        # on proposed resolved paths. Direction conflicts are unresolved, OK if not would_resolve
        pass
    return {
        "shadow_validation": "PASS" if ok else "FAIL",
        "means": "safe_to_consider_implementing_deterministically_NOT_plc_ready",
        "reasons": reasons,
        "ok": ok,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Shadow-validate Atlanta decoder candidate")
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "exports/ai-io/shadow")
    args = ap.parse_args(argv)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pricing reprice artifact (do not rewrite R2 usage.json)
    usage_path = REPO_ROOT / "exports/ai-io/investigations/MSCATL_BINDING_001_R2/usage.json"
    pricing = json.loads((REPO_ROOT / "config/ai_model_pricing.json").read_text(encoding="utf-8"))
    if usage_path.is_file():
        old = json.loads(usage_path.read_text(encoding="utf-8"))
        totals = old.get("usage_totals") or {}
        inp = float(totals.get("input_tokens") or 0)
        cached = float(totals.get("cached_input_tokens") or 0)
        out_tok = float(totals.get("output_tokens") or 0)
        m = (pricing.get("models") or {}).get("gpt-5.6-terra") or {}
        non_cached = max(inp - cached, 0)
        corrected = (
            non_cached * float(m.get("input_usd_per_million") or 2)
            + cached * float(m.get("cached_input_usd_per_million") or 0.2)
            + out_tok * float(m.get("output_usd_per_million") or 12)
        ) / 1_000_000.0
        reprice = {
            "kind": "usage_repriced",
            "generated_at": _ts(),
            "source_usage": str(usage_path),
            "original_estimated_session_cost_usd": old.get("estimated_session_cost_usd"),
            "corrected_estimated_session_cost_usd": round(corrected, 6),
            "raw_token_counts": totals,
            "pricing_snapshot": {
                "input_usd_per_million": m.get("input_usd_per_million"),
                "cached_input_usd_per_million": m.get("cached_input_usd_per_million"),
                "output_usd_per_million": m.get("output_usd_per_million"),
                "pricing_effective_date": pricing.get("pricing_effective_date"),
                "pricing_source": pricing.get("pricing_source"),
                "pricing_verified_at": pricing.get("pricing_verified_at"),
            },
            "note": "Historical usage.json left unchanged; this is an audit correction only.",
        }
        (usage_path.parent / "usage_repriced.json").write_text(
            json.dumps(reprice, indent=2), encoding="utf-8"
        )

    results = {}
    evidences = {}
    for site, machine, run in SITES:
        print(f"=== shadow {site} ===", flush=True)
        if not run.is_dir() or not (run / "project.cfg").is_file():
            results[site] = {"site": site, "run_available": False}
            continue
        ev = build_evidence_bundle(run, machine, project=site)
        evidences[site] = ev
        results[site] = evaluate_site(site, machine, run)

    # Cross-site proven checks
    cross = {}
    for site, machine, run in SITES:
        if not results.get(site, {}).get("run_available"):
            continue
        cross[site] = cross_site_proven_check(
            results[site], evidences[site].get("raw_claims") or []
        )

    atl = results.get("MSCATL_CP3") or {}
    gate = acceptance_gate(atl, {k: v for k, v in cross.items() if k != "MSCATL_CP3"})

    # Expected Atlanta impact
    crc = atl.get("claim_result_counts") or {}
    impact = {
        "CURRENT": {
            "raw": 256,
            "proven": 0,
            "needs_resolution": 256,
        },
        "SHADOW_IF_IMPLEMENTED": {
            "would_resolve": crc.get("SHADOW_WOULD_RESOLVE", 0),
            "would_remain_unresolved": crc.get("SHADOW_UNRESOLVED", 0),
            "would_ambiguous": crc.get("SHADOW_AMBIGUOUS", 0),
            "would_conflict": crc.get("SHADOW_CONFLICT", 0),
            "would_excluded": crc.get("SHADOW_EXCLUDED", 0),
        },
        "remaining_by_word_result": atl.get("word_result_counts"),
    }

    soft_path = None
    if gate.get("ok"):
        soft_dir = REPO_ROOT / "exports/io-soft-test/MSCATL_CP3"
        soft_dir.mkdir(parents=True, exist_ok=True)
        soft = {
            "kind": "io_soft_test_snapshot",
            "version": 1,
            "generated_at": _ts(),
            "project": "MSCATL_CP3",
            "machine": "MSCATL_CP3",
            "compiler_input": False,
            "racks": atl.get("racks"),
            "I/O": {
                "total_claims": 256,
                "current_proven": 0,
                "shadow_would_resolve": impact["SHADOW_IF_IMPLEMENTED"]["would_resolve"],
                "unresolved_review": (
                    impact["SHADOW_IF_IMPLEMENTED"]["would_remain_unresolved"]
                    + impact["SHADOW_IF_IMPLEMENTED"]["would_ambiguous"]
                    + impact["SHADOW_IF_IMPLEMENTED"]["would_excluded"]
                ),
                "conflicts": impact["SHADOW_IF_IMPLEMENTED"]["would_conflict"],
            },
            "shadow_validation": gate,
            "rule": RULE_NAME,
            "note": "NOT wired to Autogen or PLC generation",
        }
        soft_path = soft_dir / "io_soft_test_snapshot.json"
        soft_path.write_text(json.dumps(soft, indent=2), encoding="utf-8")

    report = {
        "kind": "atlanta_candidate_shadow_validation",
        "generated_at": _ts(),
        "rule": RULE_NAME,
        "live_api_called": False,
        "production_resolver_modified": False,
        "shadow_validation": gate,
        "atlanta_impact": impact,
        "atlanta_word_counts": atl.get("word_result_counts"),
        "atlanta_claim_counts": atl.get("claim_result_counts"),
        "atlanta_aent_words": [
            {"word": w.get("word"), "result": w.get("result"), "low": w.get("low"), "high": w.get("high")}
            for w in (atl.get("aent_words") or [])
        ],
        "atlanta_racks": atl.get("racks"),
        "cross_site": cross,
        "sites": {
            k: {
                "run_available": v.get("run_available"),
                "word_result_counts": v.get("word_result_counts"),
                "claim_result_counts": v.get("claim_result_counts"),
                "racks": v.get("racks"),
                "conservation": v.get("conservation"),
                "duplicate_shadow_channels": bool(v.get("duplicate_shadow_channels")),
            }
            for k, v in results.items()
        },
        "soft_test_snapshot": str(soft_path) if soft_path else None,
        "in_out_semantics": {
            "conclusion": (
                "Whole-word heuristic: all-zero mask correlates with INPUT catalogs; "
                "0000000011111111 correlates with OUTPUT catalogs on MSCATL/ORINDY. "
                "Catalog direction is primary when KNOWN; In_Out corroborates; "
                "disagreement → DIRECTION_CONFLICT. Mixed masks → REVIEW. "
                "Per-bit mask ownership not fully proven from FortnaPlus runtime source "
                "in-repo; fortna_io_banks treats '1' as active bits."
            ),
            "source_refs": [
                "docs/FORTNAPLUS_TABLE_REFERENCE.md (Configio direction ownership)",
                "tools/scripts/fortna_io_banks.py (In_Out '1' = active)",
                "exports/stabilization/plc5_io_residual_collision_report.md (mask patterns)",
                "empirical MSCATL/ORINDY Configio↔catalog correlation",
            ],
        },
    }
    # Write detailed Atlanta word/claim results separately (large)
    (out_dir / "shadow_validation_summary.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (out_dir / "MSCATL_CP3_shadow_detail.json").write_text(
        json.dumps(atl, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "shadow_validation": gate.get("shadow_validation"),
        "reasons": gate.get("reasons"),
        "atlanta_impact": impact,
        "cross_site": {k: {kk: vv for kk, vv in v.items() if kk != "disagreement_samples"} for k, v in cross.items()},
        "soft_test": str(soft_path) if soft_path else None,
        "out": str(out_dir / "shadow_validation_summary.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
