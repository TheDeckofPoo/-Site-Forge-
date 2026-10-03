"""Dump safety_build / safety_zone_members from known-good ORL build."""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "workspace" / ".internal" / "builds" / "20260929-200817" / "autogen_input.json"
OUT = Path(__file__).with_name("orl_known_good_safety_input.json")


def main() -> None:
    j = json.loads(SRC.read_text(encoding="utf-8"))
    out = {
        "safety_zones": j.get("safety_zones"),
        "safety_zone_members": j.get("safety_zone_members"),
        "safety_build": j.get("safety_build"),
        "areas": j.get("areas"),
        "project_name": j.get("project_name"),
        "processor": j.get("processor"),
        "omit_unresolved_safety": j.get("omit_unresolved_safety"),
    }
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("WROTE", OUT)
    for z in out["safety_zone_members"] or []:
        print(
            "SZM",
            z.get("name"),
            "area=",
            z.get("area"),
            "origin=",
            z.get("membersOrigin") or z.get("zoneOrigin"),
            "members=",
            z.get("members"),
            "operational=",
            z.get("operational"),
            "status=",
            z.get("status"),
        )
    for z in (out["safety_build"] or {}).get("zones") or []:
        print(
            "SB",
            z.get("name") or z.get("engineering_name"),
            "area=",
            z.get("area"),
            "origin=",
            z.get("membersOrigin"),
            "members=",
            z.get("members"),
            "status=",
            z.get("status"),
        )


if __name__ == "__main__":
    main()
