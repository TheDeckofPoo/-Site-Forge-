#!/usr/bin/env python3
"""Engineer Area workflow ops on SiteModel (Curtis request).

Areas are renameable engineering groupings for equipment / Autogen Main_Area.
Jam / EStop / StartStop zones are separate — rename_area never renames them.

L5X snippets are model-regenerated from library Main_Area templates using the
effective area name (same approach as fortna_autogen), never by post-hoc
string-replace of a finished PLC export.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fortna_site_model import (
    INCLUDED,
    PROV_ENGINEER,
    PROV_RUN_EXPLICIT,
    PROV_RUN_DERIVED_HIGH,
    SCOPE_ENGINEER,
    SiteModel,
    canonical_id,
    make_object,
    normalize_name,
)

# Relationship kinds that may pull attached devices when move_attached=True.
# Tag-number similarity is NEVER used.
ATTACHED_REL_KINDS = frozenset(
    {
        "motor_link",
        "vfd_link",
        "pe_assignment",
        "encoder_link",
        "motor_to_conveyor",
        "vfd_to_conveyor",
        "pe_to_conveyor",
        "encoder_to_conveyor",
    }
)

_HIGH_PROVENANCE = frozenset(
    {
        PROV_RUN_EXPLICIT,
        PROV_RUN_DERIVED_HIGH,
        PROV_ENGINEER,
        "RUN_EXPLICIT",
        "ENGINEER_CONFIGURED",
        "HIGH",
    }
)
_HIGH_CONFIDENCE = frozenset({"HIGH", "high", "1.0", "1", 1, 1.0})

def _area_matches(obj: dict[str, Any], area_id: str) -> bool:
    want = normalize_name(area_id)
    if not want:
        return False
    candidates = (
        obj.get("area_id"),
        obj.get("raw_name"),
        obj.get("normalized_name"),
        obj.get("name"),
        obj.get("canonical_id"),
    )
    for c in candidates:
        if not c:
            continue
        s = str(c)
        if normalize_name(s) == want:
            return True
        if normalize_name(s.replace("area:", "")) == want:
            return True
    return False


def _find_area(model: SiteModel, area_id: str) -> dict[str, Any] | None:
    for a in model.areas:
        if _area_matches(a, area_id):
            return a
    return None


def _equipment_in_area(model: SiteModel, area_id: str) -> list[dict[str, Any]]:
    want = normalize_name(area_id)
    out: list[dict[str, Any]] = []
    for eq in model.equipment:
        aid = normalize_name(str(eq.get("area_id") or ""))
        if aid == want:
            out.append(eq)
    return out


def _rel_endpoints(rel: dict[str, Any]) -> tuple[str, str]:
    src = rel.get("source") if rel.get("source") is not None else rel.get("from")
    tgt = rel.get("target") if rel.get("target") is not None else rel.get("to")
    return normalize_name(str(src or "")), normalize_name(str(tgt or ""))


def _rel_is_attached_high_confidence(rel: dict[str, Any]) -> bool:
    kind = str(rel.get("kind") or rel.get("type") or "").strip().lower()
    if kind not in {k.lower() for k in ATTACHED_REL_KINDS}:
        return False
    prov = str(rel.get("provenance") or "")
    conf = rel.get("confidence")
    if prov in _HIGH_PROVENANCE:
        return True
    if conf in _HIGH_CONFIDENCE or str(conf).upper() == "HIGH":
        return True
    # Explicit engineer override on the edge counts as high confidence.
    if rel.get("engineer_override"):
        return True
    return False


def _eq_identity(eq: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for k in ("normalized_name", "raw_name", "canonical_id"):
        v = eq.get(k)
        if v:
            ids.add(normalize_name(str(v)))
            ids.add(normalize_name(str(v).split(":")[-1]))
    return {i for i in ids if i}


def rename_area(model: SiteModel, old_id: str, new_id: str) -> SiteModel:
    """Rename an engineering area. Does NOT rename Jam/EStop/StartStop zones."""
    old_id = str(old_id or "").strip()
    new_id = str(new_id or "").strip()
    if not old_id or not new_id:
        raise ValueError("old_id and new_id are required")
    if normalize_name(old_id) == normalize_name(new_id):
        return model

    area = _find_area(model, old_id)
    if area is None:
        raise KeyError(f"area not found: {old_id}")

    if _find_area(model, new_id) is not None:
        raise ValueError(f"target area already exists: {new_id}")

    # Jam / EStop / StartStop / full / sorter zones are intentionally left untouched.
    og = model.operational_groups or {}
    old_norm = normalize_name(old_id)
    area["raw_name"] = new_id
    area["normalized_name"] = normalize_name(new_id)
    area["canonical_id"] = canonical_id("area", new_id)
    area["area_id"] = new_id
    area["name"] = new_id
    area["engineer_override"] = {
        **(area.get("engineer_override") or {}),
        "renamed_from": old_id,
        "area_id": new_id,
    }
    area["provenance"] = PROV_ENGINEER
    area.setdefault("evidence", []).append(
        {
            "kind": "engineer_area_rename",
            "from": old_id,
            "to": new_id,
            "note": "Jam/EStop/StartStop zones not renamed",
        }
    )

    for eq in model.equipment:
        if normalize_name(str(eq.get("area_id") or "")) == old_norm:
            eq["area_id"] = new_id
            eq.setdefault("evidence", []).append(
                {"kind": "area_rename_propagate", "from": old_id, "to": new_id}
            )

    # Mirror engineering_areas operational group entries if present (name only).
    for ea in og.get("engineering_areas") or []:
        if not isinstance(ea, dict):
            continue
        if normalize_name(str(ea.get("raw_name") or ea.get("normalized_name") or ea.get("name") or "")) == old_norm:
            ea["raw_name"] = new_id
            ea["normalized_name"] = normalize_name(new_id)
            ea["name"] = new_id
            ea["canonical_id"] = canonical_id("engineering_area", new_id)

    model.notes.append(f"Area renamed {old_id} → {new_id} (zones unchanged)")
    return model


def create_area(model: SiteModel, name: str) -> dict[str, Any]:
    """Create a new engineering area on the model. Returns the area dict."""
    name = str(name or "").strip()
    if not name:
        raise ValueError("area name is required")
    if _find_area(model, name) is not None:
        raise ValueError(f"area already exists: {name}")
    area = make_object(
        "area",
        name,
        source_table="",
        source_row=None,
        source_scope=SCOPE_ENGINEER,
        active_state="ACTIVE_LIKELY",
        inclusion=INCLUDED,
        confidence="HIGH",
        provenance=PROV_ENGINEER,
        evidence=[{"kind": "engineer_area_create"}],
        generation_state="CONFIGURATION_REQUIRED",
        area_id=name,
        run_derived=False,
    ).to_dict()
    area["name"] = name
    model.areas.append(area)
    model.notes.append(f"Area created: {name}")
    return area


def delete_area(model: SiteModel, area_id: str) -> SiteModel:
    """Delete an area only when empty (no equipment with that area_id)."""
    area_id = str(area_id or "").strip()
    area = _find_area(model, area_id)
    if area is None:
        raise KeyError(f"area not found: {area_id}")
    occupied = _equipment_in_area(model, area_id)
    if occupied:
        names = [e.get("raw_name") or e.get("normalized_name") for e in occupied[:8]]
        raise ValueError(
            f"area {area_id!r} is not empty ({len(occupied)} equipment); "
            f"move or reassign first. sample={names}"
        )
    want = normalize_name(area_id)
    model.areas = [a for a in model.areas if not _area_matches(a, area_id)]
    og = model.operational_groups or {}
    if og.get("engineering_areas"):
        og["engineering_areas"] = [
            ea
            for ea in og["engineering_areas"]
            if normalize_name(str(ea.get("raw_name") or ea.get("name") or "")) != want
        ]
    model.notes.append(f"Area deleted: {area_id}")
    return model


def _index_movable(model: SiteModel) -> dict[str, dict[str, Any]]:
    """Map normalized identities → objects that can receive area_id updates."""
    index: dict[str, dict[str, Any]] = {}
    for bucket in (
        model.equipment,
        model.motors,
        model.vfds,
        model.drives,
        model.photoeyes,
        model.encoders,
    ):
        for obj in bucket:
            for ident in _eq_identity(obj):
                index.setdefault(ident, obj)
    return index


def move_equipment(
    model: SiteModel,
    equipment_ids: list[str],
    target_area: str,
    *,
    move_attached: bool = False,
) -> SiteModel:
    """Move equipment into target_area.

    When move_attached=True, also move devices linked by explicit/high-confidence
    relationships (motor_link, vfd_link, pe_assignment, encoder_link and
    *_to_conveyor variants). Never uses tag-number similarity.
    """
    target_area = str(target_area or "").strip()
    if not target_area:
        raise ValueError("target_area is required")
    if _find_area(model, target_area) is None:
        create_area(model, target_area)

    wanted = {normalize_name(str(x)) for x in (equipment_ids or []) if str(x).strip()}
    if not wanted:
        return model

    index = _index_movable(model)
    primary: list[dict[str, Any]] = []
    for eq in model.equipment:
        ids = _eq_identity(eq)
        if ids & wanted:
            primary.append(eq)

    if not primary:
        raise KeyError(f"no equipment matched ids={sorted(wanted)}")

    to_move: dict[int, dict[str, Any]] = {id(eq): eq for eq in primary}

    if move_attached:
        primary_ids: set[str] = set()
        for eq in primary:
            primary_ids |= _eq_identity(eq)
        for rel in model.relationships or []:
            if not _rel_is_attached_high_confidence(rel):
                continue
            src, tgt = _rel_endpoints(rel)
            other: str | None = None
            if src in primary_ids and tgt:
                other = tgt
            elif tgt in primary_ids and src:
                other = src
            if not other:
                continue
            obj = index.get(other)
            if obj is not None:
                to_move[id(obj)] = obj

    for obj in to_move.values():
        prev = obj.get("area_id")
        obj["area_id"] = target_area
        obj.setdefault("evidence", []).append(
            {
                "kind": "engineer_area_move",
                "from": prev,
                "to": target_area,
                "move_attached": move_attached,
            }
        )
        if obj.get("provenance") not in {PROV_ENGINEER}:
            # Keep RUN provenance on identity; area assignment is engineer.
            obj["area_assignment_provenance"] = PROV_ENGINEER

    model.notes.append(
        f"Moved {len(to_move)} object(s) to {target_area} (move_attached={move_attached})"
    )
    return model


def propagate_area_to_workbook_rows(
    equipment: list[dict[str, Any]],
    area_name: str,
) -> list[dict[str, Any]]:
    """Return workbook-style rows with main_area set from the model area name."""
    area_name = str(area_name or "").strip()
    rows: list[dict[str, Any]] = []
    for eq in equipment or []:
        name = str(eq.get("raw_name") or eq.get("normalized_name") or eq.get("conveyor") or "").strip()
        if not name:
            continue
        row = {
            "conveyor": name,
            "include": eq.get("inclusion", INCLUDED) == INCLUDED or eq.get("include", True),
            "main_area": area_name,
            "safety_zone": eq.get("es_zone_id")
            or eq.get("safety_zone")
            or f"{area_name.replace('_Area', '')}_ESZone1",
            "type": eq.get("type") or eq.get("equipment_type") or "Transport with MS",
            "area_id": eq.get("area_id") or area_name,
        }
        # Preserve common optional fields when present on equipment.
        for k in ("downstream", "exit_pe_tag", "add_pe_tag", "motor_starter"):
            if eq.get(k) is not None:
                row[k] = eq[k]
        rows.append(row)
    return rows


def _load_library_text(library_text_or_path: str | Path) -> str:
    p = Path(str(library_text_or_path))
    if p.is_file():
        return p.read_text(encoding="utf-8", errors="replace")
    return str(library_text_or_path)


def _safe_tag(name: str) -> str:
    t = re.sub(r"[^A-Za-z0-9_]", "_", (name or "").strip())
    t = re.sub(r"_+", "_", t).strip("_")
    if not t:
        return "Area"
    if t[0].isdigit():
        t = f"A_{t}"
    return t


def generate_area_l5x_snippet(
    area_name: str,
    library_text_or_path: str | Path,
) -> dict[str, Any]:
    """Regenerate Area_UDT tag + program name stubs from library Main_Area templates.

    Uses fortna_autogen.extract_tag_block when available; otherwise a minimal
    regex extract. Replaces Main_Area → effective area for Area tags and
    program names ONLY — never a finished-PLC post-hoc rewrite.
    """
    area = _safe_tag(area_name)
    if not area:
        raise ValueError("area_name is required")

    library_text = _load_library_text(library_text_or_path)
    extract_tag_block = None
    try:
        from fortna_autogen import extract_tag_block as _etb  # type: ignore

        extract_tag_block = _etb
    except Exception:  # noqa: BLE001
        extract_tag_block = None

    def _extract(tag_name: str) -> str | None:
        if extract_tag_block is not None:
            return extract_tag_block(library_text, tag_name)
        pat = rf'<Tag Name="{re.escape(tag_name)}"[^>]*>.*?</Tag>'
        m = re.search(pat, library_text, re.S)
        return m.group(0) if m else None

    tags: list[str] = []
    programs: list[str] = []
    source = "inline_minimal"

    main_block = _extract("Main_Area")
    if main_block:
        # Only rename the Area_UDT template tag identity — model-driven.
        tags.append(main_block.replace("Main_Area", area))
        source = "library_Main_Area"
    else:
        tags.append(
            f'<Tag Name="{area}" TagType="Base" DataType="Area_UDT" '
            f'Constant="false" ExternalAccess="Read/Write">'
            f'<Data Format="Decorated"><Structure DataType="Area_UDT"/></Data></Tag>'
        )

    # Program names follow fortna_autogen area.endswith("_Area") convention.
    if area.endswith("_Area"):
        prog_names = [f"{area}_Slow", f"{area}_Fast", f"{area}_L1", f"{area}_L2"]
    else:
        prog_names = [
            f"{area}_Area_Slow",
            f"{area}_Area_Fast",
            f"{area}_Area_L1",
            f"{area}_Area_L2",
        ]
    for pn in prog_names:
        programs.append(
            f'<Program Name="{pn}" TestEdits="false" MainRoutineName="Main_Routine" '
            f'Disabled="false" UseAsFolder="false"><Routines/></Program>'
        )

    xml = (
        f'<!-- model-driven area snippet for {area} (from library Main_Area) -->\n'
        f"<Tags>\n" + "\n".join(tags) + "\n</Tags>\n"
        f"<Programs>\n" + "\n".join(programs) + "\n</Programs>\n"
    )
    return {
        "area_name": area,
        "source": source,
        "tags": tags,
        "programs": programs,
        "program_names": prog_names,
        "xml": xml,
        "model_driven": True,
    }
