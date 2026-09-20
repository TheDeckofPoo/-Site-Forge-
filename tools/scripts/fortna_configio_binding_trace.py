#!/usr/bin/env python3
"""Read-only Configio → hardware binding trace for Decoder Investigator tools.

get_configio_binding_trace(word) returns every candidate attempted and why
accepted/rejected — without mutating Site Forge state.
"""
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

from fortna_ai_io_evidence import build_raw_claims  # noqa: E402
from fortna_hardware_family import detect_family_from_catalog  # noqa: E402
from fortna_hardware_identity import build_hardware_identity_model  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    _load_configio_rows,
    _module_matching_bank,
    _module_direction,
    build_physical_word_map,
    parse_configio_catalog_word_bank,
    parse_eipcfg,
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_configio_binding_trace(
    run_dir: Path | str,
    machine: str,
    word: int | str,
) -> dict[str, Any]:
    """Complete attempted reasoning for one Configio Octal_Word (read-only)."""
    run_dir = Path(run_dir)
    machine = (machine or "").strip()
    try:
        w = int(float(str(word).strip()))
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid_word", "word": word}

    configio = _load_configio_rows(run_dir, machine)
    halves = [r for r in configio if int(r.get("octal_word") or -1) == w]
    low = next((r for r in halves if str(r.get("lohi") or "").lower().startswith("lo")), None)
    high = next((r for r in halves if str(r.get("lohi") or "").lower().startswith("hi")), None)

    topo = parse_eipcfg(run_dir, machine)
    adapters = list(topo.get("adapters") or [])
    pm = build_physical_word_map(run_dir, machine)
    word_entry = (pm.get("words") or {}).get(str(w))
    unresolved = [
        u for u in (pm.get("unresolved") or []) if int(u.get("octal_word") or -1) == w
    ]

    attempts: list[dict[str, Any]] = []
    accepted: dict[str, Any] | None = None

    def _try_bank_match(row: dict[str, Any], side: str) -> None:
        nonlocal accepted
        cbp = row.get("catalog_bank_parsed") or parse_configio_catalog_word_bank(
            str(row.get("desc") or "")
        ) or {}
        try:
            eip_bank = int(row.get("bank"))
        except (TypeError, ValueError):
            attempts.append(
                {
                    "strategy": "configio_bank_match",
                    "side": side,
                    "result": "rejected",
                    "reason": "bank_not_numeric",
                    "bank": row.get("bank"),
                }
            )
            return
        cat_u = str(cbp.get("catalog") or "").upper()
        direction = cbp.get("direction") or _module_direction(cat_u)
        found = False
        for ad in adapters:
            for mod in ad.get("modules") or []:
                if (mod.get("connection") or "").upper() == "HEADNODE":
                    continue
                if "AENT" in (mod.get("type") or "").upper():
                    continue
                try:
                    ib = int(mod["input_bank"]) if mod.get("input_bank") is not None else None
                except (TypeError, ValueError):
                    ib = None
                try:
                    ob = int(mod["output_bank"]) if mod.get("output_bank") is not None else None
                except (TypeError, ValueError):
                    ob = None
                matched = False
                match_field = ""
                if direction == "I" and ib == eip_bank:
                    matched, match_field = True, "input_bank"
                elif direction == "O" and ob == eip_bank:
                    matched, match_field = True, "output_bank"
                elif direction == "" and (ib == eip_bank or ob == eip_bank):
                    matched = True
                    match_field = "input_bank" if ib == eip_bank else "output_bank"
                if not matched:
                    continue
                mt = (mod.get("type") or "").upper()
                if cat_u and cat_u not in mt and mt not in cat_u:
                    soft = cat_u.replace("OA8I", "OA8") in mt.replace("OA8I", "OA8") or mt.replace(
                        "OA8I", "OA8"
                    ) in cat_u.replace("OA8I", "OA8")
                    if not soft:
                        attempts.append(
                            {
                                "strategy": "configio_bank_match",
                                "side": side,
                                "adapter": ad.get("rio_name") or ad.get("name"),
                                "module": mod.get("name"),
                                "slot": mod.get("slot"),
                                "catalog": mod.get("type"),
                                "bank": eip_bank,
                                "result": "rejected",
                                "reason": "catalog_mismatch",
                                "configio_catalog": cat_u,
                                "module_catalog": mt,
                            }
                        )
                        continue
                attempts.append(
                    {
                        "strategy": "configio_bank_match",
                        "side": side,
                        "adapter": ad.get("rio_name") or ad.get("name"),
                        "module": mod.get("name"),
                        "slot": mod.get("slot"),
                        "catalog": mod.get("type"),
                        "bank": eip_bank,
                        "match_field": match_field,
                        "result": "accepted" if not accepted else "candidate_after_accept",
                        "reason": "bank_and_catalog_ok",
                    }
                )
                if not accepted:
                    accepted = {
                        "strategy": "configio_bank_match",
                        "adapter": ad.get("rio_name") or ad.get("name"),
                        "module": mod.get("name"),
                        "slot": mod.get("slot"),
                        "catalog": mod.get("type"),
                        "bank": eip_bank,
                        "direction": direction or mod.get("direction"),
                    }
                found = True
                break
            if found:
                break
        if not found:
            attempts.append(
                {
                    "strategy": "configio_bank_match",
                    "side": side,
                    "bank": eip_bank,
                    "configio_catalog": cat_u or None,
                    "direction": direction,
                    "result": "rejected",
                    "reason": "no_eipmodules_bank_match",
                }
            )

    def _try_bank_only(row: dict[str, Any], side: str) -> None:
        nonlocal accepted
        try:
            cfg_bank = int(row.get("bank"))
        except (TypeError, ValueError):
            return
        hit = None
        for ad in adapters:
            hit = _module_matching_bank(ad, cfg_bank)
            if hit:
                cand, cand_dir = hit
                attempts.append(
                    {
                        "strategy": "configio_bank_only",
                        "side": side,
                        "adapter": ad.get("rio_name") or ad.get("name"),
                        "module": cand.get("name"),
                        "slot": cand.get("slot"),
                        "catalog": cand.get("type"),
                        "bank": cfg_bank,
                        "result": "accepted" if not accepted else "candidate_after_accept",
                        "reason": "synthesized_or_eipmodules_bank_hit",
                    }
                )
                if not accepted:
                    accepted = {
                        "strategy": "configio_bank_only",
                        "adapter": ad.get("rio_name") or ad.get("name"),
                        "module": cand.get("name"),
                        "slot": cand.get("slot"),
                        "catalog": cand.get("type"),
                        "bank": cfg_bank,
                        "direction": cand_dir,
                    }
                return
        attempts.append(
            {
                "strategy": "configio_bank_only",
                "side": side,
                "bank": cfg_bank,
                "result": "rejected",
                "reason": "bank_not_found_on_any_adapter",
            }
        )

    for side, row in (("Low", low), ("High", high)):
        if not row:
            attempts.append(
                {"strategy": "configio_half_present", "side": side, "result": "absent"}
            )
            continue
        _try_bank_match(row, side)
        if not accepted:
            _try_bank_only(row, side)

    # Final from physical map
    if word_entry:
        final = {
            "result": "BOUND",
            "assign_how": word_entry.get("assign_how"),
            "rio_name": word_entry.get("rio_name"),
            "catalog": word_entry.get("type"),
            "data_index": word_entry.get("data_index"),
            "eip_slot": word_entry.get("eip_slot"),
            "family": word_entry.get("family"),
        }
    elif unresolved:
        final = {
            "result": "NO_BINDING",
            "reason": unresolved[0].get("reason") or "no_eipmodules_bank_match",
            "unresolved_detail": unresolved[0],
        }
    else:
        final = {
            "result": "NO_BINDING",
            "reason": "word_absent_from_physical_map",
        }

    hw = build_hardware_identity_model(run_dir, machine)
    return {
        "ok": True,
        "kind": "configio_binding_trace",
        "machine": machine,
        "word": w,
        "configio": {
            "halves": [
                {
                    "row": r.get("row"),
                    "Octal_Word": r.get("octal_word"),
                    "Bank": r.get("bank"),
                    "LoHi": r.get("lohi"),
                    "Desc": r.get("desc"),
                    "In_Out": r.get("in_out"),
                    "Interface": r.get("interface"),
                    "catalog_bank_parsed": r.get("catalog_bank_parsed"),
                }
                for r in halves
            ]
        },
        "candidates_attempted": attempts,
        "accepted_candidate": accepted,
        "final": final,
        "hardware_adapters": [
            {
                "canonical_id": a.get("canonical_id"),
                "aliases": a.get("aliases"),
                "ip": a.get("ip_address"),
                "catalog": a.get("catalog_number"),
                "family": a.get("adapter_family"),
            }
            for a in hw.get("adapters") or []
        ],
        "read_only": True,
    }


def build_mscatl_binding_dossier(
    run_dir: Path | str | None = None,
    machine: str = "MSCATL_CP3",
) -> dict[str, Any]:
    run_dir = Path(
        run_dir or (REPO_ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN")
    )
    configio = _load_configio_rows(run_dir, machine)
    words = sorted({int(r["octal_word"]) for r in configio if r.get("octal_word") is not None})
    raw = build_raw_claims(run_dir, machine)
    hw = build_hardware_identity_model(run_dir, machine)
    pm = build_physical_word_map(run_dir, machine)

    word_traces = []
    root_buckets: dict[str, dict[str, Any]] = {}
    for w in words:
        tr = get_configio_binding_trace(run_dir, machine, w)
        reason = (tr.get("final") or {}).get("reason") or (tr.get("final") or {}).get("result")
        # Prefer most specific rejection among attempts if NO_BINDING
        if (tr.get("final") or {}).get("result") == "NO_BINDING":
            rej = [
                a.get("reason")
                for a in tr.get("candidates_attempted") or []
                if a.get("result") == "rejected" and a.get("reason")
            ]
            if rej:
                # majority rejection reason
                reason = Counter(rej).most_common(1)[0][0]
        claims = [c for c in raw if str(c.get("word")) == str(w)]
        word_traces.append(
            {
                "word": w,
                "claim_count": len(claims),
                "root_cause": reason,
                "trace": tr,
                "sample_claims": [
                    {
                        "claim_id": c.get("claim_id"),
                        "io_name": c.get("io_name"),
                        "bit": c.get("bit"),
                        "disposition": c.get("deterministic_disposition"),
                    }
                    for c in claims[:6]
                ],
            }
        )
        bucket = root_buckets.setdefault(
            str(reason),
            {"root_cause": reason, "words": [], "claim_count": 0, "word_count": 0},
        )
        bucket["words"].append(w)
        bucket["word_count"] += 1
        bucket["claim_count"] += len(claims)

    clusters = sorted(root_buckets.values(), key=lambda x: -x["claim_count"])
    return {
        "kind": "mscatl_binding_dossier",
        "generated_at": _ts(),
        "project": "MSCATL_CP3",
        "machine": machine,
        "run_dir": str(run_dir),
        "site_summary": {
            "physical_claims": len(raw),
            "proven": sum(1 for c in raw if c.get("deterministic_disposition") == "ASSIGNED"),
            "unresolved": sum(
                1
                for c in raw
                if c.get("deterministic_disposition")
                in {"physical_resolution_failure", "OWNER_CONFLICT", "UNRESOLVED_OWNER"}
            ),
            "configio_words": len(words),
            "adapters": len(hw.get("adapters") or []),
            "modules": len(hw.get("modules") or []),
            "true_hardware_conflicts": (hw.get("stats") or {}).get("true_conflict_count"),
            "hardware_types": (hw.get("stats") or {}).get("hardware_type_count"),
        },
        "root_cause_clusters": clusters,
        "word_traces": word_traces,
        "physical_map_unresolved_sample": (pm.get("unresolved") or [])[:20],
        "configio_gui_corroboration": hw.get("configio_gui_corroboration"),
    }


def build_mscatl_investigation_packet(dossier: dict[str, Any]) -> dict[str, Any]:
    clusters = dossier.get("root_cause_clusters") or []
    words = dossier.get("word_traces") or []
    reps = []
    for w in words[:8]:
        reps.append(
            {
                "word": w.get("word"),
                "root_cause": w.get("root_cause"),
                "claim_count": w.get("claim_count"),
                "configio": (w.get("trace") or {}).get("configio"),
                "final": (w.get("trace") or {}).get("final"),
                "rejected_reasons": [
                    a.get("reason")
                    for a in ((w.get("trace") or {}).get("candidates_attempted") or [])
                    if a.get("result") == "rejected"
                ][:8],
            }
        )
    sample_claims = []
    for w in words:
        for c in w.get("sample_claims") or []:
            sample_claims.append(c)
            if len(sample_claims) >= 20:
                break
        if len(sample_claims) >= 20:
            break

    return {
        "kind": "decoder_investigator_packet",
        "version": 1,
        "generated_at": _ts(),
        "live_api_called": False,
        "project": "MSCATL_CP3",
        "machine": "MSCATL_CP3",
        "problem_statement": (
            "Site Forge sees Configio-backed physical I/O claims and physical hardware "
            "topology on MSCATL_CP3, but resolves zero claims. Identify the missing "
            "deterministic Fortna binding convention — do not assign endpoints."
        ),
        "site_summary": dossier.get("site_summary"),
        "root_cause_clusters": clusters,
        "representative_configio_words": reps,
        "representative_unresolved_claims": sample_claims,
        "hardware_topology_summary": {
            "adapters": (dossier.get("site_summary") or {}).get("adapters"),
            "modules": (dossier.get("site_summary") or {}).get("modules"),
            "true_hardware_conflicts": (dossier.get("site_summary") or {}).get(
                "true_hardware_conflicts"
            ),
        },
        "available_read_only_tools": [
            "get_project_identity",
            "get_machine",
            "get_io_claim",
            "get_configio_word",
            "get_configio_rows",
            "get_configio_binding_trace",
            "get_adapter",
            "get_module",
            "get_neighbor_claims",
            "get_proven_io_examples",
            "get_failure_cluster",
            "get_physical_word_resolution_trace",
            "compare_candidate_rule_against_site",
        ],
        "observed_deterministic_failure_traces": [
            {
                "word": w.get("word"),
                "root_cause": w.get("root_cause"),
                "final": (w.get("trace") or {}).get("final"),
            }
            for w in words
        ],
        "known_facts": [
            "256 physical claims; 0 proven; 256 physical_resolution_failure",
            f"{(dossier.get('site_summary') or {}).get('configio_words')} Configio words present",
            "eipcfg XML + EIPModules present (PARTIAL_VALUE host/XML — already used)",
            "Hardware type vs instance identity separated; catalog reuse is not a conflict",
            "FortnaPlus GUI IO Configure columns match Configio.asc semantics",
            "AI must not return physical_endpoint / ai_derived / READY / Autogen / PLC",
        ],
        "ambiguities": [
            "Whether MSCATL Desc/bank conventions differ from ORINDY catalog_word_bank",
            "Whether Interface/IOCard linkage is required before bank match",
            "Whether EIPModules bank numbering uses a different base than Configio.Bank",
        ],
        "questions_for_investigator": [
            (
                "Site Forge sees 256 Configio-backed physical I/O claims and physical "
                "hardware topology, but resolves zero claims. What deterministic Fortna "
                "binding convention appears to be missing, what evidence supports that "
                "hypothesis, what contradicts it, and what rule should Site Forge investigate?"
            )
        ],
        "output_contract": {
            "type": "DecoderRuleCandidate",
            "allowed_status": ["CANDIDATE", "REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE"],
            "forbidden_fields": [
                "physical_endpoint",
                "ai_derived",
                "READY",
                "Autogen",
                "plc_channel",
                "compiler_accepted",
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, default=None)
    ap.add_argument("--machine", default="MSCATL_CP3")
    ap.add_argument("--word", type=int, default=None)
    ap.add_argument("--build-packet", action="store_true")
    args = ap.parse_args(argv)
    if args.word is not None:
        run = args.run_dir or (
            REPO_ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"
        )
        print(json.dumps(get_configio_binding_trace(run, args.machine, args.word), indent=2))
        return 0
    dossier = build_mscatl_binding_dossier(args.run_dir, args.machine)
    out_dir = REPO_ROOT / "exports" / "ai-io" / "investigations"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "mscatl_binding_dossier.json").write_text(
        json.dumps(dossier, indent=2), encoding="utf-8"
    )
    packet = build_mscatl_investigation_packet(dossier)
    packet_path = out_dir / "mscatl_binding_investigation_packet.json"
    packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "configio_words": dossier["site_summary"]["configio_words"],
                "physical_claims": dossier["site_summary"]["physical_claims"],
                "proven": dossier["site_summary"]["proven"],
                "root_cause_clusters": [
                    {
                        "root_cause": c["root_cause"],
                        "words": c["word_count"],
                        "claims": c["claim_count"],
                    }
                    for c in dossier["root_cause_clusters"]
                ],
                "packet": str(packet_path),
                "live_api_called": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
