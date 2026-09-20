#!/usr/bin/env python3
"""Configio.In_Out direction semantics (evidence-backed helper).

FortnaPlus table reference: Configio purpose includes direction ownership;
In_Out is a key field. Site Forge fortna_io_banks treats mask '1' bits as
active. Empirical current-site correlation (MSCATL/ORINDY):

  0000000000000000  ↔ input catalogs (IA16/IB16)
  0000000011111111  ↔ output catalogs (OA8I/OB16P/OW8)

Per-bit mixed masks are possible in principle; when present → REVIEW.
Catalog direction remains primary when catalog is KNOWN; In_Out corroborates.
"""
from __future__ import annotations

from typing import Any

from fortna_hardware_family import detect_family_from_catalog
from fortna_physical_word_resolver import _module_direction

MASK_ALL_ZERO = "0000000000000000"
MASK_LOW_BYTE_ONES = "0000000011111111"  # observed output-like whole-word pattern


def normalize_in_out_mask(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    # Keep only 0/1; pad/truncate to 16 for comparison when numeric-looking
    bits = "".join(ch for ch in s if ch in "01")
    return bits


def direction_from_in_out_mask(mask: Any) -> dict[str, Any]:
    """Infer whole-word direction hint from In_Out mask.

    Returns direction I|O|MIXED|UNKNOWN with confidence and notes.
    Does NOT invent per-bit channel direction for mixed masks.
    """
    bits = normalize_in_out_mask(mask)
    if not bits:
        return {
            "direction": "UNKNOWN",
            "confidence": "LOW",
            "mask": "",
            "notes": ["empty_in_out"],
        }
    ones = bits.count("1")
    zeros = bits.count("0")
    if ones == 0:
        return {
            "direction": "I",
            "confidence": "MEDIUM",
            "mask": bits,
            "notes": ["all_zero_mask_input_like", "corroborated_by_site_correlation"],
        }
    if bits == MASK_LOW_BYTE_ONES or (ones == 8 and bits.endswith("11111111") and bits.startswith("00000000")):
        return {
            "direction": "O",
            "confidence": "MEDIUM",
            "mask": bits,
            "notes": ["low_byte_ones_output_like", "corroborated_by_site_correlation"],
        }
    if 0 < ones < len(bits):
        return {
            "direction": "MIXED",
            "confidence": "LOW",
            "mask": bits,
            "ones": ones,
            "zeros": zeros,
            "notes": ["mixed_mask_per_bit_possible", "requires_REVIEW"],
        }
    return {
        "direction": "UNKNOWN",
        "confidence": "LOW",
        "mask": bits,
        "notes": ["unrecognized_mask_pattern"],
    }


def resolve_configio_direction(
    *,
    catalog: str = "",
    in_out: Any = "",
) -> dict[str, Any]:
    """Combine catalog direction + In_Out corroboration.

    Primary: known catalog → I/O from module type letters.
    Corroboration: In_Out mask.
    Conflict → REVIEW_REQUIRED (do not silently pick).
    """
    cat_dir = _module_direction(catalog) if catalog else ""
    mask_info = direction_from_in_out_mask(in_out)
    mask_dir = mask_info.get("direction") or "UNKNOWN"

    if cat_dir in ("I", "O") and mask_dir in ("I", "O"):
        if cat_dir != mask_dir:
            return {
                "direction": cat_dir,
                "status": "DIRECTION_CONFLICT",
                "catalog_direction": cat_dir,
                "mask_direction": mask_dir,
                "mask_info": mask_info,
                "notes": ["catalog_and_in_out_disagree"],
            }
        return {
            "direction": cat_dir,
            "status": "AGREE",
            "catalog_direction": cat_dir,
            "mask_direction": mask_dir,
            "mask_info": mask_info,
            "notes": ["catalog_primary_in_out_corroborates"],
        }
    if cat_dir in ("I", "O"):
        return {
            "direction": cat_dir,
            "status": "CATALOG_ONLY",
            "catalog_direction": cat_dir,
            "mask_direction": mask_dir,
            "mask_info": mask_info,
            "notes": ["catalog_primary"],
        }
    if mask_dir in ("I", "O"):
        return {
            "direction": mask_dir,
            "status": "MASK_ONLY",
            "catalog_direction": cat_dir or "",
            "mask_direction": mask_dir,
            "mask_info": mask_info,
            "notes": ["in_out_heuristic_only", "medium_confidence"],
        }
    if mask_dir == "MIXED":
        return {
            "direction": "",
            "status": "MIXED_REVIEW",
            "catalog_direction": cat_dir or "",
            "mask_direction": mask_dir,
            "mask_info": mask_info,
            "notes": ["mixed_in_out_requires_review"],
        }
    return {
        "direction": "",
        "status": "UNKNOWN",
        "catalog_direction": cat_dir or "",
        "mask_direction": mask_dir,
        "mask_info": mask_info,
        "notes": ["no_direction_evidence"],
    }
