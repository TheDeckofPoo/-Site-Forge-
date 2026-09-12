#!/usr/bin/env python3
"""Synthetic non-Greensboro SiteModel fixtures for blind genericity tests.

Names intentionally avoid Greensboro / ORNCCP / PLC2 / PLC4 literals.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_site_model import (  # noqa: E402
    AVAILABLE,
    EXCLUDED,
    GEN_CFG,
    GEN_NOT_SUPPORTED,
    HISTORICAL_OR_STALE,
    INCLUDED,
    PROV_ENGINEER,
    PROV_RUN_DERIVED,
    PROV_RUN_EXPLICIT,
    SCOPE_BASE_ONLY,
    SCOPE_HISTORICAL,
    SCOPE_OVERLAY,
    make_object,
    make_relationship,
)

FORBIDDEN_SITE_LEAKS = ("Greensboro", "ORNCCP", "PLC2", "PLC4")


def _pe(
    name: str,
    *,
    inclusion: str = INCLUDED,
    evidence: list[dict[str, Any]] | None = None,
    **attrs: Any,
) -> dict[str, Any]:
    return make_object(
        "photoeye",
        name,
        provenance=PROV_RUN_EXPLICIT,
        inclusion=inclusion,
        confidence="HIGH",
        evidence=evidence or [],
        **attrs,
    ).to_dict()


def _eq(name: str, *, inclusion: str = INCLUDED, **attrs: Any) -> dict[str, Any]:
    return make_object(
        "equipment",
        name,
        provenance=PROV_RUN_EXPLICIT,
        inclusion=inclusion,
        confidence="HIGH",
        equipment_type="STRAIGHT",
        **attrs,
    ).to_dict()


def _base_site(machine: str, site_label: str) -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "machine_scope": machine,
        "run_dir": f"synthetic/{site_label}",
        "source_of_truth": "RUN + engineer overrides only — finished PLC not read",
        "controllers": [
            make_object(
                "controller",
                machine,
                provenance=PROV_RUN_EXPLICIT,
                inclusion=INCLUDED,
                confidence="HIGH",
                source_scope=SCOPE_OVERLAY,
            ).to_dict()
        ],
        "areas": [
            make_object(
                "area",
                "Alpha_Area",
                provenance=PROV_ENGINEER,
                inclusion=INCLUDED,
                confidence="HIGH",
                area_id="Alpha_Area",
            ).to_dict()
        ],
        "equipment": [],
        "motors": [],
        "vfds": [],
        "photoeyes": [],
        "encoders": [],
        "estop_zones": [],
        "sawtooth_merges": [],
        "sorters": [],
        "tracking_systems": [],
        "wcs_interfaces": [],
        "relationships": [],
        "operational_groups": {
            "engineering_areas": [],
            "estop_zones": [],
            "startstop_zones": [],
            "jam_zones": [],
            "full_groups": [],
            "sorter_zones": [],
        },
        "decision_traces": [],
        "superseded_candidates": [],
        "unresolved": [],
        "notes": [],
    }


def TRANSPORT_SITE() -> dict[str, Any]:
    """Straight transport with motor chain, jam/full PEs, stale row, overlay, late PE."""
    site = _base_site("AlphaCtrl1", "AlphaSite")
    site["equipment"] = [
        _eq("P9001", area_id="Alpha_Area", motor="M9001", source_scope=SCOPE_OVERLAY),
        _eq("P9002", area_id="Alpha_Area", motor="M9002", source_scope=SCOPE_OVERLAY),
        _eq(
            "P8099",
            inclusion=AVAILABLE,
            active_state=HISTORICAL_OR_STALE,
            source_scope=SCOPE_HISTORICAL,
            area_id="Alpha_Area",
        ),
        _eq(
            "P9010",
            area_id="Alpha_Area",
            motor="M9010",
            source_scope=SCOPE_BASE_ONLY,
            evidence=[{"kind": "added_late", "note": "late conveyor"}],
        ),
    ]
    site["motors"] = [
        make_object(
            "motor",
            "M9001",
            provenance=PROV_RUN_EXPLICIT,
            inclusion=INCLUDED,
            confidence="HIGH",
            linked_conveyor="P9001",
            source_scope=SCOPE_OVERLAY,
        ).to_dict(),
        make_object(
            "motor",
            "M9002",
            provenance=PROV_RUN_EXPLICIT,
            inclusion=INCLUDED,
            confidence="HIGH",
            linked_conveyor="P9002",
            source_scope=SCOPE_OVERLAY,
        ).to_dict(),
        make_object(
            "motor",
            "M9010",
            provenance=PROV_RUN_EXPLICIT,
            inclusion=INCLUDED,
            confidence="HIGH",
            linked_conveyor="P9010",
        ).to_dict(),
        make_object(
            "motor",
            "M_REMOVED",
            provenance=PROV_RUN_DERIVED,
            inclusion=EXCLUDED,
            confidence="HIGH",
            active_state=HISTORICAL_OR_STALE,
            source_scope=SCOPE_HISTORICAL,
            evidence=[{"kind": "removed_device"}],
        ).to_dict(),
    ]
    site["photoeyes"] = [
        _pe(
            "PE9001_J",
            linked_conveyor="P9001",
            evidence=[{"kind": "jamcheck_link"}],
        ),
        _pe(
            "PE9001_F",
            linked_conveyor="P9001",
            evidence=[{"kind": "fullline_link"}],
        ),
        _pe(
            "PE9002_JF",
            linked_conveyor="P9002",
            evidence=[{"kind": "fulljam_link"}],
        ),
        _pe(
            "PE9010_P",
            linked_conveyor="P9010",
            evidence=[{"kind": "pe_assignment"}, {"kind": "added_late"}],
        ),
    ]
    site["relationships"] = [
        make_relationship(
            source="M9001",
            target="P9001",
            kind="motor_link",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
            source_table="Conveyor.asc",
        ),
        make_relationship(
            source="M9002",
            target="P9002",
            kind="motor_link",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
            source_table="Conveyor.asc",
        ),
        make_relationship(
            source="M9001",
            target="M9002",
            kind="mtrchain",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
            source_table="Mtrchain.asc",
        ),
        make_relationship(
            source="PE9001_J",
            target="P9001",
            kind="jamcheck_link",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
            source_table="Jamcheck.asc",
        ),
        make_relationship(
            source="PE9001_F",
            target="P9001",
            kind="fullline_link",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
            source_table="Fullline.asc",
        ),
        make_relationship(
            source="PE9002_JF",
            target="P9002",
            kind="fulljam_link",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
            source_table="Fulljam.asc",
        ),
        make_relationship(
            source="P9001",
            target="P9002",
            kind="path_link",
            provenance=PROV_RUN_DERIVED,
            confidence="MEDIUM",
        ),
    ]
    site["operational_groups"] = {
        "engineering_areas": list(site["areas"]),
        "estop_zones": [
            make_object(
                "estop_zone",
                "Alpha_ES1",
                provenance=PROV_RUN_EXPLICIT,
                inclusion=INCLUDED,
            ).to_dict()
        ],
        "startstop_zones": [
            make_object(
                "startstop_zone",
                "Alpha_SS1",
                provenance=PROV_RUN_EXPLICIT,
                inclusion=INCLUDED,
            ).to_dict()
        ],
        "jam_zones": [
            make_object(
                "jam_zone",
                "Alpha_Jam1",
                provenance=PROV_RUN_EXPLICIT,
                inclusion=INCLUDED,
            ).to_dict()
        ],
        "full_groups": [],
        "sorter_zones": [],
    }
    site["estop_zones"] = list(site["operational_groups"]["estop_zones"])
    return site


def MERGE_SITE() -> dict[str, Any]:
    """Simple merge with presence / release eyes (non-Greensboro)."""
    site = _base_site("BetaCtrlA", "BetaMergeSite")
    site["equipment"] = [
        _eq("P9101", area_id="Alpha_Area", motor="M9101"),
        _eq("P9102", area_id="Alpha_Area", motor="M9102"),
        _eq("P9103", area_id="Alpha_Area", motor="M9103"),
    ]
    site["motors"] = [
        make_object(
            "motor", n, provenance=PROV_RUN_EXPLICIT, inclusion=INCLUDED, confidence="HIGH"
        ).to_dict()
        for n in ("M9101", "M9102", "M9103")
    ]
    site["photoeyes"] = [
        _pe("PE9101_P", linked_conveyor="P9101", evidence=[{"kind": "merge_link"}]),
        _pe("PE9102_P", linked_conveyor="P9102", evidence=[{"kind": "merge_link"}]),
        _pe("PE9103_P", linked_conveyor="P9103", evidence=[{"kind": "merge_link"}]),
    ]
    site["merges"] = [
        make_object(
            "merge",
            "MergeBoss_Alpha1",
            provenance=PROV_RUN_EXPLICIT,
            inclusion=INCLUDED,
            confidence="HIGH",
            merge_type="SimpleMerge",
            inputs=["P9101", "P9102"],
            output="P9103",
        ).to_dict()
    ]
    site["relationships"] = [
        make_relationship(
            source="PE9101_P",
            target="MergeBoss_Alpha1",
            kind="merge_link",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
            source_table="MergeBoss.asc",
        ),
        make_relationship(
            source="P9101",
            target="P9103",
            kind="merge_link",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
        ),
        make_relationship(
            source="P9102",
            target="P9103",
            kind="merge_link",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
        ),
    ]
    return site


def SAWTOOTH_SITE() -> dict[str, Any]:
    """Sawtooth merge with partial lane fields (reservation unknowns)."""
    site = _base_site("GammaCtrlX", "GammaSawSite")
    site["equipment"] = [
        _eq("P9201", area_id="Alpha_Area", motor="M9201"),
        _eq("P9202", area_id="Alpha_Area", motor="M9202"),
        _eq("P9209", area_id="Alpha_Area", motor="M9209"),
    ]
    site["motors"] = [
        make_object(
            "motor", n, provenance=PROV_RUN_EXPLICIT, inclusion=INCLUDED, confidence="HIGH"
        ).to_dict()
        for n in ("M9201", "M9202", "M9209")
    ]
    site["vfds"] = [
        make_object(
            "vfd",
            "VFD9201",
            provenance=PROV_RUN_EXPLICIT,
            inclusion=INCLUDED,
            confidence="HIGH",
            linked_conveyor="P9201",
        ).to_dict()
    ]
    site["encoders"] = [
        make_object(
            "encoder",
            "ENC_GAMMA1",
            provenance=PROV_RUN_EXPLICIT,
            inclusion=INCLUDED,
            confidence="HIGH",
        ).to_dict()
    ]
    site["photoeyes"] = [
        _pe("PE9201_P", linked_conveyor="P9201", evidence=[{"kind": "saw_lane"}]),
        _pe("PE9202_P", linked_conveyor="P9202", evidence=[{"kind": "saw_lane"}]),
        _pe("PE9201_F", linked_conveyor="P9201", evidence=[{"kind": "fullline_link"}]),
    ]
    site["sawtooth_merges"] = [
        {
            **make_object(
                "sawtooth_merge",
                "SawMerge_Gamma1",
                provenance=PROV_RUN_EXPLICIT,
                inclusion=INCLUDED,
                confidence="HIGH",
                generation_state=GEN_CFG,
                motor_io="M9209",
                encoder="ENC_GAMMA1",
                area_id="Alpha_Area",
            ).to_dict(),
            "merge_type": "SawMerge",
            "lanes": [
                {
                    "name": "LaneA",
                    "conveyor": "P9201",
                    "photoeye": "PE9201_P",
                    "drive": "VFD9201",
                    "full_eye": "PE9201_F",
                    # reservation fields intentionally unknown
                    "reserve_eye": None,
                    "reserve_time": None,
                    "reservation_mode": None,
                },
                {
                    "name": "LaneB",
                    "conveyor": "P9202",
                    "photoeye": "PE9202_P",
                    "drive": None,
                    "encoder": "ENC_GAMMA1",
                    "reserve_eye": None,
                    "reservation_mode": None,
                },
            ],
        }
    ]
    site["relationships"] = [
        make_relationship(
            source="SawMerge_Gamma1",
            target="PE9201_P",
            kind="saw_lane",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
            source_table="SawLane.asc",
        ),
        make_relationship(
            source="SawMerge_Gamma1",
            target="PE9202_P",
            kind="hssaw_lane",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
            source_table="HSSawLane.asc",
        ),
        make_relationship(
            source="VFD9201",
            target="P9201",
            kind="vfd_link",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
        ),
    ]
    return site


def SORTER_SITE() -> dict[str, Any]:
    """Sorter discovery stub — scan/WCS leaves stay unsupported / config-required."""
    site = _base_site("DeltaCtrlS", "DeltaSorterSite")
    site["equipment"] = [_eq("P9301", area_id="Alpha_Area", motor="M9301")]
    site["encoders"] = [
        make_object(
            "encoder",
            "ENC_DELTA1",
            provenance=PROV_RUN_EXPLICIT,
            inclusion=INCLUDED,
            confidence="HIGH",
        ).to_dict()
    ]
    site["sorters"] = [
        make_object(
            "sorter",
            "Sorter_AlphaMain",
            provenance=PROV_RUN_EXPLICIT,
            inclusion=INCLUDED,
            confidence="MEDIUM",
            generation_state=GEN_NOT_SUPPORTED,
            sorter_type="UnitSorter",
            encoders=["ENC_DELTA1"],
            scan_zones=["ScanZone_A1"],
            scan_bosses=["ScanBoss_A1"],
            runtime_tracking=False,
            wcs_events=["DivertConfirm"],
            machines=["DeltaCtrlS"],
        ).to_dict()
    ]
    site["wcs_interfaces"] = [
        make_object(
            "wcs",
            "WCS_AlphaLink",
            provenance=PROV_RUN_EXPLICIT,
            inclusion=AVAILABLE,
            confidence="MEDIUM",
            generation_state=GEN_NOT_SUPPORTED,
            event="DivertConfirm",
            machine="DeltaCtrlS",
        ).to_dict()
    ]
    site["tracking_systems"] = [
        make_object(
            "tracking",
            "TrackQueue_Alpha",
            provenance=PROV_RUN_DERIVED,
            inclusion=AVAILABLE,
            confidence="LOW",
            generation_state=GEN_NOT_SUPPORTED,
            runtime=True,
        ).to_dict()
    ]
    site["relationships"] = [
        make_relationship(
            source="Sorter_AlphaMain",
            target="ENC_DELTA1",
            kind="sorter_static",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
            source_table="Sorters.asc",
        )
    ]
    return site


class TestBlindGenericityFixtures(unittest.TestCase):
    def test_four_builders_exist(self) -> None:
        builders = (TRANSPORT_SITE, MERGE_SITE, SAWTOOTH_SITE, SORTER_SITE)
        self.assertEqual(len(builders), 4)
        for builder in builders:
            site = builder()
            self.assertIsInstance(site, dict)
            self.assertEqual(site.get("schema_version"), "2.0")
            blob = str(site)
            for leak in FORBIDDEN_SITE_LEAKS:
                self.assertNotIn(leak, blob, msg=f"{builder.__name__} leaked {leak}")

    def test_names_are_non_greensboro(self) -> None:
        site = TRANSPORT_SITE()
        self.assertEqual(site["machine_scope"], "AlphaCtrl1")
        names = {e.get("raw_name") for e in site["equipment"]}
        self.assertIn("P9001", names)
        self.assertTrue(any(p.get("raw_name") == "PE9002_JF" for p in site["photoeyes"]))


if __name__ == "__main__":
    unittest.main()
