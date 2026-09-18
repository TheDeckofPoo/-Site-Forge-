#!/usr/bin/env python3
"""Permanent tests: I/O ownership model Gates C/D/G/H (+ collision regressions).

Covers:
  - UNRESOLVED_OWNER ≠ SPARE
  - physical endpoint equality is exact (not name-prefix)
  - NETWORK_DEVICE_* / LOGICAL_SIGNAL do not require physical endpoint
  - no mystery BOOL generation for unknown symbols
  - PLC2/PLC5 known collision cases still pass
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_hardware_io_model import (  # noqa: E402
    OWNER_ASSIGNED,
    OWNER_ENGINEER_SPARE,
    OWNER_PROVEN_SPARE,
    OWNER_UNRESOLVED,
    enrich_channel_ownership,
    make_physical_endpoint,
    physical_endpoints_equal,
    resolve_owner_state,
)
from fortna_plc_symbol_registry import (  # noqa: E402
    LOGICAL_SIGNAL,
    NETWORK_DEVICE_COMMAND,
    NETWORK_DEVICE_STATUS,
    PHYSICAL_INPUT,
    PHYSICAL_OUTPUT,
    UNKNOWN,
    classify_cp_io_operand,
    may_auto_declare_bool,
    symbol_requires_physical_endpoint,
    unknown_symbol_policy,
)

CP5_RUN = ROOT / "workspace" / "cp5-run" / "RUN"
CP4_RUN = ROOT / "workspace" / "cp4-run" / "RUN"


def _plc2_run() -> Path | None:
    for cand in (
        ROOT / "workspace" / "active" / "RUN",
        ROOT / "workspace" / "_plc2_run_peek" / "RUN",
        ROOT / "workspace" / "active_rio_audit" / "RUN",
    ):
        if (cand / "project.cfg").is_file():
            return cand
    return None


class TestUnresolvedOwnerNotSpare(unittest.TestCase):
    def test_owner_states_distinct(self) -> None:
        self.assertNotEqual(OWNER_UNRESOLVED, OWNER_PROVEN_SPARE)
        self.assertNotEqual(OWNER_UNRESOLVED, OWNER_ENGINEER_SPARE)
        self.assertNotEqual(OWNER_UNRESOLVED, "SPARE")

    def test_conflict_is_unresolved_not_spare(self) -> None:
        ep = make_physical_endpoint(
            machine="ORNCCP2",
            rio_name="CP2RIO0",
            direction="O",
            data_index=6,
            bit=6,
            module_slot=7,
            bank_word=206,
            module_type="1794-OA8I",
            channel="CP2RIO0:O.Data[6].6",
        )
        st = resolve_owner_state(
            physical_endpoint=ep,
            engineering_owner=None,
            owner_conflict=True,
            topology_known=True,
        )
        self.assertEqual(st, OWNER_UNRESOLVED)
        self.assertNotEqual(st, OWNER_PROVEN_SPARE)

    def test_enrich_conflict_flags_unresolved(self) -> None:
        ch = {
            "physical_address": "CP2RIO0:O.Data[6].6",
            "fortna_word": 206,
            "fortna_bit": 6,
            "direction": "O",
            "type": "1794-OA8I",
        }
        claims = {
            "owners": {},
            "conflicts": {"CP2RIO0:O.Data[6].6": ["INT229", "M402"]},
            "spare_channels": set(),
        }
        enrich_channel_ownership(
            ch,
            machine="ORNCCP2",
            claims=claims,
            adapter={"rio_name": "CP2RIO0"},
            module={"slot": 7, "data_index": 6, "direction": "O", "type": "1794-OA8I"},
        )
        self.assertEqual(ch["owner_state"], OWNER_UNRESOLVED)
        self.assertTrue(ch["unresolved"])
        self.assertFalse(ch.get("is_spare"))
        self.assertNotEqual(ch["owner_state"], OWNER_PROVEN_SPARE)

    def test_unused_configio_bit_is_proven_spare(self) -> None:
        ep = make_physical_endpoint(
            rio_name="CP2RIO0",
            direction="I",
            data_index=1,
            bit=3,
            module_slot=2,
            bank_word=201,
            module_type="1794-IA16",
            channel="CP2RIO0:I.Data[1].3",
        )
        st = resolve_owner_state(
            physical_endpoint=ep,
            engineering_owner=None,
            topology_known=True,
        )
        self.assertEqual(st, OWNER_PROVEN_SPARE)


class TestPhysicalEndpointEqualityNotPrefix(unittest.TestCase):
    def test_same_endpoint_equal(self) -> None:
        a = make_physical_endpoint(
            machine="ORNCCP5",
            rio_name="CP5RIO2",
            direction="O",
            data_index=0,
            bit=0,
            module_slot=1,
            bank_word=520,
            module_type="1794-OB16P",
            channel="CP5RIO2:O.Data[0].0",
        )
        b = make_physical_endpoint(
            machine="ORNCCP5",
            rio_name="CP5RIO2",
            direction="O",
            data_index=0,
            bit=0,
            module_slot=1,
            bank_word=520,
            module_type="1794-OB16P",
            channel="CP5RIO2:O.Data[0].0",
        )
        self.assertTrue(physical_endpoints_equal(a, b))

    def test_bank516_vs_520_not_equal(self) -> None:
        a = make_physical_endpoint(
            machine="ORNCCP5",
            rio_name="CP5RIO1",
            direction="I",
            data_index=6,
            bit=0,
            module_slot=7,
            bank_word=516,
            module_type="1794-IA16",
            channel="CP5RIO1:I.Data[6].0",
        )
        b = make_physical_endpoint(
            machine="ORNCCP5",
            rio_name="CP5RIO2",
            direction="O",
            data_index=0,
            bit=0,
            module_slot=1,
            bank_word=520,
            module_type="1794-OB16P",
            channel="CP5RIO2:O.Data[0].0",
        )
        self.assertFalse(physical_endpoints_equal(a, b))

    def test_p220_vs_p220a_owners_not_prefix_collapsed(self) -> None:
        """Logical names P220 / P220A are distinct — endpoint equality ignores names."""
        # Same physical bit claimed by two lettered identities must not collapse
        ep = make_physical_endpoint(
            rio_name="CP2RIO0",
            direction="I",
            data_index=2,
            bit=0,
            module_slot=3,
            bank_word=210,
            module_type="1794-IA16",
            channel="CP2RIO0:I.Data[2].0",
        )
        # Endpoint identity does not include logical name — equality is dimensional
        self.assertTrue(physical_endpoints_equal(ep, dict(ep)))
        # Distinct endpoints (different bit) are not equal even if names share prefix
        ep_a = make_physical_endpoint(
            rio_name="CP2RIO0",
            direction="I",
            data_index=2,
            bit=1,
            module_slot=3,
            bank_word=210,
            module_type="1794-IA16",
            channel="CP2RIO0:I.Data[2].1",
        )
        self.assertFalse(physical_endpoints_equal(ep, ep_a))
        # Name-prefix similarity must never be used for equality
        fake = dict(ep)
        fake["channel"] = "CP2RIO0:I.Data[2].0"  # same
        self.assertTrue(physical_endpoints_equal(ep, fake))
        # Changing only bank_word breaks equality (no fuzzy match)
        other = dict(ep)
        other["bank_word"] = 211
        other["endpoint_id"] = None  # force dimension compare
        # channel still same string — but bank_word differs → not equal
        self.assertFalse(physical_endpoints_equal(ep, other))


class TestSymbolClassPhysicalEndpointPolicy(unittest.TestCase):
    def test_network_device_command_no_endpoint_required(self) -> None:
        r = classify_cp_io_operand(
            "P402_Conv.O.Run",
            direction_hint="O",
            declared={"scope": "controller", "owner": "autogen", "datatype": "Conv_UDT"},
        )
        self.assertEqual(r["semantic_class"], NETWORK_DEVICE_COMMAND)
        self.assertIsNone(r["physical_endpoint"])
        self.assertFalse(r["requires_physical_endpoint"])
        self.assertFalse(symbol_requires_physical_endpoint(r["semantic_class"]))

    def test_network_device_status_no_endpoint_required(self) -> None:
        r = classify_cp_io_operand(
            "P220A_MS.I.Auxiliary_Forward",
            direction_hint="I",
            declared={"scope": "controller", "owner": "autogen", "datatype": "Motor_Starter_UDT"},
        )
        self.assertEqual(r["semantic_class"], NETWORK_DEVICE_STATUS)
        self.assertIsNone(r["physical_endpoint"])
        self.assertFalse(symbol_requires_physical_endpoint(NETWORK_DEVICE_STATUS))

    def test_logical_signal_no_endpoint(self) -> None:
        r = classify_cp_io_operand(
            "ENABLE_SAWTOOTH",
            declared={
                "scope": "controller",
                "owner": "control_model",
                "datatype": "BOOL",
                "semantic_class": LOGICAL_SIGNAL,
                "provenance": "PROVEN",
            },
        )
        self.assertEqual(r["semantic_class"], LOGICAL_SIGNAL)
        self.assertIsNone(r["physical_endpoint"])
        self.assertFalse(symbol_requires_physical_endpoint(LOGICAL_SIGNAL))

    def test_module_path_is_physical(self) -> None:
        r = classify_cp_io_operand("CP5RIO2:O.Data[0].0", direction_hint="O")
        self.assertEqual(r["semantic_class"], PHYSICAL_OUTPUT)
        self.assertTrue(r["requires_physical_endpoint"])
        self.assertIsNotNone(r["physical_endpoint"])
        self.assertEqual(r["root"], "CP5RIO2")

    def test_physical_input_module(self) -> None:
        r = classify_cp_io_operand("CP2RIO0:I.Data[1].0")
        self.assertEqual(r["semantic_class"], PHYSICAL_INPUT)


class TestNoMysteryBoolForUnknown(unittest.TestCase):
    def test_unknown_disposition_engineer_required(self) -> None:
        r = classify_cp_io_operand("TotallyUnknownSymbol_XYZ")
        self.assertEqual(r["semantic_class"], UNKNOWN)
        self.assertEqual(r["disposition"], "ENGINEER_REQUIRED")
        self.assertIsNone(r["physical_endpoint"])
        self.assertIn("auto_BOOL", r["forbidden_actions"])
        self.assertFalse(may_auto_declare_bool(r))

    def test_unknown_policy_fatal_fabricated(self) -> None:
        r = unknown_symbol_policy("fake_auto_bool_tag")
        self.assertEqual(r["disposition"], "FATAL")
        self.assertFalse(may_auto_declare_bool(r))

    def test_absent_reference(self) -> None:
        r = classify_cp_io_operand("INVALID")
        self.assertEqual(r["disposition"], "ABSENT_REFERENCE")
        self.assertFalse(may_auto_declare_bool(r))

    def test_assigned_owner_state_ok(self) -> None:
        st = resolve_owner_state(
            physical_endpoint=make_physical_endpoint(
                rio_name="CP2RIO0", direction="I", data_index=0, bit=0, channel="CP2RIO0:I.Data[0].0"
            ),
            engineering_owner="2PBSTART",
            topology_known=True,
        )
        self.assertEqual(st, OWNER_ASSIGNED)


class TestPlc5Plc2CollisionStillPass(unittest.TestCase):
    def test_plc5_516_520_distinct(self) -> None:
        if not (CP5_RUN / "project.cfg").is_file():
            self.skipTest("PLC5 RUN missing")
        from fortna_physical_word_resolver import build_physical_word_map, resolve_word_bit

        pm = build_physical_word_map(CP5_RUN, "ORNCCP5")
        a = resolve_word_bit(pm, 516, 0)
        b = resolve_word_bit(pm, 520, 0)
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        assert a is not None and b is not None
        self.assertNotEqual(a.get("channel"), b.get("channel"))
        ea = make_physical_endpoint(
            machine="ORNCCP5",
            rio_name=a.get("rio_name") or "",
            direction=a.get("direction") or "",
            data_index=a.get("data_index") if a.get("data_index") is not None else a.get("flex_slot"),
            bit=a.get("bit"),
            module_slot=a.get("eip_slot"),
            bank_word=516,
            module_type=a.get("type") or "",
            channel=a.get("channel") or "",
        )
        eb = make_physical_endpoint(
            machine="ORNCCP5",
            rio_name=b.get("rio_name") or "",
            direction=b.get("direction") or "",
            data_index=b.get("data_index") if b.get("data_index") is not None else b.get("flex_slot"),
            bit=b.get("bit"),
            module_slot=b.get("eip_slot"),
            bank_word=520,
            module_type=b.get("type") or "",
            channel=b.get("channel") or "",
        )
        self.assertFalse(physical_endpoints_equal(ea, eb))

    def test_plc2_m402_int229_distinct(self) -> None:
        run = _plc2_run()
        if not run:
            self.skipTest("PLC2 RUN missing")
        from fortna_physical_word_resolver import build_physical_word_map, resolve_word_bit

        pm = build_physical_word_map(run, "ORNCCP2")
        m402 = resolve_word_bit(pm, 206, 6)
        int229 = resolve_word_bit(pm, 207, 6)
        if m402 is None or int229 is None:
            self.skipTest("PLC2 banks 206/207 not resolvable on this RUN")
        self.assertNotEqual(m402.get("channel"), int229.get("channel"))

    def test_hardware_model_has_owner_states_cp4(self) -> None:
        if not (CP4_RUN / "project.cfg").is_file():
            self.skipTest("CP4 RUN missing")
        from fortna_hardware_io_model import build_hardware_io_model

        model = build_hardware_io_model(CP4_RUN, "ORNCCP4")
        self.assertTrue(model.get("ok"))
        self.assertIn("owner_states", model.get("stats") or {})
        # At least one channel carries physical_endpoint + owner_state
        found = False
        for ad in model.get("adapters") or []:
            for mod in ad.get("modules") or []:
                for ch in mod.get("channels") or []:
                    if ch.get("physical_endpoint") and ch.get("owner_state"):
                        found = True
                        self.assertIn(
                            ch["owner_state"],
                            {
                                OWNER_ASSIGNED,
                                OWNER_UNRESOLVED,
                                OWNER_PROVEN_SPARE,
                                OWNER_ENGINEER_SPARE,
                                "UNKNOWN",
                            },
                        )
                        break
                if found:
                    break
            if found:
                break
        self.assertTrue(found, "expected enriched channels with physical_endpoint")


if __name__ == "__main__":
    unittest.main(verbosity=2)
