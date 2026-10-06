#!/usr/bin/env python3
"""Evidence-driven equipment classifier for Fortna Site Forge physical I/O.

Semantic naming evidence only — never treats a name as physical-address proof.
Returns equipment_class + evidence_class + confidence + Fortna+ semantic hints
(e.g. CPx_CS.I.Start_PB), never Logix module addresses.
"""
from __future__ import annotations

import re
from typing import Any

EQUIPMENT_CLASSES = frozenset(
    {
        "PHOTOEYE",
        "SAFETY_ESTOP_PB",
        "SAFETY_SWITCH",
        "SAFETY_RELAY",
        "MASTER_CONTROL_RELAY",
        "CONTROL_STATION_START_PB",
        "CONTROL_STATION_STOP_PB",
        "CONTROL_STATION_RESET_PB",
        "CONTROL_STATION_OUTPUT",
        "DRIVE",
        "MOTOR_EQUIPMENT",
        "PUSHBUTTON_CONTROL",
        "SAFETY",
        "IO",
        "INTERNAL_LOGICAL",
        "AMBIGUOUS",
        "PHYSICAL_CHANNEL",
        "UNKNOWN",
    }
)

EVIDENCE_CLASSES = frozenset(
    {
        "PHYSICAL_FIELD_DEVICE",
        "PHYSICAL_UNUSED_CHANNEL",
        "INTERNAL_LOGICAL",
        "FOREIGN_CONTROLLER",
        "REVIEW_REQUIRED",
    }
)

CONFIDENCES = frozenset({"PROVEN", "DERIVED", "REVIEW_REQUIRED", "UNKNOWN"})

_SPARE_TOKENS = frozenset(
    {"", "SPARE", "INVALID", "N/A", "NA", "NONE", "NULL", "—", "-", "(SPARE)"}
)

# Physical-device nomenclature that keeps *_STATUS / *_ENABLE from going internal.
_PHYSICAL_NOMENCLATURE_RE = re.compile(
    r"(?:ESPB|ESLS|ESR|MCR|PBSTART|PBSTOP|PBRESET|(?:^|_)PE\d|_PE_|\bPE\d|"
    r"(?:^|[^A-Z0-9])PB\d|(?:^|_)(?:SS|RS)\d|VFD|PHOTOEYE|STARTER|(?:^|_)MS_|"
    r"(?:^|_)MTR)",
    re.I,
)

_CS_START_RE = re.compile(r"^(?:T_)?(\d*)PBSTART(?:_PLT|_PL|\.PLT)?$", re.I)
_CS_STOP_RE = re.compile(r"^(?:T_)?(\d*)PBSTOP(?:_PLT|_PL|\.PLT)?$", re.I)
_CS_RESET_RE = re.compile(r"^(?:T_)?(\d*)PBRESET(?:_PLT|_PL|\.PLT)?$", re.I)
_PLT_SUFFIX_RE = re.compile(r"(?:_PLT|_PL|\.PLT)$", re.I)
_ESPB_RE = re.compile(r"(?:^|_)ESPB\d", re.I)
_ESLS_RE = re.compile(r"(?:^|_)ESLS\d?", re.I)
_ESR_RE = re.compile(r"(?:^|_)(?:\d+)?ESR\d", re.I)
_MCR_RE = re.compile(r"(?:^|_)(?:\d+)?MCR\d", re.I)
_PE_RE = re.compile(
    r"(?:^PE\d|_PE_|PHOTOEYE|(?:^|[^A-Z0-9])PE\d)",
    re.I,
)
_VFD_RE = re.compile(r"(?:^VFD\d|^VFD_|VFD\d)", re.I)
_MOTOR_RE = re.compile(r"(?:(?:^|_)MTR|(?:^|_)MS_|STARTER|^M\d{2,4}[A-Z]?(?:_AUX)?$)", re.I)
_PB_CTRL_RE = re.compile(r"(?:(?:^|[^A-Z0-9])PB\d|(?:^|_)(?:SS|RS)\d)", re.I)
_ES_PE_RE = re.compile(r"(?:^|_)ES_PE(?:_|$)", re.I)
_MEM_RE = re.compile(r"(?:^|_)MEM(?:_|$)", re.I)
_STATUS_ENABLE_RE = re.compile(r"(?:_STATUS|_ENABLE)$", re.I)
_WORD_BIT_RE = re.compile(
    r"^(?:W(?:ORD)?\d+(?:[._]B(?:IT)?\d+)?|B(?:IT)?\d+|I\d+|O\d+)$",
    re.I,
)
_PANEL_FROM_CS_RE = re.compile(r"^(?:T_)?(\d+)PB(?:START|STOP|RESET)", re.I)


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _result(
    equipment_class: str,
    evidence_class: str,
    confidence: str,
    reasons: list[str],
    fortna_plus_hint: str = "",
    needs_review: bool | None = None,
) -> dict[str, Any]:
    if needs_review is None:
        needs_review = confidence == "REVIEW_REQUIRED" or evidence_class == "REVIEW_REQUIRED"
    return {
        "equipment_class": equipment_class,
        "evidence_class": evidence_class,
        "confidence": confidence,
        "reasons": list(reasons),
        "fortna_plus_hint": fortna_plus_hint or "",
        "needs_review": bool(needs_review),
    }


def is_proven_spare_name(name: str) -> bool:
    """True for explicit unused/spare name tokens (not address proof)."""
    u = _norm(name).upper()
    if u in _SPARE_TOKENS:
        return True
    return u.startswith("SPARE")


def is_internal_logical_name(name: str) -> bool:
    """True when nomenclature indicates an internal/logical bit, not field device."""
    n = _norm(name)
    if not n:
        return False
    u = n.upper()
    if is_proven_spare_name(n):
        return False
    if _ES_PE_RE.search(u):
        return False  # ambiguous compound — not purely internal
    if _MEM_RE.search(u) or u.startswith("MEM"):
        return True
    if _STATUS_ENABLE_RE.search(u) and not _PHYSICAL_NOMENCLATURE_RE.search(u):
        return True
    if _WORD_BIT_RE.match(u) and not _PHYSICAL_NOMENCLATURE_RE.search(u):
        return True
    # Bare logical-looking tokens with no device nomenclature
    if not _PHYSICAL_NOMENCLATURE_RE.search(u) and re.match(
        r"^[A-Z][A-Z0-9_]*_(?:OK|NOT_OK|FLAG|LATCH|MEM|BIT)$", u
    ):
        return True
    return False


def _cs_hint(kind: str, name: str, *, output: bool = False) -> str:
    """Semantic CS UDT target pattern — never a physical address."""
    m = _PANEL_FROM_CS_RE.match(_norm(name))
    panel = m.group(1) if m else "x"
    prefix = f"CP{panel}_CS"
    if output:
        return f"{prefix}.O.{kind}"
    return f"{prefix}.I.{kind}"


def map_equipment_to_device_type(equipment_class: str) -> str:
    """Map classifier equipment_class → existing device_type vocabulary."""
    ec = _norm(equipment_class).upper()
    mapping = {
        "SAFETY_ESTOP_PB": "ESPB",
        "SAFETY_SWITCH": "ESLS",
        "SAFETY_RELAY": "ESR",
        "MASTER_CONTROL_RELAY": "MCR",
        "CONTROL_STATION_START_PB": "PUSHBUTTON_CONTROL",
        "CONTROL_STATION_STOP_PB": "PUSHBUTTON_CONTROL",
        "CONTROL_STATION_RESET_PB": "PUSHBUTTON_CONTROL",
        "CONTROL_STATION_OUTPUT": "PUSHBUTTON_CONTROL",
        "PUSHBUTTON_CONTROL": "PUSHBUTTON_CONTROL",
        "PHOTOEYE": "PHOTOEYE",
        "DRIVE": "VFD",
        "MOTOR_EQUIPMENT": "MOTOR",
        "PHYSICAL_CHANNEL": "PHYSICAL_CHANNEL",
        "SAFETY": "SAFETY",
        "INTERNAL_LOGICAL": "INTERNAL_LOGICAL",
        "AMBIGUOUS": "IO",
        "IO": "IO",
        "UNKNOWN": "IO",
    }
    return mapping.get(ec, "IO")


def classify_equipment(
    name: str,
    *,
    highlight: str = "",
    source_type: str = "",
    extra: dict | None = None,
) -> dict:
    """Classify Fortna I/O nomenclature into equipment + evidence classes.

    Naming is semantic evidence only — never physical-address proof.
    """
    n = _norm(name)
    u = n.upper()
    hl = _norm(highlight).upper()
    src = _norm(source_type).upper()
    extra = extra or {}
    reasons: list[str] = []

    if hl == "FOREIGN_CONTROLLER" or src in {"FOREIGN", "FOREIGN_CONTROLLER"}:
        reasons.append("highlight/source marks FOREIGN_CONTROLLER")
        # Still attempt semantic class for the name, but evidence is foreign.
        base = classify_equipment(n, highlight="", source_type="", extra=extra)
        base["evidence_class"] = "FOREIGN_CONTROLLER"
        base["reasons"] = reasons + list(base.get("reasons") or [])
        base["needs_review"] = True
        if base.get("confidence") == "PROVEN":
            base["confidence"] = "DERIVED"
        return base

    # --- SPARE / unused channel ---
    if is_proven_spare_name(n):
        reasons.append(f"explicit spare/empty token:{u or '<empty>'}")
        conf = "PROVEN" if hl == "PHYSICAL_CHANNEL" else "DERIVED"
        if hl == "PHYSICAL_CHANNEL":
            reasons.append("highlight=PHYSICAL_CHANNEL")
        return _result(
            "PHYSICAL_CHANNEL",
            "PHYSICAL_UNUSED_CHANNEL",
            conf,
            reasons,
            needs_review=False,
        )

    # --- Compound ambiguous: ES_PE_... ---
    if _ES_PE_RE.search(u) or u.startswith("ES_PE"):
        reasons.append("compound ES_PE nomenclature — safety+photoeye ambiguous")
        return _result(
            "AMBIGUOUS",
            "REVIEW_REQUIRED",
            "REVIEW_REQUIRED",
            reasons,
            needs_review=True,
        )

    # --- Internal logical ---
    if _MEM_RE.search(u) or u.startswith("MEM"):
        reasons.append("MEM_ prefix → internal logical bit")
        return _result(
            "INTERNAL_LOGICAL",
            "INTERNAL_LOGICAL",
            "PROVEN",
            reasons,
            needs_review=False,
        )

    if _STATUS_ENABLE_RE.search(u) and not _PHYSICAL_NOMENCLATURE_RE.search(u):
        reasons.append("*_STATUS/*_ENABLE without physical device nomenclature")
        return _result(
            "INTERNAL_LOGICAL",
            "INTERNAL_LOGICAL",
            "DERIVED",
            reasons,
            needs_review=False,
        )

    if _WORD_BIT_RE.match(u) and not _PHYSICAL_NOMENCLATURE_RE.search(u):
        reasons.append("pure word/bit reference without device nomenclature")
        return _result(
            "INTERNAL_LOGICAL",
            "INTERNAL_LOGICAL",
            "DERIVED",
            reasons,
            needs_review=False,
        )

    # --- Control station PBSTART/STOP/RESET (+ pilot lights) ---
    m_start = _CS_START_RE.match(n)
    if m_start or "PBSTART" in u:
        is_plt = bool(_PLT_SUFFIX_RE.search(n)) or bool(m_start and _PLT_SUFFIX_RE.search(n))
        if is_plt or (_PLT_SUFFIX_RE.search(n) and "PBSTART" in u):
            reasons.append("PBSTART pilot-light suffix")
            return _result(
                "CONTROL_STATION_OUTPUT",
                "PHYSICAL_FIELD_DEVICE",
                "PROVEN" if m_start or u.endswith(("_PLT", "_PL")) or ".PLT" in u else "DERIVED",
                reasons,
                _cs_hint("Start_PB_LT", n, output=True),
            )
        reasons.append("PBSTART control-station start PB")
        return _result(
            "CONTROL_STATION_START_PB",
            "PHYSICAL_FIELD_DEVICE",
            "PROVEN",
            reasons,
            _cs_hint("Start_PB", n),
        )

    m_stop = _CS_STOP_RE.match(n)
    if m_stop or "PBSTOP" in u:
        if _PLT_SUFFIX_RE.search(n):
            reasons.append("PBSTOP pilot-light suffix")
            return _result(
                "CONTROL_STATION_OUTPUT",
                "PHYSICAL_FIELD_DEVICE",
                "PROVEN",
                reasons,
                _cs_hint("Stop_PB_LT", n, output=True),
            )
        reasons.append("PBSTOP control-station stop PB")
        return _result(
            "CONTROL_STATION_STOP_PB",
            "PHYSICAL_FIELD_DEVICE",
            "PROVEN",
            reasons,
            _cs_hint("Stop_PB", n),
        )

    m_reset = _CS_RESET_RE.match(n)
    if m_reset or "PBRESET" in u:
        if _PLT_SUFFIX_RE.search(n):
            reasons.append("PBRESET pilot-light suffix")
            return _result(
                "CONTROL_STATION_OUTPUT",
                "PHYSICAL_FIELD_DEVICE",
                "PROVEN",
                reasons,
                _cs_hint("Reset_PB_LT", n, output=True),
            )
        reasons.append("PBRESET control-station reset PB")
        return _result(
            "CONTROL_STATION_RESET_PB",
            "PHYSICAL_FIELD_DEVICE",
            "PROVEN",
            reasons,
            _cs_hint("Reset_PB", n),
        )

    # Generic pilot-light outputs (non-PBSTART family already handled)
    if _PLT_SUFFIX_RE.search(n):
        reasons.append("pilot-light suffix _PLT/_PL/.PLT")
        return _result(
            "CONTROL_STATION_OUTPUT",
            "PHYSICAL_FIELD_DEVICE",
            "DERIVED",
            reasons,
            "CPx_CS.O.*",
        )

    # --- Safety family ---
    if _ESPB_RE.search(u) or u.startswith("ESPB") or hl == "ESPB":
        reasons.append("ESPB e-stop pushbutton nomenclature")
        return _result(
            "SAFETY_ESTOP_PB",
            "PHYSICAL_FIELD_DEVICE",
            "PROVEN",
            reasons,
        )

    if _ESLS_RE.search(u) or u.startswith("ESLS") or hl == "ESLS":
        reasons.append("ESLS lanyard/safety-switch nomenclature")
        return _result(
            "SAFETY_SWITCH",
            "PHYSICAL_FIELD_DEVICE",
            "PROVEN",
            reasons,
        )

    if _ESR_RE.search(u) or re.match(r"^ESR\d", u) or hl == "ESR":
        reasons.append("ESR safety-relay nomenclature")
        return _result(
            "SAFETY_RELAY",
            "PHYSICAL_FIELD_DEVICE",
            "PROVEN",
            reasons,
        )

    if _MCR_RE.search(u) or re.match(r"^MCR\d", u) or hl == "MCR":
        reasons.append("MCR master-control-relay nomenclature")
        return _result(
            "MASTER_CONTROL_RELAY",
            "PHYSICAL_FIELD_DEVICE",
            "PROVEN",
            reasons,
        )

    if hl in {"SAFETY", "ESTOP"}:
        reasons.append(f"highlight={hl}")
        return _result("SAFETY", "PHYSICAL_FIELD_DEVICE", "DERIVED", reasons)

    # --- Drives / motors ---
    if _VFD_RE.search(u) or u.startswith("VFD") or hl == "VFD":
        reasons.append("VFD drive nomenclature")
        return _result(
            "DRIVE",
            "PHYSICAL_FIELD_DEVICE",
            "PROVEN",
            reasons,
        )

    if _MOTOR_RE.search(u) or hl in {"MOTOR", "MOTOR_STARTER", "STARTER"}:
        reasons.append("motor starter / MTR / MS_ nomenclature")
        return _result(
            "MOTOR_EQUIPMENT",
            "PHYSICAL_FIELD_DEVICE",
            "DERIVED",
            reasons,
        )

    # --- Photoeye ---
    if _PE_RE.search(u) or "PHOTOEYE" in u or hl in {"PE", "PHOTOEYE", "PHOTOCELL"}:
        reasons.append("photoeye / PE nomenclature")
        return _result(
            "PHOTOEYE",
            "PHYSICAL_FIELD_DEVICE",
            "PROVEN",
            reasons,
            "PEx.I.PE_Clear",
        )

    # --- Generic control-station PB/SS/RS ---
    if (
        _PB_CTRL_RE.search(u)
        or hl in {"PUSHBUTTON_CONTROL", "PUSHBUTTON", "CS"}
    ):
        reasons.append("PB#/SS#/RS# control-station pattern")
        return _result(
            "PUSHBUTTON_CONTROL",
            "PHYSICAL_FIELD_DEVICE",
            "PROVEN" if _PB_CTRL_RE.search(u) else "DERIVED",
            reasons,
        )

    # Highlight PHYSICAL_CHANNEL without spare name → unused/unknown channel review
    if hl == "PHYSICAL_CHANNEL":
        reasons.append("highlight=PHYSICAL_CHANNEL without device nomenclature")
        return _result(
            "PHYSICAL_CHANNEL",
            "PHYSICAL_UNUSED_CHANNEL" if not n else "REVIEW_REQUIRED",
            "REVIEW_REQUIRED",
            reasons,
            needs_review=True,
        )

    if is_internal_logical_name(n):
        reasons.append("internal logical name heuristic")
        return _result(
            "INTERNAL_LOGICAL",
            "INTERNAL_LOGICAL",
            "DERIVED",
            reasons,
        )

    # Extra hints
    desc = _norm(extra.get("description") or extra.get("desc") or "").upper()
    if desc:
        if "PHOTOEYE" in desc or "PHOTOCELL" in desc:
            reasons.append("description mentions photoeye")
            return _result(
                "PHOTOEYE", "PHYSICAL_FIELD_DEVICE", "DERIVED", reasons, "PEx.I.PE_Clear"
            )
        if "VFD" in desc or "DRIVE" in desc:
            reasons.append("description mentions drive")
            return _result("DRIVE", "PHYSICAL_FIELD_DEVICE", "DERIVED", reasons)

    if n:
        reasons.append("no matching Fortna device nomenclature")
        return _result(
            "UNKNOWN",
            "REVIEW_REQUIRED",
            "UNKNOWN",
            reasons,
            needs_review=True,
        )

    reasons.append("empty name")
    return _result(
        "UNKNOWN",
        "REVIEW_REQUIRED",
        "UNKNOWN",
        reasons,
        needs_review=True,
    )


if __name__ == "__main__":
    samples = [
        "PBSTART",
        "PB6_JR",
        "SS13P7",
        "ESPB22",
        "ESLS11",
        "ESR1",
        "MCR4",
        "PE12",
        "MEM_FOO",
        "ES_PE_X",
        "FOO_STATUS",
        "SPARE",
        "VFD1",
    ]
    for s in samples:
        hl = "PHYSICAL_CHANNEL" if s == "SPARE" else ""
        r = classify_equipment(s, highlight=hl)
        print(
            f"{s:12} → {r['equipment_class']:28} "
            f"ev={r['evidence_class']:24} conf={r['confidence']:16} "
            f"hint={r['fortna_plus_hint']!r} review={r['needs_review']} "
            f"reasons={r['reasons']}"
        )
        print(f"             device_type={map_equipment_to_device_type(r['equipment_class'])}")
