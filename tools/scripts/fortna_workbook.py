#!/usr/bin/env python3
"""
fortna_workbook.py — Site Forge AutoGen workbook (Excel Inputdata replacement).

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
# Stable path outside workspace/active (active/ is wiped on every RUN import)
DEFAULT_WORKBOOK_PATH = REPO_ROOT / "workspace" / "autogen_workbook.json"
_LEGACY_WORKBOOK_PATH = REPO_ROOT / "workspace" / "active" / "autogen_workbook.json"

# Gate R — Excel-style Zone1..Zone9 are UI dropdown suggestions only.
# They must NOT auto-promote into production safety_zones / ES IR shells.
_PLACEHOLDER_AREA_RE = re.compile(r"^Zone([1-9])_Area$", re.I)
_PLACEHOLDER_ZONE_RE = re.compile(r"^Zone([1-9])_ESZone\d*$", re.I)
_NUMERIC_STEM_ZONE_RE = re.compile(r"^(\d{2,})_ESZone\d*$", re.I)
_CORRUPT_ZONE_RE = re.compile(r"\[object\s+Object\]", re.I)


def is_ui_placeholder_area(name: str) -> bool:
    return bool(_PLACEHOLDER_AREA_RE.match(str(name or "").strip()))


def is_placeholder_or_test_zone_name(name: str) -> bool:
    s = str(name or "").strip()
    if not s:
        return True
    if _CORRUPT_ZONE_RE.search(s):
        return True
    if _PLACEHOLDER_ZONE_RE.match(s):
        return True
    if _NUMERIC_STEM_ZONE_RE.match(s):
        return True
    return False


def is_production_safety_zone_name(name: str) -> bool:
    """True when a zone name may enter production canonical / AutogenInput."""
    s = str(name or "").strip()
    if not s or is_placeholder_or_test_zone_name(s):
        return False
    return True


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

    When existing.machine differs from the new RUN machine (case-insensitive),
    do NOT preserve foreign main_area / safety_zone — treat as a fresh workbook.
    """
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"

    inp = load_from_run(run_dir, processor=processor)
    prev_by_name: dict[str, dict] = {}
    # Cross-machine merge must NOT preserve foreign Area/ES (MSCRENO → ORNCCP2 leak).
    existing_machine = str((existing or {}).get("machine") or "").strip().upper()
    new_machine = str(getattr(inp, "project_name", "") or "").strip().upper()
    # project_name often OReillyGreensboro_ORNCCP2 — extract controller token
    m_new = re.search(r"_([A-Z0-9]+)$", new_machine, re.I)
    new_ctrl = (m_new.group(1) if m_new else new_machine).upper()
    same_machine = bool(
        existing_machine
        and new_ctrl
        and (
            existing_machine == new_ctrl
            or existing_machine in new_machine
            or new_ctrl in existing_machine
        )
    )
    if existing and isinstance(existing.get("conveyors"), list) and same_machine:
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
        # Only preserve Area/ES edits when same controller project
        main_area = (
            (prev.get("main_area") if same_machine else None)
            or c.main_area
            or _infer_area_label(name, inp.project_name)
        )
        # Do NOT auto-mint ${Area}_ESZone1 — that Area→zone suggestion is presentation
        # only and must not rehydrate as an operational/RUN Safety shell after restart.
        # Preserve prior engineer/Transport assignment when same machine; otherwise blank.
        safety = (
            (prev.get("safety_zone") if same_machine else None)
            or c.safety_zone
            or ""
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
            "downstream": (c.downstream or prev.get("downstream") or "").strip(),
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
    # Areas: discovered first. Zone1–9 remain UI suggestions only (Gate R) —
    # they must not auto-mint production Safety zones.
    area_opts: list[str] = []
    for a in areas:
        if a["name"] and a["name"] not in area_opts:
            area_opts.append(a["name"])
    # Preserve previous custom areas only for the same controller project
    if existing and same_machine:
        for row in existing.get("conveyors") or []:
            a = (row.get("main_area") or "").strip()
            if a and a not in area_opts:
                area_opts.append(a)
    for z in range(1, 10):
        lab = f"Zone{z}_Area"
        if lab not in area_opts:
            area_opts.append(lab)

    safety_opts: list[str] = []
    # Production seeds only from discovered areas / RUN / conveyor refs — never
    # from Zone1_Area..Zone9_Area UI placeholders.
    for a in areas:
        s = (a.get("safety_zone") or "").strip()
        if s and s not in safety_opts and is_production_safety_zone_name(s):
            safety_opts.append(s)
        an = str(a.get("name") or "").strip()
        if an and not is_ui_placeholder_area(an):
            stem = an.replace("_Area", "")
            s = f"{stem}_ESZone1"
            if s not in safety_opts and is_production_safety_zone_name(s):
                safety_opts.append(s)
    for s in (inp.safety_zones or []):
        if s and s not in safety_opts and is_production_safety_zone_name(str(s)):
            safety_opts.append(str(s))
    if existing and same_machine:
        for row in existing.get("conveyors") or []:
            s = (row.get("safety_zone") or "").strip()
            if s and s not in safety_opts and is_production_safety_zone_name(s):
                safety_opts.append(s)
    # Dropdown catalog may still offer ZoneN_ESZone1 as Excel-style suggestions,
    # but they are tagged under options only — apply_workbook will not promote
    # unused suggestions into AutogenInput.safety_zones.
    for z in range(1, 10):
        lab = f"Zone{z}_ESZone1"
        if lab not in safety_opts:
            safety_opts.append(lab)

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
        # Production canonical only — UI Zone1..Zone9 catalog lives under options
        "safety_zones": [
            s for s in (inp.safety_zones or [])
            if is_production_safety_zone_name(str(s))
        ],
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
            "AREA defaults to {controller}_Area from RUN (not Zone1–Zone9 from P-digit). "
            "Zone1_Area..Zone9_Area remain dropdown suggestions only — they do not auto-create Safety zones. "
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
            "area_rules": (
                "RUN seed uses {controller}_Area; Zone1_Area..Zone9_Area are UI "
                "suggestions only and do not auto-promote Safety zones (Gate R)"
            ),
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
    # Preserve engineer subsystem state ONLY when ProjectIdentity matches.
    # Different project/controller → current RUN starts clean (Fundamentals #2/#6/#14).
    try:
        from fortna_project_identity import (
            identity_from_run,
            identity_from_workbook,
            same_project,
            stamp_workbook_identity,
        )

        current_identity = identity_from_run(run_dir)
        existing_identity = identity_from_workbook(existing) if existing else None
        allow_preserve = bool(existing) and same_project(existing_identity, current_identity)
        wb = stamp_workbook_identity(wb, current_identity)
    except Exception:
        allow_preserve = bool(existing) and same_machine
        current_identity = None

    if existing and allow_preserve:
        if isinstance(existing.get("merges_2to1"), list):
            wb["merges_2to1"] = existing["merges_2to1"]
        if isinstance(existing.get("sorter_build"), dict):
            wb["sorter_build"] = existing["sorter_build"]
        elif isinstance(existing.get("sorter"), dict):
            wb["sorter_build"] = existing["sorter"]
        if isinstance(existing.get("sawtooth_build"), dict):
            wb["sawtooth_build"] = existing["sawtooth_build"]
        elif isinstance(existing.get("sawtooth"), dict):
            wb["sawtooth_build"] = existing["sawtooth"]
        if isinstance(existing.get("wcs_build"), dict):
            wb["wcs_build"] = existing["wcs_build"]
        elif isinstance(existing.get("wcs"), dict):
            wb["wcs_build"] = existing["wcs"]
        if isinstance(existing.get("safety_build"), dict) and (
            (existing.get("safety_build") or {}).get("zones")
            or (existing.get("safety_build") or {}).get("devices")
        ):
            # Persist engineer membership decisions only — device inventory is
            # rediscovered from the current RUN by build_safety_model().
            sb = dict(existing["safety_build"])
            sb.pop("devices", None)
            wb["safety_build"] = sb
    elif existing and not allow_preserve:
        wb.setdefault(
            "_identity_reset",
            {
                "reason": "different_project_identity",
                "existing": getattr(existing_identity, "project_key", None)
                if existing_identity
                else None,
                "current": getattr(current_identity, "project_key", None)
                if current_identity
                else None,
            },
        )
    return wb


def apply_workbook_to_input(inp: AutogenInput, workbook: dict) -> AutogenInput:
    """Overlay human workbook edits onto AutogenInput before L5X generate.

    LIVE HANDOFF CONTRACT:
      Engineer Transport Apply (conveyors/areas) and Safety Apply (safety_build)
      are authoritative. An empty conveyors list must NOT skip safety_build —
      that caused field builds where testt111_ESZone1 existed on disk but the
      compiler fell back to ORNCCP2_Area + ES shell only.
    """
    if not workbook or not isinstance(workbook, dict):
        return inp

    rows = workbook.get("conveyors") or []
    # NOTE: do not return early — safety_build / project metadata still apply

    by_name = {
        (r.get("conveyor") or "").strip().upper(): r
        for r in rows
        if (r.get("conveyor") or "").strip()
    }

    if rows:
        new_convs: list[ConveyorRow] = []
        areas: list[str] = []
        seen_names: set[str] = set()
        for c in inp.conveyors or []:
            key = (c.conveyor or "").strip().upper()
            w = by_name.get(key)
            if w is not None and w.get("include") in (False, 0, "0", "false", "False"):
                continue  # excluded by engineer
            if w:
                c.main_area = (w.get("main_area") or c.main_area or "").strip()
                c.safety_zone = (w.get("safety_zone") or c.safety_zone or "").strip()
                c.type = (w.get("type") or c.type or "").strip()
                if "exit_pe_tag" in w:
                    c.exit_pe_tag = (w.get("exit_pe_tag") or "").strip()
                if "add_pe_tag" in w:
                    c.add_pe_tag = (w.get("add_pe_tag") or "").strip()
                if "exit_pe_opt" in w and w.get("exit_pe_opt") is not None:
                    c.exit_pe = (w.get("exit_pe_opt") or "").strip()
                if "downstream" in w and w.get("downstream") is not None:
                    c.downstream = (w.get("downstream") or "").strip()
                for k in ("jam_pe_tags", "full_pe_tags", "product_pe_tags", "all_pe_tags"):
                    if k in w and w.get(k) is not None:
                        setattr(
                            c,
                            k,
                            [str(x).strip() for x in (w.get(k) or []) if str(x).strip()],
                        )
                if "vfd" in (c.type or "").lower():
                    c.motor_starter = ""
                elif not c.motor_starter:
                    c.motor_starter = "Yes"
            if c.main_area and c.main_area not in areas:
                areas.append(c.main_area)
            if key:
                seen_names.add(key)
            new_convs.append(c)

        # Transport Build may create stub conveyors not yet in this RUN — ONLY when
        # the stub was explicitly engineer-created for THIS project identity.
        # A workbook row from another project must never create equipment.
        try:
            from fortna_project_identity import (
                identity_from_run,
                identity_from_workbook,
                same_project,
            )

            _wb_ident = identity_from_workbook(workbook)
            _run_ident = None
            _run = getattr(inp, "run_dir", None)
            if _run:
                _run_ident = identity_from_run(_run)
            _same = same_project(_wb_ident, _run_ident) if _run_ident else bool(_wb_ident)
        except Exception:
            _same = True

        for w in rows:
            name = (w.get("conveyor") or "").strip()
            key = name.upper()
            if not key or key in seen_names:
                continue
            if w.get("include") in (False, 0, "0", "false", "False"):
                continue
            if not _same:
                continue
            # Require explicit engineer lineage on stubs absent from RUN.
            src = str(w.get("source") or w.get("lineage") or "").strip().lower()
            eng = bool(
                w.get("engineerCreated")
                or w.get("engineer_created")
                or w.get("edited")
                or src in ("engineer", "transport_build", "engineer_created")
            )
            if not eng:
                continue
            main_area = (w.get("main_area") or "").strip() or "Transport"
            jam = [str(x).strip() for x in (w.get("jam_pe_tags") or []) if str(x).strip()]
            full = [str(x).strip() for x in (w.get("full_pe_tags") or []) if str(x).strip()]
            product = [str(x).strip() for x in (w.get("product_pe_tags") or []) if str(x).strip()]
            all_pe = [str(x).strip() for x in (w.get("all_pe_tags") or []) if str(x).strip()]
            exit_pe_tag = (w.get("exit_pe_tag") or "").strip()
            add_pe_tag = (w.get("add_pe_tag") or "").strip()
            # Never invent Default_Area_ESZone1 / Unassigned as operational zone
            raw_sz = (w.get("safety_zone") or "").strip()
            if raw_sz and (
                "default" in raw_sz.lower() or "unassigned" in raw_sz.lower()
            ):
                raw_sz = ""
            c = ConveyorRow(
                number=len(new_convs) + 1,
                conveyor=name,
                main_area=main_area,
                safety_zone=raw_sz,
                type=(w.get("type") or "Transport with MS"),
                downstream=(w.get("downstream") or "").strip(),
                motor_starter="Yes" if "vfd" not in str(w.get("type") or "").lower() else "",
                exit_pe_tag=exit_pe_tag,
                add_pe_tag=add_pe_tag,
                jam_pe_tags=jam,
                full_pe_tags=full,
                product_pe_tags=product,
                all_pe_tags=all_pe or ([exit_pe_tag] if exit_pe_tag else []),
            )
            if main_area not in areas:
                areas.append(main_area)
            seen_names.add(key)
            new_convs.append(c)

        for i, c in enumerate(new_convs, start=1):
            c.number = i

        inp.conveyors = new_convs
        if areas:
            inp.areas = areas
            zones: list[str] = []
            seen_z: set[str] = set()

            def _add_zone(z: str) -> None:
                zz = (z or "").strip()
                if not zz:
                    return
                key = zz.upper()
                if key in seen_z:
                    return
                seen_z.add(key)
                zones.append(zz)

            for c in new_convs:
                sz = getattr(c, "safety_zone", "") or ""
                # Conveyor-referenced zones are engineer/RUN assignments — keep
                # even oddly named ones; do not invent from dropdown catalogs.
                if str(sz).strip():
                    _add_zone(str(sz).strip())
            # Gate R — do NOT promote options.safety_zones (UI catalog including
            # Zone1..Zone9_ESZone1) into production AutogenInput.safety_zones.
            for a in workbook.get("areas") or []:
                if isinstance(a, dict):
                    sz = str(a.get("safety_zone") or "").strip()
                    if sz and is_production_safety_zone_name(sz):
                        _add_zone(sz)
            # Do NOT auto-mint ${area}_ESZone1 from area names alone. Production
            # shells come from conveyor.safety_zone / safety_build only.
            inp.safety_zones = zones

    # Always apply engineer Safety membership — even when conveyors[] is empty
    # (Safety Apply must not be skipped just because Transport rows are absent).
    if workbook.get("omit_unresolved_safety") or (
        isinstance(workbook.get("options"), dict)
        and (workbook.get("options") or {}).get("omit_unresolved_safety")
    ):
        try:
            inp.omit_unresolved_safety = True
        except Exception:
            pass
        try:
            if isinstance(workbook.get("options"), dict):
                inp.options = dict(workbook.get("options") or {})
        except Exception:
            pass
    sb = workbook.get("safety_build")
    if isinstance(sb, dict):
        inp.safety_build = sb
        if isinstance(sb.get("zones"), list):
            inp.safety_zone_members = list(sb.get("zones") or [])
            # Stamp Area/SafetyZone onto conveyors from Safety Build conveyorRefs
            # when Transport Apply rows are missing — engineer Safety state is
            # authoritative for those assignments.
            by_conv = {
                (getattr(c, "conveyor", "") or "").strip().upper(): c
                for c in (inp.conveyors or [])
            }
            areas_now = list(inp.areas or [])
            zones_now = list(inp.safety_zones or [])
            for z in sb.get("zones") or []:
                aname = str(z.get("area") or z.get("areaRef") or "").strip()
                zname = str(
                    z.get("source_id")
                    or z.get("engineering_name")
                    or z.get("name")
                    or ""
                ).strip()
                eng_keep = bool(z.get("engineerEdited")) or bool(z.get("members"))
                run_keep = bool(z.get("runDiscovered")) or str(
                    z.get("provenance") or z.get("origin") or ""
                ).strip() in {"RUN_DISCOVERED", "ENGINEER_CREATED"}
                # Gate R — drop unused Zone1..Zone9 / numeric test shells unless
                # engineer-authored, RUN-discovered, or already conveyor-referenced.
                # GATE 4 — RUN_DISCOVERED shells must survive even with empty members.
                if zname and zname not in zones_now:
                    if eng_keep or run_keep or is_production_safety_zone_name(zname) or any(
                        str(t or "").strip()
                        for t in (z.get("conveyors") or z.get("conveyorRefs") or [])
                    ):
                        if not is_placeholder_or_test_zone_name(zname) or eng_keep:
                            zones_now.append(zname)
                for tag in (z.get("conveyors") or z.get("conveyorRefs") or []):
                    key = str(tag or "").strip().upper()
                    c = by_conv.get(key)
                    if not c:
                        continue
                    if aname and not is_ui_placeholder_area(aname):
                        c.main_area = aname
                        if aname not in areas_now:
                            areas_now.append(aname)
                    elif aname and is_ui_placeholder_area(aname) and eng_keep:
                        c.main_area = aname
                        if aname not in areas_now:
                            areas_now.append(aname)
                    if zname and (eng_keep or not is_placeholder_or_test_zone_name(zname)):
                        c.safety_zone = zname
            if areas_now:
                inp.areas = [a for a in areas_now if a]
            if zones_now:
                inp.safety_zones = zones_now
    if workbook.get("project_name"):
        inp.project_name = str(workbook["project_name"])
    if workbook.get("processor"):
        inp.processor = str(workbook["processor"])

    # --- Full compiler handoff (GUI Autogen + Qualification must share this) ---
    # Previously sorter_build / include_programs / sawtooth / merges were NOT
    # overlaid here → Qualification Replay built a hollow PLC while reporting PASS.
    _overlay_compiler_handoff(inp, workbook)
    return inp


def _overlay_compiler_handoff(inp: AutogenInput, workbook: dict) -> None:
    """Overlay sorter/sawtooth/WCS/merges/include_programs from saved workbook."""
    sb = workbook.get("sorter_build")
    if isinstance(sb, dict) and sb:
        inp.sorter_build = dict(sb)
    elif isinstance(workbook.get("sorter"), dict) and workbook.get("sorter"):
        inp.sorter_build = dict(workbook["sorter"])

    sm = workbook.get("sorter_model")
    if isinstance(sm, dict) and sm:
        try:
            inp.sorter_model = dict(sm)
        except Exception:
            pass

    saw = workbook.get("sawtooth_build")
    if isinstance(saw, dict) and saw:
        inp.sawtooth_build = dict(saw)
    elif isinstance(workbook.get("sawtooth"), dict) and workbook.get("sawtooth"):
        inp.sawtooth_build = dict(workbook["sawtooth"])

    wcs = workbook.get("wcs_build")
    if isinstance(wcs, dict) and wcs:
        try:
            inp.wcs_build = dict(wcs)
        except Exception:
            # AutogenInput may not declare wcs_build yet — stash on options
            opts = dict(getattr(inp, "options", None) or {})
            opts["wcs_build"] = dict(wcs)
            try:
                inp.options = opts
            except Exception:
                pass
    wm = workbook.get("wcs_model")
    if isinstance(wm, dict) and wm:
        try:
            inp.wcs_model = dict(wm)
        except Exception:
            pass

    merges = workbook.get("merges_2to1")
    if isinstance(merges, list) and merges:
        # Prefer workbook merges; keep discovery fills for blank fields later
        inp.merges_2to1 = [dict(m) for m in merges if isinstance(m, dict)]

    # Program inclusion: workbook.options.include_programs or top-level
    opts = workbook.get("options") if isinstance(workbook.get("options"), dict) else {}
    inc = (
        workbook.get("include_programs")
        or opts.get("include_programs")
        or opts.get("program_packs")
        or []
    )
    if isinstance(inc, list) and inc:
        inp.include_programs = [str(x).strip() for x in inc if str(x).strip()]
    else:
        # Derive from Applied subsystem state when checkbox list absent
        derived: list[str] = list(getattr(inp, "include_programs", None) or [])
        sb_cfg = getattr(inp, "sorter_build", None) or {}
        if isinstance(sb_cfg, dict) and (
            sb_cfg.get("appliedAt")
            or int(sb_cfg.get("divert_count") or 0) > 0
            or (sb_cfg.get("tracking") or [])
            or (sb_cfg.get("known_sorters") or [])
        ):
            if "Sorter_Track" not in derived:
                derived.append("Sorter_Track")
            # Shipping sorter area L3 when area identity present
            area = str(
                sb_cfg.get("sorter_area_name")
                or sb_cfg.get("area_name")
                or ""
            ).strip()
            if sb_cfg.get("shipping_sorter_supported") or area:
                if "ShippingSorter_Area_L3" not in derived:
                    derived.append("ShippingSorter_Area_L3")
        saw_cfg = getattr(inp, "sawtooth_build", None) or {}
        if isinstance(saw_cfg, dict) and (
            saw_cfg.get("collector_conveyor") or (saw_cfg.get("lanes") or [])
        ):
            if "Sawtooth_Merge" not in derived:
                derived.append("Sawtooth_Merge")
        wcs_cfg = workbook.get("wcs_build") or opts.get("wcs_build") or {}
        if isinstance(wcs_cfg, dict) and (
            wcs_cfg.get("enabled") or wcs_cfg.get("appliedAt") or wcs_cfg.get("include")
        ):
            if "WCS_Interface_TCP_IP" not in derived:
                derived.append("WCS_Interface_TCP_IP")
        inp.include_programs = derived

    if isinstance(opts, dict) and opts:
        try:
            base_opts = dict(getattr(inp, "options", None) or {})
            base_opts.update(opts)
            inp.options = base_opts
        except Exception:
            pass


def build_effective_autogen_input(
    run_dir,
    workbook: dict | None = None,
    *,
    machine: str = "",
):
    """Canonical compiler handoff shared by GUI Autogen and Qualification Runner.

    load_from_run(RUN) → apply_workbook_to_input(workbook) including full
    sorter/sawtooth/WCS/merges/include_programs overlay.
    """
    from pathlib import Path

    from fortna_autogen import load_from_run

    run_dir = Path(run_dir)
    inp = load_from_run(run_dir)
    if machine and str(machine).strip():
        try:
            inp.machine = str(machine).strip()
        except Exception:
            pass
    if workbook and isinstance(workbook, dict):
        inp = apply_workbook_to_input(inp, workbook)
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
    if not path.is_file() and path == DEFAULT_WORKBOOK_PATH and _LEGACY_WORKBOOK_PATH.is_file():
        path = _LEGACY_WORKBOOK_PATH
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
    ap = argparse.ArgumentParser(description="Site Forge AutoGen workbook")
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
