#!/usr/bin/env python3
"""R11/R12: sealed AOI Parameters for ORI-081 + EncodedData merge.

R11 — ORI-081 must treat sealed AOI Parameters as members of AOI-instance tags
      (e.g. OTE(Induct.O_Token_Found_Ack) where Induct:TRK_Induct_TokenUpdate).

R12 — _merge_named_blocks must retain sealed EncodedData AOI definitions so
      Wave/TRK AOIs from program packs are not silently dropped; Wave AOI must
      be loadable from the approved library path.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_autogen import (  # noqa: E402
    _merge_named_blocks,
    _parse_l5x_udt_members,
    validate_bit_writers_scoped,
)
from fortna_sorter_build import WAVE_AOI_PATH, load_wave_aoi_xml  # noqa: E402


class TestR11SealedAoiParametersOri081(unittest.TestCase):
    def test_parse_indexes_sealed_aoi_parameters(self) -> None:
        xml = """
        <Controller Name="C1">
          <EncodedData EncodedType="AddOnInstructionDefinition" Name="TRK_Induct_TokenUpdate"
                       Revision="1.2" SignatureID="58B0490C">
            <Parameters>
              <Parameter Name="EnableIn" DataType="BOOL" Usage="Input"/>
              <Parameter Name="O_Token_Found_Ack" DataType="BOOL" Usage="Output"/>
            </Parameters>
            <Data>SEALED_BLOB</Data>
          </EncodedData>
        </Controller>
        """
        mems = _parse_l5x_udt_members(xml)
        aoi = mems.get("TRK_INDUCT_TOKENUPDATE") or {}
        self.assertIn("O_TOKEN_FOUND_ACK", aoi)
        self.assertEqual(aoi["O_TOKEN_FOUND_ACK"].upper(), "BOOL")

    def test_parse_indexes_name_before_encodedtype(self) -> None:
        xml = """
        <EncodedData Name="TRK_Divert_WaveFunction" EncodedType="AddOnInstructionDefinition"
                     SignatureID="464B725A">
          <Parameters>
            <Parameter Name="i_xEncPPI" DataType="BOOL" Usage="Input"/>
            <Parameter Name="i_xDivertInput" DataType="BOOL" Usage="Input"/>
          </Parameters>
        </EncodedData>
        """
        mems = _parse_l5x_udt_members(xml)
        aoi = mems.get("TRK_DIVERT_WAVEFUNCTION") or {}
        self.assertIn("I_XENCPPI", aoi)
        self.assertIn("I_XDIVERTINPUT", aoi)

    def test_ori081_aoi_instance_parameter_ote_passes(self) -> None:
        """Controller OTE on AOI-instance Parameter must PASS (Patch ORI-081 repro)."""
        l5x = """
        <Controller Name="C1">
          <AddOnInstructionDefinitions>
            <EncodedData EncodedType="AddOnInstructionDefinition" Name="TRK_Induct_TokenUpdate">
              <Parameters>
                <Parameter Name="EnableIn" DataType="BOOL" Usage="Input"/>
                <Parameter Name="EnableOut" DataType="BOOL" Usage="Output"/>
                <Parameter Name="O_Token_Found_Ack" DataType="BOOL" Usage="Output"/>
              </Parameters>
            </EncodedData>
          </AddOnInstructionDefinitions>
          <Tags>
            <Tag Name="P504_Induct" DataType="TRK_Induct_TokenUpdate"/>
            <Tag Name="Ready" DataType="BOOL"/>
          </Tags>
          <Programs>
            <Program Name="Sorter_Track">
              <Tags></Tags>
              <Routines>
                <Routine Name="Main" Type="RLL">
                  <RLLContent>
                    <Rung Number="0" Type="N">
                      <Text><![CDATA[XIC(Ready)OTE(P504_Induct.O_Token_Found_Ack);]]></Text>
                    </Rung>
                  </RLLContent>
                </Routine>
              </Routines>
            </Program>
          </Programs>
        </Controller>
        """
        res = validate_bit_writers_scoped(l5x)
        self.assertTrue(res["ok"], res.get("failure_messages"))
        self.assertEqual(res["report_fields"]["invalid_bit_writer_no_member"], [])

    def test_ori081_still_fails_unknown_aoi_member(self) -> None:
        l5x = """
        <Controller Name="C1">
          <EncodedData EncodedType="AddOnInstructionDefinition" Name="TRK_Induct_TokenUpdate">
            <Parameters>
              <Parameter Name="O_Token_Found_Ack" DataType="BOOL" Usage="Output"/>
            </Parameters>
          </EncodedData>
          <Tags>
            <Tag Name="P504_Induct" DataType="TRK_Induct_TokenUpdate"/>
          </Tags>
          <Programs>
            <Program Name="P1">
              <Routines>
                <Routine Name="Main" Type="RLL">
                  <RLLContent>
                    <Rung Number="0" Type="N">
                      <Text><![CDATA[OTE(P504_Induct.NoSuchMember);]]></Text>
                    </Rung>
                  </RLLContent>
                </Routine>
              </Routines>
            </Program>
          </Programs>
        </Controller>
        """
        res = validate_bit_writers_scoped(l5x)
        self.assertFalse(res["ok"])
        self.assertTrue(
            any("NoSuchMember" in x for x in res["report_fields"]["invalid_bit_writer_no_member"])
        )


class TestR12SealedAoiMergeAndWavePath(unittest.TestCase):
    def test_merge_keeps_sealed_encoded_aoi(self) -> None:
        host = "<AddOnInstructionDefinitions>\n</AddOnInstructionDefinitions>"
        sealed = (
            '<EncodedData EncodedType="AddOnInstructionDefinition" '
            'Name="TRK_Divert_WaveFunction" SignatureID="464B725A">'
            "<Parameters>"
            '<Parameter Name="i_xEncPPI" DataType="BOOL"/>'
            "</Parameters>"
            "</EncodedData>"
        )
        merged = _merge_named_blocks(
            host,
            [sealed],
            "AddOnInstructionDefinitions",
            "AddOnInstructionDefinition",
        )
        self.assertIn("TRK_Divert_WaveFunction", merged)
        self.assertIn("EncodedData", merged)
        self.assertIn("464B725A", merged)

    def test_merge_skips_duplicate_sealed_already_in_host(self) -> None:
        host = (
            "<AddOnInstructionDefinitions>\n"
            '<EncodedData EncodedType="AddOnInstructionDefinition" '
            'Name="TRK_Divert_WaveFunction" SignatureID="AAAA"/>'
            "<Parameters/>"
            "</EncodedData>\n"
            "</AddOnInstructionDefinitions>"
        )
        sealed = (
            '<EncodedData EncodedType="AddOnInstructionDefinition" '
            'Name="TRK_Divert_WaveFunction" SignatureID="BBBB">'
            "<Parameters/>"
            "</EncodedData>"
        )
        merged = _merge_named_blocks(
            host,
            [sealed],
            "AddOnInstructionDefinitions",
            "AddOnInstructionDefinition",
        )
        self.assertEqual(merged.count("TRK_Divert_WaveFunction"), 1)
        self.assertIn("AAAA", merged)
        self.assertNotIn("BBBB", merged)

    def test_merge_name_before_encodedtype_order(self) -> None:
        host = "<AddOnInstructionDefinitions>\n</AddOnInstructionDefinitions>"
        sealed = (
            '<EncodedData Name="TRK_Pointer" EncodedType="AddOnInstructionDefinition">'
            "<Parameters>"
            '<Parameter Name="EnableIn" DataType="BOOL"/>'
            "</Parameters>"
            "</EncodedData>"
        )
        merged = _merge_named_blocks(
            host,
            [sealed],
            "AddOnInstructionDefinitions",
            "AddOnInstructionDefinition",
        )
        self.assertIn('Name="TRK_Pointer"', merged)

    def test_wave_aoi_approved_library_path_loads(self) -> None:
        self.assertTrue(
            WAVE_AOI_PATH.is_file(),
            f"Wave AOI missing at approved path: {WAVE_AOI_PATH}",
        )
        xml = load_wave_aoi_xml()
        self.assertTrue(xml, "load_wave_aoi_xml returned empty")
        self.assertIn("TRK_Divert_WaveFunction", xml)
        self.assertRegex(xml.upper(), r"464B[_]?725A")


if __name__ == "__main__":
    unittest.main()
