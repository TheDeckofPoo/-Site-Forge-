#!/usr/bin/env python3
"""Family-neutral PhysicalEndpoint + 1734/1794 renderers.

Sanitized expectations are derived from MSCRENOPACK RUN evidence
(Configio + eipcfg + Conveyor.asc), NOT from any finished L5X oracle.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_SF_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SF_REPO / "tools" / "scripts"))

from fortna_physical_endpoint import (  # noqa: E402
    PhysicalEndpoint,
    assert_family_render_rules,
    physical_endpoint_from_hit,
    render_flex_channel,
    render_point_channel,
    render_rockwell_channel,
)
from fortna_hardware_family import FAMILY_FLEX, FAMILY_POINT  # noqa: E402

PACK_RUN = (
    _SF_REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPACK-RUN"
    / "RUN"
)

# RUN-derived acceptance cases (Conveyor.asc words + Configio/eipcfg → AENTR13).
# These mirror known-good Autogen addressing patterns without reading finished L5X.
PACK_RUN_CASES = (
    # device, fortna_word, fortna_bit, expected_channel
    ("PE514_P", 100, 0, "AENTR13:I.Data[1].0"),
    ("13MCR1", 105, 10, "AENTR13:O.Data[12].0"),
    ("M7", 106, 10, "AENTR13:O.Data[14].0"),
)


class TestFamilyRenderRules(unittest.TestCase):
    def test_point_vs_flex_data_index(self) -> None:
        assert_family_render_rules()
        self.assertEqual(render_point_channel("AENTR13", 1, "I", 0), "AENTR13:I.Data[1].0")
        self.assertNotEqual(
            render_point_channel("X", 1, "I", 0),
            render_flex_channel("X", 1, "I", 0),
        )

    def test_physical_endpoint_renderer_dispatch(self) -> None:
        ep_point = PhysicalEndpoint(
            machine="MSCRENOPACK",
            adapter="AENTR13",
            slot=1,
            direction="I",
            module_bit=0,
            module_type="1734-IB8",
            family=FAMILY_POINT,
        )
        self.assertEqual(render_rockwell_channel(ep_point), "AENTR13:I.Data[1].0")
        ep_flex = PhysicalEndpoint(
            machine="ORNCCP5",
            adapter="CP5RIO0",
            slot=2,
            direction="I",
            module_bit=0,
            module_type="1794-IA16",
            family=FAMILY_FLEX,
        )
        self.assertEqual(render_rockwell_channel(ep_flex), "CP5RIO0:I.Data[1].0")


@unittest.skipUnless((PACK_RUN / "project.cfg").is_file(), "MSCRENOPACK RUN missing")
class TestPackRunPointEndpoints(unittest.TestCase):
    """Prove current resolver reproduces RUN-derived POINT endpoints."""

    @classmethod
    def setUpClass(cls) -> None:
        from fortna_physical_word_resolver import build_physical_word_map

        cls.pm = build_physical_word_map(PACK_RUN, "MSCRENOPACK")

    def test_pack_run_cases(self) -> None:
        from fortna_physical_word_resolver import resolve_word_bit

        for device, word, bit, expected in PACK_RUN_CASES:
            with self.subTest(device=device):
                hit = resolve_word_bit(self.pm, word, bit)
                self.assertIsNotNone(hit, f"{device} word={word} bit={bit} unresolved")
                ep = physical_endpoint_from_hit(hit, machine="MSCRENOPACK")
                self.assertIsNotNone(ep)
                self.assertEqual(ep.family, FAMILY_POINT)
                channel = render_rockwell_channel(ep)
                self.assertEqual(channel, expected)
                # Hit channel string must agree with family renderer
                self.assertEqual(str(hit.get("channel") or ""), expected)

    def test_aentr13_is_real_adapter_identity(self) -> None:
        rios = set((self.pm.get("stats") or {}).get("rio_names") or [])
        self.assertIn("AENTR13", rios)
        # Must not confuse AENTR1 slot 3 with adapter AENTR13
        self.assertIn("AENTR3", rios)


if __name__ == "__main__":
    unittest.main(verbosity=2)
