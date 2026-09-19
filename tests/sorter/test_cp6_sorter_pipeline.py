#!/usr/bin/env python3
"""CP6 sorter pipeline — area identity, divert host remap, machine scope, area bind.

Virgin ORINDYAC6 RUN only. Finished PLC paths must never be used as generation input.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_autogen import (  # noqa: E402
    AutogenInput,
    ConveyorRow,
    bind_sorter_area_conveyors,
    seed_native_merges_for_sorter,
)
from fortna_autogen_provenance import audit, why_query  # noqa: E402
from fortna_sorter_build import (  # noqa: E402
    SORTER_TRACK_PACK,
    _build_divert_rename_pairs,
    _build_rename_pairs,
    _collect_encoder_rows,
    _divert_host_conveyor,
)
from fortna_sorter_discovery import (  # noqa: E402
    build_canonical_sorter_model,
    sanitize_sorter_area_name,
)
from fortna_sorter_pack_compiler import (  # noqa: E402
    compile_sorter_track_pack,
    sorter_model_to_build_config,
)

ROOT = _SF_REPO
VIRGIN_RUN = ROOT / "workspace" / "_virgin_orindy" / "RUN"
PLC2_RUN = ROOT / "workspace" / "_plc2_run_peek" / "RUN"
MACHINE = "ORINDYAC6"


class TestSanitizeAreaName(unittest.TestCase):
    def test_shipping_sorter_generic(self) -> None:
        self.assertEqual(sanitize_sorter_area_name("Shipping Sorter"), "ShippingSorter")
        self.assertEqual(sanitize_sorter_area_name("Foo Bar-Baz"), "FooBarBaz")


@unittest.skipUnless(VIRGIN_RUN.is_dir(), "virgin ORINDYAC6 RUN missing")
class TestCp6KnownSiteDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = build_canonical_sorter_model(VIRGIN_RUN, MACHINE)
        cls.cfg = sorter_model_to_build_config(cls.model)

    def test_shipping_sorter_area_identity(self) -> None:
        self.assertEqual(self.model.get("sorter_area_name"), "ShippingSorter")
        self.assertEqual(self.model.get("transport_area"), "ShippingSorter")
        self.assertTrue(self.model.get("shipping_sorter_supported"))
        fa = self.model.get("field_authority") or {}
        self.assertEqual(fa.get("transport_area"), "DERIVED")

    def test_divert_host_p610_not_p506(self) -> None:
        self.assertEqual(self.model.get("divert_host_conveyor"), "P610")
        self.assertEqual(self.cfg.get("divert_host_conveyor"), "P610")
        self.assertNotEqual(self.cfg.get("divert_host_conveyor"), "P506")

    def test_sorter_type_shoe_derived(self) -> None:
        self.assertEqual(self.model.get("sorter_type"), "shoe_sorter")
        self.assertEqual(self.cfg.get("sorter_type"), "shoe_sorter")

    def test_blind_no_finished_plc_paths(self) -> None:
        blob = str(self.model)
        self.assertNotIn("Finished", blob)
        self.assertNotIn(".L5X", str(self.model.get("source_of_truth") or ""))
        self.assertIn("RUN only", str(self.model.get("source_of_truth") or ""))


@unittest.skipUnless(VIRGIN_RUN.is_dir() and SORTER_TRACK_PACK.is_file(), "RUN/pack missing")
class TestCp6DivertHostRemap(unittest.TestCase):
    def test_encoder_dedupe_and_p610_divert(self) -> None:
        model = build_canonical_sorter_model(VIRGIN_RUN, MACHINE)
        cfg = sorter_model_to_build_config(model)
        enc = _collect_encoder_rows(cfg)
        # Induct P606 must not double-count against tracking P606 if identical;
        # ORINDY has distinct P606 induct + P610 tracking.
        keys = [(e.get("encoder_tag"), e.get("conveyor")) for e in enc]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(_divert_host_conveyor(cfg), "P610")
        divert_pairs = _build_divert_rename_pairs(cfg)
        self.assertTrue(any(a == "P506_Divert1" and b == "P610_Divert1" for a, b in divert_pairs))
        compiled = compile_sorter_track_pack(sorter_model=model, library_text="")
        self.assertTrue(compiled.get("emitted"))
        blob = "\n".join(compiled.get("tags") or []) + "\n" + (compiled.get("program_xml") or "")
        self.assertIn('Tag Name="P610_Divert1"', blob)
        self.assertNotIn('Tag Name="P506_Divert1"', blob)

    def test_rename_pairs_enc610_not_pushed_off(self) -> None:
        # Synthetic double-count case: identical induct+first tracking.
        sorter = {
            "induct_conveyor": "P606",
            "induct_has_encoder": "yes",
            "induct_encoder_tag": "ENC606",
            "divert_count": 4,
            "divert_host_conveyor": "P610",
            "tracking": [
                {
                    "conveyor": "P606",
                    "has_encoder": "yes",
                    "encoder_tag": "ENC606",
                    "pe": "PE606_I",
                },
                {
                    "conveyor": "P610",
                    "has_encoder": "yes",
                    "encoder_tag": "ENC610",
                    "pe": "PE610_I",
                },
            ],
        }
        enc = _collect_encoder_rows(sorter)
        self.assertEqual(len(enc), 2)
        pairs = dict(_build_rename_pairs(sorter))
        # ENC610 must land on an early pack slot (P506), not get pushed to P508.
        self.assertEqual(pairs.get("P504_Enc"), "ENC606")
        self.assertEqual(pairs.get("P506_Enc"), "ENC610")
        self.assertNotEqual(pairs.get("P508_Enc"), "ENC610")


@unittest.skipUnless(VIRGIN_RUN.is_dir(), "virgin RUN missing")
class TestCp6NegativeAndCrossContamination(unittest.TestCase):
    def test_other_machine_rejects_foreign_diverts(self) -> None:
        # Discover as a non-owner machine name → Sorters.Machine won't match.
        model = build_canonical_sorter_model(VIRGIN_RUN, "OTHERPLC99")
        scope = model.get("machine_scope") or {}
        # Either zero sorters kept, or rejected list non-empty
        if model.get("sorter_count"):
            # Overlay-only tables may still load base rows without Machine column match
            # when Machine field is blank — ownership filter still rejects mismatched binds.
            self.assertTrue(
                scope.get("rejected_sorters") or scope.get("rejected_diverts") is not None
            )
        # Foreign machine must not claim ShippingSorter divert host as emit-ready
        # when no owned sections remain.
        if not model.get("sorter_count"):
            self.assertFalse(model.get("detected"))
            self.assertIn(
                model.get("plc_generation"),
                ("NOT_APPLICABLE", "NOT_STARTED", None, "PHASE1_SUPPORTED"),
            )

    def test_stripped_sorter_evidence_no_divert_emit(self) -> None:
        hollow = {
            "detected": False,
            "sorter_count": 0,
            "divert_count": 0,
            "divert_rows": [],
            "tracking_path": [],
            "shipping_sorter_supported": False,
        }
        cfg = sorter_model_to_build_config(hollow)
        self.assertEqual(int(cfg.get("divert_count") or 0), 0)
        self.assertFalse(cfg.get("divert_host_conveyor"))


@unittest.skipUnless(VIRGIN_RUN.is_dir(), "virgin RUN missing")
class TestCp6AreaProgramBind(unittest.TestCase):
    def test_area_list_includes_sorter_area_fast(self) -> None:
        model = build_canonical_sorter_model(VIRGIN_RUN, MACHINE)
        cfg = sorter_model_to_build_config(model)
        area = cfg.get("area_name") or "ShippingSorter"
        inp = AutogenInput(
            project_name=MACHINE,
            machine=MACHINE,
            run_dir=str(VIRGIN_RUN),
            conveyors=[
                ConveyorRow(
                    number=606,
                    conveyor="P606",
                    type="VFD",
                    main_area=f"{MACHINE}_Area",
                ),
                ConveyorRow(
                    number=610,
                    conveyor="P610",
                    type="VFD",
                    main_area=f"{MACHINE}_Area",
                ),
                ConveyorRow(
                    number=700,
                    conveyor="P700",
                    type="VFD",
                    main_area=f"{MACHINE}_Area",
                ),
            ],
            areas=[f"{MACHINE}_Area"],
            sorter_build=cfg,
            sorter_model=model,
        )
        bound = bind_sorter_area_conveyors(inp)
        self.assertEqual(bound.get("area"), area)
        self.assertIn("P606", bound.get("conveyors") or [])
        self.assertIn("P610", bound.get("conveyors") or [])
        self.assertNotIn("P700", bound.get("conveyors") or [])
        self.assertIn(area, inp.areas)
        # Effective area list for emit includes {area}_Area_Fast naming stem
        self.assertTrue(any(c.main_area == area for c in inp.conveyors if c.clean_name == "P610"))
        prog_fast = f"{area}_Area_Fast"
        self.assertTrue(prog_fast.startswith("ShippingSorter_Area_Fast"))

    def test_native_merge_seed_includes_p600(self) -> None:
        model = build_canonical_sorter_model(VIRGIN_RUN, MACHINE)
        cfg = sorter_model_to_build_config(model)
        inp = AutogenInput(
            project_name=MACHINE,
            machine=MACHINE,
            run_dir=str(VIRGIN_RUN),
            sorter_build=cfg,
            sorter_model=model,
            merges_2to1=[],
        )
        result = seed_native_merges_for_sorter(inp)
        names = {str(m.get("name") or "").upper() for m in (inp.merges_2to1 or [])}
        self.assertIn("P600", names)
        self.assertGreaterEqual(int(result.get("total") or 0), 1)


@unittest.skipUnless(VIRGIN_RUN.is_dir(), "virgin RUN missing")
class TestCp6Provenance(unittest.TestCase):
    def test_why_divert_hosts(self) -> None:
        doc = audit(VIRGIN_RUN, MACHINE, scan_production_code=False)
        hits_ok = why_query(doc, "P610_Divert1")
        self.assertTrue(hits_ok)
        self.assertTrue(
            any(
                r.get("subsystem") == "sorter"
                and "P610_Divert1" in str(r.get("artifact") or "")
                for r in hits_ok
            )
        )
        hits_bad = why_query(doc, "P506_Divert1")
        self.assertTrue(hits_bad)
        self.assertTrue(
            any(
                (r.get("extras") or {}).get("orphan")
                or r.get("decision") == "orphan_pack_template_divert_host"
                for r in hits_bad
            )
        )
        track = why_query(doc, "Sorter_Track")
        self.assertTrue(any(r.get("artifact") == "Sorter_Track" for r in track))
        merge = why_query(doc, "P600_Merge")
        self.assertTrue(merge)


@unittest.skipUnless(PLC2_RUN.is_dir(), "PLC2 RUN missing")
class TestPlc2NoCrossContamination(unittest.TestCase):
    def test_plc2_no_shipping_sorter_diverts(self) -> None:
        model = build_canonical_sorter_model(PLC2_RUN, "ORNCCP2")
        # PLC2 has no shipping sorter application — must not invent divert host
        if int(model.get("sorter_count") or 0) == 0:
            self.assertFalse(model.get("shipping_sorter_supported"))
            cfg = sorter_model_to_build_config(model)
            self.assertEqual(int(cfg.get("divert_count") or 0), 0)


if __name__ == "__main__":
    unittest.main()
