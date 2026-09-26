#!/usr/bin/env python3
"""Real-evidence Safety closure regressions (post Warden 9a3b28b).

Test provenance labels (required by mission):
  REAL_TAR_DERIVED | REAL_SOURCE_DERIVED | GENERIC_SYNTHETIC | UNIT_SYNTHETIC
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_es_compiler import (  # noqa: E402
    build_safety_zone_irs,
    emit_es_program,
    safety_writers_from_io_map_resolved_rows,
    safety_operand_has_writer,
)
from fortna_safety_endpoint_integrity import (  # noqa: E402
    apply_endpoint_integrity_pipeline,
)
from fortna_safety_model import (  # noqa: E402
    build_safety_model,
    _estop_signal_owner_machine,
)
from fortna_transport_graph import apply_graph_to_workbook  # noqa: E402

TFCP1_RUN = Path(
    r"C:\Users\curtiskricke\warden_audit\safety_d42c_2026-09-25\_work\runs_x\TFCP1\RUN"
)
ULTAPICK_RUN = ROOT / "tools" / "diagnostics" / "_real_runs" / "ULTAPICK" / "RUN"
TPNA1_RUN = ROOT / "tools" / "diagnostics" / "_real_runs" / "TPNA1" / "RUN"


def _rung_xml(num, text, comment=""):
    return f'<Rung Number="{num}" Type="N"><Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name, rungs):
    return f'<Routine Name="{name}" Type="RLL"><RLLContent>{"".join(rungs)}</RLLContent></Routine>'


# ---------------------------------------------------------------------------
# UNIT
# ---------------------------------------------------------------------------
class TestOri058EstopOwnerUnit(unittest.TestCase):
    """UNIT_SYNTHETIC — ownership helper contract."""

    PROVENANCE = "UNIT_SYNTHETIC"

    def test_unknown_does_not_inherit_active(self) -> None:
        d = {
            "name": "2ESR1_AUX",
            "controller": "TFCP1",  # session stamp — NOT ownership
            "machine_ownership": "UNKNOWN",
        }
        self.assertEqual(_estop_signal_owner_machine(d, "TFCP1"), "")

    def test_proven_uses_active(self) -> None:
        d = {"name": "1ES", "machine_ownership": "PROVEN"}
        self.assertEqual(_estop_signal_owner_machine(d, "TFCP1"), "TFCP1")

    def test_explicit_machine_wins(self) -> None:
        d = {
            "name": "X",
            "machine": "TFCP2",
            "controller": "TFCP1",
            "machine_ownership": "UNKNOWN",
        }
        self.assertEqual(_estop_signal_owner_machine(d, "TFCP1"), "TFCP2")


class TestGenericCollisionUnit(unittest.TestCase):
    """GENERIC_SYNTHETIC — raw word.bit vs Rockwell of the SAME point.

    NOT ULTAPICK real-site proof. Values 2705.12 / I.Data[17].2 originated as
    SYNTHETIC fixtures in prior Anton unit tests (see ULTAPICK_reproducer_provenance).
    """

    PROVENANCE = "GENERIC_SYNTHETIC"

    def test_generic_wordbit_vs_rockwell_collision(self) -> None:
        devices = [
            {"name": "DEV_A", "kind": "ESLS", "physicalEndpoint": "I.Data[17].2"},
            {"name": "DEV_B", "kind": "MCR", "physicalEndpoint": "9999.1"},
        ]
        pipe = apply_endpoint_integrity_pipeline(
            devices,
            word_bit_to_endpoint={"9999.1": "ADAPTER_X:I.Data[17].2"},
            valid_endpoints={"ADAPTER_X:I.Data[17].2"},
        )
        self.assertGreaterEqual(int(pipe.get("conflicted_count") or 0), 2)
        self.assertTrue(all(d.get("assignable") is False for d in devices))

    def test_different_adapters_do_not_falsely_collide(self) -> None:
        """GENERIC_SYNTHETIC — different adapters, same Data[n].b index."""
        devices = [
            {
                "name": "A",
                "kind": "ESLS",
                "physicalEndpoint": "CP2:I.Data[17].2",
            },
            {
                "name": "B",
                "kind": "ESLS",
                "physicalEndpoint": "CP3:I.Data[17].2",
            },
        ]
        pipe = apply_endpoint_integrity_pipeline(
            devices,
            valid_endpoints={"CP2:I.Data[17].2", "CP3:I.Data[17].2"},
        )
        self.assertEqual(int(pipe.get("conflicted_count") or 0), 0)


# ---------------------------------------------------------------------------
# INTEGRATION — REAL_TAR_DERIVED
# ---------------------------------------------------------------------------
@unittest.skipUnless(
    TFCP1_RUN.is_dir() and (TFCP1_RUN / "project.cfg").is_file(),
    "TFCP1 real RUN missing",
)
class TestOri058Tfcp1RealTar(unittest.TestCase):
    """REAL_TAR_DERIVED — TFCP1 RUN from Warden corpus.

    Source: warden_audit/.../runs_x/TFCP1/RUN
    SHA context: 9a3b28b Warden re-gate
    """

    PROVENANCE = "REAL_TAR_DERIVED"
    SITE = "TFCP1"

    def test_unknown_estop_family_not_stamped_tfcp1(self) -> None:
        model = build_safety_model(run_dir=TFCP1_RUN, machine="TFCP1")
        want = {"2ESP1", "2ESP2", "2ESR1", "2ESR2", "3ESP1", "3ESR1"}
        found = {}
        for d in model.get("safetyDevices") or []:
            nm = str(d.get("name") or "")
            if nm in want:
                found[nm] = d
        self.assertEqual(set(found), want)
        for nm, d in found.items():
            self.assertEqual(
                str(d.get("machine") or ""),
                "",
                f"{nm} must not stamp active TFCP1",
            )
            self.assertEqual(d.get("inventory_scope"), "UNKNOWN_OWNERSHIP", nm)
            self.assertEqual(d.get("assignable"), False, nm)
            self.assertNotEqual(
                str(d.get("machine") or "").upper(),
                "TFCP1",
                nm,
            )

    def test_1es_direction_still_mismatch(self) -> None:
        model = build_safety_model(run_dir=TFCP1_RUN, machine="TFCP1")
        one = next(
            (d for d in (model.get("safetyDevices") or []) if d.get("name") == "1ES"),
            None,
        )
        self.assertIsNotNone(one)
        assert one is not None
        self.assertIn("DIRECTION", str(one.get("review_reason") or "").upper())
        self.assertFalse(one.get("assignable"))


@unittest.skipUnless(
    ULTAPICK_RUN.is_dir() and (ULTAPICK_RUN / "FORTNA").is_dir(),
    "ULTAPICK full RUN missing",
)
class TestUltapickRealNoFalseCollision(unittest.TestCase):
    """REAL_TAR_DERIVED — ULTAPICK extracted TAR (Warden corpus).

    Real values (Warden 9a3b28b):
      ESLS610L raw=210.2 → CP2 … I.Data[17].2
      23MCR1   raw=2702.3 → CP23 … Data[5].3
    These MUST NOT collide.
    """

    PROVENANCE = "REAL_TAR_DERIVED"
    SITE = "ULTAPICK"
    RAW_VALUES = {"ESLS610L": "210.2", "23MCR1": "2702.3"}

    def test_esls610l_and_23mcr1_do_not_falsely_collide(self) -> None:
        model = build_safety_model(run_dir=ULTAPICK_RUN, machine="ULTAPICK")
        by = {
            str(d.get("name") or "").upper(): d
            for d in (model.get("safetyDevices") or [])
        }
        a = by.get("ESLS610L")
        b = by.get("23MCR1") or by.get("T_23MCR1")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        assert a is not None and b is not None
        self.assertNotEqual(
            str(a.get("physicalEndpoint") or "").upper(),
            str(b.get("physicalEndpoint") or "").upper(),
        )
        self.assertFalse(a.get("endpointConflict"))
        self.assertFalse(b.get("endpointConflict"))
        collisions = (model.get("evidence_union") or {}).get("endpoint_collisions") or []
        for c in collisions:
            claimants = {str(x).upper() for x in (c.get("claimants") or [])}
            if "ESLS610L" in claimants and (
                "23MCR1" in claimants or "T_23MCR1" in claimants
            ):
                self.fail(f"false collision recorded: {c}")


# ---------------------------------------------------------------------------
# BUILD-PATH E2E — writers from resolved_rows object (same as Autogen)
# ---------------------------------------------------------------------------
class TestWriterGraphBuildPathE2E(unittest.TestCase):
    """BUILD-PATH E2E: writers derived from IO_MAP resolved_rows shape.

    Does NOT manually inject written_tags into emit_es_program.
    Writers come only from safety_writers_from_io_map_resolved_rows(resolved_rows).

    Provenance: GENERIC_SYNTHETIC row shapes matching Autogen emission records.
    """

    PROVENANCE = "GENERIC_SYNTHETIC"

    def _emit_with_rows(self, resolved_rows, members=("1ES",)):
        writers = safety_writers_from_io_map_resolved_rows(resolved_rows)
        eng = [
            {
                "name": "Z1",
                "area": "A1",
                "members": list(members),
                "membersOrigin": "ENGINEER_ASSIGNED",
                "engineerEdited": True,
                "conveyors": ["P1"],
            }
        ]
        irs = build_safety_zone_irs(engineer_zones=eng, default_area="A1")
        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=lambda *_: None,
            library_text="",
            written_tags=writers,  # derived from resolved_rows — not hand-built set
        )
        return writers, pack

    def test_a_valid_writer_allows_consumer(self) -> None:
        rows = [
            {
                "mod_dir": "I",
                "member": "T_1ES.I.ES_OK",
                "channel": "AENTR1:I.Data[1].0",
                "rio": "AENTR1",
                "slot": 1,
                "data_bit": 0,
            }
        ]
        writers, pack = self._emit_with_rows(rows)
        self.assertIn("T_1ES", writers)
        self.assertIn("T_1ES.I.ES_OK", writers)
        self.assertIn("Z1", pack.get("emitted_zones") or [])
        self.assertIn("ES_SIL1_Cat1(", pack["program_xml"])

    def test_b_missing_writer_blocks_consumer(self) -> None:
        # Physical evidence may exist on device, but IO_MAP rows have no Safety OTE
        rows = [
            {
                "mod_dir": "I",
                "member": "P100_PE.I.PE_Clear",  # unrelated PE writer
                "channel": "AENTR1:I.Data[2].0",
                "rio": "AENTR1",
                "slot": 2,
                "data_bit": 0,
            }
        ]
        writers, pack = self._emit_with_rows(rows)
        self.assertNotIn("T_1ES", {w.upper() for w in writers})
        self.assertFalse(
            safety_operand_has_writer(
                "T_1ES",
                written_tags=writers,
                device_evidence={
                    "T_1ES": {"physicalEndpoint": "AENTR1:I.Data[1].0"}
                },
            )
        )
        self.assertNotIn("ES_SIL1_Cat1(", pack["program_xml"])

    def test_c_unrelated_writer_blocks_consumer(self) -> None:
        rows = [
            {
                "mod_dir": "I",
                "member": "T_2ES.I.ES_OK",  # different Safety device
                "channel": "AENTR1:I.Data[3].0",
                "rio": "AENTR1",
                "slot": 3,
                "data_bit": 0,
            }
        ]
        writers, pack = self._emit_with_rows(rows, members=("1ES",))
        self.assertIn("T_2ES", writers)
        self.assertNotIn("ES_SIL1_Cat1(T_1ES", pack["program_xml"].replace(" ", ""))
        self.assertNotIn("ES_SIL1_Cat1(", pack["program_xml"])


class TestOri050BlankControllerUi(unittest.TestCase):
    """UNIT_SYNTHETIC — source contract for blank recovered controller."""

    PROVENANCE = "UNIT_SYNTHETIC"

    def test_ui_blocks_blank_recovered_controller(self) -> None:
        ui = (ROOT / "dashboard" / "fortna-plus.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("staleBlankController", ui)
        self.assertIn("recovered L5X missing controller identity", ui)


class TestOri045WorkbookLifecycle(unittest.TestCase):
    """INTEGRATION — workbook/graph lifecycle (NOT full Electron UI).

    Provenance: GENERIC_SYNTHETIC zone identity; asserts persistence contracts
    that Warden already saw pass at workbook layer. Does NOT claim REAL UI E2E.
    """

    PROVENANCE = "GENERIC_SYNTHETIC"

    def test_transport_apply_preserves_cleared_arearef_members(self) -> None:
        wb = {
            "conveyors": [],
            "areas": [],
            "options": {"areas": []},
            "safety_build": {
                "appliedAt": "2026-09-26T12:00:00Z",
                "zones": [
                    {
                        "source_id": "szone_orl",
                        "name": "Warden_ESZ",
                        "engineering_name": "Warden_ESZ",
                        "areaRef": "",
                        "area": "",
                        "areaUnlinked": True,
                        "members": ["ES914", "ESLS161", "1ESR1", "1MCR1"],
                        "engineerEdited": True,
                        "createdBy": "engineer",
                        "provenance": "ENGINEER_CREATED",
                    }
                ],
            },
        }
        r = apply_graph_to_workbook(
            {
                "areas": [],
                "deletedAreas": ["Warden_Area"],
                "safetyBuild": {
                    "source": "transport_engineer",
                    "zones": [{"name": "Warden_ESZ", "areaRef": "", "members": []}],
                },
                "merges": [],
            },
            wb,
        )
        zones = (r["workbook"].get("safety_build") or {}).get("zones") or []
        eng = [z for z in zones if (z.get("members") or [])]
        self.assertEqual(len(eng), 1)
        self.assertEqual(len(eng[0]["members"]), 4)
        self.assertEqual(eng[0].get("areaRef") or "", "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
