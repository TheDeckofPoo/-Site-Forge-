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

_MOTOR_BASE_RE = re.compile(r"^M([0-9]+[A-Z]?)$", re.I)
_MOTOR_AUX_RE = re.compile(r"^M([0-9]+[A-Z]?)_AUX$", re.I)
_MDR_RE = re.compile(r"^MDR", re.I)
_VFD_RE = re.compile(r"^VFD\d|^VFD_|^PF\d", re.I)
_PWS_RE = re.compile(r"^(?:EZ)?PWS", re.I)
_PS_NAME_RE = re.compile(r"^PS\d", re.I)
_PE_RE = re.compile(r"^(?:EZ)?PE\d", re.I)
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
) -> tuple[str, str, str]:
    """Resolve Conv_UDT tag for physical motor RUN ownership.

    Returns (logix_tag, confidence, review_reason).
    Proven when P{stem} (or exact driven P-tag) exists in known conveyors.
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
    return "", "REVIEW_REQUIRED", "MOTOR_OUT_NO_CONVEYOR_LINEAGE"


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


def classify_estop(
    io_name: str,
    *,
    direction: str = "",
    device_type: str = "",
    description: str = "",
) -> dict[str, str] | None:
    """ES / ESLS / ESR / MCR feedback → ES_UDT.I.ES_OK when INPUT evidence supports it.

    PD-0002: An MCR *energize coil* (physical OUTPUT, e.g. 'ENERGIZE MASTER CONTROL
    RELAY') is NOT an E-stop input and must not become ES_UDT.I.ES_OK.
    Device != signal: MCR coil output, MCR_AUX feedback, and canonical MCR device
    are separate concepts.
    """
    name = (io_name or "").strip()
    if not name:
        return None
    # Strip T_ for matching; keep canonical Logix via caller
    core = re.sub(r"^T_", "", name, flags=re.I)
    typ = (device_type or "").upper()
    desc_u = (description or "").upper()
    d = (direction or "").upper()
    # Panel forms: MCR1, 14MCR1, CP2_MCR1, T_14MCR1
    is_mcr = bool(
        re.match(r"^\d*MCR\d*", core, re.I)
        or re.search(r"(?:^|_)(?:MCR)\d*", core, re.I)
        or re.match(r"^MCR", core, re.I)
        or re.match(r"^CP\d+_MCR\d*", core, re.I)
    )
    is_mcr_aux = is_mcr and bool(re.search(r"_AUX$", core, re.I))
    is_es_family = bool(
        _ES_RE.match(core)
        or _ES_RE.match(name)
        or re.search(r"(?:^|_)(?:ESR)\d*", core, re.I)
        or re.match(r"^ESLS", core, re.I)
        or re.match(r"^ES\d", core, re.I)
        or is_mcr_aux  # MCR auxiliary feedback may map to ES_OK
    )
    # Bare MCR coil name without _AUX — only ES if INPUT feedback evidence, never OUTPUT coil
    if is_mcr and not is_mcr_aux:
        # Energize coil: OUTPUT / OA module / ENERGIZE description → NOT ES_UDT
        if d in {"O", "OUT", "OUTPUT"} or "ENERGIZE" in desc_u or "OA" in typ:
            return None
        # INPUT MCR without _AUX — feedback may still be ES_OK when proven input
        if d in {"I", "IN", "INPUT"} or typ in {"ESTOP", "E-STOP", "ES"} or "E-STOP" in desc_u:
            is_es_family = True
        else:
            # Ambiguous MCR without direction → do not invent ES_UDT
            return {
                "raw": name,
                "equipment_class": CLASS_ESTOP,
                "datatype": "",
                "role": "",
                "member": "",
                "canonical_id": name,
                "rule": RULE_ESTOP,
                "confidence": "REVIEW_REQUIRED",
                "review_reason": "MCR_ROLE_AMBIGUOUS_NEED_DIRECTION_EVIDENCE",
            }
    looks = is_es_family or (
        typ in {"ESTOP", "E-STOP", "ES"} or "E-STOP" in desc_u or "ESTOP" in desc_u
    )
    if not looks and not is_es_family:
        return None
    if not is_es_family and not (
        typ in {"ESTOP", "E-STOP", "ES"} or "E-STOP" in desc_u or "ESTOP" in desc_u
    ):
        return None
    # Physical OUTPUT of ES-family (non-MCR-coil handled above) needs role proof
    if d in {"O", "OUT", "OUTPUT"}:
        return {
            "raw": name,
            "equipment_class": CLASS_ESTOP,
            "datatype": UDT_ES,
            "role": "ES_OK",
            "member": MEMBER_ES_OK,
            "canonical_id": name,
            "rule": RULE_ESTOP,
            "confidence": "REVIEW_REQUIRED",
            "review_reason": "ESTOP_FAMILY_OUTPUT_NEEDS_ROLE_PROOF",
        }
    return {
        "raw": name,
        "equipment_class": CLASS_ESTOP,
        "datatype": UDT_ES,
        "role": "ES_OK",
        "member": MEMBER_ES_OK,
        "canonical_id": name,
        "rule": RULE_ESTOP,
        "confidence": "PROVEN",
    }


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
