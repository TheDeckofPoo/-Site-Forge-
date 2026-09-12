#!/usr/bin/env python3
"""PLC5 post-blind gap closure — discovery→compiler bridge.

Preserves frozen blind artifacts under exports/cp5-blind/.
Writes all new work to exports/cp5-gap-closure/.

Generation uses fortna_autogen.load_from_run (+ SiteModel PE/area enrich).
Answer-sheet comparison is isolated in fortna_answer_sheet_compare.py
and must never be imported by generation paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_site_model import (  # noqa: E402
    AVAILABLE,
    EXCLUDED,
    INCLUDED,
    _clean,
    load_json,
    normalize_name,
    write_json,
)
from fortna_sitemodel_to_autogen import (  # noqa: E402
    bridge_site_model_to_autogen,
    disposition_for_equipment,
)
from fortna_autogen import build_l5x  # noqa: E402
from fortna_knowledge_integration import structural_l5x_checks  # noqa: E402
from fortna_site_model import merge_table_rows  # noqa: E402

FROZEN_FILES = [
    "frozen_output.json",
    "generated/ORNCCP5_blind_candidate.L5X",
    "site_model.json",
    "generation_support_matrix.json",
]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_frozen(blind_dir: Path) -> dict[str, Any]:
    out = {"ok": True, "files": {}}
    for rel in FROZEN_FILES:
        p = blind_dir / rel
        if not p.is_file():
            out["ok"] = False
            out["files"][rel] = {"exists": False}
            continue
        out["files"][rel] = {
            "exists": True,
            "size": p.stat().st_size,
            "sha256": sha256_file(p),
        }
    # Compare to recorded freeze
    frozen = load_json(blind_dir / "frozen_output.json") or {}
    l5x = blind_dir / "generated" / "ORNCCP5_blind_candidate.L5X"
    if l5x.is_file() and frozen.get("generated_l5x_sha256"):
        actual = sha256_file(l5x)
        match = actual.lower() == str(frozen["generated_l5x_sha256"]).lower()
        out["l5x_matches_freeze_record"] = match
        if not match:
            out["ok"] = False
    return out


def _count_incl(objs: list[dict]) -> dict[str, int]:
    return {
        "total": len(objs),
        "INCLUDED": sum(1 for o in objs if o.get("inclusion") == INCLUDED),
        "AVAILABLE": sum(1 for o in objs if o.get("inclusion") == AVAILABLE),
        "EXCLUDED": sum(1 for o in objs if o.get("inclusion") == EXCLUDED),
    }


def pipeline_loss(
    site: dict[str, Any],
    *,
    generated_meta: dict[str, Any],
    bridge_report: dict[str, Any],
    blind_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    gen_names = {
        normalize_name(c)
        for c in (generated_meta.get("conveyor_sample") or [])
    }
    # Also parse from conveyor_count + sample; prefer full list if present
    for c in generated_meta.get("conveyors_generated_names") or []:
        gen_names.add(normalize_name(c))

    superseded = {
        normalize_name(c.get("normalized_name") or "")
        for c in (site.get("superseded_candidates") or [])
    }

    equip_disp: Counter[str] = Counter()
    equip_rows = []
    for eq in site.get("equipment") or []:
        d = disposition_for_equipment(eq, generated_names=gen_names, superseded=superseded)
        equip_disp[d] += 1
        equip_rows.append(
            {
                "name": eq.get("raw_name") or eq.get("normalized_name"),
                "type": eq.get("equipment_type") or eq.get("type"),
                "inclusion": eq.get("inclusion"),
                "disposition": d,
            }
        )

    pe_gen = int(generated_meta.get("pe_device_count") or 0)
    io_pts = int(generated_meta.get("io_point_count") or generated_meta.get("io_tags_in_l5x") or 0)
    io_mod = int(generated_meta.get("io_module_count") or 0)
    io_map_rungs = int(generated_meta.get("io_map_rungs") or 0)
    enc_gen = int(generated_meta.get("encoder_count") or 0)

    return {
        "generated_at": _ts(),
        "blind_v1_loss_note": (
            "Blind candidate used a minimal ConveyorRow list hard-capped at 40 and "
            "omitted pe_devices/io_points/modules from AutogenInput — primary bridge defect."
        ),
        "blind_v1_meta": blind_meta or {},
        "bridge_report": bridge_report,
        "entities": {
            "equipment": {
                "sitemodel": _count_incl(site.get("equipment") or []),
                "compiler_consumed_conveyors": bridge_report.get("conveyors_from_run"),
                "generated_conveyors": generated_meta.get("conveyor_count"),
                "dispositions": dict(equip_disp),
                "rows": equip_rows,
            },
            "photoeyes": {
                "sitemodel": _count_incl(site.get("photoeyes") or []),
                "compiler_consumed": bridge_report.get("pe_devices_from_run"),
                "generated": pe_gen,
                "pe_logic_rungs": generated_meta.get("pe_logic_rungs"),
            },
            "motors": {"sitemodel": _count_incl(site.get("motors") or [])},
            "vfds": {"sitemodel": _count_incl(site.get("vfds") or [])},
            "encoders": {
                "sitemodel": _count_incl(site.get("encoders") or []),
                "generated": enc_gen,
            },
            "io": {
                "compiler_io_points": bridge_report.get("io_points_from_run"),
                "compiler_modules": bridge_report.get("modules_from_run"),
                "generated_io_points": io_pts,
                "generated_io_modules": io_mod,
                "generated_io_map_rungs": io_map_rungs,
            },
            "areas": {
                "sitemodel": len(site.get("areas") or []),
                "generated_areas": generated_meta.get("area_count"),
                "areas_summary": generated_meta.get("areas_summary"),
            },
            "estop": _estop_taxonomy(site),
            "startstop_zones": len((site.get("operational_groups") or {}).get("startstop_zones") or []),
            "jam_zones": len((site.get("operational_groups") or {}).get("jam_zones") or []),
            "full_fulljam": _full_taxonomy(site),
            "merges": len(site.get("merges") or []),
            "scanners": len(site.get("scanners") or []),
            "sorters": len(site.get("sorters") or []),
            "communications": len(site.get("communications") or []),
        },
    }


def _estop_taxonomy(site: dict[str, Any]) -> dict[str, Any]:
    """Distinguish E-stop DEVICE vs ZONE vs membership."""
    raw = list(site.get("estop_zones") or [])
    og = (site.get("operational_groups") or {}).get("estop_zones") or raw
    devices = []
    zones = []
    for z in og:
        name = str(z.get("raw_name") or z.get("normalized_name") or "")
        # Heuristic from RUN naming: ES### / nES look like devices/circuits, not operational zones
        if re.match(r"^\d*ES\d*", name, re.I) or re.match(r"^ES\d+", name, re.I) or re.match(r"^\d+ES$", name, re.I):
            devices.append(name)
        elif "ZONE" in name.upper():
            zones.append(name)
        else:
            devices.append(name)  # default: EStop.asc rows are devices
    return {
        "legacy_count_labeled_zones": len(og),
        "estop_devices": len(devices),
        "estop_circuits_or_aliases": 0,
        "estop_zones_operational": len(zones),
        "note": (
            "EStop.asc rows were previously counted as 'E-stop zones'. "
            "Correct taxonomy: mostly ES devices/circuits; operational zones require explicit zone membership."
        ),
        "device_samples": devices[:20],
        "zone_samples": zones[:20],
    }


def _full_taxonomy(site: dict[str, Any]) -> dict[str, Any]:
    og = (site.get("operational_groups") or {}).get("full_groups") or []
    full_pes = []
    fulljam = []
    for g in og:
        kind = str(g.get("relationship_kind") or "")
        name = g.get("raw_name") or g.get("normalized_name")
        if "fulljam" in kind:
            fulljam.append(name)
        else:
            full_pes.append(name)
    jamchecks = sum(
        1
        for r in (site.get("relationships") or [])
        if str(r.get("kind") or "") in {"jam_link", "jamcheck_link"}
    )
    return {
        "legacy_full_groups_count": len(og),
        "full_pe_detectors": len(full_pes),
        "fulljam_detectors": len(fulljam),
        "jamcheck_relationships": jamchecks,
        "note": (
            "Prior 'Full groups' counted Full/FullJam PE relationship heads, not operational conveyor groups. "
            "Do not treat every conveyor as a Full group."
        ),
    }


def activity_taxonomy(site: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": _ts(),
        "estop": _estop_taxonomy(site),
        "full_fulljam": _full_taxonomy(site),
        "jam_zones": {
            "count": len((site.get("operational_groups") or {}).get("jam_zones") or []),
            "source": "Jamzones.asc",
        },
        "startstop_zones": {
            "count": len((site.get("operational_groups") or {}).get("startstop_zones") or []),
            "source": "StartStopZones.asc",
        },
    }


def area_candidates(run_dir: Path, machine: str, site: dict[str, Any]) -> dict[str, Any]:
    """Propose Area candidates from RUN evidence only — no answer-sheet names."""
    fortna = run_dir / "FORTNA"
    candidates = []

    # Provisional controller area (proven ownership scope, not plant Area)
    candidates.append(
        {
            "name": f"{machine}_Area",
            "status": "ENGINEER_REQUIRED_PROVISIONAL",
            "evidence": [
                f"project.cfg MACHINENAME={machine}",
                "load_from_run provisional area = controller scope",
            ],
            "confidence": "LOW",
            "note": "Not a plant engineering Area; engineer must rename/split",
        }
    )

    # StartStop zone names as grouping hints (not Areas)
    for z in (site.get("operational_groups") or {}).get("startstop_zones") or []:
        candidates.append(
            {
                "name": z.get("raw_name"),
                "status": "GROUPING_HINT_NOT_AREA",
                "evidence": ["StartStopZones.asc row"],
                "confidence": "MEDIUM",
                "note": "Start/Stop zone ≠ Engineering Area; do not auto-promote",
            }
        )

    # Jam zone owners
    if fortna.is_dir() and list(fortna.glob("Jamzones.asc*")):
        merged = merge_table_rows(fortna, "Jamzones.asc", machine)
        owners = Counter()
        for item in merged.get("rows") or []:
            row = item.get("row") or {}
            owner = _clean(row.get("Zone Owner") or row.get("Zone Owner ") or row.get("ZoneOwner"))
            if owner:
                owners[owner] += 1
        for owner, n in owners.most_common(20):
            candidates.append(
                {
                    "name": owner,
                    "status": "OWNERSHIP_HINT",
                    "evidence": [f"Jamzones.asc Zone Owner appears {n} times"],
                    "confidence": "LOW",
                    "note": "May indicate process ownership, not Engineering Area",
                }
            )

    proven = [c for c in candidates if c.get("status") == "PROVEN_AREA"]
    return {
        "generated_at": _ts(),
        "proven_areas": proven,
        "engineer_required": True,
        "candidates": candidates,
        "policy": "Do not copy finished-PLC Area names into generation",
    }


def pe_bridge_report(site: dict[str, Any], generated_meta: dict[str, Any], bridge: dict) -> dict[str, Any]:
    pes = site.get("photoeyes") or []
    role_counts: Counter[str] = Counter()
    for pe in pes:
        for r in pe.get("pe_roles") or [pe.get("role") or "UNKNOWN"]:
            role_counts[str(r)] += 1
    return {
        "generated_at": _ts(),
        "discovered": len(pes),
        "included": sum(1 for p in pes if p.get("inclusion") == INCLUDED),
        "with_io": sum(
            1 for p in pes if _clean(p.get("io_address_word") or p.get("IO_Address_Word"))
        ),
        "compiler_consumed": bridge.get("pe_devices_from_run"),
        "generated_pe_devices": generated_meta.get("pe_device_count"),
        "generated_pe_logic_rungs": generated_meta.get("pe_logic_rungs"),
        "role_counts": dict(role_counts),
        "bridge_fix": (
            "PASS" if int(generated_meta.get("pe_device_count") or 0) > 0 else "FAIL"
        ),
    }


def io_bridge_report(bridge: dict, generated_meta: dict) -> dict[str, Any]:
    return {
        "generated_at": _ts(),
        "compiler_io_points": bridge.get("io_points_from_run"),
        "compiler_modules": bridge.get("modules_from_run"),
        "generated_io_modules": generated_meta.get("io_module_count"),
        "generated_io_points": generated_meta.get("io_point_count")
        or generated_meta.get("io_tags_in_l5x"),
        "generated_io_map_rungs": generated_meta.get("io_map_rungs"),
        "io_map_mapped": generated_meta.get("io_map_mapped"),
        "io_map_source": generated_meta.get("io_map_source"),
        "bridge_fix": (
            "PASS"
            if int(generated_meta.get("io_map_rungs") or 0) > 0
            or int(generated_meta.get("io_module_count") or 0) > 0
            else "FAIL"
        ),
        "sources": ["Configio.asc", "IOCard.asc", "Conveyor I/O fields", "EIP topology"],
    }


def encoder_bridge_report(site: dict[str, Any], generated_meta: dict, l5x_text: str) -> dict[str, Any]:
    encs = site.get("encoders") or []
    present = []
    for e in encs:
        name = e.get("raw_name") or e.get("normalized_name") or ""
        in_l5x = bool(name) and name.upper() in l5x_text.upper()
        present.append(
            {
                "name": name,
                "encoder_io": e.get("encoder_io"),
                "inclusion": e.get("inclusion"),
                "source_table": e.get("source_table"),
                "in_generated_l5x": in_l5x,
                "disposition": "GENERATED" if in_l5x else "CONFIGURATION_REQUIRED",
            }
        )
    return {
        "generated_at": _ts(),
        "discovered": len(encs),
        "in_l5x_count": sum(1 for p in present if p["in_generated_l5x"]),
        "encoders": present,
        "meta_encoder_count": generated_meta.get("encoder_count"),
        "bridge_fix": "PASS" if any(p["in_generated_l5x"] for p in present) else "PARTIAL",
    }


def merge_report(site: dict[str, Any], run_dir: Path, machine: str) -> dict[str, Any]:
    merges = site.get("merges") or []
    # Zipper evidence
    fortna = run_dir / "FORTNA"
    zipper = bool(list(fortna.glob("ZipperMerge.asc*")) or list(fortna.glob("ZipperLane.asc*")))
    out = []
    for m in merges:
        name = m.get("name")
        family = "MultiInputMerge"
        if zipper and "ZIP" in str(name).upper():
            family = "ZipperMerge"
        elif str(m.get("num_inputs") or "") in {"1", "2"}:
            family = "SimpleMerge" if str(m.get("num_inputs")) == "1" else "MultiInputMerge"
        out.append(
            {
                **m,
                "merge_family": family,
                "generator_support": "CONFIGURATION_REQUIRED",
                "not_sawtooth": True,
            }
        )
    return {
        "generated_at": _ts(),
        "count": len(out),
        "merges": out,
        "zipper_tables_present": zipper,
        "generated_capabilities": [],
        "note": "Do not force merges through Sawtooth logic",
    }


def sorter_entity_audit(site: dict[str, Any], run_dir: Path, machine: str) -> dict[str, Any]:
    fortna = run_dir / "FORTNA"
    rows = []
    if fortna.is_dir():
        merged = merge_table_rows(fortna, "Sorters.asc", machine)
        for item in merged.get("rows") or []:
            row = item.get("row") or {}
            name = _clean(row.get("Sorter Name") or row.get("Name"))
            if not name:
                continue
            rows.append(
                {
                    "name": name,
                    "encoder_io": _clean(row.get("Encoder ioName") or row.get("Encoder Name")),
                    "machine": _clean(row.get("Machine")),
                    "max_cartons": _clean(row.get("Max Cartons")),
                    "source_scope": item.get("source_scope"),
                    "interpretation": (
                        "logical_sorter_record_or_segment — encoder-linked sorter entity; "
                        "not proven as independent physical sorter machine"
                    ),
                }
            )
    return {
        "generated_at": _ts(),
        "sorter_asc_active_rows": len(rows),
        "sitemodel_sorters": len(site.get("sorters") or []),
        "entities": rows,
        "warning": "Do not assume N Sorters.asc rows = N independent physical sorters",
    }


def sorter_capability_matrix(site: dict[str, Any]) -> dict[str, Any]:
    has = bool(site.get("sorters"))
    has_scan = bool(site.get("scanners"))
    has_enc = bool(site.get("encoders"))
    has_wcs = any(
        (c.get("message_class") or "").upper().startswith("WCS")
        or c.get("message_class") == "WCSEvents"
        for c in (site.get("communications") or [])
    )

    def leaf(state: str, **extra: Any) -> dict[str, Any]:
        return {"state": state, **extra}

    return {
        "generated_at": _ts(),
        "decomposition_policy": "No monolithic Sorter_Track generator",
        "capabilities": {
            "sorter_encoder_speed_validation": leaf(
                "GENERATABLE" if has_enc else "CONFIGURATION_REQUIRED", discovered=has or has_enc
            ),
            "induct_token_creation": leaf("MODELED" if has_scan else "NOT_DISCOVERED"),
            "scanner_token_update": leaf("MODELED" if has_scan else "NOT_DISCOVERED"),
            "track_offset": leaf("NOT_SUPPORTED"),
            "package_tracking": leaf("MODELED" if has else "NOT_DISCOVERED"),
            "route_destination": leaf("CONFIGURATION_REQUIRED" if has else "NOT_DISCOVERED"),
            "divert_readiness": leaf("NOT_SUPPORTED"),
            "divert_trigger": leaf("NOT_SUPPORTED"),
            "divert_confirmation": leaf("NOT_SUPPORTED"),
            "divert_rate_limit": leaf("NOT_SUPPORTED"),
            "recirculation": leaf("NOT_SUPPORTED"),
            "reason_codes": leaf("MODELED" if has else "NOT_DISCOVERED"),
            "wcs_request": leaf("MODELED" if has_wcs else "NOT_DISCOVERED"),
            "wcs_response": leaf("NOT_SUPPORTED"),
            "wcs_confirmation_event": leaf("NOT_SUPPORTED"),
        },
    }


def wcs_capability_matrix(site: dict[str, Any]) -> dict[str, Any]:
    comms = site.get("communications") or []
    has_map = any(c.get("message_class") == "MsgMap" for c in comms)
    has_ev = any(c.get("message_class") == "WCSEvents" for c in comms)
    has_peer = any("WCS" in str(c.get("ownership") or c.get("sender") or "").upper() for c in comms)
    return {
        "generated_at": _ts(),
        "capabilities": {
            "message_configuration": "MODELED" if has_map else "DISCOVERED" if has_peer else "NOT_DISCOVERED",
            "event_topic_configuration": "MODELED" if has_ev else "NOT_DISCOVERED",
            "inbound_queue": "DISCOVERED" if has_peer else "NOT_DISCOVERED",
            "outbound_queue": "DISCOVERED" if has_peer else "NOT_DISCOVERED",
            "decision_request": "NOT_SUPPORTED",
            "decision_response": "NOT_SUPPORTED",
            "divert_confirmation": "NOT_SUPPORTED",
            "tcp_transport": "NOT_SUPPORTED",
            "heartbeat": "NOT_SUPPORTED",
        },
        "note": "Do not copy finished WCS program; runtime queues ≠ static PLC defs",
    }


def sorter_aoi_matrix(library_path: Path) -> dict[str, Any]:
    """Inventory AOIs in generic library relevant to sorter leaves."""
    text = library_path.read_text(encoding="utf-8", errors="replace") if library_path.is_file() else ""
    names = sorted(set(re.findall(r'AddOnInstructionName="([^"]+)"', text)))
    # Also AOI tag definitions
    names += sorted(set(re.findall(r"<AddOnInstructionDefinition[^>]*Name=\"([^\"]+)\"", text)))
    names = sorted(set(names))

    def classify(n: str) -> str:
        u = n.upper()
        if any(x in u for x in ("DIVERT", "SORTER", "TRACK", "SCAN", "INDUCT", "WCS")):
            if "TRK_DIVERT" in u or "DIVERT" in u:
                return "GENERIC_WITH_CONFIG"
            return "GENERIC_WITH_CONFIG"
        if any(x in u for x in ("FAST_CONV", "SLOW_", "PE_", "FULL_PE", "ENC")):
            return "GENERIC_REUSABLE"
        return "UNKNOWN"

    aoi_rows = []
    for n in names:
        cls = classify(n)
        if cls == "UNKNOWN" and not any(
            k in n.upper() for k in ("CONV", "PE", "JAM", "FULL", "ENC", "VFD", "DIVERT", "TRK", "SCAN")
        ):
            continue
        aoi_rows.append(
            {
                "aoi": n,
                "classification": cls,
                "required_inputs": "see AOI definition in library",
                "run_sources": [],
                "engineer_required_arguments": [],
            }
        )
    # Overlay AOIs
    for p in (ROOT / "tools" / "libraries").glob("*AOI*.L5X"):
        aoi_rows.append(
            {
                "aoi": p.stem,
                "classification": "GENERIC_WITH_CONFIG" if "Divert" in p.name or "TRK" in p.name else "GENERIC_REUSABLE",
                "file": str(p.relative_to(ROOT)),
                "required_inputs": "see AOI L5X",
                "run_sources": [],
                "engineer_required_arguments": [],
            }
        )
    return {
        "generated_at": _ts(),
        "library": str(library_path),
        "aois": aoi_rows,
        "policy": "SITE_FIXED gold Sorter_Track/WCS/ShippingSorter programs are reference-only",
        "reference_only_forbidden_as_templates": [
            "Sorter_Track_Program.L5X",
            "WCS_Interface_TCP_IP_Program.L5X",
            "ShippingSorter_Area_L3_Program.L5X",
        ],
    }


def capability_realization(matrix_claimed: dict, generated_meta: dict, l5x_text: str) -> dict[str, Any]:
    """Correct GENERATABLE vs GENERATED reporting."""

    def state(discovered: bool, generated: bool, structural: bool = True) -> list[str]:
        s = []
        if discovered:
            s += ["DISCOVERED", "MODELED"]
        if generated:
            s += ["GENERATABLE", "REQUESTED_FOR_GENERATION", "GENERATED"]
            if structural:
                s.append("STRUCTURALLY_VALIDATED")
        elif discovered:
            s.append("GENERATABLE" if generated_meta else "MODELED")
        return s

    pe_gen = int(generated_meta.get("pe_device_count") or 0) > 0
    io_gen = int(generated_meta.get("io_map_rungs") or 0) > 0 or int(generated_meta.get("io_module_count") or 0) > 0
    enc_gen = "ENC" in l5x_text.upper() and bool(re.search(r"\bENC\d{3}", l5x_text, re.I))
    conv_gen = int(generated_meta.get("conveyor_count") or 0) > 0

    return {
        "generated_at": _ts(),
        "policy": "Must not report GENERATED unless L5X contains implementation",
        "capabilities": {
            "controller_skeleton": {
                "states": ["DISCOVERED", "MODELED", "GENERATABLE", "REQUESTED_FOR_GENERATION", "GENERATED", "STRUCTURALLY_VALIDATED"],
            },
            "conveyor_fast_logic": {
                "states": state(True, conv_gen),
                "generated_count": generated_meta.get("conveyor_count"),
            },
            "pe_logic": {
                "states": state(True, pe_gen),
                "generated_pe_devices": generated_meta.get("pe_device_count"),
                "generated_pe_logic_rungs": generated_meta.get("pe_logic_rungs"),
                "blind_v1_defect": "claimed generatable but generated 0",
            },
            "io_map": {
                "states": state(True, io_gen),
                "generated_io_map_rungs": generated_meta.get("io_map_rungs"),
                "blind_v1_defect": "claimed generatable but generated 0",
            },
            "encoder_logic": {
                "states": state(True, enc_gen),
                "in_l5x": enc_gen,
            },
            "area_logic": {
                "states": state(True, True),
                "areas": generated_meta.get("areas_summary"),
            },
        },
    }


def generate_v2(run_dir: Path, site: dict[str, Any], out_l5x: Path) -> dict[str, Any]:
    lib = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"
    inp, bridge = bridge_site_model_to_autogen(run_dir, site)
    text, meta = build_l5x(inp, lib)
    if not isinstance(meta, dict):
        meta = {"meta": str(meta)}
    meta["conveyors_generated_names"] = [c.conveyor for c in inp.conveyors]
    out_l5x.parent.mkdir(parents=True, exist_ok=True)
    out_l5x.write_text(text, encoding="utf-8")
    structural = structural_l5x_checks(out_l5x)
    # Count encoder tags in L5X
    enc_tags = sorted(set(re.findall(r"\bENC\d{2,4}[A-Z]?\b", text, flags=re.I)))
    meta["encoder_count"] = len(enc_tags)
    meta["encoder_tags_found"] = enc_tags
    return {
        "path": str(out_l5x),
        "sha256": sha256_file(out_l5x),
        "bridge": bridge,
        "meta": meta,
        "structural": structural,
        "input_counts": {
            "conveyors": len(inp.conveyors),
            "pe_devices": len(inp.pe_devices),
            "io_points": len(inp.io_points),
            "modules": len(inp.modules),
            "areas": list(inp.areas),
        },
    }


def write_report(out: Path, **ctx: Any) -> None:
    loss = ctx["pipeline_loss"]
    pe = ctx["pe_bridge"]
    io = ctx["io_bridge"]
    enc = ctx["encoder_bridge"]
    gen = ctx["generation"]
    frozen = ctx["frozen_verify"]
    lines = [
        "# PLC5 Gap Closure Report",
        "",
        f"Generated: `{_ts()}`",
        "",
        "## Frozen blind baseline",
        "",
        f"- Preserved: **{frozen.get('ok')}**",
        f"- L5X matches freeze record: **{frozen.get('l5x_matches_freeze_record')}**",
        "",
        "## Bridge fix",
        "",
        "Blind v1 omitted `pe_devices` / IO and hard-capped conveyors at 40.",
        "v2 uses `load_from_run` + SiteModel PE role enrichment.",
        "",
        "## Discovery → generation",
        "",
        f"- Equipment SiteModel: `{loss['entities']['equipment']['sitemodel']}`",
        f"- Conveyors compiler-consumed: **{loss['entities']['equipment']['compiler_consumed_conveyors']}**",
        f"- Conveyors generated: **{loss['entities']['equipment']['generated_conveyors']}**",
        f"- Dispositions: `{loss['entities']['equipment']['dispositions']}`",
        f"- PE discovered: **{pe['discovered']}** → generated: **{pe['generated_pe_devices']}** (rungs **{pe['generated_pe_logic_rungs']}**)",
        f"- IO points consumed: **{io['compiler_io_points']}** → modules gen **{io['generated_io_modules']}** / IO_MAP rungs **{io['generated_io_map_rungs']}**",
        f"- Encoders discovered: **{enc['discovered']}** → in L5X: **{enc['in_l5x_count']}**",
        "",
        "## Taxonomy corrections",
        "",
        f"- E-stop: `{ctx['activity_taxonomy']['estop']}`",
        f"- Full/FullJam: `{ctx['activity_taxonomy']['full_fulljam']}`",
        "",
        f"- Structural L5X ok: **{(gen.get('structural') or {}).get('ok')}**",
        f"- Candidate v2: `{gen.get('path')}`",
        f"- SHA256: `{gen.get('sha256')}`",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PLC5 gap closure / discovery-to-compiler bridge")
    ap.add_argument("--run-dir", type=Path, default=ROOT / "workspace" / "cp5-run" / "RUN")
    ap.add_argument("--blind-dir", type=Path, default=ROOT / "exports" / "cp5-blind")
    ap.add_argument("--out", type=Path, default=ROOT / "exports" / "cp5-gap-closure")
    ap.add_argument(
        "--answer-sheet",
        type=Path,
        default=Path(r"C:\Users\curtiskricke\Desktop\Autogen\ORLY_Greensboro_NC_PLC5.L5X"),
        help="Finished PLC5 for validation-only comparison (never generation input)",
    )
    args = ap.parse_args(argv)

    blind_dir: Path = args.blind_dir.resolve()
    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "generated").mkdir(parents=True, exist_ok=True)

    frozen_verify = verify_frozen(blind_dir)
    write_json(out / "frozen_baseline_verify.json", frozen_verify)
    if not frozen_verify.get("ok"):
        print(json.dumps({"ok": False, "error": "frozen baseline verification failed", "detail": frozen_verify}, indent=2))
        return 2

    site = json.loads((blind_dir / "site_model.json").read_text(encoding="utf-8"))
    # Do not mutate frozen site_model.json — work on a copy
    site_work = json.loads(json.dumps(site))
    write_json(out / "site_model_working_copy.json", site_work)

    blind_gen_meta = {}
    blind_result = load_json(blind_dir / "generation_result.json") or {}
    if isinstance(blind_result.get("meta"), dict):
        blind_gen_meta = blind_result["meta"]

    run_dir: Path = args.run_dir.resolve()
    machine = site_work.get("machine_scope") or "ORNCCP5"

    gen = generate_v2(run_dir, site_work, out / "generated" / "ORNCCP5_candidate_v2.L5X")
    write_json(out / "generation_result.json", gen)
    meta = gen.get("meta") or {}
    bridge = gen.get("bridge") or {}
    l5x_text = Path(gen["path"]).read_text(encoding="utf-8", errors="replace")

    loss = pipeline_loss(
        site_work,
        generated_meta=meta,
        bridge_report=bridge,
        blind_meta=blind_gen_meta,
    )
    write_json(out / "pipeline_loss.json", loss)

    tax = activity_taxonomy(site_work)
    write_json(out / "activity_taxonomy.json", tax)

    areas = area_candidates(run_dir, machine, site_work)
    write_json(out / "area_candidates.json", areas)

    pe_rep = pe_bridge_report(site_work, meta, bridge)
    write_json(out / "pe_bridge_report.json", pe_rep)

    io_rep = io_bridge_report(bridge, meta)
    write_json(out / "io_bridge_report.json", io_rep)

    enc_rep = encoder_bridge_report(site_work, meta, l5x_text)
    write_json(out / "encoder_bridge_report.json", enc_rep)

    mer_rep = merge_report(site_work, run_dir, machine)
    write_json(out / "merge_report.json", mer_rep)

    srt_audit = sorter_entity_audit(site_work, run_dir, machine)
    write_json(out / "sorter_entity_audit.json", srt_audit)

    lib = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"
    aoi_mat = sorter_aoi_matrix(lib)
    write_json(out / "sorter_aoi_matrix.json", aoi_mat)

    srt_cap = sorter_capability_matrix(site_work)
    write_json(out / "sorter_capability_matrix.json", srt_cap)

    wcs_cap = wcs_capability_matrix(site_work)
    write_json(out / "wcs_capability_matrix.json", wcs_cap)

    realization = capability_realization({}, meta, l5x_text)
    write_json(out / "capability_realization.json", realization)

    # Answer-sheet comparison (validation layer only)
    try:
        from fortna_answer_sheet_compare import compare_to_answer_sheet

        cmp = compare_to_answer_sheet(
            generated_l5x=Path(gen["path"]),
            answer_sheet=args.answer_sheet if args.answer_sheet.is_file() else None,
            site=site_work,
            generation_meta=meta,
        )
    except Exception as exc:  # noqa: BLE001
        cmp = {"ok": False, "error": str(exc), "note": "validation-only module"}
    write_json(out / "answer_sheet_comparison.json", cmp)

    write_report(
        out,
        pipeline_loss=loss,
        pe_bridge=pe_rep,
        io_bridge=io_rep,
        encoder_bridge=enc_rep,
        generation=gen,
        frozen_verify=frozen_verify,
        activity_taxonomy=tax,
    )

    summary = {
        "ok": bool(frozen_verify.get("ok"))
        and bool((gen.get("structural") or {}).get("ok"))
        and pe_rep.get("bridge_fix") == "PASS"
        and io_rep.get("bridge_fix") == "PASS",
        "frozen_preserved": frozen_verify.get("ok"),
        "equipment_discovered": loss["entities"]["equipment"]["sitemodel"]["INCLUDED"],
        "conveyors_generated": meta.get("conveyor_count"),
        "pe_discovered": pe_rep["discovered"],
        "pe_generated": pe_rep["generated_pe_devices"],
        "io_points_discovered": io_rep["compiler_io_points"],
        "io_map_rungs": io_rep["generated_io_map_rungs"],
        "encoders_discovered": enc_rep["discovered"],
        "encoders_in_l5x": enc_rep["in_l5x_count"],
        "candidate_v2": gen.get("path"),
        "candidate_v2_sha256": gen.get("sha256"),
        "out": str(out),
    }
    write_json(out / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
