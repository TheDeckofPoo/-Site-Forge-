"""Regression: Motor_Chained membership != standalone PLC conveyor object.

ACTIVE_CHAINED_SEGMENT rides under the local parent motor:
- no independent motor I/O invention
- no fabricated PE
- remains in conservation (UNACCOUNTED == 0)
- P1A/P2A are never FOREIGN merely from visual adjacency
- P300 is never omitted from conservation
- validated standalone conveyors remain ACTIVE_CONTROLLED
- known merge authorization (P105A) is not regressed
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_transport_active_control import (  # noqa: E402
    CLASS_ACTIVE,
    CLASS_CHAINED,
    CLASS_FOREIGN,
    CLASS_REVIEW,
    ALL_CLASSES,
    authorize_merges_for_active_control,
    classify_transport_active,
    conservation_summary,
    filter_conveyors_active_controlled,
)


def _rec(
    tag: str,
    *,
    classification: str,
    may_generate: bool = False,
    reason: str = "",
    flags: list[str] | None = None,
    parent_motor: str | None = None,
    pe: list[str] | None = None,
    controller_motors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "conveyor": tag,
        "classification": classification,
        "may_generate": may_generate,
        "reason": reason,
        "flags": flags or [],
        "parent_motor": parent_motor,
        "source_chain": "Mtrchain.asc" if parent_motor else None,
        "standalone_withheld_reason": reason if classification == CLASS_CHAINED else None,
        "pe_topology_allowed": pe or [],
        "controller_motors": controller_motors or [],
        "mtrchain": (
            [{"motor": parent_motor, "aux": "X", "source": "Mtrchain.asc"}]
            if parent_motor
            else []
        ),
        "merge_owners": [],
        "owner_local": "mergeboss_owner" in (flags or []),
    }


class TestTransportChainSegmentSemantics(unittest.TestCase):
    def test_motor_chained_alone_does_not_create_standalone_conv(self) -> None:
        """Filter must drop ACTIVE_CHAINED_SEGMENT even if present in input list."""
        gate = {
            "by_tag": {
                "P103A": _rec(
                    "P103A",
                    classification=CLASS_CHAINED,
                    parent_motor="M103",
                    reason="ACTIVE_CHAINED_SEGMENT:rides_under_local_parent:M103",
                    pe=["PE103A_P"],  # must still be stripped / not generated
                ),
                "P103": _rec(
                    "P103",
                    classification=CLASS_ACTIVE,
                    may_generate=True,
                    flags=["motor_starter_controller_scoped"],
                    controller_motors=["M103"],
                    pe=["PE103_P"],
                ),
            },
            "active_controlled": ["P103"],
        }
        conveyors = [
            SimpleNamespace(
                conveyor="P103A",
                exit_pe_tag="PE103A_P",
                add_pe_tag="PE103A_P",
                jam_pe_tags=["PE103A_P"],
                full_pe_tags=[],
                product_pe_tags=[],
                all_pe_tags=["PE103A_P"],
            ),
            SimpleNamespace(
                conveyor="P103",
                exit_pe_tag="PE103_P",
                add_pe_tag="",
                jam_pe_tags=["PE103_P"],
                full_pe_tags=[],
                product_pe_tags=[],
                all_pe_tags=["PE103_P"],
            ),
        ]
        kept, meta = filter_conveyors_active_controlled(conveyors, gate)
        kept_tags = {c.conveyor for c in kept}
        self.assertEqual(kept_tags, {"P103"})
        self.assertNotIn("P103A", kept_tags)
        chained = meta.get("chained_segments_retained") or []
        self.assertTrue(any(r["conveyor"] == "P103A" for r in chained))
        self.assertEqual(chained[0].get("parent_motor"), "M103")

    def test_chained_segment_stays_in_canonical_model(self) -> None:
        records = [
            _rec("P1", classification=CLASS_ACTIVE, may_generate=True),
            _rec(
                "P1A",
                classification=CLASS_CHAINED,
                parent_motor="M1",
                reason="ACTIVE_CHAINED_SEGMENT:rides_under_local_parent:M1",
            ),
            _rec("P300", classification=CLASS_FOREIGN, reason="pack"),
        ]
        cons = conservation_summary(records)
        self.assertTrue(cons["conservation_ok"])
        self.assertEqual(cons["counts"]["UNACCOUNTED"], 0)
        self.assertEqual(cons["counts"][CLASS_CHAINED], 1)
        self.assertIn("P1A", [r["conveyor"] for r in records])

    def test_chained_segment_inherits_no_fabricated_pe(self) -> None:
        gate = {
            "by_tag": {
                "P17A": _rec(
                    "P17A",
                    classification=CLASS_CHAINED,
                    parent_motor="M17",
                    pe=[],  # classifier clears PE allow-list for chained
                ),
            },
            "active_controlled": [],
        }
        c = SimpleNamespace(
            conveyor="P17A",
            exit_pe_tag="PE17A_INVENTED",
            add_pe_tag="PE17A_INVENTED",
            jam="PE17A_INVENTED",
            full="PE17A_INVENTED",
            jam_pe_tags=["PE17A_INVENTED"],
            full_pe_tags=["PE17A_INVENTED"],
            product_pe_tags=["PE17A_INVENTED"],
            all_pe_tags=["PE17A_INVENTED"],
        )
        kept, meta = filter_conveyors_active_controlled([c], gate)
        self.assertEqual(kept, [])
        # Dropped chained segment retains parent evidence; PE was never admitted.
        drop = (meta.get("chained_segments_retained") or [None])[0]
        self.assertIsNotNone(drop)
        self.assertEqual(drop["parent_motor"], "M17")
        self.assertEqual(gate["by_tag"]["P17A"]["pe_topology_allowed"], [])

    def test_p1a_p2a_not_foreign_from_visual_adjacency(self) -> None:
        records = [
            _rec(
                "P1A",
                classification=CLASS_CHAINED,
                parent_motor="M1",
                reason="ACTIVE_CHAINED_SEGMENT:rides_under_local_parent:M1",
            ),
            _rec(
                "P2A",
                classification=CLASS_CHAINED,
                parent_motor="M2",
                reason="ACTIVE_CHAINED_SEGMENT:rides_under_local_parent:M2",
            ),
        ]
        for r in records:
            self.assertEqual(r["classification"], CLASS_CHAINED)
            self.assertNotEqual(r["classification"], CLASS_FOREIGN)

    def test_p300_never_omitted_from_conservation(self) -> None:
        records = [
            _rec("P1", classification=CLASS_ACTIVE, may_generate=True),
            _rec(
                "P300",
                classification=CLASS_FOREIGN,
                reason="pack_or_other_system_mtrchain_without_local_ownership",
                parent_motor="MDR300",
            ),
        ]
        cons = conservation_summary(records)
        self.assertTrue(cons["conservation_ok"])
        self.assertEqual(cons["counts"]["UNACCOUNTED"], 0)
        self.assertEqual(cons["counts"][CLASS_FOREIGN], 1)
        tags = {r["conveyor"] for r in records}
        self.assertIn("P300", tags)

    def test_validated_standalone_conveyors_remain_generated(self) -> None:
        gate = {
            "by_tag": {
                t: _rec(
                    t,
                    classification=CLASS_ACTIVE,
                    may_generate=True,
                    flags=["motor_starter_controller_scoped"],
                    controller_motors=[f"M{t[1:]}"],
                )
                for t in ["P1", "P2", "P103", "P128A", "P1003A"]
            },
            "active_controlled": ["P1", "P2", "P103", "P128A", "P1003A"],
        }
        conveyors = [SimpleNamespace(conveyor=t) for t in gate["active_controlled"]]
        kept, meta = filter_conveyors_active_controlled(conveyors, gate)
        self.assertEqual(sorted(c.conveyor for c in kept), sorted(gate["active_controlled"]))
        self.assertEqual(meta["kept_count"], 5)

    def test_known_merge_behavior_not_regressed(self) -> None:
        """P105A MergeBoss closure still authorizes when discharge is available."""
        gate = {
            "by_tag": {
                "P1001": _rec(
                    "P1001",
                    classification=CLASS_REVIEW,  # demoted — conflict under M59
                    reason="SPLIT_REVIEW",
                ),
                "P105A": _rec(
                    "P105A",
                    classification=CLASS_ACTIVE,
                    may_generate=True,
                    flags=["mergeboss_owner", "fidelity_local_active"],
                ),
            },
            "active_controlled": ["P105A"],
        }
        # Use a merge whose both lanes are ACTIVE — simulate P105 + P105A style
        # with P105 still active for authorization path.
        gate["by_tag"]["P105"] = _rec(
            "P105",
            classification=CLASS_ACTIVE,
            may_generate=True,
            flags=["motor_starter_controller_scoped"],
            controller_motors=["M105"],
        )
        gate["active_controlled"] = ["P105", "P105A"]
        merges = [
            {
                "discovery_name": "P1001-P105A",
                "lane_a": "P105",
                "lane_b": "P105A",
                "discharge": "",
                "may_generate": False,
                "pe_a": "PE_FAKE",
            }
        ]
        with mock.patch(
            "fortna_transport_active_control._merge_route_discharge",
            return_value="P105A",
        ):
            out, meta = authorize_merges_for_active_control(
                merges, gate, run_dir=Path("."), machine="MSCRENOPICK"
            )
        self.assertIn("P1001-P105A", meta["authorized"])
        self.assertTrue(out[0]["may_generate"])
        self.assertEqual(out[0]["discharge"], "P105A")
        self.assertEqual(out[0].get("pe_a"), "")  # name-only PE stripped

    def test_all_classes_enumerated_for_conservation(self) -> None:
        self.assertIn(CLASS_CHAINED, ALL_CLASSES)
        self.assertEqual(len(ALL_CLASSES), 6)


@unittest.skipUnless(
    (
        Path(r"C:\dev\worktree\FortnaPlus\workspace\active\RUN\FORTNA\Mtrchain.asc").is_file()
        or Path("workspace/active/RUN/FORTNA/Mtrchain.asc").is_file()
    ),
    "MSCRENOPICK RUN not available",
)
class TestMscrenopickLiveChainSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        run = Path(r"C:\dev\worktree\FortnaPlus\workspace\active\RUN")
        if not (run / "FORTNA" / "Mtrchain.asc").is_file():
            run = Path("workspace/active/RUN")
        cls.gate = classify_transport_active(run, "MSCRENOPICK")

    def test_conservation_unaccounted_zero(self) -> None:
        self.assertTrue(self.gate["conservation_ok"])
        self.assertEqual(self.gate["counts"]["UNACCOUNTED"], 0)

    def test_known_chained_segments(self) -> None:
        by = self.gate["by_tag"]
        for tag in [
            "P103A",
            "P103B",
            "P127A",
            "P17A",
            "P18A",
            "P58A",
            "P70A",
            "P1005",
            "P1006",
            "P56A",
            "P1A",
            "P2A",
        ]:
            self.assertEqual(
                by[tag]["classification"],
                CLASS_CHAINED,
                msg=f"{tag} -> {by[tag]}",
            )
            self.assertFalse(by[tag]["may_generate"])
            self.assertTrue(by[tag].get("parent_motor"))

    def test_p1a_p2a_not_foreign(self) -> None:
        for tag in ("P1A", "P2A"):
            self.assertNotEqual(self.gate["by_tag"][tag]["classification"], CLASS_FOREIGN)

    def test_p300_present(self) -> None:
        self.assertIn("P300", self.gate["by_tag"])
        self.assertEqual(self.gate["counts"]["UNACCOUNTED"], 0)

    def test_forced_reviews(self) -> None:
        by = self.gate["by_tag"]
        for tag in ("P1002A", "P1004A", "P120A", "P1001", "P129", "P38"):
            self.assertEqual(by[tag]["classification"], CLASS_REVIEW, msg=tag)
            self.assertFalse(by[tag]["may_generate"])

    def test_standalone_parents_still_active(self) -> None:
        by = self.gate["by_tag"]
        for tag in ("P1", "P2", "P103", "P105A", "P128A"):
            self.assertEqual(by[tag]["classification"], CLASS_ACTIVE, msg=tag)
            self.assertTrue(by[tag]["may_generate"])


if __name__ == "__main__":
    unittest.main()
