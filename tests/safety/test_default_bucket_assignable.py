#!/usr/bin/env python3
"""Default Safety ownership bucket devices must be assignable to engineer zones.

Reproduces Curtis' virgin MSCRENOPICK screen:
  site_devices = N, operational assignments = 0
  → unassigned = N, available for new engineer zone = N
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_SF_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SF_REPO / "tools" / "scripts"))

from fortna_safety_model import (  # noqa: E402
    DEFAULT_SAFETY_NAME,
    build_safety_model,
    safety_zone_is_default,
)

RUN = (
    _SF_REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
    / "RUN"
)


def _gui_available_for_engineer_zone(model: dict, zone_name: str) -> list[str]:
    """Mirror dashboard/safety-build.js::renderDeviceLists eligibility."""
    assigned = {
        str(m).upper()
        for z in (model.get("zones") or [])
        if str(z.get("name") or "") == zone_name
        for m in (z.get("members") or [])
    }
    avail: list[str] = []
    for d in model.get("devices") or []:
        name = str(d.get("name") or "").strip()
        if not name or name.upper() in assigned:
            continue
        st = str(d.get("status") or "").upper()
        ref = str(d.get("safetyZoneRef") or "").strip()
        # Default/Unassigned bucket is eligible
        if st in ("UNASSIGNED", "") or d.get("defaultSafety") is True:
            avail.append(name)
            continue
        if not ref or safety_zone_is_default({"name": ref}):
            avail.append(name)
            continue
        if ref.upper() == zone_name.upper():
            avail.append(name)
    return avail


@unittest.skipUnless((RUN / "project.cfg").is_file(), "MSCRENOPICK RUN missing")
class TestDefaultBucketAssignable(unittest.TestCase):
    def test_virgin_all_unassigned_are_available(self) -> None:
        model = build_safety_model(
            run_dir=RUN,
            machine="MSCRENOPICK",
            engineer_safety_build={
                "zones": [
                    {
                        "name": "pick_one_ESZone1",
                        "members": [],
                        "engineerEdited": True,
                        "operational": True,
                    }
                ]
            },
        )
        c = model.get("counts") or {}
        found = int(c.get("devices_found") or c.get("site_devices") or 0)
        unassigned = int(c.get("unassigned") or 0)
        auto_n = int(c.get("automatically_resolved") or 0)
        eng_n = int(c.get("engineer_assigned") or 0)
        self.assertGreater(found, 0)
        self.assertEqual(unassigned, found, "operational assignments=0 ⇒ all unassigned")
        self.assertEqual(auto_n, 0)
        self.assertEqual(eng_n, 0)
        # Conservation law — FAIL if broken
        self.assertEqual(
            found,
            auto_n + eng_n + unassigned,
            "devices_found = auto_resolved + engineer_assigned + unassigned",
        )
        self.assertTrue(c.get("conservation_ok"), "conservation_ok must be True")

        # Backend stamps Default Safety ref while status stays UNASSIGNED
        for d in model.get("devices") or []:
            if d.get("status") == "UNASSIGNED":
                self.assertTrue(
                    d.get("defaultSafety")
                    or str(d.get("safetyZoneRef") or "") in ("", DEFAULT_SAFETY_NAME)
                    or safety_zone_is_default({"name": d.get("safetyZoneRef")}),
                )

        avail = _gui_available_for_engineer_zone(model, "pick_one_ESZone1")
        self.assertEqual(
            len(avail),
            unassigned,
            f"available for engineer zone must equal unassigned ({unassigned}), got {len(avail)}",
        )

    def test_default_zone_members_never_auto_resolved(self) -> None:
        """If Default Safety is present as a zone with members, do not AUTO_RESOLVE."""
        model = build_safety_model(
            run_dir=RUN,
            machine="MSCRENOPICK",
            engineer_safety_build={
                "zones": [
                    {
                        "name": DEFAULT_SAFETY_NAME,
                        "members": ["ESPB24", "ESPB2"],
                        "operational": False,
                        "isDefault": True,
                    },
                    {
                        "name": "pick_one_ESZone1",
                        "members": [],
                        "engineerEdited": True,
                        "operational": True,
                    },
                ]
            },
        )
        by_name = {
            str(d.get("name") or "").upper(): d for d in (model.get("devices") or [])
        }
        for n in ("ESPB24", "ESPB2"):
            d = by_name.get(n)
            if not d:
                continue
            self.assertEqual(d.get("status"), "UNASSIGNED")
            self.assertNotEqual(d.get("status"), "AUTO_RESOLVED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
