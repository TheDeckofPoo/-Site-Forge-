#!/usr/bin/env python3
"""P0-17 — bare panel-token Configio Desc is UNUSED, not UNRESOLVED_OWNER.

EP1 / EP12 / EP2 are panel identity only. They must classify as topology →
UNUSED_MAPPED / UNCLAIMED_HARDWARE_CHANNEL.

They must NOT:
  - count as unresolved owners
  - go to AI Assist
  - go to Relay escalation
  - keep Compile Hub Hardware in REVIEW_REQUIRED
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_hardware_io_model import (  # noqa: E402
    OWNER_UNRESOLVED,
    OWNER_UNUSED_MAPPED,
    _configio_desc_claim,
    _is_panel_identity_only_desc,
    enrich_channel_ownership,
)


class TestP017UnusedPanelTokenChannels(unittest.TestCase):
    def test_panel_identity_tokens(self) -> None:
        for d in ("EP1", "EP12", "EP2", "CP5", "RIO52"):
            self.assertTrue(_is_panel_identity_only_desc(d), d)
            self.assertEqual(_configio_desc_claim(d), "topology", d)

    def test_device_shaped_names_are_not_panel_identity(self) -> None:
        for d in ("ESPB2", "ESPB24", "ESLS2", "P220", "MCR1"):
            self.assertFalse(_is_panel_identity_only_desc(d), d)
            # Device-shaped Desc remains occupancy candidate (not topology-only).
            self.assertEqual(_configio_desc_claim(d), "occupied", d)

    def test_ep1_channel_is_unused_not_unresolved(self) -> None:
        ch = {
            "physical_address": "AENTR1:I.Data[0].0",
            "fortna_word": 100,
            "fortna_bit": 0,
            "direction": "I",
            "type": "1794-IB16",
            "bit_half": "low",
            "low_desc": "EP1",
            "configio_desc": "EP1",
        }
        enrich_channel_ownership(
            ch,
            machine="MSCRENOPICK",
            claims={"owners": {}, "conflicts": {}, "spare_channels": set()},
            adapter={"rio_name": "AENTR1"},
            module={"slot": 1, "data_index": 0, "direction": "I", "type": "1794-IB16"},
        )
        self.assertEqual(ch["owner_state"], OWNER_UNUSED_MAPPED)
        self.assertNotEqual(ch["owner_state"], OWNER_UNRESOLVED)
        self.assertTrue(ch.get("is_unused_mapped"))
        self.assertFalse(ch.get("unresolved"))
        self.assertFalse(ch.get("configio_occupied"))
        self.assertTrue(ch.get("configio_topology"))
        self.assertEqual(ch.get("owner_source"), "UNCLAIMED_HARDWARE_CHANNEL")
        self.assertEqual(ch.get("disposition"), "UNCLAIMED_HARDWARE_CHANNEL")

    def test_ep12_and_ep2_same_rule(self) -> None:
        for desc in ("EP12", "EP2"):
            ch = {
                "physical_address": f"AENTR2:I.Data[1].3",
                "fortna_word": 101,
                "fortna_bit": 3,
                "direction": "I",
                "type": "1794-IB16",
                "bit_half": "low",
                "low_desc": desc,
                "configio_desc": desc,
            }
            enrich_channel_ownership(
                ch,
                machine="MSCRENOPICK",
                claims={"owners": {}, "conflicts": {}, "spare_channels": set()},
                adapter={"rio_name": "AENTR2"},
                module={"slot": 2, "data_index": 1, "direction": "I", "type": "1794-IB16"},
            )
            self.assertEqual(ch["owner_state"], OWNER_UNUSED_MAPPED, desc)
            self.assertEqual(ch.get("owner_source"), "UNCLAIMED_HARDWARE_CHANNEL", desc)


if __name__ == "__main__":
    unittest.main()
