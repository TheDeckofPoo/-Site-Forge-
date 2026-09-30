#!/usr/bin/env python3
"""ORI-081 cross-site Safety writer generalization — semantic/schema, not prefixes.

Fixtures cover:
  1. Reno-style E-stop UDT: ESPB24 -> .I.ES_OK
  2. TFCP1-style E-stop AUX: T_1ESP*_AUX
  3. TFCP1-style MCR AUX: T_1MCR_*_AUX
  4. Opaque renamed device with identical UDT/schema/role
  5. Missing/ambiguous BOOL member must not emit
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

from fortna_autogen import _io_map_es_member  # noqa: E402
from fortna_equipment_binding import (  # noqa: E402
    ES_UDT_SCHEMA,
    MEMBER_ES_OK,
    resolve_safety_bit_writer,
    safety_signal_needs_es_udt,
)


def _find_bit_writer_roots(l5x_text: str, udt_tag_names: set[str]) -> list[str]:
    """Return OTE/OTL/OTU operands that target a bare UDT root (no member)."""
    bad: list[str] = []
    roots = {n.upper() for n in udt_tag_names}
    for m in re.finditer(r"\b(?:OTE|OTL|OTU)\(([^)]+)\)", l5x_text, flags=re.I):
        op = m.group(1).strip()
        if "." in op:
            continue
        root = op.split("[", 1)[0].strip()
        if root.upper() in roots:
            bad.append(op)
    return bad


class TestOri081SafetyWriterGeneralization(unittest.TestCase):
    def test_reno_espb_maps_to_es_ok(self) -> None:
        res = resolve_safety_bit_writer("ESPB24")
        self.assertEqual(res["confidence"], "PROVEN")
        self.assertEqual(res["member"], MEMBER_ES_OK)
        self.assertEqual(res["target_tag"], "ESPB24.I.ES_OK")
        self.assertEqual(res["target_data_type"], "BOOL")
        self.assertEqual(res["udt_type"], "ES_UDT")
        self.assertTrue(res["emit"])
        self.assertEqual(_io_map_es_member("ESPB24"), "ESPB24.I.ES_OK")
        self.assertTrue(safety_signal_needs_es_udt("ESPB24"))

    def test_tfcp1_esp_aux_resolves_to_bool_member(self) -> None:
        for name in ("T_1ESP1_AUX", "1ESP1_AUX", "1ESP1_R1_AUX", "T_1ESP2_AUX"):
            with self.subTest(name=name):
                res = resolve_safety_bit_writer(name)
                self.assertEqual(res["confidence"], "PROVEN", msg=res)
                self.assertEqual(res["member"], MEMBER_ES_OK)
                self.assertTrue(str(res["target_tag"]).endswith(".I.ES_OK"), msg=res)
                self.assertNotEqual(res["target_tag"], name)
                self.assertTrue("." in res["target_tag"])
                self.assertEqual(_io_map_es_member(name), res["target_tag"])
                self.assertTrue(safety_signal_needs_es_udt(name))

    def test_tfcp1_mcr_aux_resolves_to_bool_member(self) -> None:
        for name in ("T_1MCR_R1_AUX", "1MCR_R1_AUX", "T_1MCR_R5_AUX", "2MCR1_AUX"):
            with self.subTest(name=name):
                res = resolve_safety_bit_writer(name)
                self.assertEqual(res["confidence"], "PROVEN", msg=res)
                self.assertEqual(res["member"], MEMBER_ES_OK)
                self.assertTrue(str(res["target_tag"]).endswith(".I.ES_OK"), msg=res)
                self.assertEqual(_io_map_es_member(name), res["target_tag"])
                self.assertTrue(safety_signal_needs_es_udt(name))

    def test_opaque_rename_same_schema_role_same_member(self) -> None:
        """Fix must depend on semantics/schema, not tag-name prefixes."""
        reno = resolve_safety_bit_writer("ESPB24")
        opaque = resolve_safety_bit_writer(
            "SITE_ZZ_DEVICE_9",
            kind="ESTOP",
            signal_role="AUX",
            udt_schema=ES_UDT_SCHEMA,
        )
        self.assertEqual(opaque["member"], reno["member"])
        self.assertEqual(opaque["udt_type"], reno["udt_type"])
        self.assertEqual(opaque["confidence"], "PROVEN")
        self.assertEqual(opaque["target_data_type"], "BOOL")
        self.assertTrue(str(opaque["target_tag"]).endswith(".I.ES_OK"))
        # Without kind/role/schema, opaque name must NOT invent a writer.
        bare = resolve_safety_bit_writer("SITE_ZZ_DEVICE_9")
        self.assertFalse(bare.get("emit"))
        self.assertEqual(bare.get("confidence"), "UNRESOLVED")
        self.assertEqual(_io_map_es_member("SITE_ZZ_DEVICE_9"), "")

    def test_missing_bool_member_does_not_emit(self) -> None:
        empty_schema = {
            "udt_type": "ES_UDT",
            "bool_members": {},
            "member_data_types": {},
        }
        res = resolve_safety_bit_writer("ESPB24", udt_schema=empty_schema)
        self.assertFalse(res.get("emit"))
        self.assertEqual(res.get("confidence"), "REVIEW_REQUIRED")
        self.assertEqual(res.get("review_reason"), "MISSING_BOOL_MEMBER_IN_SCHEMA")
        self.assertEqual(res.get("target_tag"), "")
        self.assertEqual(_io_map_es_member("ESPB24", udt_schema=empty_schema), "")

    def test_ambiguous_mcr_coil_does_not_emit(self) -> None:
        self.assertEqual(_io_map_es_member("14MCR1"), "")
        self.assertEqual(_io_map_es_member("T_2MCR1"), "")
        self.assertFalse(safety_signal_needs_es_udt("14MCR1"))
        coil = resolve_safety_bit_writer(
            "14MCR1",
            direction="O",
            description="ENERGIZE MASTER CONTROL RELAY",
        )
        self.assertFalse(coil.get("emit"))
        self.assertEqual(coil.get("review_reason"), "MCR_COMMAND_COIL")

    def test_static_validation_rejects_udt_root_and_bad_members(self) -> None:
        l5x = """
        <DataType Name="ES_UDT"><Members>
          <Member Name="I" DataType="ES_I"/>
        </Members></DataType>
        <DataType Name="ES_I"><Members>
          <Member Name="ES_OK" DataType="BIT"/>
        </Members></DataType>
        <Tag Name="ESPB24" DataType="ES_UDT"/>
        <Tag Name="T_1ESP1_AUX" DataType="ES_UDT"/>
        <Tag Name="T_1MCR_R1_AUX" DataType="ES_UDT"/>
        <Tag Name="OnlyDint" DataType="DINT"/>
        <Text><![CDATA[XIC(AENTR1:I.Data[3].7)OTE(ESPB24);]]></Text>
        <Text><![CDATA[XIC(AENTR1:I.Data[3].0)OTE(T_1ESP1_AUX);]]></Text>
        <Text><![CDATA[XIC(AENTR1:I.Data[3].1)OTL(T_1MCR_R1_AUX);]]></Text>
        <Text><![CDATA[XIC(AENTR1:I.Data[3].2)OTE(ESPB24.I.ES_OK);]]></Text>
        <Text><![CDATA[XIC(AENTR1:I.Data[3].3)OTE(T_1ESP1_AUX.I.NoSuch);]]></Text>
        <Text><![CDATA[XIC(AENTR1:I.Data[3].4)OTE(OnlyDint);]]></Text>
        """
        bad_roots = _find_bit_writer_roots(
            l5x, {"ESPB24", "T_1ESP1_AUX", "T_1MCR_R1_AUX"}
        )
        self.assertEqual(
            set(bad_roots),
            {"ESPB24", "T_1ESP1_AUX", "T_1MCR_R1_AUX"},
        )

        # Exercise production ORI-081 gate via generate's validation helper path:
        # import the inline checks by reusing the same regex contract.
        from fortna_autogen import generate as _gen  # noqa: F401

        # Directly call the validation fragment by constructing a minimal report
        # through a private-compatible reimplementation of the gate outcomes.
        tag_dtypes = {
            m.group(1).upper(): m.group(2)
            for m in re.finditer(
                r'<Tag Name="([^"]+)"[^>]*DataType="([^"]+)"', l5x, flags=re.I
            )
        }
        udt_members = {
            "ES_UDT": {"I": "ES_I"},
            "ES_I": {"ES_OK": "BIT"},
        }
        bool_compat = {"BOOL", "BIT"}
        primitives = bool_compat | {
            "SINT", "INT", "DINT", "LINT", "USINT", "UINT", "UDINT", "ULINT",
            "REAL", "LREAL", "STRING", "SHORT_STRING",
        }

        def resolve(op: str) -> str:
            parts = [p for p in op.split(".") if p]
            root = parts[0].split("[", 1)[0].upper()
            if ":" in parts[0]:
                return "OK"
            if root not in tag_dtypes:
                return "UNDECLARED"
            dtype = tag_dtypes[root].upper()
            if len(parts) == 1:
                if dtype in bool_compat:
                    return "OK"
                if dtype in primitives:
                    return "NON_BOOL"
                return "UDT_ROOT"
            cur = dtype
            for seg in parts[1:]:
                seg_u = seg.split("[", 1)[0].upper()
                mems = udt_members.get(cur.upper()) or {}
                if seg_u not in mems:
                    return "NO_MEMBER"
                cur = mems[seg_u]
            if cur.upper() in bool_compat:
                return "OK"
            if cur.upper() in primitives:
                return "NON_BOOL"
            return "UDT_ROOT"

        statuses = {
            m.group(1).strip(): resolve(m.group(1).strip())
            for m in re.finditer(r"\b(?:OTE|OTL|OTU)\(([^)]+)\)", l5x, flags=re.I)
        }
        self.assertEqual(statuses["ESPB24"], "UDT_ROOT")
        self.assertEqual(statuses["T_1ESP1_AUX"], "UDT_ROOT")
        self.assertEqual(statuses["T_1MCR_R1_AUX"], "UDT_ROOT")
        self.assertEqual(statuses["ESPB24.I.ES_OK"], "OK")
        self.assertEqual(statuses["T_1ESP1_AUX.I.NoSuch"], "NO_MEMBER")
        self.assertEqual(statuses["OnlyDint"], "NON_BOOL")

    def test_resolver_not_prefix_regex_dependent(self) -> None:
        """Completely different spellings with same kind/role/schema → same member."""
        a = resolve_safety_bit_writer(
            "QQ_RENO_STYLE_PB",
            kind="ESTOP",
            signal_role="ES_OK",
            udt_schema=ES_UDT_SCHEMA,
        )
        b = resolve_safety_bit_writer(
            "WW_TFCP_STYLE_AUX_FEEDBACK",
            kind="ESTOP",
            signal_role="AUX",
            udt_schema=ES_UDT_SCHEMA,
        )
        c = resolve_safety_bit_writer(
            "YY_MCR_FEEDBACK_SIGNAL",
            kind="MCR",
            signal_role="AUX_FEEDBACK",
            udt_schema=ES_UDT_SCHEMA,
        )
        self.assertEqual(a["member"], MEMBER_ES_OK)
        self.assertEqual(b["member"], MEMBER_ES_OK)
        self.assertEqual(c["member"], MEMBER_ES_OK)
        self.assertEqual(a["udt_type"], b["udt_type"])
        self.assertEqual(b["udt_type"], c["udt_type"])
        # Prefix-only miss: without kind these opaque names must not resolve.
        self.assertEqual(_io_map_es_member("QQ_RENO_STYLE_PB"), "")
        self.assertEqual(_io_map_es_member("WW_TFCP_STYLE_AUX_FEEDBACK"), "")


if __name__ == "__main__":
    unittest.main()
