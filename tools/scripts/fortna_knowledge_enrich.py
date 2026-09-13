#!/usr/bin/env python3
"""Knowledge-driven enrichment of a SiteModel (PE roles, motor chains, zones, communications).

Uses fortna_knowledge (KB JSON) + RUN facts already on the model.
Does not read finished PLC. Does not invent Greensboro-specific logic.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from fortna_site_model import (
    AVAILABLE,
    EXCLUDED,
    GEN_CFG,
    GEN_NOT_SUPPORTED,
    INCLUDED,
    PROV_ENGINEER,
    PROV_RUN_DERIVED,
    PROV_RUN_EXPLICIT,
    SCOPE_HISTORICAL,
    _clean,
    make_object,
    normalize_name,
)

try:
    from fortna_knowledge import KnowledgeStore, make_decision_trace
except ImportError:  # pragma: no cover - during partial checkout
    KnowledgeStore = None  # type: ignore
    make_decision_trace = None  # type: ignore

PE_ROLES = {
    "DETECTION",
    "JAM",
    "FULL",
    "FULL_JAM",
    "RESERVE",
    "MERGE",
    "SCAN_TRIGGER",
    "UNKNOWN",
}

ATTACHED_REL_KINDS = {
    "motor_link",
    "vfd_link",
    "vfd_to_conveyor",
    "pe_assignment",
    "encoder_link",
    "mtrchain",
}


def _kb() -> Any:
    if KnowledgeStore is None:
        return None
    if hasattr(KnowledgeStore, "load") and callable(getattr(KnowledgeStore, "load")):
        return KnowledgeStore.load()  # type: ignore[attr-defined]
    return KnowledgeStore()


def _evidence_kinds(obj: dict[str, Any]) -> set[str]:
    return {str(e.get("kind") or "") for e in (obj.get("evidence") or [])}


def enrich_pe_roles(site: dict[str, Any], kb: Any = None) -> dict[str, Any]:
    """Attach first-class PE roles from knowledge + RUN evidence. Returns metrics."""
    kb = kb or _kb()
    photoeyes = site.get("photoeyes") or []
    rels = site.get("relationships") or []
    decision_traces = site.setdefault("decision_traces", [])

    jam_sensors: set[str] = set()
    full_sensors: set[str] = set()
    fulljam_sensors: set[str] = set()
    saw_lane_pes: set[str] = set()
    reserve_pes: set[str] = set()
    merge_pes: set[str] = set()
    scan_pes: set[str] = set()

    for r in rels:
        kind = str(r.get("kind") or "")
        frm = normalize_name(r.get("from") or r.get("source") or "")
        to = normalize_name(r.get("to") or r.get("target") or "")
        if kind in {"jam_link", "jamcheck_link"}:
            jam_sensors.update({frm, to})
        elif kind in {"full_link", "fullline_link"}:
            full_sensors.update({frm, to})
        elif kind == "fulljam_link":
            fulljam_sensors.update({frm, to})
        elif kind in {"saw_lane", "hssaw_lane"}:
            saw_lane_pes.update({frm, to})

    auto_resolved = 0
    engineer_required = 0
    previously_cfg = 0
    role_counts: dict[str, int] = defaultdict(int)

    for pe in photoeyes:
        nn = normalize_name(pe.get("normalized_name") or pe.get("raw_name") or "")
        raw = pe.get("raw_name") or pe.get("normalized_name") or ""
        if pe.get("engineer_override") and pe["engineer_override"].get("pe_roles"):
            roles = list(pe["engineer_override"]["pe_roles"])
            pe["pe_roles"] = roles
            pe["pe_role_source"] = "ENGINEER_OVERRIDE"
            for role in roles:
                role_counts[str(role)] += 1
            continue

        flags = {
            "jamcheck": nn in jam_sensors or any(
                e.get("kind") in {"jam_link", "jamcheck_link"} for e in (pe.get("evidence") or [])
            ),
            "fullline": nn in full_sensors or any(
                e.get("kind") in {"full_link", "fullline_link"} for e in (pe.get("evidence") or [])
            ),
            "fulljam": nn in fulljam_sensors or any(
                e.get("kind") == "fulljam_link" for e in (pe.get("evidence") or [])
            ),
            "saw_lane": nn in saw_lane_pes or any(
                e.get("kind") in {"saw_lane", "hssaw_lane"} for e in (pe.get("evidence") or [])
            ),
            "reserve": nn in reserve_pes or bool(re.search(r"_F\d*$|_RES", raw, re.I))
            and any(e.get("kind") in {"saw_lane", "hssaw_lane", "full_link"} for e in (pe.get("evidence") or [])),
            "merge": nn in merge_pes,
            "scan_trigger": nn in scan_pes,
        }

        role_objs: list[dict[str, Any]] = []
        if kb is not None and hasattr(kb, "classify_pe_roles"):
            role_objs = kb.classify_pe_roles(raw, **flags)
        else:
            # Fallback without KB module: table evidence first, suffix supporting
            if flags["jamcheck"]:
                role_objs.append(
                    {
                        "role": "JAM",
                        "confidence": "HIGH",
                        "knowledge_rule": "Jamcheck.Sensor_Name -> PE",
                        "document_source": "FPC-Fulls-Jams-Fulljams",
                    }
                )
            if flags["fullline"]:
                role_objs.append(
                    {
                        "role": "FULL",
                        "confidence": "HIGH",
                        "knowledge_rule": "Fullline.Sensor_Name -> PE",
                        "document_source": "FPC-Fulls-Jams-Fulljams",
                    }
                )
            if flags["fulljam"]:
                role_objs.append(
                    {
                        "role": "FULL_JAM",
                        "confidence": "HIGH",
                        "knowledge_rule": "Fulljam.Sensor_Name -> PE",
                        "document_source": "FPC-Fulls-Jams-Fulljams",
                    }
                )
            if flags["saw_lane"]:
                role_objs.append(
                    {
                        "role": "DETECTION",
                        "confidence": "HIGH",
                        "knowledge_rule": "SawLane.PhotoEyeIO -> PE",
                        "document_source": "FPC-HighSpeedSawtoothMerge",
                    }
                )
            if not role_objs:
                su = raw.upper()
                if re.search(r"_JF\d*$", su):
                    role_objs.append({"role": "FULL_JAM", "confidence": "MEDIUM", "knowledge_rule": "suffix:_JF"})
                elif re.search(r"_J\d*$", su):
                    role_objs.append({"role": "JAM", "confidence": "MEDIUM", "knowledge_rule": "suffix:_J"})
                elif re.search(r"_F\d*$", su):
                    role_objs.append({"role": "FULL", "confidence": "MEDIUM", "knowledge_rule": "suffix:_F"})
                elif re.search(r"_P\d*$", su):
                    role_objs.append({"role": "DETECTION", "confidence": "MEDIUM", "knowledge_rule": "suffix:_P"})
                else:
                    role_objs.append({"role": "UNKNOWN", "confidence": "LOW", "knowledge_rule": "unresolved"})

        roles = [str(r.get("role") or "UNKNOWN") for r in role_objs]
        pe["pe_roles"] = roles
        pe["pe_role_evidence"] = role_objs
        pe["pe_role_source"] = "KNOWLEDGE+RUN"

        # Primary role for legacy consumers (product|full|jam|other mapping)
        if "JAM" in roles and "FULL" not in roles and "FULL_JAM" not in roles:
            pe["role"] = "jam"
        elif "FULL_JAM" in roles:
            pe["role"] = "jam"
        elif "FULL" in roles:
            pe["role"] = "full"
        elif "DETECTION" in roles or "MERGE" in roles:
            pe["role"] = "product"
        else:
            pe["role"] = "other"

        high = any(str(r.get("confidence")) == "HIGH" for r in role_objs)
        if high and "UNKNOWN" not in roles:
            auto_resolved += 1
            if pe.get("generation_state") == GEN_CFG and pe.get("inclusion") == INCLUDED:
                previously_cfg += 1
        elif "UNKNOWN" in roles or not high:
            engineer_required += 1
            pe.setdefault("unresolved_roles", True)

        for role in roles:
            role_counts[role] += 1

        if make_decision_trace and role_objs:
            top = role_objs[0]
            decision_traces.append(
                make_decision_trace(
                    decision=f"{nn} is {','.join(roles)}",
                    run_evidence=[e for e in (pe.get("evidence") or []) if e.get("kind")],
                    knowledge_rule=str(top.get("knowledge_rule") or ""),
                    document_source=str(top.get("document_source") or ""),
                    confidence=str(top.get("confidence") or "UNKNOWN"),
                )
            )

    return {
        "photoeye_count": len(photoeyes),
        "auto_resolved": auto_resolved,
        "engineer_required": engineer_required,
        "previously_configuration_required_resolved": previously_cfg,
        "role_counts": dict(role_counts),
    }


def build_motor_chains(site: dict[str, Any], kb: Any = None) -> list[dict[str, Any]]:
    """Materialize motor_chains[] from Mtrchain relationships."""
    del kb  # reserved for future KB-driven field maps
    chains: dict[str, dict[str, Any]] = {}
    order_map: dict[str, list[str]] = defaultdict(list)

    for r in site.get("relationships") or []:
        kind = str(r.get("kind") or "")
        frm = _clean(r.get("from") or r.get("source") or "")
        to = _clean(r.get("to") or r.get("target") or "")
        if not frm or not to:
            continue
        if kind == "mtrchain":
            head = normalize_name(frm)
            ch = chains.setdefault(
                head,
                {
                    "canonical_id": f"motor_chain:{head}",
                    "kind": "motor_chain",
                    "raw_name": frm,
                    "normalized_name": head,
                    "head": frm,
                    "members": [frm],
                    "order": [frm],
                    "source": "Mtrchain.asc",
                    "provenance": r.get("provenance") or PROV_RUN_EXPLICIT,
                    "confidence": r.get("confidence") or "HIGH",
                    "evidence": [{"kind": "mtrchain", "table": "Mtrchain.asc"}],
                    "engineer_override": None,
                    "aux": None,
                    "stop_zone": None,
                },
            )
            if to not in ch["members"]:
                ch["members"].append(to)
                ch["order"].append(to)
            order_map[head].append(to)
        elif kind == "mtrchain_aux":
            # aux -> motor
            motor = normalize_name(to)
            ch = chains.setdefault(
                motor,
                {
                    "canonical_id": f"motor_chain:{motor}",
                    "kind": "motor_chain",
                    "raw_name": to,
                    "normalized_name": motor,
                    "head": to,
                    "members": [to],
                    "order": [to],
                    "source": "Mtrchain.asc",
                    "provenance": PROV_RUN_EXPLICIT,
                    "confidence": "HIGH",
                    "evidence": [{"kind": "mtrchain_aux"}],
                    "engineer_override": None,
                    "aux": frm,
                    "stop_zone": None,
                },
            )
            ch["aux"] = frm
        elif kind == "mtrchain_stop_zone":
            motor = normalize_name(frm)
            ch = chains.setdefault(
                motor,
                {
                    "canonical_id": f"motor_chain:{motor}",
                    "kind": "motor_chain",
                    "raw_name": frm,
                    "normalized_name": motor,
                    "head": frm,
                    "members": [frm],
                    "order": [frm],
                    "source": "Mtrchain.asc",
                    "provenance": PROV_RUN_EXPLICIT,
                    "confidence": "MEDIUM",
                    "evidence": [{"kind": "mtrchain_stop_zone"}],
                    "engineer_override": None,
                    "aux": None,
                    "stop_zone": to,
                },
            )
            ch["stop_zone"] = to

    out = sorted(chains.values(), key=lambda c: c.get("normalized_name") or "")
    site["motor_chains"] = out
    return out


def enrich_operational_groups(site: dict[str, Any]) -> dict[str, Any]:
    """Ensure distinct operational group buckets; never conflate Area with Jam/ES/SS."""
    og = dict(site.get("operational_groups") or {})
    og.setdefault("engineering_areas", list(site.get("areas") or []))
    og.setdefault("estop_zones", list(site.get("estop_zones") or []))
    og.setdefault("startstop_zones", list(og.get("startstop_zones") or []))
    og.setdefault("jam_zones", list(og.get("jam_zones") or []))
    og.setdefault("full_groups", list(og.get("full_groups") or []))
    og.setdefault("sorter_zones", list(og.get("sorter_zones") or []))

    # Build full_groups from fullline/fulljam relationships (names only)
    if not og["full_groups"]:
        seen: set[str] = set()
        for r in site.get("relationships") or []:
            kind = str(r.get("kind") or "")
            if kind not in {"full_link", "fullline_link", "fulljam_link"}:
                continue
            sensor = _clean(r.get("from") or r.get("source") or "")
            if not sensor or normalize_name(sensor) in seen:
                continue
            seen.add(normalize_name(sensor))
            og["full_groups"].append(
                make_object(
                    "full_group",
                    sensor,
                    source_table="Fullline.asc" if "full" in kind else "Fulljam.asc",
                    provenance=PROV_RUN_DERIVED,
                    confidence="MEDIUM",
                    evidence=[{"kind": kind}],
                    generation_state=GEN_CFG,
                    relationship_kind=kind,
                    linked_to=_clean(r.get("to") or r.get("target") or ""),
                ).to_dict()
            )

    # Sorter zones from sorter objects (identity only — not Engineering Area)
    if not og["sorter_zones"]:
        for s in site.get("sorters") or []:
            name = s.get("raw_name") or s.get("normalized_name")
            if not name:
                continue
            og["sorter_zones"].append(
                {
                    **{k: s.get(k) for k in ("canonical_id", "raw_name", "normalized_name", "provenance", "confidence")},
                    "kind": "sorter_zone",
                    "source": "Sorters.asc",
                    "evidence": s.get("evidence") or [{"kind": "sorter_static"}],
                    "engineer_override": s.get("engineer_override"),
                }
            )

    site["operational_groups"] = og
    # Keep top-level estop_zones in sync for older consumers
    if og.get("estop_zones") and not site.get("estop_zones"):
        site["estop_zones"] = og["estop_zones"]
    return og


def enrich_communications(site: dict[str, Any], run_tables: dict[str, list] | None = None) -> list[dict[str, Any]]:
    """Wire Machine/MsgMap/MsgWCS/MsgTrack/WCSEvents into communication objects.

    Distinguishes configured relationship vs runtime queue contents.
    Runtime queue rows must not become static PLC definitions automatically.
    """
    del run_tables
    comms: list[dict[str, Any]] = []
    # Prefer already-discovered wcs_interfaces / tracking_systems
    for w in site.get("wcs_interfaces") or []:
        comms.append(
            {
                "canonical_id": w.get("canonical_id") or f"comm:{normalize_name(w.get('raw_name') or '')}",
                "kind": "communication",
                "message_class": "WCS",
                "layer": "COMMUNICATION_CONFIG",
                "sender": w.get("sender") or w.get("machine") or None,
                "receiver": w.get("receiver") or "WCS",
                "topic": w.get("topic") or w.get("event") or None,
                "event": w.get("event"),
                "ownership": w.get("machine_scope") or site.get("machine_scope"),
                "source_evidence": w.get("evidence") or [{"kind": "wcs_interface"}],
                "provenance": w.get("provenance") or PROV_RUN_EXPLICIT,
                "confidence": w.get("confidence") or "MEDIUM",
                "runtime_queue": False,
                "generation_state": w.get("generation_state") or GEN_NOT_SUPPORTED,
                "raw": w,
            }
        )
    for t in site.get("tracking_systems") or []:
        comms.append(
            {
                "canonical_id": t.get("canonical_id") or f"comm_track:{normalize_name(t.get('raw_name') or '')}",
                "kind": "communication",
                "message_class": "TRACK",
                "layer": "RUNTIME_STATE" if t.get("runtime") else "STATIC_CONFIG",
                "sender": t.get("sender"),
                "receiver": t.get("receiver"),
                "topic": t.get("topic"),
                "event": None,
                "ownership": site.get("machine_scope"),
                "source_evidence": t.get("evidence") or [{"kind": "tracking"}],
                "provenance": t.get("provenance") or PROV_RUN_EXPLICIT,
                "confidence": t.get("confidence") or "MEDIUM",
                "runtime_queue": bool(t.get("runtime")),
                "generation_state": GEN_NOT_SUPPORTED,
                "raw": t,
            }
        )
    site["communications"] = comms
    site["tracking"] = list(site.get("tracking_systems") or [])
    return comms


def build_inclusion_reasons(site: dict[str, Any]) -> dict[str, Any]:
    """Store WHY for INCLUDED / AVAILABLE / EXCLUDED."""
    reasons: dict[str, Any] = {}
    for bucket in ("equipment", "motors", "vfds", "photoeyes", "encoders", "sorters", "sawtooth_merges"):
        for obj in site.get(bucket) or []:
            cid = obj.get("canonical_id") or obj.get("normalized_name")
            if not cid:
                continue
            kinds = sorted(_evidence_kinds(obj))
            inclusion = obj.get("inclusion") or AVAILABLE
            positive = [k for k in kinds if k not in {"source", "numbering_hint", "geometry_candidate"}]
            why = {
                "inclusion": inclusion,
                "active_state": obj.get("active_state"),
                "positive_evidence": positive,
                "missing": [],
                "notes": [],
            }
            if inclusion == INCLUDED:
                why["notes"].append("sufficient positive evidence for generation")
            elif inclusion == AVAILABLE:
                if not any(k in kinds for k in ("controller_io", "io_assignment", "pe_assignment", "motor_link")):
                    why["missing"].append("no I/O")
                if "mtrchain" not in kinds:
                    why["missing"].append("no Mtrchain")
                if not any(k in kinds for k in ("path_link", "convpath_link", "saw_lane", "jam_link")):
                    why["missing"].append("no current path/subsystem relationship")
                why["notes"].append("credible record but insufficient proof")
            elif inclusion == EXCLUDED:
                if obj.get("active_state") in {"INACTIVE_CONFIRMED", "HISTORICAL_OR_STALE"}:
                    why["notes"].append("explicit inactive/stale/superseded evidence")
                if obj.get("engineer_override") and obj["engineer_override"].get("inclusion") == EXCLUDED:
                    why["notes"].append("engineer exclusion")
                if obj.get("source_scope") == SCOPE_HISTORICAL:
                    why["notes"].append("historical ASC scope")
            if obj.get("engineer_override"):
                why["engineer_override"] = True
            obj["inclusion_why"] = why
            reasons[cid] = why
    site["inclusion_reasons"] = reasons
    return reasons


def build_transport_editor_v2(site: dict[str, Any]) -> dict[str, Any]:
    """Auto-populate Transport editor contents from knowledge-driven SiteModel."""
    pe_by_conv: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pe in site.get("photoeyes") or []:
        linked = normalize_name(pe.get("linked_conveyor") or pe.get("conveyor") or "")
        if linked:
            pe_by_conv[linked].append(
                {
                    "name": pe.get("raw_name") or pe.get("normalized_name"),
                    "roles": pe.get("pe_roles") or [pe.get("role") or "UNKNOWN"],
                    "role_evidence": pe.get("pe_role_evidence") or [],
                    "inclusion": pe.get("inclusion"),
                }
            )

    chain_by_member: dict[str, dict[str, Any]] = {}
    for ch in site.get("motor_chains") or []:
        for m in ch.get("members") or []:
            chain_by_member[normalize_name(m)] = ch

    motor_by_conv: dict[str, str] = {}
    vfd_by_conv: dict[str, str] = {}
    for r in site.get("relationships") or []:
        kind = str(r.get("kind") or "")
        frm = _clean(r.get("from") or r.get("source") or "")
        to = _clean(r.get("to") or r.get("target") or "")
        if kind == "motor_link":
            motor_by_conv[normalize_name(to)] = frm
            motor_by_conv[normalize_name(frm)] = to
        elif kind in {"vfd_link", "vfd_to_conveyor"}:
            vfd_by_conv[normalize_name(to)] = frm
            vfd_by_conv[normalize_name(frm)] = to

    og = site.get("operational_groups") or {}
    items = []
    for eq in site.get("equipment") or []:
        nn = normalize_name(eq.get("normalized_name") or "")
        items.append(
            {
                "canonical_id": eq.get("canonical_id"),
                "name": eq.get("raw_name") or eq.get("normalized_name"),
                "active_include": eq.get("inclusion"),
                "inclusion_why": eq.get("inclusion_why"),
                "equipment_type": eq.get("equipment_type") or eq.get("type"),
                "geometry": {
                    "x": eq.get("x"),
                    "y": eq.get("y"),
                    "length": eq.get("length"),
                    "width": eq.get("width"),
                    "angle": eq.get("angle"),
                },
                "motor": eq.get("motor") or motor_by_conv.get(nn),
                "vfd": eq.get("drive") or eq.get("vfd") or vfd_by_conv.get(nn),
                "photoeyes": pe_by_conv.get(nn) or [],
                "motor_chain": chain_by_member.get(nn)
                or chain_by_member.get(normalize_name(eq.get("motor") or "")),
                "engineering_area": eq.get("area_id"),
                "estop_zone": eq.get("es_zone_id"),
                "startstop_zone": eq.get("startstop_zone_id"),
                "jam_zone": eq.get("jam_zone_id"),
                "downstream_evidence": [
                    r
                    for r in (site.get("relationships") or [])
                    if normalize_name(r.get("from") or r.get("source") or "") == nn
                    and str(r.get("kind") or "") in {"path_link", "convpath_link", "merge_link"}
                ],
                "provenance": eq.get("provenance"),
                "confidence": eq.get("confidence"),
                "topology_unknown": not any(
                    normalize_name(r.get("from") or "") == nn or normalize_name(r.get("to") or "") == nn
                    for r in (site.get("relationships") or [])
                    if str(r.get("kind") or "") in {"path_link", "convpath_link"}
                ),
            }
        )

    return {
        "editor": "transport_v2",
        "machine": site.get("machine_scope"),
        "items": items,
        "counts": {
            "INCLUDED": sum(1 for i in items if i.get("active_include") == INCLUDED),
            "AVAILABLE": sum(1 for i in items if i.get("active_include") == AVAILABLE),
            "EXCLUDED": sum(1 for i in items if i.get("active_include") == EXCLUDED),
        },
        "zone_catalog": {
            "engineering_areas": [a.get("raw_name") for a in (og.get("engineering_areas") or [])],
            "estop_zones": [z.get("raw_name") for z in (og.get("estop_zones") or site.get("estop_zones") or [])],
            "startstop_zones": [z.get("raw_name") for z in (og.get("startstop_zones") or [])],
            "jam_zones": [z.get("raw_name") for z in (og.get("jam_zones") or [])],
        },
    }


def _vfd_base_token(name: str) -> str:
    m = re.match(r"^(VFD\d+[A-Z]?)", (name or "").upper())
    return m.group(1) if m else (name or "").upper()


def _p_tag_from_vfd_token(name: str) -> str:
    """VFD414_AUX / VFD414 → P414 (digits + optional letter)."""
    m = re.match(r"^VFD[\s\-_]*(\d{2,4}[A-Za-z]?)", name or "", re.I)
    return ("P" + m.group(1).upper()) if m else ""


def _equipment_name_set(site: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for eq in site.get("equipment") or []:
        for key in ("raw_name", "normalized_name"):
            n = _clean(eq.get(key) or "")
            if n:
                names.add(n.upper())
                names.add(normalize_name(n))
    return names


def _derive_collector_conveyor(site: dict[str, Any], merge: dict[str, Any]) -> str | None:
    """Derive collector P-tag from motor_io when that equipment exists."""
    motor = _clean(merge.get("motor_io") or merge.get("motor") or "")
    if not motor:
        return None
    candidate = _p_tag_from_vfd_token(motor)
    if not candidate:
        return None
    eq_names = _equipment_name_set(site)
    if candidate.upper() in eq_names or normalize_name(candidate) in eq_names:
        return candidate
    return None


def _derive_collector_encoder(site: dict[str, Any], merge: dict[str, Any]) -> str | None:
    """Encoder associated to merge, or ENC### matching VFD### base."""
    merge_name = _clean(merge.get("raw_name") or merge.get("normalized_name") or "")
    merge_u = merge_name.upper()
    motor = _clean(merge.get("motor_io") or merge.get("motor") or "")
    vfd_base = _vfd_base_token(motor) if motor else ""
    digits = ""
    m_dig = re.match(r"^VFD(\d+[A-Z]?)$", vfd_base)
    if m_dig:
        digits = m_dig.group(1)

    for enc in site.get("encoders") or []:
        enc_name = _clean(enc.get("raw_name") or enc.get("normalized_name") or "")
        if not enc_name:
            continue
        for assoc in enc.get("associations") or []:
            if not isinstance(assoc, dict):
                continue
            atype = str(assoc.get("type") or assoc.get("kind") or "")
            to = _clean(assoc.get("to") or "")
            if atype in {
                "encoder_to_saw_merge_via_motor_io",
                "encoder_jamzone_sawtooth",
            } and to.upper().replace(" ", "_") in {merge_u, merge_u.replace(" ", "_")}:
                return enc_name
            if merge_u and merge_u in to.upper().replace(" ", "_"):
                return enc_name
        # ENC414 ↔ VFD414
        if digits and re.match(rf"^ENC{re.escape(digits)}$", enc_name, re.I):
            return enc_name
        enable = _clean(enc.get("enable") or "")
        if vfd_base and _vfd_base_token(enable) == vfd_base:
            return enc_name
    return None


def _derive_downstream_conveyor(
    site: dict[str, Any],
    collector: str | None,
) -> str | None:
    """Best-effort downstream from motor_chain order after collector."""
    if not collector:
        return None
    coll_n = normalize_name(collector)
    eq_names = _equipment_name_set(site)
    for ch in site.get("motor_chains") or []:
        order = [normalize_name(x) for x in (ch.get("order") or ch.get("members") or [])]
        if coll_n not in order:
            continue
        idx = order.index(coll_n)
        for nxt in order[idx + 1 :]:
            if not nxt or nxt == coll_n:
                continue
            if nxt.upper().startswith("VFD") or nxt.upper().startswith("MTR"):
                continue
            if nxt.upper() in eq_names or nxt in eq_names:
                # Prefer original casing from chain
                for raw in ch.get("order") or ch.get("members") or []:
                    if normalize_name(raw) == nxt:
                        return _clean(raw) or nxt
                return nxt
    # Transport graph edges (from → to)
    tr = site.get("transport") or {}
    for edge in tr.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        frm = normalize_name(edge.get("from") or edge.get("source") or edge.get("a") or "")
        to = _clean(edge.get("to") or edge.get("target") or edge.get("b") or "")
        if frm == coll_n and to:
            return to
    return None


def build_sawtooth_editor_v2(site: dict[str, Any]) -> dict[str, Any]:
    merges = site.get("sawtooth_merges") or []
    capability_matrix = {
        "lane_identity": "VALIDATED" if merges else "DISCOVERED",
        "lane_pe": "VALIDATED" if any(
            (ln.get("photoeye") for m in merges for ln in (m.get("lanes") or []))
        ) else "MODELED",
        "lane_vfd": "VALIDATED" if any(
            (ln.get("drive") or ln.get("vfd") for m in merges for ln in (m.get("lanes") or []))
        ) else "MODELED",
        "slice_timing": "GENERATABLE",
        "reservation_semantics": "MODELED",
        "collector_tracking": "MODELED",
        "encoder_enable_reset": "GENERATABLE",
        "full_generation": "GENERATABLE",
    }
    items = []
    cfg_required = 0
    resolved = 0
    for m in merges:
        collector = _derive_collector_conveyor(site, m)
        collector_encoder = _derive_collector_encoder(site, m)
        downstream = _derive_downstream_conveyor(site, collector)
        merge_cfg_required: list[str] = list(m.get("config_required") or [])
        lanes = []
        for ln in m.get("lanes") or []:
            lane_encoder = ln.get("encoder") or collector_encoder or m.get("encoder")
            lane = {
                "lane_identity": ln.get("name"),
                "lane_conveyor": ln.get("conveyor"),
                "lane_pe": ln.get("photoeye"),
                "full_eye": ln.get("full_eye") or ln.get("full"),
                "reserve_eye": ln.get("reserve_eye") or ln.get("reserve"),
                "motor": ln.get("motor") or m.get("motor_io"),
                "drive": ln.get("drive") or ln.get("vfd"),
                "encoder": lane_encoder,
                "collector": ln.get("collector") or collector,
                "slice_time": ln.get("slice_time") or m.get("slice_time") or m.get("slice_seconds"),
                "reserve_time": ln.get("reserve_time") or m.get("reserve_time") or m.get("reserve_seconds"),
                "enable_delay": ln.get("enable_delay"),
                "reservation_mode": ln.get("reservation_mode") or m.get("reservation_mode"),
                "shifter_config": ln.get("shifter_config"),
                "opportunistic_feed": ln.get("opportunistic_feed"),
                "zones": {
                    "engineering_area": m.get("area_id"),
                    "estop_zone": m.get("es_zone_id"),
                    "startstop_zone": m.get("startstop_zone_id"),
                    "jam_zone": m.get("jam_zone_id"),
                },
                "configuration_required": [],
            }
            for field, label in (
                ("lane_conveyor", "lane conveyor"),
                ("lane_pe", "lane PE"),
                ("drive", "lane VFD"),
                ("encoder", "encoder"),
                ("reservation_mode", "reservation mode"),
                ("reserve_eye", "reserve eye"),
                ("reserve_time", "reserve time"),
            ):
                if not lane.get(field):
                    lane["configuration_required"].append(label)
                    cfg_required += 1
                else:
                    resolved += 1
            lanes.append(lane)
        # Downstream is derived when Mtrchain proves a successor; otherwise optional
        # (do not count toward blocking engineer_decisions / Apply readiness).
        for field, label in (
            ("collector_conveyor", "collector conveyor"),
            ("collector_encoder", "collector encoder"),
        ):
            val = {
                "collector_conveyor": collector,
                "collector_encoder": collector_encoder,
            }[field]
            if not val:
                if label not in merge_cfg_required:
                    merge_cfg_required.append(label)
                cfg_required += 1
            else:
                resolved += 1
        if downstream:
            resolved += 1
        merge_cfg_required = [
            x
            for x in merge_cfg_required
            if str(x).strip().lower()
            not in {"downstream conveyor", "downstream_conveyor", "discharge_conveyor"}
        ]
        items.append(
            {
                "merge_identity": m.get("raw_name") or m.get("normalized_name"),
                "merge_type": m.get("merge_type") or m.get("type") or "SawMerge",
                "lane_count": len(lanes),
                "lanes": lanes,
                "motor": m.get("motor_io"),
                "encoder": collector_encoder or m.get("encoder"),
                "collector_conveyor": collector,
                "collector_encoder": collector_encoder,
                "downstream_conveyor": downstream,
                "provenance": m.get("provenance"),
                "confidence": m.get("confidence"),
                "config_required": merge_cfg_required,
                "configuration_required": list(merge_cfg_required),
            }
        )
    total = max(resolved + cfg_required, 1)
    return {
        "editor": "sawtooth_v2",
        "detected": bool(merges),
        "merges": items,
        "capability_matrix": capability_matrix,
        "configuration_resolved_pct": round(100.0 * resolved / total, 1),
        "engineer_decisions": cfg_required,
        "note": "Unknowns stay CONFIGURATION REQUIRED; collector/encoder derived from motor_io when equipment exists",
    }


def build_sorter_editor_v2(site: dict[str, Any]) -> dict[str, Any]:
    sorters = site.get("sorters") or []
    encoders = [e.get("raw_name") or e.get("normalized_name") for e in (site.get("encoders") or [])]
    layers = {
        "STATIC_CONFIG": [],
        "RUNTIME_STATE": [],
        "COMMUNICATION_CONFIG": [],
        "ENGINEER_REQUIRED": [],
    }
    for s in sorters:
        entry = {
            "sorter": s.get("raw_name") or s.get("normalized_name"),
            "sorter_type": s.get("sorter_type") or s.get("type"),
            "encoders": s.get("encoders") or encoders[:1],
            "app_controls": s.get("app_controls") or [],
            "scan_bosses": s.get("scan_bosses") or [],
            "scan_zones": s.get("scan_zones") or [],
            "lane_assignments": s.get("lane_assignments") or [],
            "scanner_relationships": s.get("scanner_relationships") or [],
            "runtime_tracking_available": bool(s.get("runtime_tracking")),
            "routing_tables": s.get("routing_tables") or [],
            "wcs_event_topics": s.get("wcs_events") or [],
            "communication_machines": s.get("machines") or [],
            "unresolved_divert_mapping": True,
            "unresolved_conveyor_tracking_chain": True,
            "generation_state": s.get("generation_state") or GEN_NOT_SUPPORTED,
        }
        layers["STATIC_CONFIG"].append(entry["sorter"])
        layers["ENGINEER_REQUIRED"].extend(
            ["divert_map", "conveyor_tracking_chain"]
        )
        if entry["runtime_tracking_available"]:
            layers["RUNTIME_STATE"].append(entry["sorter"])

    generation_leaves = {
        "encoder_infrastructure": "GENERATABLE" if encoders else "CONFIGURATION_REQUIRED",
        "scanner_device_structures": "CONFIGURATION_REQUIRED",
        "scan_zone_configuration": "MODELED" if sorters else "DISCOVERED",
        "sorter_entity_tags": "MODELED" if sorters else "DISCOVERED",
        "wcs_message_config_tags": "GENERATION_NOT_SUPPORTED",
        "route_destination_configuration": "CONFIGURATION_REQUIRED",
        "divert_aoi_instances": "GENERATION_NOT_SUPPORTED",
        "transfer_tracking_support": "GENERATION_NOT_SUPPORTED",
    }
    return {
        "editor": "sorter_v2",
        "detected": bool(sorters),
        "sorters": sorters,
        "layers": layers,
        "generation_leaves": generation_leaves,
        "note": "No Sorter_Track clone; only proven leaves may generate. Gold L5X is reference-only.",
    }


def ui_status_summary(site: dict[str, Any], *, pe_metrics: dict | None = None,
                      transport_editor: dict | None = None,
                      sawtooth_editor: dict | None = None,
                      sorter_editor: dict | None = None) -> dict[str, Any]:
    te = transport_editor or {}
    se = sawtooth_editor or {}
    so = sorter_editor or {}
    pe = pe_metrics or {}
    t_counts = te.get("counts") or {}
    rel_review = sum(
        1
        for r in (site.get("relationships") or [])
        if str(r.get("confidence") or "").upper() in {"LOW", "UNKNOWN", ""}
    )
    return {
        "TRANSPORT": {
            "Included": t_counts.get("INCLUDED", 0),
            "Available": t_counts.get("AVAILABLE", 0),
            "Excluded": t_counts.get("EXCLUDED", 0),
            "relationships_need_review": rel_review,
        },
        "SAWTOOTH": {
            "detected": int(bool(se.get("detected"))),
            "lanes": sum(m.get("lane_count") or 0 for m in (se.get("merges") or [])),
            "configuration_resolved_pct": se.get("configuration_resolved_pct"),
            "engineer_decisions": se.get("engineer_decisions"),
        },
        "SORTER": {
            "detected": int(bool(so.get("detected"))),
            "configuration_modeled": bool(so.get("detected")),
            "encoder_resolved": (so.get("generation_leaves") or {}).get("encoder_infrastructure")
            == "GENERATABLE",
            "scan_zones_resolved": (so.get("generation_leaves") or {}).get("scan_zone_configuration")
            in {"MODELED", "GENERATABLE", "VALIDATED"},
            "divert_map_required": True,
            "generation": "partial" if so.get("detected") else "none",
        },
        "PE": {
            "auto_resolved": pe.get("auto_resolved", 0),
            "engineer_required": pe.get("engineer_required", 0),
        },
    }


def enrich_site_model(site: dict[str, Any], kb: Any = None) -> dict[str, Any]:
    """Run full knowledge enrichment pass; mutates and returns site dict."""
    kb = kb or _kb()
    site.setdefault("schema_version", "2.0")
    pe_metrics = enrich_pe_roles(site, kb)
    build_motor_chains(site, kb)
    enrich_operational_groups(site)
    enrich_communications(site)
    build_inclusion_reasons(site)
    # drives alias
    site["drives"] = list(site.get("vfds") or [])
    site["io_points"] = list(site.get("io_points") or [])
    transport_editor = build_transport_editor_v2(site)
    sawtooth_editor = build_sawtooth_editor_v2(site)
    sorter_editor = build_sorter_editor_v2(site)
    site["editors"] = {
        "transport": transport_editor,
        "sawtooth": sawtooth_editor,
        "sorter": sorter_editor,
    }
    site["ui_status_summary"] = ui_status_summary(
        site,
        pe_metrics=pe_metrics,
        transport_editor=transport_editor,
        sawtooth_editor=sawtooth_editor,
        sorter_editor=sorter_editor,
    )
    site["enrichment_metrics"] = {
        "pe_roles": pe_metrics,
        "motor_chains": len(site.get("motor_chains") or []),
        "communications": len(site.get("communications") or []),
    }
    return site
