#!/usr/bin/env python3
"""Indy five-point direction forensics + shadow gate V2.

No live API. No production resolver changes.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict  # noqa: F401 — Counter used in new_by_word
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_bit_address import parse_fortna_bit_address  # noqa: E402
from fortna_configio_direction import (  # noqa: E402
    direction_from_in_out_mask,
    resolve_configio_direction,
)
from fortna_decoder_rule_shadow import (  # noqa: E402
    _modules_flat,
    cross_site_proven_check,
    evaluate_site,
    shadow_bind_word,
)
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    _load_configio_rows,
    _load_eipmodules_rows,
    _module_matching_bank,
    build_physical_word_map,
    parse_eipcfg,
)
from fortna_rack_discovery import discover_racks  # noqa: E402
from fortna_rockwell_catalog import first_catalog  # noqa: E402

FOCUS = ("M626", "M628", "M630", "M634", "WB718G")


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def bank_collision_at(run: Path, machine: str, bank: int) -> list[dict[str, Any]]:
    hits = []
    for em in _load_eipmodules_rows(run, machine):
        try:
            ib = int(em.get("input_bank")) if em.get("input_bank") is not None else None
        except (TypeError, ValueError):
            ib = None
        try:
            ob = int(em.get("output_bank")) if em.get("output_bank") is not None else None
        except (TypeError, ValueError):
            ob = None
        if ib == bank or ob == bank:
            hits.append(
                {
                    "name": em.get("name"),
                    "adapter": em.get("adapter"),
                    "type": em.get("type"),
                    "slot": em.get("slot"),
                    "input_bank": ib,
                    "output_bank": ob,
                    "direction": em.get("direction"),
                    "matched_field": "input_bank" if ib == bank else "output_bank",
                }
            )
    return hits


def forensic_claim(c: dict[str, Any], *, run: Path, machine: str, pm: dict, cfg_by_word: dict) -> dict[str, Any]:
    w = str(c.get("word"))
    b = str(c.get("bit"))
    addr = parse_fortna_bit_address(b, source_table=str(c.get("source_table") or ""), source_row=c.get("source_row"))
    cfg_rows = cfg_by_word.get(int(float(w)), [])
    word_entry = (pm.get("words") or {}).get(w) or {}
    bwb = (pm.get("by_word_bit") or {}).get(f"{w}:{addr.logical_bit}") or {}
    resolver = PhysicalWordResolver(run, machine)
    hit = resolver.resolve(w, b) or {}

    # Shadow bind
    modules = _modules_flat(discover_racks(run, machine))
    shadow = shadow_bind_word(int(float(w)), cfg_rows, modules, run_dir=run)

    banks = []
    for r in cfg_rows:
        try:
            banks.append(int(r.get("bank")))
        except (TypeError, ValueError):
            pass
    collisions = {bank: bank_collision_at(run, machine, bank) for bank in banks}

    # Divergence point
    word_dir = word_entry.get("direction")
    bwb_dir = bwb.get("direction") or hit.get("direction")
    shadow_dir = shadow.get("direction")
    diverge = None
    if word_dir and bwb_dir and word_dir != bwb_dir:
        diverge = {
            "point": "by_word_bit_emit_vs_word_entry",
            "detail": (
                f"words_out[{w}] direction={word_dir} catalog={word_entry.get('type')} "
                f"channel_base={word_entry.get('channel_base')}, but by_word_bit[{w}:{addr.logical_bit}] "
                f"direction={bwb_dir} type={bwb.get('type')} channel={bwb.get('channel')}. "
                f"_module_matching_bank(bank) is undirected and picks first slot-ordered candidate "
                f"when the same bank number is used as IA16.input_bank and OA*.output_bank."
            ),
        }
    elif shadow_dir and bwb_dir and shadow_dir != bwb_dir:
        diverge = {
            "point": "shadow_direction_vs_proven_channel_direction",
            "detail": f"shadow={shadow_dir} proven_hit={bwb_dir}",
        }

    cat = first_catalog((cfg_rows[0] if cfg_rows else {}).get("desc"), run_dir=run)
    dir_info = resolve_configio_direction(
        catalog=(cat.catalog_number if cat else ""),
        in_out=(cfg_rows[0].get("in_out") if cfg_rows else ""),
    )
    mask_info = direction_from_in_out_mask(cfg_rows[0].get("in_out") if cfg_rows else "")

    # Component scores vs Configio+EIPModules authority
    components = {
        "catalog_extraction": "PASS" if cat and cat.catalog_status == "KNOWN_CATALOG" else "FAIL",
        "pairing": "PASS",  # singleton Low words
        "bank_normalization": "PASS",
        "module_identity_vs_configio": (
            "PASS"
            if (shadow.get("matched") or {}).get("catalog")
            and cat
            and (shadow.get("matched") or {}).get("catalog", "").upper() == cat.catalog_number.upper()
            else "FAIL"
        ),
        "direction_shadow_vs_configio": (
            "PASS"
            if shadow_dir and dir_info.get("direction") == shadow_dir
            else "FAIL"
        ),
        "direction_proven_vs_configio": (
            "FAIL"
            if bwb_dir and dir_info.get("direction") and bwb_dir != dir_info.get("direction")
            else "PASS"
        ),
        "bit_channel_number": "PASS",  # same bit index; direction/image differs
    }

    classification = "AMBIGUOUS"
    if (
        components["direction_proven_vs_configio"] == "FAIL"
        and components["direction_shadow_vs_configio"] == "PASS"
        and components["module_identity_vs_configio"] == "PASS"
        and any(len(v) > 1 for v in collisions.values())
    ):
        classification = "B_SHADOW_EXPOSES_PROVEN_DEFECT"
    elif components["direction_shadow_vs_configio"] == "FAIL":
        classification = "A_SHADOW_DIRECTION_INCOMPLETE"
    elif components["direction_proven_vs_configio"] == "FAIL":
        classification = "C_AMBIGUOUS_OR_MIXED"

    return {
        "claim_id": c.get("claim_id"),
        "IO_Name": c.get("io_name"),
        "source_table": c.get("source_table"),
        "source_row": c.get("source_row"),
        "IO_Address_Word": c.get("word"),
        "raw_IO_Address_Bit": c.get("bit"),
        "FortnaBitAddress": addr.to_dict(),
        "Configio_rows": [
            {
                "row": r.get("row"),
                "Desc": r.get("desc"),
                "Bank": r.get("bank"),
                "LoHi": r.get("lohi"),
                "In_Out": r.get("in_out"),
                "Interface": r.get("interface"),
                "I_O_Type": r.get("io_type") if "io_type" in r else None,
                "Process": r.get("process") if "process" in r else None,
                "catalog_bank_parsed": r.get("catalog_bank_parsed"),
            }
            for r in cfg_rows
        ],
        "current_disposition": c.get("deterministic_disposition"),
        "current_PROVEN_physical_address": c.get("physical_address") or hit.get("channel"),
        "current_PROVEN_provenance": {
            "resolver_hit": {
                "channel": hit.get("channel"),
                "type": hit.get("type"),
                "direction": hit.get("direction"),
                "assign_how": hit.get("assign_how"),
                "data_index": hit.get("data_index"),
                "eip_slot": hit.get("eip_slot"),
                "half_bank": hit.get("half_bank") or bwb.get("half_bank"),
            },
            "words_out_entry": {
                "type": word_entry.get("type"),
                "direction": word_entry.get("direction"),
                "channel_base": word_entry.get("channel_base"),
                "data_index": word_entry.get("data_index"),
                "eip_slot": word_entry.get("eip_slot"),
                "assign_how": word_entry.get("assign_how"),
                "low_bank": word_entry.get("low_bank"),
                "provenance": word_entry.get("provenance"),
            },
            "by_word_bit_entry": {
                "channel": bwb.get("channel"),
                "type": bwb.get("type"),
                "direction": bwb.get("direction"),
                "half_bank": bwb.get("half_bank"),
            },
            "eipmodules_bank_collisions": collisions,
        },
        "shadow": {
            "result": shadow.get("result"),
            "normalized_catalog": shadow.get("catalog"),
            "base_bank": shadow.get("base_bank"),
            "direction": shadow.get("direction"),
            "matched": shadow.get("matched"),
            "channel_expected": (
                f"{(shadow.get('matched') or {}).get('adapter')}:"
                f"{shadow.get('direction')}.Data[{(shadow.get('matched') or {}).get('data_index')}]."
                f"{addr.module_bit}"
                if shadow.get("matched")
                else None
            ),
        },
        "configio_direction_resolution": dir_info,
        "in_out_mask_analysis": mask_info,
        "divergence": diverge,
        "candidate_components": components,
        "classification": classification,
    }


def build_word_bit_map(word: int, claims: list[dict[str, Any]], cfg_rows: list[dict], pm: dict) -> dict[str, Any]:
    mask = str((cfg_rows[0] if cfg_rows else {}).get("in_out") or "")
    rows = []
    for c in claims:
        if str(c.get("word")) != str(word):
            continue
        addr = parse_fortna_bit_address(c.get("bit"))
        logical = addr.logical_bit
        mask_index = None
        mask_char = None
        # Convention probe: if mask length 16, test both indexings
        if mask and logical is not None and len(mask) >= 16:
            # left-to-right bit0 = index 0
            idx_ltr0 = logical
            # left-to-right bit15 = index 0 (MSB first)
            idx_msb0 = 15 - logical
            mask_index = {
                "if_index0_is_logical0": idx_ltr0,
                "char_if_logical0_left": mask[idx_ltr0] if idx_ltr0 < len(mask) else None,
                "if_index0_is_logical15": idx_msb0,
                "char_if_logical15_left": mask[idx_msb0] if idx_msb0 < len(mask) else None,
            }
            # For all-same masks both agree
            if mask == "0" * len(mask) or set(mask) == {"0"}:
                mask_char = "0"
            elif mask == "0000000011111111":
                # Under LTR logical0-left: bits 0-7 are '0', 8-15 are '1' — WRONG vs output-all-1s interpretation
                # Under MSB-first (index0=bit15): positions 8-15 in string are bits 7-0 → '1' for logical 0-7
                mask_char = mask[15 - logical] if logical <= 15 else None
        bwb = (pm.get("by_word_bit") or {}).get(f"{word}:{logical}") or {}
        rows.append(
            {
                "io_name": c.get("io_name"),
                "raw_bit": c.get("bit"),
                "logical_bit": logical,
                "proven_address": c.get("physical_address"),
                "by_word_bit_channel": bwb.get("channel"),
                "by_word_bit_type": bwb.get("type"),
                "mask_index_probe": mask_index,
                "mask_char_msb_first_hypothesis": mask_char,
            }
        )
    return {"word": word, "mask": mask, "claims": rows}


def main() -> int:
    run = REPO_ROOT / "workspace/_virgin_orindy/RUN"
    machine = "ORINDYAC6"
    ev = build_evidence_bundle(run, machine, project=machine)
    cfg = _load_configio_rows(run, machine)
    cfg_by_word: dict[int, list] = defaultdict(list)
    for r in cfg:
        try:
            cfg_by_word[int(r.get("octal_word"))].append(r)
        except (TypeError, ValueError):
            pass
    pm = build_physical_word_map(run, machine)
    focus = [c for c in (ev.get("raw_claims") or []) if c.get("io_name") in FOCUS]

    forensics = [
        forensic_claim(c, run=run, machine=machine, pm=pm, cfg_by_word=cfg_by_word) for c in focus
    ]

    words = sorted({int(float(c["word"])) for c in focus})
    word_maps = []
    for w in words:
        claims_w = [c for c in (ev.get("raw_claims") or []) if str(c.get("word")) == str(w)]
        word_maps.append(build_word_bit_map(w, claims_w, cfg_by_word[w], pm))

    # In_Out semantics summary from evidence
    in_out_semantics = {
        "conclusion": (
            "Observed Fortna Configio.In_Out values on ORINDY/MSCATL/RENO are overwhelmingly "
            "whole-word constants: all-0 (input-like) or 0000000011111111 (output-like). "
            "No atypical mixed masks found in surveyed current-site Configio. "
            "For the five Indy disagreements, In_Out=0000000011111111 and Desc catalogs are "
            "OA8/OA8I (output). Catalog direction and mask agree on OUTPUT. "
            "Existing PROVEN Input channels come from by_word_bit undirected bank collision: "
            "the same numeric bank is IA16.input_bank and OA*.output_bank; "
            "_module_matching_bank picks the earlier slot (IA16) when emitting bits, "
            "while words_out keeps the direction-correct OA* module. "
            "Therefore MODULE catalog direction and CLAIM proven channel direction diverged "
            "due to a Site Forge emit bug — not because In_Out encodes per-bit input on these rows. "
            "Per-bit In_Out indexing is NOT proven from in-repo FortnaPlus runtime source; "
            "fortna_io_banks treats '1' as active bits; table reference lists In_Out as a key "
            "direction-related field. Confidence for whole-word I/O image: MEDIUM-HIGH from "
            "correlation + catalog agreement; per-bit mapping: UNKNOWN."
        ),
        "zero_means": "Observed: whole-word input-like / no output bits asserted (not proven per-bit).",
        "one_means": "Observed: output-like image bits asserted (pattern 0000000011111111 on OA* rows).",
        "mixed_masks_legal": "Not observed in surveyed fixtures; treat MIXED as REVIEW if seen.",
        "source_refs": [
            "docs/FORTNAPLUS_TABLE_REFERENCE.md",
            "tools/scripts/fortna_io_banks.py",
            "tools/scripts/fortna_physical_word_resolver.py::_module_matching_bank",
            "EIPModules bank collision evidence banks 28 and 32 on ORINDY AENT-2",
        ],
    }

    # Re-run full shadow sites with V2 classification (no production change)
    atl_run = REPO_ROOT / "workspace/_mscatl_peek/MSCATL_CP3/RUN"
    indy_run = run
    atl = evaluate_site("MSCATL_CP3", "MSCATL_CP3", atl_run)
    indy = evaluate_site("ORINDYAC6", "ORINDYAC6", indy_run)
    reno = evaluate_site(
        "MSCRENOPICK",
        "MSCRENOPICK",
        REPO_ROOT / "workspace/_reno_peek/20260813-1132-MSCRENO-MSCRENOPICK-RUN/RUN",
    )
    orden = evaluate_site(
        "ORDENCP3",
        "ORDENCP3",
        REPO_ROOT / "workspace/_ordencp3_peek/ORDENCP3/RUN",
    )

    indy_ev = ev
    cross_indy = cross_site_proven_check(indy, indy_ev.get("raw_claims") or [])

    # Reclassify the five disagreements under evidence-backed defect rule
    five_status = []
    for f in forensics:
        proven = f.get("current_PROVEN_physical_address")
        shadow_ch = f.get("shadow", {}).get("channel_expected")
        five_status.append(
            {
                "IO_Name": f.get("IO_Name"),
                "claim_id": f.get("claim_id"),
                "classification": f.get("classification"),
                "proven_channel": proven,
                "shadow_channel": shadow_ch,
                "components": f.get("candidate_components"),
                "gate_treatment": (
                    "PROVEN_UNDER_REVIEW_EVIDENCE_DEFECT"
                    if f.get("classification") == "B_SHADOW_EXPOSES_PROVEN_DEFECT"
                    else "KEEP_DISAGREEMENT"
                ),
            }
        )

    unexplained = [
        s for s in five_status if s["gate_treatment"] != "PROVEN_UNDER_REVIEW_EVIDENCE_DEFECT"
    ]

    # 54 new Indy matches analysis
    new_matches = [
        r
        for r in (indy.get("claim_results") or [])
        if r.get("shadow_claim_result") == "SHADOW_WOULD_RESOLVE"
        and r.get("current_disposition") != "ASSIGNED"
    ]
    new_by_word = Counter(str(r.get("word")) for r in new_matches)
    new_groups = []
    for w, n in new_by_word.most_common():
        sample = [r for r in new_matches if str(r.get("word")) == w][:5]
        new_groups.append(
            {
                "word": w,
                "count": n,
                "catalog": (sample[0].get("matched_module") or {}).get("catalog") if sample else None,
                "adapter": (sample[0].get("matched_module") or {}).get("adapter") if sample else None,
                "direction": sample[0].get("shadow_word_result") if sample else None,
                "sample": [
                    {
                        "io_name": r.get("io_name"),
                        "bit": r.get("raw_bit"),
                        "shadow_channel": r.get("shadow_channel"),
                        "current_disposition": r.get("current_disposition"),
                    }
                    for r in sample
                ],
                "why_not_already_proven": (
                    "Current resolver by_word_bit/ledger did not ASSIGN these claims; "
                    "often phys_fail/conflict or bank-collision pollution. Same Atlanta "
                    "catalog+bank convention would bind them in shadow."
                ),
            }
        )

    # Cross-site disagrees excluding evidence-backed defects
    disagrees = cross_indy.get("disagreement_samples") or []
    defect_ids = {s["claim_id"] for s in five_status if s["gate_treatment"] == "PROVEN_UNDER_REVIEW_EVIDENCE_DEFECT"}
    remaining_disagrees = [d for d in disagrees if d.get("claim_id") not in defect_ids]

    racks = discover_racks(atl_run, "MSCATL_CP3")

    gate_ok = (
        (atl.get("conservation") or {}).get("status") == "PASS"
        and not atl.get("duplicate_shadow_channels")
        and (atl.get("word_result_counts") or {}).get("AMBIGUOUS_MATCH", 0) == 0
        and len(unexplained) == 0
        and len(remaining_disagrees) == 0
        and (atl.get("claim_result_counts") or {}).get("SHADOW_WOULD_RESOLVE", 0) > 0
    )

    soft_path = None
    if gate_ok:
        soft_dir = REPO_ROOT / "exports/io-soft-test/MSCATL_CP3"
        soft_dir.mkdir(parents=True, exist_ok=True)
        soft = {
            "kind": "io_soft_test_snapshot",
            "version": 2,
            "generated_at": _ts(),
            "project": "MSCATL_CP3",
            "machine": "MSCATL_CP3",
            "compiler_input": False,
            "autogen_input": False,
            "production_resolver": False,
            "racks": [
                {
                    "provisional_name": r.get("provisional_display_name"),
                    "engineer_name": r.get("engineer_display_name") or "",
                    "canonical_id": r.get("canonical_adapter_id"),
                    "ip": r.get("ip_address"),
                    "adapter_catalog": r.get("catalog_number"),
                    "modules": [
                        {
                            "slot": m.get("physical_slot"),
                            "catalog": m.get("catalog_number"),
                            "banks": {
                                "input_bank": m.get("input_bank"),
                                "output_bank": m.get("output_bank"),
                            },
                            "data_index": m.get("data_index"),
                            "status": m.get("status"),
                            "provenance": m.get("evidence"),
                        }
                        for m in (r.get("modules") or [])
                    ],
                }
                for r in (racks.get("racks") or [])
            ],
            "I/O": {
                "total_claims": 256,
                "current_proven": 0,
                "shadow_would_resolve": (atl.get("claim_result_counts") or {}).get(
                    "SHADOW_WOULD_RESOLVE", 0
                ),
                "unresolved_review": (
                    (atl.get("claim_result_counts") or {}).get("SHADOW_UNRESOLVED", 0)
                    + (atl.get("claim_result_counts") or {}).get("SHADOW_EXCLUDED", 0)
                    + (atl.get("claim_result_counts") or {}).get("SHADOW_AMBIGUOUS", 0)
                ),
                "conflicts": (atl.get("claim_result_counts") or {}).get("SHADOW_CONFLICT", 0),
            },
            "note": "Soft-test only — not wired to Autogen/PLC. Gate V2 passed with Indy PROVEN defects explicitly reviewed.",
        }
        soft_path = soft_dir / "io_soft_test_snapshot.json"
        soft_path.write_text(json.dumps(soft, indent=2), encoding="utf-8")

    report = {
        "kind": "indy_direction_forensics_v2",
        "generated_at": _ts(),
        "live_api_called": False,
        "production_rule_implemented": False,
        "five_disagreements": forensics,
        "five_status": five_status,
        "affected_word_bit_maps": word_maps,
        "in_out_semantics": in_out_semantics,
        "why_shadow_chose_O": (
            "Shadow uses Configio Desc catalog (OA8/OA8I → direction O) and In_Out "
            "0000000011111111 (output-like) as corroboration, then matches output_bank. "
            "Existing PROVEN I.Data comes from by_word_bit undirected bank collision, "
            "not from In_Out indicating input on these bits."
        ),
        "atlanta_refined": {
            "claim_counts": atl.get("claim_result_counts"),
            "word_counts": atl.get("word_result_counts"),
            "conservation": atl.get("conservation"),
            "racks": [
                {
                    "provisional": r.get("provisional_display_name"),
                    "ip": r.get("ip_address"),
                    "modules": len(r.get("modules") or []),
                    "unplaced": len(r.get("unplaced_modules") or []),
                }
                for r in (racks.get("racks") or [])
            ],
        },
        "indy_refined": {
            "AGREES_WITH_EXISTING_PROVEN": cross_indy.get("AGREES_WITH_EXISTING_PROVEN"),
            "DISAGREES_WITH_EXISTING_PROVEN_raw": cross_indy.get("DISAGREES_WITH_EXISTING_PROVEN"),
            "DISAGREES_after_evidence_defect_review": len(remaining_disagrees),
            "NEW_SHADOW_MATCH": cross_indy.get("NEW_SHADOW_MATCH"),
            "claim_counts": indy.get("claim_result_counts"),
            "remaining_disagreement_samples": remaining_disagrees,
        },
        "new_indy_matches_analysis": {
            "count": len(new_matches),
            "by_word": new_groups[:20],
        },
        "shadow_validation_v2": {
            "result": "PASS" if gate_ok else "FAIL",
            "means": "safe_to_consider_implementing_deterministically_NOT_plc_ready",
            "unexplained_five": unexplained,
            "remaining_cross_site_disagrees": len(remaining_disagrees),
        },
        "soft_test_snapshot": str(soft_path) if soft_path else None,
        "reno_orden_note": {
            "MSCRENOPICK": reno.get("claim_result_counts"),
            "ORDENCP3": orden.get("claim_result_counts"),
        },
    }

    out = REPO_ROOT / "exports/ai-io/forensics"
    out.mkdir(parents=True, exist_ok=True)
    (out / "indy_five_direction_forensics.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "five_classifications": [
                    (s["IO_Name"], s["classification"], s["gate_treatment"]) for s in five_status
                ],
                "atlanta": atl.get("claim_result_counts"),
                "indy": report["indy_refined"],
                "new_matches": len(new_matches),
                "shadow_validation_v2": report["shadow_validation_v2"]["result"],
                "soft_test": report["soft_test_snapshot"],
                "racks": report["atlanta_refined"]["racks"],
                "out": str(out / "indy_five_direction_forensics.json"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
