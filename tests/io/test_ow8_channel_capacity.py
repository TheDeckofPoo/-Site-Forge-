#!/usr/bin/env python3
"""OW8 occupancy must report capacity 8 (7/8 not 7)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_hardware_family import channel_capacity_for_catalog  # noqa: E402


class TestOw8Capacity(unittest.TestCase):
    def test_ow8_is_eight(self) -> None:
        self.assertEqual(channel_capacity_for_catalog("1794-OW8"), 8)

    def test_ob8_still_eight(self) -> None:
        self.assertEqual(channel_capacity_for_catalog("1794-OB8"), 8)

    def test_ib16_sixteen(self) -> None:
        self.assertEqual(channel_capacity_for_catalog("1794-IB16"), 16)


if __name__ == "__main__":
    unittest.main()
