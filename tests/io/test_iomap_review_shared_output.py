#!/usr/bin/env python3
"""RUN-backed shared physical OUTPUTs are REVIEW_SHARED_OUTPUT — not FAIL, not silent drop."""
from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_studio_preflight import _check_iomap_duplicate_otes  # noqa: E402


def _classify_claims(owners: list[dict]) -> str:
    """Mirror fortna_autogen shared-output classification."""
    def prov(o: dict) -> str:
        if o.get("engineer_override"):
            return "ENGINEER"
        how = str(o.get("how") or "").lower()
        comment = str(o.get("comment") or "")
        if how in ("configio", "map", "direct", "physical", "eipcfg") or "Bank" in comment:
            return "RUN_PROVEN"
        if "eng logical" in comment.lower():
            return "ENGINEER"
        return "UNPROVEN"

    proven = all(prov(o) == "RUN_PROVEN" for o in owners)
    return "REVIEW_SHARED_OUTPUT" if proven else "FAIL"


class TestReviewSharedOutput(unittest.TestCase):
    def test_mscreno_three_collisions_are_run_proven(self) -> None:
        cases = [
            [
                {"tname": "MTRANS", "how": "configio", "comment": "MTRANS · Bank1024.12 · via configio"},
                {"tname": "SSVSTOP1", "how": "configio", "comment": "SSVSTOP1 · Bank1024.12 · via configio"},
            ],
            [
                {"tname": "CP3PL", "how": "configio", "comment": "CP3PL · Bank1045.4 · via configio"},
                {"tname": "EZSSV12", "how": "configio", "comment": "EZSSV12 · Bank1045.14 · via configio"},
            ],
            [
                {"tname": "CPPW5", "how": "configio", "comment": "CPPW5 · Bank1045.17 · via configio"},
                {"tname": "MX14P_MX14SSV", "how": "configio", "comment": "MX14P_MX14SSV · Bank1045.17 · via configio"},
            ],
        ]
        for owners in cases:
            self.assertEqual(_classify_claims(owners), "REVIEW_SHARED_OUTPUT")

    def test_engineer_collision_fails(self) -> None:
        owners = [
            {"tname": "MTRANS", "how": "configio", "comment": "MTRANS · Bank1024.12 · via configio"},
            {"tname": "FAKE", "engineer_override": True, "comment": "FAKE (eng logical)"},
        ]
        self.assertEqual(_classify_claims(owners), "FAIL")

    def test_preflight_warns_not_errors_for_annotated_shared(self) -> None:
        l5x = """<?xml version="1.0"?>
<RSLogix5000Content>
  <Controller>
    <Programs>
      <Program Name="IO_MAP">
        <Routines>
          <Routine Name="CP_O" Type="RLL">
            <RLLContent>
              <Rung Number="1" Type="N">
                <Comment><![CDATA[MTRANS · Bank1024.12 · via configio · REVIEW_SHARED_OUTPUT · RUN_PROVEN]]></Comment>
                <Text><![CDATA[XIC(MTRANS)OTE(AENTR3:O.Data[18].2);]]></Text>
              </Rung>
              <Rung Number="2" Type="N">
                <Comment><![CDATA[SSVSTOP1 · Bank1024.12 · via configio · REVIEW_SHARED_OUTPUT · RUN_PROVEN]]></Comment>
                <Text><![CDATA[XIC(SSVSTOP1)OTE(AENTR3:O.Data[18].2);]]></Text>
              </Rung>
            </RLLContent>
          </Routine>
        </Routines>
      </Program>
    </Programs>
  </Controller>
</RSLogix5000Content>
"""
        findings: list[dict] = []

        def add(sev, kind, message, **extra):
            findings.append({"severity": sev, "kind": kind, "message": message, **extra})

        _check_iomap_duplicate_otes(l5x, add)
        errs = [f for f in findings if f["severity"] == "ERROR"]
        warns = [f for f in findings if f["kind"] == "iomap_review_shared_output"]
        self.assertFalse(errs, findings)
        self.assertTrue(warns, findings)
        self.assertIn("REVIEW_SHARED_OUTPUT", warns[0]["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
