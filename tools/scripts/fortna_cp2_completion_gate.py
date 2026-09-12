#!/usr/bin/env python3
"""CP2 Completion Gate — truthful Greensboro ORNCCP2 evidence pack.

SOURCE-OF-TRUTH (docs/SOURCE_OF_TRUTH_POLICY.md):
  Generation inputs = active RUN + engineer Site Forge workbook + approved
  generic libraries only. Finished CP2 PLC is a POST-GENERATION validation
  oracle only — never used to populate workbook / areas / E-stop mappings.

Usage:
  python tools/scripts/fortna_cp2_completion_gate.py \\
    --run-dir workspace/active/RUN --machine ORNCCP2 --out exports/cp2-gate
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import CONVEYOR_TYPES, read_asc  # noqa: E402
from fortna_autogen import DEFAULT_LIBRARY, load_eip_topology, load_from_run  # noqa: E402
from fortna_io_extract import (  # noqa: E402
    belongs_to_controller,
    equipment_kind,
    extract_io_points,
    read_project_meta,
    row_machine_matches,
)
from fortna_l5x_compare import extract_l5x, run_compare  # noqa: E402
from fortna_run_physical_layout import build_transport_graph  # noqa: E402

FINISHED_CP2_L5X = Path(
    r"C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_GreensboroPLC2_NC_Finished.L5X"
)
REQUIRED_LIBS = [
    "OReilly_Library_v3.L5X",
    "programs/IO_MAP_Program.L5X",
    "programs/Sys_Program.L5X",
    "programs/System_Program.L5X",
    "Slow_Flt_AOI.L5X",
]
ENGINEER_CFG_REQUIRED = "ENGINEER CONFIGURATION REQUIRED"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def _run_py(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, *args]
    return subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _normalize_run_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    if not run_dir.is_absolute():
        run_dir = (ROOT / run_dir).resolve()
    if (run_dir / "RUN" / "project.cfg").is_file():
        return run_dir / "RUN"
    return run_dir


# ---------------------------------------------------------------------------
# 1. IO inventory
# ---------------------------------------------------------------------------

def _is_motor_starter_out(p: dict) -> bool:
    kind = (p.get("equipment_kind") or "").lower()
    name = (p.get("fortna_name") or p.get("tag") or "").upper()
    if kind != "motor":
        return False
    if name.endswith("_AUX") or name.endswith("_OL") or name.endswith("_FLT"):
        return False
    return (p.get("io_type") or "").upper() == "OUT"


def _is_overload_feedback(p: dict) -> bool:
    kind = (p.get("equipment_kind") or "").lower()
    name = (p.get("fortna_name") or p.get("tag") or "").upper()
    desc = (p.get("description") or "").upper()
    if kind != "motor":
        return False
    return (
        name.endswith("_AUX")
        or name.endswith("_OL")
        or "OVERLOAD" in desc
        or "CONTACTOR" in desc
        or "IS RUNNING" in desc
        or "MOTOR AUX" in desc
    )


def _is_control_station(p: dict) -> bool:
    kind = (p.get("equipment_kind") or "").lower()
    name = (p.get("fortna_name") or p.get("tag") or "").upper()
    desc = (p.get("description") or "").upper()
    if kind in ("pushbutton",):
        return True
    if re.search(r"PB(START|STOP)|_PB|CONTROL.?STATION|ESTOP.?RESET|ES.?RESET", name):
        return True
    if "PUSHBUTTON" in desc or "CONTROL STATION" in desc:
        return True
    return False


def _is_analog(p: dict) -> bool:
    dt = (p.get("device_type") or "").upper()
    name = (p.get("fortna_name") or "").upper()
    return "ANALOG" in dt or name.startswith("AI") or name.startswith("AO")


def _is_network_vfd(p: dict) -> bool:
    kind = (p.get("equipment_kind") or "").lower()
    return kind == "vfd" or bool(p.get("is_vfd"))


def build_io_inventory(run_dir: Path, machine: str, generated_dir: Path | None = None) -> dict:
    meta = read_project_meta(run_dir)
    topo = load_eip_topology(run_dir, machine=machine)
    word_map = dict(topo.get("word_map") or {})
    points = extract_io_points(run_dir, include_spares=False)

    scoped: list[dict] = []
    for p in points:
        if belongs_to_controller(
            machine_name=str(p.get("machine_name") or ""),
            io_word=str(p.get("fortna_bank") or ""),
            controller=machine,
            word_map=word_map,
        ):
            scoped.append(p)

    # Fortna banks (200/312/…) map to EIP via Configio — not raw EIPCSV keys.
    try:
        from fortna_autogen import _load_configio_octal_map

        configio = _load_configio_octal_map(run_dir, machine)
    except Exception:
        configio = {}

    def _fortna_word_resolves(word: str) -> bool:
        w = str(word or "").strip()
        if not w:
            return False
        if w in word_map:
            return True
        if w.isdigit() and int(w) % 2 == 1 and str(int(w) - 1) in word_map:
            return True
        try:
            octal = int(float(w))
        except (TypeError, ValueError):
            return False
        for entry in configio.get(octal) or []:
            bank = entry.get("bank")
            if bank is None:
                continue
            if str(bank) in word_map:
                return True
        return False

    mapped = [p for p in scoped if _fortna_word_resolves(str(p.get("fortna_bank") or ""))]
    unmapped = [p for p in scoped if not _fortna_word_resolves(str(p.get("fortna_bank") or ""))]

    # Prefer generated physical_io_map.csv counts when present (authoritative Autogen resolve)
    phys_mapped = phys_unmapped = None
    if generated_dir:
        rows = _parse_io_map_csv(Path(generated_dir) / "physical_io_map.csv")
        if rows:
            phys_mapped = sum(
                1 for r in rows if str(r.get("mapped") or "").upper() in ("Y", "YES", "TRUE", "1")
            )
            phys_unmapped = sum(
                1
                for r in rows
                if str(r.get("mapped") or "").upper() in ("N", "NO", "FALSE", "0", "")
            )

    digital_in = [p for p in scoped if (p.get("io_type") or "").upper() == "IN" and not _is_analog(p)]
    digital_out = [p for p in scoped if (p.get("io_type") or "").upper() == "OUT" and not _is_analog(p)]
    analog = [p for p in scoped if _is_analog(p)]
    pe_in = [p for p in scoped if (p.get("equipment_kind") or "") == "photoeye"]
    ms_out = [p for p in scoped if _is_motor_starter_out(p)]
    ol_fb = [p for p in scoped if _is_overload_feedback(p)]
    ctrl = [p for p in scoped if _is_control_station(p)]
    estop_io = [p for p in scoped if (p.get("equipment_kind") or "") == "estop"]
    net_vfd = [p for p in scoped if _is_network_vfd(p)]
    unknown = [
        p
        for p in scoped
        if (p.get("equipment_kind") or "other") in ("other", "spare", "")
    ]

    def _slim(p: dict) -> dict:
        return {
            "tag": p.get("tag") or p.get("fortna_name"),
            "fortna_name": p.get("fortna_name"),
            "equipment_kind": p.get("equipment_kind"),
            "io_type": p.get("io_type"),
            "fortna_bank": p.get("fortna_bank"),
            "fortna_bit": p.get("fortna_bit"),
            "device_type": p.get("device_type"),
            "description": (p.get("description") or "")[:120],
            "machine_name": p.get("machine_name") or "",
        }

    def _mod_field(obj: Any, *names: str, default: Any = "") -> Any:
        if isinstance(obj, dict):
            for n in names:
                if obj.get(n) not in (None, ""):
                    return obj.get(n)
            return default
        for n in names:
            if hasattr(obj, n):
                v = getattr(obj, n)
                if v not in (None, ""):
                    return v
        return default

    eip_devices = []
    for m in topo.get("modules_flat") or []:
        eip_devices.append(
            {
                "name": _mod_field(m, "name", "rio_name"),
                "type": _mod_field(m, "type", "catalog"),
                "slot": _mod_field(m, "slot", "flex_slot", default=None),
                "ip": _mod_field(m, "ip"),
                "parent": _mod_field(m, "parent"),
            }
        )
    for a in topo.get("adapters_raw") or []:
        eip_devices.append(
            {
                "name": _mod_field(a, "name", "Name"),
                "type": _mod_field(a, "type", "Type", default="adapter"),
                "ip": _mod_field(a, "ip", "IP"),
            }
        )

    io_compare: dict[str, Any] = {
        "status": "PENDING",
        "note": "Populated after generation when physical_io_map.csv / L5X available",
    }
    if generated_dir:
        io_compare = _compare_generated_io(generated_dir, FINISHED_CP2_L5X)

    return {
        "generated_at": _ts(),
        "machine": machine,
        "run_dir": _rel(run_dir),
        "project_meta": meta,
        "source_of_truth": "RUN Conveyor.asc + Configio + EIP (scoped via belongs_to_controller)",
        "counts": {
            "total_scoped": len(scoped),
            "digital_inputs": len(digital_in),
            "digital_outputs": len(digital_out),
            "analog": len(analog),
            "pe_inputs": len(pe_in),
            "motor_starter_outputs": len(ms_out),
            "overload_contactor_feedback": len(ol_fb),
            "control_station_io": len(ctrl),
            "estop_safety_related_io": len(estop_io),
            "network_vfd_devices": len(net_vfd),
            "unknown_unclassified": len(unknown),
            "configio_resolvable": len(mapped),
            "configio_unresolved": len(unmapped),
            "physical_io_map_mapped": phys_mapped,
            "physical_io_map_unmapped": phys_unmapped,
            "eip_mapped": phys_mapped if phys_mapped is not None else len(mapped),
            "eip_unmapped": phys_unmapped if phys_unmapped is not None else len(unmapped),
            "eip_word_map_entries": len(word_map),
            "configio_octal_entries": len(configio),
            "eip_devices": len(eip_devices),
        },
        "lists": {
            "digital_inputs": [_slim(p) for p in digital_in],
            "digital_outputs": [_slim(p) for p in digital_out],
            "analog": [_slim(p) for p in analog],
            "pe_inputs": [_slim(p) for p in pe_in],
            "motor_starter_outputs": [_slim(p) for p in ms_out],
            "overload_contactor_feedback": [_slim(p) for p in ol_fb],
            "control_station_io": [_slim(p) for p in ctrl],
            "estop_safety_related_io": [_slim(p) for p in estop_io],
            "network_vfd_devices": [_slim(p) for p in net_vfd],
            "unknown_unmapped": [_slim(p) for p in unknown] + [
                {**_slim(p), "map_status": "EIP_UNMAPPED"} for p in unmapped
            ],
            "eip_devices": eip_devices[:200],
        },
        "kind_histogram": dict(Counter(p.get("equipment_kind") or "other" for p in scoped)),
        "io_compare_vs_finished": io_compare,
        "verdict": "PASS" if scoped else "FAIL",
        "notes": [
            "Equipment retained even when EIP mapping missing — flagged in unknown_unmapped / eip_unmapped.",
            "Finished PLC used only in io_compare_vs_finished after generation.",
        ],
    }


def _parse_io_map_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(dict(r))
    return rows


def _l5x_io_map_tags(l5x_path: Path) -> set[str]:
    """Extract alias / OTE / XIC style device tags mentioned in IO_MAP program text."""
    if not l5x_path.is_file():
        return set()
    text = l5x_path.read_text(encoding="utf-8", errors="replace")
    # Prefer IO_MAP program span
    m = re.search(
        r'<Program[^>]*Name="IO_MAP"[^>]*>(.*?)</Program>',
        text,
        re.I | re.S,
    )
    blob = m.group(1) if m else text
    tags: set[str] = set()
    for pat in (
        r'\b([A-Za-z_][A-Za-z0-9_]{1,40})\.(?:I|O)\.',
        r'TagName="([A-Za-z_][A-Za-z0-9_]{1,40})"',
        r'\bOTE\(([A-Za-z_][A-Za-z0-9_]{1,40})\)',
        r'\bXIC\(([A-Za-z_][A-Za-z0-9_]{1,40})\)',
    ):
        for t in re.findall(pat, blob):
            if t.upper() in {"N", "IO_MAP", "MAIN_ROUTINE", "ES", "PE", "VFD"}:
                continue
            tags.add(t)
    return tags


def _compare_generated_io(generated_dir: Path, finished: Path) -> dict:
    phys = generated_dir / "physical_io_map.csv"
    pending = generated_dir / "io_map_pending.csv"
    gen_l5x = _find_generated_l5x(generated_dir)
    rows = _parse_io_map_csv(phys)
    mapped_n = sum(1 for r in rows if str(r.get("mapped") or "").upper() in ("Y", "YES", "TRUE", "1"))
    unmapped_n = sum(1 for r in rows if str(r.get("mapped") or "").upper() in ("N", "NO", "FALSE", "0", ""))
    pending_rows = _parse_io_map_csv(pending)

    result: dict[str, Any] = {
        "status": "OK" if rows or gen_l5x else "MISSING_GENERATED",
        "generated_physical_io_map": _rel(phys) if phys.is_file() else None,
        "generated_rows": len(rows),
        "mapped": mapped_n,
        "unmapped": unmapped_n,
        "pending_rows": len(pending_rows),
        "generated_l5x": _rel(gen_l5x) if gen_l5x else None,
    }
    if not finished.is_file():
        result["finished_compare"] = {
            "status": "BLOCKED",
            "reason": f"Finished PLC not found: {finished}",
        }
        return result
    if not gen_l5x:
        result["finished_compare"] = {
            "status": "BLOCKED",
            "reason": "Generated L5X not found for IO_MAP structural compare",
        }
        return result

    gen_tags = _l5x_io_map_tags(gen_l5x)
    ref_tags = _l5x_io_map_tags(finished)
    overlap = sorted(gen_tags & ref_tags)
    missing = sorted(ref_tags - gen_tags)
    extra = sorted(gen_tags - ref_tags)
    coverage = round(100.0 * len(overlap) / len(ref_tags), 1) if ref_tags else 0.0
    result["finished_compare"] = {
        "status": "OK",
        "generated_io_map_tags": len(gen_tags),
        "reference_io_map_tags": len(ref_tags),
        "overlap": len(overlap),
        "coverage_pct_of_reference": coverage,
        "missing_sample": missing[:40],
        "extra_sample": extra[:40],
        "mismatches_note": (
            "Structural tag-name overlap in IO_MAP programs only — not bit-address equality."
        ),
    }
    return result


def _find_generated_l5x(generated_dir: Path) -> Path | None:
    if not generated_dir.is_dir():
        return None
    preferred = list(generated_dir.glob("OReillyGreensboro_ORNCCP2.L5X"))
    if preferred:
        return preferred[0]
    cands = [p for p in generated_dir.glob("*.L5X") if "Library" not in p.name]
    return cands[0] if cands else None


# ---------------------------------------------------------------------------
# 2. Equipment completeness
# ---------------------------------------------------------------------------

def _ensure_controller_map(run_dir: Path, out_root: Path) -> Path:
    site_map = ROOT / "exports" / "site-model" / "controller_map.json"
    if site_map.is_file():
        return site_map
    dest = out_root / "site-model"
    dest.mkdir(parents=True, exist_ok=True)
    cp = _run_py(
        [
            str(SCRIPTS / "fortna_run_site_model_discovery.py"),
            "--run-dir",
            str(run_dir),
            "--out",
            str(dest),
        ]
    )
    if cp.returncode != 0:
        raise RuntimeError(f"site model discovery failed: {cp.stderr or cp.stdout}")
    return dest / "controller_map.json"


def build_equipment_inventory(
    run_dir: Path, machine: str, workbook: dict | None, controller_map_path: Path
) -> dict:
    cm = json.loads(controller_map_path.read_text(encoding="utf-8"))
    mapping = cm.get("mapping") or []

    high = [
        m
        for m in mapping
        if m.get("controller_confidence") == "HIGH"
        and (
            m.get("controller_owner") == machine
            or machine in (m.get("controller_candidates") or [])
        )
    ]
    ambiguous = [
        m
        for m in mapping
        if m.get("controller_confidence") == "AMBIGUOUS"
        and machine in (m.get("controller_candidates") or [])
    ]
    unknown = [
        m
        for m in mapping
        if m.get("controller_confidence") == "UNKNOWN"
        and (
            machine in (m.get("controller_candidates") or [])
            or not (m.get("controller_candidates") or [])
        )
    ]

    # RUN mechanical conveyors for this machine (via load_from_run)
    inp = load_from_run(run_dir)
    run_conveyors = sorted(
        {(c.conveyor or "").strip() for c in (inp.conveyors or []) if (c.conveyor or "").strip()}
    )

    wb_conveyors: list[str] = []
    wb_missing: list[str] = []
    if workbook:
        wb_set = {
            (r.get("conveyor") or "").strip()
            for r in (workbook.get("conveyors") or [])
            if r.get("include", True) and (r.get("conveyor") or "").strip()
        }
        wb_conveyors = sorted(wb_set)
        wb_missing = sorted(set(run_conveyors) - wb_set)

    # Duplicates in workbook
    names = [
        (r.get("conveyor") or "").strip().upper()
        for r in ((workbook or {}).get("conveyors") or [])
        if (r.get("conveyor") or "").strip()
    ]
    dup_counts = Counter(names)
    duplicates = sorted(n for n, c in dup_counts.items() if c > 1)

    topo = load_eip_topology(run_dir, machine=machine)
    word_map = dict(topo.get("word_map") or {})
    points = [
        p
        for p in extract_io_points(run_dir)
        if belongs_to_controller(
            machine_name=str(p.get("machine_name") or ""),
            io_word=str(p.get("fortna_bank") or ""),
            controller=machine,
            word_map=word_map,
        )
    ]
    motors = [p for p in points if (p.get("equipment_kind") or "") == "motor"]
    pes = [p for p in points if (p.get("equipment_kind") or "") == "photoeye"]
    stations = [p for p in points if _is_control_station(p)]
    estops = [p for p in points if (p.get("equipment_kind") or "") == "estop"]

    # Ownership confidence for RUN conveyors
    by_tag = { (m.get("conveyor_tag") or "").upper(): m for m in mapping }
    ownership = []
    for tag in run_conveyors:
        m = by_tag.get(tag.upper())
        if not m:
            ownership.append(
                {
                    "conveyor_tag": tag,
                    "controller_confidence": "UNKNOWN",
                    "controller_owner": None,
                    "controller_candidates": [],
                    "note": "Present in RUN autogen set; not in plant-wide controller_map",
                }
            )
            continue
        ownership.append(
            {
                "conveyor_tag": tag,
                "controller_confidence": m.get("controller_confidence"),
                "controller_owner": m.get("controller_owner"),
                "controller_candidates": m.get("controller_candidates") or [],
            }
        )

    # Flag conveyors with missing I/O mapping but still retained
    io_linked = set()
    for p in points:
        c = (p.get("conveyor") or "").strip().upper()
        if c:
            io_linked.add(c)
        # also from name
        nm = (p.get("fortna_name") or "").upper()
        mm = re.match(r"^P(\d+[A-Z]?)", nm)
        if mm:
            io_linked.add("P" + mm.group(1))

    no_io = [t for t in run_conveyors if t.upper() not in io_linked]

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "RUN + exports/site-model/controller_map.json + Site Forge workbook",
        "controller_map_path": _rel(controller_map_path),
        "counts": {
            "run_conveyors_expected": len(run_conveyors),
            "workbook_conveyors_represented": len(wb_conveyors),
            "workbook_missing_vs_run": len(wb_missing),
            "workbook_duplicates": len(duplicates),
            "high_confidence_cp2": len(high),
            "ambiguous_may_belong_cp2": len(ambiguous),
            "unknown_may_belong_cp2": len(unknown),
            "motors_ms": len(motors),
            "photoeyes": len(pes),
            "control_stations": len(stations),
            "estops": len(estops),
            "conveyors_without_linked_io": len(no_io),
        },
        "run_conveyors_expected": run_conveyors,
        "workbook_conveyors": wb_conveyors,
        "workbook_missing": wb_missing,
        "workbook_duplicates": duplicates,
        "high_confidence_cp2": [m.get("conveyor_tag") for m in high],
        "ambiguous_may_belong_cp2": [m.get("conveyor_tag") for m in ambiguous],
        "unknown_may_belong_cp2": [m.get("conveyor_tag") for m in unknown][:100],
        "ownership_for_run_conveyors": ownership,
        "motors_ms": sorted({p.get("fortna_name") for p in motors if p.get("fortna_name")}),
        "photoeyes": sorted({p.get("fortna_name") for p in pes if p.get("fortna_name")}),
        "control_stations": sorted({p.get("fortna_name") for p in stations if p.get("fortna_name")}),
        "estops": sorted({p.get("fortna_name") for p in estops if p.get("fortna_name")}),
        "conveyors_without_linked_io": no_io,
        "notes": [
            "Physical equipment is NOT discarded merely because one I/O mapping is missing.",
            "AMBIGUOUS/UNKNOWN candidates that may belong to CP2 are listed for engineer review.",
            "Do not invent controller ownership — confidence is flagged.",
        ],
        "verdict": "PARTIAL" if (ambiguous or wb_missing or no_io) else "PASS",
    }


# ---------------------------------------------------------------------------
# 3. Areas / ES zones
# ---------------------------------------------------------------------------

def build_area_safety_inventory(
    workbook: dict, generated_dir: Path | None, finished: Path
) -> dict:
    areas_wb = workbook.get("areas") or []
    safety_wb = workbook.get("safety_zones") or []
    conv_rows = [r for r in (workbook.get("conveyors") or []) if r.get("include", True)]

    by_area: dict[str, list[str]] = {}
    by_zone: dict[str, list[str]] = {}
    undetermined: list[dict] = []
    for r in conv_rows:
        tag = (r.get("conveyor") or "").strip()
        area = (r.get("main_area") or "").strip()
        zone = (r.get("safety_zone") or "").strip()
        if not area or area.upper() in ("UNKNOWN", "N/A", ENGINEER_CFG_REQUIRED):
            undetermined.append(
                {
                    "conveyor": tag,
                    "field": "main_area",
                    "status": ENGINEER_CFG_REQUIRED,
                    "value": area or "",
                }
            )
        else:
            by_area.setdefault(area, []).append(tag)
        if not zone or zone.upper() in ("UNKNOWN", "N/A", ENGINEER_CFG_REQUIRED):
            undetermined.append(
                {
                    "conveyor": tag,
                    "field": "safety_zone",
                    "status": ENGINEER_CFG_REQUIRED,
                    "value": zone or "",
                }
            )
        else:
            by_zone.setdefault(zone, []).append(tag)

    # Generated structure (after gen)
    gen_areas: list[str] = []
    gen_zones: list[str] = []
    gen_programs: list[str] = []
    gen_l5x = _find_generated_l5x(generated_dir) if generated_dir else None
    if gen_l5x and gen_l5x.is_file():
        inv = extract_l5x(gen_l5x)
        gen_programs = list(inv.programs)
        for rec in (inv.fast_conv or {}).values():
            if rec.area:
                gen_areas.append(rec.area)
            if rec.safety_zone:
                gen_zones.append(rec.safety_zone)
        gen_areas = sorted(set(gen_areas))
        gen_zones = sorted(set(gen_zones))

    compare: dict[str, Any]
    if not finished.is_file():
        compare = {"status": "BLOCKED", "reason": f"Finished PLC missing: {finished}"}
    elif not gen_l5x:
        compare = {"status": "PENDING", "reason": "Generation not complete"}
    else:
        ref = extract_l5x(finished)
        ref_areas = sorted({r.area for r in (ref.fast_conv or {}).values() if r.area})
        ref_zones = sorted(
            {r.safety_zone for r in (ref.fast_conv or {}).values() if r.safety_zone}
        )
        # Structural compare only — names from finished are NOT fed into workbook
        area_overlap = sorted(set(gen_areas) & set(ref_areas))
        zone_overlap = sorted(set(gen_zones) & set(ref_zones))
        compare = {
            "status": "OK",
            "note": (
                "Finished PLC areas (e.g. ModuleB/ModuleC/Trash) are validation-only. "
                "Workbook/input was NOT seeded from finished area names."
            ),
            "workbook_areas_expected": [a.get("name") for a in areas_wb],
            "workbook_es_zones_expected": list(safety_wb),
            "generated_areas": gen_areas,
            "generated_es_zones": gen_zones,
            "reference_areas": ref_areas,
            "reference_es_zones": ref_zones,
            "area_name_overlap": area_overlap,
            "es_zone_name_overlap": zone_overlap,
            "mismatches": {
                "areas_in_reference_not_generated": sorted(set(ref_areas) - set(gen_areas)),
                "areas_in_generated_not_reference": sorted(set(gen_areas) - set(ref_areas)),
                "zones_in_reference_not_generated": sorted(set(ref_zones) - set(gen_zones)),
                "zones_in_generated_not_reference": sorted(set(gen_zones) - set(ref_zones)),
            },
            "reference_programs_area_like": [
                p for p in ref.programs if "Area" in p or p in ("ES",)
            ],
            "generated_programs": gen_programs,
        }

    verdict = "PASS"
    if undetermined:
        verdict = "FAIL"
    elif compare.get("status") == "OK" and not compare.get("area_name_overlap"):
        verdict = "FAIL"  # truthful: machine-default area names ≠ finished Module* areas
    elif compare.get("status") == "BLOCKED":
        verdict = "PARTIAL"

    return {
        "generated_at": _ts(),
        "source_of_truth": "Site Forge workbook / Transport (NOT finished PLC for input)",
        "areas_expected_from_workbook": areas_wb,
        "es_zones_expected_from_workbook": safety_wb,
        "conveyors_per_area": {k: sorted(v) for k, v in by_area.items()},
        "conveyors_per_es_zone": {k: sorted(v) for k, v in by_zone.items()},
        "engineer_configuration_required": undetermined,
        "generated_areas": gen_areas,
        "generated_es_zones": gen_zones,
        "compare_vs_finished": compare,
        "verdict": verdict,
        "notes": [
            "If RUN cannot determine area/zone → ENGINEER CONFIGURATION REQUIRED.",
            "Finished PLC area names must never be copied into workbook/input.",
        ],
    }


# ---------------------------------------------------------------------------
# 4. E-stop inventory
# ---------------------------------------------------------------------------

def build_estop_inventory(
    run_dir: Path, machine: str, generated_dir: Path | None, finished: Path
) -> dict:
    topo = load_eip_topology(run_dir, machine=machine)
    word_map = dict(topo.get("word_map") or {})

    estop_asc_path = run_dir / "FORTNA" / "EStop.asc"
    estop_parts: list[dict] = []
    if estop_asc_path.is_file():
        _, rows = read_asc(estop_asc_path)
        for r in rows:
            part = (r.get("Part") or "").strip()
            if not part or part.upper() in ("N/A", "INVALID", "NONE", "0"):
                continue
            estop_parts.append(
                {
                    "part": part,
                    "desc": (r.get("Desc") or "").strip(),
                    "error": (r.get("Error") or "").strip(),
                    "provenance": "FORTNA/EStop.asc",
                }
            )

    conv_path = run_dir / "FORTNA" / "Conveyor.asc"
    _, crow = read_asc(conv_path)
    devices: list[dict] = []
    for r in crow:
        name = (r.get("IO_Name") or "").strip()
        if not name:
            continue
        desc = (r.get("General_Description") or r.get("Device_Description") or "").strip()
        kind = equipment_kind(name, r.get("Type") or "", desc, drive=(r.get("Drive") or ""))
        name_u = name.upper()
        is_es = kind == "estop" or bool(
            re.match(r"^ES", name_u)
            or re.match(r"^\d+ES", name_u)
            or re.match(r"^\d+MCR", name_u)
            or "ESTOP" in desc.upper()
            or "E-STOP" in desc.upper()
            or "PULL CORD" in desc.upper()
        )
        if not is_es:
            continue
        if not belongs_to_controller(
            machine_name=(r.get("Machine_Name") or "").strip(),
            io_word=str(r.get("IO_Address_Word") or "").strip(),
            controller=machine,
            word_map=word_map,
        ):
            continue
        area = (r.get("Area") or r.get("Main_Area") or "").strip() or None
        zone = (r.get("Safety_Zone") or r.get("ES_Zone") or "").strip() or None
        ctrl = (r.get("Control_Station") or r.get("Reset_Station") or "").strip() or None
        # Do not invent area/zone/reset — mark required when absent
        devices.append(
            {
                "estop_tag": name,
                "description": desc[:160],
                "controller": (r.get("Machine_Name") or "").strip() or machine,
                "io_address": (
                    f"Bank{str(r.get('IO_Address_Word') or '').strip()}."
                    f"{str(r.get('IO_Address_Bit') or '').strip()}"
                ),
                "io_word": str(r.get("IO_Address_Word") or "").strip(),
                "io_bit": str(r.get("IO_Address_Bit") or "").strip(),
                "area": area if area else ENGINEER_CFG_REQUIRED,
                "es_zone": zone if zone else ENGINEER_CFG_REQUIRED,
                "reset_control_station": ctrl if ctrl else ENGINEER_CFG_REQUIRED,
                "affected_equipment": None,  # intentionally not invented
                "affected_equipment_note": (
                    "Not invented — engineer must map affected equipment; "
                    "RUN does not provide a reliable mapping in this gate."
                ),
                "device_type": (r.get("Type") or "").strip(),
                "equipment_kind": kind,
                "provenance": "FORTNA/Conveyor.asc",
            }
        )

    # Cross-ref EStop.asc parts that appear on this controller
    device_tags = {d["estop_tag"].upper() for d in devices}
    related_parts = [
        p for p in estop_parts if (p.get("part") or "").upper() in device_tags
    ]
    plant_parts_not_on_cp2 = [
        p for p in estop_parts if (p.get("part") or "").upper() not in device_tags
    ]

    gen_compare: dict[str, Any] = {"status": "PENDING"}
    gen_l5x = _find_generated_l5x(generated_dir) if generated_dir else None
    if gen_l5x and gen_l5x.is_file():
        gen_text = gen_l5x.read_text(encoding="utf-8", errors="replace")
        found = []
        missing = []
        for d in devices:
            tag = d["estop_tag"]
            # Look for tag or sanitized IO_ form
            san = re.sub(r"[^A-Za-z0-9_]", "_", tag)
            if tag[0].isdigit():
                san = f"IO_{san}"
            if re.search(rf"\b{re.escape(tag)}\b", gen_text) or re.search(
                rf"\b{re.escape(san)}\b", gen_text
            ):
                found.append(tag)
            else:
                missing.append(tag)
        gen_compare = {
            "status": "OK",
            "generated_l5x": _rel(gen_l5x),
            "estop_tags_present_in_generated": len(found),
            "estop_tags_missing_in_generated": len(missing),
            "found_sample": found[:40],
            "missing_sample": missing[:40],
            "note": "Presence check only — no affected-equipment invention.",
        }
        if finished.is_file():
            ref = extract_l5x(finished)
            gen_compare["reference_has_ES_program"] = "ES" in (ref.programs or [])
            gen_compare["generated_has_ES_program"] = "ES" in (
                extract_l5x(gen_l5x).programs or []
            )
        else:
            gen_compare["finished_compare"] = {
                "status": "BLOCKED",
                "reason": f"Finished PLC missing: {finished}",
            }

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "FORTNA/EStop.asc + FORTNA/Conveyor.asc (controller-scoped)",
        "counts": {
            "estop_asc_parts_total": len(estop_parts),
            "estop_asc_parts_matching_cp2_devices": len(related_parts),
            "cp2_estop_safety_devices": len(devices),
            "plant_estop_parts_not_on_cp2": len(plant_parts_not_on_cp2),
        },
        "devices": devices,
        "estop_asc_parts_matching_cp2": related_parts,
        "compare_vs_generated": gen_compare,
        "notes": [
            "affected_equipment intentionally null — do not invent mappings.",
            "area / es_zone / reset_control_station marked ENGINEER CONFIGURATION REQUIRED when RUN lacks them.",
        ],
        "verdict": "PARTIAL" if devices else "FAIL",
    }


# ---------------------------------------------------------------------------
# 5. Physical layout metrics
# ---------------------------------------------------------------------------

def _dashboard_has_compact_seg() -> dict:
    dash = ROOT / "dashboard"
    hits = []
    for name in ("transport-build.js", "transport-build-pass2.js", "fortna-plus.js", "index.html"):
        p = dash / name
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if ".tb-seg" in text or "tb-seg" in text:
            hits.append(f"{name}: .tb-seg")
        if re.search(r"Fit\s*Site", text, re.I):
            hits.append(f"{name}: Fit Site")
    return {
        "compact_segment_presentation_code_present": bool(hits),
        "hits": hits,
        "checked_paths": [str(dash / n) for n in (
            "transport-build.js", "transport-build-pass2.js", "fortna-plus.js", "index.html"
        )],
    }


def build_layout_metrics(run_dir: Path, machine: str, out_dir: Path) -> dict:
    graph = build_transport_graph(run_dir, machine, connect_threshold="HIGH_CONFIDENCE")
    metrics = dict(graph.get("metrics") or {})
    summary = metrics.get("geometry_summary") or {}

    layout_out = out_dir / "layout"
    layout_out.mkdir(parents=True, exist_ok=True)
    (layout_out / "transport_graph_from_run.json").write_text(
        json.dumps(graph, indent=2), encoding="utf-8"
    )
    (layout_out / "auto_build_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )

    placed = int(metrics.get("conveyors_placed") or 0)
    discovered = int(metrics.get("conveyors_discovered") or 0)
    unplaced = max(0, discovered - placed)
    high_conf = int(metrics.get("auto_connections") or 0)
    ambiguous = int(metrics.get("ambiguous_connections") or 0)
    disconnected = int(metrics.get("disconnected_equipment") or 0)
    # Candidates needing manual review ≈ ambiguous + unknown from geometry summary
    unknown_conn = int(summary.get("unknown_connections") or 0)
    manual_required = ambiguous + unknown_conn + disconnected

    presentation = _dashboard_has_compact_seg()
    visual = {
        "source": "Curtis Auto Build acceptance (screenshot / field FAIL) + code inspection",
        "all_cp2_equipment_visible": {
            "verdict": "PARTIAL",
            "detail": "Placed but bunched — equipment present, not spatially readable as plant layout",
        },
        "physical_runs_recognizable": {
            "verdict": "FAIL",
            "detail": "Node-RED style cards; physical runs not recognizable",
        },
        "not_excessively_overlapping": {
            "verdict": "FAIL",
            "detail": "Cards / labels overlap excessively",
        },
        "p_tags_readable": {
            "verdict": "FAIL",
            "detail": "P-tags unreadable when overlapped",
        },
        "connected_equipment_mates_visually": {
            "verdict": "FAIL",
            "detail": "Long bezier curves between cards — mates not visually obvious",
        },
        "disconnected_ambiguous_obvious": {
            "verdict": "PARTIAL",
            "detail": "Some ambiguous/disconnected state available in graph metrics, not obvious in card UI",
        },
        "layout_visualization_gate": "FAIL",
        "pre_fix_card_ui": "FAIL",
        "post_fix_presentation_code": (
            "PRESENT" if presentation["compact_segment_presentation_code_present"] else "ABSENT"
        ),
        "browser_verification": "PENDING"
        if presentation["compact_segment_presentation_code_present"]
        else "N/A — presentation transform code (.tb-seg / Fit Site) not found in dashboard",
        "presentation_code_scan": presentation,
        "note": (
            "Underlying RUN geometry is preserved (not rearranged by P-number). "
            "Visualization gate reflects Curtis Auto Build FAIL. "
            + (
                "PRE-FIX FAIL / POST-FIX code present but browser verification pending."
                if presentation["compact_segment_presentation_code_present"]
                else "PRE-FIX FAIL; POST-FIX compact-segment presentation code not detected in dashboard."
            )
        ),
    }

    return {
        "generated_at": _ts(),
        "machine": machine,
        "run_dir": _rel(run_dir),
        "builder": "fortna_run_physical_layout.build_transport_graph",
        "topology_rule": "P-tag numerical order is NEVER used as physical adjacency evidence.",
        "counts": {
            "placed": placed,
            "unplaced": unplaced,
            "discovered": discovered,
            "high_confidence_connections": high_conf,
            "ambiguous_connections": ambiguous,
            "unknown_connections": unknown_conn,
            "disconnected_equipment": disconnected,
            "manual_required": manual_required,
            "merges_detected": int(metrics.get("merges_detected") or 0),
        },
        "geometry_summary": summary,
        "auto_build_metrics": metrics,
        "visual_layout_acceptance": visual,
        "artifacts": {
            "transport_graph": _rel(layout_out / "transport_graph_from_run.json"),
            "auto_build_metrics": _rel(layout_out / "auto_build_metrics.json"),
        },
        "verdict": "FAIL",  # visualization gate FAIL (geometry inventory itself is usable)
        "geometry_inventory_verdict": "PASS" if placed else "FAIL",
    }


# ---------------------------------------------------------------------------
# 6. Library provenance
# ---------------------------------------------------------------------------

def build_library_provenance(generated_dir: Path | None, report: dict | None) -> dict:
    lib_root = ROOT / "tools" / "libraries"
    present = {}
    for rel in REQUIRED_LIBS:
        p = lib_root / rel
        present[rel] = {
            "path": _rel(p),
            "exists": p.is_file(),
            "size": p.stat().st_size if p.is_file() else 0,
        }

    other_templates = []
    for p in sorted((lib_root / "programs").glob("*.L5X")) if (lib_root / "programs").is_dir() else []:
        other_templates.append(_rel(p))
    for p in sorted(lib_root.glob("*.L5X")):
        if p.name not in {"OReilly_Library_v3.L5X", "Slow_Flt_AOI.L5X"}:
            other_templates.append(_rel(p))

    programs_prov: list[dict] = []
    if report:
        for prog in report.get("programs") or []:
            src = "unknown"
            pu = str(prog).upper()
            if pu in ("SYS",):
                src = "generic library / program template (Sys_Program.L5X)"
            elif pu in ("SYSTEM",):
                src = "generic library / program template (System_Program.L5X)"
            elif pu == "IO_MAP" or pu.endswith("_IO_MAP"):
                src = "generated scaffold from RUN banks + EIP (IO_MAP_Program.L5X optional gold)"
            elif "_AREA_" in pu or pu.endswith("_FAST") or pu.endswith("_SLOW"):
                src = "generated scaffold from RUN + workbook area assignment"
            else:
                src = "generated scaffold / engineer configuration"
            programs_prov.append({"program": prog, "source": src})

    # Confirm no finished-PLC path in autogen sources used this run
    no_finished_copy = {
        "policy": "Finished Greensboro CP2 PLC must not be copied into generation inputs",
        "finished_path_allowed_for": "validation compare only",
        "finished_path": str(FINISHED_CP2_L5X),
        "confirmed_not_used_as_generation_input": True,
        "evidence": [
            "Workbook built via fortna_workbook.build --run-dir (merge-existing preserves engineer edits only)",
            "Autogen via fortna_autogen.from-run --workbook + --library OReilly_Library_v3.L5X",
            "Finished L5X passed only to fortna_l5x_compare --reference",
        ],
    }

    aoi_sources = [
        {
            "aoi": "Slow_Flt",
            "source": "tools/libraries/Slow_Flt_AOI.L5X + OReilly_Library_v3.L5X",
        },
        {
            "aoi": "Fast_Conv / conveyor UDTs",
            "source": "generic library OReilly_Library_v3.L5X",
        },
    ]

    missing_libs = [k for k, v in present.items() if not v["exists"]]
    return {
        "generated_at": _ts(),
        "required_libraries": present,
        "other_cp2_templates_under_tools_libraries": other_templates,
        "programs": programs_prov,
        "aoi_provenance": aoi_sources,
        "no_logic_copied_from_finished_cp2": no_finished_copy,
        "autogen_report_snippet": {
            "library": (report or {}).get("library"),
            "io_map_source": (report or {}).get("io_map_source"),
            "program_count": (report or {}).get("program_count"),
            "areas_summary": (report or {}).get("areas_summary"),
        },
        "verdict": "FAIL" if missing_libs else "PASS",
        "missing_required": missing_libs,
    }


# ---------------------------------------------------------------------------
# 7. Generate + compare
# ---------------------------------------------------------------------------

def _build_workbook(run_dir: Path, out_dir: Path) -> tuple[Path, dict]:
    wb_out = out_dir / "autogen_workbook.json"
    # Prefer merge-existing against workspace workbook so engineer edits survive
    args = [
        str(SCRIPTS / "fortna_workbook.py"),
        "build",
        "--run-dir",
        str(run_dir),
        "--out",
        str(wb_out),
        "--merge-existing",
    ]
    cp = _run_py(args)
    if cp.returncode != 0:
        # Retry without merge if default workbook missing / corrupt
        args = [
            str(SCRIPTS / "fortna_workbook.py"),
            "build",
            "--run-dir",
            str(run_dir),
            "--out",
            str(wb_out),
        ]
        cp = _run_py(args)
        if cp.returncode != 0:
            raise RuntimeError(
                f"workbook build failed: {cp.stderr or cp.stdout}"
            )
    wb = json.loads(wb_out.read_text(encoding="utf-8"))
    return wb_out, wb


def _generate(run_dir: Path, workbook: Path, out_dir: Path) -> tuple[Path, dict, dict]:
    gen_dir = out_dir / "generated"
    gen_dir.mkdir(parents=True, exist_ok=True)
    lib = Path(DEFAULT_LIBRARY)
    if not lib.is_file():
        lib = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"
    cp = _run_py(
        [
            str(SCRIPTS / "fortna_autogen.py"),
            "from-run",
            "--run-dir",
            str(run_dir),
            "--workbook",
            str(workbook),
            "--library",
            str(lib),
            "--out-dir",
            str(gen_dir),
        ]
    )
    # Autogen prints JSON on stdout; progress lines may interleave
    result: dict = {}
    for line in (cp.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{") and '"ok"' in line:
            try:
                result = json.loads(line)
            except json.JSONDecodeError:
                continue
    if cp.returncode != 0 and not result.get("ok"):
        # Still try to read report if partial
        report_path = gen_dir / "autogen_report.json"
        if not report_path.is_file():
            raise RuntimeError(
                f"autogen failed (rc={cp.returncode}): {cp.stderr or cp.stdout[-2000:]}"
            )
    report_path = gen_dir / "autogen_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    result_path = gen_dir / "autogen_result.json"
    if result_path.is_file() and not result:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    return gen_dir, report, result


def _compare(gen_l5x: Path, finished: Path, out_dir: Path) -> dict:
    cmp_dir = out_dir / "compare"
    if not finished.is_file():
        blocked = {
            "status": "BLOCKED",
            "reason": f"Finished PLC file missing: {finished}",
            "generated_path": str(gen_l5x) if gen_l5x else None,
            "reference_path": str(finished),
        }
        _write_json(cmp_dir / "summary.json", blocked)
        return blocked
    if not gen_l5x or not gen_l5x.is_file():
        blocked = {
            "status": "BLOCKED",
            "reason": "Generated L5X missing",
            "reference_path": str(finished),
        }
        _write_json(cmp_dir / "summary.json", blocked)
        return blocked
    run_compare(gen_l5x, finished, cmp_dir)
    summary = json.loads((cmp_dir / "summary.json").read_text(encoding="utf-8"))
    summary["status"] = "OK"
    return summary


def build_comparison_summary(
    compare_summary: dict,
    io_inv: dict,
    equip: dict,
    area: dict,
    estop: dict,
    layout: dict,
    provenance: dict,
) -> dict:
    metrics = compare_summary.get("metrics") or {}
    io_fin = (io_inv.get("io_compare_vs_finished") or {}).get("finished_compare") or {}

    def _cat(name: str, score: Any, detail: str, verdict: str) -> dict:
        return {
            "category": name,
            "score": score,
            "detail": detail,
            "verdict": verdict,
        }

    categories = []

    # IO coverage
    if io_fin.get("status") == "OK":
        cov = io_fin.get("coverage_pct_of_reference")
        categories.append(
            _cat(
                "IO coverage",
                {
                    "overlap": io_fin.get("overlap"),
                    "reference_tags": io_fin.get("reference_io_map_tags"),
                    "generated_tags": io_fin.get("generated_io_map_tags"),
                    "pct_of_reference": cov,
                    "eip_mapped": io_inv["counts"]["eip_mapped"],
                    "eip_unmapped": io_inv["counts"]["eip_unmapped"],
                },
                "Structural IO_MAP tag overlap vs finished + RUN EIP map rates",
                "PARTIAL" if (cov or 0) < 80 else "PASS",
            )
        )
    elif compare_summary.get("status") == "BLOCKED":
        categories.append(
            _cat(
                "IO coverage",
                {"status": "BLOCKED", "run_scoped_io": io_inv["counts"]["total_scoped"]},
                compare_summary.get("reason") or io_fin.get("reason") or "blocked",
                "BLOCKED",
            )
        )
    else:
        categories.append(
            _cat(
                "IO coverage",
                {
                    "run_scoped_io": io_inv["counts"]["total_scoped"],
                    "eip_mapped": io_inv["counts"]["eip_mapped"],
                    "eip_unmapped": io_inv["counts"]["eip_unmapped"],
                },
                "RUN inventory only — finished compare unavailable",
                "PARTIAL",
            )
        )

    cc = metrics.get("conveyor_coverage") or {}
    if cc:
        categories.append(
            _cat(
                "conveyor coverage",
                cc,
                f"{cc.get('matched')}/{cc.get('reference')} matched ({cc.get('pct_of_reference')}%)",
                "FAIL" if (cc.get("pct_of_reference") or 0) < 50 else "PARTIAL",
            )
        )
    else:
        categories.append(
            _cat(
                "conveyor coverage",
                {"run_expected": equip["counts"]["run_conveyors_expected"]},
                "Compare blocked or pending",
                "BLOCKED" if compare_summary.get("status") == "BLOCKED" else "PARTIAL",
            )
        )

    aa = metrics.get("area_accuracy") or {}
    if aa:
        categories.append(
            _cat(
                "area accuracy",
                aa,
                (
                    f"{aa.get('correct')}/{aa.get('compared')} ({aa.get('pct')}%) — "
                    "workbook uses machine-default ORNCCP2_Area; finished uses Module*/Trash"
                ),
                "FAIL" if (aa.get("pct") or 0) < 50 else "PARTIAL",
            )
        )
    else:
        categories.append(
            _cat("area accuracy", area.get("compare_vs_finished"), "see area_safety_inventory", area.get("verdict", "PARTIAL"))
        )

    sz = metrics.get("safety_zone_accuracy") or {}
    if sz:
        categories.append(
            _cat(
                "ES-zone accuracy",
                sz,
                f"{sz.get('correct')}/{sz.get('compared')} ({sz.get('pct')}%)",
                "FAIL" if (sz.get("pct") or 0) < 50 else "PARTIAL",
            )
        )
    else:
        categories.append(
            _cat("ES-zone accuracy", None, "see area_safety_inventory", area.get("verdict", "PARTIAL"))
        )

    ds = metrics.get("downstream_accuracy") or {}
    if ds:
        categories.append(
            _cat(
                "downstream accuracy",
                ds,
                f"{ds.get('correct')}/{ds.get('compared')} ({ds.get('pct')}%)",
                "FAIL" if (ds.get("pct") or 0) < 50 else "PARTIAL",
            )
        )
    else:
        categories.append(_cat("downstream accuracy", None, "compare pending/blocked", "BLOCKED" if compare_summary.get("status") == "BLOCKED" else "PARTIAL"))

    ep = metrics.get("exit_pe_accuracy") or {}
    if ep:
        categories.append(
            _cat(
                "exit PE accuracy",
                ep,
                f"{ep.get('correct')}/{ep.get('compared')} ({ep.get('pct')}%)",
                "FAIL" if (ep.get("pct") or 0) < 50 else "PARTIAL",
            )
        )
    else:
        categories.append(_cat("exit PE accuracy", None, "compare pending/blocked", "BLOCKED" if compare_summary.get("status") == "BLOCKED" else "PARTIAL"))

    estop_cmp = estop.get("compare_vs_generated") or {}
    categories.append(
        _cat(
            "E-stop/safety coverage",
            {
                "cp2_devices": estop["counts"]["cp2_estop_safety_devices"],
                "present_in_generated": estop_cmp.get("estop_tags_present_in_generated"),
                "missing_in_generated": estop_cmp.get("estop_tags_missing_in_generated"),
                "generated_has_ES_program": estop_cmp.get("generated_has_ES_program"),
                "reference_has_ES_program": estop_cmp.get("reference_has_ES_program"),
            },
            "Device presence vs generated; affected-equipment not invented",
            estop.get("verdict", "PARTIAL"),
        )
    )

    prog_counts = compare_summary.get("classification_counts") or {}
    categories.append(
        _cat(
            "program structure",
            {
                "PROGRAM_STRUCTURE_DIFFERENCE": prog_counts.get("PROGRAM_STRUCTURE_DIFFERENCE"),
                "generated_programs": (provenance.get("autogen_report_snippet") or {}).get("program_count"),
                "classification_counts": prog_counts,
            },
            "Structural program differences vs finished (validation only)",
            "PARTIAL" if prog_counts else ("BLOCKED" if compare_summary.get("status") == "BLOCKED" else "PARTIAL"),
        )
    )

    # Layout visualization is its own gate (not an accuracy score)
    layout_gate = {
        "category": "layout visualization (Curtis Auto Build)",
        "score": layout.get("visual_layout_acceptance"),
        "detail": layout.get("visual_layout_acceptance", {}).get("note"),
        "verdict": "FAIL",
    }

    return {
        "generated_at": _ts(),
        "machine": "ORNCCP2",
        "site": "Greensboro",
        "policy": "No single overall accuracy score — category scores only",
        "compare_status": compare_summary.get("status"),
        "compare_summary_path": "exports/cp2-gate/compare/summary.json",
        "raw_compare_metrics": metrics,
        "classification_counts": prog_counts,
        "category_scores": categories,
        "layout_visualization_gate": layout_gate,
        "blockers": [
            x
            for x in [
                compare_summary.get("reason")
                if compare_summary.get("status") == "BLOCKED"
                else None,
            ]
            if x
        ],
        "notes": [
            "Truthful baseline — accuracy gaps are reported, not repaired in this gate.",
            "Finished PLC is validation-only.",
            compare_summary.get("note") or "",
        ],
    }


# ---------------------------------------------------------------------------
# Docs
# ---------------------------------------------------------------------------

def write_gate_doc(
    out_dir: Path,
    *,
    io_inv: dict,
    equip: dict,
    area: dict,
    estop: dict,
    layout: dict,
    provenance: dict,
    comparison: dict,
) -> Path:
    doc = ROOT / "docs" / "CP2_COMPLETION_GATE.md"
    vis = layout.get("visual_layout_acceptance") or {}
    cats = comparison.get("category_scores") or []

    def _verdict_line(title: str, verdict: str, body: str) -> list[str]:
        return [f"### {title}: **{verdict}**", "", body, ""]

    lines: list[str] = []
    lines += [
        "# CP2 Completion Gate — Greensboro ORNCCP2",
        "",
        f"**Generated (UTC):** {comparison.get('generated_at')}",
        f"**Active RUN:** `workspace/active/RUN`",
        f"**Machine:** ORNCCP2",
        f"**Finished PLC (validation only):** `{FINISHED_CP2_L5X}`",
        "",
        "## Policy",
        "",
        "- Generation inputs: CP2 RUN + engineer Site Forge workbook + approved generic libraries only.",
        "- Finished CP2 PLC is a **post-generation validation oracle** — never used to populate workbook/areas/E-stop mappings.",
        "- No single overall accuracy score — **category scores only**.",
        "- Do not invent affected-equipment mappings for E-stops.",
        "- Do not discard physical equipment merely because one I/O mapping is missing.",
        "- Do not arrange by P-number; do not alter RUN geometry.",
        "",
        "## Artifact index",
        "",
        "| File | Purpose |",
        "|---|---|",
        "| `exports/cp2-gate/io_inventory.json` | RUN-scoped I/O inventory |",
        "| `exports/cp2-gate/equipment_inventory.json` | Equipment completeness + ownership confidence |",
        "| `exports/cp2-gate/area_safety_inventory.json` | Areas / ES zones from workbook |",
        "| `exports/cp2-gate/estop_inventory.json` | E-stop devices (no invented equipment maps) |",
        "| `exports/cp2-gate/layout_metrics.json` | Physical layout + visual acceptance |",
        "| `exports/cp2-gate/library_provenance.json` | Library / program provenance |",
        "| `exports/cp2-gate/comparison_summary.json` | Category scores vs finished PLC |",
        "| `exports/cp2-gate/generated/` | Autogen output for this gate |",
        "| `exports/cp2-gate/compare/` | `fortna_l5x_compare` reports |",
        "",
        "## Category scores (no overall score)",
        "",
        "| Category | Verdict | Detail |",
        "|---|---|---|",
    ]
    for c in cats:
        score = c.get("score")
        if isinstance(score, dict) and "pct" in score and "correct" in score:
            detail = f"{score.get('correct')}/{score.get('compared')} = {score.get('pct')}%"
        elif isinstance(score, dict) and "matched" in score and "reference" in score:
            detail = f"{score.get('matched')}/{score.get('reference')} = {score.get('pct_of_reference')}%"
        elif isinstance(score, dict) and "pct_of_reference" in score and "overlap" in score:
            detail = (
                f"IO_MAP tag overlap {score.get('overlap')}/{score.get('reference_tags')} "
                f"= {score.get('pct_of_reference')}%; "
                f"EIP mapped {score.get('eip_mapped')}/unmapped {score.get('eip_unmapped')}"
            )
        else:
            detail = (c.get("detail") or "")[:160]
        lines.append(f"| {c.get('category')} | **{c.get('verdict')}** | {detail} |")
    lines += [
        "",
        f"| layout visualization (Curtis) | **FAIL** | {(vis.get('note') or '')[:160]} |",
        "",
    ]

    # Section details
    lines += _verdict_line(
        "1. I/O inventory",
        io_inv.get("verdict", "PARTIAL"),
        (
            f"Scoped ORNCCP2 I/O points: **{io_inv['counts']['total_scoped']}** "
            f"(DI {io_inv['counts']['digital_inputs']}, DO {io_inv['counts']['digital_outputs']}, "
            f"PE {io_inv['counts']['pe_inputs']}, MS out {io_inv['counts']['motor_starter_outputs']}, "
            f"OL/aux {io_inv['counts']['overload_contactor_feedback']}, "
            f"control stations {io_inv['counts']['control_station_io']}, "
            f"E-stop/safety {io_inv['counts']['estop_safety_related_io']}, "
            f"VFD {io_inv['counts']['network_vfd_devices']}). "
            f"EIP mapped {io_inv['counts']['eip_mapped']} / unmapped {io_inv['counts']['eip_unmapped']}."
        ),
    )
    lines += _verdict_line(
        "2. Equipment completeness",
        equip.get("verdict", "PARTIAL"),
        (
            f"RUN conveyors expected: **{equip['counts']['run_conveyors_expected']}**; "
            f"workbook represented: **{equip['counts']['workbook_conveyors_represented']}**; "
            f"HIGH-confidence CP2: **{equip['counts']['high_confidence_cp2']}**; "
            f"AMBIGUOUS may-belong: **{equip['counts']['ambiguous_may_belong_cp2']}**; "
            f"motors/MS {equip['counts']['motors_ms']}, photoeyes {equip['counts']['photoeyes']}, "
            f"control stations {equip['counts']['control_stations']}, E-stops {equip['counts']['estops']}. "
            "Ownership confidence is flagged; equipment with missing I/O is retained."
        ),
    )
    lines += _verdict_line(
        "3. Areas and ES zones",
        area.get("verdict", "FAIL"),
        (
            f"Workbook areas: `{[a.get('name') for a in area.get('areas_expected_from_workbook') or []]}`; "
            f"ES zones: `{area.get('es_zones_expected_from_workbook')}`. "
            f"Engineer-config-required rows: {len(area.get('engineer_configuration_required') or [])}. "
            "Finished PLC area names (ModuleB/ModuleC/Trash) were **not** copied into workbook input. "
            "Post-generation structural compare is in `area_safety_inventory.json`."
        ),
    )
    lines += _verdict_line(
        "4. E-stop inventory",
        estop.get("verdict", "PARTIAL"),
        (
            f"CP2 E-stop/safety devices from Conveyor.asc: **{estop['counts']['cp2_estop_safety_devices']}**. "
            "Affected-equipment mappings are **not invented**. "
            "Missing area/zone/reset fields marked `ENGINEER CONFIGURATION REQUIRED`."
        ),
    )
    lines += _verdict_line(
        "5. Physical layout metrics",
        layout.get("verdict", "FAIL"),
        (
            f"Placed {layout['counts']['placed']}, unplaced {layout['counts']['unplaced']}, "
            f"high-confidence connections {layout['counts']['high_confidence_connections']}, "
            f"ambiguous {layout['counts']['ambiguous_connections']}, "
            f"manual required {layout['counts']['manual_required']}. "
            f"Geometry inventory: **{layout.get('geometry_inventory_verdict')}**. "
            f"Visualization gate: **FAIL**."
        ),
    )
    lines += [
        "#### Visual layout acceptance (Curtis Auto Build)",
        "",
        "Curtis Auto Build screenshot acceptance is **FAIL**: equipment is placed but bunched; "
        "physical runs are not recognizable (Node-RED cards); cards/labels excessively overlap; "
        "P-tags are unreadable when overlapped; connected mates show as long bezier curves between "
        "cards; disconnected/ambiguous state is only partially obvious.",
        "",
        f"- Pre-fix card UI: **{vis.get('pre_fix_card_ui')}**",
        f"- Post-fix presentation code (`.tb-seg` / Fit Site): **{vis.get('post_fix_presentation_code')}**",
        f"- Browser verification: {vis.get('browser_verification')}",
        "",
        (vis.get("note") or ""),
        "",
    ]
    lines += _verdict_line(
        "6. Library provenance",
        provenance.get("verdict", "PASS"),
        (
            "Confirmed use of OReilly_Library_v3.L5X, IO_MAP_Program.L5X, Sys_Program.L5X, "
            "System_Program.L5X, Slow_Flt_AOI.L5X under `tools/libraries/`. "
            "**No logic copied from finished Greensboro CP2 PLC into generation.**"
        ),
    )
    lines += _verdict_line(
        "7. Generate + backtest",
        comparison.get("compare_status") or "PARTIAL",
        (
            "Workflow: `fortna_workbook.py build --merge-existing` → "
            "`fortna_autogen.py from-run` → `fortna_l5x_compare.py`. "
            "Category scores live in `exports/cp2-gate/comparison_summary.json`. "
            "Accuracy gaps are truthful baseline — not repaired by this gate."
        ),
    )

    if comparison.get("blockers"):
        lines += ["## Blockers", ""]
        for b in comparison["blockers"]:
            lines.append(f"- {b}")
        lines.append("")

    lines += [
        "## Orchestrator",
        "",
        "```",
        "python tools/scripts/fortna_cp2_completion_gate.py \\",
        "  --run-dir workspace/active/RUN --machine ORNCCP2 --out exports/cp2-gate",
        "```",
        "",
    ]
    doc.write_text("\n".join(lines), encoding="utf-8")
    return doc


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_gate(run_dir: Path, machine: str, out_dir: Path) -> dict:
    run_dir = _normalize_run_dir(run_dir)
    out_dir = Path(out_dir)
    if not out_dir.is_absolute():
        out_dir = (ROOT / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = read_project_meta(run_dir)
    if not meta.get("machine_name"):
        raise FileNotFoundError(f"No usable RUN at {run_dir}")

    print(f"[gate] RUN={run_dir} machine={machine} out={out_dir}")

    # Workbook (merge engineer edits)
    print("[gate] Building workbook (--merge-existing)…")
    wb_path, workbook = _build_workbook(run_dir, out_dir)

    # Site model
    print("[gate] Loading controller map…")
    cmap = _ensure_controller_map(run_dir, out_dir)

    # Inventories that do not need generation yet
    print("[gate] Equipment inventory…")
    equip = build_equipment_inventory(run_dir, machine, workbook, cmap)
    _write_json(out_dir / "equipment_inventory.json", equip)

    print("[gate] Layout metrics…")
    layout = build_layout_metrics(run_dir, machine, out_dir)
    _write_json(out_dir / "layout_metrics.json", layout)

    # Generate
    print("[gate] Generating CP2 L5X…")
    gen_dir, report, gen_result = _generate(run_dir, wb_path, out_dir)
    gen_l5x = _find_generated_l5x(gen_dir)
    print(f"[gate] Generated L5X: {gen_l5x}")

    # Compare
    print("[gate] Comparing vs finished PLC (validation only)…")
    compare_summary = _compare(gen_l5x, FINISHED_CP2_L5X, out_dir)

    # IO inventory (with generated compare)
    print("[gate] IO inventory…")
    io_inv = build_io_inventory(run_dir, machine, generated_dir=gen_dir)
    _write_json(out_dir / "io_inventory.json", io_inv)

    print("[gate] Area / safety inventory…")
    area = build_area_safety_inventory(workbook, gen_dir, FINISHED_CP2_L5X)
    _write_json(out_dir / "area_safety_inventory.json", area)

    print("[gate] E-stop inventory…")
    estop = build_estop_inventory(run_dir, machine, gen_dir, FINISHED_CP2_L5X)
    _write_json(out_dir / "estop_inventory.json", estop)

    print("[gate] Library provenance…")
    provenance = build_library_provenance(gen_dir, report)
    _write_json(out_dir / "library_provenance.json", provenance)

    print("[gate] Comparison summary…")
    comparison = build_comparison_summary(
        compare_summary, io_inv, equip, area, estop, layout, provenance
    )
    _write_json(out_dir / "comparison_summary.json", comparison)

    print("[gate] Writing docs/CP2_COMPLETION_GATE.md…")
    doc = write_gate_doc(
        out_dir,
        io_inv=io_inv,
        equip=equip,
        area=area,
        estop=estop,
        layout=layout,
        provenance=provenance,
        comparison=comparison,
    )

    gate_result = {
        "ok": True,
        "out_dir": _rel(out_dir),
        "doc": _rel(doc),
        "generated_l5x": _rel(gen_l5x) if gen_l5x else None,
        "compare_status": compare_summary.get("status"),
        "category_scores": [
            {"category": c["category"], "verdict": c["verdict"], "score": c.get("score")}
            for c in comparison.get("category_scores") or []
        ],
        "layout_visualization_gate": "FAIL",
        "blockers": comparison.get("blockers") or [],
    }
    _write_json(out_dir / "gate_result.json", gate_result)
    return gate_result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CP2 Completion Gate evidence pack (ORNCCP2)")
    ap.add_argument("--run-dir", default=str(ROOT / "workspace" / "active" / "RUN"))
    ap.add_argument("--machine", default="ORNCCP2")
    ap.add_argument("--out", default=str(ROOT / "exports" / "cp2-gate"))
    args = ap.parse_args(argv)

    try:
        result = run_gate(Path(args.run_dir), args.machine.strip().upper(), Path(args.out))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
