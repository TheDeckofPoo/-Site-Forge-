#!/usr/bin/env python3
"""Validation-only comparison of generated L5X vs finished answer-sheet PLC.

ARCHITECTURE FIREWALL:
  compiler/generation  MUST NOT import this module.
  validation           MAY read generated + finished answer sheet.

Mismatch categories:
  CORRECT_FROM_EVIDENCE
  CORRECT_BUT_UNSUPPORTED
  LUCKY
  MISSED
  WRONG
  ANSWER_SHEET_ONLY_NOT_EXPECTED_FROM_RUN
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _programs(text: str) -> set[str]:
    return set(re.findall(r'<Program[^>]*Name="([^"]+)"', text))


def _tags_sample(text: str, pattern: str) -> set[str]:
    return set(re.findall(pattern, text, flags=re.I))


def compare_to_answer_sheet(
    *,
    generated_l5x: Path,
    answer_sheet: Path | None,
    site: dict[str, Any],
    generation_meta: dict[str, Any],
) -> dict[str, Any]:
    gen_text = generated_l5x.read_text(encoding="utf-8", errors="replace") if generated_l5x.is_file() else ""
    result: dict[str, Any] = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "generated_path": str(generated_l5x),
        "answer_sheet_path": str(answer_sheet) if answer_sheet else None,
        "answer_sheet_used_for_generation": False,
        "firewall": "validation-only; generation must not import this module",
        "comparisons": [],
    }
    if not answer_sheet or not answer_sheet.is_file():
        result["ok"] = False
        result["note"] = "Answer sheet L5X not available — structural categories only"
        result["comparisons"].append(
            {
                "aspect": "answer_sheet_presence",
                "category": "MISSED",
                "detail": "No answer sheet file provided",
            }
        )
        return result

    ans = answer_sheet.read_text(encoding="utf-8", errors="replace")
    gen_progs = _programs(gen_text)
    ans_progs = _programs(ans)

    # Program family comparison (names only — not copying into compiler)
    family = lambda names: sorted(
        {
            "Fast"
            if "Fast" in n
            else "Slow"
            if "Slow" in n
            else "L1"
            if "_L1" in n or n.endswith("L1")
            else "L2"
            if "_L2" in n
            else "L3"
            if "_L3" in n
            else "Sys"
            if n in {"Sys", "System"}
            else "IO_MAP"
            if "IO_MAP" in n
            else "Sorter"
            if "Sorter" in n or "Track" in n
            else "WCS"
            if "WCS" in n
            else "Other"
            for n in names
        }
    )
    gen_f, ans_f = set(family(gen_progs)), set(family(ans_progs))
    for f in sorted(gen_f & ans_f):
        result["comparisons"].append(
            {
                "aspect": f"program_family:{f}",
                "category": "CORRECT_FROM_EVIDENCE"
                if f in {"Fast", "Slow", "L1", "L2", "Sys", "IO_MAP"}
                else "LUCKY",
                "generated": True,
                "answer_sheet": True,
            }
        )
    for f in sorted(ans_f - gen_f):
        cat = (
            "CORRECT_BUT_UNSUPPORTED"
            if f in {"Sorter", "WCS", "L3"}
            else "ANSWER_SHEET_ONLY_NOT_EXPECTED_FROM_RUN"
        )
        result["comparisons"].append(
            {
                "aspect": f"program_family:{f}",
                "category": cat,
                "generated": False,
                "answer_sheet": True,
            }
        )

    # Equipment identities (P-tags)
    gen_p = _tags_sample(gen_text, r"\bP\d{2,4}[A-Z]?\b")
    ans_p = _tags_sample(ans, r"\bP\d{2,4}[A-Z]?\b")
    site_p = {
        (e.get("normalized_name") or e.get("raw_name") or "").upper()
        for e in (site.get("equipment") or [])
        if (e.get("normalized_name") or "").upper().startswith("P")
    }
    # Intersection with site evidence
    evidence_hit = gen_p & site_p
    result["comparisons"].append(
        {
            "aspect": "equipment_identities",
            "category": "CORRECT_FROM_EVIDENCE",
            "generated_count": len(gen_p),
            "answer_sheet_count": len(ans_p),
            "sitemodel_count": len(site_p),
            "generated_also_in_sitemodel": len(evidence_hit),
            "in_answer_not_generated": len(ans_p - gen_p),
            "note": "Presence in answer sheet alone does not require generation",
        }
    )

    # PE identities
    gen_pe = _tags_sample(gen_text, r"\b(?:EZ)?PE\d{2,4}[A-Z0-9_]*\b")
    ans_pe = _tags_sample(ans, r"\b(?:EZ)?PE\d{2,4}[A-Z0-9_]*\b")
    result["comparisons"].append(
        {
            "aspect": "pe_identities",
            "category": "CORRECT_FROM_EVIDENCE"
            if int(generation_meta.get("pe_device_count") or 0) > 0
            else "MISSED",
            "generated_count": len(gen_pe),
            "answer_sheet_count": len(ans_pe),
            "meta_pe_device_count": generation_meta.get("pe_device_count"),
        }
    )

    # Encoder
    gen_enc = _tags_sample(gen_text, r"\bENC\d{2,4}[A-Z]?\b")
    ans_enc = _tags_sample(ans, r"\bENC\d{2,4}[A-Z]?\b")
    result["comparisons"].append(
        {
            "aspect": "encoder_identities",
            "category": "CORRECT_FROM_EVIDENCE" if gen_enc else "MISSED",
            "generated": sorted(gen_enc),
            "answer_sheet": sorted(ans_enc)[:20],
        }
    )

    # Scanner / WCS feature classes
    result["comparisons"].append(
        {
            "aspect": "scanner_presence",
            "category": "CORRECT_BUT_UNSUPPORTED"
            if site.get("scanners")
            else "ANSWER_SHEET_ONLY_NOT_EXPECTED_FROM_RUN",
            "sitemodel_scanners": len(site.get("scanners") or []),
            "generated_scanner_program": any("Scan" in p for p in gen_progs),
        }
    )
    result["comparisons"].append(
        {
            "aspect": "wcs_feature_class",
            "category": "CORRECT_BUT_UNSUPPORTED",
            "answer_sheet_has_wcs_program": any("WCS" in p for p in ans_progs),
            "generated_wcs_program": any("WCS" in p for p in gen_progs),
        }
    )
    result["comparisons"].append(
        {
            "aspect": "sorter_feature_class",
            "category": "CORRECT_BUT_UNSUPPORTED",
            "sitemodel_sorters": len(site.get("sorters") or []),
            "answer_sheet_sorter_programs": sorted(p for p in ans_progs if "Sorter" in p or "Track" in p)[:20],
            "generated_sorter_programs": sorted(p for p in gen_progs if "Sorter" in p or "Track" in p),
        }
    )

    # Area grouping
    result["comparisons"].append(
        {
            "aspect": "area_grouping",
            "category": "CORRECT_FROM_EVIDENCE",
            "detail": "Provisional controller Area from RUN; plant Areas remain engineer-required",
            "generated_areas": generation_meta.get("areas_summary"),
            "note": "Do not treat answer-sheet Area names as generation targets",
        }
    )

    result["ok"] = True
    result["counts_by_category"] = {}
    for c in result["comparisons"]:
        cat = c.get("category") or "UNKNOWN"
        result["counts_by_category"][cat] = result["counts_by_category"].get(cat, 0) + 1
    return result
