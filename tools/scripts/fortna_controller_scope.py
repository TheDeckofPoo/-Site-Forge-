#!/usr/bin/env python3
"""ControllerScopeModel — LOCAL / EXTERNAL_REFERENCE / OUT_OF_SCOPE / UNRESOLVED.

Builds a machine-scoped mechanical conveyor inventory from RUN ownership
(fortna_cp2_ownership) plus direct geometry / merge / mtrchain neighbor links.

SOURCE-OF-TRUTH: active RUN only. Never invents ownership from P-number ranges
(P1xx=PLC1 style heuristics are forbidden). Never reads finished PLC paths.

Usage:
  python tools/scripts/fortna_controller_scope.py \\
    --run-dir workspace/active/RUN --machine ORNCCP2 \\
    --out exports/plc2-foundation/controller_scope.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import CONVEYOR_TYPES, read_asc  # noqa: E402
from fortna_autogen import load_eip_topology  # noqa: E402
from fortna_cp2_ownership import classify_ownership  # noqa: E402
from fortna_io_extract import (  # noqa: E402
    belongs_to_controller,
    extract_io_points,
    row_machine_matches,
)
from fortna_run_geometry_investigate import (  # noqa: E402
    _clean,
    _dist,
    _f,
    _is_mech_conveyor,
    _load_merge_hints,
    _load_mtrchain,
)

SCOPE_CLASSES = (
    "LOCAL",
    "EXTERNAL_REFERENCE",
    "OUT_OF_SCOPE",
    "UNRESOLVED",
)
MECH_TYPES = {t.upper() for t in CONVEYOR_TYPES} | {"ZEROPRESSURE", "ACCUMULATOR", "MDR"}
P_TAG_RE = re.compile(r"^P\d{2,4}[A-Z0-9_]*$", re.I)
PE_TO_P = re.compile(r"^(?:EZ)?PE[\s\-_]*(\d{2,4}[A-Za-z]?)", re.I)
VFD_TO_P = re.compile(r"^VFD[\s\-_]*(\d{2,4}[A-Za-z]?)", re.I)
MOTOR_TO_P = re.compile(r"^M[\s\-_]*(\d{2,4}[A-Za-z]?)", re.I)
MOTOR_STATUS_SUFFIX = re.compile(r"(_AUX|_OL|_FLT|_RUN|_OK)$", re.I)

# Mate threshold in RUN drawing units (direct abutment only — no remote flood).
_MATE_U = 50.0


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_run_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    if not run_dir.is_absolute():
        run_dir = (ROOT / run_dir).resolve()
    if (run_dir / "RUN" / "project.cfg").is_file():
        return run_dir / "RUN"
    return run_dir


def _p_from_device(name: str) -> str:
    n = name or ""
    for rx in (PE_TO_P, VFD_TO_P, MOTOR_TO_P):
        m = rx.match(n)
        if m:
            return ("P" + m.group(1)).upper()
    return ""


def _quick_anchors(row: dict) -> tuple[dict | None, dict | None]:
    try:
        from fortna_physical_geometry import build_equipment_geometry

        g = build_equipment_geometry(row)
        if g.get("entry") and g.get("exit"):
            return g["entry"], g["exit"]
    except Exception:
        pass
    x, y = _f(row.get("X_cord")), _f(row.get("Y_cord"))
    ang, length = _f(row.get("Angle")), _f(row.get("Length"))
    if x is None or y is None or ang is None or not length or length <= 0:
        return None, None
    rad = ang * math.pi / 180.0
    return (
        {"x": x, "y": y},
        {"x": x + length * math.cos(rad), "y": y + length * math.sin(rad)},
    )


def _slim_io(p: dict) -> dict:
    return {
        "tag": p.get("tag") or p.get("fortna_name"),
        "fortna_name": p.get("fortna_name") or p.get("io_name"),
        "equipment_kind": p.get("equipment_kind"),
        "io_type": p.get("io_type"),
        "fortna_bank": p.get("fortna_bank"),
        "fortna_bit": p.get("fortna_bit"),
        "device_type": p.get("device_type"),
        "machine_name": p.get("machine_name") or "",
    }


def _assoc_ptag(p: dict, mech_tags: set[str]) -> str:
    """Associate an IO point to a mechanical P-tag via name / conveyor field."""
    linked = (p.get("conveyor") or "").strip().upper()
    if linked in mech_tags:
        return linked
    name = (p.get("fortna_name") or p.get("io_name") or p.get("tag") or "").strip()
    if MOTOR_STATUS_SUFFIX.search(name):
        base = MOTOR_STATUS_SUFFIX.sub("", name)
        guess = _p_from_device(base)
    else:
        guess = _p_from_device(name)
    if guess in mech_tags:
        return guess
    parent = re.match(r"^(P\d{2,4})[A-Z]$", guess)
    if parent and parent.group(1) in mech_tags:
        return parent.group(1)
    return ""


def _geometry_neighbor_pairs(
    mech_by_name: dict[str, dict],
    local_tags: set[str],
) -> set[tuple[str, str]]:
    """Direct exit↔entry mates between LOCAL and non-LOCAL only (one hop)."""
    local_ends: list[tuple[str, dict, dict]] = []
    for tag in local_tags:
        row = mech_by_name.get(tag)
        if not row:
            continue
        en, ex = _quick_anchors(row)
        if en and ex:
            local_ends.append((tag, en, ex))

    pairs: set[tuple[str, str]] = set()
    for tag, row in mech_by_name.items():
        if tag in local_tags:
            continue
        en, ex = _quick_anchors(row)
        if not en or not ex:
            continue
        for loc, oen, oex in local_ends:
            if (
                _dist(oex, en) <= _MATE_U
                or _dist(ex, oen) <= _MATE_U
                or _dist(oen, en) <= _MATE_U
                or _dist(oex, ex) <= _MATE_U
            ):
                pairs.add((loc, tag))
                break
    return pairs


def _merge_neighbor_pairs(
    merge_hints: list[dict],
    local_tags: set[str],
    mech_tags: set[str],
) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for hint in merge_hints:
        mentioned = {
            (p or "").strip().upper()
            for p in (hint.get("p_tags_mentioned") or [])
            if (p or "").strip()
        }
        mentioned &= mech_tags
        locals_hit = mentioned & local_tags
        others = mentioned - local_tags
        for loc in locals_hit:
            for other in others:
                pairs.add((loc, other))
    return pairs


def _mtrchain_neighbor_pairs(
    mtrchain: dict[str, list[str]],
    local_tags: set[str],
    mech_tags: set[str],
) -> set[tuple[str, str]]:
    """Conveyors that share a motor chain entry with a LOCAL tag."""
    motor_to_convs: dict[str, set[str]] = defaultdict(set)
    for conv, motors in mtrchain.items():
        cu = (conv or "").strip().upper()
        if cu not in mech_tags:
            continue
        for motor in motors:
            mu = (motor or "").strip().upper()
            if mu:
                motor_to_convs[mu].add(cu)

    pairs: set[tuple[str, str]] = set()
    for _motor, convs in motor_to_convs.items():
        locals_hit = convs & local_tags
        others = convs - local_tags
        for loc in locals_hit:
            for other in others:
                pairs.add((loc, other))
    return pairs


def build_controller_scope(
    run_dir: Path | str,
    machine: str = "ORNCCP2",
) -> dict[str, Any]:
    """Build ControllerScopeModel for a machine (default ORNCCP2)."""
    run_dir = _normalize_run_dir(Path(run_dir))
    machine = (machine or "ORNCCP2").strip().upper()

    ownership = classify_ownership(run_dir, machine)
    by_class = ownership.get("by_class") or {}
    classifications = {
        (c.get("conveyor_tag") or "").upper(): c
        for c in (ownership.get("classifications") or [])
        if c.get("conveyor_tag")
    }

    # LOCAL = CP2_CONFIRMED. Optionally promote CP2_CANDIDATE when device owners
    # are solely the target (classifier normally emits those as CONFIRMED).
    local: set[str] = {t.upper() for t in (by_class.get("CP2_CONFIRMED") or [])}
    for tag in by_class.get("CP2_CANDIDATE") or []:
        rec = classifications.get((tag or "").upper()) or {}
        owners = [o for o in (rec.get("controller_owners") or []) if o]
        others = [o for o in owners if not row_machine_matches(o, machine)]
        if owners and not others:
            local.add(tag.upper())

    not_cp2 = {t.upper() for t in (by_class.get("NOT_CP2") or [])}
    unknown = {t.upper() for t in (by_class.get("UNKNOWN") or [])}
    candidates = {
        t.upper()
        for t in (by_class.get("CP2_CANDIDATE") or [])
        if t.upper() not in local
    }

    conv_path = run_dir / "FORTNA" / "Conveyor.asc"
    _h, rows = read_asc(conv_path)
    mech_by_name: dict[str, dict] = {}
    for r in rows:
        name = _clean(r.get("IO_Name")).upper()
        if not name or not _is_mech_conveyor(r):
            continue
        if name not in mech_by_name:
            mech_by_name[name] = r
    mech_tags = set(mech_by_name)

    try:
        word_map = dict(load_eip_topology(run_dir, machine=machine).get("word_map") or {})
    except Exception:
        word_map = {}

    mtrchain = _load_mtrchain(run_dir)
    merge_hints = _load_merge_hints(run_dir, machine)

    geo_pairs = _geometry_neighbor_pairs(mech_by_name, local)
    merge_pairs = _merge_neighbor_pairs(merge_hints, local, mech_tags)
    mtr_pairs = _mtrchain_neighbor_pairs(mtrchain, local, mech_tags)

    neighbor_of_local: dict[str, list[dict]] = defaultdict(list)
    external: set[str] = set()
    # Direct neighbors eligible for EXTERNAL_REFERENCE (never recurse further).
    neighbor_eligible = not_cp2 | unknown | candidates
    for src, link_type, pairs in (
        ("geometry", "geometry_mate", geo_pairs),
        ("merge", "merge_hint", merge_pairs),
        ("mtrchain", "mtrchain_shared_motor", mtr_pairs),
    ):
        for loc, other in pairs:
            if other in local or other not in neighbor_eligible:
                continue
            external.add(other)
            neighbor_of_local[other].append(
                {
                    "local_tag": loc,
                    "link_type": link_type,
                    "source": src,
                }
            )
    # Contested CP2_CANDIDATE rows remain in-scope as EXTERNAL_REFERENCE even
    # without a geometric mate — they are not OUT_OF_SCOPE remote equipment.
    external |= candidates

    # IO attachment via belongs_to_controller + name association
    io_by_ptag: dict[str, list[dict]] = defaultdict(list)
    related_by_ptag: dict[str, list[dict]] = defaultdict(list)
    try:
        points = extract_io_points(run_dir, include_spares=False)
    except Exception:
        points = []

    for p in points:
        ptag = _assoc_ptag(p, mech_tags)
        if not ptag:
            continue
        on_ctrl = belongs_to_controller(
            machine_name=str(p.get("machine_name") or ""),
            io_word=str(p.get("fortna_bank") or ""),
            controller=machine,
            word_map=word_map,
        )
        slim = _slim_io(p)
        if on_ctrl:
            io_by_ptag[ptag].append(slim)
        else:
            related_by_ptag[ptag].append(slim)

    devices: list[dict[str, Any]] = []
    counts = {c: 0 for c in SCOPE_CLASSES}

    all_tags = sorted(set(classifications) | set(mech_by_name))
    for tag in all_tags:
        own = classifications.get(tag) or {}
        oclass = own.get("class") or (
            "UNKNOWN" if tag in unknown else ("NOT_CP2" if tag in not_cp2 else "UNKNOWN")
        )

        if tag in local:
            scope = "LOCAL"
        elif tag in external or oclass == "CP2_CANDIDATE":
            scope = "EXTERNAL_REFERENCE"
        elif oclass == "UNKNOWN" or tag in unknown:
            scope = "UNRESOLVED"
        else:
            scope = "OUT_OF_SCOPE"

        counts[scope] += 1
        ev = list((own.get("evidence") or {}).get("reasons") or [])
        for link in neighbor_of_local.get(tag) or []:
            ev.append(
                f"external_link:{link['link_type']}:{link['local_tag']}→{tag}"
            )
        if scope == "LOCAL":
            ev.append("scope:LOCAL via CP2_CONFIRMED ownership")
        elif scope == "EXTERNAL_REFERENCE":
            ev.append("scope:EXTERNAL_REFERENCE direct neighbor of LOCAL")

        owned = list(io_by_ptag.get(tag) or [])
        related = list(related_by_ptag.get(tag) or [])
        # For EXTERNAL_REFERENCE, related_io also includes LOCAL-side IO that
        # geometrically/merge-links to this neighbor (already in owned of locals).
        if scope == "EXTERNAL_REFERENCE":
            for link in neighbor_of_local.get(tag) or []:
                loc = link["local_tag"]
                for item in io_by_ptag.get(loc) or []:
                    if item not in related and item not in owned:
                        related.append(item)

        devices.append(
            {
                "conveyor_tag": tag,
                "scope_class": scope,
                "ownership_class": oclass,
                "controller_owners": list(own.get("controller_owners") or []),
                "owned_io": owned,
                "related_io": related,
                "evidence": ev,
                "neighbor_links": list(neighbor_of_local.get(tag) or []),
                "external_reference": scope == "EXTERNAL_REFERENCE",
                "plc_owned": scope == "LOCAL",
            }
        )

    by_scope = {
        c: [d["conveyor_tag"] for d in devices if d["scope_class"] == c]
        for c in SCOPE_CLASSES
    }

    return {
        "generated_at": _ts(),
        "machine": machine,
        "run_dir": str(run_dir),
        "source_of_truth": (
            "RUN only — fortna_cp2_ownership + belongs_to_controller + "
            "geometry/merge/mtrchain direct neighbors"
        ),
        "policy": {
            "local_from": "CP2_CONFIRMED (CP2_CANDIDATE only if sole target device owner)",
            "external_from": "NOT_CP2/UNKNOWN direct upstream/downstream of LOCAL",
            "no_p_number_heuristics": True,
            "no_recursive_remote_expansion": True,
            "finished_plc_not_used": True,
            "neighbor_sources": ["geometry_mate", "merge_hint", "mtrchain_shared_motor"],
        },
        "counts": counts,
        "counts_total_mechanical": len(devices),
        "by_scope": by_scope,
        "ownership_counts": dict(ownership.get("counts") or {}),
        "devices": devices,
    }


def local_tags(scope: dict[str, Any]) -> set[str]:
    """Return the LOCAL conveyor tag set from a scope payload."""
    by = scope.get("by_scope") or {}
    tags = by.get("LOCAL") or []
    if tags:
        return {str(t).upper() for t in tags}
    return {
        str(d.get("conveyor_tag") or "").upper()
        for d in (scope.get("devices") or [])
        if (d.get("scope_class") or "") == "LOCAL" and d.get("conveyor_tag")
    }


def write_controller_scope(scope: dict[str, Any], path: Path | str) -> Path:
    out_path = Path(path)
    if not out_path.is_absolute():
        out_path = (ROOT / out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(scope, indent=2), encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Build ControllerScopeModel (LOCAL / EXTERNAL_REFERENCE / …)"
    )
    ap.add_argument("--run-dir", default=str(ROOT / "workspace" / "active" / "RUN"))
    ap.add_argument("--machine", default="ORNCCP2")
    ap.add_argument(
        "--out",
        default=str(ROOT / "exports" / "plc2-foundation" / "controller_scope.json"),
    )
    args = ap.parse_args(argv)

    scope = build_controller_scope(Path(args.run_dir), args.machine.strip().upper())
    out = write_controller_scope(scope, Path(args.out))
    counts = scope.get("counts") or {}
    print("=== ControllerScopeModel ===")
    print(f"machine: {scope.get('machine')}")
    for cls in SCOPE_CLASSES:
        print(f"  {cls}: {counts.get(cls, 0)}")
    loc = sorted(local_tags(scope))
    sample = ", ".join(loc[:12])
    more = f" …(+{len(loc) - 12})" if len(loc) > 12 else ""
    print(f"  sample LOCAL: {sample}{more}")
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
