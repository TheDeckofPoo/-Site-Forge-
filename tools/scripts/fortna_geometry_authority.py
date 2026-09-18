#!/usr/bin/env python3
"""Geometry authority stack for Site Forge Transportation canvas.

Authority (highest wins for *effective* geometry):
  1. ENGINEER_ASSIGNED  — explicit engineer override (never mutates source)
  2. PROVEN_RUN         — Fortna Parts/Conveyor X_cord/Y_cord/... geometry
  3. DERIVED_TOPOLOGY   — topology-derived placement when physical unavailable
  4. FALLBACK_LAYOUT    — deterministic Site Forge layout
  5. UNKNOWN

Rules:
  - Deterministic fallback must NOT silently overwrite PROVEN_RUN.
  - source_geometry / effective_geometry / override_provenance are separate.
  - Schema spelling is X_cord / Y_cord (NOT X_coord / Y_coord).
  - X/Y = infeed/ENTRY end; Angle = flow deg CCW from +X; Length=-1 on CURVE.
  - Normalization may translate/scale the whole system; relative X/Y preserved.
  - Connectivity validates geometry; GEOMETRY_TOPOLOGY_MISMATCH when far apart.
  - No site-specific production branches (acceptance examples are report-only artifacts).
"""
from __future__ import annotations

import copy
from typing import Any

from fortna_physical_geometry import (  # noqa: E402
    CALIBRATION,
    build_equipment_geometry,
    classify_mate,
    dist,
)

# ---------------------------------------------------------------------------
# Authority codes (effective geometry provenance)
# ---------------------------------------------------------------------------
ENGINEER_ASSIGNED = "ENGINEER_ASSIGNED"
PROVEN_RUN = "PROVEN_RUN"
DERIVED_TOPOLOGY = "DERIVED_TOPOLOGY"
FALLBACK_LAYOUT = "FALLBACK_LAYOUT"
UNKNOWN = "UNKNOWN"

AUTHORITY_RANK = {
    ENGINEER_ASSIGNED: 1,
    PROVEN_RUN: 2,
    DERIVED_TOPOLOGY: 3,
    FALLBACK_LAYOUT: 4,
    UNKNOWN: 5,
}

SCHEMA_FIELDS = (
    "X_cord",
    "Y_cord",
    "Length",
    "Width",
    "Angle",
    "Type",
    "Inside_Radius",
)

REQUIRED_RENDER_FIELDS = (
    "source_anchor",
    "render_anchor",
    "body_center",
    "entry_endpoint",
    "exit_endpoint",
    "angle",
    "length",
    "width",
    "geometry_provenance",
)

MISMATCH = "GEOMETRY_TOPOLOGY_MISMATCH"

# Default mate gap threshold for mismatch flag (drawing units)
DEFAULT_MISMATCH_GAP = 1200.0


def _f(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s or s.upper() in {"N/A", "INVALID", "NONE", "~"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _pt(x: float | None, y: float | None) -> dict[str, float] | None:
    if x is None or y is None:
        return None
    return {"x": float(x), "y": float(y)}


def _pt_from(obj: dict | None) -> dict[str, float] | None:
    if not obj:
        return None
    x, y = _f(obj.get("x")), _f(obj.get("y"))
    return _pt(x, y)


def has_usable_run_xy(row: dict[str, Any] | None) -> bool:
    """True when RUN provides usable Fortna X_cord/Y_cord (proven placement)."""
    if not row:
        return False
    x = _f(row.get("X_cord", row.get("x", row.get("sourceX"))))
    y = _f(row.get("Y_cord", row.get("y", row.get("sourceY"))))
    return x is not None and y is not None


def has_usable_run_geometry(row: dict[str, Any] | None) -> bool:
    if not has_usable_run_xy(row):
        return False
    angle = _f((row or {}).get("Angle", (row or {}).get("angle", (row or {}).get("sourceAngle"))))
    return angle is not None


def rank_of(code: str | None) -> int:
    return AUTHORITY_RANK.get(str(code or UNKNOWN).upper(), AUTHORITY_RANK[UNKNOWN])


def higher_authority(a: str, b: str) -> str:
    return a if rank_of(a) <= rank_of(b) else b


def extract_run_source(row: dict[str, Any]) -> dict[str, Any]:
    """Immutable RUN source geometry snapshot (X_cord spelling)."""
    return {
        "X_cord": _f(row.get("X_cord", row.get("x", row.get("sourceX")))),
        "Y_cord": _f(row.get("Y_cord", row.get("y", row.get("sourceY")))),
        "Length": _f(row.get("Length", row.get("length"))),
        "Width": _f(row.get("Width", row.get("width"))),
        "Angle": _f(row.get("Angle", row.get("angle", row.get("sourceAngle")))),
        "Type": str(row.get("Type") or row.get("equipment_type") or row.get("equipmentType") or "").strip(),
        "Inside_Radius": _f(row.get("Inside_Radius", row.get("inside_radius", row.get("insideRadius")))),
        "Infeed_Tangent": _f(row.get("Infeed_Tangent", row.get("infeed_tangent", row.get("infeedTangent")))),
        "Discharge_Tangent": _f(
            row.get("Discharge_Tangent", row.get("discharge_tangent", row.get("dischargeTangent")))
        ),
        "b": _f(row.get("b", row.get("exit_bearing", row.get("exitBearing")))),
        "calibration": CALIBRATION["version"],
        "xy_meaning": CALIBRATION["xy_meaning"],
        "field_spelling": "X_cord/Y_cord",
    }


def _body_from_geom(geom: dict[str, Any]) -> dict[str, Any]:
    entry = _pt_from(geom.get("entry"))
    exit_pt = _pt_from(geom.get("exit"))
    center = _pt_from(geom.get("center"))
    if center is None and entry and exit_pt:
        center = {
            "x": (entry["x"] + exit_pt["x"]) / 2.0,
            "y": (entry["y"] + exit_pt["y"]) / 2.0,
        }
    src = geom.get("source") or {}
    return {
        "entry_endpoint": entry,
        "exit_endpoint": exit_pt,
        "body_center": center,
        "source_anchor": entry,  # infeed = source/render anchor under greensboro-infeed-v1
        "render_anchor": entry,
        "angle": _f(geom.get("angle_in", src.get("Angle"))),
        "length": _f(geom.get("length", src.get("Length"))),
        "width": _f(geom.get("width", src.get("Width"))),
        "kind": geom.get("kind"),
        "path": geom.get("path") or [],
        "confidence": geom.get("confidence"),
    }


def _empty_body() -> dict[str, Any]:
    return {
        "entry_endpoint": None,
        "exit_endpoint": None,
        "body_center": None,
        "source_anchor": None,
        "render_anchor": None,
        "angle": None,
        "length": None,
        "width": None,
        "kind": "unknown",
        "path": [],
        "confidence": "LOW",
    }


def resolve_object_geometry(
    row: dict[str, Any] | None,
    *,
    engineer_override: dict[str, Any] | None = None,
    derived: dict[str, Any] | None = None,
    fallback: dict[str, Any] | None = None,
    mate_entries: list[tuple[float, float]] | None = None,
    tag: str | None = None,
) -> dict[str, Any]:
    """Resolve one conveyor object under the authority stack.

    Returns a record with source_geometry, effective_geometry, override_provenance,
    geometry_provenance, and REQUIRED_RENDER_FIELDS. Engineer override never mutates
    source_geometry.
    """
    row = row or {}
    source = extract_run_source(row)
    source_geom = None
    source_prov = UNKNOWN

    if has_usable_run_geometry(row):
        source_geom = build_equipment_geometry(row, mate_entries=mate_entries)
        if source_geom.get("kind") and source_geom.get("kind") != "unknown":
            source_prov = PROVEN_RUN
        elif has_usable_run_xy(row):
            source_prov = PROVEN_RUN  # XY proven even if length/curve incomplete
        else:
            source_prov = UNKNOWN
    elif has_usable_run_xy(row):
        source_geom = {
            "kind": "point",
            "entry": {"x": source["X_cord"], "y": source["Y_cord"]},
            "exit": None,
            "center": {"x": source["X_cord"], "y": source["Y_cord"]},
            "source": source,
            "confidence": "MEDIUM",
        }
        source_prov = PROVEN_RUN

    # Candidates for effective geometry (lower rank number = higher authority)
    candidates: list[tuple[str, dict[str, Any]]] = []

    if engineer_override:
        ov = copy.deepcopy(engineer_override)
        # Accept either body fields or Conveyor-like row fields
        if ov.get("entry_endpoint") or ov.get("X_cord") is not None or ov.get("x") is not None:
            if ov.get("entry_endpoint") is None and (
                _f(ov.get("X_cord", ov.get("x"))) is not None
            ):
                body = _body_from_geom(build_equipment_geometry(ov, mate_entries=mate_entries))
            else:
                body = {
                    **_empty_body(),
                    "entry_endpoint": _pt_from(ov.get("entry_endpoint") or ov.get("entry")),
                    "exit_endpoint": _pt_from(ov.get("exit_endpoint") or ov.get("exit")),
                    "body_center": _pt_from(ov.get("body_center") or ov.get("center")),
                    "source_anchor": _pt_from(
                        ov.get("source_anchor") or ov.get("entry_endpoint") or ov.get("entry")
                    ),
                    "render_anchor": _pt_from(
                        ov.get("render_anchor") or ov.get("entry_endpoint") or ov.get("entry")
                    ),
                    "angle": _f(ov.get("angle", ov.get("Angle"))),
                    "length": _f(ov.get("length", ov.get("Length"))),
                    "width": _f(ov.get("width", ov.get("Width"))),
                    "kind": ov.get("kind") or "override",
                    "confidence": "ENGINEER",
                }
                if body["body_center"] is None and body["entry_endpoint"] and body["exit_endpoint"]:
                    body["body_center"] = {
                        "x": (body["entry_endpoint"]["x"] + body["exit_endpoint"]["x"]) / 2.0,
                        "y": (body["entry_endpoint"]["y"] + body["exit_endpoint"]["y"]) / 2.0,
                    }
            candidates.append((ENGINEER_ASSIGNED, body))

    if source_geom and source_prov == PROVEN_RUN:
        candidates.append((PROVEN_RUN, _body_from_geom(source_geom)))

    if derived:
        d = copy.deepcopy(derived)
        body = {
            **_empty_body(),
            "entry_endpoint": _pt_from(d.get("entry_endpoint") or d.get("entry")),
            "exit_endpoint": _pt_from(d.get("exit_endpoint") or d.get("exit")),
            "body_center": _pt_from(d.get("body_center") or d.get("center")),
            "source_anchor": _pt_from(d.get("source_anchor") or d.get("entry")),
            "render_anchor": _pt_from(d.get("render_anchor") or d.get("entry")),
            "angle": _f(d.get("angle")),
            "length": _f(d.get("length")),
            "width": _f(d.get("width")),
            "kind": d.get("kind") or "derived",
            "confidence": d.get("confidence") or "MEDIUM",
        }
        candidates.append((DERIVED_TOPOLOGY, body))

    # Fallback only when nothing higher is available — never overwrites PROVEN
    if fallback and not any(p in (ENGINEER_ASSIGNED, PROVEN_RUN) for p, _ in candidates):
        f = copy.deepcopy(fallback)
        body = {
            **_empty_body(),
            "entry_endpoint": _pt_from(f.get("entry_endpoint") or f.get("entry") or {"x": f.get("x"), "y": f.get("y")}),
            "exit_endpoint": _pt_from(f.get("exit_endpoint") or f.get("exit")),
            "body_center": _pt_from(f.get("body_center") or f.get("center") or {"x": f.get("x"), "y": f.get("y")}),
            "source_anchor": _pt_from(f.get("source_anchor") or {"x": f.get("x"), "y": f.get("y")}),
            "render_anchor": _pt_from(f.get("render_anchor") or {"x": f.get("x"), "y": f.get("y")}),
            "angle": _f(f.get("angle", 0.0)),
            "length": _f(f.get("length")),
            "width": _f(f.get("width")),
            "kind": f.get("kind") or "fallback",
            "confidence": "LOW",
        }
        candidates.append((FALLBACK_LAYOUT, body))

    if not candidates:
        candidates.append((UNKNOWN, _empty_body()))

    candidates.sort(key=lambda c: rank_of(c[0]))
    provenance, effective = candidates[0]

    # Guard: if PROVEN exists, FALLBACK must not win (belt-and-suspenders)
    proven_bodies = [b for p, b in candidates if p == PROVEN_RUN]
    if provenance == FALLBACK_LAYOUT and proven_bodies:
        provenance, effective = PROVEN_RUN, proven_bodies[0]

    override_prov = None
    if engineer_override:
        override_prov = {
            "authority": ENGINEER_ASSIGNED,
            "fields": sorted(
                k
                for k in (
                    "X_cord",
                    "Y_cord",
                    "Angle",
                    "Length",
                    "Width",
                    "entry_endpoint",
                    "exit_endpoint",
                    "angle",
                    "length",
                    "width",
                )
                if engineer_override.get(k) is not None
            ),
            "source_geometry_mutated": False,
        }

    record = {
        "tag": tag or str(row.get("IO_Name") or row.get("conveyorTag") or "").strip(),
        "source_geometry": {
            "fields": source,
            "body": _body_from_geom(source_geom) if source_geom else _empty_body(),
            "raw_geom": source_geom,
            "provenance": source_prov,
        },
        "effective_geometry": effective,
        "override_provenance": override_prov,
        "geometry_provenance": provenance,
        # Required per rendered object (flat accessors)
        "source_anchor": (source_geom and _body_from_geom(source_geom).get("source_anchor"))
        or effective.get("source_anchor"),
        "render_anchor": effective.get("render_anchor"),
        "body_center": effective.get("body_center"),
        "entry_endpoint": effective.get("entry_endpoint"),
        "exit_endpoint": effective.get("exit_endpoint"),
        "angle": effective.get("angle"),
        "length": effective.get("length"),
        "width": effective.get("width"),
        "authority_stack": [p for p, _ in candidates],
        "schema_fields": list(SCHEMA_FIELDS),
        "calibration": CALIBRATION["version"],
    }
    return record


def apply_engineer_override(
    record: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    """Return a new record with engineer override applied.

    Does not mutate the original record or its source_geometry.
    """
    src_row = (record.get("source_geometry") or {}).get("fields") or {}
    # Prefer original row-like fields for rebuild
    row = {
        "X_cord": src_row.get("X_cord"),
        "Y_cord": src_row.get("Y_cord"),
        "Length": src_row.get("Length"),
        "Width": src_row.get("Width"),
        "Angle": src_row.get("Angle"),
        "Type": src_row.get("Type"),
        "Inside_Radius": src_row.get("Inside_Radius"),
        "Infeed_Tangent": src_row.get("Infeed_Tangent"),
        "Discharge_Tangent": src_row.get("Discharge_Tangent"),
        "b": src_row.get("b"),
        "IO_Name": record.get("tag"),
    }
    return resolve_object_geometry(
        row,
        engineer_override=override,
        tag=record.get("tag"),
    )


def normalize_system(
    records: list[dict[str, Any]],
    *,
    scale: float = 1.0,
    translate: tuple[float, float] = (0.0, 0.0),
    flip_y: bool = False,
    y_origin: float | None = None,
) -> list[dict[str, Any]]:
    """Uniform viewport normalize — preserves relative spatial relationships.

    Applies the SAME translate/scale/(optional Y flip) to every object's
    effective endpoints. Does not independently auto-layout each conveyor.
    Source geometry fields are left intact; normalized copies live under
    effective_geometry / render_* only.
    """
    if not records:
        return []
    if scale <= 0:
        scale = 1.0
    tx, ty = translate
    out: list[dict[str, Any]] = []

    def xform(pt: dict[str, float] | None) -> dict[str, float] | None:
        if not pt:
            return None
        x = (float(pt["x"]) * scale) + tx
        y = float(pt["y"])
        if flip_y:
            origin = y_origin if y_origin is not None else 0.0
            y = (origin - y) * scale + ty
        else:
            y = y * scale + ty
        return {"x": x, "y": y}

    for rec in records:
        r = copy.deepcopy(rec)
        eff = r.get("effective_geometry") or {}
        for key in (
            "entry_endpoint",
            "exit_endpoint",
            "body_center",
            "source_anchor",
            "render_anchor",
        ):
            eff[key] = xform(eff.get(key))
        # Angle preserved under uniform scale/translate; Y-flip mirrors angle
        ang = _f(eff.get("angle"))
        if ang is not None and flip_y:
            eff["angle"] = (-float(ang)) % 360.0
        if _f(eff.get("length")) is not None:
            eff["length"] = float(eff["length"]) * scale
        if _f(eff.get("width")) is not None:
            eff["width"] = float(eff["width"]) * scale
        r["effective_geometry"] = eff
        r["render_anchor"] = eff.get("render_anchor")
        r["body_center"] = eff.get("body_center")
        r["entry_endpoint"] = eff.get("entry_endpoint")
        r["exit_endpoint"] = eff.get("exit_endpoint")
        r["angle"] = eff.get("angle")
        r["length"] = eff.get("length")
        r["width"] = eff.get("width")
        # source_geometry untouched
        r["normalization"] = {
            "scale": scale,
            "translate": {"x": tx, "y": ty},
            "flip_y": flip_y,
            "relative_preserved": True,
            "source_geometry_mutated": False,
        }
        out.append(r)
    return out


def relative_deltas(
    records: list[dict[str, Any]],
    *,
    use_source: bool = True,
) -> dict[str, dict[str, float]]:
    """tag → delta from first object's anchor (for relative-preservation checks)."""
    pts: list[tuple[str, float, float]] = []
    for r in records:
        tag = str(r.get("tag") or "")
        if use_source:
            body = ((r.get("source_geometry") or {}).get("body") or {})
            pt = body.get("source_anchor") or body.get("entry_endpoint")
        else:
            pt = r.get("render_anchor") or r.get("entry_endpoint")
        if not pt:
            continue
        pts.append((tag, float(pt["x"]), float(pt["y"])))
    if not pts:
        return {}
    x0, y0 = pts[0][1], pts[0][2]
    return {t: {"dx": x - x0, "dy": y - y0} for t, x, y in pts}


def validate_topology_geometry(
    records: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    *,
    gap_threshold: float = DEFAULT_MISMATCH_GAP,
    snap: bool = False,
) -> list[dict[str, Any]]:
    """Validate proven relationships against geometry.

    relationships: [{from, to, kind?}] using conveyor tags.
    Flags GEOMETRY_TOPOLOGY_MISMATCH when exit→entry gap exceeds threshold.
    Does NOT silently snap (snap=False default) — Fortna semantics must prove snapping.
    Mtrchain refs are not assumed to be physical adjacency; pass only proven mates.
    """
    del snap  # explicit: never snap here
    by_tag = {str(r.get("tag") or "").upper(): r for r in records}
    flags: list[dict[str, Any]] = []
    for rel in relationships or []:
        frm = str(rel.get("from") or rel.get("from_conveyor") or "").strip().upper()
        to = str(rel.get("to") or rel.get("to_conveyor") or "").strip().upper()
        if not frm or not to or frm not in by_tag or to not in by_tag:
            continue
        a = by_tag[frm]
        b = by_tag[to]
        exit_pt = a.get("exit_endpoint") or ((a.get("effective_geometry") or {}).get("exit_endpoint"))
        entry_pt = b.get("entry_endpoint") or ((b.get("effective_geometry") or {}).get("entry_endpoint"))
        if not exit_pt or not entry_pt:
            continue
        gap = dist(exit_pt, entry_pt)
        width_ref = _f(a.get("width")) or _f(b.get("width")) or 200.0
        mate = classify_mate(exit_pt, entry_pt, width_ref)
        if gap > gap_threshold or mate in {"AMBIGUOUS", "UNKNOWN"}:
            if gap > gap_threshold:
                flags.append(
                    {
                        "code": MISMATCH,
                        "from": frm,
                        "to": to,
                        "gap": gap,
                        "mate_class": mate,
                        "relationship_kind": rel.get("kind") or rel.get("role") or "unknown",
                        "action": "flag_only",
                        "snapped": False,
                        "note": "Endpoints far apart — do not silently snap",
                    }
                )
    return flags


def display_transform(
    record: dict[str, Any],
    *,
    offset: dict[str, float] | None = None,
) -> dict[str, Any]:
    """ONE authoritative display transform for body / label / hit / context menu.

    offset: presentation-only {dx, dy} — never mutates source_geometry.
    """
    off = offset or {"dx": 0.0, "dy": 0.0}
    dx = float(off.get("dx") or 0.0)
    dy = float(off.get("dy") or 0.0)

    def shift(pt: dict[str, float] | None) -> dict[str, float] | None:
        if not pt:
            return None
        return {"x": float(pt["x"]) + dx, "y": float(pt["y"]) + dy}

    eff = record.get("effective_geometry") or {}
    entry = shift(record.get("entry_endpoint") or eff.get("entry_endpoint"))
    exit_pt = shift(record.get("exit_endpoint") or eff.get("exit_endpoint"))
    center = shift(record.get("body_center") or eff.get("body_center"))
    if center is None and entry and exit_pt:
        center = {"x": (entry["x"] + exit_pt["x"]) / 2.0, "y": (entry["y"] + exit_pt["y"]) / 2.0}
    anchor = shift(record.get("render_anchor") or eff.get("render_anchor") or entry)
    angle = record.get("angle", eff.get("angle"))
    return {
        "body": {
            "entry": entry,
            "exit": exit_pt,
            "center": center,
            "anchor": anchor,
            "angle": angle,
            "length": record.get("length", eff.get("length")),
            "width": record.get("width", eff.get("width")),
        },
        "label": {"x": (center or anchor or {"x": 0, "y": 0})["x"], "y": (center or anchor or {"x": 0, "y": 0})["y"]},
        "hit_target": {
            "center": center or anchor,
            "entry": entry,
            "exit": exit_pt,
            "angle": angle,
        },
        "context_menu_target": {
            "center": center or anchor,
            "entry": entry,
            "exit": exit_pt,
        },
        "selection": {"center": center or anchor},
        "hover": {"center": center or anchor},
        "offset": {"dx": dx, "dy": dy},
        "geometry_provenance": record.get("geometry_provenance"),
        "same_transform": True,
    }


def count_provenance(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = {ENGINEER_ASSIGNED: 0, PROVEN_RUN: 0, DERIVED_TOPOLOGY: 0, FALLBACK_LAYOUT: 0, UNKNOWN: 0}
    for r in records:
        p = str(r.get("geometry_provenance") or UNKNOWN).upper()
        if p not in counts:
            counts[p] = 0
        counts[p] += 1
    return counts


def attach_authority_to_layout_node(node: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Merge authority fields onto a Transport Build node (non-destructive)."""
    n = node
    n["geometry_provenance"] = record.get("geometry_provenance")
    n["source_geometry"] = copy.deepcopy(record.get("source_geometry"))
    n["effective_geometry"] = copy.deepcopy(record.get("effective_geometry"))
    n["override_provenance"] = copy.deepcopy(record.get("override_provenance"))
    n["source_anchor"] = record.get("source_anchor")
    n["render_anchor"] = record.get("render_anchor")
    n["body_center"] = record.get("body_center")
    n["entry_endpoint"] = record.get("entry_endpoint")
    n["exit_endpoint"] = record.get("exit_endpoint")
    # Keep existing provenance.geometry in sync for diagnostics
    prov = dict(n.get("provenance") or {})
    prov["geometry_authority"] = record.get("geometry_provenance")
    prov["geometry"] = (
        "ENGINEER_ASSIGNED"
        if record.get("geometry_provenance") == ENGINEER_ASSIGNED
        else ("IMPORTED" if record.get("geometry_provenance") == PROVEN_RUN else prov.get("geometry") or "UNKNOWN")
    )
    n["provenance"] = prov
    return n


def resolve_rows(
    rows: list[dict[str, Any]],
    *,
    overrides: dict[str, dict[str, Any]] | None = None,
    derived_by_tag: dict[str, dict[str, Any]] | None = None,
    fallback_by_tag: dict[str, dict[str, Any]] | None = None,
    tag_field: str = "IO_Name",
) -> list[dict[str, Any]]:
    """Batch-resolve conveyor rows → authority records."""
    overrides = overrides or {}
    derived_by_tag = derived_by_tag or {}
    fallback_by_tag = fallback_by_tag or {}
    out: list[dict[str, Any]] = []
    for row in rows:
        tag = str(row.get(tag_field) or row.get("conveyorTag") or row.get("IO_Name") or "").strip()
        key = tag.upper()
        out.append(
            resolve_object_geometry(
                row,
                engineer_override=overrides.get(key) or overrides.get(tag),
                derived=derived_by_tag.get(key) or derived_by_tag.get(tag),
                fallback=fallback_by_tag.get(key) or fallback_by_tag.get(tag),
                tag=tag,
            )
        )
    return out
