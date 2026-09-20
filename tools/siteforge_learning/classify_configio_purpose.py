#!/usr/bin/env python3
"""Classify Configio row PURPOSE before dialect classification.

Physical-I/O learning must not treat Fortna internal memory / N/A placeholders
as UNKNOWN hardware dialects. Source rows are never deleted — only classified.
"""
from __future__ import annotations

import re
from typing import Any

PURPOSE_PHYSICAL_IO = "PHYSICAL_IO_CANDIDATE"
PURPOSE_ADAPTER_NETWORK = "ADAPTER_OR_NETWORK_STATUS"
PURPOSE_INTERNAL_MEMORY = "INTERNAL_MEMORY"
PURPOSE_NONPHYSICAL = "NONPHYSICAL_CONFIG"
PURPOSE_DISABLED = "DISABLED_OR_NOT_APPLICABLE"
PURPOSE_INCOMPLETE = "INCOMPLETE_CONFIGURATION"
PURPOSE_UNKNOWN = "UNKNOWN_PURPOSE"

# Curtis-confirmed internal FortnaPlus program memory/logic patterns
_MEMORY_RE = re.compile(
    r"(?i)^\s*("
    r"MEM(?:ORY)?(?:[\s_\-]*WORD)?[\s_\-]*\d*"
    r"|MEM[\s_\-]?WD[\s_\-]?\d*"
    r"|MEMWD[\s_\-]?\d*"
    r"|MEMORY[\s_\-]+\d+"
    r"|Memory_Word_\d+"
    r"|AENTR?-MEM[\-\d]*"
    r"|CP\d+[_\-]?MEM\d*"
    r"|MEM\b"
    r")\s*$"
)

_SEPARATOR_RE = re.compile(r"^[\-\_=]{3,}$")
_ROW_LABEL_RE = re.compile(r"(?i)^Row\s*\d+$")

_PLACEHOLDER_RE = re.compile(r"(?i)^\s*(N/?A|INVALID|NONE|NULL|-)\s*$")

_ADAPTER_STATUS_RE = re.compile(
    r"(?i)^\s*("
    r"\d{4}-AENTR?(?:/\w+)?"
    r"|AENTR?\-?\d*"
    r"|PowerFlex[\w\-]*"
    r"|VU[\w\-]*"
    r")\s*$"
)

# Bare numeric Desc (often placeholder index text) — not a hardware dialect
_BARE_NUMERIC_RE = re.compile(r"^\d{1,4}$")


def _truthy_physical_bank(bank: Any) -> bool:
    try:
        b = int(float(str(bank).strip()))
    except (TypeError, ValueError):
        return False
    return b > 0


def _truthy_word(word: Any) -> bool:
    s = str(word or "").strip()
    if not s or s.upper() in ("N/A", "INVALID", "NONE", ""):
        return False
    try:
        return int(float(s)) >= 0
    except (TypeError, ValueError):
        return bool(s)


def _iface_is_physical(iface: str) -> bool:
    u = (iface or "").strip().upper()
    if not u or u in ("N/A", "INVALID", "NONE", ""):
        return False
    # RTA / EIP / PLC5 physical interfaces seen in Fortna
    return any(k in u for k in ("RTA", "EIP", "ENET", "ETHERNET", "POINT", "FLEX"))


def classify_configio_purpose(row: dict[str, Any]) -> dict[str, Any]:
    """Classify one Configio row's purpose.

    Returns:
      purpose, reasons[], keep_in_physical_io_queue (bool),
      exception_nonphysical_desc_but_physical_fields (bool)
    """
    desc = str(row.get("desc") or row.get("Desc") or "").strip()
    iface = str(row.get("interface") or row.get("Interface") or "").strip()
    bank = row.get("bank") if "bank" in row else row.get("Bank")
    word = row.get("octal_word") if "octal_word" in row else row.get("Octal_Word")
    lohi = str(row.get("lohi") or row.get("LoHi") or "").strip()
    in_out = str(row.get("in_out") or row.get("In_Out") or "").strip()
    io_type = str(row.get("i_o_type") or row.get("I_O_Type") or "").strip()
    status = str(row.get("status") or row.get("Status") or "").strip()
    process = str(row.get("process") or row.get("Process") or "").strip()

    has_bank = _truthy_physical_bank(bank)
    has_word = _truthy_word(word)
    has_iface = _iface_is_physical(iface)
    has_inout = bool(in_out) and in_out.upper() not in ("N/A", "INVALID", "")
    has_lohi = bool(lohi) and lohi.upper() not in ("N/A", "INVALID", "")
    strong_physical = has_iface and (has_bank or has_word) and (has_inout or has_lohi or has_bank)

    reasons: list[str] = []
    iface_u = iface.upper()
    io_type_u = io_type.upper()
    memory_by_field = iface_u == "MEMORY" or io_type_u == "MEMORY"
    memory_by_desc = bool(desc and _MEMORY_RE.match(desc))

    # --- Internal memory by field semantics (Gilfoyle / PMart) and/or Desc ---
    if memory_by_field:
        if strong_physical and has_iface and iface_u != "MEMORY":
            return {
                "purpose": PURPOSE_PHYSICAL_IO,
                "reasons": [
                    "i_o_type_or_interface_memory",
                    "BUT_conflicting_strong_physical_interface",
                ],
                "keep_in_physical_io_queue": True,
                "exception_nonphysical_desc_but_physical_fields": True,
                "detection": "field_semantics_conflict_review",
            }
        return {
            "purpose": PURPOSE_INTERNAL_MEMORY,
            "reasons": ["interface_or_i_o_type_equals_memory"],
            "keep_in_physical_io_queue": False,
            "exception_nonphysical_desc_but_physical_fields": False,
            "detection": "field_semantics",
        }

    if memory_by_desc:
        if strong_physical:
            return {
                "purpose": PURPOSE_PHYSICAL_IO,
                "reasons": [
                    "desc_looks_like_internal_memory",
                    "BUT_strong_physical_fields_present",
                ],
                "keep_in_physical_io_queue": True,
                "exception_nonphysical_desc_but_physical_fields": True,
                "detection": "desc_pattern_conflict",
            }
        return {
            "purpose": PURPOSE_INTERNAL_MEMORY,
            "reasons": ["desc_matches_internal_memory_pattern"],
            "keep_in_physical_io_queue": False,
            "exception_nonphysical_desc_but_physical_fields": False,
            "detection": "desc_pattern",
        }

    # --- Adapter / network status-looking Desc ---
    if desc and _ADAPTER_STATUS_RE.match(desc):
        # PowerFlex / AENT / VU names are network-device identity, not I/O channel dialects
        if not strong_physical or "POWERFLEX" in desc.upper() or desc.upper().startswith("VU"):
            return {
                "purpose": PURPOSE_ADAPTER_NETWORK,
                "reasons": ["desc_looks_like_adapter_or_drive"],
                "keep_in_physical_io_queue": False,
                "exception_nonphysical_desc_but_physical_fields": False,
            }

    # Bare numeric Desc alone is not a dialect — keep only if strong physical fields
    if desc and _BARE_NUMERIC_RE.match(desc) and not strong_physical:
        return {
            "purpose": PURPOSE_INCOMPLETE if has_iface else PURPOSE_NONPHYSICAL,
            "reasons": ["bare_numeric_desc", "insufficient_physical_fields"],
            "keep_in_physical_io_queue": False,
            "exception_nonphysical_desc_but_physical_fields": False,
        }

    if desc and (_SEPARATOR_RE.match(desc) or _ROW_LABEL_RE.match(desc)):
        return {
            "purpose": PURPOSE_NONPHYSICAL,
            "reasons": ["separator_or_row_label_desc"],
            "keep_in_physical_io_queue": False,
            "exception_nonphysical_desc_but_physical_fields": False,
        }

    # --- Placeholder Desc ---
    placeholder = (not desc) or bool(_PLACEHOLDER_RE.match(desc))
    if placeholder:
        if strong_physical:
            return {
                "purpose": PURPOSE_PHYSICAL_IO,
                "reasons": [
                    "desc_blank_or_placeholder",
                    "strong_physical_fields_keep_candidate",
                ],
                "keep_in_physical_io_queue": True,
                "exception_nonphysical_desc_but_physical_fields": True,
            }
        # Entire row nonphysical / not applicable
        if not has_bank and not has_word and not has_iface:
            purpose = PURPOSE_DISABLED if desc.upper() in ("N/A", "INVALID") or not desc else PURPOSE_INCOMPLETE
            if desc.upper() in ("N/A", "INVALID"):
                purpose = PURPOSE_DISABLED
            elif not desc:
                purpose = PURPOSE_INCOMPLETE
            return {
                "purpose": purpose,
                "reasons": ["placeholder_desc", "no_physical_fields"],
                "keep_in_physical_io_queue": False,
                "exception_nonphysical_desc_but_physical_fields": False,
            }
        if has_iface and not has_bank and not has_word:
            return {
                "purpose": PURPOSE_INCOMPLETE,
                "reasons": ["placeholder_desc", "interface_without_bank_or_word"],
                "keep_in_physical_io_queue": False,
                "exception_nonphysical_desc_but_physical_fields": False,
            }
        return {
            "purpose": PURPOSE_NONPHYSICAL,
            "reasons": ["placeholder_desc", "weak_or_mixed_fields"],
            "keep_in_physical_io_queue": False,
            "exception_nonphysical_desc_but_physical_fields": False,
        }

    # --- Status flags ---
    st_u = status.upper()
    if st_u in ("DISABLED", "INACTIVE", "NOTUSED", "NOT_USED") and not strong_physical:
        return {
            "purpose": PURPOSE_DISABLED,
            "reasons": [f"status={status}"],
            "keep_in_physical_io_queue": False,
            "exception_nonphysical_desc_but_physical_fields": False,
        }

    # --- Physical I/O candidate ---
    if has_iface or has_bank or has_word or has_inout:
        reasons.append("physical_field_evidence")
        if desc:
            reasons.append("non_empty_desc")
        return {
            "purpose": PURPOSE_PHYSICAL_IO,
            "reasons": reasons,
            "keep_in_physical_io_queue": True,
            "exception_nonphysical_desc_but_physical_fields": False,
        }

    return {
        "purpose": PURPOSE_UNKNOWN,
        "reasons": ["no_matching_purpose_rule"],
        "keep_in_physical_io_queue": False,
        "exception_nonphysical_desc_but_physical_fields": False,
    }
