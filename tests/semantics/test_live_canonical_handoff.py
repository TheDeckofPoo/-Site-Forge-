#!/usr/bin/env python3
"""LIVE canonical handoff — arbitrary Area/Safety names through production path.

Gate G: do NOT hardcode site names in production. Use unique runtime names.
Simulates Electron: Transport Apply rows + Safety Apply → workbook →
load_from_run + apply_workbook_to_input → build_l5x → parse L5X.

Fails if production falls back to ORNCCP2 defaults when engineer Areas exist.
"""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# Prefer canonical names used by existing tests:
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---


import json
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import AutogenInput, ConveyorRow, build_l5x  # noqa: E402
from fortna_workbook import apply_workbook_to_input  # noqa: E402
from fortna_es_compiler import build_safety_zone_irs, emit_es_program  # noqa: E402
from fortna_studio_preflight import preflight_l5x  # noqa: E402

LIBRARY = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"


def _rung_xml(num: int, text: str, comment: str = "") -> str:
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name: str, rungs: list[str]) -> str:
    body = "".join(
        r.replace('Number="0"', f'Number="{i}"', 1) if 'Number="0"' in r else r
        for i, r in enumerate(rungs)
    )
    return f'<Routine Name="{name}" Type="RLL"><RLLContent>{body}</RLLContent></Routine>'


def _unique(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000) % 100000000}"


def _base_run_input() -> AutogenInput:
    """Simulate load_from_run defaults (site-default Area) before workbook overlay."""
    return AutogenInput(
        project_name="ORNCCP2",
        areas=["ORNCCP2_Area"],
        safety_zones=["ORNCCP2_ESZone1"],
        conveyors=[
            ConveyorRow(
                number=i + 1,
                conveyor=tag,
                main_area="ORNCCP2_Area",
                safety_zone="ORNCCP2_ESZone1",
                type="Transport with MS",
                motor_starter="Yes",
            )
            for i, tag in enumerate(["P400", "P402", "P404", "P406", "P138", "P222", "P1000", "P1001"])
        ],
        include_sys=True,
        include_io_map=True,
    )


def _workbook_for(area: str, zone: str, convs: list[str], members: list[str]) -> dict:
    return {
        "conveyors": [
            {
                "conveyor": t,
                "include": True,
                "main_area": area,
                "safety_zone": zone,
                "type": "Transport with MS",
                "transport_build": True,
                "source": "transport_build_graph",
            }
            for t in convs
        ]
        + [
            # Remaining RUN conveyors stay on default area (partial build)
            {
                "conveyor": t,
                "include": True,
                "main_area": "ORNCCP2_Area",
                "safety_zone": "ORNCCP2_ESZone1",
                "type": "Transport with MS",
            }
            for t in ["P1000", "P1001"]
        ],
        "areas": [area, "ORNCCP2_Area"],
        "safety_build": {
            "version": 1,
            "source": "safety_build",
            "appliedAt": "2026-09-17T23:59:00Z",
            "zones": [
                {
                    "name": zone,
                    "area": area,
                    "areaRef": area,
                    "conveyors": list(convs),
                    "conveyorRefs": list(convs),
                    "members": list(members),
                    "membersOrigin": "ENGINEER_ASSIGNED",
                    "engineerEdited": True,
                    "status": "READY",
                }
            ],
            "unassignedDevices": ["CP3_ESR5"],
            "counts": {
                "devices_found": len(members) + 1,
                "unassigned": 1,
                "engineer_assigned": len(members),
            },
        },
    }


class TestSafetyBuildSurvivesEmptyConveyorsBug(unittest.TestCase):
    """Regression: safety_build alone must not be skipped (Curtis field failure)."""

    def test_safety_only_workbook_still_applies_members(self) -> None:
        inp = _base_run_input()
        wb = {
            # Intentionally NO conveyors key — mirrors hollow Safety Apply write
            "safety_build": {
                "appliedAt": "2026-09-17T23:32:01Z",
                "zones": [
                    {
                        "name": "testt111_ESZone1",
                        "area": "testt111",
                        "conveyors": ["P400", "P402", "P404", "P406"],
                        "members": ["4ES", "5ES", "6ES", "ES422", "CP2_ES", "CP2_ESR1"],
                        "membersOrigin": "ENGINEER_ASSIGNED",
                        "engineerEdited": True,
                    }
                ],
            }
        }
        out = apply_workbook_to_input(inp, wb)
        self.assertTrue(out.safety_zone_members)
        self.assertEqual(out.safety_zone_members[0]["name"], "testt111_ESZone1")
        self.assertEqual(len(out.safety_zone_members[0]["members"]), 6)
        self.assertIn("testt111", out.areas)
        # Conveyors stamped from zone.conveyors
        moved = [c for c in out.conveyors if c.main_area == "testt111"]
        self.assertGreaterEqual(len(moved), 4)


@unittest.skipUnless(LIBRARY.is_file(), "library missing")
class TestArbitraryLiveHandoff(unittest.TestCase):
    def _run_once(self, prefix: str) -> dict:
        area = _unique(prefix)
        zone = f"{area}_ESZone1"
        convs = ["P400", "P402", "P404", "P406"]
        members = ["4ES", "5ES", "ES422", "CP2_ES", "CP2_ESR1", "CP2_MCR1"]
        inp = _base_run_input()
        wb = _workbook_for(area, zone, convs, members)

        # Boundary traces
        trace = {
            "SafetyUI": {"zone": zone, "members": len(members), "area": area},
            "SavedCanonical": {
                "zone": wb["safety_build"]["zones"][0]["name"],
                "members": len(wb["safety_build"]["zones"][0]["members"]),
                "conveyors": len(wb["conveyors"]),
            },
        }
        effective = apply_workbook_to_input(inp, wb)
        trace["EffectiveModel"] = {
            "areas": list(effective.areas),
            "zone_members": len((effective.safety_zone_members or [{}])[0].get("members") or []),
            "area_convs": sum(1 for c in effective.conveyors if c.main_area == area),
        }
        self.assertIn(area, effective.areas, "engineer Area must replace/join RUN defaults")
        self.assertNotEqual(
            effective.areas,
            ["ORNCCP2_Area"],
            "must not fall back to only ORNCCP2_Area",
        )

        irs = build_safety_zone_irs(
            safety_zones=effective.safety_zones,
            areas=effective.areas,
            engineer_zones=list(effective.safety_zone_members or []),
            default_area=area,
            area_conveyors={area: convs},
        )
        ir = next((z for z in irs if z.name == zone or z.name.replace("_", "") == zone.replace("_", "")), None)
        # _safe may alter names slightly — match by containing prefix
        if ir is None:
            ir = next((z for z in irs if area.replace("_", "") in z.name.replace("_", "")), None)
        self.assertIsNotNone(ir, f"IR missing zone for {zone}; got {[z.name for z in irs]}")
        assert ir is not None
        trace["PLCCompiler"] = {"zone": ir.name, "members": len(ir.members)}
        self.assertEqual(len(ir.members), len(members))

        l5x, report = build_l5x(effective, LIBRARY)
        # Program names use Area as-is (may append _Area in some paths)
        progs = re.findall(r'<Program Name="([^"]+)"', l5x)
        area_progs = [p for p in progs if area in p or area.replace("_", "") in p.replace("_", "")]
        # fortna may sanitize area name
        safe_area = re.sub(r"[^\w]", "_", area)
        area_progs = [p for p in progs if safe_area in p or area in p]
        self.assertTrue(
            any(p.endswith("_Fast") for p in area_progs),
            f"missing Fast for {area}; programs={progs}",
        )
        self.assertTrue(any(p.endswith("_Slow") for p in area_progs), progs)
        self.assertTrue(any(p.endswith("_L1") for p in area_progs), progs)
        self.assertTrue(any(p.endswith("_L2") for p in area_progs), progs)

        safe_zone = ir.name
        self.assertIn(f"{safe_zone}_Safe_Logic", l5x)
        self.assertIn(f"{safe_zone}_Safe_PI", l5x)
        self.assertIn("P01_Safety_20ms", l5x)
        self.assertIn(f"JSR({safe_zone}_Safe_Logic", l5x)

        es = report.get("es_program") or {}
        self.assertIn(safe_zone, es.get("emitted_zones") or [])
        self.assertFalse(es.get("shell"))

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "LIVE.L5X"
            path.write_text(l5x, encoding="utf-8")
            pre = preflight_l5x(path)
            self.assertTrue(pre.get("ok"), pre.get("issues")[:5] if pre.get("issues") else pre)

        trace["L5X"] = {
            "area_programs": area_progs,
            "safe_logic": f"{safe_zone}_Safe_Logic" in l5x,
            "safe_pi": f"{safe_zone}_Safe_PI" in l5x,
            "es_emitted": es.get("emitted_zones"),
        }
        return {"area": area, "zone": safe_zone, "trace": trace, "members": len(members)}

    def test_two_arbitrary_names_without_code_change(self) -> None:
        a = self._run_once("ZZ_ACCEPT")
        b = self._run_once("QQ_PROBE")
        self.assertNotEqual(a["area"], b["area"])
        self.assertEqual(a["members"], b["members"])
        out = ROOT / "exports" / "stabilization" / "live_canonical_handoff.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"pass": True, "run_a": a, "run_b": b}, indent=2),
            encoding="utf-8",
        )
        print(f"  [PASS] live handoff evidence → {out}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
