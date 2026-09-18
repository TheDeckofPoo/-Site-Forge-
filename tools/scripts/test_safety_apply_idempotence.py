#!/usr/bin/env python3
"""Safety Apply idempotence — Gate C.

Root cause of [object Object]_ESZone1: workbook.areas held area *objects*
and JS did String(area) → "[object Object]" when minting preferred zone names.

Apply Safety must reconcile by zone identity (update), never append copies.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
SAFETY_JS = ROOT / "dashboard" / "safety-build.js"
FLEX_RACK = ROOT / "dashboard" / "hardware" / "flex-rack.js"
FLEX_CSS = ROOT / "dashboard" / "hardware" / "flex-hardware.css"


def area_name_of(a) -> str:
    """Mirror dashboard/safety-build.js areaNameOf."""
    if a is None:
        return ""
    if isinstance(a, (str, int, float)):
        s = str(a).strip()
        if not s or s == "[object Object]":
            return ""
        return s
    if isinstance(a, dict):
        s = str(a.get("name") or a.get("id") or a.get("area") or a.get("areaName") or "").strip()
        if not s or s == "[object Object]":
            return ""
        return s
    return ""


def is_corrupt_zone_name(name: str) -> bool:
    s = str(name or "")
    return (not s) or bool(re.search(r"\[object\s+Object\]", s, re.I))


_PLACEHOLDER_AREA_RE = re.compile(r"^Zone([1-9])_Area$", re.I)
_PLACEHOLDER_ZONE_RE = re.compile(r"^Zone([1-9])_ESZone\d*$", re.I)
_NUMERIC_STEM_ZONE_RE = re.compile(r"^(\d{2,})_ESZone\d*$", re.I)


def is_placeholder_or_test_zone_name(name: str) -> bool:
    s = str(name or "").strip()
    if not s or is_corrupt_zone_name(s):
        return True
    if _PLACEHOLDER_ZONE_RE.match(s) or _NUMERIC_STEM_ZONE_RE.match(s):
        return True
    return False


def preferred_es_zone(area) -> str | None:
    """Suggestion only — Gate R forbids auto-persisting these from area names alone."""
    an = area_name_of(area)
    if not an or is_corrupt_zone_name(an):
        return None
    if _PLACEHOLDER_AREA_RE.match(an):
        return None
    stem = re.sub(r"_Area$", "", an, flags=re.I)
    if not stem or is_corrupt_zone_name(stem) or re.match(r"^\d{2,}$", stem):
        return None
    return f"{stem}_ESZone1"


def build_zones_from_areas(areas, existing_zones: list[dict] | None = None) -> list[dict]:
    """Reconcile by identity — Gate R: do NOT mint AUTO_DEFAULT from area names."""
    by_name: dict[str, dict] = {}
    for ez in existing_zones or []:
        name = str(ez.get("source_id") or ez.get("name") or ez.get("id") or "").strip()
        if not name or is_corrupt_zone_name(name):
            continue
        # Drop unused Zone1..Zone9 / numeric test shells unless engineer-authored
        if is_placeholder_or_test_zone_name(name) and not (
            ez.get("engineerEdited") and (ez.get("members") or [])
        ):
            continue
        area_ref = area_name_of(ez.get("areaRef") or ez.get("area"))
        members = []
        seen = set()
        for m in ez.get("members") or []:
            nm = str(m or "").strip()
            if not nm:
                continue
            key = nm.upper()
            if key in seen:
                continue
            seen.add(key)
            members.append(nm)
        eng_name = str(ez.get("engineering_name") or ez.get("name") or name).strip()
        by_name[name] = {
            "source_id": name,
            "name": eng_name,
            "engineering_name": eng_name,
            "areaRef": area_ref,
            "members": members,
            "engineerEdited": bool(ez.get("engineerEdited")),
        }
    # Gate R — areas alone do not invent Safety zones into production
    _ = areas
    return [z for z in by_name.values() if not is_corrupt_zone_name(z["name"])]


def apply_safety(zones: list[dict], areas) -> list[dict]:
    """Apply = rebuild/reconcile; must converge."""
    return build_zones_from_areas(areas, existing_zones=zones)


class TestSafetyApplyIdempotence(unittest.TestCase):
    def test_area_object_does_not_mint_object_object_zone(self) -> None:
        areas = [{"id": "a1", "name": "Trans Test_Area"}]
        # Gate R — areas alone do not invent zones
        zones = build_zones_from_areas(areas)
        self.assertEqual(zones, [])
        self.assertIsNone(preferred_es_zone({"name": "[object Object]"}))

    def test_apply_five_times_converges(self) -> None:
        areas = [{"id": "a1", "name": "Trans Test_Area"}]
        zones = [
            {
                "source_id": "Trans_Test_ESZone1",
                "name": "Trans_Test_ESZone1",
                "engineering_name": "Trans_Test_ESZone1",
                "areaRef": "Trans Test_Area",
                "members": ["ES500", "ES406"],
                "engineerEdited": True,
            }
        ]
        assign = ["ES500", "ES406"]
        snapshots = []
        for _ in range(5):
            zones = apply_safety(zones, areas)
            z = next(x for x in zones if x["source_id"] == "Trans_Test_ESZone1")
            z["members"] = list(assign)
            z["engineerEdited"] = True
            snapshots.append(
                (
                    len(zones),
                    tuple(sorted(x["source_id"] for x in zones)),
                    tuple(sorted(z["members"])),
                )
            )
        self.assertEqual(len(set(snapshots)), 1, msg=f"non-idempotent: {snapshots}")
        self.assertEqual(snapshots[0][0], 1)
        self.assertNotIn("[object Object]_ESZone1", snapshots[0][1])

    def test_corrupt_zone_dropped_on_reconcile(self) -> None:
        areas = [{"name": "Trans Test_Area"}]
        existing = [
            {
                "source_id": "Trans_Test_ESZone1",
                "name": "Trans_Test_ESZone1",
                "areaRef": "Trans Test_Area",
                "members": ["ES1"],
                "engineerEdited": True,
            },
            {"name": "[object Object]_ESZone1", "areaRef": "[object Object]", "members": ["ES1"]},
        ]
        zones = apply_safety(existing, areas)
        names = [z["name"] for z in zones]
        self.assertEqual(names, ["Trans_Test_ESZone1"])
        self.assertEqual(zones[0]["members"], ["ES1"])

    def test_duplicate_members_deduped(self) -> None:
        areas = ["ModuleA_Area"]
        existing = [
            {
                "source_id": "ModuleA_ESZone1",
                "name": "ModuleA_ESZone1",
                "areaRef": "ModuleA_Area",
                "members": ["ES1", "es1", "ES2", "ES2"],
                "engineerEdited": True,
            }
        ]
        zones = apply_safety(existing, areas)
        # case-preserving first occurrence; case-insensitive dedupe
        self.assertEqual([m.upper() for m in zones[0]["members"]], ["ES1", "ES2"])

    def test_zone1_placeholder_does_not_persist(self) -> None:
        areas = ["ORNCCP5_Area", "Zone1_Area"]
        existing = [
            {"name": "ORNCCP5_ESZone1", "areaRef": "ORNCCP5_Area", "members": []},
            {"name": "Zone1_ESZone1", "areaRef": "ORNCCP5_Area", "members": []},
            {"name": "Zone9_ESZone1", "areaRef": "ORNCCP5_Area", "members": []},
            {"name": "123456_ESZone1", "areaRef": "123456", "members": []},
        ]
        zones = apply_safety(existing, areas)
        names = {z["name"] for z in zones}
        self.assertIn("ORNCCP5_ESZone1", names)
        self.assertNotIn("Zone1_ESZone1", names)
        self.assertNotIn("Zone9_ESZone1", names)
        self.assertNotIn("123456_ESZone1", names)

    def test_source_has_area_name_of_guard(self) -> None:
        text = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("function areaNameOf", text)
        self.assertIn("function isCorruptZoneName", text)
        self.assertIn("function isPlaceholderOrTestZoneName", text)
        self.assertIn("[object Object]", text)  # explicit guard, not a mute-only filter
        # Gate R — must not auto-create ${stem}_ESZone1 for every workbook area
        self.assertIn("do NOT auto-create", text)
        self.assertIn("AUTO_DEFAULT", text)


class TestFlexAdapterVisualCleanup(unittest.TestCase):
    def test_no_port_divs_in_adapter_markup(self) -> None:
        js = FLEX_RACK.read_text(encoding="utf-8", errors="replace")
        # renderAdapterFace must not emit flex-port jack rectangles
        start = js.index("function renderAdapterFace")
        end = js.index("function renderIoFace", start)
        face = js[start:end]
        self.assertNotIn('class="flex-port', face)
        self.assertIn("flex-adapter-clean", face)
        self.assertIn("flex-cat", face)

    def test_flex_io_width_preserved(self) -> None:
        css = FLEX_CSS.read_text(encoding="utf-8", errors="replace")
        self.assertRegex(css, r"\.flex-io\s*\{[^}]*width:\s*84px")
        self.assertRegex(css, r"\.flex-adapter\s*\{[^}]*width:\s*100px")
        self.assertIn("display: none", css)  # ports hidden


if __name__ == "__main__":
    unittest.main(verbosity=2)
