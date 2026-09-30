#!/usr/bin/env python3
"""ORI-084: sidecar physical_io_map must not false-bad-bit POINT high bytes."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_autogen import (  # noqa: E402
    _fortna_bit_is_high,
    _fortna_bit_to_data_bit,
    _point_card_max_bit,
)


class TestOri084SidecarHighBit(unittest.TestCase):
    def test_point_high_byte_maps_after_minus_eight(self) -> None:
        max_bit = _point_card_max_bit("1734-IB8")
        self.assertEqual(max_bit, 7)
        for fortna_bit, expect in (("10", 0), ("14", 4), ("17", 7)):
            self.assertTrue(_fortna_bit_is_high(fortna_bit), fortna_bit)
            hv = int(fortna_bit, 8)
            bit_for_card = str(hv - 8) if hv >= 8 else fortna_bit
            data = _fortna_bit_to_data_bit(bit_for_card, max_bit=max_bit)
            self.assertEqual(data, expect, fortna_bit)

    def test_without_adjust_high_bit_fails_on_point_card(self) -> None:
        # Documents the pre-fix failure mode the sidecar must not emit.
        self.assertIsNone(_fortna_bit_to_data_bit("14", max_bit=7))


if __name__ == "__main__":
    unittest.main()
