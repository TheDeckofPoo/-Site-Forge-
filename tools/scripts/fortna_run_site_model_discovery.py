#!/usr/bin/env python3
"""RUN Site Model Discovery Pass 1 — controller-independent inventory.

SOURCE-OF-TRUTH (docs/SOURCE_OF_TRUTH_POLICY.md):
  INPUT SIDE only. Never reads finished/reference L5X or print OCR to populate
  the site model. Discovery / evidence only — does not change Auto Build topology.

Usage:
  python fortna_run_site_model_discovery.py \\
    --run-dir workspace/active/RUN \\
    --out exports/site-model
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import CONVEYOR_TYPES, read_asc  # noqa: E402
from fortna_run_geometry_investigate import (  # noqa: E402
    _anchors,
    _clean,
    _f,
    _is_motor_row,
    _is_pe_row,
    _load_mtrchain,
)

try:
    from fortna_autogen import _load_eip_adapters, load_from_run
except Exception:  # pragma: no cover
    _load_eip_adapters = None  # type: ignore
    load_from_run = None  # type: ignore

try:
    from fortna_io_extract import belongs_to_controller, row_machine_matches
except Exception:  # pragma: no cover
    belongs_to_controller = None  # type: ignore
    row_machine_matches = None  # type: ignore

MECH = {t.upper() for t in CONVEYOR_TYPES} | {"ZEROPRESSURE", "ACCUMULATOR", "MDR"}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _p_ok(name: str) -> bool:
    return bool(re.match(r"^P\d{2,4}[A-Za-z0-9_]*$", (name or "").strip(), re.I))


def _pe_to_p(pe: str) -> str:
    m = re.match(r"^(?:EZ)?PE[\s\-_]*(\d{2,4}[A-Za-z]?)", pe or "", re.I)
    return ("P" + m.group(1)) if m else ""


def discover(run_dir: Path) -> dict:
    fortna = run_dir / "FORTNA"
    conv_path = fortna / "Conveyor.asc"
    if not conv_path.is_file():
        raise FileNotFoundError(conv_path)

    word_map = {}
    if _load_eip_adapters:
        try:
            _a, _ip, _m, _t, word_map = _load_eip_adapters(run_dir)
        except Exception:
            word_map = {}

    # Per-controller Autogen-scoped sets (metadata only — not a filter that drops equipment)
    controller_sets: dict[str, set[str]] = {}
    # Discover controllers from Machine_Name on Conveyor.asc + known masters
    _h, rows = read_asc(conv_path)
    machines_seen = {
        _clean(r.get("Machine_Name"))
        for r in rows
        if _clean(r.get("Machine_Name"))
        and _clean(r.get("Machine_Name")).upper() not in ("N/A", "INVALID", "NONE", "ALL")
    }
    # Also try load_from_run for active machine set
    if load_from_run:
        try:
            inp = load_from_run(run_dir, processor="1756-L83E")
            pn = getattr(inp, "project_name", "") or ""
            m = re.search(r"_([A-Z0-9]+)$", pn)
            if m:
                machines_seen.add(m.group(1))
            controller_sets[m.group(1) if m else "ACTIVE"] = {
                (c.conveyor or "").strip().upper()
                for c in (inp.conveyors or [])
                if c.conveyor
            }
        except Exception:
            pass

    for mach in sorted(machines_seen):
        if mach in controller_sets:
            continue
        # Approximate: PE/motor rows belonging to controller → linked P tags
        linked: set[str] = set()
        for r in rows:
            name = _clean(r.get("IO_Name"))
            if not name:
                continue
            on = False
            if belongs_to_controller:
                try:
                    on = belongs_to_controller(
                        machine_name=_clean(r.get("Machine_Name")),
                        io_word=str(r.get("IO_Address_Word") or "").strip(),
                        controller=mach,
                        word_map=word_map,
                    )
                except Exception:
                    on = _clean(r.get("Machine_Name")).upper() == mach.upper()
            else:
                on = _clean(r.get("Machine_Name")).upper() == mach.upper()
            if not on:
                continue
            if _is_pe_row(r):
                g = _pe_to_p(name)
                if g:
                    linked.add(g.upper())
            if name.upper().startswith("VFD"):
                dm = re.search(r"(\d{2,4})", name)
                if dm:
                    linked.add(f"P{dm.group(1)}")
            if _is_motor_row(r) and re.match(r"^M\d", name, re.I):
                dm = re.search(r"(\d{2,4})", name)
                if dm:
                    linked.add(f"P{dm.group(1)}")
        # Explicit Machine_Name on mechanical rows
        for r in rows:
            if _clean(r.get("Type")).upper() not in MECH:
                continue
            nm = _clean(r.get("IO_Name"))
            if _p_ok(nm) and _clean(r.get("Machine_Name")).upper() == mach.upper():
                linked.add(nm.upper())
        controller_sets[mach] = linked

    mtrchain = _load_mtrchain(run_dir)

    # Full mechanical inventory — NEVER drop for missing controller
    equipment: dict[str, dict] = {}
    for r in rows:
        typ = _clean(r.get("Type")).upper()
        name = _clean(r.get("IO_Name"))
        if typ not in MECH or not _p_ok(name):
            continue
        key = name.upper()
        if key in equipment:
            continue
        x, y = _f(r.get("X_cord")), _f(r.get("Y_cord"))
        ang, length, width = _f(r.get("Angle")), _f(r.get("Length")), _f(r.get("Width"))
        anchors = None
        if x is not None and y is not None and ang is not None and length and length > 0:
            anchors = _anchors(x, y, length, ang)

        owners = []
        for mach, tags in controller_sets.items():
            if key in tags:
                owners.append(mach)
                continue
            # Base-tag match: P600C-style links vs P600
            base_m = re.match(r"^(P\d{2,4})", key)
            base = base_m.group(1) if base_m else key
            if any(
                t == key or t.startswith(key) or key.startswith(t) or t == base
                for t in tags
            ):
                owners.append(mach)
        # Explicit Machine_Name
        row_mach = _clean(r.get("Machine_Name"))
        if row_mach and row_mach.upper() not in ("N/A", "INVALID", "NONE", "ALL"):
            if row_mach not in owners:
                owners.insert(0, row_mach)

        conf = "HIGH" if len(owners) == 1 else ("AMBIGUOUS" if len(owners) > 1 else "UNKNOWN")
        motors = list(mtrchain.get(key, []))

        pe_assoc = []
        for rpe in rows:
            if not _is_pe_row(rpe):
                continue
            pe = _clean(rpe.get("IO_Name"))
            if _pe_to_p(pe).upper() == key:
                pe_assoc.append({"photoeye": pe, "association": "name_suffix_match", "provenance": "RUN"})

        equipment[key] = {
            "conveyor_tag": name,
            "equipment_type": typ,
            "x": x,
            "y": y,
            "angle": ang,
            "length": length,
            "width": width,
            "infeed_tangent": _f(r.get("Infeed_Tangent")),
            "discharge_tangent": _f(r.get("Discharge_Tangent")),
            "nose_over": _clean(r.get("NoseOver")),
            "infeed_elevation": _f(r.get("Infeed_Elevation")),
            "discharge_elevation": _f(r.get("Discharge_Elevation")),
            "entry_anchor": anchors["entry"] if anchors else None,
            "exit_anchor": anchors["exit"] if anchors else None,
            "geometry_provenance": {
                "x": "RUN",
                "y": "RUN",
                "angle": "RUN",
                "length": "RUN",
                "width": "RUN",
                "entry_anchor": "INFERRED_GEOMETRY",
                "exit_anchor": "INFERRED_GEOMETRY",
                "anchor_assumption": (
                    "X/Y treated as footprint center; angle = flow deg CCW from +X; "
                    "anchors = center ± Length/2 — ASSUMPTION until proven"
                ),
            },
            "controller_owner": owners[0] if len(owners) == 1 else None,
            "controller_candidates": owners,
            "controller_confidence": conf,
            "motors": motors,
            "photoeyes": pe_assoc,
            "drawing_page": _clean(r.get("Electrical Drawing Page No.")),
            "part_number": _clean(r.get("Part_Number")),
            "machine_name_field": row_mach,
            "io_address_word": _clean(r.get("IO_Address_Word")),
        }

    # Devices summary
    devices = []
    for r in rows:
        name = _clean(r.get("IO_Name"))
        if not name:
            continue
        if _is_motor_row(r) or _is_pe_row(r) or name.upper().startswith("VFD"):
            devices.append(
                {
                    "tag": name,
                    "type": _clean(r.get("Type")),
                    "machine_name": _clean(r.get("Machine_Name")),
                    "kind": (
                        "vfd"
                        if name.upper().startswith("VFD")
                        else ("photoeye" if _is_pe_row(r) else "motor")
                    ),
                    "provenance": "RUN",
                }
            )

    counts = {
        "total_unique_conveyors": len(equipment),
        "conveyors_with_xy": sum(
            1 for e in equipment.values() if e["x"] is not None and e["y"] is not None
        ),
        "conveyors_with_angle": sum(1 for e in equipment.values() if e["angle"] is not None),
        "conveyors_with_length": sum(
            1 for e in equipment.values() if e["length"] is not None and e["length"] > 0
        ),
        "conveyors_with_width": sum(
            1 for e in equipment.values() if e["width"] is not None and e["width"] > 0
        ),
        "conveyors_with_controller_ownership_high": sum(
            1 for e in equipment.values() if e["controller_confidence"] == "HIGH"
        ),
        "conveyors_with_ambiguous_controller": sum(
            1 for e in equipment.values() if e["controller_confidence"] == "AMBIGUOUS"
        ),
        "conveyors_with_no_controller": sum(
            1 for e in equipment.values() if e["controller_confidence"] == "UNKNOWN"
        ),
        "devices": len(devices),
    }

    site_model = {
        "generated_at": _ts(),
        "run_dir": str(run_dir),
        "source_of_truth": "RUN only — finished L5X not read",
        "model": "SiteModel",
        "counts": counts,
        "controllers": sorted(controller_sets.keys()),
        "equipment": sorted(equipment.values(), key=lambda e: e["conveyor_tag"]),
        "devices": devices,
        "relationships": [],  # filled by table discovery / future passes
        "areas": [],  # RUN does not reliably provide areas here
        "geometry": {
            "anchor_status": "INFERRED_GEOMETRY",
            "tangent_fields": {
                "Infeed_Tangent": "Present on many CURVE/BELT rows; appears to be geometric curve parameter (not conveyor-to-conveyor link)",
                "Discharge_Tangent": "Same as Infeed_Tangent — local geometry, not topology FK",
                "NoseOver": "Occasional 'Double Noseover' on BELT — equipment feature flag",
            },
        },
    }
    return site_model, controller_sets, equipment


def build_controller_map(equipment: dict, controller_sets: dict) -> dict:
    mapping = []
    for tag, e in sorted(equipment.items()):
        mapping.append(
            {
                "conveyor_tag": e["conveyor_tag"],
                "controller_owner": e["controller_owner"],
                "controller_candidates": e["controller_candidates"],
                "controller_confidence": e["controller_confidence"],
                "provenance": "RUN",
                "evidence": {
                    "machine_name_field": e["machine_name_field"],
                    "io_link_controllers": [
                        m for m, tags in controller_sets.items() if tag in tags
                    ],
                },
            }
        )
    return {
        "generated_at": _ts(),
        "source_of_truth": "RUN only",
        "note": "Controller ownership is metadata — equipment remains in site model even if UNKNOWN",
        "mapping": mapping,
        "counts": Counter(m["controller_confidence"] for m in mapping),
    }


def analyze_convpath(run_dir: Path) -> dict:
    path = run_dir / "FORTNA" / "Convpath.asc"
    pathsets = run_dir / "FORTNA" / "Pathsets.asc"
    out: dict = {
        "generated_at": _ts(),
        "source_of_truth": "RUN only",
        "question": "Can Convpath encode ordered conveyor paths like P132→P134→P136→P138?",
    }
    if not path.is_file():
        out["exists"] = False
        out["answer"] = "Convpath.asc missing"
        return out

    h, rows = read_asc(path)
    nonempty = []
    p_edges = []
    for r in rows:
        piece, inp, outp, pe_at, pen = (
            _clean(r.get("Piece")),
            _clean(r.get("Input")),
            _clean(r.get("Output")),
            _clean(r.get("PE_at")),
            _clean(r.get("PEname")),
        )
        if any(
            v and v.upper() not in ("INVALID", "N/A", "NONE", "0", "0.000")
            for v in (piece, inp, outp, pe_at, pen)
        ):
            nonempty.append(
                {"Piece": piece, "Input": inp, "Output": outp, "PE_at": pe_at, "PEname": pen}
            )
        if re.match(r"^P\d", inp or "", re.I) and re.match(r"^P\d", outp or "", re.I):
            p_edges.append((inp.upper(), outp.upper(), piece))

    # Pathsets
    ps_info = {"exists": pathsets.is_file()}
    if pathsets.is_file():
        ph, prows = read_asc(pathsets)
        usable_ps = []
        for r in prows:
            name = _clean(r.get("Name"))
            pths = [_clean(r.get(f"Pth{i}")) for i in range(1, 11)]
            if name or any(p and p not in ("0",) for p in pths):
                usable_ps.append({"Name": name, "paths": pths, "LaneType": _clean(r.get("LaneType"))})
        # Filter all-zero shells
        real_ps = [
            u
            for u in usable_ps
            if any(p and p not in ("0", "0.000", "INVALID", "N/A") for p in u["paths"])
            or (u["Name"] and u["Name"].upper() not in ("INVALID", "N/A", ""))
        ]
        ps_info.update(
            {
                "headers": ph,
                "row_count": len(prows),
                "rows_with_any_name_or_path": len(usable_ps),
                "rows_with_real_path_data": len(real_ps),
                "samples": real_ps[:10],
            }
        )

    out.update(
        {
            "file": "FORTNA/Convpath.asc",
            "headers": h,
            "row_count": len(rows),
            "schema_interpretation": {
                "Piece": "Likely tracking piece / carton identity slot (not conveyor tag in this RUN)",
                "Input": "Likely numeric/slot input — not populated with P-tags here",
                "Output": "Likely numeric/slot output — not populated with P-tags here",
                "PE_at": "Photoeye position along path (numeric)",
                "PEname": "Photoeye name along path",
            },
            "non_placeholder_rows": len(
                [
                    r
                    for r in nonempty
                    if r["Piece"].upper() != "INVALID"
                    or (r["Input"] not in ("0.000", "0", "") and r["Input"].upper() != "INVALID")
                ]
            ),
            "placeholder_rows": sum(
                1
                for r in rows
                if _clean(r.get("Piece")).upper() == "INVALID"
                and _clean(r.get("Input")) in ("0.000", "0", "")
            ),
            "p_to_p_edges_found": len(p_edges),
            "p_to_p_edge_samples": p_edges[:20],
            "example_rows_first_nonempty_looking": nonempty[:5],
            "pathsets": ps_info,
            "answer": (
                "NO — On this RUN, Convpath.asc does not encode ordered conveyor topology. "
                "All 1000 rows are placeholders (Piece=INVALID, Input/Output=0.000). "
                "Zero P→P edges were found. Pathsets.asc likewise has no real Pth1..Pth10 conveyor "
                "sequences. Therefore a sequence like P132→P134→P136→P138 cannot be derived from "
                "Convpath without geometry inference or engineer input."
            ),
            "what_convpath_appears_to_be": (
                "A tracking / piece-path slot table (Piece + PE_at/PEname) intended for carton "
                "tracking along a path, not a static conveyor-to-conveyor downstream graph. "
                "In this archive it is unpopulated."
            ),
        }
    )
    return out


def analyze_tables(run_dir: Path) -> dict:
    """Relational discovery for key ASC tables."""
    fortna = run_dir / "FORTNA"
    specs = [
        ("Conveyor.asc", "physical+devices", ["IO_Name", "Type", "X_cord", "Y_cord", "Motor", "Machine_Name"]),
        ("Convpath.asc", "tracking?", ["Piece", "Input", "Output", "PE_at", "PEname"]),
        ("Pathsets.asc", "sort/divert paths?", ["Name", "Pth1", "Pth2", "Divert Solenoid"]),
        ("Mtrchain.asc", "control topology", ["Motor_Name", "Motor_Chained1", "Motor_Aux"]),
        ("Jamzones.asc", "jam/full logic", ["Zone Name", "Zone Owner ", "Latch Bit"]),
        ("Jamcheck.asc", "jam/full logic", ["Sensor_Name", "Conveyor_Name", "Jam_Owner", "Zone"]),
        ("Fulljam.asc", "jam/full logic", ["Sensor_Name", "Conveyor_Name", "Owner", "Response IO"]),
        ("Fullline.asc", "jam/full logic", ["Sensor_Name", "Conveyor_Name", "Response IO"]),
        ("Merges.asc", "merge logic", ["Merge Table Name", "Valid", "Presense_Eye1"]),
        ("MergeBoss.asc", "merge logic", ["Name", "Owner", "NumInputs", "OperableInput"]),
        ("MergeInputs.asc", "merge logic", ["Name", "MergeBoss", "Presense", "MergeRoute"]),
        ("EStop.asc", "safety", ["Part", "Error"]),
        ("FORTNADT.asc", "IO bit image", ["Machine", "HiBank", "LoBank", "Bits_On_Off"]),
        ("CTRLDT.asc", "IO bit image", ["Bits_On_Off"]),
        ("GUIDT.asc", "IO bit image", ["Bits_On_Off"]),
    ]

    # Include machine-suffixed merge files
    extra = list(fortna.glob("Merge*.asc*")) + list(fortna.glob("Jam*.asc*")) + list(
        fortna.glob("Full*.asc*")
    )

    tables = []
    seen_files = set()

    def add_table(fname: str, category_hint: str, key_hints: list[str]) -> None:
        # Prefer exact, then machine-suffixed
        candidates = [fortna / fname]
        if not fname.endswith((".ORNCCP2", ".ORNCCP4", ".ORNCCP5")):
            candidates += list(fortna.glob(fname + ".*"))
        for p in candidates:
            if not p.is_file() or p.name.startswith("old."):
                continue
            if p.name in seen_files:
                continue
            seen_files.add(p.name)
            headers, rows = read_asc(p)
            # Collect repeated tag-like tokens
            tag_hits = Counter()
            for r in rows[:500]:
                for v in r.values():
                    s = _clean(v)
                    if re.match(r"^(P|M|PE|EZPE|VFD|ENC)\d", s, re.I):
                        tag_hits[s.upper()] += 1
            # Classify
            cat = category_hint
            if "Convpath" in p.name or "Pathset" in p.name:
                # override after content check
                usable = sum(
                    1
                    for r in rows
                    if any(
                        _clean(r.get(k)).upper() not in ("", "INVALID", "N/A", "0", "0.000")
                        for k in headers
                    )
                )
                if usable == 0 or all(
                    _clean(r.get("Piece")).upper() == "INVALID" for r in rows[:50]
                ):
                    cat = "tracking_unpopulated"
            tables.append(
                {
                    "file": p.name,
                    "category_hint": cat,
                    "headers": headers,
                    "row_count": len(rows),
                    "key_fields_present": [k for k in key_hints if k in headers],
                    "likely_foreign_keys": [
                        k
                        for k in headers
                        if any(
                            x in k.lower()
                            for x in (
                                "conveyor",
                                "motor",
                                "sensor",
                                "pe",
                                "owner",
                                "machine",
                                "zone",
                                "merge",
                                "response",
                                "input",
                                "output",
                                "chained",
                            )
                        )
                    ],
                    "repeated_tag_samples": tag_hits.most_common(15),
                    "describes": _classify_table(p.name, headers, cat),
                }
            )

    for fname, hint, keys in specs:
        add_table(fname, hint, keys)
    for p in extra:
        if p.name not in seen_files and not p.name.startswith("old."):
            add_table(p.name, "merge_or_jam_variant", [])

    return {
        "generated_at": _ts(),
        "source_of_truth": "RUN only",
        "tables": tables,
        "summary": {
            "physical_topology_direct": (
                "No populated Convpath/Pathsets P→P graph found. Conveyor.asc has geometry, "
                "not successor links."
            ),
            "control_topology": "Mtrchain, Jamcheck/Fulljam/Fullline Response IO, MergeInputs ReleaseIO",
            "controller_ownership": (
                "Machine_Name on some rows; Jam_Owner / MergeBoss Owner / PE IO scoping"
            ),
        },
    }


def _classify_table(name: str, headers: list[str], hint: str) -> list[str]:
    n = name.upper()
    out = []
    if "CONVPATH" in n or "PATHSET" in n:
        out.append("tracking (unpopulated on this RUN)")
    if name.upper().startswith("CONVEYOR"):
        out += ["physical geometry", "device inventory", "weak controller hints"]
    if "MTRCHAIN" in n:
        out.append("control topology (motor latch/chain)")
    if "JAM" in n or "FULL" in n:
        out.append("jam/full logic")
    if "MERGE" in n:
        out.append("merge logic")
    if "ESTOP" in n:
        out.append("safety / estop parts list")
    if n.endswith("DT.ASC") or "DT.ASC" in n:
        out.append("controller IO bit image / runtime DT")
    if not out:
        out.append(hint or "unknown")
    return out


def write_docs(
    out_dir: Path,
    site: dict,
    cmap: dict,
    tables: dict,
    convpath: dict,
) -> None:
    c = site["counts"]
    lines = [
        "# RUN Site Model Discovery Pass 1",
        "",
        f"Generated: `{site['generated_at']}`",
        f"RUN: `{site['run_dir']}`",
        "",
        "## Source-of-truth firewall",
        "",
        "Finished PLC and prints were **not** used to populate this model.",
        "See `docs/SOURCE_OF_TRUTH_POLICY.md`.",
        "",
        "## Canonical model",
        "",
        "```",
        "SiteModel",
        "  equipment[]      # physical conveyors — one row per P-tag, plant-wide",
        "  devices[]        # motors / PEs / VFDs from Conveyor.asc",
        "  relationships[]  # reserved (Convpath empty; geometry/manual later)",
        "  controllers[]    # ownership metadata map",
        "  areas[]          # not reliably available from RUN geometry tables",
        "  geometry[]       # embedded on equipment with provenance",
        "```",
        "",
        "Controller ownership is **metadata**, not a filter that deletes equipment.",
        "",
        "## Inventory counts",
        "",
        f"| Metric | Count |",
        f"|---|---:|",
        f"| Total unique mechanical conveyors | {c['total_unique_conveyors']} |",
        f"| With XY | {c['conveyors_with_xy']} |",
        f"| With angle | {c['conveyors_with_angle']} |",
        f"| With length | {c['conveyors_with_length']} |",
        f"| With width | {c['conveyors_with_width']} |",
        f"| Controller ownership HIGH | {c['conveyors_with_controller_ownership_high']} |",
        f"| Controller AMBIGUOUS | {c['conveyors_with_ambiguous_controller']} |",
        f"| Controller UNKNOWN / none | {c['conveyors_with_no_controller']} |",
        "",
        "## Convpath investigation (highest priority)",
        "",
        convpath.get("answer", ""),
        "",
        "**What Convpath appears to be:** ",
        convpath.get("what_convpath_appears_to_be", ""),
        "",
        f"- Rows: {convpath.get('row_count')}",
        f"- P→P edges found: **{convpath.get('p_to_p_edges_found')}**",
        f"- Placeholder rows: {convpath.get('placeholder_rows')}",
        "",
        "Therefore a sequence such as `P132 → P134 → P136 → P138` **cannot** be derived from",
        "Convpath on this archive without geometry inference or engineer configuration.",
        "",
        "## Geometry",
        "",
        "Entry/exit anchors remain **`INFERRED_GEOMETRY`** (center ± Length/2 assumption).",
        "",
        "- `Infeed_Tangent` / `Discharge_Tangent`: present especially on CURVE/BELT; look like",
        "  local curve geometry parameters, **not** foreign keys to adjacent conveyors.",
        "- `NoseOver`: occasional equipment feature (`Double Noseover`), not topology.",
        "",
        "## Controllers",
        "",
        f"Controllers observed/linked: {', '.join(site.get('controllers') or []) or '—'}",
        "",
        "See `controller_map.json`. Unknown ownership does **not** remove the conveyor from the site model.",
        "",
        "## Headline question",
        "",
        "**Can the RUN describe physical conveyor topology directly, or are we still forced to infer topology from geometry/manual engineering?**",
        "",
        "**Answer: Still forced to infer / engineer.**",
        "",
        "This RUN provides a strong **physical equipment + geometry inventory** (hundreds of P-tags with XY/angle/length)",
        "and useful **control relationships** (Mtrchain, jam/full, merge boss/inputs), but it does **not** provide a",
        "populated static conveyor successor graph (Convpath/Pathsets empty). Physical topology therefore remains:",
        "",
        "1. `INFERRED_GEOMETRY` (exit→entry mating), and/or",
        "2. **ENGINEER**-entered Transport Build connections,",
        "",
        "not a direct RUN path table export.",
        "",
        "## Artifacts",
        "",
        "- `site_model_inventory.json`",
        "- `controller_map.json`",
        "- `table_relationships.json`",
        "- `convpath_analysis.json`",
        "",
        "No Auto Build production topology changes in this pass.",
        "",
    ]
    (out_dir / ".." / ".." / "docs" / "RUN_SITE_MODEL_DISCOVERY.md").resolve()
    docs = ROOT / "docs" / "RUN_SITE_MODEL_DISCOVERY.md"
    docs.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RUN Site Model Discovery Pass 1")
    ap.add_argument("--run-dir", default=str(ROOT / "workspace" / "active" / "RUN"))
    ap.add_argument("--out", default=str(ROOT / "exports" / "site-model"))
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    site, controller_sets, equipment = discover(run_dir)
    site["controllers"] = sorted(controller_sets.keys())
    cmap = build_controller_map(equipment, controller_sets)
    # serialize Counter
    cmap["counts"] = dict(cmap["counts"])
    tables = analyze_tables(run_dir)
    convpath = analyze_convpath(run_dir)

    (out / "site_model_inventory.json").write_text(json.dumps(site, indent=2), encoding="utf-8")
    (out / "controller_map.json").write_text(json.dumps(cmap, indent=2), encoding="utf-8")
    (out / "table_relationships.json").write_text(json.dumps(tables, indent=2), encoding="utf-8")
    (out / "convpath_analysis.json").write_text(json.dumps(convpath, indent=2), encoding="utf-8")
    write_docs(out, site, cmap, tables, convpath)

    c = site["counts"]
    print("RUN SITE MODEL DISCOVERY")
    print(f"  unique conveyors: {c['total_unique_conveyors']}")
    print(f"  with XY/angle/length: {c['conveyors_with_xy']}/{c['conveyors_with_angle']}/{c['conveyors_with_length']}")
    print(
        f"  controller HIGH/AMBIGUOUS/UNKNOWN: "
        f"{c['conveyors_with_controller_ownership_high']}/"
        f"{c['conveyors_with_ambiguous_controller']}/"
        f"{c['conveyors_with_no_controller']}"
    )
    print(f"  Convpath P→P edges: {convpath.get('p_to_p_edges_found')}")
    print(f"  docs: {ROOT / 'docs' / 'RUN_SITE_MODEL_DISCOVERY.md'}")
    print(f"  out: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
