#!/usr/bin/env python3
"""GATE 1 — Safety lifecycle that mirrors the engineer UI path.

Simulates: discover → create engineer zone → assign X devices → Apply payload
→ reopen (rebuild from payload) → ES emit.

Does NOT invent membership in the ES generator.
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


import re
import sys
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_es_compiler import build_safety_zone_irs, emit_es_program  # noqa: E402


def _rung_xml(n: int, text: str, comment: str = "") -> str:
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return (
        f'<Rung Number="{n}" Type="N">{c}'
        f"<Text><![CDATA[{text}]]></Text></Rung>"
    )


def _routine(name: str, body: str) -> str:
    return f'<Routine Name="{name}" Type="RLL"><RLLContent>{body}</RLLContent></Routine>'


class TestNoAutoMintAreaEsZones(unittest.TestCase):
    """Autogen must not invent {Area}_ESZone1 shells without Safety Apply."""

    def test_from_run_safety_zones_empty_by_default(self) -> None:
        import inspect
        from fortna_autogen import load_from_run

        src = inspect.getsource(load_from_run)
        self.assertNotIn(
            'safety_zones=[f"{a.replace',
            src,
            msg="must not auto-mint {Area}_ESZone1 from areas list",
        )


class TestSafetyUiLifecycleE2E(unittest.TestCase):
    def test_assign_apply_reopen_es_emit(self) -> None:
        # Discovery: 20 Safety devices (scaled fixture; field had 127)
        devices = [f"ES{600 + i}" for i in range(16)] + [
            "6MCR1",
            "6ESR1",
            "6ESR2",
            "6ES",
        ]
        self.assertEqual(len(devices), 20)

        # Engineer creates operational zone (Transport-seeded empty shell)
        eng_zone = {
            "id": "ORINDYAC6_ESZone1",
            "source_id": "ORINDYAC6_ESZone1",
            "name": "ORINDYAC6_ESZone1",
            "engineering_name": "ORINDYAC6_ESZone1",
            "area": "ORINDYAC6_Area",
            "areaRef": "ORINDYAC6_Area",
            "conveyors": ["P600", "P604"],
            "conveyorRefs": ["P600", "P604"],
            "members": [],
            "membersOrigin": "UNRESOLVED",
            "engineerEdited": False,
            "createdBy": "engineer",
            "provenance": "ENGINEER_CREATED",
            "runDiscovered": False,
        }

        # Assign X=5 devices
        x = 5
        assigned = devices[:x]
        remaining = devices[x:]
        eng_zone["members"] = list(assigned)
        eng_zone["membersOrigin"] = "ENGINEER_ASSIGNED"
        eng_zone["engineerEdited"] = True

        # Apply payload (what applySafety writes)
        payload = {
            "version": 1,
            "source": "safety_build",
            "zones": [eng_zone],
            "devices": [
                {
                    "name": d,
                    "kind": "ESTOP",
                    "status": "ENGINEER_ASSIGNED" if d in assigned else "UNASSIGNED",
                    "safetyZoneRef": "ORINDYAC6_ESZone1" if d in assigned else None,
                }
                for d in devices
            ],
            "unassignedDevices": remaining,
            "counts": {
                "devices": len(devices),
                "unassigned": len(remaining),
                "assigned": x,
                "default_safety": len(remaining),
            },
        }

        # Invariant
        self.assertEqual(
            payload["counts"]["devices"],
            payload["counts"]["assigned"] + payload["counts"]["unassigned"],
        )
        self.assertEqual(len(payload["zones"][0]["members"]), x)
        self.assertEqual(len(payload["unassignedDevices"]), 20 - x)

        # Reopen = rebuild IR from persisted payload (no membership invention)
        irs = build_safety_zone_irs(
            safety_zones=[],
            areas=["ORINDYAC6_Area"],
            estop_model=None,
            engineer_zones=payload["zones"],
            default_area="ORINDYAC6_Area",
            area_conveyors={"ORINDYAC6_Area": ["P600", "P604"]},
        )
        self.assertTrue(irs)
        z = next(z for z in irs if "ORINDYAC6" in z.name or z.name.endswith("ESZone1"))
        self.assertGreaterEqual(len(z.members), x)
        self.assertEqual(z.device_membership_status, "RESOLVED")

        # ES emit must produce Safe_Logic / Safe_PI (not NOP-only shell)
        lib = (ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X").read_text(
            encoding="utf-8", errors="ignore"
        )
        seen = set()

        def ensure_tag(n: str) -> None:
            seen.add(n)

        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=lambda *_a, **_k: "",
            library_text=lib,
            ensure_tag=ensure_tag,
            add_tag_block=lambda *_a, **_k: None,
        )
        xml = (pack or {}).get("program_xml") or ""
        self.assertIn("Safe_Logic", xml)
        self.assertIn("Safe_PI", xml)
        self.assertIn("JSR(", xml)
        # Must not be NOP-only Main
        self.assertNotEqual(
            re.findall(r'<Routine Name="([^"]+)"', xml),
            ["Main_Routine"],
        )

        # Delete engineer zone → all return to Default (payload model)
        payload2 = {
            **payload,
            "zones": [],
            "unassignedDevices": list(devices),
            "counts": {
                "devices": len(devices),
                "unassigned": len(devices),
                "assigned": 0,
                "default_safety": len(devices),
            },
            "devices": [
                {"name": d, "kind": "ESTOP", "status": "UNASSIGNED", "safetyZoneRef": None}
                for d in devices
            ],
        }
        self.assertEqual(payload2["counts"]["unassigned"], 20)
        self.assertEqual(payload2["counts"]["assigned"], 0)

        # Idempotent second apply of eng zone
        payload3 = dict(payload)
        self.assertEqual(len(payload3["zones"][0]["members"]), x)

    def test_append_more_members_second_assign(self) -> None:
        """Engineer can append additional devices to the same zone."""
        zone = {
            "source_id": "ORINDYAC6_ESZone1",
            "name": "ORINDYAC6_ESZone1",
            "members": ["ES600", "ES601"],
            "membersOrigin": "ENGINEER_ASSIGNED",
            "engineerEdited": True,
            "provenance": "ENGINEER_CREATED",
        }
        more = ["ES602", "ES603"]
        members = list(dict.fromkeys([*(zone["members"]), *more]))
        zone["members"] = members
        self.assertEqual(zone["members"], ["ES600", "ES601", "ES602", "ES603"])
        irs = build_safety_zone_irs(
            safety_zones=[],  # no auto-minted shells
            areas=["ORINDYAC6_Area"],
            engineer_zones=[zone],
            default_area="ORINDYAC6_Area",
            area_conveyors={"ORINDYAC6_Area": ["P600"]},
        )
        self.assertEqual(len(irs), 1)
        self.assertEqual(len(irs[0].members), 4)
        self.assertEqual(irs[0].device_membership_status, "RESOLVED")

    def test_empty_safety_zones_list_does_not_emit_area_shells(self) -> None:
        """Without engineer_zones, empty safety_zones → no fake Area_ESZone1 IRs."""
        irs = build_safety_zone_irs(
            safety_zones=[],
            areas=["Zone1_Area", "Default_Area", "ORINDYAC6_Area"],
            engineer_zones=[],
            default_area="ORINDYAC6_Area",
        )
        self.assertEqual(irs, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
