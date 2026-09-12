#!/usr/bin/env python3
"""Neutral legacy layout decoder framework (scaffold).

Only decode formats that are understood from legally accessible RUN/config
research (see docs/LEGACY_LAYOUT_DATA_RESEARCH.md). Do not invent parsers.

Output schema:
  equipment[], connections[], geometry[], layers[], annotations[], provenance[]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def empty_model(*, source: str = "", note: str = "") -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "note": note
        or "Scaffold only — populate after a format is confirmed in LEGACY_LAYOUT_DATA_RESEARCH.md",
        "equipment": [],
        "connections": [],
        "geometry": [],
        "layers": [],
        "annotations": [],
        "provenance": [],
    }


def decode_from_conveyor_asc(run_dir: Path) -> dict[str, Any]:
    """Baseline decoder: known Conveyor.asc geometry fields (already used by Site Forge)."""
    import sys

    sys.path.insert(0, str(ROOT / "tools" / "scripts"))
    from fortna_asc import read_asc
    from fortna_physical_geometry import build_equipment_geometry
    from fortna_run_geometry_investigate import _clean, _is_mech_conveyor

    model = empty_model(
        source=str(run_dir / "FORTNA" / "Conveyor.asc"),
        note="Decoded from known Conveyor.asc geometry (infeed-origin model)",
    )
    _h, rows = read_asc(run_dir / "FORTNA" / "Conveyor.asc")
    seen = set()
    for r in rows:
        if not _is_mech_conveyor(r):
            continue
        tag = _clean(r.get("IO_Name")).upper()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        geom = build_equipment_geometry(r)
        model["equipment"].append(
            {
                "id": tag,
                "type": _clean(r.get("Type")),
                "layer": _clean(r.get("Layer")),
                "provenance": "RUN_EXPLICIT",
            }
        )
        if geom.get("entry") and geom.get("exit"):
            model["geometry"].append(
                {
                    "equipment_id": tag,
                    "entry": geom["entry"],
                    "exit": geom["exit"],
                    "angle": geom.get("angle_in"),
                    "length": geom.get("length"),
                    "width": geom.get("width"),
                    "provenance": "RUN_EXPLICIT",
                    "model": geom.get("calibration") or "greensboro-infeed-v1",
                }
            )
        layer = _clean(r.get("Layer"))
        if layer:
            model["layers"].append({"id": layer, "provenance": "RUN_EXPLICIT"})
    # dedupe layers
    uniq = {x["id"]: x for x in model["layers"]}
    model["layers"] = list(uniq.values())
    model["provenance"].append(
        {
            "statement": "Conveyor.asc X_cord/Y_cord/Angle/Length/Width/Layer decoded",
            "confidence": "HIGH",
        }
    )
    return model


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Legacy layout decoder scaffold")
    ap.add_argument("--run-dir", default="")
    ap.add_argument("--out", default="exports/layout-research/legacy_layout_model.json")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    if args.run_dir:
        run_dir = Path(args.run_dir)
        if not run_dir.is_absolute():
            run_dir = ROOT / run_dir
        model = decode_from_conveyor_asc(run_dir)
    else:
        model = empty_model()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(model, indent=2), encoding="utf-8")
    print(f"wrote {out} equipment={len(model['equipment'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
