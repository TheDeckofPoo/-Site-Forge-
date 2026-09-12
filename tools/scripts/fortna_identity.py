#!/usr/bin/env python3
"""Exact conveyor / equipment identity matching (no ambiguous string prefixes).

P120 must NOT imply P1200. P424 may relate to P424A (same numeric base + letter suffix).
"""
from __future__ import annotations

import re

_P_TAG = re.compile(r"^P(\d{2,4})([A-Z]*)$", re.I)


def parse_p_tag(tag: str) -> tuple[str, str] | None:
    """Return (digits, letter_suffix) for P### / P###A style tags."""
    m = _P_TAG.match((tag or "").strip().upper())
    if not m:
        return None
    return m.group(1), m.group(2)


def conveyor_identities_match(a: str, b: str) -> bool:
    """True when two identities refer to the same conveyor family.

    Rules:
    - Exact match (case-insensitive)
    - Same numeric base with optional trailing letters only (P424 ↔ P424A)
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
    return pa[0] == pb[0]


def linked_owns_conveyor(conveyor: str, linked: set[str] | frozenset[str]) -> bool:
    """Whether `conveyor` is owned by any identity in `linked` under exact-family rules."""
    cu = (conveyor or "").strip().upper()
    if not cu:
        return False
    if cu in linked:
        return True
    return any(conveyor_identities_match(cu, lc) for lc in linked)
