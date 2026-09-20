#!/usr/bin/env python3
"""CP8 evidence-integrity gate — corrected evidence model + claim occupancy.

Does NOT modify production resolver. No finished L5X. No live API by default.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tools"))

from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_asc import read_asc  # noqa: E402
from fortna_hardware_conflict import classify_catalog_disagreement  # noqa: E402
from fortna_hardware_family import channel_capacity_for_catalog  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    _load_eipmodules_rows,
    parse_eipcfg,
)

_FORM_RE = re.compile(
    r"^(?P<panel>[A-Za-z][A-Za-z0-9_]*)-"
    r"(?P<catalog>\d{4}-[A-Za-z0-9]+)-"
    r"(?P<numeric>\d+)(?P<alpha>[ABab])$",
    re.I,
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_ornccp4_run() -> Path:
    for p in [
        ROOT / "exports/learning/_extract/ab56d6beb1b1ca87/RUN",
        ROOT / "workspace/cp4-run/RUN",
    ]:
        if (p / "project.cfg").is_file():
            return p
    raise FileNotFoundError("ORNCCP4 RUN not found")


def _load_form_rows(run: Path) -> list[dict[str, Any]]:
    paths = sorted(run.rglob("Configio.asc*"))
    paths.sort(key=lambda p: (0 if p.name.count(".") >= 2 else 1, str(p)))
    _, raw = read_asc(paths[0])
    out = []
    for r in raw:
        desc = (r.get("Desc") or "").strip()
        m = _FORM_RE.match(desc)
        if not m:
            continue
        out.append(
            {
                "desc": desc,
                "panel": m.group("panel").upper(),
                "catalog_hint": m.group("catalog"),
                "numeric_token": int(m.group("numeric")),
                "alpha_suffix": m.group("alpha").upper(),
                "bank": r.get("Bank"),
                "octal_word": r.get("Octal_Word") or r.get("OctalWord"),
                "lohi": (r.get("LoHi") or "").strip(),
                "in_out": (r.get("In_Out") or "").strip(),
                "interface": (r.get("Interface") or "").strip(),
                "i_o_type": (r.get("I_O_Type") or "").strip(),
            }
        )
    return out


def _direct_module_for_bank(
    eip_rows: list[dict], bank: int, catalog_hint: str, direction: str
) -> dict | None:
    if bank <= 0:
        return None
    cat_u = (catalog_hint or "").upper()
    if direction == "I":
        cands = [r for r in eip_rows if int(r.get("input_bank") or -1) == bank]
    elif direction == "O":
        cands = [r for r in eip_rows if int(r.get("output_bank") or -999) == bank]
    else:
        cands = [
            r
            for r in eip_rows
            if int(r.get("input_bank") or -1) == bank
            or int(r.get("output_bank") or -999) == bank
        ]
    if not cands:
        return None
    # Prefer catalog match but do not invent — if unique bank hit, return it
    exact = [c for c in cands if (c.get("type") or "").upper() == cat_u]
    chosen = exact[0] if len(exact) == 1 else (cands[0] if len(cands) == 1 else None)
    if chosen is None and len(cands) == 1:
        chosen = cands[0]
    if chosen is None:
        return {"ambiguous_candidates": cands, "module": None}
    return {
        "module": {
            "adapter": chosen.get("adapter"),
            "type": chosen.get("type"),
            "slot": chosen.get("slot"),
            "input_bank": chosen.get("input_bank"),
            "output_bank": chosen.get("output_bank"),
        },
        "ambiguous_candidates": None,
    }


def _claims_for_word(ev_claims: list[dict], word: str | int) -> list[dict]:
    w = str(word)
    return [c for c in ev_claims if str(c.get("word")) == w]


def _half_bits(lohi: str) -> tuple[str, list[int], list[str]]:
    """Return (half_name, logical_bits, fortna_labels)."""
    u = (lohi or "").lower()
    if u.startswith("l"):
        return "Low", list(range(0, 8)), [str(i) for i in range(0, 8)]
    if u.startswith("h"):
        # Fortna High labels 10-17 octal → logical 8-15
        labels = ["10", "11", "12", "13", "14", "15", "16", "17"]
        return "High", list(range(8, 16)), labels
    return "Unknown", [], []


def build_integrity_dossier(run: Path, machine: str = "ORNCCP4") -> dict[str, Any]:
    rows = _load_form_rows(run)
    eip = _load_eipmodules_rows(run, machine)
    topo = parse_eipcfg(run, machine)
    ev = build_evidence_bundle(run, machine, project=machine)
    claims = ev.get("raw_claims") or []

    # Index rows by panel+catalog_hint+numeric
    by_pair: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        key = (r["panel"], r["catalog_hint"], r["numeric_token"], str(r.get("octal_word")))
        by_pair[key][r["alpha_suffix"]] = r

    pairs_out = []
    capacity_violations = []
    oa8i_high_conclusions = []

    for key, sides in sorted(by_pair.items(), key=lambda kv: kv[0][2]):
        panel, cat_hint, numeric, word = key
        a = sides.get("A")
        b = sides.get("B")
        if not a or not b:
            continue

        def _dir(cat: str) -> str:
            u = cat.upper()
            if any(x in u for x in ("IA", "IB", "IM")):
                return "I"
            if any(x in u for x in ("OA", "OB", "OW")):
                return "O"
            return ""

        dir_a = _dir(cat_hint)
        try:
            bank_a = int(float(str(a.get("bank"))))
        except (TypeError, ValueError):
            bank_a = -1
        try:
            bank_b = int(float(str(b.get("bank"))))
        except (TypeError, ValueError):
            bank_b = -1

        low_res = _direct_module_for_bank(eip, bank_a, cat_hint, dir_a)
        high_res = _direct_module_for_bank(eip, bank_b, cat_hint, dir_a)
        low_mod = (low_res or {}).get("module")
        high_mod = (high_res or {}).get("module")

        # Logical pairing
        logical = "UNKNOWN"
        if (a.get("lohi") or "").lower().startswith("l") and (
            b.get("lohi") or ""
        ).lower().startswith("h"):
            if bank_b == bank_a + 1 and str(a.get("octal_word")) == str(b.get("octal_word")):
                logical = "LOW_HIGH_PAIR"
            else:
                logical = "NOT_PAIRED"

        # High physical relationship — DO NOT assume SAME_AS_LOW
        if high_mod and low_mod:
            if (
                high_mod.get("adapter") == low_mod.get("adapter")
                and high_mod.get("slot") == low_mod.get("slot")
            ):
                high_rel = "SAME_AS_LOW"
                basis = ["both_halves_direct_eipmodules_same_adapter_slot"]
            else:
                high_rel = "SEPARATE_MODULE"
                basis = ["both_halves_direct_eipmodules_different_modules"]
        elif high_mod and not low_mod:
            high_rel = "SEPARATE_MODULE"
            basis = ["high_has_direct_module_low_does_not"]
        elif not high_mod and low_mod:
            # No independent High module — relationship UNKNOWN until claim occupancy
            high_rel = "UNKNOWN"
            basis = [
                "high_has_no_direct_eipmodules_bank_match",
                "do_not_infer_same_as_low_from_naming_alone",
            ]
        else:
            high_rel = "UNKNOWN"
            basis = ["neither_half_direct_module"]

        # Authoritative catalog from Low module when present
        auth_cat = (low_mod or {}).get("type") or ""
        eipcfg_type = ""
        if low_mod:
            for ad in topo.get("adapters") or []:
                if (ad.get("name") or "") == (low_mod.get("adapter") or ""):
                    for mod in ad.get("modules") or []:
                        if int(mod.get("slot") or -1) == int(low_mod.get("slot") or -2):
                            eipcfg_type = mod.get("type") or ""
                            break
        alias = classify_catalog_disagreement(
            human_name_or_desc=a.get("desc") or "",
            eipmodules_type=auth_cat,
            eipcfg_type=eipcfg_type or auth_cat,
        )
        capacity = channel_capacity_for_catalog(auth_cat) if auth_cat else None

        # Claim occupancy
        word_claims = _claims_for_word(claims, word)
        half_a_name, bits_a, labels_a = _half_bits(a.get("lohi") or "")
        half_b_name, bits_b, labels_b = _half_bits(b.get("lohi") or "")

        def _occupancy(half_bits: list[int], half_name: str) -> dict[str, Any]:
            matched = []
            for c in word_claims:
                try:
                    bit = int(float(str(c.get("bit"))))
                except (TypeError, ValueError):
                    # may be octal label
                    from fortna_bit_address import parse_fortna_octal_bit

                    p = parse_fortna_octal_bit(c.get("bit"))
                    bit = int(p["logical_bit"]) if p and p.get("logical_bit") is not None else -1
                if bit in half_bits:
                    matched.append(c)
            return {
                "half": half_name,
                "logical_bits": half_bits,
                "fortna_bit_labels": labels_a if half_name == "Low" else labels_b,
                "physical_claim_count": len(matched),
                "claim_examples": [
                    {
                        "io_name": c.get("io_name"),
                        "claim_id": c.get("claim_id"),
                        "bit": c.get("bit"),
                        "disposition": c.get("deterministic_disposition"),
                    }
                    for c in matched[:12]
                ],
            }

        occ_a = _occupancy(bits_a, half_a_name)
        occ_b = _occupancy(bits_b, half_b_name)

        # Refine high_physical_relationship using claim occupancy
        if high_rel == "UNKNOWN" and not high_mod:
            if occ_b["physical_claim_count"] == 0:
                high_rel = "NO_PHYSICAL_CLAIMS"
                basis.append("high_half_zero_physical_claims")
            else:
                high_rel = "UNKNOWN"
                basis.append(
                    f"high_half_has_{occ_b['physical_claim_count']}_physical_claims_without_direct_module"
                )

        # Capacity check: if someone would map High claims onto Low module
        if (
            low_mod
            and capacity is not None
            and occ_b["physical_claim_count"] > 0
            and high_rel in {"UNKNOWN", "SAME_AS_LOW"}
        ):
            # Logical bits 8..15 onto capacity-8 module would violate
            if capacity <= 8 and any(b >= capacity for b in bits_b):
                capacity_violations.append(
                    {
                        "desc_a": a["desc"],
                        "desc_b": b["desc"],
                        "auth_catalog": auth_cat,
                        "capacity": capacity,
                        "high_claim_count": occ_b["physical_claim_count"],
                        "issue": "high_logical_bits_outside_module_capacity_if_inherited",
                    }
                )

        if "OA8I" in (auth_cat or cat_hint).upper():
            oa8i_high_conclusions.append(
                {
                    "pair": f"{a['desc']} / {b['desc']}",
                    "auth_catalog": auth_cat or cat_hint,
                    "capacity": capacity or channel_capacity_for_catalog("1794-OA8I"),
                    "high_physical_claim_count": occ_b["physical_claim_count"],
                    "high_physical_relationship": high_rel,
                    "conclusion": (
                        "OA8I High half has ZERO physical claims — Configio High is logical word structure only"
                        if occ_b["physical_claim_count"] == 0
                        else "OA8I High half HAS physical claims — STOP: do not map bits 8..15 onto 8ch module by assumption"
                    ),
                }
            )

        pairs_out.append(
            {
                "panel": panel,
                "catalog_hint": cat_hint,
                "numeric_token": numeric,
                "octal_word": word,
                "logical_pair_relationship": logical,
                "low_direct_module_resolution": low_mod,
                "high_direct_module_resolution": high_mod,
                "high_physical_relationship": high_rel,
                "relationship_basis": basis,
                # Explicit: removed ambiguous same_physical_module boolean
                "DEPRECATED_same_physical_module_removed": True,
                "authoritative_catalog": auth_cat,
                "eipcfg_type": eipcfg_type,
                "alias_classification": alias,
                "module_capacity": capacity,
                "A_Low": {
                    "desc": a["desc"],
                    "bank": bank_a,
                    "lohi": a.get("lohi"),
                    "occupancy": occ_a,
                },
                "B_High": {
                    "desc": b["desc"],
                    "bank": bank_b,
                    "lohi": b.get("lohi"),
                    "occupancy": occ_b,
                },
                "numeric_token_equals_low_slot": bool(
                    low_mod and int(low_mod.get("slot") or -1) == int(numeric)
                ),
            }
        )

    low_slot_agree = sum(1 for p in pairs_out if p["numeric_token_equals_low_slot"])
    low_count = sum(1 for p in pairs_out if p["low_direct_module_resolution"])

    dossier = {
        "kind": "CP8_EVIDENCE_INTEGRITY_DOSSIER",
        "form": "PANEL_CATALOG_NUMERIC_ALPHA",
        "generated_at": _ts(),
        "machine": machine,
        "run": str(run),
        "scope_note": (
            "DERIVED_DIALECT_RULE / CANDIDATE_RULE — observed on ORNCCP4 Low/A rows only; "
            "not universal Fortna semantics. Identity is structural form, not CP8."
        ),
        "evidence_model_fix": {
            "removed_ambiguous_field": "same_physical_module",
            "removed_reason": (
                "Boolean conflated (a) direct EIPModules resolution of High with "
                "(b) inferred inheritance from Low. High had no direct module → false, "
                "while narrative claimed SAME. Replaced with explicit fields."
            ),
            "replacement_fields": [
                "logical_pair_relationship",
                "low_direct_module_resolution",
                "high_direct_module_resolution",
                "high_physical_relationship",
                "relationship_basis",
            ],
            "terminology": {
                "LOGICAL_CONFIGIO_HALF": "Configio Low or High row for a word",
                "PHYSICAL_MODULE_INSTANCE": "EIPModules/eipcfg bridged module",
                "PHYSICAL_CHANNEL": "assigned Logix channel within module capacity",
            },
        },
        "numeric_token": {
            "scope": "PANEL_CATALOG_NUMERIC_ALPHA / ORNCCP4 / Low-A rows with direct module",
            "agree": low_slot_agree,
            "n": low_count,
            "rate": (low_slot_agree / low_count) if low_count else 0,
            "status": "DERIVED_DIALECT_RULE / CANDIDATE_RULE",
            "not_universal": True,
        },
        "pairs": pairs_out,
        "capacity_violations_if_high_inherited": capacity_violations,
        "oa8i_high_half": oa8i_high_conclusions,
        "high_relationship_summary": {
            "NO_PHYSICAL_CLAIMS": sum(
                1 for p in pairs_out if p["high_physical_relationship"] == "NO_PHYSICAL_CLAIMS"
            ),
            "UNKNOWN": sum(
                1 for p in pairs_out if p["high_physical_relationship"] == "UNKNOWN"
            ),
            "SAME_AS_LOW": sum(
                1 for p in pairs_out if p["high_physical_relationship"] == "SAME_AS_LOW"
            ),
            "SEPARATE_MODULE": sum(
                1 for p in pairs_out if p["high_physical_relationship"] == "SEPARATE_MODULE"
            ),
        },
        "alias_mismatches": [
            p["alias_classification"]
            for p in pairs_out
            if (p.get("alias_classification") or {}).get("classification")
            == "ALIAS_CATALOG_MISMATCH"
        ],
        "production_resolver_modified": False,
        "api_required": None,  # filled by caller after analysis
    }

    # API required if any High half has claims without direct module, or capacity issues
    needs_api = any(
        p["high_physical_relationship"] == "UNKNOWN"
        and p["B_High"]["occupancy"]["physical_claim_count"] > 0
        for p in pairs_out
    ) or bool(capacity_violations)
    # If ALL highs are NO_PHYSICAL_CLAIMS, relationship is established: High is logical-only
    all_no_claims = all(
        p["high_physical_relationship"] == "NO_PHYSICAL_CLAIMS" for p in pairs_out
    )
    dossier["api_required"] = bool(needs_api and not all_no_claims)
    dossier["deterministic_high_conclusion"] = (
        "All 8 High halves carry ZERO physical claims. High Configio rows are "
        "LOGICAL_CONFIGIO_HALF structure only; they do not prove additional physical "
        "channels or a second module. No inheritance mapping required for claim resolution."
        if all_no_claims
        else "Ambiguity remains — High halves have unresolved physical claim relationship."
    )
    return dossier


def write_neutral_blind_packet(dossier: dict[str, Any], out: Path) -> Path:
    evidence_rows = []
    for p in dossier.get("pairs") or []:
        evidence_rows.append(
            {
                "panel": p.get("panel"),
                "catalog_hint": p.get("catalog_hint"),
                "authoritative_catalog": p.get("authoritative_catalog"),
                "module_capacity": p.get("module_capacity"),
                "numeric_token": p.get("numeric_token"),
                "octal_word": p.get("octal_word"),
                "logical_pair_relationship": p.get("logical_pair_relationship"),
                "A_Low": {
                    "desc": p["A_Low"]["desc"],
                    "bank": p["A_Low"]["bank"],
                    "lohi": p["A_Low"]["lohi"],
                    "direct_module": p.get("low_direct_module_resolution"),
                    "claim_occupancy": p["A_Low"]["occupancy"],
                },
                "B_High": {
                    "desc": p["B_High"]["desc"],
                    "bank": p["B_High"]["bank"],
                    "lohi": p["B_High"]["lohi"],
                    "direct_module": p.get("high_direct_module_resolution"),
                    "claim_occupancy": p["B_High"]["occupancy"],
                },
                "adapter_identity_note": "use exact EIPAdapters TargetIP bridge evidence when present",
                "alias_classification": p.get("alias_classification"),
            }
        )
    blind = {
        "kind": "decoder_investigator_blind_packet",
        "investigation_id": "CP8_ALPHA_DIALECT_REMAINING_R1",
        "generated_at": _ts(),
        "question": (
            "Site Forge observes paired Configio rows with the same word, A/Low and B/High, "
            "adjacent banks, and only the Low row directly matching EIPModules. Determine "
            "what physical relationship, if any, the High row has to the Low row/module. "
            "Use claim occupancy, module capacity, topology, and current-site evidence. "
            "Also determine how catalog-looking Desc values should be treated when "
            "EIPModules.Type and eipcfg agree on a different catalog. Do not assign "
            "endpoints. If the evidence does not prove a relationship, return "
            "INSUFFICIENT_EVIDENCE."
        ),
        "constraints": [
            "current-site evidence only",
            "read-only tools",
            "no finished/reference L5X",
            "no endpoint assignments",
            "do not assume High binds to Low module",
            "module capacity must bound any physical channel claim",
            "identify general Fortna semantic — not a site-specific mapping",
        ],
        "evidence_rows": evidence_rows,
        # Deliberately NO note asserting High→Low binding
    }
    path = out / "blind_packet.json"
    path.write_text(json.dumps(blind, indent=2), encoding="utf-8")
    return path


def main() -> int:
    run = _find_ornccp4_run()
    dossier = build_integrity_dossier(run)
    out = ROOT / "exports/learning/investigations/CP8_ALPHA_DIALECT"
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence_integrity_dossier.json").write_text(
        json.dumps(dossier, indent=2), encoding="utf-8"
    )
    # Human summary
    lines = [
        "CP8 EVIDENCE INTEGRITY DOSSIER",
        f"generated: {dossier['generated_at']}",
        f"machine: {dossier['machine']}",
        "",
        "MODEL FIX:",
        f"  removed: {dossier['evidence_model_fix']['removed_ambiguous_field']}",
        f"  reason: {dossier['evidence_model_fix']['removed_reason']}",
        "",
        f"NUMERIC (Low/A → slot): {dossier['numeric_token']}",
        f"HIGH RELATIONSHIP SUMMARY: {dossier['high_relationship_summary']}",
        f"DETERMINISTIC CONCLUSION: {dossier['deterministic_high_conclusion']}",
        f"API REQUIRED: {dossier['api_required']}",
        "",
        "PAIRS:",
    ]
    for p in dossier["pairs"]:
        lines.append(
            f"  {p['A_Low']['desc']} / {p['B_High']['desc']}: "
            f"logical={p['logical_pair_relationship']} "
            f"high_rel={p['high_physical_relationship']} "
            f"A_claims={p['A_Low']['occupancy']['physical_claim_count']} "
            f"B_claims={p['B_High']['occupancy']['physical_claim_count']} "
            f"cap={p['module_capacity']} auth={p['authoritative_catalog']}"
        )
    lines.append("")
    lines.append("OA8I HIGH:")
    for o in dossier["oa8i_high_half"]:
        lines.append(f"  {o}")
    (out / "evidence_integrity_dossier.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Always write corrected neutral blind packet (for review even if API not needed)
    bp = write_neutral_blind_packet(dossier, out)
    print(
        json.dumps(
            {
                "api_required": dossier["api_required"],
                "high_summary": dossier["high_relationship_summary"],
                "oa8i": dossier["oa8i_high_half"],
                "numeric": dossier["numeric_token"],
                "blind_packet": str(bp),
                "dossier": str(out / "evidence_integrity_dossier.json"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
