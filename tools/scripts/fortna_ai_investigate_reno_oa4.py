#!/usr/bin/env python3
"""Offline Reno investigation: OA4 Low-half bits 4–7 anomaly → DecoderRuleCandidate.

Does NOT call OpenAI. Does NOT assign endpoints. Does NOT create READY.
Produces a DecoderRuleCandidate for Anton / Site Forge review.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_ai_decoder_schema import validate_decoder_rule_candidate  # noqa: E402
from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_ai_readonly_tools import SiteForgeReadOnlyContext  # noqa: E402
from fortna_hardware_family import channel_capacity_for_catalog  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    parse_fortna_octal_bit,
)


def investigate_reno_oa4_low_overflow(
    run_dir: Path | str | None = None,
    machine: str = "MSCRENOPICK",
) -> dict[str, Any]:
    run_dir = Path(
        run_dir
        or (
            REPO_ROOT
            / "workspace"
            / "_reno_peek"
            / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
            / "RUN"
        )
    )
    ctx = SiteForgeReadOnlyContext(run_dir=run_dir, machine=machine, project="MSCRENOPICK")
    evidence = ctx.evidence
    resolver = PhysicalWordResolver(run_dir, machine)

    # Focus claims: word 1011 bits 4 and 5 (the unexplained prior AI remaps)
    focus = [
        c
        for c in (evidence.get("raw_claims") or [])
        if str(c.get("word")) == "1011" and str(c.get("bit")) in {"4", "5"}
    ]
    focus_ids = [c["claim_id"] for c in focus]

    # Configio halves for 1011
    cfg = []
    for r in evidence.get("configio") or []:
        try:
            if int(r.get("Octal_Word")) == 1011:
                cfg.append(r)
        except (TypeError, ValueError):
            continue

    # Neighbours on same word
    neighbours = [
        c
        for c in (evidence.get("raw_claims") or [])
        if str(c.get("word")) == "1011"
    ]
    proven_same_word = [
        c for c in neighbours if c.get("deterministic_disposition") == "ASSIGNED"
    ]
    failed_same_word = [
        c
        for c in neighbours
        if c.get("deterministic_disposition") == "physical_resolution_failure"
    ]

    # Resolver map coverage for 1011
    mapped_bits = {}
    for b in list(range(0, 18)):
        hit = resolver.resolve(1011, b)
        if hit and hit.get("channel"):
            mapped_bits[b] = hit.get("channel")

    # Capacity of Low/High modules from proven channels
    low_cap = channel_capacity_for_catalog("1734-OA4")
    observed_facts = [
        "Configio word 1011 Low → Bank 8; High → Bank 9; Interface=RTA1; In_Out=0000000011111111",
        "AENTR3 POINT rack: consecutive 1734-OA4 modules at Data[9] (bank 8) and Data[10] (bank 9)",
        f"1734-OA4 channel capacity = {low_cap} (bits 0..{low_cap - 1} only)",
        "Site Forge parse_fortna_octal_bit: bits 0-7 → Low half module_bit=raw; bits 10-17/8-15 → High half",
        "by_word_bit emits 1011:0-3 → AENTR3:O.Data[9].0-3 and 1011:8-11/10-13 → AENTR3:O.Data[10].0-3",
        "by_word_bit does NOT emit 1011:4 or 1011:5 — hence physical_resolution_failure",
        "Proven Low neighbours: EZSSV3/4/5/9 bits 0-3 → Data[9].0-3",
        "Proven High neighbours: EZSSV10/11 bits 10/11 → Data[10].0/1; CL17 bit12 → Data[10].2; M70 bit13 → Data[10].3",
        "Prior AI proposal mapped bit5→Data[10].1 and bit4→Data[10].0 — those channels are ALREADY owned by EZSSV11/EZSSV10",
        "Word 1010 (same OA4 pair pattern) has proven bits 0-3 and 10-13 only — no claims on bits 4-7",
    ]

    evidence_refs = [
        {"source": "Configio.asc", "ref": "row:22", "fact": "Octal_Word=1011 Bank=8 LoHi=Low In_Out=0000000011111111 Interface=RTA1"},
        {"source": "Configio.asc", "ref": "row:23", "fact": "Octal_Word=1011 Bank=9 LoHi=High In_Out=0000000011111111 Interface=RTA1"},
        {"source": "eipcfg", "ref": "AENTR3.slot9", "fact": "1734-OA4 data_index=9 direction=O"},
        {"source": "eipcfg", "ref": "AENTR3.slot10", "fact": "1734-OA4 data_index=10 direction=O"},
        {"source": "fortna_physical_word_resolver.py", "ref": "parse_fortna_octal_bit", "fact": "Low raw 0-7 → module_bit=raw; High 8+/10-17 → module_bit within half"},
        {"source": "HardwareIOModel", "ref": "AENTR3 proven", "fact": "EZSSV10→Data[10].0 EZSSV11→Data[10].1 already ASSIGNED"},
    ]

    supporting = [
        {
            "claim_id": c.get("claim_id"),
            "summary": f"{c.get('io_name')} word={c.get('word')} bit={c.get('bit')} → {c.get('physical_address')}",
            "evidence": "ASSIGNED neighbour demonstrating OA4 Low(0-3)/High(10-13) packing",
        }
        for c in proven_same_word
    ]
    supporting.append(
        {
            "summary": "Word 1010 M4/M15/M16/M17 bits 0-3 and M18/M56/M71/M72 bits 10-13 follow same OA4 pair packing",
            "evidence": "ASSIGNED claims on adjacent Configio output word with banks 6/7",
        }
    )

    counterexamples = [
        {
            "summary": "Hypothesis 'Fortna bit 4/5 remaps to High module bit 0/1' (prior AI endpoint proposal)",
            "why_contradicts": (
                "Would assign AENTR3:O.Data[10].0 and .1 which are already ASSIGNED to "
                "EZSSV10 (bit 10) and EZSSV11 (bit 11). Silent steal — not a valid decode."
            ),
        },
        {
            "summary": "Hypothesis 'Low half bits 4-7 overflow onto next OA4 with module_bit=fortna_bit-4'",
            "why_contradicts": (
                "Next OA4 (Data[10]) is already the Configio High-half target for banks 9 / bits 10-13. "
                "Overflow remapping collides with High-half packing already proven on this word."
            ),
        },
    ]

    candidate = {
        "investigation_id": "inv_reno_oa4_low_bit_overflow_1011",
        "subsystem": "physical_io_word_bit_decode",
        "failure_pattern": (
            "POINT_OA4_LOW_HALF_BIT_OVERFLOW: Conveyor claims use Fortna Low-half bits 4-7 "
            "against a Configio Low bank bound to a 4-channel 1734-OA4/IA4 module"
        ),
        "affected_claim_ids": focus_ids,
        "affected_count": len(focus_ids),
        "observed_facts": observed_facts,
        "evidence_refs": evidence_refs,
        "candidate_rule_name": "point_4ch_half_bit_domain",
        "candidate_rule_description": (
            "When a Configio Low/High bank pair maps to consecutive 4-channel POINT modules "
            "(1734-OA4 / 1734-IA4), valid Conveyor IO_Address_Bit values for that Fortna word are "
            "restricted to: Low half decimal bits 0-3; High half octal-style 10-13 (or decimal 8-11). "
            "Bits 4-7 on such words are OUT OF DOMAIN for the Low OA4 and are NOT an alternate "
            "encoding for the High module. They must surface as physical_resolution_failure / "
            "REVIEW_REQUIRED (engineer encoding check), not silent remapping onto High-half channels."
        ),
        "proposed_inputs": [
            "Configio.Octal_Word",
            "Configio.Bank (Low/High)",
            "Configio.LoHi",
            "Configio.In_Out",
            "Configio.Interface",
            "module catalog capacity (channel_capacity_for_catalog)",
            "Conveyor.IO_Address_Bit",
            "parse_fortna_octal_bit half + module_bit",
        ],
        "proposed_transformation": (
            "IF half==Low AND module_capacity==4 AND fortna_raw_bit>=4 AND fortna_raw_bit<=7: "
            "DO NOT remap; emit resolution_failure reason=low_half_bit_exceeds_module_capacity; "
            "flag REVIEW_REQUIRED for Conveyor bit encoding. "
            "ELSE keep existing Low(0..cap-1) / High(8+/10+) packing."
        ),
        "expected_outputs": [
            "physical_resolution_failure with explicit reason for bits 4-7 on 4ch Low halves",
            "no channel collision with proven High-half ASSIGNED owners",
            "unchanged decode for bits 0-3 and 10-13 on same word",
        ],
        "supporting_examples": supporting,
        "counterexamples": counterexamples,
        "ambiguities": [
            "Whether Conveyor bits 4/5 were mistyped and intended as High-half 14/15 or 12/13 — requires engineer/table judgment",
            "Whether any Fortna site legitimately uses decimal 4-7 as a second Low nibble when High bank is unused — not evidenced on MSCRENOPICK word 1011 (High bank IS used)",
        ],
        "additional_evidence_needed": [
            "Confirm with Fortna Configio/IOCard documentation whether 4-channel cards ever accept Low bits 4-7",
            "Scan other POINT sites for Conveyor bits 4-7 on words whose Low bank is OA4/IA4 with an active High bank",
            "If mistype suspected: compare print/OCR or alternate Conveyor shadow for EZSSV15/EZSSV18 intended bits",
        ],
        "tests_required": [
            "MSCRENOPICK word 1011 bits 0-3 and 10-13 remain ASSIGNED unchanged",
            "bits 4 and 5 remain unresolved with reason low_half_bit_exceeds_module_capacity (not remapped)",
            "Any candidate remap to Data[10].0/.1 must FAIL regression against EZSSV10/EZSSV11 owners",
            "Word 1010 bits 0-3/10-13 packing regression",
            "Cross-site: no site-name special case; rule keyed by catalog capacity + Configio halves",
        ],
        "scope": (
            "1734 POINT family; Configio RTA Interface; Low/High bank pair bound to 4-channel "
            "OA4/IA4 modules; Conveyor bit domain validation. Not a FLEX 1794-IA16/OA16 rule."
        ),
        "confidence": "HIGH",
        "status": "REVIEW_REQUIRED",
    }

    validation = validate_decoder_rule_candidate(candidate)
    return {
        "ok": True,
        "live_api_called": False,
        "compiler_authority": False,
        "creates_ready": False,
        "endpoint_assignments_emitted": False,
        "mapped_bits_1011": mapped_bits,
        "focus_claims": [
            {
                "claim_id": c.get("claim_id"),
                "io_name": c.get("io_name"),
                "word": c.get("word"),
                "bit": c.get("bit"),
                "disposition": c.get("deterministic_disposition"),
                "parse_fortna_octal_bit": parse_fortna_octal_bit(c.get("bit")),
            }
            for c in focus
        ],
        "failed_same_word_count": len(failed_same_word),
        "proven_same_word_count": len(proven_same_word),
        "candidate": candidate,
        "schema_validation": validation,
        "engineering_judgment_required": [
            "Decide if EZSSV15/EZSSV18 Conveyor bits are data-entry errors vs true Fortna variant",
            "Do not accept prior AI endpoint proposals — they collide with proven High-half owners",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Offline Reno OA4 bit-overflow investigation")
    ap.add_argument("--run-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    result = investigate_reno_oa4_low_overflow(args.run_dir)
    out = args.out or (
        REPO_ROOT / "exports" / "ai-io" / "investigations" / "reno_oa4_low_overflow.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "out": str(out),
                "status": result["candidate"]["status"],
                "rule": result["candidate"]["candidate_rule_name"],
                "schema_ok": result["schema_validation"]["ok"],
                "live_api_called": False,
                "endpoint_assignments_emitted": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
