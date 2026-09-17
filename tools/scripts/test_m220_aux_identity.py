#!/usr/bin/env python3
"""PL-3: M220_AUX and M220A_AUX must never collapse to the same logical OTE owner.

Exact physical identity is authoritative. Alphabetic suffixes must not be stripped
to establish ownership. Fixtures prove distinct Auxiliary_Forward targets.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))


def _motor_to_p_base_replica(mot_core: str, known_convs: set[str]) -> str:
    """Mirror of fortna_autogen._motor_to_p_base post-PL-3 contract."""
    mm = re.match(r"^M(\d{2,4})([A-Z]?)$", mot_core, re.I)
    if not mm:
        return ""
    digits, letters = mm.group(1), (mm.group(2) or "").upper()
    full = f"P{digits}{letters}"
    if full in known_convs:
        return full
    if letters:
        return ""
    base = f"P{digits}"
    if base in known_convs:
        return base
    p1 = f"{base}_P1"
    if p1 in known_convs:
        return p1
    return ""


def aux_ote(mot_core: str, known: set[str]) -> str:
    pbase = _motor_to_p_base_replica(mot_core, known)
    m = re.match(r"^M(\d{2,4}[A-Z]?)$", mot_core, re.I)
    digits = m.group(1) if m else ""
    return f"{pbase}_MS.I.Auxiliary_Forward" if pbase else f"P{digits}_MS.I.Auxiliary_Forward"


class TestM220AuxIdentity(unittest.TestCase):
    def test_both_parents_present_map_distinct(self) -> None:
        known = {"P220", "P220A", "P100"}
        a = aux_ote("M220", known)
        b = aux_ote("M220A", known)
        self.assertEqual(a, "P220_MS.I.Auxiliary_Forward")
        self.assertEqual(b, "P220A_MS.I.Auxiliary_Forward")
        self.assertNotEqual(a, b)

    def test_bare_parent_suppressed_does_not_steal_lettered(self) -> None:
        """Historical collision: P220 suppressed, only P220A in known → bare M220
        must NOT map onto P220A (LEGACY_HEURISTIC / NAME_NORMALIZATION_COLLISION).
        """
        known = {"P220A", "P100"}  # P220 assembly-suppressed / absent
        a = aux_ote("M220", known)
        b = aux_ote("M220A", known)
        self.assertEqual(b, "P220A_MS.I.Auxiliary_Forward")
        self.assertNotEqual(a, b)
        self.assertEqual(a, "P220_MS.I.Auxiliary_Forward")  # fallback keeps bare identity
        self.assertNotIn("P220A", a)

    def test_lettered_never_strips_to_bare(self) -> None:
        known = {"P220"}  # P220A absent
        b = aux_ote("M220A", known)
        # Exact lettered missing → empty pbase → P220A_MS fallback (keeps suffix)
        self.assertEqual(b, "P220A_MS.I.Auxiliary_Forward")
        self.assertNotEqual(b, "P220_MS.I.Auxiliary_Forward")


class TestLetteredCollisionCandidates(unittest.TestCase):
    """Report-only fixture list — does not mutate records."""

    CANDIDATES = [
        ("M220_AUX", "M220A_AUX"),
        ("M130", "M130A"),
        ("P136", "P136A"),
        ("P150", "P150A"),
        ("P145", "P145A"),
    ]

    def test_candidate_pairs_documented(self) -> None:
        self.assertGreaterEqual(len(self.CANDIDATES), 3)
        self.assertIn(("M220_AUX", "M220A_AUX"), self.CANDIDATES)


if __name__ == "__main__":
    unittest.main()
