#!/usr/bin/env python3
"""ORI-082: mapped outputs must expose writer coverage classes."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_autogen import _classify_mapped_output_writers  # noqa: E402


class TestOri082WriterCoverage(unittest.TestCase):
    def test_writer_classes(self) -> None:
        l5x = """
        <Program Name="Area_Fast"><Routines>
        <Routine Name="Conv_Fast"><RLLContent>
        <Text><![CDATA[Fast_Conv(P1_Conv,NO_PE,NO_PE);]]></Text>
        </RLLContent></Routine>
        </Routines></Program>
        <Program Name="IO_MAP"><Routines>
        <Routine Name="CP_O"><RLLContent>
        <Text><![CDATA[XIC(M1)OTE(AENTR3:O.Data[11].0);]]></Text>
        <Text><![CDATA[XIC(EZSSV3)OTE(AENTR1:O.Data[2].1);]]></Text>
        </RLLContent></Routine>
        </Routines></Program>
        """
        cov = _classify_mapped_output_writers(
            mapped_output_tags=["M1", "EZSSV3", "P1_Conv"],
            l5x_text=l5x,
            intentional_undriven={"EZSSV3"},
        )
        self.assertEqual(cov["by_class"]["VALID_WRITER"], ["P1_Conv"])
        self.assertEqual(cov["by_class"]["INTENTIONALLY_UNDRIVEN_REVIEW"], ["EZSSV3"])
        self.assertEqual(cov["by_class"]["DEFECT"], ["M1"])
        self.assertEqual(cov["outputs_with_valid_writers"], 1)
        self.assertEqual(cov["intentional_review_outputs"], 1)
        self.assertEqual(cov["writerless_defect_outputs"], 1)


if __name__ == "__main__":
    unittest.main()
