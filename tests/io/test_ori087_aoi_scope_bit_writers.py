#!/usr/bin/env python3
"""ORI-087: static bit-writer validator must be AOI-scope aware.

Legal AOI-local BOOL parameters/locals (including EN/DN/ER-style symbols when
declared on the AOI) must PASS. Undeclared AOI names, AOI UDT roots, and
ordinary routine UDT-root OTEs must still FAIL. No special-casing of
AOI_SNTP_QUERY / Trigger_Update_Now / EN / DN / ER.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_autogen import validate_bit_writers_scoped  # noqa: E402


def _aoi_xml(
    name: str,
    *,
    params: list[tuple[str, str]],
    locals_: list[tuple[str, str]] | None = None,
    logic: str,
) -> str:
    param_xml = "".join(
        f'<Parameter Name="{n}" DataType="{dt}" TagType="Base" '
        f'Usage="Input" Required="false" Visible="true"/>'
        for n, dt in params
    )
    local_xml = "".join(
        f'<LocalTag Name="{n}" DataType="{dt}" TagType="Base" '
        f'ExternalAccess="Read/Write"/>'
        for n, dt in (locals_ or [])
    )
    return f"""
    <AddOnInstructionDefinition Name="{name}" Revision="0.1">
      <Parameters>{param_xml}</Parameters>
      <LocalTags>{local_xml}</LocalTags>
      <Routines>
        <Routine Name="Logic" Type="RLL">
          <RLLContent>
            <Rung Number="0" Type="N">
              <Text><![CDATA[{logic}]]></Text>
            </Rung>
          </RLLContent>
        </Routine>
      </Routines>
    </AddOnInstructionDefinition>
    """


class TestOri087AoiScopeBitWriters(unittest.TestCase):
    def test_aoi_bool_input_xic_and_output_ote_ok(self) -> None:
        l5x = f"""
        <Controller Name="C1">
        {_aoi_xml(
            "AOI_GENERIC_PACK",
            params=[
                ("EnableIn", "BOOL"),
                ("EnableOut", "BOOL"),
                ("Cmd_Go", "BOOL"),
                ("Sts_Done", "BOOL"),
            ],
            logic="XIC(Cmd_Go)OTE(Sts_Done);",
        )}
        <Tags>
          <Tag Name="CtrlBool" DataType="BOOL"/>
        </Tags>
        </Controller>
        """
        res = validate_bit_writers_scoped(l5x)
        self.assertTrue(res["ok"], res.get("failure_messages"))
        self.assertEqual(res["report_fields"]["invalid_bit_writer_undeclared_aoi"], [])
        self.assertEqual(res["report_fields"]["invalid_udt_root_ote_count"], 0)

    def test_aoi_local_en_dn_er_style_bools_ok(self) -> None:
        """EN/DN/ER pass only because they are AOI parameters — not name special-cases."""
        l5x = f"""
        <Controller Name="C1">
        {_aoi_xml(
            "AOI_TIMEY_QUERY",
            params=[
                ("EnableIn", "BOOL"),
                ("EnableOut", "BOOL"),
                ("Trigger_Update_Now", "BOOL"),
                ("EN", "BOOL"),
                ("DN", "BOOL"),
                ("ER", "BOOL"),
            ],
            logic=(
                "XIC(EnableIn)OTE(Trigger_Update_Now);"
                "OTE(EN);OTE(DN);OTE(ER);"
            ),
        )}
        </Controller>
        """
        res = validate_bit_writers_scoped(l5x)
        self.assertTrue(res["ok"], res.get("failure_messages"))
        undecl = res["report_fields"]["invalid_bit_writer_undeclared"]
        self.assertEqual(undecl, [])
        # Confirm findings resolved from AOI scope, not controller
        aoi_hits = [
            f
            for f in res["findings"]
            if f["containing_object_type"] == "AOI_DEFINITION"
            and f["operand"] in {"Trigger_Update_Now", "EN", "DN", "ER"}
        ]
        self.assertGreaterEqual(len(aoi_hits), 4)
        for f in aoi_hits:
            self.assertEqual(f["status"], "OK")
            self.assertEqual(f["resolved_symbol_source"], "scope_local")

    def test_undeclared_aoi_local_fails(self) -> None:
        l5x = f"""
        <Controller Name="C1">
        {_aoi_xml(
            "AOI_GENERIC_PACK",
            params=[("EnableIn", "BOOL"), ("EnableOut", "BOOL")],
            logic="OTE(NotDeclaredHere);",
        )}
        </Controller>
        """
        res = validate_bit_writers_scoped(l5x)
        self.assertFalse(res["ok"])
        self.assertIn(
            "NotDeclaredHere",
            res["report_fields"]["invalid_bit_writer_undeclared_aoi"],
        )

    def test_aoi_udt_root_ote_fails(self) -> None:
        l5x = f"""
        <Controller Name="C1">
        <DataType Name="ES_UDT"><Members>
          <Member Name="I" DataType="ES_I"/>
        </Members></DataType>
        <DataType Name="ES_I"><Members>
          <Member Name="ES_OK" DataType="BIT"/>
        </Members></DataType>
        {_aoi_xml(
            "AOI_GENERIC_PACK",
            params=[("EnableIn", "BOOL"), ("SafetyBlob", "ES_UDT")],
            logic="OTE(SafetyBlob);",
        )}
        </Controller>
        """
        res = validate_bit_writers_scoped(l5x)
        self.assertFalse(res["ok"])
        self.assertIn("SafetyBlob", res["report_fields"]["invalid_udt_root_otes"])

    def test_aoi_nonexistent_member_fails(self) -> None:
        l5x = f"""
        <Controller Name="C1">
        <DataType Name="ES_UDT"><Members>
          <Member Name="I" DataType="ES_I"/>
        </Members></DataType>
        <DataType Name="ES_I"><Members>
          <Member Name="ES_OK" DataType="BIT"/>
        </Members></DataType>
        {_aoi_xml(
            "AOI_GENERIC_PACK",
            params=[("EnableIn", "BOOL"), ("SafetyBlob", "ES_UDT")],
            logic="OTE(SafetyBlob.I.NoSuch);",
        )}
        </Controller>
        """
        res = validate_bit_writers_scoped(l5x)
        self.assertFalse(res["ok"])
        self.assertTrue(
            any("NoSuch" in x for x in res["report_fields"]["invalid_bit_writer_no_member"])
        )

    def test_ordinary_routine_udt_root_still_fails(self) -> None:
        l5x = """
        <Controller Name="C1">
        <DataType Name="ES_UDT"><Members>
          <Member Name="I" DataType="ES_I"/>
        </Members></DataType>
        <DataType Name="ES_I"><Members>
          <Member Name="ES_OK" DataType="BIT"/>
        </Members></DataType>
        <Tags>
          <Tag Name="ESPB24" DataType="ES_UDT"/>
          <Tag Name="OKBit" DataType="BOOL"/>
        </Tags>
        <Programs>
          <Program Name="IO_MAP">
            <Tags/>
            <Routines>
              <Routine Name="CP_O" Type="RLL">
                <RLLContent>
                  <Rung Number="0" Type="N">
                    <Text><![CDATA[XIC(OKBit)OTE(ESPB24);]]></Text>
                  </Rung>
                  <Rung Number="1" Type="N">
                    <Text><![CDATA[OTE(ESPB24.I.ES_OK);]]></Text>
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
        self.assertIn("ESPB24", res["report_fields"]["invalid_udt_root_otes"])
        # Member form remains OK
        ok_ops = [f for f in res["findings"] if f["operand"] == "ESPB24.I.ES_OK"]
        self.assertEqual(ok_ops[0]["status"], "OK")

    def test_warden_ori087_reduced_reproducer(self) -> None:
        """Reduced reproducer matching Warden AOI-local false-positive class."""
        # Pull real AOI_SNTP_QUERY body OTEs from library when present; otherwise
        # synthesize an equivalent anonymous AOI with the same parameter shapes.
        lib = _SF_REPO / "tools" / "libraries" / "OReilly_Library_v3.L5X"
        if lib.is_file():
            text = lib.read_text(encoding="utf-8", errors="replace")
            m = re.search(
                r'<AddOnInstructionDefinition[^>]*Name="AOI_SNTP_QUERY".*?'
                r"</AddOnInstructionDefinition>",
                text,
                flags=re.I | re.S,
            )
            self.assertIsNotNone(m)
            l5x = f"<Controller Name=\"C1\">{m.group(0)}</Controller>"
        else:
            l5x = f"""
            <Controller Name="C1">
            {_aoi_xml(
                "AOI_CLOCK_QUERY",
                params=[
                    ("EnableIn", "BOOL"),
                    ("EnableOut", "BOOL"),
                    ("Trigger_Update_Now", "BOOL"),
                    ("EN", "BOOL"),
                    ("DN", "BOOL"),
                    ("ER", "BOOL"),
                ],
                logic="OTE(Trigger_Update_Now);OTE(EN);OTE(DN);OTE(ER);",
            )}
            </Controller>
            """
        res = validate_bit_writers_scoped(l5x)
        aoi_undecl = res["report_fields"]["invalid_bit_writer_undeclared_aoi"]
        # The ORI-087 defect class: these must NOT be reported undeclared.
        for sym in ("Trigger_Update_Now", "EN", "DN", "ER"):
            self.assertNotIn(sym, aoi_undecl, msg=f"{sym} falsely undeclared")
        # No UDT-root regressions from the AOI body itself for these BOOL params
        for sym in ("Trigger_Update_Now", "EN", "DN", "ER"):
            self.assertNotIn(sym, res["report_fields"]["invalid_udt_root_otes"])


class TestOri088LocalEquipmentAccounting(unittest.TestCase):
    def test_p105a_review_withheld_and_ssv_intentional(self) -> None:
        from fortna_autogen import account_local_active_equipment

        # Discovery-style lane list
        lea = account_local_active_equipment(
            generated_conveyors={"P1", "P2", "P3", "P4", "P128", "P1001"},
            merges=[
                {
                    "name": "P1001-P105A",
                    "classification": "REVIEW_REQUIRED",
                    "discharge": "",
                    "lanes": [
                        {"input_name": "P1001", "section": "P1001"},
                        {"input_name": "P105A", "section": "P105A"},
                    ],
                }
            ],
            merges_withheld=["P1001-P105A"],
            local_active_tags=["P1", "P2", "P3", "P4", "P128", "P1001", "P105A"],
            io_points=[{"device_name": "SSV105A", "direction": "O"}],
            section_ids=["P1001", "P105A"],
        )
        self.assertEqual(
            lea["by_tag"]["P105A"]["classification"], "REVIEW_WITHHELD"
        )
        self.assertEqual(lea["by_tag"]["P1"]["classification"], "GENERATED_LOCAL")
        self.assertIn("SSV105A", lea["ssv_intentional_review"])
        self.assertEqual(lea["ssv_classifications"]["SSV105A"], "INTENTIONAL_REVIEW")

        # Autogen-style: lanes is an int count; identities on lane_a/lane_b
        lea2 = account_local_active_equipment(
            generated_conveyors={"P1", "P1001"},
            merges=[
                {
                    "name": "P1001-P105A",
                    "classification": "REVIEW_REQUIRED",
                    "discharge": "",
                    "lanes": 2,
                    "lane_a": "P1001",
                    "lane_b": "P105A",
                }
            ],
            merges_withheld=["P1001-P105A"],
            local_active_tags=["P105A", "P1001"],
            io_points=[{"device_name": "SSV105A"}],
        )
        self.assertEqual(lea2["by_tag"]["P105A"]["classification"], "REVIEW_WITHHELD")
        self.assertEqual(lea2["ssv_classifications"]["SSV105A"], "INTENTIONAL_REVIEW")


if __name__ == "__main__":
    unittest.main()
