#!/usr/bin/env python3
"""RUN-only CP2 ownership classification for plant-wide mechanical P-tags.

SOURCE-OF-TRUTH: active RUN only. Never reads finished/reference PLC to invent
ownership or lettered conveyors. Finished PLC conveyor count (57) is a
post-generation validation observation only — not a generation target.

Classes (per mechanical P-tag):
  CP2_CONFIRMED | CP2_CANDIDATE | NOT_CP2 | UNKNOWN

Rules (exact match only — no startswith prefix ownership):
  1. Explicit conveyor Machine_Name → that owner
  2. Exact PE/motor/VFD → P via belongs_to_controller + name association + Mtrchain
  3. Include motors (not only PE/VFD) — fixes the Autogen PE/VFD-only 37 undercount
  4. Only target-machine devices → CP2_CONFIRMED
  5. Target + other exact device owner → CP2_CANDIDATE
  6. Only other controller → NOT_CP2
  7. Else UNKNOWN

Lettered motors (M130A) are device evidence on parent mechanical P130 when
P130A is not itself a RUN mechanical row — they do not invent P130A conveyors.

Usage:
  python tools/scripts/fortna_cp2_ownership.py \\
    --run-dir workspace/active/RUN --machine ORNCCP2 \\
    --out exports/cp2-gate/ownership_classification.json
"""
from __future__ import annotations

import argparse
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

from fortna_asc import CONVEYOR_TYPES, read_asc  # noqa: E402
from fortna_autogen import load_eip_topology  # noqa: E402
from fortna_io_extract import belongs_to_controller, row_machine_matches  # noqa: E402
from fortna_run_geometry_investigate import (  # noqa: E402
    _clean,
    _is_motor_row,
    _is_pe_row,
    _load_mtrchain,
)

MECH_TYPES = {t.upper() for t in CONVEYOR_TYPES} | {"ZEROPRESSURE", "ACCUMULATOR", "MDR"}
BLANK_MACHINE = frozenset({"", "N/A", "INVALID", "NONE", "ALL", "0"})
MOTOR_STATUS_SUFFIX = re.compile(r"(_AUX|_OL|_FLT|_RUN|_OK)$", re.I)
P_TAG_RE = re.compile(r"^P\d{2,4}[A-Z0-9_]*$", re.I)
CLASSES = ("CP2_CONFIRMED", "CP2_CANDIDATE", "NOT_CP2", "UNKNOWN")

# Autogen PE/VFD-only scoped count (historical undercount) — observation baseline.
OLD_AUTOGEN_SCOPED_COUNT = 37
# Finished Greensboro CP2 Fast_Conv count — validation observation only.
FINISHED_PLC_CONVEYOR_COUNT = 57


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_run_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    if not run_dir.is_absolute():
        run_dir = (ROOT / run_dir).resolve()
    if (run_dir / "RUN" / "project.cfg").is_file():
        return run_dir / "RUN"
    return run_dir


def _is_mech_ptag(name: str, typ: str) -> bool:
    return (typ or "").strip().upper() in MECH_TYPES and bool(P_TAG_RE.match(name or ""))


def _extract_p_from_pe(name: str) -> str:
    m = re.match(r"^(?:EZ)?PE[\s\-_]*(\d{2,4}[A-Za-z]?)", name or "", re.I)
    return ("P" + m.group(1).upper()) if m else ""


def _extract_p_from_vfd(name: str) -> str:
    m = re.match(r"^VFD[\s\-_]*(\d{2,4}[A-Za-z]?)", name or "", re.I)
    return ("P" + m.group(1).upper()) if m else ""


def _extract_p_from_motor(name: str) -> str:
    m = re.match(r"^M[\s\-_]*(\d{2,4}[A-Za-z]?)", name or "", re.I)
    return ("P" + m.group(1).upper()) if m else ""


def _motor_assoc_targets(motor_name: str, mech_tags: set[str]) -> list[tuple[str, str]]:
    """Exact motor→P association. Lettered motors may evidence parent P### only."""
    exact = _extract_p_from_motor(motor_name)
    if not exact:
        return []
    if exact in mech_tags:
        return [(exact, "motor_exact_name")]
    parent_m = re.match(r"^(P\d{2,4})[A-Z]$", exact)
    if parent_m and parent_m.group(1) in mech_tags:
        return [(parent_m.group(1), "lettered_motor_parent")]
    return []


def _discover_controllers(rows: list[dict], target: str) -> list[str]:
    found = {target}
    for r in rows:
        mn = _clean(r.get("Machine_Name"))
        if mn and mn.upper() not in BLANK_MACHINE:
            found.add(mn)
    return sorted(found)


def _device_controllers(
    row: dict,
    controllers: list[str],
    word_maps: dict[str, dict],
) -> list[str]:
    mn = _clean(row.get("Machine_Name"))
    iw = str(row.get("IO_Address_Word") or "").strip()
    owners: list[str] = []
    for ctrl in controllers:
        if belongs_to_controller(
            machine_name=mn,
            io_word=iw,
            controller=ctrl,
            word_map=word_maps.get(ctrl) or {},
        ):
            owners.append(ctrl)
    return owners


def classify_ownership(
    run_dir: Path,
    machine: str = "ORNCCP2",
) -> dict[str, Any]:
    """Classify every plant-wide mechanical P-tag. RUN-only — no finished PLC."""
    run_dir = _normalize_run_dir(run_dir)
    machine = (machine or "ORNCCP2").strip().upper()
    conv_path = run_dir / "FORTNA" / "Conveyor.asc"
    if not conv_path.is_file():
        raise FileNotFoundError(f"Missing Conveyor.asc under {run_dir}")

    _h, rows = read_asc(conv_path)
    controllers = _discover_controllers(rows, machine)
    word_maps: dict[str, dict] = {}
    for ctrl in controllers:
        try:
            word_maps[ctrl] = dict(
                load_eip_topology(run_dir, machine=ctrl).get("word_map") or {}
            )
        except Exception:
            word_maps[ctrl] = {}

    mtrchain = _load_mtrchain(run_dir)

    # Plant-wide mechanical inventory (never drop for missing controller)
    mech: dict[str, dict] = {}
    for r in rows:
        name = _clean(r.get("IO_Name"))
        typ = _clean(r.get("Type"))
        if not _is_mech_ptag(name, typ):
            continue
        key = name.upper()
        if key in mech:
            continue
        mech[key] = r
    mech_tags = set(mech)

    evidence: dict[str, dict[str, Any]] = {}
    for tag, r in mech.items():
        mn = _clean(r.get("Machine_Name"))
        evidence[tag] = {
            "conveyor_tag": tag,
            "machine_name_field": mn,
            "pe_links": [],
            "motor_links": [],
            "vfd_links": [],
            "mtrchain_motors": list(mtrchain.get(tag, [])),
            "device_owners": set(),
            "machine_owners": set(),
            "reasons": [],
            "assoc_notes": [],
        }
        if mn and mn.upper() not in BLANK_MACHINE:
            evidence[tag]["machine_owners"].add(mn)
            evidence[tag]["reasons"].append(f"explicit_machine_name:{mn}")

    # Index motors by name → controllers (for Mtrchain resolution)
    motor_owners: dict[str, set[str]] = defaultdict(set)

    for r in rows:
        name = _clean(r.get("IO_Name"))
        if not name:
            continue
        nu = name.upper()
        owners = _device_controllers(r, controllers, word_maps)
        owner_set = set(owners)

        if _is_pe_row(r):
            link = _extract_p_from_pe(name)
            if link in mech_tags:
                evidence[link]["pe_links"].append(name)
                evidence[link]["device_owners"].update(owner_set)
                evidence[link]["reasons"].append(
                    f"pe_exact:{name}→{link} owners={sorted(owner_set)}"
                )
            continue

        if nu.startswith("VFD"):
            link = _extract_p_from_vfd(name)
            if link in mech_tags:
                evidence[link]["vfd_links"].append(name)
                evidence[link]["device_owners"].update(owner_set)
                evidence[link]["reasons"].append(
                    f"vfd_exact:{name}→{link} owners={sorted(owner_set)}"
                )
            continue

        if _is_motor_row(r) and not MOTOR_STATUS_SUFFIX.search(nu):
            motor_owners[nu].update(owner_set)
            for target_tag, mode in _motor_assoc_targets(name, mech_tags):
                evidence[target_tag]["motor_links"].append(name)
                evidence[target_tag]["device_owners"].update(owner_set)
                evidence[target_tag]["reasons"].append(
                    f"{mode}:{name}→{target_tag} owners={sorted(owner_set)}"
                )
                if mode == "lettered_motor_parent":
                    evidence[target_tag]["assoc_notes"].append(
                        f"{name} evidences parent {target_tag} (no lettered mechanical row)"
                    )

    # Mtrchain: motors chained to a conveyor transfer their device owners
    for tag, ev in evidence.items():
        for motor in ev["mtrchain_motors"]:
            mo = motor_owners.get(motor.upper(), set())
            if not mo:
                continue
            ev["device_owners"].update(mo)
            ev["reasons"].append(
                f"mtrchain:{motor}→{tag} owners={sorted(mo)}"
            )

    classifications: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for tag in sorted(evidence):
        ev = evidence[tag]
        machine_owners = {o for o in ev["machine_owners"] if o}
        device_owners = {o for o in ev["device_owners"] if o}

        # Rule 1: explicit conveyor Machine_Name wins when present
        if machine_owners:
            owners = set(machine_owners)
            owner_source = "machine_name"
        else:
            owners = set(device_owners)
            owner_source = "device_association"

        other = sorted(o for o in owners if not row_machine_matches(o, machine))
        has_target = any(row_machine_matches(o, machine) for o in owners)

        if has_target and not other:
            cls = "CP2_CONFIRMED"
        elif has_target and other:
            cls = "CP2_CANDIDATE"
        elif owners and not has_target:
            cls = "NOT_CP2"
        else:
            cls = "UNKNOWN"

        counts[cls] += 1
        reasons = list(ev["reasons"])
        reasons.append(f"owner_source:{owner_source}")
        reasons.append(f"owners:{sorted(owners) or ['(none)']}")
        reasons.append(f"class:{cls}")

        classifications.append(
            {
                "conveyor_tag": tag,
                "class": cls,
                "controller_owners": sorted(owners),
                "match_mode": "EXACT",
                "evidence": {
                    "machine_name_field": ev["machine_name_field"],
                    "pe_links": sorted(set(ev["pe_links"])),
                    "motor_links": sorted(set(ev["motor_links"])),
                    "vfd_links": sorted(set(ev["vfd_links"])),
                    "mtrchain_motors": list(ev["mtrchain_motors"]),
                    "other_controller_conflicts": other,
                    "match_mode": "EXACT",
                    "assoc_notes": list(ev["assoc_notes"]),
                    "reasons": reasons,
                },
            }
        )

    by_class = {
        c: [r["conveyor_tag"] for r in classifications if r["class"] == c]
        for c in CLASSES
    }

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "RUN only (Conveyor.asc + Mtrchain.asc + EIP word map)",
        "policy": {
            "match_mode": "EXACT",
            "no_startswith_prefix_ownership": True,
            "include_motors": True,
            "finished_plc_not_used_for_classification": True,
            "lettered_motors_evidence_parent_only": True,
            "finished_plc_count_is_validation_observation_only": True,
        },
        "counts": {c: int(counts.get(c, 0)) for c in CLASSES},
        "counts_total_mechanical": len(classifications),
        "validation_observation": {
            "old_autogen_pe_vfd_scoped_count": OLD_AUTOGEN_SCOPED_COUNT,
            "cp2_confirmed_count": int(counts.get("CP2_CONFIRMED", 0)),
            "finished_plc_conveyor_count": FINISHED_PLC_CONVEYOR_COUNT,
            "note": (
                "CONFIRMED > old 37 because motors + Mtrchain are included. "
                "CONFIRMED is not forced to equal finished 57: that gap is naming "
                "granularity (finished lettered AOIs like P130A vs RUN parent P130) "
                "plus RUN scoping differences — not a copy target."
            ),
        },
        "by_class": by_class,
        "classifications": classifications,
    }


def write_classification(payload: dict[str, Any], out_path: Path) -> Path:
    out_path = Path(out_path)
    if not out_path.is_absolute():
        out_path = (ROOT / out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def print_summary(payload: dict[str, Any]) -> None:
    counts = payload.get("counts") or {}
    obs = payload.get("validation_observation") or {}
    print("=== CP2 ownership classification (RUN-only, EXACT) ===")
    print(f"machine: {payload.get('machine')}")
    print(f"plant mechanical P-tags: {payload.get('counts_total_mechanical')}")
    for cls in CLASSES:
        print(f"  {cls}: {counts.get(cls, 0)}")
    print(
        "validation observation: "
        f"CONFIRMED={obs.get('cp2_confirmed_count')} vs old Autogen-scoped "
        f"{obs.get('old_autogen_pe_vfd_scoped_count')} vs finished PLC "
        f"{obs.get('finished_plc_conveyor_count')} (observation only, not a target)"
    )
    by = payload.get("by_class") or {}
    for cls in ("CP2_CONFIRMED", "CP2_CANDIDATE"):
        tags = by.get(cls) or []
        sample = ", ".join(tags[:12])
        more = f" …(+{len(tags) - 12})" if len(tags) > 12 else ""
        print(f"  sample {cls}: {sample}{more}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="RUN-only CP2 ownership classification (exact PE/motor/VFD + Mtrchain)"
    )
    ap.add_argument("--run-dir", default=str(ROOT / "workspace" / "active" / "RUN"))
    ap.add_argument("--machine", default="ORNCCP2")
    ap.add_argument(
        "--out",
        default=str(ROOT / "exports" / "cp2-gate" / "ownership_classification.json"),
    )
    args = ap.parse_args(argv)

    payload = classify_ownership(Path(args.run_dir), args.machine.strip().upper())
    out = write_classification(payload, Path(args.out))
    print_summary(payload)
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
