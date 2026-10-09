#!/usr/bin/env python3
"""Diagnostic probe: Transportation ACTIVE-CONTROL evidence classification.

PERMANENT LAW
  Visualization presence != ACTIVE_CONTROLLED.
  A conveyor is ACTIVE_CONTROLLED only with corroborating operational /
  control evidence beyond graphical presence.

Classes (every visual conveyor object must receive exactly one):
  ACTIVE_CONTROLLED
  ACTIVE_CHAINED_SEGMENT
  VISUAL_ONLY_SOURCE_GEOMETRY
  FOREIGN_CONTROLLER
  REVIEW_REQUIRED
  INVALID_ORPHANED_REFERENCE

Coverage denominator:
  generated ACTIVE_CONTROLLED / total ACTIVE_CONTROLLED
  (NOT generated / all visualization objects)

Diagnostic only — does NOT modify fortna_autogen.py or production generators.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))
os.chdir(REPO)
os.environ.setdefault("FORTNA_PRISM_DISABLE", "1")

MACHINE = "MSCRENOPICK"
OUT_DIR = REPO / "exports" / "delivery_gate_20261002"
OUT_DIR.mkdir(parents=True, exist_ok=True)
JSON_OUT = OUT_DIR / "MSCRENOPICK_TRANSPORT_ACTIVE_EVIDENCE.json"
TXT_OUT = OUT_DIR / "MSCRENOPICK_TRANSPORT_ACTIVE_EVIDENCE.txt"

CLASSES = (
    "ACTIVE_CONTROLLED",
    "ACTIVE_CHAINED_SEGMENT",
    "VISUAL_ONLY_SOURCE_GEOMETRY",
    "FOREIGN_CONTROLLER",
    "REVIEW_REQUIRED",
    "INVALID_ORPHANED_REFERENCE",
)

NA = frozenset({"", "N/A", "NA", "INVALID", "NONE", "ALL", "0", "~"})
P_TAG_RE = re.compile(r"^P\d{1,4}(?!\d)[A-Z0-9_]*$", re.I)
_LOGIC_RE = re.compile(
    r"\b(XIC|XIO|OTE|OTL|OTU|TON|TOF|OSR|JSR|MOV|EQU|NEQ|GEQ|LEQ|GRT|LES|"
    r"ADD|SUB|MUL|DIV|CPT)\b",
    re.I,
)
_NOP_RE = re.compile(r"\bNOP\s*\(", re.I)


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _is_na(v: Any) -> bool:
    return _clean(v).upper() in NA


def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.is_file() or p.is_dir():
            return p
    return None


def resolve_run_dir() -> Path:
    candidates = [
        REPO / "workspace" / "active" / "RUN",
        REPO.parent / "FortnaPlus" / "workspace" / "active" / "RUN",
        REPO
        / "workspace"
        / "_reno_peek"
        / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
        / "RUN",
        REPO.parent
        / "FortnaPlus"
        / "workspace"
        / "_reno_peek"
        / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
        / "RUN",
    ]
    for cand in candidates:
        cfg = cand / "project.cfg"
        if not cfg.is_file():
            continue
        try:
            txt = cfg.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"MACHINENAME\s*=\s*MSCRENOPICK", txt, re.I):
            return cand
    hit = _first_existing(candidates)
    if hit is None:
        raise FileNotFoundError("MSCRENOPICK RUN not found")
    return hit


def resolve_l5x() -> Path | None:
    cands: list[Path] = []
    for base in (
        REPO.parent / "FortnaPlus" / "exports" / "current",
        REPO / "exports" / "current",
    ):
        if not base.is_dir():
            continue
        cands.extend(
            sorted(
                base.glob("MSCRENOPICK_*.L5X"),
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )
        )
    return _first_existing(cands)


def resolve_autogen_report() -> Path | None:
    builds = [
        REPO.parent / "FortnaPlus" / "workspace" / ".internal" / "builds",
        REPO / "workspace" / ".internal" / "builds",
    ]
    cands: list[Path] = []
    for base in builds:
        if not base.is_dir():
            continue
        for d in base.iterdir():
            if not d.is_dir():
                continue
            rep = d / "autogen_report.json"
            if rep.is_file() and (
                any(d.glob("MSCRENOPICK*")) or "MSCRENOPICK" in d.name.upper()
            ):
                cands.append(rep)
    if not cands:
        return None
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for rep in cands:
        try:
            j = json.loads(rep.read_text(encoding="utf-8"))
        except Exception:
            continue
        proj = str(j.get("project") or j.get("controller") or "").upper()
        if "MSCRENOPICK" in proj or not proj:
            return rep
    return cands[0]


# ---------------------------------------------------------------------------
# Evidence loaders
# ---------------------------------------------------------------------------


def graph_nodes(run_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from fortna_run_physical_layout import build_transport_graph

    graph = build_transport_graph(run_dir, MACHINE)
    nodes: list[dict[str, Any]] = []
    for area in graph.get("areas") or []:
        for n in area.get("nodes") or []:
            tag = _clean(n.get("conveyorTag") or n.get("label")).upper()
            if not tag:
                continue
            nodes.append(dict(n, conveyorTag=tag))
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for n in nodes:
        t = n["conveyorTag"]
        if t in seen:
            continue
        seen.add(t)
        uniq.append(n)
    return uniq, graph


def load_conveyor_asc_index(run_dir: Path) -> dict[str, dict[str, Any]]:
    from fortna_asc import read_asc

    path = run_dir / "FORTNA" / "Conveyor.asc"
    _h, rows = read_asc(path)
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        name = _clean(r.get("IO_Name")).upper()
        if not name or not P_TAG_RE.match(name):
            continue
        # Prefer first mechanical-looking row; keep first if already present.
        if name in out:
            continue
        out[name] = dict(r)
    return out


def load_mtrchain_by_conveyor(run_dir: Path) -> dict[str, list[dict[str, Any]]]:
    from fortna_asc import read_asc

    path = run_dir / "FORTNA" / "Mtrchain.asc"
    if not path.is_file():
        return {}
    _h, rows = read_asc(path)
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        motor = _clean(r.get("Motor_Name"))
        if _is_na(motor):
            continue
        for i in range(1, 11):
            chained = _clean(r.get(f"Motor_Chained{i}"))
            if _is_na(chained):
                continue
            # Chained targets may be P-tags or other devices.
            if P_TAG_RE.match(chained):
                out[chained.upper()].append(
                    {
                        "motor": motor,
                        "motor_ndx": _clean(r.get("Motor_Ndx")),
                        "aux": _clean(r.get("Motor_Aux")),
                        "source": "Mtrchain.asc",
                    }
                )
    return dict(out)


def load_motor_vfd_rows(run_dir: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    """Index MOTOR/VFD-like Conveyor.asc rows by normalized device name."""
    from fortna_asc import read_asc
    from fortna_io_extract import belongs_to_controller, row_machine_matches

    path = run_dir / "FORTNA" / "Conveyor.asc"
    _h, rows = read_asc(path)
    motors: dict[str, dict] = {}
    vfds: dict[str, dict] = {}
    for r in rows:
        name = _clean(r.get("IO_Name"))
        if not name:
            continue
        typ = _clean(r.get("Type")).upper()
        nu = name.upper()
        mach = _clean(r.get("Machine_Name"))
        on_ctrl = False
        if mach and mach.upper() not in NA:
            try:
                on_ctrl = bool(row_machine_matches(mach, MACHINE))
            except Exception:
                on_ctrl = mach.upper() == MACHINE.upper()
        if nu.startswith("VFD") and (on_ctrl or not mach or mach.upper() in NA):
            if on_ctrl or not mach or mach.upper() in NA:
                # Keep controller-owned; blank machine kept as candidate only if
                # IO word later proves ownership — store with flag.
                vfds[nu] = {
                    "name": name,
                    "machine_name": mach,
                    "type": typ,
                    "on_controller": on_ctrl,
                    "io_word": _clean(r.get("IO_Address_Word")),
                    "io_bit": _clean(r.get("IO_Address_Bit")),
                }
        if (typ == "MOTOR" or re.match(r"^M\d", nu)) and on_ctrl:
            motors[nu] = {
                "name": name,
                "machine_name": mach,
                "type": typ,
                "on_controller": on_ctrl,
                "io_word": _clean(r.get("IO_Address_Word")),
                "io_bit": _clean(r.get("IO_Address_Bit")),
            }
    return motors, vfds


def load_pe_topology(run_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Sensor→conveyor topology (Fullline/Jamcheck/Fulljam) + controller PE IO."""
    from fortna_run_equipment_fidelity import _fortna_dir, _load_sensor_conveyor_map
    from fortna_io_extract import (
        belongs_to_controller,
        equipment_kind,
        extract_io_points,
    )

    fortna = _fortna_dir(run_dir)
    sensor_map = _load_sensor_conveyor_map(fortna)
    by_conv: dict[str, list[dict[str, Any]]] = defaultdict(list)

    # Topology authority
    for sensor, conv in sensor_map.items():
        by_conv[conv.upper()].append(
            {
                "photoeye": sensor,
                "association": "topology_table",
                "authority": "Fullline/Jamcheck/Fulljam",
                "confidence": "HIGH",
            }
        )

    # Controller-scoped physical PE IO (supporting; topology still preferred)
    try:
        points = extract_io_points(run_dir, include_spares=False)
    except Exception:
        points = []
    try:
        from fortna_autogen import _load_eip_adapters

        _a, _ip, _m, _t, word_map = _load_eip_adapters(run_dir)
    except Exception:
        word_map = {}

    for p in points:
        kind = p.get("equipment_kind") or equipment_kind(
            p.get("fortna_name") or "", p.get("device_type") or "", p.get("description") or ""
        )
        if kind != "photoeye":
            continue
        if not belongs_to_controller(
            machine_name=str(p.get("machine_name") or ""),
            io_word=str(p.get("fortna_bank") or ""),
            controller=MACHINE,
            word_map=word_map,
        ):
            continue
        name = _clean(p.get("fortna_name")).upper()
        conv = sensor_map.get(name) or ""
        if not conv:
            # Name similarity is supporting only — never authority.
            m = re.match(r"^(?:EZ)?PE[\s\-_]*(\d{1,4}[A-Za-z]?)", name, re.I)
            if m:
                guess = ("P" + m.group(1)).upper()
                by_conv[guess].append(
                    {
                        "photoeye": name,
                        "association": "name_similarity_supporting",
                        "authority": "NOT_ENDPOINT_AUTHORITY",
                        "confidence": "LOW",
                        "io_word": str(p.get("fortna_bank") or ""),
                        "io_bit": str(p.get("fortna_bit") or ""),
                        "machine_name": str(p.get("machine_name") or ""),
                    }
                )
            continue
        # Dedup if topology already listed
        existing = {x["photoeye"].upper() for x in by_conv[conv.upper()]}
        if name in existing:
            # Enrich with physical IO
            for x in by_conv[conv.upper()]:
                if x["photoeye"].upper() == name:
                    x["io_word"] = str(p.get("fortna_bank") or "")
                    x["io_bit"] = str(p.get("fortna_bit") or "")
                    x["machine_name"] = str(p.get("machine_name") or "")
                    x["physical_io"] = True
        else:
            by_conv[conv.upper()].append(
                {
                    "photoeye": name,
                    "association": "topology_plus_controller_io",
                    "authority": "Fullline/Jamcheck/Fulljam+IO",
                    "confidence": "HIGH",
                    "io_word": str(p.get("fortna_bank") or ""),
                    "io_bit": str(p.get("fortna_bit") or ""),
                    "machine_name": str(p.get("machine_name") or ""),
                    "physical_io": True,
                }
            )
    return dict(by_conv)


def load_physical_io_for_conveyors(
    run_dir: Path, tags: set[str]
) -> dict[str, list[dict[str, Any]]]:
    """Physical I/O points whose device name implies a conveyor family on this PLC."""
    from fortna_io_extract import belongs_to_controller, extract_io_points

    try:
        points = extract_io_points(run_dir, include_spares=False)
    except Exception:
        return {}
    try:
        from fortna_autogen import _load_eip_adapters

        _a, _ip, _m, _t, word_map = _load_eip_adapters(run_dir)
    except Exception:
        word_map = {}

    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in points:
        if not belongs_to_controller(
            machine_name=str(p.get("machine_name") or ""),
            io_word=str(p.get("fortna_bank") or ""),
            controller=MACHINE,
            word_map=word_map,
        ):
            continue
        name = _clean(p.get("fortna_name")).upper()
        # Direct P-tag device
        if name in tags:
            out[name].append(
                {
                    "device": name,
                    "kind": p.get("equipment_kind") or p.get("device_type"),
                    "bank": str(p.get("fortna_bank") or ""),
                    "bit": str(p.get("fortna_bit") or ""),
                    "machine_name": str(p.get("machine_name") or ""),
                }
            )
            continue
        # M### / VFD### / PE### → P### family (supporting relationship)
        m = re.match(r"^(?:M|VFD|(?:EZ)?PE)[\s\-_]*(\d{1,4}[A-Za-z]?)", name, re.I)
        if not m:
            continue
        cand = ("P" + m.group(1)).upper()
        if cand not in tags:
            # lettered parent
            parent = re.match(r"^(P\d{1,4})", cand)
            if parent and parent.group(1) in tags:
                cand = parent.group(1)
            else:
                continue
        out[cand].append(
            {
                "device": name,
                "kind": p.get("equipment_kind") or p.get("device_type"),
                "bank": str(p.get("fortna_bank") or ""),
                "bit": str(p.get("fortna_bit") or ""),
                "machine_name": str(p.get("machine_name") or ""),
                "link": "device_family_to_conveyor",
            }
        )
    return dict(out)


def load_merge_evidence(run_dir: Path) -> dict[str, Any]:
    from fortna_asc import read_asc
    from fortna_run_equipment_fidelity import _fortna_dir, _load_merge_boss_owners

    fortna = _fortna_dir(run_dir)
    owners = _load_merge_boss_owners(fortna, MACHINE)
    bosses: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []

    boss_path = fortna / f"MergeBoss.asc.{MACHINE}"
    if not boss_path.is_file():
        boss_path = fortna / "MergeBoss.asc"
    if boss_path.is_file():
        _h, rows = read_asc(boss_path)
        for r in rows:
            name = _clean(r.get("Name"))
            if _is_na(name):
                continue
            if _clean(r.get("Valid")).upper() not in {"Y", "YES", "1", "TRUE"}:
                # Still record if Owner matches — some rows may be transitional.
                if _clean(r.get("Owner")).upper() != MACHINE.upper():
                    continue
            bosses.append(
                {
                    "name": name,
                    "owner": _clean(r.get("Owner")),
                    "valid": _clean(r.get("Valid")),
                    "num_inputs": _clean(r.get("NumInputs")),
                    "operable_input": _clean(r.get("OperableInput")),
                    "process": _clean(r.get("Process")),
                    "lanes": re.findall(r"P\d{1,4}[A-Z0-9_]*", name, flags=re.I),
                    "source": str(boss_path.name),
                }
            )

    mi_path = fortna / f"MergeInputs.asc.{MACHINE}"
    if not mi_path.is_file():
        mi_path = fortna / "MergeInputs.asc"
    if mi_path.is_file():
        _h, rows = read_asc(mi_path)
        for r in rows:
            name = _clean(r.get("Name"))
            if _is_na(name):
                continue
            inputs.append(
                {
                    "name": name,
                    "merge_boss": _clean(r.get("MergeBoss")),
                    "valid": _clean(r.get("Valid")),
                    "presense": _clean(r.get("Presense")),
                    "release_io": _clean(r.get("ReleaseIO")),
                    "merge_route": _clean(r.get("MergeRoute")),
                    "source": str(mi_path.name),
                }
            )

    by_tag: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for b in bosses:
        for lane in b.get("lanes") or []:
            by_tag[lane.upper()].append({"kind": "mergeboss", **b})
    for inp in inputs:
        tag = _clean(inp.get("name")).upper()
        if P_TAG_RE.match(tag):
            by_tag[tag].append({"kind": "mergeinput", **inp})
        boss = _clean(inp.get("merge_boss"))
        for lane in re.findall(r"P\d{1,4}[A-Z0-9_]*", boss, flags=re.I):
            by_tag[lane.upper()].append({"kind": "mergeinput_boss_lane", **inp})

    return {
        "bosses": bosses,
        "inputs": inputs,
        "owners_by_tag": {k: sorted(v) for k, v in owners.items()},
        "by_tag": dict(by_tag),
    }


def load_trigger_link(run_dir: Path) -> dict[str, list[str]]:
    """TriggerLink_Name from Conveyor.asc as start/stop / Link Part style evidence."""
    from fortna_asc import read_asc

    path = run_dir / "FORTNA" / "Conveyor.asc"
    _h, rows = read_asc(path)
    out: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        name = _clean(r.get("IO_Name")).upper()
        if not name or not P_TAG_RE.match(name):
            continue
        # Column may have trailing space in header
        link = _clean(r.get("TriggerLink_Name") or r.get("TriggerLink_Name "))
        if link and not _is_na(link):
            out[name].append(link)
        err = _clean(r.get("ErrLink"))
        if err and not _is_na(err):
            out[name].append(f"ErrLink:{err}")
    return dict(out)


def generated_set(
    run_dir: Path, l5x: Path | None, report_path: Path | None
) -> tuple[set[str], dict[str, Any]]:
    meta: dict[str, Any] = {"sources": []}
    tags: set[str] = set()
    try:
        from fortna_autogen import load_from_run

        inp = load_from_run(run_dir)
        for c in inp.conveyors or []:
            t = _clean(getattr(c, "conveyor", None) or getattr(c, "name", None)).upper()
            if t:
                tags.add(t)
        meta["sources"].append({"kind": "load_from_run", "count": len(tags)})
        meta["load_from_run"] = sorted(tags)
        meta["merges_2to1"] = list(getattr(inp, "merges_2to1", None) or [])
        meta["merges_withheld_attr"] = list(
            getattr(inp, "_merges_withheld_review", None) or []
        )
    except Exception as ex:  # noqa: BLE001
        meta["load_from_run_error"] = str(ex)

    if l5x and l5x.is_file():
        text = l5x.read_text(encoding="utf-8", errors="replace")
        aoi = {m.upper() for m in re.findall(r'Name="(P\d{1,4}[A-Z0-9_]*)_Conv"', text)}
        tags |= aoi
        meta["sources"].append({"kind": "l5x_conv_tags", "count": len(aoi)})
        meta["l5x_conv"] = sorted(aoi)

    if report_path and report_path.is_file():
        try:
            rep = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as ex:  # noqa: BLE001
            meta["autogen_report_error"] = str(ex)
            rep = {}
        lea = rep.get("local_equipment_accounting") or {}
        gen = {
            _clean(x).upper()
            for x in (lea.get("generated_conveyors") or [])
            if _clean(x)
        }
        if not gen:
            for t, info in (lea.get("by_tag") or {}).items():
                if (info or {}).get("classification") == "GENERATED_LOCAL":
                    gen.add(_clean(t).upper())
        tags |= gen
        meta["sources"].append({"kind": "autogen_report", "count": len(gen)})
        meta["autogen_report"] = {
            "path": str(report_path),
            "conveyor_count": rep.get("conveyor_count"),
            "conveyors_with_real_pe": rep.get("conveyors_with_real_pe"),
            "merges_withheld_review": list(rep.get("merges_withheld_review") or []),
            "merges_withheld_count": rep.get("merges_withheld_count"),
        }
        meta["merges_withheld_review"] = list(rep.get("merges_withheld_review") or [])

    meta["generated_union_count"] = len(tags)
    return tags, meta


def fidelity_index(run_dir: Path) -> dict[str, dict[str, Any]]:
    try:
        from fortna_run_equipment_fidelity import classify_run_equipment_fidelity

        fid = classify_run_equipment_fidelity(run_dir, MACHINE)
    except Exception as ex:  # noqa: BLE001
        return {"__error__": {"error": str(ex)}}
    out: dict[str, dict[str, Any]] = {}
    for row in fid.get("rows") or []:
        ident = _clean(row.get("identity")).upper()
        if ident:
            out[ident] = row
    out["__meta__"] = {
        "counts": fid.get("counts"),
        "local_active_tags": fid.get("local_active_tags"),
        "foreign_tags": [
            t
            for t in (fid.get("foreign_tags") or [])
            if P_TAG_RE.match(str(t or ""))
        ],
    }
    return out


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _motor_matches_conveyor(motor_name: str, tag: str) -> bool:
    """Exact family match: M303↔P303, M128A↔P128A.

    Bare M128 may also own bare P128. Bare M128 does NOT own lettered P128A
    (lettered conveyors need lettered motors or other ownership proof).
    Lettered M128A may also own bare parent P128.
    """
    raw = re.sub(
        r"(_)?(AUX|FLT|OK|RUN|EN|CMD|REF|FB)$",
        "",
        str(motor_name or ""),
        flags=re.I,
    )
    m = re.match(r"^M[\s\-_]*(\d{1,4})([A-Z]?)$", raw, re.I)
    c = re.match(r"^P(\d{1,4})([A-Z]?)$", tag or "", re.I)
    if not m or not c:
        return False
    if m.group(1) != c.group(1):
        return False
    m_let = (m.group(2) or "").upper()
    c_let = (c.group(2) or "").upper()
    if m_let == c_let:
        return True
    # Lettered motor may also own bare parent conveyor.
    if m_let and not c_let:
        return True
    return False


def _vfd_matches_conveyor(vfd_name: str, tag: str) -> bool:
    raw = re.sub(
        r"(_)?(AUX|FLT|OK|RUN|EN|CMD|REF|FB)$",
        "",
        str(vfd_name or ""),
        flags=re.I,
    )
    m = re.match(r"^VFD[\s\-_]*(\d{1,4})([A-Z]?)$", raw, re.I)
    c = re.match(r"^P(\d{1,4})([A-Z]?)$", tag or "", re.I)
    if not m or not c:
        return False
    if m.group(1) != c.group(1):
        return False
    m_let = (m.group(2) or "").upper()
    c_let = (c.group(2) or "").upper()
    if m_let == c_let:
        return True
    if m_let and not c_let:
        return True
    return False


def build_evidence_row(
    node: dict[str, Any],
    *,
    asc: dict[str, Any] | None,
    mtrchain: list[dict[str, Any]],
    motors: dict[str, dict],
    vfds: dict[str, dict],
    pe_by_conv: list[dict[str, Any]],
    phys_io: list[dict[str, Any]],
    merge_hits: list[dict[str, Any]],
    trigger_links: list[str],
    fid: dict[str, Any] | None,
    generated: set[str],
) -> dict[str, Any]:
    from fortna_io_extract import row_machine_matches

    tag = node["conveyorTag"]
    asc = asc or {}
    fid = fid or {}

    machine_name = _clean(asc.get("Machine_Name") or node.get("machineName") or "")
    eq_type = _clean(asc.get("Type") or node.get("equipmentType") or "")
    drive_field = _clean(asc.get("Drive") or "")
    motor_col = _clean(asc.get("Motor") or "")
    io_word = _clean(asc.get("IO_Address_Word") or "")
    io_bit = _clean(asc.get("IO_Address_Bit") or "")
    in_motor_chain = _clean(asc.get("In Motor Chain") or "")

    # Machine ownership
    machine_match = False
    machine_foreign = False
    if machine_name and machine_name.upper() not in NA:
        try:
            machine_match = bool(row_machine_matches(machine_name, MACHINE))
        except Exception:
            machine_match = machine_name.upper() == MACHINE.upper()
        machine_foreign = not machine_match
    machine_evidence = {
        "present": bool(machine_name) and machine_name.upper() not in NA,
        "value": machine_name or None,
        "matches_controller": machine_match,
        "foreign": machine_foreign,
    }

    # Conveyor/config table row
    config_evidence = {
        "present": bool(asc),
        "type": eq_type or None,
        "drive_field": drive_field or None,
        "motor_column": motor_col or None,
        "io_address_word": io_word or None,
        "io_address_bit": io_bit or None,
        "in_motor_chain": in_motor_chain or None,
        "part_number": _clean(asc.get("Part_Number")) or None,
        "source": "FORTNA/Conveyor.asc" if asc else None,
    }

    # Motor / starter
    motor_hits: list[dict[str, Any]] = list(mtrchain)
    if motor_col and not _is_na(motor_col):
        motor_hits.append(
            {"motor": motor_col, "source": "Conveyor.asc.Motor", "motor_ndx": motor_col}
        )
    # Controller motor rows matching family
    for mn, minfo in motors.items():
        if _motor_matches_conveyor(mn, tag) and minfo.get("on_controller"):
            motor_hits.append(
                {
                    "motor": mn,
                    "source": "Conveyor.asc.MOTOR_row",
                    "machine_name": minfo.get("machine_name"),
                    "io_word": minfo.get("io_word"),
                    "io_bit": minfo.get("io_bit"),
                }
            )
    # Dedupe by motor name
    seen_m: set[str] = set()
    motors_dedup: list[dict[str, Any]] = []
    for mh in motor_hits:
        key = _clean(mh.get("motor")).upper()
        if not key or key in seen_m:
            continue
        seen_m.add(key)
        motors_dedup.append(mh)
    motor_evidence = {
        "present": bool(motors_dedup),
        "motors": motors_dedup,
        "count": len(motors_dedup),
    }

    # VFD
    vfd_hits: list[dict[str, Any]] = []
    if drive_field and re.search(r"VFD", drive_field, re.I):
        vfd_hits.append({"vfd": drive_field, "source": "Conveyor.asc.Drive"})
    for vn, vinfo in vfds.items():
        if _vfd_matches_conveyor(vn, tag) and vinfo.get("on_controller"):
            vfd_hits.append(
                {
                    "vfd": vn,
                    "source": "Conveyor.asc.VFD_row",
                    "machine_name": vinfo.get("machine_name"),
                    "io_word": vinfo.get("io_word"),
                }
            )
    vfd_evidence = {"present": bool(vfd_hits), "vfds": vfd_hits, "count": len(vfd_hits)}

    # PE
    pe_topo = [
        p
        for p in pe_by_conv
        if p.get("association")
        in {"topology_table", "topology_plus_controller_io"}
        or p.get("authority") not in {None, "NOT_ENDPOINT_AUTHORITY"}
    ]
    pe_name_only = [
        p for p in pe_by_conv if p.get("association") == "name_similarity_supporting"
    ]
    pe_evidence = {
        "present": bool(pe_topo),
        "topology_relationships": pe_topo,
        "name_similarity_supporting_only": pe_name_only,
        "topology_count": len(pe_topo),
        "name_only_count": len(pe_name_only),
    }

    # Physical I/O
    phys_non_pe = [
        x
        for x in phys_io
        if "PE" not in str(x.get("kind") or "").upper()
        and not re.match(r"^(?:EZ)?PE", str(x.get("device") or ""), re.I)
    ]
    phys_evidence = {
        "present": bool(phys_io),
        "points": phys_io[:20],
        "count": len(phys_io),
        "non_pe_count": len(phys_non_pe),
    }

    # Start/stop / Link Part / TriggerLink
    link_evidence = {
        "present": bool(trigger_links),
        "links": trigger_links,
    }

    # Merge / other operational
    merge_evidence = {
        "present": bool(merge_hits),
        "relationships": merge_hits,
        "count": len(merge_hits),
    }

    # Graph presentation flags
    external = bool(node.get("externalReference")) or str(
        node.get("scopeClass") or ""
    ).upper() == "EXTERNAL_REFERENCE"
    plc_owned_flag = bool(node.get("plcOwned", True))
    fid_cls = _clean(fid.get("fidelity_class")).upper()

    # ---- Corroborating operational evidence beyond graphics ----
    #
    # IMPORTANT: plant-wide Mtrchain / digit-family motor name matches are NOT
    # by themselves proof that THIS controller actively controls a conveyor.
    # Display-context EXTERNAL_REFERENCE neighbors often share plant Mtrchain
    # rows (PACK_*, CP8_*, etc.) without being MSCRENOPICK-owned equipment.
    #
    # Controller-local ownership proof (any one is sufficient when paired with
    # real ops evidence, or alone when explicit):
    #   - explicit Machine_Name match to this controller
    #   - MergeBoss Owner = this controller
    #   - fidelity LOCAL_ACTIVE_EQUIPMENT (Machine / linked local IO / MergeBoss)
    #   - graph plcOwned / non-external Autogen membership with linked evidence
    owner_local_mergeboss = any(
        _clean(h.get("owner")).upper() == MACHINE.upper()
        for h in merge_hits
        if h.get("kind") == "mergeboss"
    )
    fidelity_local_active = fid_cls == "LOCAL_ACTIVE_EQUIPMENT"

    # Motors that are actually controller-scoped (MOTOR row on_controller),
    # as opposed to plant-wide Mtrchain-only hits.
    controller_scoped_motors = [
        m
        for m in motors_dedup
        if m.get("source") == "Conveyor.asc.MOTOR_row"
        or (
            m.get("machine_name")
            and str(m.get("machine_name")).upper() == MACHINE.upper()
        )
    ]
    mtrchain_only_motors = [
        m for m in motors_dedup if m.get("source") == "Mtrchain.asc"
    ]

    evidence_flags: list[str] = []
    if machine_match:
        evidence_flags.append("machine_ownership")
    if controller_scoped_motors:
        evidence_flags.append("motor_starter_controller_scoped")
    elif mtrchain_only_motors:
        evidence_flags.append("motor_mtrchain_plantwide")
    if vfd_hits:
        evidence_flags.append("vfd")
    if pe_topo:
        evidence_flags.append("photoeye_topology")
    if phys_non_pe:
        evidence_flags.append("physical_io")
    if trigger_links:
        evidence_flags.append("trigger_link")
    if owner_local_mergeboss:
        evidence_flags.append("mergeboss_owner")
    elif merge_hits:
        evidence_flags.append("merge_relationship")
    if fidelity_local_active:
        evidence_flags.append("fidelity_local_active")
    if asc and machine_match:
        evidence_flags.append("conveyor_config_owned")
    elif asc and (
        controller_scoped_motors or pe_topo or vfd_hits or fidelity_local_active
    ):
        evidence_flags.append("conveyor_config_linked")

    unique_ops = sorted(set(evidence_flags))

    # Strong controller-local ownership (not plant-wide association alone).
    controller_local_ownership = bool(
        machine_match
        or owner_local_mergeboss
        or fidelity_local_active
        or (
            (not external)
            and plc_owned_flag
            and (
                controller_scoped_motors
                or pe_topo
                or phys_non_pe
                or vfd_hits
            )
        )
    )

    # Classification
    reason_parts: list[str] = []
    classification = "REVIEW_REQUIRED"

    if not tag or tag.upper() in NA or tag.upper() == "INVALID":
        classification = "INVALID_ORPHANED_REFERENCE"
        reason_parts.append("unusable_or_placeholder_identity")
    elif machine_foreign or fid_cls == "FOREIGN_EQUIPMENT":
        classification = "FOREIGN_CONTROLLER"
        reason_parts.append(
            f"foreign_machine:{machine_name}"
            if machine_foreign
            else f"fidelity_FOREIGN:{','.join(list(fid.get('reasons') or [])[:3])}"
        )
    elif external and not controller_local_ownership:
        # Visualization neighbor / staging geometry without THIS controller's
        # ownership proof. Plant Mtrchain or PE topology on another system's
        # conveyor does not make it ACTIVE_CONTROLLED here.
        other_system_hint = any(
            re.search(
                r"\b(PACK_|SHIP_|CP\d+_|\bCP[0-9]\b|MSCRENOPACK|MSCRENOSHIP)",
                str(m.get("aux") or "") + " " + str(m.get("motor") or ""),
                re.I,
            )
            for m in motors_dedup
        )
        if other_system_hint:
            classification = "FOREIGN_CONTROLLER"
            reason_parts.append(
                "external_display_neighbor_with_other_system_mtrchain_or_aux"
            )
        else:
            classification = "VISUAL_ONLY_SOURCE_GEOMETRY"
            reason_parts.append(
                "external_display_neighbor_without_local_controller_ownership"
            )
        if mtrchain_only_motors and "motor_mtrchain_plantwide" not in reason_parts:
            reason_parts.append(
                "plantwide_mtrchain_ignored_for_external_without_ownership"
            )
    elif controller_local_ownership and (
        unique_ops
        or machine_match
        or owner_local_mergeboss
        or fidelity_local_active
    ):
        # Credible independent operational evidence on THIS controller.
        weak_only = set(unique_ops) <= {
            "merge_relationship",
            "trigger_link",
            "motor_mtrchain_plantwide",
        }
        if weak_only and not (
            machine_match or owner_local_mergeboss or fidelity_local_active
        ):
            classification = "REVIEW_REQUIRED"
            reason_parts.append(
                f"weak_operational_signal_only:{','.join(unique_ops)}"
            )
        else:
            classification = "ACTIVE_CONTROLLED"
            reason_parts.append("corroborating_ops:" + "+".join(unique_ops))
    elif unique_ops and not controller_local_ownership:
        classification = "REVIEW_REQUIRED"
        reason_parts.append(
            "ops_signals_present_but_controller_ownership_unproven:"
            + "+".join(unique_ops)
        )
    else:
        if fid_cls == "TEMPLATE_GRAPHICAL_ONLY":
            classification = "VISUAL_ONLY_SOURCE_GEOMETRY"
            reason_parts.append("template_graphical_only")
        else:
            classification = "VISUAL_ONLY_SOURCE_GEOMETRY"
            reason_parts.append(
                "visualization_present_without_operational_evidence"
            )

    # PE applicability for ACTIVE_CONTROLLED
    if classification == "ACTIVE_CONTROLLED":
        if pe_topo:
            pe_status = "REQUIRED_AND_FOUND"
            pe_reason = "topology_or_controller_io_relationship_present"
        elif pe_name_only:
            pe_status = "REVIEW_REQUIRED"
            pe_reason = (
                "name_similarity_only_not_topology_authority;"
                "do_not_invent_PE_from_conveyor_name"
            )
        else:
            pe_status = "NOT_APPLICABLE"
            pe_reason = (
                "no_Fortna_PE_topology_or_controller_PE_IO_relationship;"
                "PE_not_required_for_every_conveyor"
            )
    else:
        pe_status = "NOT_EVALUATED"
        pe_reason = "conveyor_not_ACTIVE_CONTROLLED"

    was_generated = tag in generated

    return {
        "conveyor": tag,
        "visualization_present": "YES",
        "equipment_type": eq_type or None,
        "graph_external_reference": external,
        "graph_plc_owned_flag": plc_owned_flag,
        "fidelity_class": fid_cls or None,
        "fidelity_reasons": list(fid.get("reasons") or []),
        "machine_controller_evidence": machine_evidence,
        "conveyor_config_evidence": config_evidence,
        "motor_starter_evidence": motor_evidence,
        "vfd_evidence": vfd_evidence,
        "photoeye_evidence": pe_evidence,
        "physical_io_evidence": phys_evidence,
        "start_stop_link_part_evidence": link_evidence,
        "other_operational_relationship": merge_evidence,
        "operational_evidence_flags": unique_ops,
        "final_classification": classification,
        "generation_yes_no": "YES" if was_generated else "NO",
        "was_generated": was_generated,
        "pe_relationship_status": pe_status,
        "pe_relationship_reason": pe_reason,
        "reason": "; ".join(reason_parts) if reason_parts else "unspecified",
        "provenance": {
            "asc_source": "FORTNA/Conveyor.asc" if asc else None,
            "graph_node_id": node.get("id"),
            "mtrchain_source": "FORTNA/Mtrchain.asc" if mtrchain else None,
            "merge_sources": sorted(
                {
                    str(h.get("source"))
                    for h in merge_hits
                    if h.get("source")
                }
            ),
        },
    }


def routine_quality(l5x: Path | None) -> list[dict[str, Any]]:
    watch = ("Conv_Flt", "Control_Station", "Stacklight", "Conv_Jam", "Conv_Fast", "Conv_PE")
    if not l5x or not l5x.is_file():
        return [
            {
                "routine": r,
                "status": "L5X_MISSING",
                "complete": False,
                "acceptance": "FAIL",
            }
            for r in watch
        ]
    text = l5x.read_text(encoding="utf-8", errors="replace")
    findings: list[dict[str, Any]] = []
    for rt in watch:
        m = re.search(rf'<Routine Name="{re.escape(rt)}"[\s\S]*?</Routine>', text)
        if not m:
            findings.append(
                {
                    "routine": rt,
                    "present": False,
                    "rung_count": 0,
                    "nontrivial_rungs": 0,
                    "nop_only_rungs": 0,
                    "status": "ABSENT",
                    "complete": False,
                    "acceptance": "REVIEW_REQUIRED",
                    "note": "Routine not present in L5X",
                }
            )
            continue
        body = m.group(0)
        rungs = re.findall(r"<Rung[\s\S]*?</Rung>", body)
        nontrivial = nop_only = emptyish = 0
        for r in rungs:
            has_logic = bool(_LOGIC_RE.search(r))
            has_nop = bool(_NOP_RE.search(r))
            if has_logic:
                nontrivial += 1
            elif has_nop:
                nop_only += 1
            else:
                emptyish += 1
        if nontrivial == 0 and (nop_only > 0 or len(rungs) == 0 or emptyish == len(rungs)):
            status = "PLACEHOLDER_NOP_ONLY" if nop_only else "EMPTY_OR_NO_LOGIC"
            acceptance = "FAIL"
            note = "Exists but NOP/empty — NOT counted as FUNCTIONAL generation"
        else:
            status = "FUNCTIONAL"
            acceptance = "FUNCTIONAL"
            note = "Has non-NOP logic rungs"
        findings.append(
            {
                "routine": rt,
                "present": True,
                "rung_count": len(rungs),
                "nontrivial_rungs": nontrivial,
                "nop_only_rungs": nop_only,
                "empty_or_comment_rungs": emptyish,
                "status": status,
                "complete": nontrivial > 0,
                "acceptance": acceptance,
                "note": note,
            }
        )
    return findings


def classify_routine_acceptance(findings: list[dict[str, Any]], name: str) -> str:
    for f in findings:
        if f.get("routine") == name:
            if f.get("acceptance") == "FUNCTIONAL":
                return "FUNCTIONAL"
            if f.get("status") == "ABSENT":
                # Absent may be NOT_APPLICABLE for some profiles — leave REVIEW
                # unless we prove N/A. Default FAIL for mandatory transport set.
                return "FAIL"
            if f.get("status") in {"PLACEHOLDER_NOP_ONLY", "EMPTY_OR_NO_LOGIC"}:
                return "FAIL"
            return str(f.get("acceptance") or "FAIL")
    return "FAIL"


def build_merge_report(
    merge_ev: dict[str, Any],
    classifications: dict[str, dict[str, Any]],
    withheld_names: list[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for b in merge_ev.get("bosses") or []:
        name = _clean(b.get("name"))
        if not name or name in seen:
            continue
        seen.add(name)
        lanes = [x.upper() for x in (b.get("lanes") or [])]
        lane_cls = {
            lane: (classifications.get(lane) or {}).get("final_classification")
            for lane in lanes
        }
        inputs = [
            i
            for i in (merge_ev.get("inputs") or [])
            if _clean(i.get("merge_boss")).upper() == name.upper()
        ]
        withheld = name in {w.upper() for w in withheld_names} or any(
            w.upper() == name.upper() for w in withheld_names
        )
        # Generation decision for merges: withheld stay REVIEW; else if all
        # lanes ACTIVE_CONTROLLED and owner local → eligible (but may still
        # be withheld by generator policy).
        if withheld:
            gen = "NO"
            why = f"generator_withheld_review:{name}"
            status = "REVIEW_REQUIRED"
        elif _clean(b.get("owner")).upper() != MACHINE.upper():
            gen = "NO"
            why = f"foreign_or_unknown_owner:{b.get('owner')}"
            status = "FOREIGN_CONTROLLER"
        elif all(lane_cls.get(l) == "ACTIVE_CONTROLLED" for l in lanes) and lanes:
            gen = "NO"  # still not silently generated if prior withhold empty
            # If not in withheld list, report as eligible-but-check
            if not withheld_names:
                gen = "ELIGIBLE"
                why = "all_lanes_ACTIVE_CONTROLLED_owner_local"
                status = "ACTIVE_CONTROLLED"
            else:
                # Other merges withheld; this one not listed → eligible
                gen = "ELIGIBLE_NOT_EMITTED_OR_CHECK"
                why = "lanes_active_owner_local;confirm_emit_path"
                status = "ACTIVE_CONTROLLED"
        else:
            gen = "NO"
            why = f"lane_classifications:{lane_cls}"
            status = "REVIEW_REQUIRED"

        # PE/motor for lanes
        pe_motor = {}
        for lane in lanes:
            row = classifications.get(lane) or {}
            pe_motor[lane] = {
                "pe_status": row.get("pe_relationship_status"),
                "motors": (row.get("motor_starter_evidence") or {}).get("motors"),
                "classification": row.get("final_classification"),
            }

        out.append(
            {
                "merge": name,
                "owner": b.get("owner"),
                "valid": b.get("valid"),
                "visual_evidence": "YES" if lanes else "PARTIAL",
                "active_controls_evidence": {
                    "owner": b.get("owner"),
                    "operable_input": b.get("operable_input"),
                    "num_inputs": b.get("num_inputs"),
                    "inputs": inputs,
                },
                "parent_child_lanes": lanes,
                "lane_classifications": lane_cls,
                "pe_motor_by_lane": pe_motor,
                "generator_withheld": withheld,
                "generation": gen,
                "status": status,
                "reason": why,
                "source": b.get("source"),
            }
        )
    # Ensure withheld names appear even if boss parse missed them
    for w in withheld_names:
        wu = w.upper()
        if wu in {x["merge"].upper() for x in out}:
            continue
        lanes = [t.upper() for t in re.findall(r"P\d{1,4}[A-Z0-9_]*", w, flags=re.I)]
        out.append(
            {
                "merge": w,
                "owner": None,
                "visual_evidence": "UNKNOWN",
                "active_controls_evidence": {},
                "parent_child_lanes": lanes,
                "lane_classifications": {
                    lane: (classifications.get(lane) or {}).get("final_classification")
                    for lane in lanes
                },
                "generator_withheld": True,
                "generation": "NO",
                "status": "REVIEW_REQUIRED",
                "reason": "listed_in_autogen_merges_withheld_review",
            }
        )
    return out


def render_txt(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("MSCRENOPICK TRANSPORT ACTIVE-CONTROL EVIDENCE")
    lines.append("=" * 78)
    lines.append(f"generated_at: {payload.get('generated_at')}")
    lines.append(f"run_dir: {payload.get('run_dir')}")
    lines.append(f"l5x: {payload.get('l5x')}")
    lines.append(f"candidate_base_sha: {payload.get('candidate_base_sha')}")
    lines.append(f"branch: {payload.get('branch')}")
    lines.append("")
    lines.append("LAW")
    lines.append("-" * 78)
    lines.append("VISUALIZATION PRESENCE != ACTIVE_CONTROLLED")
    lines.append(
        "Coverage = generated ACTIVE_CONTROLLED / total ACTIVE_CONTROLLED"
    )
    lines.append("Visual-only geometry is preserved (never silently deleted).")
    lines.append("")

    s = payload.get("summary") or {}
    lines.append("ACCEPTANCE COUNTS")
    lines.append("-" * 78)
    lines.append(f"VISUAL CONVEYOR OBJECTS: {s.get('visual_conveyor_objects')}")
    lines.append(f"ACTIVE_CONTROLLED: {s.get('ACTIVE_CONTROLLED')}")
    lines.append(
        f"VISUAL_ONLY_SOURCE_GEOMETRY: {s.get('VISUAL_ONLY_SOURCE_GEOMETRY')}"
    )
    lines.append(f"FOREIGN_CONTROLLER: {s.get('FOREIGN_CONTROLLER')}")
    lines.append(f"REVIEW_REQUIRED: {s.get('REVIEW_REQUIRED')}")
    lines.append(
        f"INVALID_ORPHANED_REFERENCE: {s.get('INVALID_ORPHANED_REFERENCE')}"
    )
    lines.append(
        f"UNCLASSIFIED / SILENTLY LOST: {s.get('unclassified_or_silently_lost')}"
    )
    lines.append(
        f"ACTIVE_CONTROLLED GENERATED: "
        f"{s.get('active_controlled_generated')}/{s.get('ACTIVE_CONTROLLED')}"
    )
    lines.append(f"ACTIVE GENERATION COVERAGE: {s.get('active_generation_coverage_pct')}%")
    lines.append(f"Conv_Flt: {s.get('Conv_Flt')}")
    lines.append(f"Control_Station: {s.get('Control_Station')}")
    lines.append(f"Stacklight: {s.get('Stacklight')}")
    lines.append(f"PE relationships accounted: {s.get('pe_relationships_accounted')}")
    lines.append(f"Merges accounted: {s.get('merges_accounted')}")
    lines.append("")

    lines.append("COMPARISON TO PRIOR CONSERVATION (presence-based)")
    lines.append("-" * 78)
    cmp_ = payload.get("comparison_to_prior_conservation") or {}
    for k, v in cmp_.items():
        lines.append(f"  {k}: {v}")
    lines.append("")

    lines.append("GENERIC RULE ASSESSMENT")
    lines.append("-" * 78)
    for note in payload.get("generic_rule_assessment") or []:
        lines.append(f"  - {note}")
    lines.append("")

    lines.append("ROUTINE QUALITY (existence != completion)")
    lines.append("-" * 78)
    for f in payload.get("routine_quality") or []:
        lines.append(
            f"  {f.get('routine')}: status={f.get('status')} "
            f"rungs={f.get('rung_count')} nontrivial={f.get('nontrivial_rungs')} "
            f"nop_only={f.get('nop_only_rungs')} acceptance={f.get('acceptance')}"
        )
    lines.append("")

    lines.append("MERGES")
    lines.append("-" * 78)
    for m in payload.get("merges") or []:
        lines.append(
            f"  {m.get('merge')}: status={m.get('status')} gen={m.get('generation')} "
            f"owner={m.get('owner')} lanes={m.get('parent_child_lanes')} "
            f"reason={m.get('reason')}"
        )
    lines.append("")

    lines.append("53-OBJECT CLASSIFICATION")
    lines.append("-" * 78)
    lines.append(
        f"{'TAG':<10} {'CLASS':<28} {'GEN':<4} {'PE':<20} REASON"
    )
    for row in payload.get("conveyors") or []:
        lines.append(
            f"{row.get('conveyor'):<10} {row.get('final_classification'):<28} "
            f"{row.get('generation_yes_no'):<4} "
            f"{str(row.get('pe_relationship_status') or '-'):<20} "
            f"{row.get('reason')}"
        )
    lines.append("")

    lines.append("PER-OBJECT EVIDENCE DETAIL")
    lines.append("-" * 78)
    for row in payload.get("conveyors") or []:
        lines.append(f"\n### {row.get('conveyor')}")
        lines.append(f"  visualization: {row.get('visualization_present')}")
        me = row.get("machine_controller_evidence") or {}
        lines.append(
            f"  machine: present={me.get('present')} value={me.get('value')} "
            f"match={me.get('matches_controller')} foreign={me.get('foreign')}"
        )
        ce = row.get("conveyor_config_evidence") or {}
        lines.append(
            f"  config: present={ce.get('present')} type={ce.get('type')} "
            f"drive={ce.get('drive_field')} motor_col={ce.get('motor_column')}"
        )
        mo = row.get("motor_starter_evidence") or {}
        motors = ", ".join(
            _clean(x.get("motor")) for x in (mo.get("motors") or [])[:6]
        )
        lines.append(f"  motor/starter: present={mo.get('present')} [{motors}]")
        vf = row.get("vfd_evidence") or {}
        lines.append(f"  vfd: present={vf.get('present')} count={vf.get('count')}")
        pe = row.get("photoeye_evidence") or {}
        pe_names = ", ".join(
            _clean(x.get("photoeye"))
            for x in (pe.get("topology_relationships") or [])[:6]
        )
        lines.append(
            f"  pe_topology: present={pe.get('present')} [{pe_names}] "
            f"name_only={pe.get('name_only_count')}"
        )
        pi = row.get("physical_io_evidence") or {}
        lines.append(
            f"  physical_io: present={pi.get('present')} count={pi.get('count')}"
        )
        lk = row.get("start_stop_link_part_evidence") or {}
        lines.append(f"  link/trigger: present={lk.get('present')} {lk.get('links')}")
        ot = row.get("other_operational_relationship") or {}
        lines.append(
            f"  other/merge: present={ot.get('present')} count={ot.get('count')}"
        )
        lines.append(f"  flags: {row.get('operational_evidence_flags')}")
        lines.append(f"  CLASS: {row.get('final_classification')}")
        lines.append(f"  GENERATE: {row.get('generation_yes_no')}")
        lines.append(
            f"  PE status: {row.get('pe_relationship_status')} "
            f"({row.get('pe_relationship_reason')})"
        )
        lines.append(f"  reason: {row.get('reason')}")

    lines.append("")
    lines.append("WARDEN READY")
    lines.append("-" * 78)
    lines.append(str(payload.get("warden_ready")))
    lines.append(f"note: {payload.get('warden_ready_note')}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    run_dir = resolve_run_dir()
    l5x = resolve_l5x()
    report = resolve_autogen_report()

    # Branch / SHA
    import subprocess

    def _git(*args: str) -> str:
        try:
            return subprocess.check_output(
                ["git", *args], cwd=str(REPO), text=True, stderr=subprocess.DEVNULL
            ).strip()
        except Exception:
            return ""

    head = _git("rev-parse", "HEAD")
    branch = _git("branch", "--show-current")

    nodes, graph = graph_nodes(run_dir)
    tags = {n["conveyorTag"] for n in nodes}
    asc_index = load_conveyor_asc_index(run_dir)
    mtr_by_conv = load_mtrchain_by_conveyor(run_dir)
    motors, vfds = load_motor_vfd_rows(run_dir)
    pe_map = load_pe_topology(run_dir)
    phys_map = load_physical_io_for_conveyors(run_dir, tags)
    merge_ev = load_merge_evidence(run_dir)
    trigger_map = load_trigger_link(run_dir)
    gen_tags, gen_meta = generated_set(run_dir, l5x, report)
    fid_idx = fidelity_index(run_dir)

    rows: list[dict[str, Any]] = []
    for node in sorted(nodes, key=lambda n: n["conveyorTag"]):
        tag = node["conveyorTag"]
        rows.append(
            build_evidence_row(
                node,
                asc=asc_index.get(tag),
                mtrchain=mtr_by_conv.get(tag) or [],
                motors=motors,
                vfds=vfds,
                pe_by_conv=pe_map.get(tag) or [],
                phys_io=phys_map.get(tag) or [],
                merge_hits=merge_ev.get("by_tag", {}).get(tag) or [],
                trigger_links=trigger_map.get(tag) or [],
                fid=fid_idx.get(tag),
                generated=gen_tags,
            )
        )

    by_class = Counter(r["final_classification"] for r in rows)
    for c in CLASSES:
        by_class.setdefault(c, 0)

    active = [r for r in rows if r["final_classification"] == "ACTIVE_CONTROLLED"]
    active_gen = [r for r in active if r["was_generated"]]
    active_count = len(active)
    active_gen_count = len(active_gen)
    coverage = (
        round(100.0 * active_gen_count / active_count, 2) if active_count else 0.0
    )
    unclassified = len(rows) - sum(by_class[c] for c in CLASSES)
    conservation_ok = (
        len(rows) == sum(by_class[c] for c in CLASSES) and unclassified == 0
    )

    class_by_tag = {r["conveyor"]: r for r in rows}
    withheld = list(
        (gen_meta.get("merges_withheld_review") or [])
        or ((gen_meta.get("autogen_report") or {}).get("merges_withheld_review") or [])
    )
    merges = build_merge_report(merge_ev, class_by_tag, withheld)

    rq = routine_quality(l5x)
    conv_flt = classify_routine_acceptance(rq, "Conv_Flt")
    cs = classify_routine_acceptance(rq, "Control_Station")
    sl = classify_routine_acceptance(rq, "Stacklight")

    # PE accounted: every ACTIVE has pe_relationship_status set
    pe_accounted = all(
        r.get("pe_relationship_status")
        in {"REQUIRED_AND_FOUND", "NOT_APPLICABLE", "REVIEW_REQUIRED"}
        for r in active
    )
    merges_accounted = len(merges) >= len(withheld) and all(
        m.get("status") for m in merges
    )

    # Prior conservation used presence-based "generated" class.
    prior = {
        "prior_report_classes": {
            "generated": 47,
            "foreign": 5,
            "withheld": 1,
        },
        "prior_method": (
            "classified 'generated' from load_from_run∪L5X∪report presence — "
            "NOT active-control evidence proof"
        ),
        "new_method": (
            "ACTIVE_CONTROLLED requires corroborating ops evidence "
            "(Machine / config / motor / VFD / PE topology / I/O / merge owner / link)"
        ),
        "load_from_run_generated_count": len(gen_meta.get("load_from_run") or gen_tags),
        "active_controlled_count": active_count,
        "active_also_generated": active_gen_count,
        "generated_but_not_active": sorted(
            r["conveyor"]
            for r in rows
            if r["was_generated"]
            and r["final_classification"] != "ACTIVE_CONTROLLED"
        ),
        "active_but_not_generated": sorted(
            r["conveyor"]
            for r in rows
            if (not r["was_generated"])
            and r["final_classification"] == "ACTIVE_CONTROLLED"
        ),
        "class_delta_vs_prior_generated_47": active_count - 47,
    }

    rule_notes: list[str] = []
    gen_not_active = prior.get("generated_but_not_active") or []
    active_not_gen = prior.get("active_but_not_generated") or []
    sectionish = [
        t
        for t in gen_not_active
        if re.search(r"A$|B$|C$", t)
        or t.startswith("P100")
    ]
    if gen_not_active:
        rule_notes.append(
            "GENERIC RULE GAP (do not patch site-specifically): production "
            "admitted conveyors into generation without controller-local "
            "ACTIVE_CONTROLLED evidence. On MSCRENOPICK this set is "
            f"{gen_not_active} (n={len(gen_not_active)}). Autogen progress "
            "reports Sections[MSCRENOPICK]: promoted=15 — matching this count. "
            "Section/assembly promotion must not imply ACTIVE_CONTROLLED."
        )
        rule_notes.append(
            "Evidence on those rows: Machine_Name=N/A, no fidelity "
            "linked_local / LOCAL_ACTIVE, no PE topology authority, only "
            "plant-wide Mtrchain and/or In Motor Chain=Y. That is insufficient "
            "corroboration under the permanent Transportation law."
        )
    if sectionish and len(sectionish) == len(gen_not_active):
        rule_notes.append(
            "Pattern: lettered section curves / P100x chain members were "
            "generated via section promotion or parent-family linkage, not "
            "independent motor/PE/Machine ownership on this controller."
        )
    if active_not_gen:
        rule_notes.append(
            "ACTIVE_CONTROLLED but not generated (expected if merge-withheld): "
            f"{active_not_gen}. P105A is MergeBoss-owned MSCRENOPICK lane of "
            "withheld merge P1001-P105A — preserve as ACTIVE evidence, keep "
            "merge generation REVIEW_REQUIRED/withheld."
        )
    if (
        active_gen_count == 32
        and by_class["FOREIGN_CONTROLLER"] == 5
        and len(gen_not_active) == 15
    ):
        rule_notes.append(
            "Warden observed generated≈32. Evidence-based ACTIVE generated=32. "
            "Prior presence-based conservation counted 47 (=32 ACTIVE generated "
            "+ 15 section-promoted REVIEW). Do not treat 47 as ACTIVE proof."
        )
    if not gen_not_active and active_count == len(
        gen_meta.get("load_from_run") or []
    ):
        rule_notes.append(
            "load_from_run membership aligns with ACTIVE_CONTROLLED evidence."
        )
    if conv_flt == "FAIL":
        rule_notes.append(
            "KNOWN FAIL: Conv_Flt is PLACEHOLDER_NOP_ONLY — must not count as "
            "FUNCTIONAL Transportation generation. Determine FUNCTIONAL vs "
            "NOT_APPLICABLE with deterministic evidence before any Warden handoff."
        )
    if cs == "FAIL":
        rule_notes.append(
            "KNOWN FAIL: Control_Station is placeholder/NOP — same rule as Conv_Flt."
        )
    if sl == "FAIL":
        rule_notes.append(
            "KNOWN FAIL: Stacklight is placeholder/NOP — same rule as Conv_Flt."
        )
    rule_notes.append(
        "Diagnostic only — no production Transportation rule changes in this "
        "pass. Return evidence to Curtis/Gilfoyle before generator edits."
    )
    rule_notes.append(
        "Coverage must remain ACTIVE_generated/ACTIVE_total — never /53 visual."
    )
    rule_notes.append(
        "Visual geometry conservation: FOREIGN + REVIEW + ACTIVE + VISUAL_ONLY "
        "+ INVALID must equal visual count; no silent deletion of visual-only "
        "or review objects."
    )

    warden_ready = "NO"
    warden_note = (
        "Mandatory Transportation routines Conv_Flt / Control_Station / Stacklight "
        "are still placeholder/NOP-only (FAIL). Return to Curtis/Gilfoyle — "
        "do NOT hand a new SHA to Warden; do NOT disturb frozen "
        "41033e45084bfd4b3dfb7639655a2082319ad7f2."
    )

    summary = {
        "visual_conveyor_objects": len(rows),
        "ACTIVE_CONTROLLED": by_class["ACTIVE_CONTROLLED"],
        "ACTIVE_CHAINED_SEGMENT": by_class.get("ACTIVE_CHAINED_SEGMENT", 0),
        "VISUAL_ONLY_SOURCE_GEOMETRY": by_class["VISUAL_ONLY_SOURCE_GEOMETRY"],
        "FOREIGN_CONTROLLER": by_class["FOREIGN_CONTROLLER"],
        "REVIEW_REQUIRED": by_class["REVIEW_REQUIRED"],
        "INVALID_ORPHANED_REFERENCE": by_class["INVALID_ORPHANED_REFERENCE"],
        "unclassified_or_silently_lost": unclassified,
        "conservation_ok": conservation_ok,
        "active_controlled_generated": active_gen_count,
        "active_generation_coverage_pct": coverage,
        "Conv_Flt": conv_flt,
        "Control_Station": cs,
        "Stacklight": sl,
        "pe_relationships_accounted": "YES" if pe_accounted else "NO",
        "merges_accounted": "YES" if merges_accounted else "NO",
        "warden_ready": warden_ready,
    }

    payload: dict[str, Any] = {
        "title": "MSCRENOPICK_TRANSPORT_ACTIVE_EVIDENCE",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_base_sha": "09371a1ff0293ef3405b2b3737a383bbd19d31a2",
        "frozen_warden_qualification_sha": (
            "41033e45084bfd4b3dfb7639655a2082319ad7f2"
        ),
        "branch": branch,
        "head_sha": head,
        "run_dir": str(run_dir),
        "l5x": str(l5x) if l5x else None,
        "autogen_report": str(report) if report else None,
        "law": {
            "visualization_ne_active_controlled": True,
            "coverage_denominator": "ACTIVE_CONTROLLED",
            "classes": list(CLASSES),
            "conservation_invariant": (
                "VISUAL = ACTIVE_CONTROLLED + ACTIVE_CHAINED_SEGMENT + "
                "VISUAL_ONLY_SOURCE_GEOMETRY + FOREIGN_CONTROLLER + "
                "REVIEW_REQUIRED + INVALID_ORPHANED_REFERENCE"
            ),
        },
        "summary": summary,
        "comparison_to_prior_conservation": prior,
        "generic_rule_assessment": rule_notes,
        "generated_meta": gen_meta,
        "graph_metrics": (graph.get("metrics") or {}),
        "routine_quality": rq,
        "merges": merges,
        "conveyors": rows,
        "warden_ready": warden_ready,
        "warden_ready_note": warden_note,
        "outputs": {"json": str(JSON_OUT), "txt": str(TXT_OUT)},
    }

    JSON_OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    TXT_OUT.write_text(render_txt(payload), encoding="utf-8")

    print("Wrote", JSON_OUT)
    print("Wrote", TXT_OUT)
    print("VISUAL", len(rows))
    print("ACTIVE_CONTROLLED", by_class["ACTIVE_CONTROLLED"])
    print("ACTIVE_CHAINED_SEGMENT", by_class.get("ACTIVE_CHAINED_SEGMENT", 0))
    print("VISUAL_ONLY", by_class["VISUAL_ONLY_SOURCE_GEOMETRY"])
    print("FOREIGN", by_class["FOREIGN_CONTROLLER"])
    print("REVIEW", by_class["REVIEW_REQUIRED"])
    print("INVALID", by_class["INVALID_ORPHANED_REFERENCE"])
    print("LOST", unclassified)
    print(
        f"ACTIVE GEN {active_gen_count}/{active_count} = {coverage}%"
    )
    print("Conv_Flt", conv_flt, "Control_Station", cs, "Stacklight", sl)
    print("WARDEN READY", warden_ready)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
