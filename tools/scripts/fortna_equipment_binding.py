#!/usr/bin/env python3
"""Equipment-aware I/O binding — device vs signal (raw Fortna names immutable).

Canonical identities are DERIVED. Raw IO_Name / sourceName are never rewritten.

Rules (site-free):
  motor_starter_m_to_p_canonicalization
  power_supply_pws_to_ps_udt
  air_pressure_ps_to_airpress_udt

Collision-safe motor Logix tag:
  prefer bare P{stem} Motor_Starter_UDT when free;
  else P{stem}_MS when bare P{stem} is owned by a conveyor/Conv_UDT.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable, Mapping, Sequence

RULE_MOTOR_M_TO_P = "motor_starter_m_to_p_canonicalization"
RULE_POWER_SUPPLY = "power_supply_pws_to_ps_udt"
RULE_AIR_PRESSURE = "air_pressure_ps_to_airpress_udt"

CLASS_MOTOR_STARTER = "MOTOR_STARTER"
CLASS_POWER_SUPPLY = "POWER_SUPPLY"
CLASS_AIR_PRESSURE = "AIR_PRESSURE_SWITCH"
CLASS_VFD = "VFD"
CLASS_MDR = "MDR"

UDT_MOTOR_STARTER = "Motor_Starter_UDT"
UDT_PS = "PS_UDT"
UDT_AIR = "AirPressure_Switch_UDT"
UDT_ES = "ES_UDT"

MEMBER_RUN = "O.Run"
MEMBER_AUX_FWD = "I.Auxiliary_Forward"
MEMBER_PS_OK = "I.PS_OK"
MEMBER_PRESSURE_OK = "I.Pressure_OK"
MEMBER_ES_OK = "I.ES_OK"

# Strict discrete starter — never MDR*/VFD*/MTRANS*
_MOTOR_BASE_RE = re.compile(r"^M([0-9]+[A-Z]?)$", re.I)
_MOTOR_AUX_RE = re.compile(r"^M([0-9]+[A-Z]?)_AUX$", re.I)
_MDR_RE = re.compile(r"^MDR", re.I)
_VFD_RE = re.compile(r"^VFD\d|^VFD_|^PF\d", re.I)
_PWS_RE = re.compile(r"^(?:EZ)?PWS", re.I)
_PS_NAME_RE = re.compile(r"^PS\d", re.I)
_CONV_FROM_DESC_RE = re.compile(
    r"(?:CONVEYOR|CONV)\s+([A-Z]{1,3}\d+[A-Z]?)\b", re.I
)


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

    def member_path(self, role: str) -> str:
        sig = self.signals.get(role)
        if not sig:
            return ""
        member = {
            "RUN_COMMAND": MEMBER_RUN,
            "AUXILIARY_FORWARD": MEMBER_AUX_FWD,
            "PS_OK": MEMBER_PS_OK,
            "PRESSURE_OK": MEMBER_PRESSURE_OK,
            "ES_OK": MEMBER_ES_OK,
        }.get(role, "")
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
    # Motor field sometimes holds drawing refs, not conveyor id — ignore unless CONV-like
    mf = (motor_field or "").strip().upper()
    if re.match(r"^(?:MP|P|C)\d+[A-Z]?$", mf):
        return mf, "Conveyor.Motor"
    return "", ""


def choose_motor_logix_tag(
    canonical_id: str,
    *,
    reserved_bare_tags: Iterable[str] | None = None,
) -> str:
    """Prefer bare P{stem}; fall back to P{stem}_MS on Conv/P-tag collision."""
    bare = (canonical_id or "").strip()
    if not bare:
        return ""
    reserved = {(t or "").strip().upper() for t in (reserved_bare_tags or []) if t}
    if bare.upper() in reserved:
        return f"{bare}_MS"
    return bare


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
        # EZPWS / PWS or explicit power-supply description
        if _PS_NAME_RE.match(name) and (
            "AIR" in desc_u or "PRESSURE" in desc_u
        ) and "POWER" not in desc_u:
            # PS* with air language wins over weak power tokens
            pass
        else:
            if _PWS_RE.match(name) or "POWER" in desc_u:
                return {
                    "raw": name,
                    "equipment_class": CLASS_POWER_SUPPLY,
                    "datatype": UDT_PS,
                    "role": "PS_OK",
                    "member": MEMBER_PS_OK,
                    "canonical_id": name,  # keep Fortna identity as Logix tag
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
        # Ambiguous PS* — do not guess
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


def _row_get(row: Mapping[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        if k in row and row[k] is not None:
            return str(row[k]).strip()
    return default


def build_motor_starter_devices(
    rows: Sequence[Mapping[str, Any]],
    *,
    machine: str = "",
    archive_sha: str = "",
    reserved_bare_tags: Iterable[str] | None = None,
) -> list[EquipmentDevice]:
    """Aggregate Type=MOTOR strict M# / M#_AUX into MotorStarter devices.

    Requires same-machine exact stem pairing for AUX→device ownership.
    Unpaired AUX or base → REVIEW_REQUIRED device (or skipped for non-MOTOR).
    """
    reserved = set(reserved_bare_tags or [])
    # Also reserve conveyor-like IO_Names present in the same row set
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
        } or re.match(r"^P\d+[A-Z]?$", n, re.I):
            if re.match(r"^P\d+[A-Z]?$", n, re.I):
                reserved.add(n.upper())

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
        canonical_id = f"P{stem}"
        logix = choose_motor_logix_tag(canonical_id, reserved_bare_tags=reserved)
        signals: dict[str, EquipmentSignal] = {}
        raw_names: list[str] = []
        driven = ""
        driven_prov = ""
        confidence = "PROVEN"
        review = ""

        if b:
            bn = _row_get(b, "IO_Name", "io_name", "name")
            desc = _row_get(b, "General_Description", "description", "desc")
            signals["RUN_COMMAND"] = EquipmentSignal(
                role="RUN_COMMAND",
                raw_name=bn,
                direction="OUT",
                description=desc,
            )
            raw_names.append(bn)
            driven, driven_prov = extract_driven_conveyor(
                desc, _row_get(b, "Motor", "motor")
            )
        if a:
            an = _row_get(a, "IO_Name", "io_name", "name")
            desc = _row_get(a, "General_Description", "description", "desc")
            signals["AUXILIARY_FORWARD"] = EquipmentSignal(
                role="AUXILIARY_FORWARD",
                raw_name=an,
                direction="IN",
                description=desc,
            )
            raw_names.append(an)
            if not driven:
                driven, driven_prov = extract_driven_conveyor(
                    desc, _row_get(a, "Motor", "motor")
                )

        if not b or not a:
            confidence = "REVIEW_REQUIRED"
            review = "UNPAIRED_MOTOR_STARTER_SIGNAL"
        # Guard: do not claim AUX owns P{n} without base on this machine
        if a and not b:
            confidence = "REVIEW_REQUIRED"
            review = "AUX_WITHOUT_MATCHING_BASE"

        devices.append(
            EquipmentDevice(
                canonical_id=canonical_id,
                logix_tag=logix,
                equipment_class=CLASS_MOTOR_STARTER,
                datatype=UDT_MOTOR_STARTER,
                rule=RULE_MOTOR_M_TO_P,
                signals=signals,
                driven_conveyor=driven,
                driven_conveyor_provenance=driven_prov,
                confidence=confidence,
                review_reason=review,
                machine=machine,
                archive_sha=archive_sha,
                raw_names=raw_names,
            )
        )
    return devices


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
        member = info["member"]
        tag = info["canonical_id"]
        sig = EquipmentSignal(
            role=role,
            raw_name=n,
            direction="IN",
            description=desc,
        )
        dev = EquipmentDevice(
            canonical_id=tag,
            logix_tag=tag,
            equipment_class=cls,
            datatype=info["datatype"],
            rule=info["rule"],
            signals={role: sig},
            confidence=info.get("confidence", "PROVEN"),
            machine=machine,
            archive_sha=archive_sha,
            raw_names=[n],
        )
        # stash member for display helpers
        if member and role:
            # member_path uses role map
            pass
        out.append(dev)
    return out


def index_bindings_by_raw(
    devices: Sequence[EquipmentDevice],
) -> dict[str, dict[str, Any]]:
    """Map raw Fortna name → binding view for GUI/compiler."""
    idx: dict[str, dict[str, Any]] = {}
    for d in devices:
        for role, sig in d.signals.items():
            key = (sig.raw_name or "").strip().upper()
            if not key:
                continue
            idx[key] = {
                "raw_name": sig.raw_name,
                "role": role,
                "direction": sig.direction,
                "canonical_id": d.canonical_id,
                "logix_tag": d.logix_tag,
                "equipment_class": d.equipment_class,
                "datatype": d.datatype,
                "member_path": d.member_path(role),
                "driven_conveyor": d.driven_conveyor,
                "driven_conveyor_provenance": d.driven_conveyor_provenance,
                "rule": d.rule,
                "confidence": d.confidence,
                "review_reason": d.review_reason,
                "raw_names": list(d.raw_names),
            }
    return idx


def build_equipment_bindings(
    rows: Sequence[Mapping[str, Any]],
    *,
    machine: str = "",
    archive_sha: str = "",
    reserved_bare_tags: Iterable[str] | None = None,
) -> dict[str, Any]:
    motors = build_motor_starter_devices(
        rows,
        machine=machine,
        archive_sha=archive_sha,
        reserved_bare_tags=reserved_bare_tags,
    )
    power_air = build_power_air_devices(
        rows, machine=machine, archive_sha=archive_sha
    )
    devices = list(motors) + list(power_air)
    by_raw = index_bindings_by_raw(devices)
    return {
        "machine": machine,
        "archive_sha": archive_sha,
        "devices": [d.to_dict() for d in devices],
        "by_raw": by_raw,
        "counts": {
            "motor_starters": len(motors),
            "motor_proven": sum(1 for d in motors if d.confidence == "PROVEN"),
            "motor_review": sum(1 for d in motors if d.confidence != "PROVEN"),
            "power_supplies": sum(
                1 for d in power_air if d.equipment_class == CLASS_POWER_SUPPLY
            ),
            "air_pressure": sum(
                1 for d in power_air if d.equipment_class == CLASS_AIR_PRESSURE
            ),
            "ps_prefix_review": sum(
                1 for d in power_air if d.equipment_class == "UNKNOWN_PS_PREFIX"
            ),
        },
    }


def binding_for_io_name(
    io_name: str,
    by_raw: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any] | None:
    if not by_raw:
        return None
    return dict(by_raw.get((io_name or "").strip().upper()) or {}) or None
