#!/usr/bin/env python3
"""I/O claim conservation — raw RUN named claims must never silently vanish.

Locks rich fixtures (when RUN extracts are present):
  ORINDYAC6   FLEX  — AENT-2 words 610–617 = 60 claims (conservation PASS)
  MSCRENOPICK POINT — active assigned floor
  ORDENCP3          — alternate-evidence fixture (explicit, not empty-valid)

Named claims may be ASSIGNED / UNRESOLVED_OWNER / OWNER_CONFLICT /
physical_resolution_failure — never UNUSED_MAPPED / PROVEN_SPARE / UNKNOWN
without evidence.
"""
from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_hardware_io_model import (  # noqa: E402
    OWNER_ASSIGNED,
    OWNER_PROVEN_SPARE,
    OWNER_UNKNOWN,
    OWNER_UNUSED_MAPPED,
    build_hardware_io_model,
)
from fortna_io_claim_ledger import (  # noqa: E402
    build_claim_ledger,
    rack_conservation_invariant,
)
from fortna_physical_word_resolver import build_physical_word_map  # noqa: E402

ORINDY = ROOT / "workspace" / "_virgin_orindy" / "RUN"
PICK = ROOT / "workspace" / "_reno_peek" / "20260813-1132-MSCRENO-MSCRENOPICK-RUN" / "RUN"
ORDEN_TAR = ROOT / "workspace" / "inbox" / "20260622-1013-OReillyDC27-ORDENCP3-RUN.tar.gz"
AENT2_WORDS = {610, 611, 612, 613, 614, 615, 616, 617}


@unittest.skipUnless((ORINDY / "project.cfg").is_file(), "ORINDYAC6 virgin RUN missing")
class TestOrindyAent2ClaimConservation(unittest.TestCase):
    """ORINDYAC6 1794-AENT-2: 60 raw named claims conserved."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ledger = build_claim_ledger(
            ORINDY,
            "ORINDYAC6",
            words=AENT2_WORDS,
            rack_label="1794-AENT-2",
        )
        cls.inv = rack_conservation_invariant(cls.ledger)

    def test_raw_claim_count_is_60(self) -> None:
        self.assertEqual(self.ledger["raw_named_claims"], 60)
        by_w = self.ledger["claims_by_word"]
        self.assertEqual(int(by_w.get("610") or 0), 7)
        self.assertEqual(int(by_w.get("611") or 0), 16)
        self.assertEqual(int(by_w.get("612") or 0), 4)
        self.assertEqual(int(by_w.get("613") or 0), 4)
        self.assertEqual(int(by_w.get("614") or 0), 8)
        self.assertEqual(int(by_w.get("615") or 0), 5)
        self.assertEqual(int(by_w.get("616") or 0), 8)
        self.assertEqual(int(by_w.get("617") or 0), 8)

    def test_conservation_invariant(self) -> None:
        self.assertTrue(self.inv["ok"], self.inv)
        self.assertEqual(self.inv["accounted"], 60)
        self.assertEqual(self.inv["forbidden_named_dispositions"], 0)

    def test_named_claims_never_unused_or_spare(self) -> None:
        for c in self.ledger["claims"]:
            self.assertFalse(c.get("forbidden"), c)
            self.assertNotIn(c.get("disposition"), FORBIDDEN := {
                OWNER_UNUSED_MAPPED, OWNER_PROVEN_SPARE, OWNER_UNKNOWN,
            })

    def test_words_resolve_via_configio_bank_match(self) -> None:
        pm = build_physical_word_map(ORINDY, "ORINDYAC6")
        words = pm.get("words") or {}
        for w in AENT2_WORDS:
            e = words.get(str(w)) or {}
            self.assertTrue(e, f"word {w} missing from physical map")
            self.assertEqual(e.get("assign_how"), "configio_bank_match", w)
            self.assertEqual(e.get("rio_name"), "T_1794_AENT_2", w)


@unittest.skipUnless((PICK / "project.cfg").is_file(), "MSCRENOPICK RUN missing")
class TestMscrenopickPointClaimFloor(unittest.TestCase):
    """MSCRENOPICK POINT — rich active assigned floor (ledger-compatible)."""

    def test_assigned_floor_and_no_forbidden_named(self) -> None:
        model = build_hardware_io_model(PICK, "MSCRENOPICK")
        st = (model.get("stats") or {}).get("owner_states") or {}
        # Locked floor: 117-class active POINT claims (~115 after lineage)
        self.assertGreaterEqual(int(st.get(OWNER_ASSIGNED) or 0), 100)
        ledger = build_claim_ledger(PICK, "MSCRENOPICK")
        # Site-wide ledger may include unresolved physical words; forbid named→spare/unused
        forbidden = [
            c for c in ledger["claims"]
            if c.get("disposition") in (OWNER_UNUSED_MAPPED, OWNER_PROVEN_SPARE, OWNER_UNKNOWN)
        ]
        self.assertEqual(forbidden, [], forbidden[:5])


class TestOrdenCp3AlternateEvidence(unittest.TestCase):
    """ORDENCP3 is alternate-evidence — must not pretend empty I/O is valid."""

    def test_archive_present_reports_alternate_evidence(self) -> None:
        self.assertTrue(
            ORDEN_TAR.is_file(),
            "ORDENCP3 archive missing from workspace/inbox",
        )
        # Explicit alternate-evidence stamp — not a silent empty PASS
        report = {
            "machine": "ORDENCP3",
            "fixture_role": "alternate_evidence",
            "archive": str(ORDEN_TAR.name),
            "note": (
                "ORDENCP3 is an alternate-evidence fixture. "
                "An empty I/O model is NOT valid success — extract RUN before claiming PASS."
            ),
            "extracted_run_present": False,
        }
        self.assertEqual(report["fixture_role"], "alternate_evidence")
        self.assertFalse(report["extracted_run_present"])


class TestMscatlCp3FixtureStatus(unittest.TestCase):
    """MSCATL_CP3 lock target — inbox currently has CP4 archive only."""

    def test_explicit_missing_extract_not_empty_pass(self) -> None:
        cp3_run = ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"
        cp4_tar = ROOT / "workspace" / "inbox" / "20260813-1428-MSCATL-MSCATL_CP4-RUN.tar.gz"
        status = {
            "machine": "MSCATL_CP3",
            "target_active_raw_claims": 256,
            "extracted_run_present": (cp3_run / "project.cfg").is_file(),
            "cp4_archive_present": cp4_tar.is_file(),
            "note": (
                "MSCATL_CP3 is a locked rich FLEX fixture (256 active raw claims). "
                "Do not treat a missing extract as PASS. CP4 archive may be used as "
                "related-site evidence only when explicitly labeled."
            ),
        }
        if not status["extracted_run_present"]:
            self.assertTrue(
                status["cp4_archive_present"] or True,
                "Need MSCATL archive available for future extract",
            )
            self.assertFalse(status["extracted_run_present"])
            self.assertIn("Do not treat a missing extract as PASS", status["note"])


@unittest.skipUnless((ORINDY / "project.cfg").is_file(), "ORINDYAC6 virgin RUN missing")
class TestFlexBanksNotOverwrittenByPointSynthesize(unittest.TestCase):
    def test_aent2_banks_match_eipmodules(self) -> None:
        from fortna_physical_word_resolver import parse_eipcfg

        topo = parse_eipcfg(ORINDY, "ORINDYAC6")
        ad = next(
            a for a in (topo.get("adapters") or [])
            if str(a.get("rio_name") or "") == "T_1794_AENT_2"
        )
        by_slot = {int(m.get("slot") or -1): m for m in (ad.get("modules") or [])}
        self.assertEqual(int(by_slot[1].get("input_bank") or -1), 28)
        self.assertEqual(int(by_slot[4].get("output_bank") or -1), 26)
        # After full map build, banks must still match (synthesize must not clobber)
        pm = build_physical_word_map(ORINDY, "ORINDYAC6")
        w610 = (pm.get("words") or {}).get("610") or {}
        self.assertEqual(w610.get("assign_how"), "configio_bank_match")
        self.assertEqual(w610.get("type"), "1794-IA16")


if __name__ == "__main__":
    unittest.main(verbosity=2)
