#!/usr/bin/env python3
"""
fortna_workbook.py — FortnaPlus AutoGen workbook (Excel Inputdata replacement).

Built automatically from a Fortna RUN (tar.gz extract):
  - Conveyor rows (area, safety zone, type, PE wiring, template)
  - Areas / e-stop zones
  - IO map summary (banks → RIO modules)
  - EIP modules

Engineers edit rows in the dashboard, then Generate L5X uses this workbook
(no Excel VBA, no site-specific .xlsm required).

CLI:
  py fortna_workbook.py build --run-dir ...
  py fortna_workbook.py save  --run-dir ... --out path.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_autogen import (  # noqa: E402
    TYPE_TO_TEMPLATE,
    AutogenInput,
    ConveyorRow,
    FORTNA_TYPE_TO_AUTOGEN,
    FORTNA_TYPE_TO_AUTOGEN_VFD,
    load_from_run,
    _fortna_bit_to_data_bit,
)

# Excel-style TYPE strings engineers recognize (dropdown)
AUTOGEN_TYPES = [
    "Transport with MS",
    "Accumulation with MS",
    "Transport with VFD",
    "Accumulation with VFD",
    "Transport with MDR",
    "Accumulation with MDR",
    "Gravity",
]

WORKBOOK_VERSION = 1
DEFAULT_WORKBOOK_PATH = REPO_ROOT / "workspace" / "active" / "autogen_workbook.json"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _template_for_type(ag_type: str) -> str:
    key = (ag_type or "").strip().lower()
    return TYPE_TO_TEMPLATE.get(key) or "P3000_Conv"


def _infer_area_label(conveyor: str, machine: str) -> str:
    """ZoneN_Area from P### first digit (matches current autogen)."""
    m = re.match(r"^P(\d)", (conveyor or "").upper())
    if m:
        return f"Zone{m.group(1)}_Area"
    safe = re.sub(r"[^A-Za-z0-9_]", "_", machine or "Site")[:24]
    return f"{safe}_Area"


def _bulk_type_hint(asc_type: str, is_vfd: bool) -> str:
    typ = (asc_type or "").upper()
    m = FORTNA_TYPE_TO_AUTOGEN_VFD if is_vfd else FORTNA_TYPE_TO_AUTOGEN
    return m.get(typ, "Transport with VFD" if is_vfd else "Transport with MS")


def build_workbook_from_run(
    run_dir: Path,
    *,
    processor: str = "1756-L83E",
    existing: dict | None = None,
) -> dict:
    """
    Auto-fill workbook from tar.gz RUN.

    If existing workbook is passed, preserve human edits (main_area, type,
    safety_zone, include) for matching conveyor names.
    """
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"

    inp = load_from_run(run_dir, processor=processor)
    prev_by_name: dict[str, dict] = {}
    if existing and isinstance(existing.get("conveyors"), list):
        for row in existing["conveyors"]:
            name = (row.get("conveyor") or "").strip().upper()
            if name:
                prev_by_name[name] = row

    conveyors_out: list[dict] = []
    for i, c in enumerate(inp.conveyors or [], start=1):
        name = (c.conveyor or "").strip()
        prev = prev_by_name.get(name.upper(), {})
        ag_type = prev.get("type") or c.type or "Transport with MS"
        if ag_type not in AUTOGEN_TYPES:
            # normalize common variants
            low = ag_type.lower()
            for t in AUTOGEN_TYPES:
                if t.lower() == low:
                    ag_type = t
                    break
        main_area = prev.get("main_area") or c.main_area or _infer_area_label(name, inp.project_name)
        safety = prev.get("safety_zone") or c.safety_zone or (
            f"{main_area.replace('_Area', '')}_ESZone1"
        )
        include = prev.get("include", True)
        if include in ("0", 0, "false", "False", False):
            include = False
        else:
            include = True

        is_vfd = "vfd" in (ag_type or "").lower()
        conveyors_out.append({
            "number": i,
            "include": include,
            "conveyor": name,
            "main_area": main_area,
            "safety_zone": safety,
            "type": ag_type,
            "template": _template_for_type(ag_type),
            "drive": "VFD" if is_vfd else "MS",
            "exit_pe_tag": c.exit_pe_tag or "",
            "jam_pe_tags": list(c.jam_pe_tags or []),
            "full_pe_tags": list(c.full_pe_tags or []),
            "product_pe_tags": list(c.product_pe_tags or []),
            "all_pe_tags": list(c.all_pe_tags or []),
            "exit_pe_opt": c.exit_pe or "",
            "jam_opt": c.jam or "",
            "full_opt": c.full or "",
            "motor_starter": c.motor_starter or ("" if is_vfd else "Yes"),
            "espc": c.espc or "",
            "control_station": c.control_station or "",
            "power_supply": c.power_supply or "",
            "source": "run",
            "edited": bool(prev.get("edited")),
            "notes": prev.get("notes") or "",
        })

    # Areas from conveyor rows (unique, order by first appearance)
    areas: list[dict] = []
    seen_a: set[str] = set()
    for row in conveyors_out:
        a = row["main_area"]
        if a and a not in seen_a:
            seen_a.add(a)
            areas.append({
                "name": a,
                "safety_zone": row["safety_zone"],
                "conveyor_count": sum(1 for r in conveyors_out if r["main_area"] == a and r["include"]),
            })
    for a in areas:
        a["conveyor_count"] = sum(
            1 for r in conveyors_out if r["main_area"] == a["name"] and r["include"]
        )

    # IO points + physical resolve (fast map for UI)
    word_map = dict(inp.io_word_map or {})
    io_rows: list[dict] = []
    for p in inp.io_points or []:
        name = (p.device_name or "").strip()
        if not name:
            continue
        word = str(p.fortna_bank or "").strip()
        bit = str(p.fortna_bit or "").strip()
        data_bit = _fortna_bit_to_data_bit(bit)
        info = word_map.get(word)
        if not info and word.isdigit() and int(word) % 2 == 1:
            info = word_map.get(str(int(word) - 1))
        module_ref = ""
        mapped = False
        if info and data_bit is not None and 0 <= data_bit <= 15:
            rio = info.get("rio_name") or ""
            slot = int(info.get("flex_slot") or 0)
            direction = (info.get("direction") or p.direction or "I").upper()
            module_ref = f"{rio}:{direction}.Data[{slot}].{data_bit}"
            mapped = True
        io_rows.append({
            "name": name,
            "device_type": p.device_type or "",
            "direction": (p.direction or "I").upper(),
            "fortna_bank": word,
            "fortna_bit": bit,
            "module_ref": module_ref,
            "mapped": mapped,
            "description": (p.description or "")[:80],
        })

    modules = []
    for m in inp.modules or []:
        modules.append({
            "name": m.name,
            "type": m.type,
            "slot": m.slot,
            "ip": m.ip,
            "parent": m.parent,
            "rack": m.rack,
        })

    # Type / area rollups for quick human review
    type_counts: dict[str, int] = {}
    for r in conveyors_out:
        if not r["include"]:
            continue
        type_counts[r["type"]] = type_counts.get(r["type"], 0) + 1

    # --- Dropdown option lists (reusable every site; values come from this RUN) ---
    # Areas: discovered + standard Zone1–9 (Excel-style names can be added by user via bulk)
    area_opts: list[str] = []
    for a in areas:
        if a["name"] and a["name"] not in area_opts:
            area_opts.append(a["name"])
    for z in range(1, 10):
        lab = f"Zone{z}_Area"
        if lab not in area_opts:
            area_opts.append(lab)
    # Preserve any previous custom areas from existing workbook
    if existing:
        for row in existing.get("conveyors") or []:
            a = (row.get("main_area") or "").strip()
            if a and a not in area_opts:
                area_opts.append(a)

    safety_opts: list[str] = []
    for a in areas:
        s = (a.get("safety_zone") or "").strip()
        if s and s not in safety_opts:
            safety_opts.append(s)
    for a in area_opts:
        s = f"{a.replace('_Area', '')}_ESZone1"
        if s not in safety_opts:
            safety_opts.append(s)
    for s in (inp.safety_zones or []):
        if s and s not in safety_opts:
            safety_opts.append(s)
    if existing:
        for row in existing.get("conveyors") or []:
            s = (row.get("safety_zone") or "").strip()
            if s and s not in safety_opts:
                safety_opts.append(s)

    # All photoeye tags on this controller (for Exit PE dropdown)
    pe_opts: list[str] = []
    pe_seen: set[str] = set()
    for pe in inp.pe_devices or []:
        n = (pe.get("name") or pe.get("fortna_name") or "").strip()
        if n and n.upper() not in pe_seen:
            pe_seen.add(n.upper())
            pe_opts.append(n)
    for row in conveyors_out:
        for n in row.get("all_pe_tags") or []:
            if n and str(n).upper() not in pe_seen:
                pe_seen.add(str(n).upper())
                pe_opts.append(str(n))
    pe_opts.sort(key=lambda x: x.upper())

    # Per-row PE candidates (linked first, then full site list) for Exit PE dropdown
    for row in conveyors_out:
        linked: list[str] = []
        for n in (
            [row.get("exit_pe_tag") or ""]
            + list(row.get("product_pe_tags") or [])
            + list(row.get("jam_pe_tags") or [])
            + list(row.get("full_pe_tags") or [])
            + list(row.get("all_pe_tags") or [])
        ):
            if n and n not in linked:
                linked.append(n)
        # Prefer linked PEs at top of dropdown, then rest of site PEs
        rest = [p for p in pe_opts if p not in linked]
        row["exit_pe_choices"] = linked + rest

    # Excel PE option strings (jam/full/exit logic presets)
    pe_logic_opts = [
        "",
        "Yes Standard when Jam reset and PE clear",
        "Yes Disable Jam Logic",
        "Yes Jam reset with reset button without PE condition",
        "Yes Jam auto reset if PE clear",
        "Yes Standard Logic",
        "Yes Disable Release Bit to check Full condition of the conveyor",
    ]

    wb = {
        "version": WORKBOOK_VERSION,
        "kind": "fortna_autogen_workbook",
        "generated_utc": _ts(),
        "source": "run_tar_gz",
        "run_dir": str(run_dir),
        "project_name": inp.project_name,
        "processor": inp.processor or processor,
        "major_rev": inp.major_rev or "35",
        "minor_rev": inp.minor_rev or "00",
        "machine": (inp.project_name or "").split("_")[-1] if inp.project_name else "",
        "areas": areas,
        "safety_zones": list(inp.safety_zones or []),
        "conveyors": conveyors_out,
        "io_points": io_rows,
        "modules": modules,
        "eip_adapters": list(inp.eip_adapters or []),
        "eip_interface_ip": inp.eip_interface_ip or "",
        "rio_names": [t.get("rio_name") for t in (inp.eip_topology or [])],
        "type_counts": type_counts,
        "autogen_types": AUTOGEN_TYPES,
        # Dropdown catalogs for dashboard (reusable every site)
        "options": {
            "types": AUTOGEN_TYPES,
            "areas": area_opts,
            "safety_zones": safety_opts,
            "exit_pe": pe_opts,
            "pe_logic": pe_logic_opts,
        },
        "stats": {
            "conveyor_count": len(conveyors_out),
            "conveyor_included": sum(1 for r in conveyors_out if r["include"]),
            "area_count": len(areas),
            "io_point_count": len(io_rows),
            "io_mapped": sum(1 for r in io_rows if r["mapped"]),
            "io_unmapped": sum(1 for r in io_rows if not r["mapped"]),
            "module_count": len(modules),
            "word_map_count": len(word_map),
        },
        "human_notes": (
            "All conveyor rows come from the RUN tar.gz (FORTNA/Conveyor.asc). "
            "TYPE is inferred from ASC Type (STRAIGHT/CURVE/ACCUM/…) + whether a VFD drive is linked. "
            "AREA is inferred from the first digit of P### (P106→Zone1, P602→Zone6) — editable. "
            "Exit PE is the product/discharge PE tag linked to that conveyor in the ASC (or PE list). "
            "Dropdowns let you override; Generate uses your choices."
        ),
        "automation": {
            "filled_from": "Conveyor.asc + EIPCSV/EIPModules + extract_io_points (all inside tar.gz)",
            "type_rules": (
                "ASC Type ACCUM/ZEROPRESSURE → Accumulation with MS/VFD; "
                "STRAIGHT/CURVE/MERGE/… → Transport with MS/VFD; "
                "VFD vs MS chosen when Drive/VFD tags exist for that conveyor"
            ),
            "area_rules": "P### first digit → ZoneN_Area (O'Reilly convention; editable in dropdown)",
            "exit_pe_rules": "Product/exit PE tags from Conveyor.asc PE columns for that conveyor",
            "io_rules": "Bank.Word.Bit + EIP word_map → CPxRIOn:I/O.Data[slot].bit",
            "needs_human": [
                "Area rename / merge (Redroom vs Zone5 style)",
                "TYPE override when ASC type is wrong",
                "Exclude spare / future conveyors (include=false)",
                "Special PE jam/full options if non-standard",
            ],
        },
    }
    return wb


def apply_workbook_to_input(inp: AutogenInput, workbook: dict) -> AutogenInput:
    """Overlay human workbook edits onto AutogenInput before L5X generate."""
    if not workbook or not isinstance(workbook, dict):
        return inp

    rows = workbook.get("conveyors") or []
    if not rows:
        return inp

    by_name = {
        (r.get("conveyor") or "").strip().upper(): r
        for r in rows
        if (r.get("conveyor") or "").strip()
    }

    new_convs: list[ConveyorRow] = []
    areas: list[str] = []
    for c in inp.conveyors or []:
        key = (c.conveyor or "").strip().upper()
        w = by_name.get(key)
        if w is not None and w.get("include") in (False, 0, "0", "false", "False"):
            continue  # excluded by engineer
        if w:
            c.main_area = (w.get("main_area") or c.main_area or "").strip()
            c.safety_zone = (w.get("safety_zone") or c.safety_zone or "").strip()
            c.type = (w.get("type") or c.type or "").strip()
            # Exit PE chosen from dropdown (empty = none)
            if "exit_pe_tag" in w:
                c.exit_pe_tag = (w.get("exit_pe_tag") or "").strip()
            if "exit_pe_opt" in w and w.get("exit_pe_opt") is not None:
                c.exit_pe = (w.get("exit_pe_opt") or "").strip()
            if "vfd" in (c.type or "").lower():
                c.motor_starter = ""
            elif not c.motor_starter:
                c.motor_starter = "Yes"
        if c.main_area and c.main_area not in areas:
            areas.append(c.main_area)
        new_convs.append(c)

    # Renumber
    for i, c in enumerate(new_convs, start=1):
        c.number = i

    inp.conveyors = new_convs
    if areas:
        inp.areas = areas
        inp.safety_zones = [
            f"{a.replace('_Area', '')}_ESZone1" for a in areas
        ]
    if workbook.get("project_name"):
        inp.project_name = str(workbook["project_name"])
    if workbook.get("processor"):
        inp.processor = str(workbook["processor"])
    return inp


def save_workbook(wb: dict, path: Path | None = None) -> Path:
    path = Path(path) if path else DEFAULT_WORKBOOK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = dict(wb)
    wb["saved_utc"] = _ts()
    path.write_text(json.dumps(wb, indent=2), encoding="utf-8")
    return path


def load_workbook(path: Path | None = None) -> dict | None:
    path = Path(path) if path else DEFAULT_WORKBOOK_PATH
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def bulk_set_type(workbook: dict, conveyor_names: list[str], new_type: str) -> dict:
    names = {n.strip().upper() for n in conveyor_names if n and n.strip()}
    for row in workbook.get("conveyors") or []:
        if (row.get("conveyor") or "").upper() in names:
            row["type"] = new_type
            row["template"] = _template_for_type(new_type)
            row["drive"] = "VFD" if "vfd" in new_type.lower() else "MS"
            row["edited"] = True
            if "vfd" in new_type.lower():
                row["motor_starter"] = ""
            else:
                row["motor_starter"] = "Yes"
    # refresh type_counts
    counts: dict[str, int] = {}
    for r in workbook.get("conveyors") or []:
        if r.get("include", True):
            counts[r.get("type") or ""] = counts.get(r.get("type") or "", 0) + 1
    workbook["type_counts"] = counts
    return workbook


def bulk_set_area(workbook: dict, conveyor_names: list[str], main_area: str, safety_zone: str = "") -> dict:
    names = {n.strip().upper() for n in conveyor_names if n and n.strip()}
    sz = safety_zone or f"{main_area.replace('_Area', '')}_ESZone1"
    for row in workbook.get("conveyors") or []:
        if (row.get("conveyor") or "").upper() in names:
            row["main_area"] = main_area
            row["safety_zone"] = sz
            row["edited"] = True
    # rebuild areas list
    areas: list[dict] = []
    seen: set[str] = set()
    for row in workbook.get("conveyors") or []:
        a = row.get("main_area") or ""
        if a and a not in seen:
            seen.add(a)
            areas.append({
                "name": a,
                "safety_zone": row.get("safety_zone") or "",
                "conveyor_count": 0,
            })
    for a in areas:
        a["conveyor_count"] = sum(
            1 for r in workbook.get("conveyors") or []
            if r.get("main_area") == a["name"] and r.get("include", True)
        )
    workbook["areas"] = areas
    return workbook


def main() -> int:
    ap = argparse.ArgumentParser(description="FortnaPlus AutoGen workbook")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build workbook JSON from RUN")
    b.add_argument("--run-dir", required=True)
    b.add_argument("--processor", default="1756-L83E")
    b.add_argument("--out", default="")
    b.add_argument("--merge-existing", action="store_true", help="Preserve edits from default workbook path")

    s = sub.add_parser("load", help="Load saved workbook")
    s.add_argument("--path", default=str(DEFAULT_WORKBOOK_PATH))

    args = ap.parse_args()
    try:
        if args.cmd == "build":
            existing = load_workbook() if args.merge_existing else None
            wb = build_workbook_from_run(
                Path(args.run_dir),
                processor=args.processor,
                existing=existing,
            )
            out = Path(args.out) if args.out else DEFAULT_WORKBOOK_PATH
            save_workbook(wb, out)
            # Compact stdout for Electron
            slim = {
                "ok": True,
                "path": str(out),
                "project_name": wb["project_name"],
                "stats": wb["stats"],
                "type_counts": wb["type_counts"],
                "areas": wb["areas"],
                "autogen_types": wb["autogen_types"],
                "options": wb.get("options") or {},
                "conveyors": wb["conveyors"],
                "io_points": wb["io_points"][:200],  # cap for IPC
                "io_points_total": len(wb["io_points"]),
                "modules": wb["modules"][:80],
                "human_notes": wb["human_notes"],
                "automation": wb["automation"],
            }
            print(json.dumps(slim, separators=(",", ":")))
            return 0
        if args.cmd == "load":
            wb = load_workbook(Path(args.path))
            if not wb:
                print(json.dumps({"ok": False, "error": "No workbook saved"}))
                return 1
            print(json.dumps({"ok": True, "workbook": wb}, separators=(",", ":")))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
