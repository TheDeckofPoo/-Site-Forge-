#!/usr/bin/env python3
"""Probe ORI-054 failing ES_UDT / zone routine emission."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_autogen import AutogenInput, ConveyorRow, build_l5x  # noqa: E402

LIBRARY = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"


def main() -> None:
    inp = AutogenInput(
        project_name="Synthetic_Safety_CTRL",
        machine="SYNTH_SAFE",
        areas=["Pack_Area"],
        safety_zones=["Pack_ESZone1"],
        safety_zone_members=[
            {"name": "Pack_ESZone1", "area": "Pack_Area", "members": ["ES100"]}
        ],
        safety_build={
            "zones": [
                {
                    "name": "Pack_ESZone1",
                    "area": "Pack_Area",
                    "members": ["ES100"],
                    "status": "READY",
                }
            ]
        },
        conveyors=[
            ConveyorRow(
                number=1,
                conveyor="P100",
                main_area="Pack_Area",
                safety_zone="Pack_ESZone1",
                type="Transport with MS",
            )
        ],
        include_sys=False,
        include_io_map=True,
        include_io_map_gold=False,
    )
    inp.io_points = []
    l5x, report = build_l5x(inp, LIBRARY)
    es_tags = re.findall(r'Tag Name="([^"]+)"[^>]*DataType="ES_UDT"', l5x)
    print("ES_UDT count", len(es_tags))
    print("ES_UDT sample", es_tags[:30])
    print("has ES100 tag", bool(re.search(r'Tag Name="(?:T_)?ES100"', l5x)))
    print("Pack_ESZone1 in l5x", "Pack_ESZone1" in l5x)
    print("es_program keys", sorted((report.get("es_program") or {}).keys()))
    es = report.get("es_program") or {}
    for k in (
        "status",
        "shell",
        "emitted",
        "partial",
        "emitted_zones",
        "omitted_zones",
        "detail",
    ):
        print(f"  {k}: {es.get(k)!r}")
    # membership / zone routine markers
    for needle in (
        "Pack_ESZone1_Safe_Logic",
        "ES_SIL1_Cat1",
        "ES100",
        "T_ES100",
    ):
        print(f"needle {needle}: {needle in l5x}")


if __name__ == "__main__":
    main()
