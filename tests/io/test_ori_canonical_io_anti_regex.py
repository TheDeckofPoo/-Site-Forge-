#!/usr/bin/env python3
"""Anti-regex: multiple raw address spellings normalize via hardware context.

Proves the implementation does NOT depend on literal prefixes such as
T_1794_AENT_*, CP3RIO*, or CP6RIO*. Adapter tokens are opaque; fixtures use
renamed device spellings while keeping the same hardware source structure.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_asc import write_asc  # noqa: E402
from fortna_canonical_io_discovery import (  # noqa: E402
    FAMILY_FLEX,
    FAMILY_POINT,
    PHYSICAL,
    RENDERABLE,
    REVIEW_REQUIRED,
    UNBACKED_ADDRESS_CANDIDATE,
    HardwareIoContext,
    build_io_source_index,
    endpoints_equal_ignoring_raw,
    normalize_raw_address,
    parse_address_structure,
)
from fortna_safety_endpoint_integrity import normalize_endpoint_key  # noqa: E402


class TestCanonicalIoAntiRegex(unittest.TestCase):
    def test_structure_parse_opaque_adapter_tokens(self) -> None:
        # Representative shapes — adapters deliberately NOT the mission examples.
        shapes = [
            ("WIDGET_IO_HEAD_9:I.Data[3].14", "LOGIX_DATA_MEMBER", 3, None, "I", 14),
            ("PANELX_BUS2:1:I.0", "COMPACT_SLOT_DIR_BIT", None, 1, "I", 0),
            ("ZZ_FLEX_NODE:6:I.1", "COMPACT_SLOT_DIR_BIT", None, 6, "I", 1),
        ]
        for raw, form, data, slot, direction, bit in shapes:
            st = parse_address_structure(raw)
            self.assertEqual(st.form, form, raw)
            self.assertEqual(st.direction, direction, raw)
            self.assertEqual(st.bit, bit, raw)
            self.assertEqual(st.data_index, data, raw)
            self.assertEqual(st.module_slot, slot, raw)

    def test_renamed_prefixes_same_canonical_endpoint(self) -> None:
        """Change raw device names; hardware structure holds endpoint identity."""
        hw = HardwareIoContext(
            controller="SITECTRL",
            panel="EP_A",
            adapter="RIO_CANON",  # hardware authority
            module_slot=6,
            module_type="1794-IA16",
            family=FAMILY_FLEX,
            bank_word=201,
            direction="I",
            bit=1,
            source_file="eipcfg",
            source_type="physical_word_map",
            confidence="HIGH",
        )
        # Three different opaque spellings of the SAME structural point.
        # Deliberately avoid mission-example literals as fixed strings.
        raws = [
            "ALPHA_HEAD_6:I.Data[5].1",  # Flex slot6 → Data[5]
            "BETA_NODE:6:I.1",  # compact slot form
            "GAMMA_X:I.Data[5].1",
        ]
        eps = [normalize_raw_address(r, hardware=hw) for r in raws]
        for ep, raw in zip(eps, raws):
            self.assertEqual(ep.classification, PHYSICAL, raw)
            self.assertEqual(ep.adapter, "RIO_CANON", raw)  # hardware wins
            self.assertEqual(ep.direction, "I", raw)
            self.assertEqual(ep.bit, 1, raw)
            self.assertEqual(ep.raw_address, raw)  # spelling preserved
            self.assertNotEqual(ep.raw_address, ep.adapter)
        # Pairwise equal ignoring raw
        self.assertTrue(endpoints_equal_ignoring_raw(eps[0], eps[1]))
        self.assertTrue(endpoints_equal_ignoring_raw(eps[1], eps[2]))
        # Renderable Logix uses hardware adapter, not raw token
        for ep in eps:
            self.assertEqual(ep.render_status, RENDERABLE)
            self.assertTrue(ep.rendered_logix.startswith("RIO_CANON:"))
            self.assertIn("Data[", ep.rendered_logix)

    def test_unfamiliar_opaque_spelling_is_review_not_drop(self) -> None:
        # Hardware proves physical I/O; raw spelling is opaque garbage.
        hw = HardwareIoContext(
            controller="SITECTRL",
            adapter="RIO_CANON",
            module_slot=1,
            module_type="1734-IB8",
            family=FAMILY_POINT,
            direction="I",
            bit=0,
            source_file="configio",
            source_type="physical_word_map",
            confidence="HIGH",
        )
        ep = normalize_raw_address("!!!not-a-known-syntax!!!", hardware=hw)
        self.assertEqual(ep.classification, PHYSICAL)
        self.assertEqual(ep.render_status, RENDERABLE)  # hardware enough to render
        self.assertEqual(ep.raw_address, "!!!not-a-known-syntax!!!")

    def test_physical_without_render_is_review_render(self) -> None:
        # Compact form without family → physical structure, render incomplete.
        ep = normalize_raw_address(
            "ANYTOKEN:3:O.2",
            hardware=HardwareIoContext(
                controller="X",
                adapter="ANYTOKEN",
                source_type="alias_record",
                confidence="MEDIUM",
            ),
        )
        self.assertEqual(ep.module_slot, 3)
        self.assertEqual(ep.direction, "O")
        self.assertEqual(ep.bit, 2)
        self.assertEqual(ep.classification, PHYSICAL)
        # No family → cannot finish Data[] render
        self.assertIn(ep.render_status, {REVIEW_REQUIRED, "REVIEW_REQUIRED"})

    def test_normalize_endpoint_key_accepts_compact_form(self) -> None:
        k1 = normalize_endpoint_key("Q_HEAD:I.Data[3].14")
        k2 = normalize_endpoint_key("q_head : i . data [ 3 ] . 14")
        self.assertEqual(k1, k2)
        k3 = normalize_endpoint_key("NODEZ:6:I.1")
        self.assertIn("6", k3)
        self.assertIn("I", k3)
        self.assertIn("1", k3)
        # Renamed adapter → different key (opaque token preserved when no hw)
        k4 = normalize_endpoint_key("OTHER:6:I.1")
        self.assertNotEqual(k3, k4)

    def test_syntax_alone_is_not_physical(self) -> None:
        """ORI-089: raw address spelling must not prove PHYSICAL by itself."""
        # Deliberately weird adapter token — parses, but no hardware provenance.
        ep = normalize_raw_address("T_1794_AENT_WEIRD:I.Data[1].0")
        self.assertEqual(ep.raw_address, "T_1794_AENT_WEIRD:I.Data[1].0")
        self.assertNotEqual(ep.classification, PHYSICAL)
        self.assertEqual(ep.classification, REVIEW_REQUIRED)
        self.assertIn(UNBACKED_ADDRESS_CANDIDATE, ep.notes)
        # Same structural parse with hardware context → PHYSICAL
        hw = HardwareIoContext(
            controller="SITECTRL",
            panel="EP1",
            adapter="RIO_CANON",
            module_slot=2,
            module_type="1794-IB16",
            family=FAMILY_FLEX,
            direction="I",
            bit=0,
            source_file="eipcfg",
            source_type="physical_word_map",
            confidence="HIGH",
        )
        ep2 = normalize_raw_address("T_1794_AENT_WEIRD:I.Data[1].0", hardware=hw)
        self.assertEqual(ep2.classification, PHYSICAL)
        self.assertEqual(ep2.adapter, "RIO_CANON")  # hardware wins
        self.assertEqual(ep2.raw_address, "T_1794_AENT_WEIRD:I.Data[1].0")

    def test_source_index_conservation_synthetic(self) -> None:
        """Minimal RUN: index conserves physical evidence rows."""
        with tempfile.TemporaryDirectory() as td:
            run = Path(td) / "RUN"
            fortna = run / "FORTNA"
            fortna.mkdir(parents=True)
            (run / "project.cfg").write_text(
                "MACHINENAME = SITECTRL\nPROJECTNAME = Synth\n",
                encoding="utf-8",
            )
            # Empty conveyor — index still returns conservation structure
            write_asc(
                fortna / "Conveyor.asc",
                [
                    "IO_Name",
                    "General_Description",
                    "IO_Address_Word",
                    "IO_Address_Bit",
                    "Device_Description",
                    "Part_Number",
                    "IO_Module_Type",
                    "Type",
                    "Machine_Name",
                    "Motor",
                    "Drive",
                    "X_cord",
                    "Y_cord",
                    "Length",
                    "Angle",
                    "Width",
                ],
                [],
            )
            idx = build_io_source_index(run, "SITECTRL")
            self.assertIn("conservation_ok", idx)
            self.assertTrue(idx["policy"]["source_hardware_semantics_gt_tag_spelling"])
            self.assertTrue(idx["policy"]["unfamiliar_syntax_is_review_not_drop"])
            self.assertEqual(
                idx["discovered_total"],
                idx["accounted_total"],
            )


if __name__ == "__main__":
    unittest.main()
