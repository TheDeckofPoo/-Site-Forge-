#!/usr/bin/env python3
"""MSCRENOPICK I/O FORENSICS — evidence-only analysis (no production mutations).

Reads frozen ledger artifacts + optional live RUN (read-only).
Does not invent mappings. Does not optimize percentages.
Outputs MSCRENOPICK_IO_FORENSICS.json / .txt on the analysis branch only.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))

OUT_DIR = Path(__file__).resolve().parent
LEDGER_DIR = OUT_DIR / "mscrenopick_io_correctness_ledger"
PROOF_JSON = OUT_DIR / "mscrenopick_io_correctness_proof.json"
OUT_JSON = OUT_DIR / "MSCRENOPICK_IO_FORENSICS.json"
OUT_TXT = OUT_DIR / "MSCRENOPICK_IO_FORENSICS.txt"

FROZEN_SHA = "41033e45084bfd4b3dfb7639655a2082319ad7f2"

FAMILIES = (
    "SAFETY",
    "CONTROL_STATION_PUSHBUTTON",
    "PHOTOEYE",
    "MOTOR_STARTER_VFD",
    "POWER_OTHER_PHYSICAL",
    "INTERNAL_LOGICAL",
    "FOREIGN",
    "UNKNOWN",
)

OCCUPANCY_CLASSES = (
    "REAL_UNUSED_PHYSICAL_CHANNEL",
    "REAL_OCCUPIED_FIELD_POINT",
    "INTERNAL_LOGICAL_EVIDENCE",
    "DUPLICATE_SOURCE_NOISE",
    "UNKNOWN",
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _family_from_device(d: dict[str, Any]) -> str:
    st = _norm(d.get("final_status")).split(":")[0]
    own = _norm(d.get("ownership")).upper()
    ec = _norm(d.get("evidence_class")).upper()
    dt = _norm(d.get("device_type")).upper()
    ec_equip = _norm(d.get("equipment_class")).upper()
    name = _norm(d.get("canonical_name")).upper()

    if st == "FOREIGN_CONTROLLER" or own == "FOREIGN" or ec == "FOREIGN_CONTROLLER":
        return "FOREIGN"
    if st == "INTERNAL_LOGICAL" or ec == "INTERNAL_LOGICAL" or dt == "INTERNAL_LOGICAL":
        return "INTERNAL_LOGICAL"
    if dt in {"ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP"} or "SAFETY" in ec_equip:
        return "SAFETY"
    if dt == "PUSHBUTTON_CONTROL" or "CONTROL_STATION" in ec_equip or "PUSHBUTTON" in ec_equip:
        return "CONTROL_STATION_PUSHBUTTON"
    if dt == "PHOTOEYE" or "PHOTOEYE" in ec_equip or re.search(r"(?:^PE\d|_PE\d|_PE$)", name):
        return "PHOTOEYE"
    if dt in {"VFD", "MOTOR", "DRIVE"} or any(
        x in ec_equip for x in ("DRIVE", "MOTOR", "VFD")
    ) or re.search(r"(?:VFD|MTR|STARTER|(?:^|_)MS\d)", name):
        return "MOTOR_STARTER_VFD"
    if dt == "PHYSICAL_CHANNEL":
        return "POWER_OTHER_PHYSICAL"
    if dt and dt not in {"IO", "UNKNOWN", ""}:
        return "POWER_OTHER_PHYSICAL"
    return "UNKNOWN"


def _load_kb() -> dict[str, Any]:
    try:
        from fortna_io_knowledge_base import load_knowledge_base, match_knowledge

        kb = load_knowledge_base(REPO / "workspace" / "fortna_io_knowledge_base.json")
        return {"kb": kb, "match": match_knowledge}
    except Exception as ex:  # noqa: BLE001
        return {"kb": {}, "match": None, "error": str(ex)[:200]}


def _kb_matches(name: str, kb_pack: dict[str, Any]) -> list[dict[str, Any]]:
    match_fn = kb_pack.get("match")
    if not callable(match_fn):
        return []
    try:
        hits = match_fn(name, kb=kb_pack.get("kb")) or []
        out = []
        for h in hits[:6]:
            out.append(
                {
                    "pattern_key": h.get("pattern_key") or h.get("pattern"),
                    "pattern": h.get("pattern"),
                    "equipment_class": h.get("equipment_class"),
                    "fortna_plus_udt_aoi_bool_target": h.get(
                        "fortna_plus_udt_aoi_bool_target"
                    ),
                    "accepted_engineer_decision": h.get("accepted_engineer_decision"),
                    "confidence": h.get("confidence"),
                    "source": (h.get("provenance") or {}).get("source"),
                }
            )
        return out
    except Exception:
        return []


def _classify_equipment_safe(name: str, highlight: str = "") -> dict[str, Any]:
    try:
        from fortna_io_equipment_classifier import classify_equipment

        return dict(classify_equipment(name, highlight=highlight) or {})
    except Exception as ex:  # noqa: BLE001
        return {"error": str(ex)[:120]}


def _fortna_plus_hint(d: dict[str, Any], kb_hits: list[dict[str, Any]], sem: dict[str, Any]) -> str:
    if d.get("fortna_plus_hint"):
        return _norm(d.get("fortna_plus_hint"))
    if sem.get("fortna_plus_hint"):
        return _norm(sem.get("fortna_plus_hint"))
    for h in kb_hits:
        if h.get("fortna_plus_udt_aoi_bool_target"):
            return _norm(h["fortna_plus_udt_aoi_bool_target"])
    dt = _norm(d.get("device_type")).upper()
    name = _norm(d.get("canonical_name")).upper()
    if dt == "ESPB" or name.startswith("ESPB"):
        return "ESZone.I.ESPB_* / Safety AOI member (semantic)"
    if dt == "ESLS" or name.startswith("ESLS"):
        return "ESZone.I.ESLS_* / Safety lanyard member (semantic)"
    if dt == "ESR" or name.startswith("ESR"):
        return "ESZone.I.ESR_* (semantic)"
    if dt == "MCR" or name.startswith("MCR"):
        return "ESZone.I.MCR_* (semantic)"
    if dt == "PUSHBUTTON_CONTROL":
        if "START" in name:
            return "CPx_CS.I.Start_PB"
        if "STOP" in name:
            return "CPx_CS.I.Stop_PB"
        if "RESET" in name:
            return "CPx_CS.I.Reset_PB"
        return "CPx_CS.I.* (control-station member; exact member TBD)"
    return ""


def _physical_world_evidence(d: dict[str, Any]) -> dict[str, Any]:
    """Physical-world evidence YES/NO with cited reasons — no invented endpoints."""
    reasons = []
    yes = False
    name = _norm(d.get("canonical_name"))
    dt = _norm(d.get("device_type")).upper()
    ec = _norm(d.get("evidence_class")).upper()
    endpoint = _norm(d.get("physical_endpoint"))
    word = _norm(d.get("word"))
    bit = _norm(d.get("bit"))
    src = d.get("source_evidence") or []

    if ec == "PHYSICAL_FIELD_DEVICE":
        yes = True
        reasons.append("evidence_class=PHYSICAL_FIELD_DEVICE")
    if dt in {"ESPB", "ESLS", "ESR", "MCR", "PUSHBUTTON_CONTROL", "PHOTOEYE", "VFD", "MOTOR", "SAFETY"}:
        yes = True
        reasons.append(f"device_type nomenclature={dt}")
    if endpoint and not endpoint.upper().startswith("OCCUPANCY:"):
        # word.bit style endpoint from safety model is weak physical; Logix module is strong
        if re.search(r":\d*:?[IO]\.Data", endpoint, re.I) or "AENT" in endpoint.upper():
            yes = True
            reasons.append(f"module-style endpoint={endpoint}")
        else:
            reasons.append(f"weak/word-style endpoint={endpoint} (not module-proven)")
    source_types = sorted({_norm(s.get("source_type")) for s in src if _norm(s.get("source_type"))})
    if any(t in {"estop_table", "safety_evidence", "conveyor_named_claim"} for t in source_types):
        yes = True
        reasons.append(f"source_types={source_types}")
    if word:
        reasons.append(f"word={word} bit={bit}")
    if not yes:
        reasons.append("no strong physical-field nomenclature or module endpoint")
    return {"physical_world_evidence": "YES" if yes else "NO", "reasons": reasons}


def _ownership_evidence(d: dict[str, Any], active_words: set[str]) -> dict[str, Any]:
    word = _norm(d.get("word"))
    code = _norm(d.get("deterministic_code"))
    own = _norm(d.get("ownership")).upper()
    sm = _norm(d.get("source_machine")).upper()
    in_map = d.get("word_in_active_configio")
    if in_map is None and word:
        in_map = word in active_words or (word.isdigit() and word in active_words)
    return {
        "ownership": own or "UNKNOWN",
        "source_machine": sm or "",
        "deterministic_code": code,
        "word_in_active_configio": in_map,
        "controller": _norm(d.get("controller")),
        "module": _norm(d.get("module")),
        "slot": _norm(d.get("slot")),
        "word": word,
        "bit": _norm(d.get("bit")),
        "physical_endpoint": _norm(d.get("physical_endpoint")),
        "active_controller_claim": (
            "PROVEN_LOCAL"
            if own == "LOCAL" and (d.get("physical_endpoint") or in_map)
            else (
                "PROVEN_FOREIGN"
                if own == "FOREIGN"
                else (
                    "WORD_ABSENT_FROM_ACTIVE_CONFIGIO"
                    if in_map is False
                    else "UNRESOLVED"
                )
            )
        ),
    }


def _resolution_feasibility(d: dict[str, Any], own: dict[str, Any], phys: dict[str, Any]) -> dict[str, Any]:
    """Whether deterministic / AI / Relay / engineer should be able to resolve — forensic opinion."""
    code = _norm(own.get("deterministic_code")).upper()
    in_map = own.get("word_in_active_configio")
    name = _norm(d.get("canonical_name")).upper()
    family = _family_from_device(d)
    st = _norm(d.get("final_status")).split(":")[0]

    det_possible = False
    det_why = ""
    ai_possible = False
    ai_why = ""
    relay_possible = False
    relay_why = ""
    eng_required = True
    eng_why = ""

    if st in {"MAPPED", "FOREIGN_CONTROLLER", "ENGINEER_CONFIRMED", "UNSUPPORTED", "SPARE_UNUSED", "INTERNAL_LOGICAL"}:
        return {
            "deterministic_resolution_should_be_possible": st in {"MAPPED", "FOREIGN_CONTROLLER", "INTERNAL_LOGICAL", "SPARE_UNUSED"},
            "ai_should_be_able_to_resolve": False,
            "relay_should_be_able_to_resolve": False,
            "engineer_confirmation_genuinely_required": st in {"ENGINEER_CONFIRMED"} or False,
            "notes": f"already terminal={st}",
        }

    if code == "ENDPOINT_ON_ACTIVE_CONTROLLER" or (
        own.get("ownership") == "LOCAL" and _norm(own.get("physical_endpoint")) and "AENT" in _norm(own.get("physical_endpoint")).upper()
    ):
        det_possible = True
        det_why = "endpoint already on active controller — mapping/generation gap, not ownership gap"
        eng_required = False
        eng_why = "deterministic ownership proven; engineer only if map conflict"
    elif code == "EXPLICIT_FOREIGN_MACHINE":
        det_possible = True
        det_why = "Machine_Name proves foreign"
        eng_required = False
        eng_why = "foreign already deterministically proven"
    elif code == "WORD_NOT_IN_ACTIVE_CONFIGIO":
        det_possible = False
        det_why = (
            "word absent from active Configio/EIP — cannot invent LOCAL endpoint; "
            "deterministic path exhausted without foreign Machine_Name or alternate binding"
        )
        # AI/Relay can hypothesize foreign/remote/legacy ranges but must not invent endpoints
        ai_possible = True
        ai_why = (
            "AI can cluster word-range ownership (foreign controller / remote I/O / legacy map) "
            "with cited evidence; must not invent LOCAL module endpoints"
        )
        relay_possible = True
        relay_why = (
            "Relay site-level audit can compare finished-site patterns for same nomenclature "
            "and word-range ownership; still cannot invent physical addresses"
        )
        eng_required = True
        eng_why = (
            "after cluster AI+Relay, LOCAL vs FOREIGN vs remote ownership for off-Configio "
            "words remains an engineer confirmation unless stronger RUN evidence appears"
        )
    elif code == "OWNERSHIP_UNRESOLVED" or not _norm(d.get("word")):
        det_possible = False
        det_why = "no word/bit and no explicit Machine_Name — insufficient deterministic binding"
        ai_possible = True
        ai_why = "AI may locate alternate evidence in EStop/Conveyor/safety tables if present"
        relay_possible = True
        relay_why = "Relay may find finished-site naming analogues"
        eng_required = True
        eng_why = "genuinely under-specified without word or machine claim"
    else:
        det_possible = False
        det_why = f"unresolved code={code or 'NONE'}"
        ai_possible = True
        ai_why = "possible cluster reasoning"
        relay_possible = True
        relay_why = "possible site audit"
        eng_required = True
        eng_why = "default: engineer after escalation ladder"

    # Typo / garbage names
    if name in {"ESPB1O"} or re.search(r"ESPB1O", name):
        eng_required = True
        eng_why = "likely OCR/typo candidate (ESPB1O) — engineer must confirm identity or drop"
        ai_possible = True
        ai_why = "AI can flag likely typo of ESPB10/ESPB1 but must not silently remap"

    if family == "SAFETY" and in_map is False:
        eng_why = (
            (eng_why + "; ") if eng_why else ""
        ) + "Safety membership must not be invented — engineer/zone assignment required for LOCAL claim"

    return {
        "deterministic_resolution_should_be_possible": det_possible,
        "deterministic_rationale": det_why,
        "ai_should_be_able_to_resolve": ai_possible,
        "ai_rationale": ai_why,
        "relay_should_be_able_to_resolve": relay_possible,
        "relay_rationale": relay_why,
        "engineer_confirmation_genuinely_required": eng_required,
        "engineer_rationale": eng_why,
    }


def _forensic_device(d: dict[str, Any], *, active_words: set[str], kb_pack: dict[str, Any]) -> dict[str, Any]:
    name = _norm(d.get("canonical_name"))
    family = _family_from_device(d)
    sem = _classify_equipment_safe(name, _norm(d.get("device_type")))
    kb_hits = _kb_matches(name, kb_pack)
    phys = _physical_world_evidence(d)
    own = _ownership_evidence(d, active_words)
    feas = _resolution_feasibility(d, own, phys)
    trace = d.get("escalation_trace") or {}
    return {
        "name": name,
        "device_family": family,
        "device_type": d.get("device_type"),
        "equipment_class": d.get("equipment_class") or sem.get("equipment_class"),
        "evidence_class": d.get("evidence_class"),
        "final_status": d.get("final_status"),
        "all_source_evidence": d.get("source_evidence") or [],
        "source_evidence_count": d.get("source_evidence_count") or len(d.get("source_evidence") or []),
        "physical_world_evidence": phys["physical_world_evidence"],
        "physical_world_evidence_reasons": phys["reasons"],
        "active_controller_ownership_evidence": own,
        "module": own.get("module"),
        "slot": own.get("slot"),
        "channel_or_endpoint": own.get("physical_endpoint"),
        "word": own.get("word"),
        "bit": own.get("bit"),
        "nomenclature_evidence": {
            "classifier": sem,
            "device_type": d.get("device_type"),
            "equipment_class": d.get("equipment_class"),
            "classifier_reasons": d.get("classifier_reasons") or sem.get("reasons"),
        },
        "known_fortna_pattern_match": {
            "matched": bool(sem.get("equipment_class") and sem.get("equipment_class") not in {"UNKNOWN", "AMBIGUOUS"}),
            "equipment_class": sem.get("equipment_class"),
            "confidence": sem.get("confidence"),
        },
        "knowledge_base_match": kb_hits,
        "likely_fortna_plus_representation": _fortna_plus_hint(d, kb_hits, sem),
        "current_reason_unresolved": d.get("reason"),
        "deterministic_code": d.get("deterministic_code"),
        "critical": bool(d.get("critical")),
        "escalation_trace_summary": {
            "cluster_id": trace.get("cluster_id"),
            "ai_api_called": trace.get("ai_api_called"),
            "relay_called": trace.get("relay_called"),
            "final_classification": trace.get("final_classification"),
            "engineer_confirmation_required": trace.get("engineer_confirmation_required"),
            "ai_validation": trace.get("ai_validation"),
            "relay_validation": trace.get("relay_validation"),
        },
        "engineer_confirmation": d.get("engineer_confirmation"),
        **feas,
    }


def _endpoint_key(endpoint: str = "", word: str = "", bit: str = "") -> str:
    ep = _norm(endpoint)
    if ep:
        return ep.upper()
    w, b = _norm(word), _norm(bit)
    if w and b != "":
        return f"WB:{w}.{b}"
    return ""


def _audit_occupancy(
    occ_rows: list[dict[str, Any]],
    devices: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Audit each unproven channel occupancy row — never call SPARE without proof."""
    # Index named device endpoints
    named_eps: dict[str, str] = {}
    named_wb: dict[str, str] = {}
    for d in devices:
        if _norm(d.get("device_type")) == "PHYSICAL_CHANNEL" and _norm(d.get("final_status")) == "SPARE_UNUSED":
            continue
        ek = _endpoint_key(d.get("physical_endpoint"), d.get("word"), d.get("bit"))
        if ek:
            named_eps[ek] = _norm(d.get("canonical_name"))
        wb = f"{_norm(d.get('word'))}.{_norm(d.get('bit'))}"
        if _norm(d.get("word")) and _norm(d.get("bit")) != "":
            named_wb[wb] = _norm(d.get("canonical_name"))
        for ch in d.get("channel_evidence") or []:
            cek = _endpoint_key(ch.get("endpoint"), ch.get("word"), ch.get("bit"))
            if cek:
                named_eps[cek] = _norm(d.get("canonical_name"))

    audited = []
    for r in occ_rows:
        ep = _norm(r.get("physical_endpoint") or r.get("source_signal"))
        word = _norm(r.get("word"))
        bit = _norm(r.get("bit"))
        ek = _endpoint_key(ep, word, bit)
        wb = f"{word}.{bit}" if word and bit != "" else ""
        owner = named_eps.get(ek) or named_wb.get(wb) or ""
        signal = _norm(r.get("source_signal"))
        signal_u = signal.upper()

        classification = "UNKNOWN"
        rationale = []
        is_endpoint_shaped = bool(
            re.match(r"^[A-Z][A-Z0-9_]*:\d*:?[IO]\.Data", signal, re.I)
            or re.match(r"^[A-Z][A-Z0-9_]*:\d*:?[IO]\.Data", ep, re.I)
            or signal_u.startswith("CH:")
        )

        if owner:
            classification = "REAL_OCCUPIED_FIELD_POINT"
            rationale.append(f"matches named device endpoint owner={owner}")
        elif signal_u in {"SPARE", "INVALID", "N/A", ""} or signal_u.startswith("SPARE"):
            # Explicit spare token would be proven — but these rows are in unproven bucket,
            # so if we see SPARE token here something inconsistent; still report.
            classification = "REAL_UNUSED_PHYSICAL_CHANNEL"
            rationale.append("explicit spare/invalid token on known module channel")
        elif is_endpoint_shaped:
            # Module channel exists as physical hardware capacity; RUN did not name a device
            # and did not explicitly mark SPARE — unproven unused candidate, NOT SPARE.
            classification = "REAL_UNUSED_PHYSICAL_CHANNEL"
            rationale.append(
                "known module/channel address present; no named occupant; "
                "no explicit SPARE token — occupancy capacity, not proven spare"
            )
        elif re.match(r"^MEM_", signal_u) or signal_u.endswith("_STATUS") or signal_u.endswith("_ENABLE"):
            classification = "INTERNAL_LOGICAL_EVIDENCE"
            rationale.append("internal/logical naming on channel row")
        else:
            classification = "UNKNOWN"
            rationale.append("insufficient evidence to classify occupancy row")

        # Duplicate noise: identical endpoint appearing with multiple source signals
        audited.append(
            {
                "occupancy_key": r.get("occupancy_key"),
                "source_signal": signal,
                "physical_endpoint": ep,
                "word": word,
                "bit": bit,
                "direction": _norm(r.get("direction")),
                "module": _norm(r.get("module")),
                "slot": _norm(r.get("slot")),
                "classification": classification,
                "named_occupant_if_any": owner or None,
                "rationale": rationale,
                "may_call_spare": classification == "REAL_UNUSED_PHYSICAL_CHANNEL"
                and (signal_u in {"SPARE", "INVALID", "N/A"} or signal_u.startswith("SPARE")),
                "note": (
                    "Do NOT classify as SPARE_UNUSED without explicit unused/spare proof"
                    if not (
                        signal_u in {"SPARE", "INVALID", "N/A"}
                        or signal_u.startswith("SPARE")
                    )
                    else "explicit spare token present"
                ),
            }
        )

    # Mark duplicate/source noise: same endpoint key appearing >1 with same classification
    by_ep: dict[str, list[int]] = defaultdict(list)
    for i, a in enumerate(audited):
        k = _endpoint_key(a.get("physical_endpoint"), a.get("word"), a.get("bit"))
        if k:
            by_ep[k].append(i)
    for k, idxs in by_ep.items():
        if len(idxs) > 1:
            for i in idxs:
                if audited[i]["classification"] not in {
                    "REAL_OCCUPIED_FIELD_POINT",
                    "INTERNAL_LOGICAL_EVIDENCE",
                }:
                    audited[i]["classification"] = "DUPLICATE_SOURCE_NOISE"
                    audited[i]["rationale"].append(
                        f"duplicate occupancy rows for same endpoint key={k} (count={len(idxs)})"
                    )

    return audited


def _proposed_improvements(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Generic resolver improvement proposals — NOT implemented."""
    unresolved = report.get("unresolved_physical_devices") or []
    occ = report.get("unproven_channel_occupancy_audit") or {}
    by_code = Counter(
        _norm(d.get("deterministic_code")) for d in unresolved
    )
    proposals = []

    if by_code.get("WORD_NOT_IN_ACTIVE_CONFIGIO", 0) >= 3:
        proposals.append(
            {
                "id": "GEN-IO-001",
                "title": "Off-Configio word-range ownership clustering (generic)",
                "problem": (
                    f"{by_code.get('WORD_NOT_IN_ACTIVE_CONFIGIO')} unresolved devices share "
                    "WORD_NOT_IN_ACTIVE_CONFIGIO — often contiguous word hundreds (1100s) "
                    "suggesting foreign/remote/legacy map ownership."
                ),
                "proposal": (
                    "Add a deterministic pre-AI cluster heuristic: group wildcard Machine_Name "
                    "claims by word-hundreds + device family; if ZERO words in the cluster appear "
                    "in active Configio AND peer machines in the same RUN claim overlapping ranges, "
                    "emit ownership=FOREIGN_CANDIDATE / REMOTE_IO_CANDIDATE with cited peer evidence "
                    "— still requiring engineer confirm before LOCAL map write."
                ),
                "does_not": "Invent physical endpoints or Safety zone membership",
                "priority": "HIGH",
            }
        )

    if any(d.get("name") == "ESPB1O" for d in unresolved):
        proposals.append(
            {
                "id": "GEN-IO-002",
                "title": "Nomenclature typo / OCR suspect gate",
                "problem": "ESPB1O looks like a typo of ESPB10/ESPB1 — currently treated as real Safety device.",
                "proposal": (
                    "Generic suspicious-identifier detector (O/0, I/1 confusable characters in "
                    "ESPB/ESLS/MCR/PB families) → flag REVIEW with suggested alternates; "
                    "never auto-rename."
                ),
                "does_not": "Silently remap or drop evidence",
                "priority": "MEDIUM",
            }
        )

    occ_summary = occ.get("by_classification") or {}
    if int(occ_summary.get("REAL_UNUSED_PHYSICAL_CHANNEL", 0) or 0) > 0:
        proposals.append(
            {
                "id": "GEN-IO-003",
                "title": "Module capacity vs proven-spare ledger split (already started)",
                "problem": (
                    f"{occ_summary.get('REAL_UNUSED_PHYSICAL_CHANNEL')} unproven unused channels "
                    "remain as occupancy — correct exclusion from resolution %, but engineers need "
                    "a capacity view separate from field-device resolution."
                ),
                "proposal": (
                    "Expose MODULE_CHANNEL_CAPACITY ledger in Hardware I/O: occupied / explicit-spare / "
                    "unnamed-unproven. Keep unnamed-unproven out of PHYSICAL_DEVICE_RESOLUTION denominator."
                ),
                "does_not": "Re-inflate resolution % by calling occupancy SPARE",
                "priority": "HIGH",
            }
        )

    if any(d.get("device_family") == "SAFETY" and d.get("word") for d in unresolved):
        proposals.append(
            {
                "id": "GEN-IO-004",
                "title": "Safety evidence union ≠ active-controller Configio binding",
                "problem": (
                    "Many ESPB/ESLS appear in EStop.asc / safety_model evidence with words "
                    "absent from active Configio — physical-world YES, ownership unresolved."
                ),
                "proposal": (
                    "Split Safety discovery into (a) SAFETY_CANDIDATE inventory from EStop/Conveyor "
                    "and (b) SAFETY_BOUND when PhysicalWordResolver proves module endpoint on the "
                    "active controller. Candidate inventory remains visible for engineer zone "
                    "assignment without blocking non-Safety PLC generation."
                ),
                "does_not": "Auto-assign Safety zones or invent Safe_PI members",
                "priority": "HIGH",
            }
        )

    pb = [d for d in unresolved if d.get("device_family") == "CONTROL_STATION_PUSHBUTTON"]
    if pb:
        proposals.append(
            {
                "id": "GEN-IO-005",
                "title": "Control-station PB semantic target without address invention",
                "problem": (
                    "PB6_JR / SS13P7 retain strong nomenclature (control station) but off-Configio words."
                ),
                "proposal": (
                    "When nomenclature proves CONTROL_STATION_* , record likely Fortna Plus UDT member "
                    "(CPx_CS.I.*) as semantic target while ownership stays REVIEW/FOREIGN until binding "
                    "evidence exists — improves workbench clarity without fake LOCAL maps."
                ),
                "does_not": "Write IO_MAP rows or L5X aliases without endpoint proof",
                "priority": "MEDIUM",
            }
        )

    proposals.append(
        {
            "id": "GEN-IO-006",
            "title": "Cross-machine Configio range index for foreign proof",
            "problem": "FOREIGN today requires explicit Machine_Name ≠ active; wildcard N/A blocks proof.",
            "proposal": (
                "Build a read-only index of all machines' Configio word ownership in the RUN. "
                "If word W is absent locally but present under Machine_Name=X in the same RUN, "
                "cite that as deterministic FOREIGN evidence for wildcard claims of W."
            ),
            "does_not": "Guess when word is absent from ALL machines",
            "priority": "HIGH",
        }
    )

    return proposals


def main() -> int:
    proof = {}
    if PROOF_JSON.is_file():
        proof = json.loads(PROOF_JSON.read_text(encoding="utf-8"))

    canon_path = LEDGER_DIR / "CANONICAL_PHYSICAL_DEVICE_LEDGER.json"
    if not canon_path.is_file():
        print(json.dumps({"error": "missing canonical ledger", "path": str(canon_path)}))
        return 2
    canon = json.loads(canon_path.read_text(encoding="utf-8"))
    devices = list(canon.get("devices") or [])
    occ_rows = list(canon.get("channel_occupancy_rows") or [])
    active_words = {str(w) for w in (canon.get("active_configio_words") or [])}

    # Optionally enrich active words from live RUN (read-only)
    run_dir = Path(proof.get("run_dir") or r"C:\dev\worktree\FortnaPlus\workspace\active\RUN")
    run_note = ""
    if run_dir.is_dir() and (run_dir / "project.cfg").is_file():
        try:
            from fortna_physical_word_resolver import PhysicalWordResolver

            pwr = PhysicalWordResolver(run_dir, "MSCRENOPICK")
            wm = pwr.io_word_map() or {}
            active_words |= {str(k) for k in wm.keys()}
            run_note = f"enriched active_configio_words from read-only RUN {run_dir} (n={len(wm)})"
        except Exception as ex:  # noqa: BLE001
            run_note = f"RUN present but resolver enrich failed: {ex}"[:240]
    else:
        run_note = "live RUN not available in analysis worktree; using ledger active_configio_words only"

    kb_pack = _load_kb()

    unresolved_statuses = {"REVIEW_REQUIRED", "ENGINEER_CONFIRM_REQUIRED"}
    unresolved = [
        d
        for d in devices
        if _norm(d.get("final_status")).split(":")[0] in unresolved_statuses
        and _family_from_device(d) != "INTERNAL_LOGICAL"
    ]
    # Also include focus devices even if resolved (SS13P9 FOREIGN, ESPB22 confirmed)
    focus_names = {"PB6_JR", "SS13P7", "SS13P9"}
    focus_devices = [
        d for d in devices if _norm(d.get("canonical_name")).upper() in focus_names
    ]
    safety_all = [
        d
        for d in devices
        if _family_from_device(d) == "SAFETY"
        or _norm(d.get("device_type")).upper() in {"ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP"}
    ]
    safety_unresolved = [
        d
        for d in safety_all
        if _norm(d.get("final_status")).split(":")[0] in unresolved_statuses
    ]

    forensic_unresolved = [
        _forensic_device(d, active_words=active_words, kb_pack=kb_pack) for d in unresolved
    ]
    forensic_focus = [
        _forensic_device(d, active_words=active_words, kb_pack=kb_pack) for d in focus_devices
    ]
    forensic_safety_unresolved = [
        _forensic_device(d, active_words=active_words, kb_pack=kb_pack) for d in safety_unresolved
    ]
    forensic_safety_all = [
        {
            "name": _norm(d.get("canonical_name")),
            "device_family": _family_from_device(d),
            "device_type": d.get("device_type"),
            "final_status": d.get("final_status"),
            "ownership": d.get("ownership"),
            "word": d.get("word"),
            "bit": d.get("bit"),
            "physical_endpoint": d.get("physical_endpoint"),
            "deterministic_code": d.get("deterministic_code"),
            "reason": d.get("reason"),
            "assignable": d.get("assignable"),
        }
        for d in safety_all
    ]

    occ_audit = _audit_occupancy(occ_rows, devices)
    occ_by = Counter(a["classification"] for a in occ_audit)
    spare_calls = sum(1 for a in occ_audit if a.get("may_call_spare"))

    family_counts = Counter(f["device_family"] for f in forensic_unresolved)
    eng_genuinely = sum(
        1 for f in forensic_unresolved if f.get("engineer_confirmation_genuinely_required")
    )
    det_possible_n = sum(
        1 for f in forensic_unresolved if f.get("deterministic_resolution_should_be_possible")
    )

    # Percentage decomposition (explanation only — not optimization)
    unique_phys = int(canon.get("unique_physical_devices") or 0)
    mapped = int(canon.get("unique_mapped") or 0)
    review = int(canon.get("unique_review") or 0)
    unsupported = int(canon.get("unique_unsupported") or 0)
    eng_conf = int(canon.get("unique_engineer_confirmed") or 0)
    proven_spare = int(canon.get("proven_physical_spares") or canon.get("unique_spare") or 0)
    foreign = int(canon.get("unique_foreign") or 0)
    resolved_phys = mapped + proven_spare + unsupported + eng_conf
    # Note: FOREIGN excluded from physical denom by design

    report: dict[str, Any] = {
        "ori": "MSCRENOPICK_IO_FORENSICS",
        "mission": "FORENSIC_EVIDENCE_ONLY",
        "frozen_qualification_sha": FROZEN_SHA,
        "analysis_branch": "analysis/mscrenopick-io-forensics",
        "built_at": _ts(),
        "do_not_disturb_qualification": True,
        "no_production_code_changes": True,
        "run_enrichment_note": run_note,
        "headline_metrics_explained": {
            "SOURCE_CONSERVATION_PCT": canon.get("SOURCE_CONSERVATION_PCT") or proof.get("SOURCE_CONSERVATION_PCT"),
            "PHYSICAL_DEVICE_RESOLUTION_PCT": canon.get("PHYSICAL_DEVICE_RESOLUTION_PCT")
            or proof.get("PHYSICAL_DEVICE_RESOLUTION_PCT"),
            "GENERATED_PHYSICAL_IO_PCT": canon.get("GENERATED_PHYSICAL_IO_PCT")
            or proof.get("GENERATED_PHYSICAL_IO_PCT"),
            "decomposition": {
                "unique_physical_devices_denominator": unique_phys,
                "mapped": mapped,
                "engineer_confirmed": eng_conf,
                "unsupported": unsupported,
                "proven_spares": proven_spare,
                "review_engineer_confirm_required": review,
                "resolved_count_in_physical_denom": resolved_phys,
                "resolution_pct_check": round(100.0 * resolved_phys / max(1, unique_phys), 2),
                "foreign_excluded_from_physical_denom": foreign,
                "unproven_channel_occupancy_excluded": int(
                    canon.get("unproven_channel_occupancy") or 0
                ),
                "why_not_86pct": (
                    "Prior 86.45% counted 128 unoccupied module channels as SPARE_UNUSED resolved. "
                    "Those are now occupancy-excluded; physical denom is named field devices only."
                ),
                "why_generated_low": (
                    "GENERATED_PHYSICAL_IO_PCT = mapped named field devices / named physical field devices. "
                    f"Only {mapped} mapped of ~{unique_phys - proven_spare} named physical candidates."
                ),
            },
        },
        "family_counts_unresolved": dict(family_counts),
        "unresolved_summary": {
            "count": len(forensic_unresolved),
            "engineer_confirmation_genuinely_required_count": eng_genuinely,
            "deterministic_should_be_possible_count": det_possible_n,
            "by_deterministic_code": dict(
                Counter(_norm(d.get("deterministic_code")) for d in forensic_unresolved)
            ),
        },
        "focus_pushbuttons": forensic_focus,
        "unresolved_physical_devices": forensic_unresolved,
        "safety_population": {
            "unique_total": len(safety_all),
            "unresolved_count": len(safety_unresolved),
            "by_status": dict(Counter(_norm(d.get("final_status")).split(":")[0] for d in safety_all)),
            "all_devices": forensic_safety_all,
            "unresolved_forensics": forensic_safety_unresolved,
        },
        "unproven_channel_occupancy_audit": {
            "total": len(occ_audit),
            "by_classification": dict(occ_by),
            "explicit_spare_token_count": spare_calls,
            "note": (
                "REAL_UNUSED_PHYSICAL_CHANNEL without explicit spare token is module capacity, "
                "NOT proven SPARE_UNUSED."
            ),
            "rows": occ_audit,
        },
        "proposed_generic_resolver_improvements": [],  # filled below
        "active_configio_words_sample": sorted(active_words)[:80],
        "active_configio_word_count": len(active_words),
    }
    report["proposed_generic_resolver_improvements"] = _proposed_improvements(report)

    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    OUT_TXT.write_text(_render_txt(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "json": str(OUT_JSON),
                "txt": str(OUT_TXT),
                "unresolved": len(forensic_unresolved),
                "occupancy": len(occ_audit),
                "occ_classes": dict(occ_by),
                "proposals": len(report["proposed_generic_resolver_improvements"]),
                "frozen_sha_untouched": FROZEN_SHA,
            },
            indent=2,
        )
    )
    return 0


def _render_txt(report: dict[str, Any]) -> str:
    lines: list[str] = []
    w = lines.append
    w("=" * 78)
    w("MSCRENOPICK I/O FORENSICS — EVIDENCE ONLY")
    w("=" * 78)
    w(f"Frozen qualification SHA: {report['frozen_qualification_sha']}")
    w(f"Analysis branch:          {report['analysis_branch']}")
    w(f"Built at:                 {report['built_at']}")
    w("NO production code changes. Qualification SHA not disturbed.")
    w("")
    hm = report["headline_metrics_explained"]
    w("--- HEADLINE METRICS (explained, not optimized) ---")
    w(f"  SOURCE CONSERVATION %:        {hm.get('SOURCE_CONSERVATION_PCT')}")
    w(f"  PHYSICAL DEVICE RESOLUTION %: {hm.get('PHYSICAL_DEVICE_RESOLUTION_PCT')}")
    w(f"  GENERATED PHYSICAL I/O %:     {hm.get('GENERATED_PHYSICAL_IO_PCT')}")
    dec = hm.get("decomposition") or {}
    w(f"  physical denom: {dec.get('unique_physical_devices_denominator')}")
    w(f"    mapped={dec.get('mapped')} eng_confirmed={dec.get('engineer_confirmed')} "
      f"unsupported={dec.get('unsupported')} proven_spare={dec.get('proven_spares')} "
      f"review={dec.get('review_engineer_confirm_required')}")
    w(f"  foreign excluded: {dec.get('foreign_excluded_from_physical_denom')}")
    w(f"  unproven occupancy excluded: {dec.get('unproven_channel_occupancy_excluded')}")
    w(f"  WHY NOT 86%: {dec.get('why_not_86pct')}")
    w(f"  WHY GENERATED LOW: {dec.get('why_generated_low')}")
    w("")
    w(f"RUN note: {report.get('run_enrichment_note')}")
    w(f"Active Configio words: {report.get('active_configio_word_count')} "
      f"(sample: {', '.join(report.get('active_configio_words_sample') or [])})")
    w("")
    w("--- UNRESOLVED FAMILY COUNTS ---")
    for fam, n in sorted((report.get("family_counts_unresolved") or {}).items()):
        w(f"  {fam}: {n}")
    us = report.get("unresolved_summary") or {}
    w(f"  TOTAL unresolved: {us.get('count')}")
    w(f"  engineer genuinely required: {us.get('engineer_confirmation_genuinely_required_count')}")
    w(f"  deterministic should be possible: {us.get('deterministic_should_be_possible_count')}")
    w(f"  by code: {us.get('by_deterministic_code')}")
    w("")
    w("--- FOCUS: PB6_JR / SS13P7 / SS13P9 ---")
    for d in report.get("focus_pushbuttons") or []:
        w(f"  [{d.get('name')}] family={d.get('device_family')} status={d.get('final_status')}")
        w(f"    physical_world={d.get('physical_world_evidence')} "
          f"ownership={d.get('active_controller_ownership_evidence', {}).get('active_controller_claim')}")
        w(f"    word={d.get('word')} bit={d.get('bit')} endpoint={d.get('channel_or_endpoint') or '—'}")
        w(f"    reason: {d.get('current_reason_unresolved')}")
        w(f"    Fortna Plus hint: {d.get('likely_fortna_plus_representation') or '—'}")
        w(f"    det_possible={d.get('deterministic_resolution_should_be_possible')} "
          f"ai={d.get('ai_should_be_able_to_resolve')} "
          f"relay={d.get('relay_should_be_able_to_resolve')} "
          f"eng_required={d.get('engineer_confirmation_genuinely_required')}")
        w(f"    eng_why: {d.get('engineer_rationale')}")
        w(f"    source_evidence_count={d.get('source_evidence_count')}")
        for s in (d.get("all_source_evidence") or [])[:5]:
            w(f"      - {s.get('source_type')} @ {s.get('source_file')} "
              f"mach={s.get('machine')} {s.get('word')}.{s.get('bit')} → {s.get('final_status')}")
        w("")
    w("--- SAFETY POPULATION ---")
    sp = report.get("safety_population") or {}
    w(f"  unique_total={sp.get('unique_total')} unresolved={sp.get('unresolved_count')} "
      f"by_status={sp.get('by_status')}")
    for d in sp.get("unresolved_forensics") or []:
        w(f"  [{d.get('name')}] {d.get('device_type')} word={d.get('word')}.{d.get('bit')} "
          f"code={d.get('deterministic_code')} phys={d.get('physical_world_evidence')} "
          f"eng_required={d.get('engineer_confirmation_genuinely_required')}")
        w(f"    reason: {d.get('current_reason_unresolved')}")
        w(f"    hint: {d.get('likely_fortna_plus_representation') or '—'}")
    w("")
    w("--- ALL UNRESOLVED PHYSICAL DEVICES ---")
    for d in report.get("unresolved_physical_devices") or []:
        w(f"  [{d.get('name')}] family={d.get('device_family')} status={d.get('final_status')}")
        w(f"    phys={d.get('physical_world_evidence')} code={d.get('deterministic_code')} "
          f"word={d.get('word')}.{d.get('bit')} ep={d.get('channel_or_endpoint') or '—'}")
        w(f"    det={d.get('deterministic_resolution_should_be_possible')} "
          f"ai={d.get('ai_should_be_able_to_resolve')} "
          f"relay={d.get('relay_should_be_able_to_resolve')} "
          f"eng={d.get('engineer_confirmation_genuinely_required')}")
        w(f"    why_eng: {d.get('engineer_rationale')}")
        kb = d.get("knowledge_base_match") or []
        if kb:
            w(f"    KB: {', '.join(_norm(x.get('pattern_key')) for x in kb[:3])}")
    w("")
    occ = report.get("unproven_channel_occupancy_audit") or {}
    w("--- UNPROVEN CHANNEL OCCUPANCY AUDIT (128) ---")
    w(f"  total={occ.get('total')} by_class={occ.get('by_classification')}")
    w(f"  explicit_spare_token_count={occ.get('explicit_spare_token_count')}")
    w(f"  NOTE: {occ.get('note')}")
    # Summarize modules
    mod_c: Counter[str] = Counter()
    for r in occ.get("rows") or []:
        mod = _norm(r.get("module")) or _norm(r.get("physical_endpoint")).split(":")[0]
        mod_c[mod or "?"] += 1
    w("  by module/prefix:")
    for m, n in mod_c.most_common(20):
        w(f"    {m}: {n}")
    w("")
    w("--- PROPOSED GENERIC RESOLVER IMPROVEMENTS (NOT IMPLEMENTED) ---")
    for p in report.get("proposed_generic_resolver_improvements") or []:
        w(f"  {p.get('id')} [{p.get('priority')}] {p.get('title')}")
        w(f"    problem:  {p.get('problem')}")
        w(f"    proposal: {p.get('proposal')}")
        w(f"    does_not: {p.get('does_not')}")
        w("")
    w("=" * 78)
    w("END FORENSICS")
    w("=" * 78)
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
