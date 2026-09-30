#!/usr/bin/env python3
"""Equipment-aware I/O binding — device vs signal (raw Fortna names immutable).

Canonical identities are DERIVED. Raw IO_Name / sourceName are never rewritten.

Production rules (site-free; finished L5X is validation-only):
  motor_starter_aux_to_ms_udt
      M{stem}_AUX → P{stem}_MS.I.Auxiliary_Forward (Motor_Starter_UDT)
  motor_out_to_conv_run
      M{stem} OUT → P{stem}_Conv.O.Run (Conv_UDT) when conveyor lineage proven
      else REVIEW_REQUIRED (never Motor_Starter_UDT.O.Run for physical outs)
  power_supply_pws_to_ps_udt
  air_pressure_ps_to_airpress_udt
  estop_to_es_udt / pe_to_pe_udt / cs_to_cs_udt

Known-family + unresolved member → REVIEW_REQUIRED (never silent BOOL).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable, Mapping, Sequence

RULE_MOTOR_AUX = "motor_starter_aux_to_ms_udt"
RULE_MOTOR_OUT_CONV = "motor_out_to_conv_run"
RULE_MOTOR_M_TO_P = "motor_starter_m_to_p_canonicalization"  # legacy alias retained
RULE_POWER_SUPPLY = "power_supply_pws_to_ps_udt"
RULE_AIR_PRESSURE = "air_pressure_ps_to_airpress_udt"
RULE_ESTOP = "estop_to_es_udt"
RULE_PE = "pe_to_pe_udt"
RULE_CS = "cs_to_cs_udt"
RULE_CONV = "conveyor_to_conv_udt"

CLASS_MOTOR_STARTER = "MOTOR_STARTER"
CLASS_CONVEYOR = "CONVEYOR"
CLASS_POWER_SUPPLY = "POWER_SUPPLY"
CLASS_AIR_PRESSURE = "AIR_PRESSURE_SWITCH"
CLASS_ESTOP = "ESTOP"
CLASS_PHOTOEYE = "PHOTOEYE"
CLASS_CONTROL_STATION = "CONTROL_STATION"
CLASS_VFD = "VFD"
CLASS_MDR = "MDR"

UDT_MOTOR_STARTER = "Motor_Starter_UDT"
UDT_CONV = "Conv_UDT"
UDT_PS = "PS_UDT"
UDT_AIR = "AirPressure_Switch_UDT"
UDT_ES = "ES_UDT"
UDT_PE = "PE_UDT"
UDT_CS = "CS_UDT"

MEMBER_RUN = "O.Run"
MEMBER_RELEASE = "O.Release"
MEMBER_AUX_FWD = "I.Auxiliary_Forward"
MEMBER_PS_OK = "I.PS_OK"
MEMBER_PRESSURE_OK = "I.Pressure_OK"
MEMBER_ES_OK = "I.ES_OK"
MEMBER_PE_CLEAR = "I.PE_Clear"
MEMBER_CS = {
    "START_PB": "I.Start_PB",
    "STOP_PB": "I.Stop_PB",
    "RESET_PB": "I.Reset_PB",
    "START_PB_LT": "O.Start_PB_LT",
    "STOP_PB_LT": "O.Stop_PB_LT",
    "HORN": "O.Horn",
    "RED": "O.Red",
}

# Canonical ES_UDT schema — scalar BOOL/BIT feedback member only.
# Never invent member names; only emit paths present in this schema.
ES_UDT_SCHEMA: dict[str, Any] = {
    "udt_type": UDT_ES,
    "bool_members": {
        "ES_OK": MEMBER_ES_OK,
        "FEEDBACK": MEMBER_ES_OK,
        "AUX": MEMBER_ES_OK,
        "AUX_FEEDBACK": MEMBER_ES_OK,
        "PRIMARY": MEMBER_ES_OK,  # ESTOP/ESLS/ESR device root is the feedback signal
        "RELATED": MEMBER_ES_OK,
    },
    "member_data_types": {
        MEMBER_ES_OK: "BIT",  # BOOL-compatible
    },
}
_ES_FEEDBACK_KINDS = frozenset({"ESTOP", "ESLS", "ESR"})
_ES_FEEDBACK_ROLES = frozenset(
    {"ES_OK", "FEEDBACK", "AUX", "AUX_FEEDBACK", "PRIMARY", "RELATED"}
)
_MCR_FEEDBACK_ROLES = frozenset({"ES_OK", "FEEDBACK", "AUX", "AUX_FEEDBACK", "RELATED"})

_MOTOR_BASE_RE = re.compile(r"^M([0-9]+[A-Z]?)$", re.I)
_MOTOR_AUX_RE = re.compile(r"^M([0-9]+[A-Z]?)_AUX$", re.I)
_MDR_RE = re.compile(r"^MDR", re.I)
_VFD_RE = re.compile(r"^VFD\d|^VFD_|^PF\d", re.I)
_PWS_RE = re.compile(r"^(?:EZ)?PWS", re.I)
_PS_NAME_RE = re.compile(r"^PS\d", re.I)
_PE_RE = re.compile(r"^(?:EZ)?PE\d", re.I)
# Legacy prefix hint retained for callers that still probe _ES_RE; semantic
# resolution uses fortna_safety_model._classify_device / _signal_parse.
_ES_RE = re.compile(
    r"^(?:T_)?(?:ES\d|ESLS\d|ESPB\d|ESTP\d|\d+ES\d*$|\d+(?:MCR|ESR)\d*)",
    re.I,
)
_CS_PB_RE = re.compile(r"^(\d+)PB(START|STOP|RESET)(_PLT)?$", re.I)
_CONV_FROM_DESC_RE = re.compile(
    r"(?:CONVEYOR|CONV)\s+([A-Z]{1,3}\d+[A-Z]?)\b", re.I
)
_P_TAG_RE = re.compile(r"^P\d+[A-Z]?(?:_P\d+)?$", re.I)

_ROLE_MEMBER = {
    "AUXILIARY_FORWARD": MEMBER_AUX_FWD,
    "CONVEYOR_RUN": MEMBER_RUN,
    "CONVEYOR_RELEASE": MEMBER_RELEASE,
    "PS_OK": MEMBER_PS_OK,
    "PRESSURE_OK": MEMBER_PRESSURE_OK,
    "ES_OK": MEMBER_ES_OK,
    "PE_CLEAR": MEMBER_PE_CLEAR,
    **MEMBER_CS,
}


@dataclass
class EquipmentSignal:
    role: str
    raw_name: str
    direction: str = ""
    physical_endpoint: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EquipmentDevice:
    """Canonical equipment object owning one or more raw signals."""

    canonical_id: str
    logix_tag: str
    equipment_class: str
    datatype: str
    rule: str
    signals: dict[str, EquipmentSignal] = field(default_factory=dict)
    driven_conveyor: str = ""
    driven_conveyor_provenance: str = ""
    confidence: str = "PROVEN"
    review_reason: str = ""
    machine: str = ""
    archive_sha: str = ""
    source_fact_uids: list[str] = field(default_factory=list)
    raw_names: list[str] = field(default_factory=list)

    def member_for_role(self, role: str) -> str:
        return _ROLE_MEMBER.get(role, "")

    def member_path(self, role: str) -> str:
        member = self.member_for_role(role)
        if not member or not self.logix_tag:
            return ""
        return f"{self.logix_tag}.{member}"

    def display_for_raw(self, raw_name: str) -> str:
        raw_u = (raw_name or "").strip().upper()
        for role, sig in self.signals.items():
            if (sig.raw_name or "").strip().upper() == raw_u:
                return self.member_path(role)
        return ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "logix_tag": self.logix_tag,
            "equipment_class": self.equipment_class,
            "datatype": self.datatype,
            "rule": self.rule,
            "signals": {k: v.to_dict() for k, v in self.signals.items()},
            "driven_conveyor": self.driven_conveyor,
            "driven_conveyor_provenance": self.driven_conveyor_provenance,
            "confidence": self.confidence,
            "review_reason": self.review_reason,
            "machine": self.machine,
            "archive_sha": self.archive_sha,
            "source_fact_uids": list(self.source_fact_uids),
            "raw_names": list(self.raw_names),
        }


def parse_motor_starter_name(io_name: str) -> dict[str, str] | None:
    """Parse strict discrete starter name. None for MDR/VFD/other."""
    n = (io_name or "").strip()
    if not n or _MDR_RE.match(n) or _VFD_RE.match(n):
        return None
    m = _MOTOR_AUX_RE.match(n)
    if m:
        stem = m.group(1).upper()
        return {
            "raw": n,
            "stem": stem,
            "role": "AUXILIARY_FORWARD",
            "canonical_id": f"P{stem}",
            "raw_base": f"M{stem}",
        }
    m = _MOTOR_BASE_RE.match(n)
    if m:
        stem = m.group(1).upper()
        return {
            "raw": n,
            "stem": stem,
            "role": "RUN_COMMAND",
            "canonical_id": f"P{stem}",
            "raw_base": f"M{stem}",
        }
    return None


def extract_driven_conveyor(description: str = "", motor_field: str = "") -> tuple[str, str]:
    """Best-effort driven conveyor from description (not from M→P identity)."""
    desc = description or ""
    m = _CONV_FROM_DESC_RE.search(desc)
    if m:
        return m.group(1).upper(), "Conveyor.General_Description"
    mf = (motor_field or "").strip().upper()
    if re.match(r"^(?:MP|P|C)\d+[A-Z]?$", mf):
        return mf, "Conveyor.Motor"
    return "", ""


def choose_motor_ms_tag(canonical_id: str) -> str:
    """Motor_Starter_UDT Logix tag is always P{stem}_MS (oracle contract)."""
    bare = (canonical_id or "").strip()
    if not bare:
        return ""
    if bare.upper().endswith("_MS"):
        return bare
    return f"{bare}_MS"


def choose_motor_logix_tag(
    canonical_id: str,
    *,
    reserved_bare_tags: Iterable[str] | None = None,
) -> str:
    """Compatibility wrapper — MS tags always use _MS suffix (oracle-aligned)."""
    _ = reserved_bare_tags  # retained for call-site compatibility
    return choose_motor_ms_tag(canonical_id)


def choose_conveyor_run_tag(
    stem: str,
    *,
    known_convs: Iterable[str] | None = None,
    driven_conveyor: str = "",
    section_model: dict | None = None,
    motor_name: str = "",
) -> tuple[str, str, str]:
    """Resolve Conv_UDT tag for physical motor RUN ownership.

    Returns (logix_tag, confidence, review_reason).
    Proven when P{stem} (or exact driven P-tag) exists in known conveyors.

    When bare P{stem} is absent but lettered sections share the motor in the
    CURRENT RUN section model, pick the unique highest-confidence owner
    (PROVEN_RUN over PROVEN_CROSS_TABLE). Multiple peers at the same tier →
    REVIEW_REQUIRED (do not guess from prints).
    """
    known = {(t or "").strip().upper() for t in (known_convs or []) if t}
    stem_u = (stem or "").strip().upper()
    cand = f"P{stem_u}"
    if cand in known:
        return f"{cand}_Conv", "PROVEN", ""
    # Assembly sections P136_P1 etc.
    p1 = f"{cand}_P1"
    if p1 in known:
        return f"{p1}_Conv", "PROVEN", ""
    driven = (driven_conveyor or "").strip().upper()
    if driven and _P_TAG_RE.match(driven) and driven in known:
        return f"{driven}_Conv", "PROVEN", ""
    if driven and _P_TAG_RE.match(driven):
        # Description names a P-tag conveyor not in known set → DERIVED/REVIEW
        return f"{driven}_Conv", "REVIEW_REQUIRED", "CONVEYOR_LINEAGE_NOT_IN_KNOWN_CONVS"

    # CURRENT RUN section-model ownership (e.g. M120 → P120C PROVEN_RUN)
    owner, own_conf, own_reason = resolve_motor_section_owner(
        motor_name=motor_name or f"M{stem_u}",
        stem=stem_u,
        known_convs=known,
        section_model=section_model,
    )
    if owner and own_conf in {"PROVEN", "PROVEN_RUN"}:
        return f"{owner}_Conv", "PROVEN", own_reason
    if owner and own_conf == "REVIEW_REQUIRED":
        return "", "REVIEW_REQUIRED", own_reason
    return "", "REVIEW_REQUIRED", "MOTOR_OUT_NO_CONVEYOR_LINEAGE"


_CONF_TIER = {
    "PROVEN_RUN": 3,
    "PROVEN": 3,
    "PROVEN_CROSS_TABLE": 2,
    "DOC_DEFINED": 1,
    "UNRESOLVED": 0,
    "REVIEW_REQUIRED": 0,
}


def resolve_motor_section_owner(
    *,
    motor_name: str,
    stem: str = "",
    known_convs: Iterable[str] | None = None,
    section_model: dict | None = None,
) -> tuple[str, str, str]:
    """Re-derive motor→section RUN ownership from CURRENT section model evidence.

    Returns (section_id, confidence, provenance_reason).
    Unique top-tier claimant → that section. Ambiguous peers → REVIEW_REQUIRED.
    """
    known = {(t or "").strip().upper() for t in (known_convs or []) if t}
    mot = (motor_name or "").strip().upper()
    if not mot:
        stem_u = (stem or "").strip().upper()
        mot = f"M{stem_u}" if stem_u else ""
    if not mot:
        return "", "REVIEW_REQUIRED", "MOTOR_NAME_EMPTY"
    sm = section_model if isinstance(section_model, dict) else {}
    sections = sm.get("sections") if isinstance(sm.get("sections"), dict) else {}
    claimants: list[tuple[str, str, int, list]] = []
    for sid, info in sections.items():
        su = str(sid or "").strip().upper()
        if not su or not _P_TAG_RE.match(su):
            continue
        if known and su not in known:
            continue
        if not isinstance(info, dict):
            continue
        sec_mot = str(info.get("motor") or "").strip().upper()
        prov = list(info.get("provenance") or [])
        mentions = sec_mot == mot or any(
            str(p.get("motor") or "").strip().upper() == mot
            for p in prov
            if isinstance(p, dict)
        )
        if not mentions:
            continue
        conf = str(info.get("confidence") or "UNRESOLVED").upper()
        tier = _CONF_TIER.get(conf, 0)
        claimants.append((su, conf, tier, prov))
    if not claimants:
        return "", "REVIEW_REQUIRED", f"NO_SECTION_CLAIMS_{mot}"
    best_tier = max(c[2] for c in claimants)
    top = [c for c in claimants if c[2] == best_tier]
    if len(top) != 1:
        peers = ",".join(sorted(c[0] for c in top))
        return (
            "",
            "REVIEW_REQUIRED",
            f"AMBIGUOUS_MOTOR_OWNERSHIP:{mot}->[{peers}] tier={best_tier}",
        )
    su, conf, _tier, prov = top[0]
    kinds = [
        str(p.get("kind") or "")
        for p in prov
        if isinstance(p, dict)
        and str(p.get("motor") or "").strip().upper() in {"", mot}
    ]
    reason = (
        f"SECTION_MODEL:{mot}->{su} confidence={conf} "
        f"provenance_kinds={','.join(k for k in kinds if k) or 'section.motor'}"
    )
    # Normalize to PROVEN when PROVEN_RUN / PROVEN
    out_conf = "PROVEN" if _CONF_TIER.get(conf, 0) >= 3 else conf
    if out_conf != "PROVEN":
        # Cross-table-only unique claim still needs review before forcing writer
        return su, "REVIEW_REQUIRED", reason + "|CROSS_TABLE_ONLY"
    return su, out_conf, reason


def classify_power_or_air(
    io_name: str,
    description: str = "",
    device_type: str = "",
) -> dict[str, str] | None:
    """Classify POWER_SUPPLY vs AIR_PRESSURE_SWITCH. Never PS-prefix alone."""
    name = (io_name or "").strip()
    name_u = name.upper()
    desc_u = (description or "").upper()
    if not name:
        return None

    if _PWS_RE.match(name) or "POWER SUPPLY" in desc_u or "PWR SUPPLY" in desc_u or "POWER SUP" in desc_u:
        if _PS_NAME_RE.match(name) and (
            "AIR" in desc_u or "PRESSURE" in desc_u
        ) and "POWER" not in desc_u:
            pass
        else:
            if _PWS_RE.match(name) or "POWER" in desc_u:
                return {
                    "raw": name,
                    "equipment_class": CLASS_POWER_SUPPLY,
                    "datatype": UDT_PS,
                    "role": "PS_OK",
                    "member": MEMBER_PS_OK,
                    "canonical_id": name,
                    "rule": RULE_POWER_SUPPLY,
                    "confidence": "PROVEN",
                }

    if _PS_NAME_RE.match(name):
        if "AIR" in desc_u or "PRESSURE" in desc_u:
            return {
                "raw": name,
                "equipment_class": CLASS_AIR_PRESSURE,
                "datatype": UDT_AIR,
                "role": "PRESSURE_OK",
                "member": MEMBER_PRESSURE_OK,
                "canonical_id": name,
                "rule": RULE_AIR_PRESSURE,
                "confidence": "PROVEN",
            }
        return {
            "raw": name,
            "equipment_class": "UNKNOWN_PS_PREFIX",
            "datatype": "",
            "role": "",
            "member": "",
            "canonical_id": name,
            "rule": "",
            "confidence": "REVIEW_REQUIRED",
            "review_reason": "PS_PREFIX_AMBIGUOUS_NO_AIR_OR_POWER_EVIDENCE",
        }
    return None


def resolve_safety_bit_writer(
    signal_name: str,
    *,
    kind: str = "",
    signal_role: str = "",
    direction: str = "",
    device_type: str = "",
    description: str = "",
    udt_schema: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve physical Safety signal → scalar BOOL/BIT writer target.

    Architecture:
      physical signal → canonical signal role → scalar PLC member

    Driven by safety_model kind/role + UDT/member schema. Never prefix-regex
    alone, and never guess a member name. A name ending in _AUX is a signal
    role clue only after model/schema classification — not a device root.

    Returns dict with:
      target_tag, target_data_type, source_signal_role, confidence,
      provenance, udt_base, udt_type, member, emit, review_reason
    """
    empty = {
        "target_tag": "",
        "target_data_type": "",
        "source_signal_role": "",
        "confidence": "UNRESOLVED",
        "provenance": "",
        "udt_base": "",
        "udt_type": "",
        "member": "",
        "emit": False,
        "review_reason": "",
        "raw": (signal_name or "").strip(),
        "equipment_class": "",
        "datatype": "",
        "canonical_id": (signal_name or "").strip(),
        "rule": RULE_ESTOP,
    }
    name = (signal_name or "").strip()
    if not name:
        return empty

    if udt_schema is None:
        schema = dict(ES_UDT_SCHEMA)
    else:
        schema = dict(udt_schema)
    if "bool_members" in schema:
        bool_members = dict(schema.get("bool_members") or {})
    else:
        bool_members = dict(ES_UDT_SCHEMA["bool_members"])
    if "member_data_types" in schema:
        member_types = dict(schema.get("member_data_types") or {})
    else:
        member_types = dict(ES_UDT_SCHEMA["member_data_types"])
    udt_type = str(schema.get("udt_type") or UDT_ES)

    typ = (device_type or "").strip().upper()
    desc_u = (description or "").upper()
    d = (direction or "").strip().upper()
    explicit_kind = (kind or "").strip().upper()
    explicit_role = (signal_role or "").strip().upper()

    # Semantic classification from canonical safety model (site-spelling agnostic).
    parsed: dict[str, str] = {
        "kind": "",
        "signal_role": "",
        "stem": "",
        "disposition": "REJECTED",
    }
    try:
        from fortna_safety_model import _classify_device, _signal_parse

        model_kind = explicit_kind or _classify_device(name)
        parsed = _signal_parse(name, model_kind)
    except Exception:
        model_kind = explicit_kind
        parsed = {
            "kind": model_kind,
            "signal_role": explicit_role or "PRIMARY",
            "stem": name,
            "disposition": "SIGNAL" if model_kind else "REJECTED",
        }

    resolved_kind = (
        explicit_kind
        or str(parsed.get("kind") or "").strip().upper()
        or (
            "ESTOP"
            if typ in {"ESTOP", "E-STOP", "ES", "ESLS", "ESR"}
            or "E-STOP" in desc_u
            or "ESTOP" in desc_u
            else ""
        )
    )
    resolved_role = (
        explicit_role or str(parsed.get("signal_role") or "").strip().upper() or "PRIMARY"
    )

    # Opaque rename path: explicit kind+role+schema without model name match.
    if not resolved_kind and explicit_kind:
        resolved_kind = explicit_kind
    if not resolved_kind:
        return {**empty, "review_reason": "NO_SAFETY_KIND"}

    # INT_* never becomes a Safety UDT writer.
    u = name.upper().replace("-", "_")
    if u.startswith("INT_"):
        return {**empty, "review_reason": "INTERLOCK_NOT_SAFETY_DEVICE"}

    # MCR energize coil (COMMAND / PRIMARY without AUX) is BOOL coil — not ES_UDT.
    if resolved_kind == "MCR" and resolved_role not in _MCR_FEEDBACK_ROLES:
        if d in {"O", "OUT", "OUTPUT"} or "ENERGIZE" in desc_u or "OA" in typ:
            return {
                **empty,
                "source_signal_role": "COMMAND",
                "confidence": "UNRESOLVED",
                "provenance": "mcr_command_coil_not_es_udt",
                "review_reason": "MCR_COMMAND_COIL",
                "equipment_class": CLASS_ESTOP,
            }
        if d in {"I", "IN", "INPUT"} or typ in {"ESTOP", "E-STOP", "ES"} or "E-STOP" in desc_u:
            resolved_role = "FEEDBACK"
        else:
            return {
                **empty,
                "source_signal_role": resolved_role or "PRIMARY",
                "confidence": "REVIEW_REQUIRED",
                "provenance": "mcr_role_ambiguous",
                "review_reason": "MCR_ROLE_AMBIGUOUS_NEED_DIRECTION_EVIDENCE",
                "equipment_class": CLASS_ESTOP,
                "canonical_id": name,
            }

    # Feedback kinds / roles → schema BOOL member (never UDT root).
    role_for_member = resolved_role
    if resolved_kind in _ES_FEEDBACK_KINDS:
        if role_for_member not in _ES_FEEDBACK_ROLES:
            role_for_member = "ES_OK"
    elif resolved_kind == "MCR":
        if role_for_member not in _MCR_FEEDBACK_ROLES:
            return {
                **empty,
                "source_signal_role": resolved_role,
                "confidence": "REVIEW_REQUIRED",
                "provenance": "mcr_non_feedback_role",
                "review_reason": "MCR_NON_FEEDBACK_ROLE",
                "equipment_class": CLASS_ESTOP,
            }
    else:
        # Unknown kind even with dtype hint — do not guess a member.
        if typ not in {"ESTOP", "E-STOP", "ES", "ESLS", "ESR", "MCR"} and not (
            "E-STOP" in desc_u or "ESTOP" in desc_u
        ):
            return {
                **empty,
                "source_signal_role": resolved_role,
                "confidence": "REVIEW_REQUIRED",
                "provenance": "unsupported_safety_kind",
                "review_reason": f"UNSUPPORTED_KIND:{resolved_kind}",
                "equipment_class": CLASS_ESTOP,
            }
        role_for_member = "ES_OK"

    member = str(bool_members.get(role_for_member) or bool_members.get("ES_OK") or "")
    if not member:
        return {
            **empty,
            "source_signal_role": role_for_member,
            "confidence": "REVIEW_REQUIRED",
            "provenance": "schema_missing_bool_member",
            "review_reason": "MISSING_BOOL_MEMBER_IN_SCHEMA",
            "equipment_class": CLASS_ESTOP,
            "udt_type": udt_type,
        }

    member_dt = str(member_types.get(member) or "")
    if member_dt.upper() not in {"BIT", "BOOL", ""}:
        return {
            **empty,
            "source_signal_role": role_for_member,
            "confidence": "REVIEW_REQUIRED",
            "provenance": "schema_member_not_bool",
            "review_reason": f"NON_BOOL_MEMBER:{member}:{member_dt}",
            "equipment_class": CLASS_ESTOP,
            "udt_type": udt_type,
            "member": member,
        }

    try:
        from fortna_tag_registry import canonical_safety_logix_tag

        base = canonical_safety_logix_tag(name) or name
    except Exception:
        core = re.sub(r"^T_", "", name, flags=re.I)
        base = name if re.match(r"^[A-Za-z_]", name) else f"T_{core}"

    target = f"{base}.{member}"
    conf = "PROVEN"
    review_reason = ""
    # Physical OUTPUT against a feedback role still needs role proof.
    if d in {"O", "OUT", "OUTPUT"} and resolved_kind in _ES_FEEDBACK_KINDS:
        conf = "REVIEW_REQUIRED"
        review_reason = "ESTOP_FAMILY_OUTPUT_NEEDS_ROLE_PROOF"

    return {
        "target_tag": target,
        "target_data_type": "BOOL" if member_dt.upper() in {"BIT", "BOOL", ""} else member_dt,
        "source_signal_role": role_for_member if role_for_member != "PRIMARY" else "ES_OK",
        "confidence": conf,
        "provenance": (
            f"safety_model:{resolved_kind}/{resolved_role}+schema:{udt_type}.{member}"
        ),
        "udt_base": base,
        "udt_type": udt_type,
        "member": member,
        "emit": conf == "PROVEN",
        "review_reason": review_reason,
        "raw": name,
        "equipment_class": CLASS_ESTOP,
        "datatype": udt_type if conf in {"PROVEN", "REVIEW_REQUIRED"} else "",
        "canonical_id": base,
        "role": "ES_OK",
        "rule": RULE_ESTOP,
        "kind": resolved_kind,
    }


def safety_signal_needs_es_udt(
    signal_name: str,
    *,
    kind: str = "",
    signal_role: str = "",
    direction: str = "",
    device_type: str = "",
    description: str = "",
    udt_schema: Mapping[str, Any] | None = None,
) -> bool:
    """True when the signal should be typed as ES_UDT (feedback writer path)."""
    res = resolve_safety_bit_writer(
        signal_name,
        kind=kind,
        signal_role=signal_role,
        direction=direction,
        device_type=device_type,
        description=description,
        udt_schema=udt_schema,
    )
    if res.get("udt_type") != UDT_ES:
        return False
    if res.get("confidence") == "PROVEN" and res.get("member"):
        return True
    # REVIEW on feedback role still needs the UDT shell so static checks see a structure.
    if res.get("confidence") == "REVIEW_REQUIRED" and res.get("member") and res.get(
        "review_reason"
    ) == "ESTOP_FAMILY_OUTPUT_NEEDS_ROLE_PROOF":
        return True
    return False


def classify_estop(
    io_name: str,
    *,
    direction: str = "",
    device_type: str = "",
    description: str = "",
    kind: str = "",
    signal_role: str = "",
    udt_schema: Mapping[str, Any] | None = None,
) -> dict[str, str] | None:
    """ES / ESLS / ESR / MCR feedback → ES_UDT.I.ES_OK via semantic resolver.

    PD-0002: An MCR *energize coil* (physical OUTPUT, e.g. 'ENERGIZE MASTER CONTROL
    RELAY') is NOT an E-stop input and must not become ES_UDT.I.ES_OK.
    Device != signal: MCR coil output, MCR_AUX feedback, and canonical MCR device
    are separate concepts.
    """
    name = (io_name or "").strip()
    if not name:
        return None
    res = resolve_safety_bit_writer(
        name,
        kind=kind,
        signal_role=signal_role,
        direction=direction,
        device_type=device_type,
        description=description,
        udt_schema=udt_schema,
    )
    reason = str(res.get("review_reason") or "")
    # Non-Safety / command coil → caller treats as unrelated.
    if reason in {
        "NO_SAFETY_KIND",
        "INTERLOCK_NOT_SAFETY_DEVICE",
        "MCR_COMMAND_COIL",
    }:
        return None
    if reason.startswith("UNSUPPORTED_KIND:"):
        return None
    if res.get("confidence") == "UNRESOLVED" and not res.get("member"):
        return None
    out = {
        "raw": name,
        "equipment_class": CLASS_ESTOP,
        "datatype": str(res.get("datatype") or (UDT_ES if res.get("member") else "")),
        "role": str(res.get("role") or res.get("source_signal_role") or ""),
        "member": str(res.get("member") or ""),
        "canonical_id": str(res.get("canonical_id") or name),
        "rule": RULE_ESTOP,
        "confidence": str(res.get("confidence") or "REVIEW_REQUIRED"),
    }
    if res.get("review_reason"):
        out["review_reason"] = str(res["review_reason"])
    if res.get("target_tag"):
        out["target_tag"] = str(res["target_tag"])
    if res.get("provenance"):
        out["provenance"] = str(res["provenance"])
    return out


def classify_photoeye(
    io_name: str,
    *,
    direction: str = "",
    device_type: str = "",
    description: str = "",
) -> dict[str, str] | None:
    name = (io_name or "").strip()
    if not name:
        return None
    typ = (device_type or "").upper()
    desc_u = (description or "").upper()
    if not (
        _PE_RE.match(name)
        or typ in {"PHOTOCELL", "PHOTOEYE", "PE"}
        or "PHOTOEYE" in desc_u
        or "PHOTO EYE" in desc_u
    ):
        return None
    if not _PE_RE.match(name) and typ not in {"PHOTOCELL", "PHOTOEYE", "PE"}:
        return {
            "raw": name,
            "equipment_class": CLASS_PHOTOEYE,
            "datatype": UDT_PE,
            "role": "PE_CLEAR",
            "member": MEMBER_PE_CLEAR,
            "canonical_id": name,
            "rule": RULE_PE,
            "confidence": "REVIEW_REQUIRED",
            "review_reason": "PE_FAMILY_NAME_WEAK",
        }
    d = (direction or "").upper()
    if d in {"O", "OUT", "OUTPUT"}:
        return {
            "raw": name,
            "equipment_class": CLASS_PHOTOEYE,
            "datatype": UDT_PE,
            "role": "PE_CLEAR",
            "member": MEMBER_PE_CLEAR,
            "canonical_id": name,
            "rule": RULE_PE,
            "confidence": "REVIEW_REQUIRED",
            "review_reason": "PE_ON_OUTPUT_DIRECTION",
        }
    return {
        "raw": name,
        "equipment_class": CLASS_PHOTOEYE,
        "datatype": UDT_PE,
        "role": "PE_CLEAR",
        "member": MEMBER_PE_CLEAR,
        "canonical_id": name,
        "rule": RULE_PE,
        "confidence": "PROVEN",
    }


def classify_control_station(
    io_name: str,
    *,
    direction: str = "",
    device_type: str = "",
    description: str = "",
) -> dict[str, str] | None:
    """nPBSTART/STOP/RESET (+ _PLT) → CS_UDT members."""
    name = (io_name or "").strip()
    m = _CS_PB_RE.match(name) or _CS_PB_RE.match(re.sub(r"^T_", "", name, flags=re.I))
    if not m:
        return None
    panel, kind, plt = m.group(1), m.group(2).upper(), m.group(3)
    cs_tag = f"CP{panel}_CS"
    if plt:
        role = f"{kind}_PB_LT"
        member = MEMBER_CS.get(role, f"O.{kind.title()}_PB_LT")
    else:
        role = f"{kind}_PB"
        member = MEMBER_CS.get(role, f"I.{kind.title()}_PB")
    return {
        "raw": name,
        "equipment_class": CLASS_CONTROL_STATION,
        "datatype": UDT_CS,
        "role": role,
        "member": member,
        "canonical_id": cs_tag,
        "rule": RULE_CS,
        "confidence": "PROVEN",
    }


def _row_get(row: Mapping[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        if k in row and row[k] is not None:
            return str(row[k]).strip()
    return default


def _collect_known_convs(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    known: set[str] = set()
    for r in rows:
        n = _row_get(r, "IO_Name", "io_name", "name")
        t = _row_get(r, "Type", "device_type", "type").upper()
        if t in {
            "STRAIGHT",
            "ZEROPRESSURE",
            "BELT",
            "CURVE",
            "CONVEYOR",
            "SPUR",
            "MERGE",
        } or _P_TAG_RE.match(n):
            if _P_TAG_RE.match(n):
                known.add(n.upper())
    return known


def build_motor_related_devices(
    rows: Sequence[Mapping[str, Any]],
    *,
    machine: str = "",
    archive_sha: str = "",
    known_convs: Iterable[str] | None = None,
) -> list[EquipmentDevice]:
    """Build Motor_Starter (AUX) + Conv run (OUT) devices from Type=MOTOR rows."""
    known = set(known_convs or []) | _collect_known_convs(rows)
    bases: dict[str, Mapping[str, Any]] = {}
    auxs: dict[str, Mapping[str, Any]] = {}
    for r in rows:
        n = _row_get(r, "IO_Name", "io_name", "name")
        t = _row_get(r, "Type", "device_type", "type").upper()
        if t != "MOTOR":
            continue
        parsed = parse_motor_starter_name(n)
        if not parsed:
            continue
        stem = parsed["stem"]
        if parsed["role"] == "AUXILIARY_FORWARD":
            auxs[stem] = r
        else:
            bases[stem] = r

    devices: list[EquipmentDevice] = []
    for stem in sorted(set(bases) | set(auxs)):
        b = bases.get(stem)
        a = auxs.get(stem)
        driven = ""
        driven_prov = ""
        if b:
            driven, driven_prov = extract_driven_conveyor(
                _row_get(b, "General_Description", "description", "desc"),
                _row_get(b, "Motor", "motor"),
            )
        if a and not driven:
            driven, driven_prov = extract_driven_conveyor(
                _row_get(a, "General_Description", "description", "desc"),
                _row_get(a, "Motor", "motor"),
            )

        # --- Motor_Starter_UDT owns AUX only ---
        if a:
            an = _row_get(a, "IO_Name", "io_name", "name")
            desc = _row_get(a, "General_Description", "description", "desc")
            ms_tag = choose_motor_ms_tag(f"P{stem}")
            conf = "PROVEN"
            review = ""
            if not b:
                conf = "REVIEW_REQUIRED"
                review = "AUX_WITHOUT_MATCHING_BASE"
            devices.append(
                EquipmentDevice(
                    canonical_id=f"P{stem}",
                    logix_tag=ms_tag,
                    equipment_class=CLASS_MOTOR_STARTER,
                    datatype=UDT_MOTOR_STARTER,
                    rule=RULE_MOTOR_AUX,
                    signals={
                        "AUXILIARY_FORWARD": EquipmentSignal(
                            role="AUXILIARY_FORWARD",
                            raw_name=an,
                            direction="IN",
                            description=desc,
                        )
                    },
                    driven_conveyor=driven,
                    driven_conveyor_provenance=driven_prov,
                    confidence=conf,
                    review_reason=review,
                    machine=machine,
                    archive_sha=archive_sha,
                    raw_names=[an],
                )
            )

        # --- Conv_UDT owns physical motor OUT (not MS.O.Run) ---
        if b:
            bn = _row_get(b, "IO_Name", "io_name", "name")
            desc = _row_get(b, "General_Description", "description", "desc")
            conv_tag, conf, review = choose_conveyor_run_tag(
                stem, known_convs=known, driven_conveyor=driven
            )
            devices.append(
                EquipmentDevice(
                    canonical_id=conv_tag.replace("_Conv", "") if conv_tag else f"P{stem}",
                    logix_tag=conv_tag or f"P{stem}_Conv",
                    equipment_class=CLASS_CONVEYOR,
                    datatype=UDT_CONV,
                    rule=RULE_MOTOR_OUT_CONV,
                    signals={
                        "CONVEYOR_RUN": EquipmentSignal(
                            role="CONVEYOR_RUN",
                            raw_name=bn,
                            direction="OUT",
                            description=desc,
                        )
                    },
                    driven_conveyor=driven,
                    driven_conveyor_provenance=driven_prov,
                    confidence=conf,
                    review_reason=review,
                    machine=machine,
                    archive_sha=archive_sha,
                    raw_names=[bn],
                )
            )
    return devices


# Back-compat name used by older call sites / tests
def build_motor_starter_devices(
    rows: Sequence[Mapping[str, Any]],
    *,
    machine: str = "",
    archive_sha: str = "",
    reserved_bare_tags: Iterable[str] | None = None,
) -> list[EquipmentDevice]:
    return build_motor_related_devices(
        rows,
        machine=machine,
        archive_sha=archive_sha,
        known_convs=reserved_bare_tags,
    )


def build_power_air_devices(
    rows: Sequence[Mapping[str, Any]],
    *,
    machine: str = "",
    archive_sha: str = "",
) -> list[EquipmentDevice]:
    out: list[EquipmentDevice] = []
    seen: set[str] = set()
    for r in rows:
        n = _row_get(r, "IO_Name", "io_name", "name")
        if not n or n.upper() in seen:
            continue
        desc = _row_get(r, "General_Description", "description", "desc")
        typ = _row_get(r, "Type", "device_type", "type")
        info = classify_power_or_air(n, desc, typ)
        if not info:
            continue
        seen.add(n.upper())
        cls = info["equipment_class"]
        if cls == "UNKNOWN_PS_PREFIX":
            out.append(
                EquipmentDevice(
                    canonical_id=n,
                    logix_tag="",
                    equipment_class=cls,
                    datatype="",
                    rule="",
                    signals={},
                    confidence="REVIEW_REQUIRED",
                    review_reason=info.get("review_reason", ""),
                    machine=machine,
                    archive_sha=archive_sha,
                    raw_names=[n],
                )
            )
            continue
        role = info["role"]
        tag = info["canonical_id"]
        out.append(
            EquipmentDevice(
                canonical_id=tag,
                logix_tag=tag,
                equipment_class=cls,
                datatype=info["datatype"],
                rule=info["rule"],
                signals={
                    role: EquipmentSignal(
                        role=role,
                        raw_name=n,
                        direction="IN",
                        description=desc,
                    )
                },
                confidence=info.get("confidence", "PROVEN"),
                machine=machine,
                archive_sha=archive_sha,
                raw_names=[n],
            )
        )
    return out


def build_es_pe_cs_devices(
    rows: Sequence[Mapping[str, Any]],
    *,
    machine: str = "",
    archive_sha: str = "",
) -> list[EquipmentDevice]:
    out: list[EquipmentDevice] = []
    seen: set[str] = set()
    for r in rows:
        n = _row_get(r, "IO_Name", "io_name", "name")
        if not n or n.upper() in seen:
            continue
        desc = _row_get(r, "General_Description", "description", "desc")
        typ = _row_get(r, "Type", "device_type", "type")
        # Approximate direction from Type when present
        typ_u = typ.upper()
        direction = "OUT" if typ_u in {"MOTOR", "BEACON", "ANALOGOUTPUT"} else "IN"
        info = (
            classify_estop(n, direction=direction, device_type=typ, description=desc)
            or classify_photoeye(n, direction=direction, device_type=typ, description=desc)
            or classify_control_station(
                n, direction=direction, device_type=typ, description=desc
            )
        )
        if not info:
            continue
        seen.add(n.upper())
        role = info["role"]
        tag = info["canonical_id"]
        # Digit-leading ES → keep raw; Logix T_ form applied by safety/tag registry later
        out.append(
            EquipmentDevice(
                canonical_id=tag,
                logix_tag=tag,
                equipment_class=info["equipment_class"],
                datatype=info["datatype"],
                rule=info["rule"],
                signals={
                    role: EquipmentSignal(
                        role=role,
                        raw_name=n,
                        direction=direction,
                        description=desc,
                    )
                },
                confidence=info.get("confidence", "PROVEN"),
                review_reason=info.get("review_reason", ""),
                machine=machine,
                archive_sha=archive_sha,
                raw_names=[n],
            )
        )
    return out


def index_bindings_by_raw(
    devices: Sequence[EquipmentDevice],
) -> dict[str, dict[str, Any]]:
    """Map raw Fortna name → binding view for GUI/compiler."""
    idx: dict[str, dict[str, Any]] = {}
    for d in devices:
        if d.equipment_class == "UNKNOWN_PS_PREFIX" and d.raw_names:
            key = d.raw_names[0].upper()
            idx[key] = {
                "raw_name": d.raw_names[0],
                "role": "",
                "direction": "",
                "canonical_id": d.canonical_id,
                "logix_tag": "",
                "equipment_class": d.equipment_class,
                "datatype": "",
                "member_path": "",
                "member": "",
                "driven_conveyor": "",
                "driven_conveyor_provenance": "",
                "rule": "",
                "confidence": "REVIEW_REQUIRED",
                "review_reason": d.review_reason,
                "raw_names": list(d.raw_names),
                "physical_endpoint": "",
            }
            continue
        for role, sig in d.signals.items():
            key = (sig.raw_name or "").strip().upper()
            if not key:
                continue
            member = d.member_for_role(role)
            mp = d.member_path(role)
            idx[key] = {
                "raw_name": sig.raw_name,
                "role": role,
                "direction": sig.direction,
                "canonical_id": d.canonical_id,
                "logix_tag": d.logix_tag,
                "equipment_class": d.equipment_class,
                "datatype": d.datatype,
                "member_path": mp,
                "member": member,
                "generated_target": mp,
                "driven_conveyor": d.driven_conveyor,
                "driven_conveyor_provenance": d.driven_conveyor_provenance,
                "rule": d.rule,
                "confidence": d.confidence,
                "review_reason": d.review_reason,
                "raw_names": list(d.raw_names),
                "physical_endpoint": sig.physical_endpoint,
                "machine": d.machine,
                "archive_sha": d.archive_sha,
            }
    return idx


def build_equipment_bindings(
    rows: Sequence[Mapping[str, Any]],
    *,
    machine: str = "",
    archive_sha: str = "",
    reserved_bare_tags: Iterable[str] | None = None,
) -> dict[str, Any]:
    motors = build_motor_related_devices(
        rows,
        machine=machine,
        archive_sha=archive_sha,
        known_convs=reserved_bare_tags,
    )
    power_air = build_power_air_devices(
        rows, machine=machine, archive_sha=archive_sha
    )
    es_pe_cs = build_es_pe_cs_devices(
        rows, machine=machine, archive_sha=archive_sha
    )
    devices = list(motors) + list(power_air) + list(es_pe_cs)
    by_raw = index_bindings_by_raw(devices)

    def _count(cls: str) -> int:
        return sum(1 for d in devices if d.equipment_class == cls)

    return {
        "machine": machine,
        "archive_sha": archive_sha,
        "devices": [d.to_dict() for d in devices],
        "by_raw": by_raw,
        "counts": {
            "motor_starters": _count(CLASS_MOTOR_STARTER),
            "conveyor_run_bindings": _count(CLASS_CONVEYOR),
            "motor_proven": sum(
                1
                for d in motors
                if d.confidence == "PROVEN"
            ),
            "motor_review": sum(
                1 for d in motors if d.confidence != "PROVEN"
            ),
            "power_supplies": _count(CLASS_POWER_SUPPLY),
            "air_pressure": _count(CLASS_AIR_PRESSURE),
            "ps_prefix_review": sum(
                1 for d in power_air if d.equipment_class == "UNKNOWN_PS_PREFIX"
            ),
            "estop": _count(CLASS_ESTOP),
            "photoeye": _count(CLASS_PHOTOEYE),
            "control_station": _count(CLASS_CONTROL_STATION),
        },
        "binding_matrix": {
            "ES_UDT": MEMBER_ES_OK,
            "PE_UDT": MEMBER_PE_CLEAR,
            "Motor_Starter_UDT": MEMBER_AUX_FWD,
            "Conv_UDT": f"{MEMBER_RUN} / {MEMBER_RELEASE}",
            "PS_UDT": MEMBER_PS_OK,
            "AirPressure_Switch_UDT": MEMBER_PRESSURE_OK,
            "CS_UDT": "I.Start_PB / I.Stop_PB / O.*_LT / O.Horn / O.Red",
        },
    }


def binding_for_io_name(
    io_name: str,
    by_raw: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any] | None:
    if not by_raw:
        return None
    return dict(by_raw.get((io_name or "").strip().upper()) or {}) or None
