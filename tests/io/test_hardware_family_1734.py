#!/usr/bin/env python3
"""Regression: 1734 POINT I/O family must not enter the 1794 FLEX path.

Proves:
  - family detection (1734-* → POINT, 1794-* → FLEX)
  - adapter identity preserved
  - slot / catalog / direction preserved
  - data_index does NOT apply Flex slot-1 shift to POINT
  - physical_map_to_topology keeps family=1734
  - unsupported POINT catalog blocks with precise error (no 1794 sub)
  - HardwareIOModel exposes family + point renderer id
"""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# Prefer canonical names used by existing tests:
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---


import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_hardware_family import (  # noqa: E402
    FAMILY_FLEX,
    FAMILY_POINT,
    assert_no_family_substitution,
    compiler_supports_catalog,
    data_index_for_module,
    detect_family_from_catalog,
    detect_family_from_types,
    renderer_for_family,
)
from fortna_physical_word_resolver import (  # noqa: E402
    _data_index_for_module,
    parse_eipcfg,
    physical_map_to_topology,
)


def _write_point_eipcfg(path: Path) -> None:
    """Minimal 1734-AENTR + POINT modules — synthetic fixture, not site evidence."""
    root = ET.Element("EIPConfig")
    ad = ET.SubElement(
        root,
        "Adapter",
        name="AENTR1",
        targetip="192.168.1.10",
        InputAddress="0",
        OutputAddress="0",
    )
    ET.SubElement(
        ad,
        "Module",
        name="AENTR1",
        type="1734-AENTR",
        slot="0",
        connection="HEADNODE",
    )
    ET.SubElement(
        ad,
        "Module",
        name="IB8-1",
        type="1734-IB8",
        slot="1",
        connection="EXCLUSIVEOWNER",
    )
    ET.SubElement(
        ad,
        "Module",
        name="OB8E-2",
        type="1734-OB8E",
        slot="2",
        connection="EXCLUSIVEOWNER",
    )
    ET.SubElement(
        ad,
        "Module",
        name="IA4-3",
        type="1734-IA4",
        slot="3",
        connection="EXCLUSIVEOWNER",
    )
    path.write_text(
        '<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode"),
        encoding="utf-8",
    )


class TestHardwareFamily1734(unittest.TestCase):
    def test_family_detection(self):
        self.assertEqual(detect_family_from_catalog("1734-AENTR"), FAMILY_POINT)
        self.assertEqual(detect_family_from_catalog("1734-IB8"), FAMILY_POINT)
        self.assertEqual(detect_family_from_catalog("1794-IA16"), FAMILY_FLEX)
        self.assertEqual(detect_family_from_catalog("1794-AENT"), FAMILY_FLEX)
        self.assertEqual(
            detect_family_from_types(["1734-AENTR", "1734-IB8"]), FAMILY_POINT
        )
        self.assertEqual(
            detect_family_from_types(["1794-AENT", "1794-IA16"]), FAMILY_FLEX
        )
        # POINT evidence must win — never translate to FLEX
        self.assertEqual(
            detect_family_from_types(["1794-IA16", "1734-IB8"]), FAMILY_POINT
        )

    def test_data_index_no_flex_shift_for_point(self):
        self.assertEqual(data_index_for_module(2, FAMILY_FLEX), 1)  # Flex slot-1
        self.assertEqual(data_index_for_module(2, FAMILY_POINT), 2)  # POINT raw
        self.assertEqual(_data_index_for_module(2, "1734"), 2)
        self.assertEqual(_data_index_for_module(2, "1794"), 1)

    def test_no_family_substitution(self):
        assert_no_family_substitution("1734-IB8", "1734-IB8/C")
        with self.assertRaises(ValueError):
            assert_no_family_substitution("1734-IB8", "1794-IA16")

    def test_unsupported_point_catalog_blocks(self):
        ok, reason = compiler_supports_catalog("1734-IB8")
        self.assertTrue(ok)
        ok, reason = compiler_supports_catalog("1734-XYZ99")
        self.assertFalse(ok)
        self.assertIn("Unsupported POINT I/O catalog", reason)
        self.assertIn("1734-XYZ99", reason)
        # Must NOT mention 1794 substitution
        self.assertNotIn("1794", reason)

    def test_renderer_ids(self):
        self.assertEqual(renderer_for_family(FAMILY_POINT), "point")
        self.assertEqual(renderer_for_family(FAMILY_FLEX), "flex")

    def test_eipcfg_fixture_preserves_point_identity(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td) / "RUN"
            fortna = run / "FORTNA"
            fortna.mkdir(parents=True)
            # Minimal project.cfg so machine resolution does not fail hard
            (run / "project.cfg").write_text(
                "[project]\nmachine_name=POINTTEST\n", encoding="utf-8"
            )
            eip = fortna / "POINTTEST-RTA-eipcfg.xml"
            _write_point_eipcfg(eip)

            topo = parse_eipcfg(run, "POINTTEST")
            adapters = topo.get("adapters") or []
            self.assertEqual(len(adapters), 1)
            ad = adapters[0]
            self.assertEqual(ad.get("family"), FAMILY_POINT)
            mods = ad.get("modules") or []
            cats = [m.get("type") for m in mods]
            self.assertIn("1734-AENTR", cats)
            self.assertIn("1734-IB8", cats)
            self.assertIn("1734-OB8E", cats)
            for m in mods:
                self.assertEqual(m.get("family"), FAMILY_POINT)
                # No Flex slot-1 shift on POINT bridged modules
                slot = int(m.get("slot") or 0)
                if "AENT" not in (m.get("type") or "").upper():
                    self.assertEqual(int(m.get("data_index")), slot)

            # Build a physical_map-like adapters blob and convert to autogen topo
            pm = {
                "adapters": [
                    {
                        "name": ad.get("name"),
                        "rio_name": "AENTR1",
                        "targetip": ad.get("targetip"),
                        "panel": "CP1",
                        "family": FAMILY_POINT,
                        "modules": mods,
                    }
                ]
            }
            eip_topo = physical_map_to_topology(pm)
            self.assertEqual(len(eip_topo), 1)
            self.assertEqual(eip_topo[0]["family"], FAMILY_POINT)
            for c in eip_topo[0]["children"]:
                self.assertEqual(c["family"], FAMILY_POINT)
                self.assertTrue(str(c["type"]).startswith("1734"))
                self.assertFalse(str(c["type"]).startswith("1794"))
                # Slot preserved — POINT flex_slot == eip_slot
                self.assertEqual(c["flex_slot"], c["eip_slot"])

    def test_autogen_blocks_unsupported_point_child(self):
        from fortna_autogen import _require_supported_eip_child, _unsupported_point_catalog_error

        err = _require_supported_eip_child("1734-XYZ99", "1734")
        self.assertIsNotNone(err)
        self.assertIn("Unsupported POINT I/O catalog", err)
        self.assertEqual(
            _unsupported_point_catalog_error("1734-XYZ99"),
            "Unsupported POINT I/O catalog:\n1734-XYZ99",
        )
        self.assertIsNone(_require_supported_eip_child("1734-IB8", "1734"))


class TestHardwareIoModel1734Synthetic(unittest.TestCase):
    """HardwareIOModel path with synthetic POINT eipcfg (no Configio words required)."""

    def test_model_exposes_point_family_and_renderer(self):
        from fortna_hardware_io_model import build_hardware_io_model

        with tempfile.TemporaryDirectory() as td:
            run = Path(td) / "RUN"
            fortna = run / "FORTNA"
            fortna.mkdir(parents=True)
            (run / "project.cfg").write_text(
                "[project]\nmachine_name=POINTTEST\n", encoding="utf-8"
            )
            _write_point_eipcfg(fortna / "POINTTEST-RTA-eipcfg.xml")
            # Empty Configio so panel packing still yields adapters from eipcfg
            (fortna / "Configio.asc").write_text(
                "Octal_Word\tDesc\tIn_Out\tInterface\n", encoding="utf-8"
            )

            model = build_hardware_io_model(run, "POINTTEST")
            self.assertTrue(model.get("ok"))
            adapters = model.get("adapters") or []
            self.assertTrue(adapters, "expected POINT adapter in model")
            ad = adapters[0]
            self.assertEqual(ad.get("family"), FAMILY_POINT)
            self.assertEqual(ad.get("renderer"), "point")
            cats = [m.get("catalog") or m.get("type") for m in (ad.get("modules") or [])]
            self.assertTrue(any(str(c).startswith("1734") for c in cats))
            self.assertFalse(any(str(c).startswith("1794") for c in cats))
            # Families list on controller
            fams = model.get("controller", {}).get("hardware_families") or []
            self.assertIn(FAMILY_POINT, fams)


if __name__ == "__main__":
    unittest.main()
