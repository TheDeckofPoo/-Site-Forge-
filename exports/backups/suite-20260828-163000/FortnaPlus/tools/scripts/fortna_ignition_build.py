#!/usr/bin/env python3
"""
fortna_ignition_build.py — Layout + tag/device seed for Ignition Build tab.

Gold layout source = RUN Conveyor.asc (X_cord / Y_cord / Width / Length / Angle).
PDF prints add panel labels / zones via OCR later; geometry is far more reliable
from the tar.gz than reconstructing CAD lines from multi-sheet PDFs.

Exports (not a full .gwbk yet):
  - layout.json       equipment with plant coordinates
  - layout.svg        schematic overview for the dashboard
  - tags_import.json  Memory tags for Designer Import Tags (all zones)
  - devices.json      device inventory for Perspective bindings
  - ignition_manifest.json

Future: pack tag JSON + Perspective view resources into a partial project zip
or guided .gwbk assembly (Ignition gateway backup is a versioned ZIP).

Usage:
  py tools/scripts/fortna_ignition_build.py build --run-dir workspace/active/RUN
  py tools/scripts/fortna_ignition_build.py build --use-active
"""
from __future__ import annotations

import argparse
import json
import math
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

from fortna_asc import read_asc  # noqa: E402
from fortna_io_extract import (  # noqa: E402
    equipment_kind,
    normalize_io_name,
    parse_drawing_page,
    read_project_meta,
)

SKIP = frozenset({
    "", "INVALID", "N/A", "SPARE", "ALWAYSON", "NEVERON", "NONE", "~", "N/A~",
})
# Types that are layout decoration only
SKIP_TYPES = frozenset({"INVALID", "IMAGE"})

KIND_COLORS = {
    "conveyor": "#22d3ee",
    "vfd": "#f59e0b",
    "motor": "#a78bfa",
    "photoeye": "#34d399",
    "power_supply": "#f472b6",
    "beacon": "#fbbf24",
    "estop": "#f87171",
    "pushbutton": "#60a5fa",
    "sorter": "#c084fc",
    "scanner": "#2dd4bf",
    "device": "#94a3b8",
}

# Physical conveyor mechanical types in Conveyor.asc (plan geometry)
PHYSICAL_CONV_TYPES = frozenset({
    "STRAIGHT", "BELT", "CURVE", "MERGE", "SKEW", "SPUR", "TRIANG",
    "ACCUM", "ZEROPRESSURE", "MOTOR", "SPIRAL", "GAPPER",
})


def _f(val, default: float = 0.0) -> float:
    try:
        s = str(val or "").strip().replace(",", "")
        if not s or s in ("N/A", "~", "-1", "-1.000"):
            return default
        return float(s)
    except ValueError:
        return default


def _safe_tag(name: str) -> str:
    t = re.sub(r"[^A-Za-z0-9_/]", "_", (name or "").strip())
    t = re.sub(r"_+", "_", t).strip("_")
    if not t:
        return "Tag"
    if t[0].isdigit():
        t = f"T_{t}"
    return t[:80]


def load_layout_equipment(
    run_dir: Path,
    *,
    machine: str | None = None,
    scope_to_machine: bool = True,
) -> list[dict]:
    """
    Equipment rows with plant coordinates from Conveyor.asc.

    When scope_to_machine=True (default), only devices for this master PLC:
      - Machine_Name match, or
      - IO word on this controller's EIP map, or
      - conveyor linked from an in-scope photoeye/VFD
    """
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"
    conv = run_dir / "FORTNA" / "Conveyor.asc"
    if not conv.is_file():
        raise FileNotFoundError(f"Missing Conveyor.asc under {run_dir}")

    from fortna_io_extract import (
        belongs_to_controller,
        read_project_meta,
        row_machine_matches,
    )
    from fortna_autogen import load_eip_topology

    meta = read_project_meta(run_dir)
    controller = (machine or meta.get("machine_name") or "").strip()
    word_map: dict = {}
    if scope_to_machine and controller:
        try:
            word_map = dict((load_eip_topology(run_dir) or {}).get("word_map") or {})
        except Exception:
            word_map = {}

    _, rows = read_asc(conv)

    # Pass 1: in-scope PE / VFD → linked conveyor names
    linked_conveyors: set[str] = set()
    if scope_to_machine and controller:
        for row in rows:
            name = (row.get("IO_Name") or "").strip()
            if not name:
                continue
            typ = (row.get("Type") or "").strip()
            desc = (row.get("General_Description") or "")[:160]
            drive = (row.get("Drive") or "").strip()
            kind = equipment_kind(name, typ, desc, drive=drive)
            if kind not in ("photoeye", "vfd"):
                continue
            if not belongs_to_controller(
                machine_name=(row.get("Machine_Name") or "").strip(),
                io_word=str(row.get("IO_Address_Word") or "").strip(),
                controller=controller,
                word_map=word_map,
            ):
                continue
            # PE → P### from name / description
            text = f"{name} {desc}".upper()
            for m in re.finditer(r"\bP(\d{2,4}[A-Z]?)\b", text):
                linked_conveyors.add(f"P{m.group(1)}")
            m = re.search(r"(?:EZ)?PE(\d{2,4}[A-Z]?)", name, re.I)
            if m:
                linked_conveyors.add(f"P{m.group(1).upper()}")
            if kind == "vfd":
                dm = re.search(r"(\d{2,4})", name)
                if dm:
                    linked_conveyors.add(f"P{dm.group(1)}")

    out: list[dict] = []
    for row in rows:
        name = (row.get("IO_Name") or "").strip()
        if not name or name.upper() in SKIP:
            continue
        typ = (row.get("Type") or "").strip()
        if typ.upper() in SKIP_TYPES:
            continue
        desc = (row.get("General_Description") or row.get("Device_Description") or "")[:160]
        drive = (row.get("Drive") or "").strip()
        kind = equipment_kind(name, typ, desc, drive=drive)
        word = (row.get("IO_Address_Word") or "").strip()
        bit = (row.get("IO_Address_Bit") or "").strip()
        row_mach = (row.get("Machine_Name") or "").strip()

        if scope_to_machine and controller:
            is_physical_conv = typ.upper() in PHYSICAL_CONV_TYPES and (
                kind == "conveyor" or name.upper().startswith("P")
            )
            if is_physical_conv and re.match(r"^P\d", name, re.I):
                # Conveyors often untagged (Machine_Name=N/A) — keep if PE/VFD-linked
                name_u = normalize_io_name(name).upper()
                base_m = re.match(r"^(P\d{2,4})", name_u)
                base = base_m.group(1) if base_m else name_u
                if row_mach and row_mach.upper() not in ("N/A", "INVALID", "", "NONE", "ALL"):
                    if not row_machine_matches(row_mach, controller):
                        continue
                elif name_u not in linked_conveyors and base not in linked_conveyors:
                    if not any(
                        lc == name_u or lc.startswith(name_u) or name_u.startswith(lc)
                        for lc in linked_conveyors
                    ):
                        continue
            else:
                # PE / VFD / motors / beacons: machine or RIO word
                if not belongs_to_controller(
                    machine_name=row_mach,
                    io_word=word,
                    controller=controller,
                    word_map=word_map,
                ):
                    continue

        x = _f(row.get("X_cord") or row.get("X_COORD"))
        y = _f(row.get("Y_cord") or row.get("Y_COORD"))
        # Keep zero-origin only if named equipment with type (some sites park at 0)
        w = abs(_f(row.get("Width"), 200))
        length = _f(row.get("Length"), 0)
        if length < 0:
            length = 800.0
        if length == 0:
            length = 400.0
        angle = _f(row.get("Angle"), 0)
        bank = f"Bank{word}.{bit}" if word or bit else ""
        is_physical_conv = typ.upper() in PHYSICAL_CONV_TYPES and (
            kind == "conveyor" or name.upper().startswith("P")
        )
        drawing_page = parse_drawing_page(row)
        out.append({
            "id": normalize_io_name(name) or name,
            "name": name,
            "type": typ,
            "kind": kind,
            "is_physical_conveyor": is_physical_conv,
            "machine_name": row_mach,
            "x": x,
            "y": y,
            "width": max(w, 80),
            "length": max(length, 200),
            "angle": angle,
            "description": desc,
            "drive": drive,
            "io_address": bank,
            "motor": (row.get("Motor") or "").strip(),
            "drawing_page": drawing_page,
            "print_page": drawing_page,
            "color": KIND_COLORS.get(kind, KIND_COLORS["device"]),
            "ignition_tag": f"[default]Site/{_safe_tag(kind)}/{_safe_tag(name)}",
        })
    return out


def load_eip_modules(run_dir: Path) -> dict:
    """
    EtherNet/IP adapters + I/O modules + IPs from RUN.

    Sources (in priority order):
      FORTNA/*-RTA-eipcfg.xml  — interface IP, adapter target IPs, module types/slots
      PROJECT/EIPAdapters.asc.* — rack, TargetIP, TtlModules
      PROJECT/EIPModules.asc.*  — per-slot module inventory
    """
    import xml.etree.ElementTree as ET
    from collections import Counter

    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"

    result: dict = {
        "interface_ip": "",
        "adapters": [],
        "module_type_counts": {},
        "adapter_count": 0,
        "module_count": 0,
        "sources": [],
    }

    # XML (RTA eipcfg) — prefer THIS machine's file. Multi-PLC Reno tars ship
    # MSCRENOPACK/PICK/SHIP + CPEIP eipcfg side-by-side; taking the first
    # alphabetically left SHIP with only PACK/test racks.
    machine = ""
    try:
        from fortna_io_extract import read_project_meta
        machine = (read_project_meta(run_dir).get("machine_name") or "").strip()
    except Exception:
        machine = ""
    all_xml = list((run_dir / "FORTNA").glob("*-eipcfg.xml")) + list(
        (run_dir / "FORTNA").glob("*eipcfg*.xml")
    )
    # de-dupe paths
    seen_xp: set[str] = set()
    xml_hits: list[Path] = []
    for xp in all_xml:
        k = str(xp.resolve())
        if k in seen_xp:
            continue
        seen_xp.add(k)
        xml_hits.append(xp)

    def _xml_rank(xp: Path) -> tuple:
        n = xp.name.upper()
        mach_u = machine.upper()
        if mach_u and mach_u in n and "SAVE" not in n:
            return (0, n)
        if mach_u and mach_u.replace("MSCRENO", "") and mach_u.replace("MSCRENO", "") in n:
            # e.g. SHIP in MSCRENOSHIP-RTA1-eipcfg.xml
            return (0, n)
        if n.startswith("CPEIP") or "TEST" in n:
            return (3, n)
        if "SAVE" in n:
            return (4, n)
        # Other site machines in the same tar
        if any(x in n for x in ("PACK", "PICK", "SHIP", "GNS")) and (
            not mach_u or mach_u not in n
        ):
            return (2, n)
        return (1, n)

    xml_hits.sort(key=_xml_rank)
    for xp in xml_hits:
        try:
            root = ET.parse(xp).getroot()
        except ET.ParseError:
            continue
        adapters_here = []
        types: Counter = Counter()
        for ad in root.findall("Adapter"):
            mods = []
            for m in ad.findall("Module"):
                mt = (m.get("type") or "").strip()
                mods.append({
                    "name": m.get("name") or "",
                    "type": mt,
                    "slot": m.get("slot") or "",
                    "connection": m.get("connection") or "",
                })
                if mt:
                    types[mt] += 1
            adapters_here.append({
                "name": ad.get("name") or "",
                "ip": ad.get("targetip") or "",
                "input_address": ad.get("InputAddress") or "",
                "output_address": ad.get("OutputAddress") or "",
                "module_count": len(mods),
                "modules": mods,
            })
        if not adapters_here:
            continue
        result["interface_ip"] = root.get("interfaceip") or root.get("name") or ""
        result["sources"].append(str(xp.relative_to(run_dir)))
        result["adapters"] = adapters_here
        result["module_type_counts"] = dict(types)
        result["adapter_count"] = len(result["adapters"])
        result["module_count"] = sum(a["module_count"] for a in result["adapters"])
        # Prefer machine-matched eipcfg; otherwise keep first usable and continue
        # only if this file is ranked as this machine's.
        if _xml_rank(xp)[0] == 0 or not machine:
            return result
        # Non-matching file: keep as fallback but try a better one
        # (loop continues; better rank already sorted first so we usually return above)
        return result

    # Fallback ASC
    proj = run_dir / "PROJECT"
    for p in sorted(proj.glob("EIPAdapters.asc*")):
        _, rows = read_asc(p)
        result["sources"].append(str(p.relative_to(run_dir)))
        for r in rows:
            name = (r.get("Name") or "").strip()
            if not name or name.upper() in ("N/A", "INVALID"):
                continue
            result["adapters"].append({
                "name": name,
                "ip": (r.get("TargetIP") or "").strip(),
                "rack": (r.get("Rack") or "").strip(),
                "module_count": int(_f(r.get("TtlModules"), 0)),
                "modules": [],
            })
        result["adapter_count"] = len(result["adapters"])
        break

    for p in sorted(proj.glob("EIPModules.asc*")):
        _, rows = read_asc(p)
        result["sources"].append(str(p.relative_to(run_dir)))
        types = Counter()
        by_ad: dict[str, list] = {}
        for r in rows:
            name = (r.get("Name") or "").strip()
            if not name or name.upper() in ("N/A", "INVALID"):
                continue
            mt = (r.get("Type") or "").strip()
            ad = (r.get("Adapter") or "").strip()
            mod = {
                "name": name,
                "type": mt,
                "slot": (r.get("Slot") or "").strip(),
                "connection": (r.get("Connection") or "").strip(),
                "rack": (r.get("Rack") or "").strip(),
            }
            by_ad.setdefault(ad or "?", []).append(mod)
            if mt:
                types[mt] += 1
        # attach modules to adapters when names match
        for a in result["adapters"]:
            a["modules"] = by_ad.get(a["name"], [])
            if a["modules"]:
                a["module_count"] = len(a["modules"])
        result["module_type_counts"] = dict(types)
        result["module_count"] = sum(len(v) for v in by_ad.values())
        break

    return result


def _area_for_name(name: str) -> str:
    """
    Map equipment name → ZoneN for tag folders.

    O'Reilly convention: first digit of the equipment number is the zone.
      P309 / PE309 / EZPE309_F / WB309 → Zone3
    """
    u = (name or "").upper().strip()
    m = re.match(r"^P(\d)", u)
    if m:
        return f"Zone{m.group(1)}"
    # Photoeyes / beacons / ES: EZPE602A_F, PE106_JF, WB500, ES610C
    m = re.match(r"^(?:EZ)?PE(\d)", u)
    if m:
        return f"Zone{m.group(1)[0]}"
    m = re.match(r"^(?:WB|WH|PS|ES|VFD)(\d)", u)
    if m:
        return f"Zone{m.group(1)[0]}"
    # Leading-digit Fortna names: 1ES, 7ES
    m = re.match(r"^(\d)", u)
    if m:
        return f"Zone{m.group(1)}"
    return "Site"


def _atomic(
    name: str,
    *,
    dtype: str = "Boolean",
    opc: str = "",
    doc: str = "",
    tooltip: str = "",
    value_source: str = "opc",
    x: float | None = None,
    y: float | None = None,
) -> dict:
    tag: dict = {
        "name": _safe_tag(name),
        "tagType": "AtomicTag",
        "dataType": dtype,
        "valueSource": value_source,
        "documentation": doc or "",
        "engUnit": "",
        "tooltip": tooltip or "",
    }
    if value_source == "opc" and opc:
        tag["opcServer"] = "Ignition OPC UA Server"
        tag["opcItemPath"] = opc
    elif value_source == "memory":
        tag["value"] = False if dtype == "Boolean" else 0
    if x is not None and y is not None:
        tag["layout"] = {"x": x, "y": y}
    return tag


def build_tag_seed(equipment: list[dict], machine: str) -> dict:
    """Kind-folder draft (legacy). Prefer build_plc_aligned_tags for Logix parity."""
    folders: dict[str, list] = {}
    for e in equipment:
        kind = e.get("kind") or "device"
        folders.setdefault(kind, []).append(
            _atomic(
                e["name"],
                opc=f"ns=1;s=[{machine}]{e['name']}",
                doc=e.get("description") or "",
                tooltip=e.get("io_address") or "",
                x=e.get("x"),
                y=e.get("y"),
            )
        )
    children = [
        {"name": _safe_tag(kind), "tagType": "Folder", "tags": tags}
        for kind, tags in sorted(folders.items())
    ]
    return {
        "name": "Site",
        "tagType": "Folder",
        "tags": children,
        "provider": "default",
        "note": "Kind-folder seed. See tags_plc_aligned.json for Logix-parity paths.",
    }


def to_memory_tags_import(node: dict | list) -> dict | list:
    """
    Convert a PLC-aligned / OPC tag tree into Designer Memory-tag import format.

    - Keeps folder structure (Site / ZoneN / Conveyors / …)
    - Atomic tags → valueSource=memory (works without a PLC device)
    - Drops opcServer / opcItemPath so import never fails on missing device
    """
    if isinstance(node, list):
        return [to_memory_tags_import(x) for x in node]
    if not isinstance(node, dict):
        return node
    out: dict = {}
    for k, v in node.items():
        if k in ("opcServer", "opcItemPath", "provider", "note", "layout"):
            continue
        if k == "tags" and isinstance(v, list):
            out[k] = [to_memory_tags_import(c) for c in v]
        elif k == "children" and isinstance(v, list):
            out["tags"] = [to_memory_tags_import(c) for c in v]
        else:
            out[k] = v
    # Atomic tags: force memory source + default value
    if (out.get("tagType") or "").lower() in ("atomictag", "atomic"):
        out["valueSource"] = "memory"
        dtype = (out.get("dataType") or "Boolean").lower()
        if "value" not in out:
            if dtype in ("boolean", "bool"):
                # Clear PE defaults True (green); Run defaults False
                name = (out.get("name") or "").lower()
                out["value"] = True if name in ("clear", "pe_clear") else False
            elif dtype in ("string",):
                out["value"] = out.get("value") or ""
            else:
                out["value"] = 0
        out.pop("opcServer", None)
        out.pop("opcItemPath", None)
    return out


def build_plc_aligned_tags(equipment: list[dict], machine: str, eip: dict | None = None) -> dict:
    """
    Tag tree aligned with fortna_autogen L5X naming so HMI and PLC share one model:

      [default]Site/Zone1/Conveyors/P116/Run
      [default]Site/Zone1/Photoeyes/EZPE116_P/Clear
      [default]Site/EIP/CP5RIO0/...

    opcItemPath targets Logix tags after autogen (P116_Conv, EZPE116_P.I.PE_Clear, …).
    """
    plc = _safe_tag(machine) or "PLC"
    by_area: dict[str, dict[str, list]] = {}

    for e in equipment:
        name = (e.get("name") or "").strip()
        if not name:
            continue
        kind = e.get("kind") or "device"
        area = _area_for_name(name)
        bucket = by_area.setdefault(area, {"conveyors": [], "photoeyes": [], "drives": [], "other": []})
        safe = _safe_tag(name)
        x, y = e.get("x"), e.get("y")
        io = e.get("io_address") or ""
        doc = e.get("description") or ""

        if e.get("is_physical_conveyor") or (
            kind == "conveyor" and re.match(r"^P\d", name, re.I)
        ):
            # Mirror L5X: Pxxx_Conv UDT members used by HMI
            conv_folder = {
                "name": safe,
                "tagType": "Folder",
                "tags": [
                    _atomic("Run", opc=f"ns=1;s=[{plc}]{safe}_Conv.Run", doc=doc, tooltip=io, x=x, y=y),
                    _atomic("Fault", opc=f"ns=1;s=[{plc}]{safe}_Conv.Flt", dtype="Boolean"),
                    _atomic("Jam", opc=f"ns=1;s=[{plc}]{safe}_Conv.Jam", dtype="Boolean"),
                    _atomic("Type", opc=f"ns=1;s=[{plc}]{safe}_Conv.Type", dtype="Int4", value_source="opc"),
                    _atomic(
                        "Label",
                        dtype="String",
                        value_source="memory",
                        doc=f"{name} {(e.get('type') or '')}".strip(),
                    ),
                ],
            }
            # memory default for Label
            conv_folder["tags"][-1]["value"] = name
            bucket["conveyors"].append(conv_folder)
        elif kind == "photoeye":
            bucket["photoeyes"].append({
                "name": safe,
                "tagType": "Folder",
                "tags": [
                    _atomic(
                        "Clear",
                        opc=f"ns=1;s=[{plc}]{safe}.I.PE_Clear",
                        doc=doc,
                        tooltip=io,
                        x=x,
                        y=y,
                    ),
                    _atomic("Jam", opc=f"ns=1;s=[{plc}]{safe}.Flt.PE_Jam", dtype="Boolean"),
                    _atomic("Full", opc=f"ns=1;s=[{plc}]{safe}.Full", dtype="Boolean"),
                ],
            })
        elif kind in ("vfd", "motor"):
            bucket["drives"].append(
                _atomic(
                    safe,
                    opc=f"ns=1;s=[{plc}]{safe}",
                    doc=doc,
                    tooltip=io,
                    x=x,
                    y=y,
                )
            )
        else:
            bucket["other"].append(
                _atomic(safe, opc=f"ns=1;s=[{plc}]{safe}", doc=doc, tooltip=io, x=x, y=y)
            )

    area_folders = []
    for area in sorted(by_area.keys()):
        b = by_area[area]
        kids = []
        if b["conveyors"]:
            kids.append({"name": "Conveyors", "tagType": "Folder", "tags": b["conveyors"]})
        if b["photoeyes"]:
            kids.append({"name": "Photoeyes", "tagType": "Folder", "tags": b["photoeyes"]})
        if b["drives"]:
            kids.append({"name": "Drives", "tagType": "Folder", "tags": b["drives"]})
        if b["other"]:
            kids.append({"name": "Other", "tagType": "Folder", "tags": b["other"]})
        # Area control bits (match Area_UDT used in Slow_Flt / PE_Logic)
        kids.insert(0, {
            "name": "Area",
            "tagType": "Folder",
            "tags": [
                _atomic("Run", opc=f"ns=1;s=[{plc}]{area}_Area.Run"),
                _atomic("Jam_Reset", opc=f"ns=1;s=[{plc}]{area}_Area.Jam_Reset"),
                _atomic("MtrFlt_Reset", opc=f"ns=1;s=[{plc}]{area}_Area.MtrFlt_Reset"),
            ],
        })
        area_folders.append({"name": area, "tagType": "Folder", "tags": kids})

    # EIP adapters — prefer PLC topology (CP1RIO0…CP4RIO2 with .51–.58).
    # eipcfg XML alone lists PointIO 1734 names and can miss .57/.58 Flex heads.
    eip_tags = []
    topo = list((eip or {}).get("topology") or [])
    # Prefer adapters that appear in word_map (this controller’s RIO), drop
    # multi-panel duplicates (CP5/CP6 reusing same IPs).
    used_rios = {
        str((info or {}).get("rio_name") or "").strip()
        for info in ((eip or {}).get("word_map") or {}).values()
        if isinstance(info, dict) and (info or {}).get("rio_name")
    }
    if topo:
        for ad in topo:
            rio = (ad.get("rio_name") or ad.get("name") or "").strip()
            ip = (ad.get("ip") or "").strip()
            if not rio:
                continue
            if used_rios and rio not in used_rios:
                continue
            eip_tags.append(
                _atomic(
                    _safe_tag(rio),
                    dtype="Boolean",
                    value_source="memory",
                    doc=f"Flex RIO {rio} @ {ip}",
                    tooltip=ip,
                )
            )
    else:
        for i, ad in enumerate((eip or {}).get("adapters") or []):
            ip = (ad.get("ip") or "").strip()
            name = (ad.get("name") or f"AENT_{i}").strip()
            # Prefer CPxRIOn-style label from last IP octet when possible
            label = name
            m = re.search(r"\.(\d+)$", ip)
            if m:
                last = int(m.group(1))
                # Map common Fortna octets → panel (display only)
                if 51 <= last <= 58:
                    label = f"RIO_{last}"
            eip_tags.append(
                _atomic(
                    _safe_tag(label),
                    dtype="Boolean",
                    value_source="memory",
                    doc=f"EIP adapter {ip} ({name})",
                    tooltip=ip,
                )
            )

    root_tags = list(area_folders)
    if eip_tags:
        root_tags.append({"name": "EIP_Adapters", "tagType": "Folder", "tags": eip_tags})
    root_tags.append({
        "name": "System",
        "tagType": "Folder",
        "tags": [
            _atomic("PLC_Name", dtype="String", value_source="memory", doc=machine),
            _atomic("Heartbeat", dtype="Int4", value_source="memory"),
        ],
    })
    # set memory values
    for t in root_tags[-1]["tags"]:
        if t["name"] == "PLC_Name":
            t["value"] = machine
        if t["name"] == "Heartbeat":
            t["value"] = 0

    return {
        "name": "Site",
        "tagType": "Folder",
        "tags": root_tags,
        "provider": "default",
        "plcDevice": plc,
        "note": (
            "PLC-aligned seed for Ignition Tag Browser import (JSON). "
            "Create Logix driver device named to match opcItemPath [ORNCCP5]… "
            "Paths match fortna_autogen L5X: Pxxx_Conv, PE.I.PE_Clear, ZoneN_Area."
        ),
    }


def build_opc_devices(machine: str, eip: dict) -> dict:
    """Logix / Ethernet device connection seed for Designer (manual or scripted)."""
    plc_ip = (eip or {}).get("interface_ip") or ""
    adapters = []
    for a in (eip or {}).get("adapters") or []:
        adapters.append({
            "name": a.get("name") or "",
            "hostname": a.get("ip") or "",
            "type": "Flex1794",
            "module_count": a.get("module_count") or len(a.get("modules") or []),
        })
    return {
        "gateway": {
            "note": "Create these under Config → OPC UA → Device Connections (or OPC COM)",
        },
        "devices": [
            {
                "name": _safe_tag(machine) or "ORNCCP5",
                "type": "Allen-Bradley Logix Driver",
                "hostname": plc_ip or "192.168.1.9",
                "slot": 0,
                "connectionPath": "",
                "description": f"Fortna recontrol PLC ({machine}) — from RUN eipcfg interface IP",
            }
        ],
        "remote_io": adapters,
        "tag_provider": "default",
        "browse_path_hint": f"[{_safe_tag(machine)}]",
    }


def write_tags_csv(path: Path, equipment: list[dict], machine: str) -> int:
    """Flat CSV for review / Excel; not native Ignition import but useful for commissioning."""
    lines = [
        "area,kind,name,ignition_path,opc_item_path,io_address,x,y,description"
    ]
    plc = _safe_tag(machine)
    n = 0
    for e in equipment:
        name = e.get("name") or ""
        if not name:
            continue
        kind = e.get("kind") or "device"
        area = _area_for_name(name)
        safe = _safe_tag(name)
        if e.get("is_physical_conveyor") or (kind == "conveyor" and re.match(r"^P\d", name, re.I)):
            ign = f"[default]Site/{area}/Conveyors/{safe}/Run"
            opc = f"ns=1;s=[{plc}]{safe}_Conv.Run"
        elif kind == "photoeye":
            ign = f"[default]Site/{area}/Photoeyes/{safe}/Clear"
            opc = f"ns=1;s=[{plc}]{safe}.I.PE_Clear"
        else:
            ign = f"[default]Site/{area}/Other/{safe}"
            opc = f"ns=1;s=[{plc}]{safe}"
        desc = (e.get("description") or "").replace('"', "'")
        lines.append(
            f'{area},{kind},"{name}","{ign}","{opc}","{e.get("io_address") or ""}",'
            f'{e.get("x") or 0},{e.get("y") or 0},"{desc}"'
        )
        n += 1
    path.write_text("\n".join(lines), encoding="utf-8")
    return n


def write_designer_readme(
    path: Path,
    *,
    machine: str,
    plc_ip: str,
    out_dir: Path,
) -> None:
    text = f"""# Ignition import guide — {machine}

Generated by Site Forge `fortna_ignition_build.py`.

## After Ignition installs

1. **Gateway** — start Ignition Gateway (default http://localhost:8088).
2. **Designer** — open Designer, create project e.g. `OReilly_Greensboro`.
3. **Logix device**
   - Config → OPC UA → Device Connections → Create
   - Type: **Allen-Bradley Logix Driver**
   - Name: `{_safe_tag(machine)}`  (must match opc paths)
   - Hostname: `{plc_ip or "192.168.1.9"}`  (from RUN eipcfg)
   - Slot: 0
4. **Tags**
   - Tag Browser → Default provider
   - Import / paste from `tags_plc_aligned.json` (Designer 8.1+ tag JSON export format is close;
     if import fails, create folders manually and use `tags_flat.csv` as the checklist)
5. **Layout**
   - `layout.svg` / `layout_conveyors_only.svg` — drop into a Perspective **Drawing** or Image component
   - Or use `devices.json` x/y to place symbols on a coordinate container
6. **PLC**
   - Download autogen L5X to the controller first so OPC browse paths exist
   - PE live bits: `EZPExxx.I.PE_Clear` (mapped by PLC IO_MAP)
   - Conveyor: `Pxxx_Conv.Run` / `.Jam` / `.Flt`

## Files in this folder

| File | Use |
|------|-----|
| layout.svg | Full site schematic (conveyors + PE/VFD) |
| layout_conveyors_only.svg | Clean belt-only map |
| tags_import.json | **Import this** — Memory tags, all zones |
| tags_plc_aligned.json | Optional OPC paths for live PLC later |
| tags_flat.csv | Spreadsheet checklist |
| devices.json | Symbol list with plant coordinates |
| opc_devices.json | Logix + Flex adapter IPs |
| eip_modules.json | Full EIP inventory |
| layout.json | Full geometry dump |

## Not yet automated

- Full `.gwbk` pack (gateway backup ZIP)
- Perspective view resources with bindings
- UDT import matching PE_UDT / Conv_UDT

See also **INTERACTIVE_LAYOUT.md** for live color (run / PE blocked).
"""
    path.write_text(text, encoding="utf-8")


def write_interactive_readme(path: Path, *, machine: str) -> None:
    text = f"""# Interactive plant layout — {machine}

## Is layout.svg live?

**No.** In Designer, if you drop `layout.svg` into an **Image** (or flat Drawing), it is only a picture.
It will **not** change color when a conveyor runs or a photoeye blocks.

That matches what you are seeing now.

## How live color works

Ignition needs each object bound to a **tag**:

| Object | Tag (from autogen / tags_plc_aligned) | Color idea |
|--------|----------------------------------------|------------|
| Conveyor P116 | `[default]Site/Zone1/Conveyors/P116/Run` → PLC `P116_Conv.Run` | Idle cyan · **Run green** · Fault red |
| PE EZPE116_P | `…/Photoeyes/EZPE116_P/Clear` → `EZPE116_P.I.PE_Clear` | **Clear green** · **Blocked red** (Clear false) |

## Two ways to get there

### A) Recommended — Coordinate symbols (`hmi_symbols.json`)

1. Create small Perspective views: `ConveyorBelt`, `Photoeye` (rectangle / circle).
2. On each view, bind **style.classes** or **fill/stroke** to a view param / tag.
3. Parent view: **Coordinate Container** (or Flex + absolute positions).
4. For each row in `hmi_symbols.json`, place an embedded view at `x_pct` / `y_pct` (0–100).
5. Pass tag paths from the JSON into each instance.

Site Forge will automate embedding later; the JSON is the full placement + binding list today.

### B) SVG with ids (advanced)

`layout.svg` now has:

- `id="conv-P116"`, `id="pe-EZPE116_P"`, …
- `data-tag="[default]Site/.../Run"`
- CSS classes: `.conv.run`, `.pe.blocked`, …

A gateway script or custom module can set `class` / `stroke` from tag change events.
A plain Image component **cannot** do that by itself.

## Larger image

Rebuild from Site Forge **Ignition Build** tab (or CLI). New SVG uses a larger canvas,
thicker belts, bigger PE dots, and tighter padding so the plant fills more of the frame.

```
py tools/scripts/fortna_ignition_build.py build --use-active
```

Then re-import / refresh the SVG in Designer.

## Prerequisites for real live data

1. PLC program downloaded (autogen L5X) so `Pxxx_Conv.Run` and PE bits exist.
2. Logix device in Ignition connected (see `opc_devices.json` / DESIGNER_IMPORT.md).
3. Tags created / imported (`tags_plc_aligned.json`).
4. Interactive symbols (path A) — not a static Image alone.
"""
    path.write_text(text, encoding="utf-8")


def build_devices(equipment: list[dict]) -> list[dict]:
    """Device list for Perspective components / SVG symbols."""
    out = []
    for e in equipment:
        name = e.get("name") or ""
        kind = e.get("kind") or "device"
        area = _area_for_name(name)
        safe = _safe_tag(name)
        if e.get("is_physical_conveyor") or (kind == "conveyor" and re.match(r"^P\d", name, re.I)):
            tag_path = f"[default]Site/{area}/Conveyors/{safe}/Run"
        elif kind == "photoeye":
            tag_path = f"[default]Site/{area}/Photoeyes/{safe}/Clear"
        else:
            tag_path = f"[default]Site/{area}/Other/{safe}"
        out.append({
            "id": e["id"],
            "name": e["name"],
            "class": e["kind"],
            "type": e["type"],
            "area": area,
            "tagPath": tag_path,
            "x": e["x"],
            "y": e["y"],
            "width": e["width"],
            "length": e["length"],
            "angle": e["angle"],
            "io": e.get("io_address") or "",
            "description": e.get("description") or "",
        })
    return out


def _svg_elem_id(prefix: str, name: str) -> str:
    """Stable SVG id for live binding (id must start with a letter)."""
    safe = _safe_tag(name).replace("/", "_")
    return f"{prefix}-{safe}"


def render_svg(
    equipment: list[dict],
    *,
    title: str = "Site layout",
    mode: str = "conveyor",  # conveyor | equipment | all
    machine: str = "PLC",
) -> str:
    """2D schematic for Ignition-style layout (plant units from Conveyor.asc).

    Each conveyor/PE gets a stable id + data-tag attributes so the SVG can become
    live later (Perspective script / coordinate symbols). Static Image = no live
    color; use ids + bindings or hmi_symbols.json for interactivity.

    mode:
      conveyor  — physical belts only (fills holes vs PE scatter)
      equipment — PE / VFD / motor / pwr as symbols on top of belts
      all       — everything plottable
    """
    convs = [
        e for e in equipment
        if e.get("is_physical_conveyor")
        or (e.get("kind") == "conveyor" and (e.get("type") or "").upper() in PHYSICAL_CONV_TYPES)
    ]
    devices = [
        e for e in equipment
        if e.get("kind") in ("photoeye", "vfd", "motor", "power_supply", "sorter", "beacon", "estop", "scanner")
        and not e.get("is_physical_conveyor")
    ]

    if mode == "conveyor":
        pts = convs or [e for e in equipment if e.get("kind") == "conveyor"]
    elif mode == "equipment":
        pts = convs + devices
    else:
        pts = [e for e in equipment if e.get("kind") in KIND_COLORS]

    def _is_parked(e: dict) -> bool:
        x, y = float(e.get("x") or 0), float(e.get("y") or 0)
        # ASC park / unplaced rows (common junk coords)
        if x == 0 and y in (0, 60000):
            return True
        if abs(x) < 50 and abs(y) < 50:
            return True
        # Shared dump coords used by many motors/power supplies
        if abs(x) < 500 and abs(y) < 500 and e.get("kind") in ("motor", "power_supply", "vfd"):
            return True
        return False

    pts = [e for e in pts if not _is_parked(e)]
    convs = [e for e in convs if not _is_parked(e)]
    devices = [e for e in devices if not _is_parked(e)]

    if not pts:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 400">'
            '<rect width="100%" height="100%" fill="#0a0f14"/>'
            '<text x="40" y="200" fill="#64748b" font-family="sans-serif" font-size="16">'
            "No layout points — load a RUN with Conveyor.asc coordinates"
            "</text></svg>"
        )

    # Bounds from densest conveyor cluster (largest collective of conveyance).
    # Ignore floating outliers (parked PE/motors, distant dump coords) so the
    # main plant fills the center of the frame — target ~80%+ useful layout.
    def _endpoint_pts(items: list[dict]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for e in items:
            x0, y0 = float(e["x"]), float(e["y"])
            out.append((x0, y0))
            ang = math.radians(e.get("angle") or 0)
            L = float(e.get("length") or 0)
            if L > 0:
                out.append((x0 + L * math.cos(ang), y0 + L * math.sin(ang)))
        return out

    bound_src = convs if convs else pts
    raw_pts = _endpoint_pts(bound_src)

    def _densest_cluster_bounds(
        pts_xy: list[tuple[float, float]],
    ) -> tuple[float, float, float, float]:
        if not pts_xy:
            return 0.0, 1000.0, 0.0, 1000.0
        if len(pts_xy) < 6:
            xs0 = [p[0] for p in pts_xy]
            ys0 = [p[1] for p in pts_xy]
            return min(xs0), max(xs0), min(ys0), max(ys0)
        xs0 = [p[0] for p in pts_xy]
        ys0 = [p[1] for p in pts_xy]
        span0 = max(max(xs0) - min(xs0), max(ys0) - min(ys0), 1.0)
        # Grid cell ~6% of plant span — groups nearby belts, isolates floaters
        cell = max(span0 * 0.06, 800.0)
        grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
        for x, y in pts_xy:
            key = (int(math.floor(x / cell)), int(math.floor(y / cell)))
            grid.setdefault(key, []).append((x, y))
        # Seed = densest cell
        seed = max(grid.items(), key=lambda kv: len(kv[1]))[0]
        # Flood-fill neighboring cells with any points (8-connected)
        cluster_keys: set[tuple[int, int]] = set()
        stack = [seed]
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in cluster_keys:
                continue
            if (cx, cy) not in grid:
                continue
            cluster_keys.add((cx, cy))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    stack.append((cx + dx, cy + dy))
        cluster_pts = [p for k in cluster_keys for p in grid[k]]
        # Keep cluster if it holds a solid majority; else fall back to percentiles
        if len(cluster_pts) < max(4, int(len(pts_xy) * 0.45)):
            s_x = sorted(xs0)
            s_y = sorted(ys0)
            lo = max(0, int(len(s_x) * 0.05))
            hi = min(len(s_x) - 1, int(len(s_x) * 0.95))
            return s_x[lo], s_x[hi], s_y[lo], s_y[hi]
        cxs = [p[0] for p in cluster_pts]
        cys = [p[1] for p in cluster_pts]
        return min(cxs), max(cxs), min(cys), max(cys)

    min_x, max_x, min_y, max_y = _densest_cluster_bounds(raw_pts)
    # Slight expand so clipped endpoints still show
    margin_u = max(max_x - min_x, max_y - min_y, 1000.0) * 0.04
    min_x -= margin_u
    max_x += margin_u
    min_y -= margin_u
    max_y += margin_u
    content_w = max(max_x - min_x, 800.0)
    content_h = max(max_y - min_y, 800.0)
    # Tight pad so densest plant fills the frame (centered)
    pad = max(content_w, content_h) * 0.02
    span_x = content_w + pad * 2
    span_y = content_h + pad * 2

    def tx(x: float) -> float:
        return x - min_x + pad

    def ty(y: float) -> float:
        return max_y - y + pad  # flip Y

    # Fill a large canvas; scale uses the tighter of W/H so plant is as large as possible.
    # Extra fill factor keeps small sites (1/3 plant) from looking like a corner stamp.
    target_w, target_h = 4200.0, 2600.0
    scale = min(target_w / span_x, target_h / span_y) * 1.35
    vb_w = span_x * scale
    vb_h = span_y * scale
    # Compact chrome: title band + legend band so plant stays centered in remaining space
    chrome_top = 32.0
    chrome_bot = 24.0
    ox, oy = 0.0, chrome_top
    vb_h_total = vb_h + chrome_top + chrome_bot
    plc = _safe_tag(machine) or "PLC"

    n_conv = len(convs)
    n_dev = len(devices) if mode != "conveyor" else 0
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb_w:.1f} {vb_h_total:.1f}" '
        f'width="100%" height="100%" preserveAspectRatio="xMidYMid meet" '
        f'style="background:#0a0f14" data-static="true" data-interactive-ready="ids">',
        # State classes for live scripting later (default = idle colors)
        "<style><![CDATA[",
        "  .conv { stroke-linecap: round; opacity: 0.95; }",
        "  .conv.idle { stroke: #22d3ee; }",
        "  .conv.run { stroke: #22c55e; }",
        "  .conv.fault { stroke: #ef4444; }",
        "  .conv.jam { stroke: #f59e0b; }",
        "  .pe { opacity: 0.98; }",
        "  .pe-ring { fill: none; stroke-width: 1.2; }",
        "  .pe-core { stroke: #0a0f14; stroke-width: 0.5; }",
        "  .pe.clear .pe-core { fill: #34d399; }",
        "  .pe.clear .pe-ring { stroke: #6ee7b7; }",
        "  .pe.blocked .pe-core { fill: #ef4444; }",
        "  .pe.blocked .pe-ring { stroke: #fca5a5; }",
        "  .pe.fault .pe-core { fill: #f59e0b; }",
        "  .pe.fault .pe-ring { stroke: #fcd34d; }",
        "  .pe-label { fill: #94a3b8; font-size: 10px; font-family: Segoe UI,sans-serif; }",
        "  .vfd, .motor { opacity: 0.9; }",
        "]]></style>",
        f'<rect width="100%" height="100%" fill="#0a0f14"/>',
        f'<text x="14" y="22" fill="#64748b" font-family="Segoe UI,sans-serif" font-size="13" font-weight="600">'
        f'{_xml(title)} · {n_conv} belts'
        + (f" · {n_dev} devices" if n_dev else "")
        + "</text>",
        f'<g id="plant" transform="translate({ox:.1f},{oy:.1f})">',
        '<g id="conveyors">',
    ]

    # 1) Physical conveyors as centerline segments (true length + angle)
    for e in convs:
        name = e.get("name") or e.get("id") or "conv"
        safe = _safe_tag(name)
        eid = _svg_elem_id("conv", name)
        area = _area_for_name(name)
        tag_path = f"[default]Site/{area}/Conveyors/{safe}/Run"
        opc = f"ns=1;s=[{plc}]{safe}_Conv.Run"
        x0, y0 = e["x"], e["y"]
        L = max(e.get("length") or 400, 200)
        ang = math.radians(e.get("angle") or 0)
        x1 = x0 + L * math.cos(ang)
        y1 = y0 + L * math.sin(ang)
        sx0, sy0 = tx(x0) * scale, ty(y0) * scale
        sx1, sy1 = tx(x1) * scale, ty(y1) * scale
        # Thick belts so the plant reads large when the SVG is scaled to fit
        stroke = max(min((e.get("width") or 200) * scale * 0.85, 40), 9.0)
        color = e.get("color") or KIND_COLORS["conveyor"]
        typ_u = (e.get("type") or "").upper()
        if typ_u == "CURVE":
            color = "#38bdf8"
        elif typ_u in ("MERGE", "SPUR"):
            color = "#818cf8"
        elif typ_u in ("ACCUM", "ZEROPRESSURE"):
            color = "#2dd4bf"
        page = e.get("drawing_page") or e.get("print_page")
        page_txt = f" · print #{page}" if page else ""
        page_attr = f' data-print-page="{int(page)}"' if page else ""
        parts.append(
            f'<line id="{eid}" class="conv idle" data-name="{_xml(name)}" '
            f'data-kind="conveyor" data-type="{_xml(typ_u)}" '
            f'data-tag="{_xml(tag_path)}" data-opc="{_xml(opc)}" '
            f'data-state-tag="{_xml(tag_path)}"{page_attr} '
            f'x1="{sx0:.1f}" y1="{sy0:.1f}" x2="{sx1:.1f}" y2="{sy1:.1f}" '
            f'stroke="{color}" stroke-width="{stroke:.1f}">'
            f'<title>{_xml(name)} · {_xml(typ_u) or "conveyor"}{page_txt}</title></line>'
        )
    parts.append("</g>")

    # 2) Optional equipment symbols (PE / VFD / motor) — larger for clickability
    if mode in ("equipment", "all"):
        parts.append('<g id="devices">')
        for e in devices:
            name = e.get("name") or e.get("id") or "dev"
            safe = _safe_tag(name)
            kind = e["kind"]
            area = _area_for_name(name)
            cx = tx(e["x"]) * scale
            cy = ty(e["y"]) * scale
            color = e.get("color") or "#94a3b8"
            if kind == "photoeye":
                eid = _svg_elem_id("pe", name)
                tag_path = f"[default]Site/{area}/Photoeyes/{safe}/Clear"
                # PE_Clear true = clear (green); false/blocked = red in live logic
                opc = f"ns=1;s=[{plc}]{safe}.I.PE_Clear"
                # Tiny round PE (no on-map text — name/print live in <title>)
                r_core = 2.4
                r_ring = 3.8
                pe_fill = color if color != "#94a3b8" else "#34d399"
                page = e.get("drawing_page") or e.get("print_page")
                page_txt = f" · print #{page}" if page else ""
                page_attr = f' data-print-page="{int(page)}"' if page else ""
                parts.append(
                    f'<g id="{eid}" class="pe clear" data-name="{_xml(name)}" '
                    f'data-kind="photoeye" data-tag="{_xml(tag_path)}" data-opc="{_xml(opc)}" '
                    f'data-invert-state="false"{page_attr}>'
                    f'<title>{_xml(name)} · photoeye{page_txt}</title>'
                    f'<circle class="pe-ring" cx="{cx:.1f}" cy="{cy:.1f}" r="{r_ring}" '
                    f'stroke="#6ee7b7"/>'
                    f'<circle class="pe-core" cx="{cx:.1f}" cy="{cy:.1f}" r="{r_core}" '
                    f'fill="{pe_fill}"/>'
                    f'</g>'
                )
            elif kind in ("vfd", "power_supply", "motor"):
                eid = _svg_elem_id(kind[:3], name)
                s = 16
                tag_path = f"[default]Site/{area}/Other/{safe}"
                page = e.get("drawing_page") or e.get("print_page")
                page_txt = f" · print #{page}" if page else ""
                page_attr = f' data-print-page="{int(page)}"' if page else ""
                parts.append(
                    f'<rect id="{eid}" class="{kind}" data-name="{_xml(name)}" '
                    f'data-kind="{kind}" data-tag="{_xml(tag_path)}"{page_attr} '
                    f'x="{cx - s/2:.1f}" y="{cy - s/2:.1f}" width="{s}" height="{s}" '
                    f'fill="{color}" rx="3">'
                    f'<title>{_xml(name)} · {_xml(kind)}{page_txt}</title></rect>'
                )
            else:
                eid = _svg_elem_id("dev", name)
                page = e.get("drawing_page") or e.get("print_page")
                page_txt = f" · print #{page}" if page else ""
                page_attr = f' data-print-page="{int(page)}"' if page else ""
                parts.append(
                    f'<circle id="{eid}" data-name="{_xml(name)}" data-kind="{kind}"'
                    f'{page_attr} '
                    f'cx="{cx:.1f}" cy="{cy:.1f}" r="5.5" fill="{color}" opacity="0.85">'
                    f'<title>{_xml(name)} · {_xml(kind)}{page_txt}</title></circle>'
                )
        parts.append("</g>")

    parts.append("</g>")  # plant group

    # Compact legend in bottom chrome band (does not shrink the plant)
    ly = vb_h_total - 10
    parts.append('<g font-family="Segoe UI,sans-serif" font-size="11" fill="#64748b">')
    legend_items = [
        ("rect", "#22d3ee", "Belt"),
        ("circle", "#34d399", "PE"),
        ("rect", "#f59e0b", "Jam/VFD"),
    ]
    for i, (shape, col, lab) in enumerate(legend_items):
        x = 14 + i * 100
        if shape == "circle":
            parts.append(f'<circle cx="{x + 5}" cy="{ly - 4}" r="4" fill="{col}"/>')
        else:
            parts.append(f'<rect x="{x}" y="{ly - 8}" width="14" height="5" fill="{col}" rx="1"/>')
        parts.append(f'<text x="{x + 18}" y="{ly}">{lab}</text>')
    parts.append("</g></svg>")
    return "\n".join(parts)


def build_hmi_symbols(equipment: list[dict], machine: str) -> dict:
    """
    Normalized 0–100 layout + tag paths for Perspective Coordinate Container.

    This is the preferred interactive path:
      - One symbol view (ConveyorBelt / Photoeye)
      - Repeat for each row; bind color to tag
    """
    plc = _safe_tag(machine) or "PLC"
    plot = [
        e for e in equipment
        if not (e["x"] == 0 and e["y"] in (0, 60000))
        and (
            e.get("is_physical_conveyor")
            or e.get("kind") in (
                "photoeye", "vfd", "motor", "conveyor",
                "beacon", "power_supply",
            )
        )
    ]
    if not plot:
        return {"symbols": [], "bounds": {}, "note": "No plottable equipment"}

    # Bounds from densest conveyor cluster (same logic as SVG — ignore floaters)
    convs = [e for e in plot if e.get("is_physical_conveyor") or e.get("kind") == "conveyor"]
    base = convs or plot
    pts_xy: list[tuple[float, float]] = []
    for e in base:
        pts_xy.append((float(e["x"]), float(e["y"])))
        if e.get("is_physical_conveyor") or e.get("kind") == "conveyor":
            ang = math.radians(e.get("angle") or 0)
            L = float(e.get("length") or 0)
            if L > 0:
                pts_xy.append((e["x"] + L * math.cos(ang), e["y"] + L * math.sin(ang)))
    if pts_xy:
        # Reuse densest-cell idea (inline compact form)
        xs_all = [p[0] for p in pts_xy]
        ys_all = [p[1] for p in pts_xy]
        span0 = max(max(xs_all) - min(xs_all), max(ys_all) - min(ys_all), 1.0)
        cell = max(span0 * 0.06, 800.0)
        grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
        for x, y in pts_xy:
            key = (int(math.floor(x / cell)), int(math.floor(y / cell)))
            grid.setdefault(key, []).append((x, y))
        seed = max(grid.items(), key=lambda kv: len(kv[1]))[0]
        cluster_keys: set[tuple[int, int]] = set()
        stack = [seed]
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in cluster_keys or (cx, cy) not in grid:
                continue
            cluster_keys.add((cx, cy))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        stack.append((cx + dx, cy + dy))
        cluster_pts = [p for k in cluster_keys for p in grid[k]]
        if len(cluster_pts) >= max(4, int(len(pts_xy) * 0.45)):
            xs_all = [p[0] for p in cluster_pts]
            ys_all = [p[1] for p in cluster_pts]
        min_x, max_x = min(xs_all), max(xs_all)
        min_y, max_y = min(ys_all), max(ys_all)
        pad_u = max(max_x - min_x, max_y - min_y, 1000.0) * 0.04
        min_x -= pad_u
        max_x += pad_u
        min_y -= pad_u
        max_y += pad_u
    else:
        min_x = max_x = min_y = max_y = 0.0
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)

    def nx(x: float) -> float:
        return round(100.0 * (x - min_x) / span_x, 3)

    def ny(y: float) -> float:
        # flip Y for screen coords (0 top)
        return round(100.0 * (max_y - y) / span_y, 3)

    symbols = []
    for e in plot:
        name = e.get("name") or ""
        safe = _safe_tag(name)
        kind = e.get("kind") or "device"
        area = _area_for_name(name)
        is_conv = e.get("is_physical_conveyor") or (
            kind == "conveyor" and re.match(r"^P\d", name, re.I)
        )
        page = e.get("drawing_page") or e.get("print_page")
        if is_conv:
            symbols.append({
                "id": _svg_elem_id("conv", name),
                "name": name,
                "kind": "conveyor",
                "symbol": "ConveyorBelt",
                "x_pct": nx(e["x"]),
                "y_pct": ny(e["y"]),
                "length_pct": round(100.0 * max(e.get("length") or 400, 200) / span_x, 3),
                "angle": e.get("angle") or 0,
                "width_pct": round(max(0.15, 100.0 * (e.get("width") or 200) / span_x * 0.4), 3),
                "drawing_page": page,
                "print_page": page,
                "tags": {
                    "run": f"[default]Site/{area}/Conveyors/{safe}/Run",
                    "fault": f"[default]Site/{area}/Conveyors/{safe}/Fault",
                    "jam": f"[default]Site/{area}/Conveyors/{safe}/Jam",
                },
                "opc": {
                    "run": f"ns=1;s=[{plc}]{safe}_Conv.Run",
                    "fault": f"ns=1;s=[{plc}]{safe}_Conv.Flt",
                },
                "colors": {
                    "idle": "#22d3ee",
                    "run": "#22c55e",
                    "fault": "#ef4444",
                    "jam": "#f59e0b",
                },
            })
        elif kind == "photoeye":
            symbols.append({
                "id": _svg_elem_id("pe", name),
                "name": name,
                "kind": "photoeye",
                "symbol": "Photoeye",
                "x_pct": nx(e["x"]),
                "y_pct": ny(e["y"]),
                "drawing_page": page,
                "print_page": page,
                "tags": {
                    "clear": f"[default]Site/{area}/Photoeyes/{safe}/Clear",
                    "jam": f"[default]Site/{area}/Photoeyes/{safe}/Jam",
                },
                "opc": {
                    "clear": f"ns=1;s=[{plc}]{safe}.I.PE_Clear",
                },
                "colors": {
                    "clear": "#34d399",
                    "blocked": "#ef4444",  # Clear == false → product present
                    "fault": "#f59e0b",
                },
                "note": "When Clear tag is False, show blocked color (red)",
            })
        elif kind == "beacon":
            symbols.append({
                "id": _svg_elem_id("bcn", name),
                "name": name,
                "kind": "beacon",
                "symbol": "Beacon",
                "x_pct": nx(e["x"]),
                "y_pct": ny(e["y"]),
                "drawing_page": page,
                "print_page": page,
                "tags": {
                    "status": f"[default]Site/{area}/Other/{safe}",
                },
                "colors": {"idle": "#fbbf24", "active": "#f59e0b"},
            })
        elif kind == "power_supply":
            symbols.append({
                "id": _svg_elem_id("ps", name),
                "name": name,
                "kind": "power_supply",
                "symbol": "PowerSupply",
                "x_pct": nx(e["x"]),
                "y_pct": ny(e["y"]),
                "drawing_page": page,
                "print_page": page,
                "tags": {
                    "status": f"[default]Site/{area}/Other/{safe}",
                },
                "colors": {"ok": "#f472b6", "fault": "#9f1239"},
            })
    return {
        "machine": machine,
        "coordinate_system": "percent_0_100_top_left",
        "bounds_plant": {
            "min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y,
        },
        "symbol_count": len(symbols),
        "conveyor_count": sum(1 for s in symbols if s["kind"] == "conveyor"),
        "photoeye_count": sum(1 for s in symbols if s["kind"] == "photoeye"),
        "beacon_count": sum(1 for s in symbols if s["kind"] == "beacon"),
        "power_supply_count": sum(1 for s in symbols if s["kind"] == "power_supply"),
        "symbols": symbols,
        "perspective_note": (
            "Interactive HMI path: Perspective Coordinate Container + embedded symbol views. "
            "Bind ConveyorBelt fill/stroke to tags.run (green when true). "
            "Bind Photoeye fill to tags.clear (green when true, red when false). "
            "A static SVG Image component cannot change color from tags by itself."
        ),
    }


def _xml(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_package(run_dir: Path, out_dir: Path | None = None, *, layout_mode: str = "equipment") -> dict:
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"
    meta = read_project_meta(run_dir)
    machine = meta.get("machine_name") or "Machine"
    project = meta.get("project_name") or machine

    equipment = load_layout_equipment(run_dir)
    physical = [e for e in equipment if e.get("is_physical_conveyor")]
    plot = [
        e for e in equipment
        if e["kind"] in KIND_COLORS and not (e["x"] == 0 and e["y"] in (0, 60000))
    ]
    eip = load_eip_modules(run_dir)
    # Merge Flex topology (same source as PLC L5X modules) so EIP_Adapters
    # includes CP4RIO1/CP4RIO2 at .57/.58 — eipcfg alone often stops at .56.
    try:
        from fortna_autogen import load_eip_topology
        topo = load_eip_topology(run_dir) or {}
        eip = dict(eip or {})
        eip["topology"] = list(topo.get("topology") or [])
        eip["word_map"] = dict(topo.get("word_map") or {})
        if topo.get("interface_ip") and not eip.get("interface_ip"):
            eip["interface_ip"] = topo.get("interface_ip")
    except Exception:
        pass
    tags = build_tag_seed(equipment, machine)
    tags_plc = build_plc_aligned_tags(equipment, machine, eip)
    devices = build_devices(equipment)
    opc = build_opc_devices(machine, eip)
    title = f"{project} / {machine}"
    # Default: conveyors as centerlines + PE/VFD symbols (2D Ignition style)
    svg = render_svg(equipment, title=title, mode=layout_mode, machine=machine)
    svg_conv_only = render_svg(
        equipment, title=f"{title} (conveyors)", mode="conveyor", machine=machine
    )
    hmi_symbols = build_hmi_symbols(equipment, machine)

    # Local wall-clock stamp (used in reports); folder prefers tar.gz basename
    now_local = datetime.now().astimezone()
    stamp = now_local.strftime("%Y%m%d-%H%M%S")
    stamp_human = now_local.strftime("%Y-%m-%d %H:%M:%S %Z").strip() or now_local.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    machine_safe = _safe_tag(machine) or "Machine"
    try:
        from fortna_source_id import export_label_from_meta, studio_safe_name
        export_label = export_label_from_meta()
    except Exception:
        export_label = ""
        studio_safe_name = lambda s, **kw: re.sub(r"[^A-Za-z0-9_]", "_", s or "Site")  # noqa: E731
    # Always unique folder per run so exports don't overwrite (track history).
    # stamp first, then site label — e.g. 20260813-143022-20260803_0815_…_ORDENCP4_RUN
    label = studio_safe_name(export_label or machine_safe)
    folder_name = f"{stamp}-{label}"
    out = out_dir or (REPO_ROOT / "exports" / "ignition-build" / folder_name)
    out.mkdir(parents=True, exist_ok=True)

    drawings_dir = REPO_ROOT / "workspace" / "drawings"
    layout = {
        "ok": True,
        "machine": machine,
        "project": project,
        "run_dir": str(run_dir),
        "generated": datetime.now(timezone.utc).isoformat(),
        "equipment_count": len(equipment),
        "physical_conveyor_count": len(physical),
        "plotted_count": len(plot),
        "equipment": equipment,
        "bounds": _bounds(physical or plot or equipment),
        "eip": eip,
        "sources": {
            "geometry": "FORTNA/Conveyor.asc X/Y/Width/Length/Angle — physical STRAIGHT/CURVE/… segments",
            "eip_modules": eip.get("sources") or [],
            "drawings_dir": str(drawings_dir),
            "drawings_note": (
                "Put facility zips in workspace/drawings/inbox/. "
                "DWG (SYS_DL_ForHMI) + mechanical PDFs improve centerlines beyond RUN stubs."
            ),
            "plc_tags": "Aligned with fortna_autogen L5X (Pxxx_Conv, PE.I.PE_Clear, ZoneN_Area)",
        },
    }
    (out / "layout.json").write_text(json.dumps(layout, separators=(",", ":")), encoding="utf-8")
    (out / "layout.svg").write_text(svg, encoding="utf-8")
    (out / "layout_conveyors_only.svg").write_text(svg_conv_only, encoding="utf-8")
    # tags_seed.json removed — use tags_import.json only for Designer
    (out / "tags_plc_aligned.json").write_text(json.dumps(tags_plc, indent=2), encoding="utf-8")
    (out / "devices.json").write_text(json.dumps(devices, separators=(",", ":")), encoding="utf-8")
    (out / "hmi_symbols.json").write_text(json.dumps(hmi_symbols, indent=2), encoding="utf-8")
    (out / "eip_modules.json").write_text(json.dumps(eip, indent=2), encoding="utf-8")
    (out / "opc_devices.json").write_text(json.dumps(opc, indent=2), encoding="utf-8")
    csv_n = write_tags_csv(out / "tags_flat.csv", equipment, machine)
    write_designer_readme(
        out / "DESIGNER_IMPORT.md",
        machine=machine,
        plc_ip=eip.get("interface_ip") or "",
        out_dir=out,
    )
    write_interactive_readme(out / "INTERACTIVE_LAYOUT.md", machine=machine)

    # Browser click-to-test screen — rebuilt every export from THIS layout
    # (layout-agnostic: works for any site as long as RUN geometry exists)
    try:
        write_poc_preview_html(
            out / "interactive_test.html",
            svg=svg,
            symbols=hmi_symbols,
            machine=machine,
        )
        # Keep legacy name too
        write_poc_preview_html(
            out / "poc_preview.html",
            svg=svg,
            symbols=hmi_symbols,
            machine=machine,
        )
    except Exception as exc:
        (out / "interactive_test_error.txt").write_text(str(exc), encoding="utf-8")

    # --- Importable Ignition project folder (copy → data/projects → Scan Filesystem) ---
    perspective_project = ""
    perspective_zip = ""
    tags_import_path = ""
    try:
        from fortna_perspective_pack import pack_perspective_project

        n_conv = int(hmi_symbols.get("conveyor_count") or 0) or 80
        n_pe = int(hmi_symbols.get("photoeye_count") or 0) or 60
        # Cap for Designer comfort; layout still uses full symbols file for pick
        n_conv = min(max(n_conv, 10), 200)
        n_pe = min(max(n_pe, 10), 150)
        # Project name follows tar.gz stem when available (raw-test rule)
        proj_base = export_label or f"{machine_safe}_{stamp}"
        proj_name = f"Site Forge_{_safe_tag(proj_base)}"[:80]
        pack = pack_perspective_project(
            out,
            project_name=proj_name,
            symbols=hmi_symbols,
            max_conv=n_conv,
            max_pe=n_pe,
            # Larger canvas so small sites (e.g. CP4 ≈ 1/3 plant) still fill the view
            canvas_w=1920,
            canvas_h=1200,
            symbols_source=str(out / "hmi_symbols.json"),
            svg_path=out / "layout_conveyors_only.svg",
            cluster=False,  # use full scoped symbol set from this build
            with_tags=True,
            # Do not embed multi-MB SVG in view.json — breaks Designer ("no-project" canvas).
            # layout.svg is still exported beside the project for manual Image/Media use.
            embed_svg=False,
        )
        perspective_project = pack.get("project_dir") or ""
        perspective_zip = pack.get("zip") or ""
        # PRIMARY tags file = full PLC-aligned tree as Memory tags (all Zone1–N).
        # Designer does NOT auto-load tags from the project folder — you must Import Tags.
        tags_memory = to_memory_tags_import(tags_plc)
        tags_import_path = str(out / "tags_import.json")
        (out / "tags_import.json").write_text(
            json.dumps(tags_memory, indent=2), encoding="utf-8"
        )
        # One-line purpose file sitting next to the JSON (Explorer-friendly)
        (out / "tags_import.PURPOSE.txt").write_text(
            "PURPOSE: Import this into Designer Tag Browser (default provider → Import Tags).\n"
            "Memory tags for all Site/Zone1…ZoneN conveyors + photoeyes. Required for HMI colors.\n"
            "Ignition does NOT load this automatically when you copy the project folder.\n",
            encoding="utf-8",
        )
        # Also inside project folder so it travels with the copy
        if perspective_project:
            try:
                Path(perspective_project).joinpath("tags_import.json").write_text(
                    json.dumps(tags_memory, indent=2), encoding="utf-8"
                )
                Path(perspective_project).joinpath("tags_import.PURPOSE.txt").write_text(
                    "Import this JSON via Tag Browser → Import Tags (Memory tags, all zones).\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
        # Optional: PLC-aligned (OPC paths) for later gateway device binding — NOT for first import
        (out / "tags_plc_aligned.json").write_text(
            json.dumps(tags_plc, indent=2), encoding="utf-8"
        )
        (out / "tags_plc_aligned.PURPOSE.txt").write_text(
            "PURPOSE: Optional later — same folder tree with OPC item paths for a live PLC device.\n"
            "Do NOT import this first. Use tags_import.json for Designer Memory tags.\n",
            encoding="utf-8",
        )
        # tags_seed.json and tags_import_plc.json are no longer written (redundant).
        (out / "TAGS_README.txt").write_text(
            "\n".join([
                "Site Forge tag files",
                "=" * 44,
                "",
                "tags_import.json          ← IMPORT THIS (Designer → Tag Browser → Import Tags)",
                "tags_import.PURPOSE.txt   ← short purpose note next to the file",
                "",
                "tags_plc_aligned.json     ← optional later (OPC paths for live PLC)",
                "tags_plc_aligned.PURPOSE.txt",
                "",
                "REMOVED (not needed):",
                "  tags_seed.json       — old kind-folder layout (photoeye/, conveyor/)",
                "  tags_import_plc.json — was a duplicate of tags_import / plc_aligned",
                "",
                "After import you should see Site/Zone1 … ZoneN (all zones).",
                "",
            ]),
            encoding="utf-8",
        )
        # Short copy instructions at build root
        (out / "COPY_TO_IGNITION.txt").write_text(
            "\n".join([
                "Site Forge Ignition project (from Build layout)",
                "=" * 48,
                f"Machine: {machine}",
                f"Folder stamp: {stamp}",
                f"Generated (local): {stamp_human}",
                f"Export folder: {out}",
                f"Project folder: {proj_name}",
                "",
                "STEP A — Project views",
                "1) Copy project folder into Ignition data\\projects\\:",
                f"   {perspective_project}",
                r"   → C:\Program Files\Inductive Automation\Ignition\data\projects\\",
                "2) Gateway → Projects → Scan Filesystem",
                "3) Designer → open the project → Views → Site Forge/POC/Plant_Layout",
                "",
                "STEP B — Tags (REQUIRED — not automatic)",
                "Ignition stores tags in the Gateway tag provider, not inside the project",
                "folder. Copying a new project does NOT replace old tags.",
                "",
                "Clear old tags (recommended before each new site):",
                "  Tag Browser → expand Site → right-click Site → Delete",
                "  (or delete old Site Forge_* projects under data\\projects\\)",
                "",
                "Import new tags:",
                "1) Designer Tag Browser → select provider 'default'",
                "2) Right-click → Import Tags",
                f"3) Select: {out / 'tags_import.json'}",
                "4) Confirm you see Site/Zone1 … ZoneN (all zones)",
                "",
                "See TAGS_README.txt + tags_import.PURPOSE.txt next to the JSON.",
                "",
                f"Zip (optional): {perspective_zip}",
                f"SVG underlay: {out / 'layout_conveyors_only.svg'}",
                f"Counts: {n_conv} conveyors / {n_pe} photoeyes (scoped to this master)",
                "",
            ]),
            encoding="utf-8",
        )
    except Exception as pack_exc:
        (out / "perspective_pack_error.txt").write_text(str(pack_exc), encoding="utf-8")

    slim_equipment = [
        {k: e[k] for k in (
            "id", "name", "kind", "type", "is_physical_conveyor", "x", "y", "width", "length", "angle",
            "color", "io_address", "ignition_tag", "description",
        ) if k in e}
        for e in physical[:500]
    ]
    plc_ip = eip.get("interface_ip") or ""
    # Pointer file so dashboard / scripts always find the newest build
    try:
        latest = {
            "folder_stamp": stamp,
            "generated_local": stamp_human,
            "out_dir": str(out),
            "project_name": (
                Path(perspective_project).name if perspective_project else f"Site Forge_{machine_safe}_{stamp}"
            ),
            "perspective_project": perspective_project,
            "machine": machine,
        }
        latest_path = REPO_ROOT / "exports" / "ignition-build" / "LATEST.json"
        latest_path.write_text(json.dumps(latest, indent=2), encoding="utf-8")
        (REPO_ROOT / "exports" / "ignition-build" / "LATEST.txt").write_text(
            "\n".join([
                f"stamp={stamp}",
                f"local_time={stamp_human}",
                f"out_dir={out}",
                f"project={latest['project_name']}",
                f"perspective_project={perspective_project}",
                "",
            ]),
            encoding="utf-8",
        )
        (out / "BUILD_STAMP.txt").write_text(
            "\n".join([
                f"folder_stamp={stamp}",
                f"generated_local={stamp_human}",
                f"machine={machine}",
                f"project_name={latest['project_name']}",
                "",
            ]),
            encoding="utf-8",
        )
    except Exception:
        pass

    # Stage ignition export into PRISM (site = tar.gz stem)
    prism_info: dict = {}
    try:
        from fortna_prism_ingest import after_export
        prism_info = after_export(
            export_dir=out,
            kind="ignition",
            site=folder_name,
        )
    except Exception as exc:
        prism_info = {"ok": False, "error": str(exc)}

    manifest = {
        "ok": True,
        "out_dir": str(out),
        "export_name": folder_name,
        "source_label": folder_name,
        "folder_stamp": stamp,
        "generated_local": stamp_human,
        "machine": machine,
        "project": project,
        "project_name": (
            Path(perspective_project).name
            if perspective_project
            else f"Site Forge_{_safe_tag(folder_name)}"[:80]
        ),
        "prism": prism_info,
        "equipment_count": len(equipment),
        "physical_conveyor_count": len(physical),
        "plotted_count": len(plot),
        "kind_counts": _kind_counts(equipment),
        "tag_csv_rows": csv_n,
        "plc_ip": plc_ip,
        "eip_summary": {
            "interface_ip": plc_ip,
            "adapter_count": eip.get("adapter_count"),
            "module_count": eip.get("module_count"),
            "module_type_counts": eip.get("module_type_counts"),
            "adapters": [
                {"name": a["name"], "ip": a["ip"], "module_count": a["module_count"]}
                for a in (eip.get("adapters") or [])
            ],
        },
        "files": {
            "layout_json": str(out / "layout.json"),
            "layout_svg": str(out / "layout.svg"),
            "layout_conveyors_only_svg": str(out / "layout_conveyors_only.svg"),
            "tags_plc_aligned": str(out / "tags_plc_aligned.json"),
            "tags_flat_csv": str(out / "tags_flat.csv"),
            "devices": str(out / "devices.json"),
            "hmi_symbols": str(out / "hmi_symbols.json"),
            "opc_devices": str(out / "opc_devices.json"),
            "eip_modules": str(out / "eip_modules.json"),
            "designer_readme": str(out / "DESIGNER_IMPORT.md"),
            "interactive_readme": str(out / "INTERACTIVE_LAYOUT.md"),
            "interactive_test_html": str(out / "interactive_test.html"),
            "poc_preview_html": str(out / "poc_preview.html"),
            "perspective_project": perspective_project,
            "perspective_zip": perspective_zip,
            "tags_import": tags_import_path,
            "copy_to_ignition": str(out / "COPY_TO_IGNITION.txt"),
        },
        "perspective_project": perspective_project,
        "project_name": Path(perspective_project).name if perspective_project else "",
        "drawings_dir": str(drawings_dir),
        "hmi_symbol_count": hmi_symbols.get("symbol_count", 0),
        "gwbk_status": (
            f"Layout SVG is larger + has element ids/data-tags. "
            f"Still a static image until bound — see INTERACTIVE_LAYOUT.md. "
            f"hmi_symbols.json ({hmi_symbols.get('symbol_count', 0)} symbols) is the live HMI path. "
            f"PLC IP {plc_ip or 'TBD'}."
        ),
        "equipment_sample": slim_equipment[:80],
        "svg": svg,
        "bounds": layout["bounds"],
    }
    (out / "ignition_manifest.json").write_text(
        json.dumps({k: v for k, v in manifest.items() if k != "svg"}, indent=2),
        encoding="utf-8",
    )
    return manifest


def _bounds(equipment: list[dict]) -> dict:
    if not equipment:
        return {"min_x": 0, "max_x": 0, "min_y": 0, "max_y": 0}
    xs = [e["x"] for e in equipment]
    ys = [e["y"] for e in equipment]
    return {
        "min_x": min(xs), "max_x": max(xs),
        "min_y": min(ys), "max_y": max(ys),
    }


def _kind_counts(equipment: list[dict]) -> dict:
    c: dict[str, int] = {}
    for e in equipment:
        k = e.get("kind") or "device"
        c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items(), key=lambda kv: -kv[1]))


def select_poc_equipment(
    equipment: list[dict],
    *,
    n_conv: int = 10,
    n_pe: int = 10,
) -> list[dict]:
    """
    Pick a small, layout-friendly set for interactive POC.

    Prefers longer P### conveyors near the plant centroid, then photoeyes
    closest to those conveyors (or any PE with valid coords).
    """
    convs = [
        e for e in equipment
        if e.get("is_physical_conveyor")
        or (
            e.get("kind") == "conveyor"
            and re.match(r"^P\d", (e.get("name") or ""), re.I)
            and (e.get("type") or "").upper() in PHYSICAL_CONV_TYPES
        )
    ]
    convs = [e for e in convs if not (e["x"] == 0 and e["y"] in (0, 60000))]
    pes = [
        e for e in equipment
        if e.get("kind") == "photoeye" and not (e["x"] == 0 and e["y"] in (0, 60000))
    ]
    if not convs:
        return []

    # Prefer longer belts (more visible), then name order for stability
    convs_sorted = sorted(
        convs,
        key=lambda e: (-(e.get("length") or 0), e.get("name") or ""),
    )
    picked_conv = convs_sorted[: max(1, n_conv)]

    # PE near any picked conveyor
    def min_dist2(pe: dict) -> float:
        best = 1e30
        for c in picked_conv:
            dx = (pe["x"] - c["x"])
            dy = (pe["y"] - c["y"])
            best = min(best, dx * dx + dy * dy)
        return best

    pes_sorted = sorted(pes, key=min_dist2)
    picked_pe = pes_sorted[: max(0, n_pe)]
    return picked_conv + picked_pe


def write_poc_preview_html(
    path: Path,
    *,
    svg: str,
    symbols: dict,
    machine: str,
) -> None:
    """Browser POC: click toggles simulate Run / PE blocked without Ignition."""
    convs = [s for s in (symbols.get("symbols") or []) if s.get("kind") == "conveyor"]
    pes = [s for s in (symbols.get("symbols") or []) if s.get("kind") == "photoeye"]
    # Escape </script> in SVG
    svg_safe = svg.replace("</script>", "<\\/script>")
    conv_json = json.dumps(convs)
    pe_json = json.dumps(pes)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Site Forge interactive test — { _xml(machine) }</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; }}
    body {{
      margin: 0; font-family: Segoe UI, system-ui, sans-serif;
      background: #0a0f14; color: #e2e8f0; display: flex; height: 100vh;
      overflow: hidden;
    }}
    #panel {{
      width: 300px; flex-shrink: 0; border-right: 1px solid #1e293b;
      padding: 14px; overflow-y: auto; background: #0f172a;
    }}
    #panel h1 {{ font-size: 15px; margin: 0 0 8px; color: #fb923c; }}
    #panel p {{ font-size: 12px; color: #94a3b8; line-height: 1.45; margin: 0 0 12px; }}
    .btn-row {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }}
    button {{
      background: #1e293b; border: 1px solid #334155; color: #e2e8f0;
      border-radius: 8px; padding: 6px 10px; font-size: 11px; cursor: pointer;
    }}
    button:hover {{ border-color: #fb923c; color: #fb923c; }}
    button.primary {{ background: #c2410c; border-color: #ea580c; }}
    .group {{ margin-bottom: 16px; }}
    .group h2 {{
      font-size: 10px; text-transform: uppercase; letter-spacing: .06em;
      color: #64748b; margin: 0 0 8px;
    }}
    .item {{
      display: flex; align-items: center; justify-content: space-between;
      gap: 8px; padding: 6px 8px; margin-bottom: 4px;
      background: #101820; border: 1px solid #1e293b; border-radius: 8px;
      font-size: 12px; font-family: ui-monospace, Consolas, monospace;
    }}
    .item.on-run {{ border-color: #22c55e; }}
    .item.on-block {{ border-color: #ef4444; }}
    .item button {{ padding: 3px 8px; font-size: 10px; }}
    #stage {{
      flex: 1 1 auto; min-width: 0; min-height: 0;
      overflow: hidden; padding: 16px 20px;
      display: flex; align-items: center; justify-content: center;
      background: radial-gradient(ellipse at center, #0f172a 0%, #0a0f14 70%);
    }}
    #stage svg {{
      width: min(100%, 1600px);
      height: min(100%, 92vh);
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      background: #0a0f14;
      border-radius: 12px;
      box-shadow: 0 0 0 1px #1e293b, 0 12px 40px rgba(0,0,0,.45);
    }}
    #stage .conv {{ cursor: pointer; transition: stroke .15s; }}
    #stage .pe {{ cursor: pointer; }}
    #stage .pe .pe-core {{ transition: fill .15s; }}
    #stage .pe .pe-ring {{ transition: stroke .15s; }}
    #stage .conv:hover {{ filter: brightness(1.25); }}
    #stage .pe:hover {{ filter: brightness(1.25); }}
    .legend {{ font-size: 11px; color: #64748b; margin-top: 12px; line-height: 1.5; }}
    .tag {{ font-size: 10px; color: #475569; word-break: break-all; }}
  </style>
</head>
<body>
  <aside id="panel">
    <h1>Interactive test</h1>
    <p>
      <strong>{ _xml(machine) }</strong> — {len(convs)} conveyors + {len(pes)} photoeyes.<br/>
      Auto-built from this site&rsquo;s RUN layout (changes every rebuild).<br/>
      Click a belt or PE on the map, or use the toggles — no PLC / no Designer required.
    </p>
    <div class="btn-row">
      <button class="primary" type="button" id="btn-all-run">All belts RUN</button>
      <button type="button" id="btn-all-idle">All belts idle</button>
      <button type="button" id="btn-all-block">All PE blocked</button>
      <button type="button" id="btn-all-clear">All PE clear</button>
    </div>
    <div class="group">
      <h2>Conveyors (Run)</h2>
      <div id="conv-list"></div>
    </div>
    <div class="group">
      <h2>Photoeyes (Clear = green / Blocked = red)</h2>
      <div id="pe-list"></div>
    </div>
    <div class="legend">
      Cyan belt = idle · Green belt = running<br/>
      Green PE = clear · Red PE = blocked<br/>
      See POC_README.md for Ignition Designer steps.
    </div>
  </aside>
  <main id="stage">{svg_safe}</main>
  <script>
    const CONVS = {conv_json};
    const PES = {pe_json};
    const state = {{ conv: {{}}, pe: {{}} }};

    function setConv(id, run) {{
      state.conv[id] = !!run;
      const el = document.getElementById(id);
      if (el) {{
        el.classList.toggle('run', !!run);
        el.classList.toggle('idle', !run);
        el.setAttribute('stroke', run ? '#22c55e' : (el.dataset.idleStroke || '#22d3ee'));
      }}
      const row = document.querySelector('[data-row="'+id+'"]');
      if (row) {{
        row.classList.toggle('on-run', !!run);
        const b = row.querySelector('button');
        if (b) b.textContent = run ? 'RUN' : 'idle';
      }}
    }}
    function setPe(id, clear) {{
      // clear=true → green; clear=false (blocked) → red
      // PE is a <g> with .pe-core (fill) + .pe-ring (stroke)
      state.pe[id] = !!clear;
      const el = document.getElementById(id);
      if (el) {{
        el.classList.toggle('clear', !!clear);
        el.classList.toggle('blocked', !clear);
        const core = el.querySelector('.pe-core') || el;
        const ring = el.querySelector('.pe-ring');
        core.setAttribute('fill', clear ? '#34d399' : '#ef4444');
        if (ring) ring.setAttribute('stroke', clear ? '#6ee7b7' : '#fca5a5');
      }}
      const row = document.querySelector('[data-row="'+id+'"]');
      if (row) {{
        row.classList.toggle('on-block', !clear);
        const b = row.querySelector('button');
        if (b) b.textContent = clear ? 'clear' : 'BLOCKED';
      }}
    }}

    function buildLists() {{
      const cl = document.getElementById('conv-list');
      const pl = document.getElementById('pe-list');
      cl.innerHTML = '';
      pl.innerHTML = '';
      CONVS.forEach(s => {{
        state.conv[s.id] = false;
        const el = document.getElementById(s.id);
        if (el) el.dataset.idleStroke = el.getAttribute('stroke') || '#22d3ee';
        const div = document.createElement('div');
        div.className = 'item';
        div.dataset.row = s.id;
        div.innerHTML = '<div><div>'+s.name+'</div><div class="tag">'+(s.tags&&s.tags.run||'')+'</div></div>';
        const btn = document.createElement('button');
        btn.textContent = 'idle';
        btn.onclick = () => setConv(s.id, !state.conv[s.id]);
        div.appendChild(btn);
        cl.appendChild(div);
        if (el) el.addEventListener('click', () => setConv(s.id, !state.conv[s.id]));
      }});
      PES.forEach(s => {{
        state.pe[s.id] = true; // start clear
        const div = document.createElement('div');
        div.className = 'item';
        div.dataset.row = s.id;
        div.innerHTML = '<div><div>'+s.name+'</div><div class="tag">'+(s.tags&&s.tags.clear||'')+'</div></div>';
        const btn = document.createElement('button');
        btn.textContent = 'clear';
        btn.onclick = () => setPe(s.id, !state.pe[s.id]);
        div.appendChild(btn);
        pl.appendChild(div);
        const el = document.getElementById(s.id);
        if (el) el.addEventListener('click', () => setPe(s.id, !state.pe[s.id]));
        setPe(s.id, true);
      }});
    }}

    document.getElementById('btn-all-run').onclick = () => CONVS.forEach(s => setConv(s.id, true));
    document.getElementById('btn-all-idle').onclick = () => CONVS.forEach(s => setConv(s.id, false));
    document.getElementById('btn-all-block').onclick = () => PES.forEach(s => setPe(s.id, false));
    document.getElementById('btn-all-clear').onclick = () => PES.forEach(s => setPe(s.id, true));
    buildLists();
  </script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def write_poc_ignition_script(path: Path, symbols: dict, machine: str) -> None:
    """Perspective message/script sketch to paint SVG ids from tag values."""
    lines = [
        f"# Site Forge Ignition POC — {machine}",
        "# Paste into a Perspective view script (or gateway timer) after embedding layout_poc.svg",
        "# in a component that preserves element ids (Drawing / Markdown HTML — not plain Image).",
        "#",
        "# Pseudo-API — adapt to your Ignition version:",
        "#   el = system.perspective.getSvgElement(...) or component.getElementById(id)",
        "#",
        "def apply_poc_colors(svg_component):",
        "    # Conveyors: True Run -> green stroke",
    ]
    for s in symbols.get("symbols") or []:
        if s.get("kind") == "conveyor":
            tag = s.get("tags", {}).get("run", "")
            eid = s.get("id", "")
            lines.append(f"    # {s.get('name')}")
            lines.append(f"    run = system.tag.readBlocking(['{tag}'])[0].value")
            lines.append(f"    # set stroke of '{eid}' to '#22c55e' if run else '#22d3ee'")
        elif s.get("kind") == "photoeye":
            tag = s.get("tags", {}).get("clear", "")
            eid = s.get("id", "")
            lines.append(f"    # {s.get('name')}")
            lines.append(f"    clear = system.tag.readBlocking(['{tag}'])[0].value")
            lines.append(f"    # set fill of '{eid}' to '#34d399' if clear else '#ef4444'")
    lines.append("")
    lines.append("# Memory-tag test (no PLC): create tags from tags_poc_memory.json as Memory tags,")
    lines.append("# toggle values in Tag Browser, re-run apply_poc_colors.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_poc_readme(path: Path, *, machine: str, n_conv: int, n_pe: int) -> None:
    path.write_text(
        f"""# Interactive layout POC — {machine}

**{n_conv} conveyors + {n_pe} photoeyes** for proving live color before scaling to the full site.

## Files

| File | Purpose |
|------|---------|
| `poc_preview.html` | **Open in Chrome/Edge** — click belts/PEs, no Ignition needed |
| `layout_poc.svg` | Small SVG with `id` + `data-tag` on every object |
| `hmi_symbols_poc.json` | Positions + tag paths for Coordinate Container later |
| `tags_poc_memory.json` | Memory tags for Designer testing without PLC |
| `ignition_poc_script.py` | Sketch of tag→SVG color script |
| `POC_README.md` | This file |

## 1) Browser proof (do this first)

1. Double-click `poc_preview.html` (or Open with browser).
2. Click a cyan belt → turns **green** (Run).
3. Click a green PE → turns **red** (blocked).
4. Use panel buttons: All RUN / idle / blocked / clear.

This proves the **IDs + color model** work. Same IDs go into Ignition.

## 2) Ignition Designer (live or memory tags)

1. Create project / open existing.
2. Create folder tags under `[default]Site/...` from `tags_poc_memory.json` (Memory) **or** bind OPC to PLC after autogen L5X is online.
3. Drop `layout_poc.svg` into a Perspective component that keeps DOM ids (Drawing if available; avoid plain Image for scripting).
4. Use `ignition_poc_script.py` as a guide: read each tag, set stroke/fill on matching `id`.
5. Toggle Memory tags in Tag Browser → colors should change.

### Color rules

| Object | Tag | True | False |
|--------|-----|------|-------|
| Conveyor | `…/Conveyors/Pxxx/Run` | green `#22c55e` | cyan idle `#22d3ee` |
| Photoeye | `…/Photoeyes/…/Clear` | green clear `#34d399` | red blocked `#ef4444` |

## 3) Next after POC works

- Scale to full site via full `hmi_symbols.json` (or Coordinate Container symbols).
- Prefer symbol views over pure SVG once click actions / popups are needed.

## Greenfield note

This POC only needs **RUN** geometry + naming. No gold L5X programs required.
When the next site has only tar.gz + prints, the same POC path still works.
""",
        encoding="utf-8",
    )


def build_poc_package(
    run_dir: Path,
    out_dir: Path | None = None,
    *,
    n_conv: int = 10,
    n_pe: int = 10,
) -> dict:
    """Interactive proof-of-concept: N conveyors + N photoeyes + browser preview."""
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"
    meta = read_project_meta(run_dir)
    machine = meta.get("machine_name") or "Machine"
    project = meta.get("project_name") or machine

    all_eq = load_layout_equipment(run_dir)
    poc_eq = select_poc_equipment(all_eq, n_conv=n_conv, n_pe=n_pe)
    if not poc_eq:
        return {"ok": False, "error": "No conveyors with layout coords for POC"}

    title = f"{project} / {machine} POC ({n_conv}c+{n_pe}pe)"
    svg = render_svg(poc_eq, title=title, mode="equipment", machine=machine)
    # Remove the "static until bound" footer noise for POC title clarity
    symbols = build_hmi_symbols(poc_eq, machine)
    # Only keep conv+pe in symbols list (build_hmi already does)
    tags_mem = build_plc_aligned_tags(poc_eq, machine, eip=None)

    now_local = datetime.now().astimezone()
    stamp = now_local.strftime("%Y%m%d-%H%M%S")
    stamp_human = now_local.strftime("%Y-%m-%d %H:%M:%S %Z").strip() or now_local.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    out = out_dir or (
        REPO_ROOT
        / "exports"
        / "ignition-build"
        / f"{stamp}-{_safe_tag(machine)}-POC"
    )
    out.mkdir(parents=True, exist_ok=True)

    (out / "layout_poc.svg").write_text(svg, encoding="utf-8")
    (out / "hmi_symbols_poc.json").write_text(json.dumps(symbols, indent=2), encoding="utf-8")
    (out / "tags_poc_memory.json").write_text(json.dumps(tags_mem, indent=2), encoding="utf-8")
    write_poc_preview_html(out / "poc_preview.html", svg=svg, symbols=symbols, machine=machine)
    write_poc_ignition_script(out / "ignition_poc_script.py", symbols, machine)
    write_poc_readme(out / "POC_README.md", machine=machine, n_conv=n_conv, n_pe=n_pe)

    # Importable Perspective components (Conveyor / Photoeye + small plant view)
    perspective_pack = {}
    try:
        from fortna_perspective_pack import pack_perspective_project

        pack_dir = out / "perspective-import"
        perspective_pack = pack_perspective_project(
            pack_dir,
            project_name=f"Site Forge_POC_{stamp}",
            symbols=symbols,
            max_conv=max(n_conv, 40),
            max_pe=max(n_pe, 40),
            canvas_w=1400,
            canvas_h=900,
        )
    except Exception as exc:
        perspective_pack = {"ok": False, "error": str(exc)}
    (out / "poc_equipment.json").write_text(
        json.dumps(
            {
                "machine": machine,
                "n_conv": n_conv,
                "n_pe": n_pe,
                "equipment": [
                    {k: e.get(k) for k in (
                        "name", "kind", "type", "x", "y", "length", "width", "angle", "io_address"
                    )}
                    for e in poc_eq
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    n_c = sum(1 for e in poc_eq if e.get("is_physical_conveyor") or e.get("kind") == "conveyor")
    n_p = sum(1 for e in poc_eq if e.get("kind") == "photoeye")
    manifest = {
        "ok": True,
        "poc": True,
        "out_dir": str(out),
        "machine": machine,
        "project": project,
        "conveyor_count": n_c,
        "photoeye_count": n_p,
        "equipment_count": len(poc_eq),
        "physical_conveyor_count": n_c,
        "plotted_count": len(poc_eq),
        "kind_counts": _kind_counts(poc_eq),
        "svg": svg,
        "files": {
            "layout_poc_svg": str(out / "layout_poc.svg"),
            "poc_preview_html": str(out / "poc_preview.html"),
            "hmi_symbols_poc": str(out / "hmi_symbols_poc.json"),
            "tags_poc_memory": str(out / "tags_poc_memory.json"),
            "ignition_poc_script": str(out / "ignition_poc_script.py"),
            "poc_readme": str(out / "POC_README.md"),
            "layout_svg": str(out / "layout_poc.svg"),  # dashboard preview
            "perspective_project": perspective_pack.get("project_dir") or "",
            "perspective_zip": perspective_pack.get("zip") or "",
            "perspective_import_readme": perspective_pack.get("readme") or "",
        },
        "perspective_pack": perspective_pack,
        "gwbk_status": (
            f"POC ready: {n_c} conveyors + {n_p} PEs. "
            f"Browser: poc_preview.html. "
            f"Ignition import: perspective-import/Site Forge_POC "
            f"(see IMPORT_TO_IGNITION.md)."
        ),
        "bounds": _bounds(poc_eq),
        "eip_summary": {},
    }
    (out / "ignition_manifest.json").write_text(
        json.dumps({k: v for k, v in manifest.items() if k != "svg"}, indent=2),
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Site Forge Ignition Build — layout + tag seed")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build", help="Build layout SVG + tag/device seed from RUN")
    p.add_argument("--run-dir", default="")
    p.add_argument("--use-active", action="store_true")
    p.add_argument("--out-dir", default="")
    p.add_argument(
        "--mode",
        default="equipment",
        choices=["conveyor", "equipment", "all"],
        help="SVG mode: conveyor centerlines only, or + PE/VFD symbols",
    )
    p_poc = sub.add_parser(
        "build-poc",
        help="Interactive POC: N conveyors + N photoeyes + browser preview HTML",
    )
    p_poc.add_argument("--run-dir", default="")
    p_poc.add_argument("--use-active", action="store_true")
    p_poc.add_argument("--out-dir", default="")
    p_poc.add_argument("--n-conv", type=int, default=10)
    p_poc.add_argument("--n-pe", type=int, default=10)
    args = ap.parse_args()
    try:
        if args.cmd == "build":
            rd = Path(args.run_dir) if args.run_dir else REPO_ROOT / "workspace" / "active" / "RUN"
            if args.use_active or not args.run_dir:
                rd = REPO_ROOT / "workspace" / "active" / "RUN"
            if not (rd / "project.cfg").is_file() and (rd / "RUN" / "project.cfg").is_file():
                rd = rd / "RUN"
            out = Path(args.out_dir) if args.out_dir else None
            result = build_package(rd, out, layout_mode=args.mode)
            print(json.dumps(result, separators=(",", ":")))
            return 0 if result.get("ok") else 1
        if args.cmd == "build-poc":
            rd = Path(args.run_dir) if args.run_dir else REPO_ROOT / "workspace" / "active" / "RUN"
            if args.use_active or not args.run_dir:
                rd = REPO_ROOT / "workspace" / "active" / "RUN"
            if not (rd / "project.cfg").is_file() and (rd / "RUN" / "project.cfg").is_file():
                rd = rd / "RUN"
            out = Path(args.out_dir) if args.out_dir else None
            result = build_poc_package(
                rd, out, n_conv=int(args.n_conv), n_pe=int(args.n_pe)
            )
            print(json.dumps(result, separators=(",", ":")))
            return 0 if result.get("ok") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
