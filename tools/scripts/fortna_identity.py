#!/usr/bin/env python3
"""Exact conveyor / equipment identity matching (no ambiguous string prefixes).

P120 must NOT imply P1200. P424 may relate to P424A (same numeric base + letter suffix).
Section tokens like P136_P1 / P136_P2 are distinct conveyors (exact section match only).
"""
from __future__ import annotations

import re

# digits + optional letter suffix OR optional _P# section (not both required)
_P_TAG = re.compile(
    r"^P(\d{2,4})(?:([A-Z]+)|_(P\d+))?$",
    re.I,
)


def parse_p_tag(tag: str) -> tuple[str, str] | None:
    """Return (digits, suffix) for P### / P###A / P###_P1 style tags.

    suffix is:
      - '' for plain P120
      - letter(s) for P130A → 'A'
      - section token including underscore for P136_P1 → '_P1'
    """
    m = _P_TAG.match((tag or "").strip().upper())
    if not m:
        return None
    digits = m.group(1)
    letters = m.group(2) or ""
    section = m.group(3) or ""
    if section:
        return digits, f"_{section.upper()}"
    return digits, letters.upper()


def conveyor_identities_match(a: str, b: str) -> bool:
    """True when two identities refer to the same conveyor family.

    Rules:
    - Exact match (case-insensitive)
    - Same numeric base with optional trailing letters only (P424 ↔ P424A)
    - Section tokens (P136_P1) match only the identical section — not P136, not P136_P2
    - NEVER digit-prefix (P120 ↛ P1200; P12 ↛ P120)
    """
    au = (a or "").strip().upper()
    bu = (b or "").strip().upper()
    if not au or not bu:
        return False
    if au == bu:
        return True
    pa, pb = parse_p_tag(au), parse_p_tag(bu)
    if not pa or not pb:
        return False
    # Critical: digit groups must be identical strings, not prefix-equal
    if pa[0] != pb[0]:
        return False
    sa, sb = pa[1], pb[1]
    # Section conveyors are distinct identities — require exact suffix match
    if sa.startswith("_P") or sb.startswith("_P"):
        return sa == sb
    # Letter family: P130 ↔ P130A (empty or letters only)
    return True


def linked_owns_conveyor(conveyor: str, linked: set[str] | frozenset[str]) -> bool:
    """Whether `conveyor` is owned by any identity in `linked` under exact-family rules."""
    cu = (conveyor or "").strip().upper()
    if not cu:
        return False
    if cu in linked:
        return True
    return any(conveyor_identities_match(cu, lc) for lc in linked)
