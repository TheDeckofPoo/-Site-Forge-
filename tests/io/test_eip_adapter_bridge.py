#!/usr/bin/env python3
"""Exact EIPAdapters TargetIP bridge — no site specials."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_eip_adapter_bridge import (  # noqa: E402
    build_adapter_bridges,
    load_eipadapters_rows,
)
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    parse_eipcfg,
)
from fortna_rack_discovery import discover_racks  # noqa: E402

MSCATL = ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"
ORINDY = ROOT / "workspace" / "_virgin_orindy" / "RUN"
PICK = (
    ROOT
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
    / "RUN"
)


class TestExactAdapterBridge(unittest.TestCase):
    @unittest.skipUnless((MSCATL / "project.cfg").is_file(), "missing")
    def test_atlanta_exact_ip_bridge_proven(self) -> None:
        topo = parse_eipcfg(MSCATL, "MSCATL_CP3")
        stats = topo.get("adapter_bridge_stats") or {}
        self.assertEqual(stats.get("proven_bridge"), 3)
        self.assertEqual(stats.get("substring_fallback"), 0)
        joins = {
            m.get("bank_join")
            for a in topo["adapters"]
            for m in (a.get("modules") or [])
            if m.get("bank_join")
        }
        self.assertEqual(joins, {"exact_ip_bridge"})

    @unittest.skipUnless((MSCATL / "project.cfg").is_file(), "missing")
    def test_atlanta_claims_proven_not_derived(self) -> None:
        r = PhysicalWordResolver(MSCATL, "MSCATL_CP3")
        hit = r.resolve(700, 0)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.get("channel"), "T_1794_AENT_1:I.Data[0].0")
        self.assertEqual(hit.get("bank_join"), "exact_ip_bridge")
        self.assertEqual(hit.get("binding_confidence"), "PROVEN")

    @unittest.skipUnless((MSCATL / "project.cfg").is_file(), "missing")
    def test_atlanta_rack_bank_binding_proven(self) -> None:
        d = discover_racks(MSCATL, "MSCATL_CP3")
        self.assertEqual(d["stats"]["rack_count"], 3)
        for rack in d["racks"]:
            for m in rack.get("modules") or []:
                self.assertEqual(m.get("placement_status"), "PROVEN")
                self.assertEqual(m.get("bank_binding_status"), "PROVEN")

    @unittest.skipUnless((ORINDY / "project.cfg").is_file(), "missing")
    def test_indy_exact_bridge(self) -> None:
        topo = parse_eipcfg(ORINDY, "ORINDYAC6")
        stats = topo.get("adapter_bridge_stats") or {}
        self.assertGreaterEqual(stats.get("proven_bridge") or 0, 4)

    @unittest.skipUnless((PICK / "project.cfg").is_file(), "missing")
    def test_reno_polluted_ip_not_forced_proven_bridge(self) -> None:
        """PICK EIPAdapters IPs disagree with eipcfg — bridge must not fake PROVEN."""
        rows = load_eipadapters_rows(PICK, "MSCRENOPICK")
        topo = parse_eipcfg(PICK, "MSCRENOPICK")
        stats = topo.get("adapter_bridge_stats") or {}
        # Exact IP bridge should not succeed for polluted ASC→eipcfg IPs
        self.assertEqual(stats.get("proven_bridge") or 0, 0)
        bridges = stats.get("bridges") or {}
        if bridges:
            self.assertTrue(
                any(
                    (b.get("match_stage_2") == "NO_IP_MATCH")
                    for b in bridges.values()
                )
            )
        self.assertTrue(any(r.get("name", "").startswith("AENTR") for r in rows))

    def test_bridge_builder_unique_ip(self) -> None:
        bridges = build_adapter_bridges(
            eipmodules_adapter_names=["ADAP-1-LOGICAL"],
            eipadapters_rows=[{"name": "ADAP-1-LOGICAL", "target_ip": "10.0.0.1"}],
            eipcfg_adapters=[{"name": "ADAP-1", "targetip": "10.0.0.1"}],
        )
        ev = bridges["ADAP-1-LOGICAL"]
        self.assertEqual(ev.status, "PROVEN")
        self.assertEqual(ev.match_stage_1, "EXACT_NAME")
        self.assertEqual(ev.match_stage_2, "EXACT_IP")
        self.assertEqual(ev.eipcfg_adapter_name, "ADAP-1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
