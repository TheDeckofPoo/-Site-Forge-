#!/usr/bin/env python3
"""Conveyor section discovery from RUN + deterministic cross-table relationships.

SOURCE OF TRUTH: RUN tables + Fortna docs + proven cross-table rules.
Finished PLC is validation-only — never a generation input.
Do not hardcode site-specific conveyor lists; mark unknowns UNRESOLVED.

Confidence:
  PROVEN_RUN          — direct Conveyor.asc mechanical / device row
  PROVEN_CROSS_TABLE  — Mtrchain / Fullline / PE↔SSV naming linkage
  DOC_DEFINED         — library / training vocabulary (type codes)
  UNRESOLVED          — insufficient evidence
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_asc import read_asc  # noqa: E402
from fortna_identity import parse_p_tag  # noqa: E402
from fortna_io_extract import (  # noqa: E402
    belongs_to_controller,
    normalize_io_name,
    read_project_meta,
    row_machine_matches,
)

PROVEN_RUN = "PROVEN_RUN"
PROVEN_CROSS_TABLE = "PROVEN_CROSS_TABLE"
DOC_DEFINED = "DOC_DEFINED"
UNRESOLVED = "UNRESOLVED"

MECH_TYPES = frozenset(
    {
        "STRAIGHT",
        "BELT",
        "CURVE",
        "MERGE",
        "SKEW",
        "SPUR",
        "TRIANG",
        "ACCUM",
        "ZEROPRESSURE",
    }
)
BLANK = frozenset({"", "N/A", "INVALID", "NONE", "ALL", "~", "0"})
_CHAIN_COLS = tuple(f"Motor_Chained{i}" for i in range(1, 11))

# Library Conv_UDT.Type (DOC_DEFINED) — ignore swapped Phase4 text.
# P1000=0 Transport+VFD, P2000=1 Accum+VFD, P4000=2 Accum+MS, P3000=3 Transport+MS
TYPE_CODE_TRANSPORT_VFD = 0
TYPE_CODE_ACCUM_VFD = 1
TYPE_CODE_ACCUM_MS = 2
TYPE_CODE_TRANSPORT_MS = 3

_MOTOR_RE = re.compile(r"^M(\d{2,4})(?:([A-Z]+)|_(P\d+))?$", re.I)
_TIMER_MOTOR_RE = re.compile(r"^tmM(\d{2,4}[A-Z]?)$", re.I)
_P_TAG_RE = re.compile(r"^P(\d{2,4})(?:([A-Z]+)|_(P\d+))?$", re.I)


def _clean(val: Any) -> str:
    s = str(val or "").strip()
    return "" if s.upper() in BLANK else s


def _norm_run_dir(run_dir: Path | str) -> Path:
    run_dir = Path(run_dir)
    if not run_dir.is_absolute():
        run_dir = (REPO_ROOT / run_dir).resolve()
    if (run_dir / "RUN" / "project.cfg").is_file():
        return run_dir / "RUN"
    return run_dir


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_solenoid_device_signal(name: str) -> bool:
    """True for SSV*/SSVEZPE* hold/release solenoids (DEVICE_SIGNAL ≠ CONTROL_SECTION).

    GATE F: SSVEZPE134_P1 / SSVEZPE134_P2 style names must not be promoted to
    independent P134_P1 / P134_P2 conveyor sections solely from solenoid naming.
    """
    n = (name or "").strip().upper()
    if not n:
        return False
    return n.startswith("SSVEZPE") or n.startswith("SSV")


def _section_from_pe_or_ssv(name: str) -> str | None:
    """EZPE136_P1 / SSVEZPE150_P1 / SSV150_P1 / SSVEZPE312_P → section id token.

    Token extraction only — callers must gate CONTROL_SECTION promotion with
    is_solenoid_device_signal() so SSV names do not invent independent conveyors.
    """
    n = (name or "").strip().upper()
    if not n:
        return None
    # Prefer section form _(P\d+) when present
    m = re.match(
        r"^(?:SSV)?(?:EZ)?PE(\d{2,4})(?:([A-Z]+)|_(P\d+))?(?:_P)?(?:_|$)",
        n,
        re.I,
    )
    if not m:
        m = re.match(r"^SSV(\d{2,4})(?:([A-Z]+)|_(P\d+))?(?:_P)?(?:_|$)", n, re.I)
    if not m:
        return None
    digits = m.group(1)
    letters = (m.group(2) or "").upper()
    section = (m.group(3) or "").upper() if m.lastindex >= 3 else ""
    if section:
        return f"P{digits}_{section}"
    if letters:
        return f"P{digits}{letters}"
    return f"P{digits}"


def _motor_to_section(motor: str) -> str | None:
    """M130A → P130A; M150 → P150; M136_P1 → P136_P1.

    Never map M1000AUX / M1000_AUX → P1000AUX (DEVICE_SIGNAL ≠ CONTROL_SECTION).
    """
    raw = (motor or "").strip()
    core = re.sub(r"(_)?(AUX|FLT|OK|RUN|EN|CMD|REF|FB)$", "", raw, flags=re.I)
    m = _MOTOR_RE.match(core)
    if not m:
        return None
    digits, letters, section = m.group(1), (m.group(2) or "").upper(), (m.group(3) or "").upper()
    if letters in {"AUX", "FLT", "OK", "RUN", "EN", "CMD"}:
        letters = ""
    if section:
        return f"P{digits}_{section}"
    return f"P{digits}{letters}"


def _parse_timer_motor(timer: str) -> str | None:
    """tmM130A → M130A; non-motor timers → None."""
    m = _TIMER_MOTOR_RE.match((timer or "").strip())
    if not m:
        return None
    return f"M{m.group(1).upper()}"


def classify_conv_type(asc_type: str, is_vfd: bool) -> dict[str, Any]:
    """Map RUN ASC Type + VFD flag → Conv_UDT type_code / Autogen type_str.

    Authority: OReilly_Library_v3 Area_L1 presets
      P1000 Transport+VFD = 0
      P2000 Accum+VFD     = 1
      P4000 Accum+MS      = 2
      P3000 Transport+MS  = 3

    Finished Greensboro Trash STRAIGHT belts show Type:=2 in the validation
    oracle, which *contradicts* both RUN ASC (STRAIGHT→Transport) and the
    library Transport+MS=3 preset. Do NOT flip Transport+MS to 2 from that
    oracle alone — classify as LIBRARY_CONTRACT vs ORACLE divergence and keep
    the library+RUN deterministic mapping.
    """
    typ = (asc_type or "").strip().upper()
    accum = typ in ("ACCUM", "ZEROPRESSURE")
    vfd = bool(is_vfd)
    if vfd and accum:
        code, tstr = TYPE_CODE_ACCUM_VFD, "Accumulation with VFD"
    elif vfd:
        code, tstr = TYPE_CODE_TRANSPORT_VFD, "Transport with VFD"
    elif accum:
        code, tstr = TYPE_CODE_ACCUM_MS, "Accumulation with MS"
    else:
        code, tstr = TYPE_CODE_TRANSPORT_MS, "Transport with MS"
    return {
        "type_code": code,
        "type_str": tstr,
        "asc_type": typ or UNRESOLVED,
        "is_vfd": vfd,
        "confidence": DOC_DEFINED if typ else UNRESOLVED,
        "provenance": [
            {
                "kind": "library_conv_udt_type",
                "rule": "P1000=0 Transport+VFD, P2000=1 Accum+VFD, P4000=2 Accum+MS, P3000=3 Transport+MS",
                "confidence": DOC_DEFINED,
            },
            {
                "kind": "run_asc_type",
                "asc_type": typ or None,
                "accum": accum,
                "is_vfd": vfd,
                "confidence": PROVEN_RUN if typ else UNRESOLVED,
            },
        ],
    }


def resolve_ssv_endpoint(name: str, known_sections: set[str] | frozenset[str] | None) -> str | None:
    """SSVEZPE{n}_{Pn|P} / SSV* → {section}_Conv.O.Release when section is known."""
    section = _section_from_pe_or_ssv(name)
    if not section:
        return None
    known = {str(s).strip().upper() for s in (known_sections or []) if str(s).strip()}
    if known and section.upper() not in known:
        # Allow parent mechanical when section PE uses bare _P (P312)
        parsed = parse_p_tag(section)
        if not parsed:
            return None
        # Prefer exact section; do not silently collapse P150_P1 → P150
        return None
    return f"{section}_Conv.O.Release"


def _load_conveyor_rows(run_dir: Path) -> list[dict[str, str]]:
    path = run_dir / "FORTNA" / "Conveyor.asc"
    if not path.is_file():
        return []
    _h, rows = read_asc(path)
    return rows


def _load_mtrchain_rows(run_dir: Path) -> list[dict[str, str]]:
    path = run_dir / "FORTNA" / "Mtrchain.asc"
    if not path.is_file():
        return []
    _h, rows = read_asc(path)
    return rows


def _load_fullline_rows(run_dir: Path) -> list[dict[str, str]]:
    path = run_dir / "FORTNA" / "Fullline.asc"
    if not path.is_file():
        return []
    _h, rows = read_asc(path)
    return rows


def _controller_device(
    row: dict[str, str],
    machine: str,
    word_map: dict | None = None,
) -> bool:
    mn = _clean(row.get("Machine_Name"))
    word = _clean(row.get("IO_Address_Word"))
    return belongs_to_controller(
        machine_name=mn,
        io_word=word,
        controller=machine,
        word_map=word_map,
    )


def discover_sections(
    run_dir: Path | str,
    machine: str,
    *,
    word_map: dict | None = None,
) -> dict[str, Any]:
    """Discover assemblies/sections with provenance for one controller.

    Promotions (PROVEN_CROSS_TABLE):
      - Letter motors M{n}A.. on controller → sections P{n}A.. even if only P{n} mechanical
      - EZPE{n}_P1 (photocell) → section P{n}_P1 (not bare P{n})
      - SSVEZPE{n}_P1/_P2 solenoids are DEVICE_SIGNAL — never promote independent
        P{n}_P1 conveyors solely from solenoid naming (GATE F); keep/restore master
        P{n} when RUN mechanical/control evidence proves it
      - Mtrchain Motor_Chained* naming P / lettered identities (SSV chain = signal)
    """
    run_dir = _norm_run_dir(run_dir)
    machine = (machine or "").strip()
    rows = _load_conveyor_rows(run_dir)
    mtr_rows = _load_mtrchain_rows(run_dir)

    mechanical: dict[str, dict[str, Any]] = {}
    motors_on_ctrl: dict[str, dict[str, Any]] = {}
    pe_ssv_on_ctrl: list[dict[str, Any]] = []

    for row in rows:
        raw = _clean(row.get("IO_Name"))
        if not raw:
            continue
        name = normalize_io_name(raw) or raw
        name_u = name.upper()
        typ = (row.get("Type") or "").strip().upper()
        on_ctrl = _controller_device(row, machine, word_map)

        if typ in MECH_TYPES and _P_TAG_RE.match(name_u):
            # Mechanical conveyors: Machine_Name match OR untagged (filled later via devices)
            row_mach = _clean(row.get("Machine_Name"))
            include = False
            if row_mach and row_mach.upper() not in BLANK:
                include = row_machine_matches(row_mach, machine)
            else:
                include = True  # candidate; ownership via motors/PE below
            if include:
                mechanical[name_u] = {
                    "id": name_u,
                    "asc_type": typ,
                    "drive": _clean(row.get("Drive")),
                    "description": _clean(row.get("General_Description")),
                    "machine_name": row_mach,
                    "io_word": _clean(row.get("IO_Address_Word")),
                    "confidence": PROVEN_RUN,
                    "provenance": [
                        {
                            "kind": "conveyor_asc",
                            "table": "Conveyor.asc",
                            "io_name": raw,
                            "type": typ,
                            "confidence": PROVEN_RUN,
                        }
                    ],
                }

        if typ == "MOTOR" or re.match(r"^M\d", name_u):
            if on_ctrl:
                # Strip role suffixes with or without underscore (M1000AUX / M1000_AUX)
                # BEFORE letter-group match — never invent motor M1000AUX → P1000AUX.
                core_mot = re.sub(
                    r"(_)?(AUX|FLT|OK|RUN|EN|CMD|REF|FB)$",
                    "",
                    name_u,
                    flags=re.I,
                )
                mm = _MOTOR_RE.match(core_mot)
                if mm:
                    letter = (mm.group(2) or "").upper()
                    if letter in {"AUX", "FLT", "OK", "RUN", "EN", "CMD"}:
                        letter = ""
                    if mm.group(3):
                        mot = f"M{mm.group(1)}_{mm.group(3)}".upper()
                    elif letter:
                        mot = f"M{mm.group(1)}{letter}".upper()
                    else:
                        mot = f"M{mm.group(1)}"
                    motors_on_ctrl[mot] = {
                        "motor": mot,
                        "io_name": raw,
                        "machine_name": _clean(row.get("Machine_Name")),
                        "signal_role": (
                            "AUXILIARY_FORWARD"
                            if re.search(r"AUX", name_u, re.I)
                            else "MOTOR_COMMAND"
                        ),
                        "kind": "DEVICE_SIGNAL",
                        "provenance": {
                            "kind": "conveyor_asc_motor",
                            "table": "Conveyor.asc",
                            "confidence": PROVEN_RUN,
                        },
                    }

        if typ in ("PHOTOCELL", "TRIANG") or re.match(r"^(?:SSV)?(?:EZ)?PE\d", name_u) or name_u.startswith("SSV"):
            if on_ctrl or (row_machine_matches(_clean(row.get("Machine_Name")), machine)):
                sec = _section_from_pe_or_ssv(raw)
                pe_ssv_on_ctrl.append(
                    {
                        "io_name": raw,
                        "type": typ,
                        "section": sec,
                        "is_ssv": bool(re.search(r"SSV", raw, re.I)),
                        "description": _clean(row.get("General_Description")),
                        "machine_name": _clean(row.get("Machine_Name")),
                    }
                )

    # Mtrchain: only chains whose Motor_Name is on this controller
    mtr_chained_sections: set[str] = set()
    mtr_evidence: list[dict[str, Any]] = []
    for row in mtr_rows:
        motor = _clean(row.get("Motor_Name"))
        if not motor:
            continue
        mot_u = re.sub(r"(_AUX|_FLT|_OK|_RUN)$", "", motor.upper(), flags=re.I)
        if mot_u not in motors_on_ctrl:
            continue
        chained = [_clean(row.get(c)) for c in _CHAIN_COLS]
        chained = [c for c in chained if c]
        timer = _clean(row.get("Timer_Name"))
        for c in chained:
            cu = c.upper()
            if cu.startswith("SSV"):
                sec = _section_from_pe_or_ssv(cu)
                if not sec:
                    continue
                parsed_ssv = parse_p_tag(sec)
                suffix = (parsed_ssv[1] if parsed_ssv else "") or ""
                # GATE F: SSV hold/release in Motor_Chained* is DEVICE_SIGNAL.
                # Do not invent independent P{n}_P1/_P2 CONTROL_SECTIONs from it.
                if suffix.startswith("_P") and is_solenoid_device_signal(cu):
                    parent_sec = f"P{parsed_ssv[0]}" if parsed_ssv else sec
                    mtr_evidence.append(
                        {
                            "kind": "mtrchain_ssv_device_signal",
                            "motor": mot_u,
                            "chained": cu,
                            "section": parent_sec,
                            "device_signal_token": sec,
                            "timer": timer,
                            "confidence": PROVEN_CROSS_TABLE,
                            "rule": (
                                "SSVEZPE*_P1/_P2 solenoid is DEVICE_SIGNAL — "
                                "not an independent conveyor section"
                            ),
                        }
                    )
                    continue
                mtr_chained_sections.add(sec)
                mtr_evidence.append(
                    {
                        "kind": "mtrchain_ssv",
                        "motor": mot_u,
                        "chained": cu,
                        "section": sec,
                        "timer": timer,
                        "confidence": PROVEN_CROSS_TABLE,
                    }
                )
            elif _P_TAG_RE.match(cu):
                mtr_chained_sections.add(cu)
                mtr_evidence.append(
                    {
                        "kind": "mtrchain_p",
                        "motor": mot_u,
                        "chained": cu,
                        "section": cu,
                        "timer": timer,
                        "confidence": PROVEN_CROSS_TABLE,
                    }
                )

    sections: dict[str, dict[str, Any]] = {}
    assemblies: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"id": "", "sections": [], "mechanical": None, "provenance": []}
    )

    def _ensure_section(
        sid: str,
        *,
        confidence: str,
        provenance: list[dict],
        parent: str | None = None,
        asc_type: str = "",
        kind: str = "",
        motor: str = "",
    ) -> None:
        su = sid.upper()
        if not su or not _P_TAG_RE.match(su):
            return
        parsed = parse_p_tag(su)
        parent_id = parent or (f"P{parsed[0]}" if parsed else "")
        if su not in sections:
            parent_mech = mechanical.get(parent_id) or mechanical.get(su)
            atype = asc_type or (parent_mech or {}).get("asc_type") or ""
            sections[su] = {
                "id": su,
                "parent_mechanical": parent_id if parent_id != su else (parent_id if su in mechanical else parent_id),
                "kind": kind or ("mechanical" if su in mechanical else "promoted"),
                "asc_type": atype,
                "motor": motor,
                "confidence": confidence,
                "provenance": list(provenance),
                "from_mechanical_row": su in mechanical,
            }
            if parent_id:
                asm = assemblies[parent_id]
                asm["id"] = parent_id
                if parent_id in mechanical:
                    asm["mechanical"] = parent_id
                if su not in asm["sections"]:
                    asm["sections"].append(su)
                asm["provenance"].extend(provenance)
        else:
            sections[su]["provenance"].extend(provenance)
            # Upgrade confidence if stronger
            order = {PROVEN_RUN: 3, PROVEN_CROSS_TABLE: 2, DOC_DEFINED: 1, UNRESOLVED: 0}
            if order.get(confidence, 0) > order.get(sections[su].get("confidence"), 0):
                sections[su]["confidence"] = confidence
            if motor and not sections[su].get("motor"):
                sections[su]["motor"] = motor
            if kind and sections[su].get("kind") == "promoted":
                sections[su]["kind"] = kind

    # Seed mechanical rows that are controller-owned via Machine_Name or later evidence
    owned_mechanical: set[str] = set()
    for sid, info in mechanical.items():
        mn = info.get("machine_name") or ""
        if mn and row_machine_matches(mn, machine):
            owned_mechanical.add(sid)
            _ensure_section(
                sid,
                confidence=PROVEN_RUN,
                provenance=info["provenance"],
                parent=sid,
                asc_type=info["asc_type"],
                kind="mechanical",
            )

    # Letter-motor promotion: M130A..E on controller → P130A..E
    for mot, minfo in motors_on_ctrl.items():
        sec = _motor_to_section(mot)
        if not sec:
            continue
        parsed = parse_p_tag(sec)
        if not parsed:
            continue
        parent = f"P{parsed[0]}"
        letters = parsed[1]
        # Promote lettered sections when motor is on this controller
        if letters and not letters.startswith("_P"):
            prov = [
                {
                    "kind": "letter_motor_promotion",
                    "motor": mot,
                    "parent_mechanical": parent if parent in mechanical else None,
                    "rule": "Letter motors M{n}A.. on controller promote P{n}A.. sections",
                    "confidence": PROVEN_CROSS_TABLE,
                    **(minfo.get("provenance") or {}),
                }
            ]
            atype = (mechanical.get(parent) or {}).get("asc_type") or ""
            _ensure_section(
                sec,
                confidence=PROVEN_CROSS_TABLE,
                provenance=prov,
                parent=parent,
                asc_type=atype,
                kind="letter_motor_promotion",
                motor=mot,
            )
            owned_mechanical.add(parent)
            if parent in mechanical and parent not in sections:
                _ensure_section(
                    parent,
                    confidence=PROVEN_RUN,
                    provenance=mechanical[parent]["provenance"],
                    parent=parent,
                    asc_type=mechanical[parent]["asc_type"],
                    kind="mechanical",
                )
        elif not letters:
            # Plain motor M128 → evidence for P128
            if sec in mechanical:
                owned_mechanical.add(sec)
                _ensure_section(
                    sec,
                    confidence=PROVEN_RUN,
                    provenance=[
                        {
                            "kind": "motor_owns_mechanical",
                            "motor": mot,
                            "confidence": PROVEN_CROSS_TABLE,
                        }
                    ]
                    + mechanical[sec]["provenance"],
                    parent=sec,
                    asc_type=mechanical[sec]["asc_type"],
                    kind="mechanical",
                    motor=mot,
                )

    # PE section tokens → P{n}_P1 etc. (photocell CONTROL_SECTION evidence).
    # GATE F: SSV*/SSVEZPE*_P1/_P2 solenoids are DEVICE_SIGNAL — do not promote
    # independent conveyor sections solely from solenoid naming; keep/restore
    # master P{n} when RUN mechanical evidence proves it.
    for rec in pe_ssv_on_ctrl:
        sec = rec.get("section")
        if not sec:
            continue
        parsed = parse_p_tag(sec)
        if not parsed:
            continue
        parent = f"P{parsed[0]}"
        suffix = parsed[1]
        io_name = rec.get("io_name") or ""
        if suffix.startswith("_P"):
            if rec.get("is_ssv") and is_solenoid_device_signal(io_name):
                # Solenoid naming alone ≠ pe_ssv_section. Restore/keep master.
                if parent in mechanical:
                    owned_mechanical.add(parent)
                    if parent not in sections:
                        _ensure_section(
                            parent,
                            confidence=PROVEN_RUN,
                            provenance=list(mechanical[parent]["provenance"])
                            + [
                                {
                                    "kind": "ssv_device_signal",
                                    "io_name": io_name,
                                    "device_signal_token": sec,
                                    "rule": (
                                        "SSVEZPE*_P1/_P2 is DEVICE_SIGNAL — "
                                        "keep master P{n} CONTROL_SECTION"
                                    ),
                                    "confidence": PROVEN_CROSS_TABLE,
                                }
                            ],
                            parent=parent,
                            asc_type=mechanical[parent]["asc_type"],
                            kind="mechanical",
                        )
                    elif parent in sections:
                        sections[parent].setdefault("provenance", []).append(
                            {
                                "kind": "ssv_device_signal",
                                "io_name": io_name,
                                "device_signal_token": sec,
                                "rule": (
                                    "SSVEZPE*_P1/_P2 is DEVICE_SIGNAL — "
                                    "not an independent conveyor section"
                                ),
                                "confidence": PROVEN_CROSS_TABLE,
                            }
                        )
                continue
            atype = (mechanical.get(parent) or mechanical.get(sec) or {}).get("asc_type") or ""
            # Prefer ZEROPRESSURE/ACCUM from parent family when promoting merge sections
            for cand in (parent, f"{parent}A", sec):
                if cand in mechanical:
                    atype = mechanical[cand]["asc_type"]
                    break
            prov = [
                {
                    "kind": "pe_section",
                    "io_name": io_name,
                    "type": rec.get("type"),
                    "rule": "EZPE{n}_P1 → section id P{n}_P1 (photocell CONTROL_SECTION)",
                    "confidence": PROVEN_CROSS_TABLE,
                }
            ]
            _ensure_section(
                sec,
                confidence=PROVEN_CROSS_TABLE,
                provenance=prov,
                parent=parent,
                asc_type=atype,
                kind="pe_ssv_section",
            )
            owned_mechanical.add(parent)
            if parent in mechanical and parent not in sections:
                _ensure_section(
                    parent,
                    confidence=PROVEN_RUN,
                    provenance=mechanical[parent]["provenance"],
                    parent=parent,
                    asc_type=mechanical[parent]["asc_type"],
                    kind="mechanical",
                )
        else:
            # Non-section PE still owns mechanical / lettered id
            if sec in mechanical or sec in sections:
                owned_mechanical.add(parent if parent in mechanical else sec)
                _ensure_section(
                    sec,
                    confidence=PROVEN_RUN if sec in mechanical else PROVEN_CROSS_TABLE,
                    provenance=[
                        {
                            "kind": "pe_link",
                            "io_name": rec["io_name"],
                            "confidence": PROVEN_CROSS_TABLE,
                        }
                    ],
                    parent=parent,
                    asc_type=(mechanical.get(sec) or {}).get("asc_type") or "",
                    kind="mechanical" if sec in mechanical else "pe_linked",
                )

    # Mtrchain chained SSV / P identities
    for ev in mtr_evidence:
        sec = ev.get("section")
        if not sec:
            continue
        parsed = parse_p_tag(sec)
        parent = f"P{parsed[0]}" if parsed else sec
        atype = (mechanical.get(parent) or mechanical.get(sec) or {}).get("asc_type") or ""
        _ensure_section(
            sec,
            confidence=PROVEN_CROSS_TABLE,
            provenance=[ev],
            parent=parent,
            asc_type=atype,
            kind="mtrchain_chained",
            motor=ev.get("motor") or "",
        )

    # Drop untagged mechanical with no device evidence on this controller
    final_sections = {
        k: v
        for k, v in sections.items()
        if v.get("from_mechanical_row")
        or v.get("kind")
        in (
            "letter_motor_promotion",
            "pe_ssv_section",
            "mtrchain_chained",
            "pe_linked",
        )
        or k in owned_mechanical
    }

    # Keep mechanical parents that gained letter/section children
    for sid, info in list(final_sections.items()):
        parent = info.get("parent_mechanical") or ""
        if parent and parent in mechanical and parent not in final_sections:
            final_sections[parent] = {
                "id": parent,
                "parent_mechanical": parent,
                "kind": "mechanical",
                "asc_type": mechanical[parent]["asc_type"],
                "motor": "",
                "confidence": PROVEN_RUN,
                "provenance": mechanical[parent]["provenance"],
                "from_mechanical_row": True,
            }

    final_assemblies: dict[str, Any] = {}
    for sid, info in final_sections.items():
        parent = info.get("parent_mechanical") or sid
        asm = final_assemblies.setdefault(
            parent,
            {
                "id": parent,
                "sections": [],
                "mechanical": parent if parent in mechanical else None,
                "asc_type": (mechanical.get(parent) or {}).get("asc_type"),
                "provenance": [],
            },
        )
        if sid not in asm["sections"]:
            asm["sections"].append(sid)
        asm["provenance"].extend(info.get("provenance") or [])

    for asm in final_assemblies.values():
        asm["sections"] = sorted(set(asm["sections"]))
        # Dedupe provenance by kind+key
        seen = set()
        uniq = []
        for p in asm["provenance"]:
            key = (p.get("kind"), p.get("motor"), p.get("io_name"), p.get("section"), p.get("chained"))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(p)
        asm["provenance"] = uniq

    # Assembly-only parents: mechanical bodies that must NOT emit their own Conv when
    # letter-motor or PE/SSV sections were promoted for the same numeric family.
    # Evidence: M130A..E motors → sections P130A..E; EZPE150_P1/SSV → P150_P1 (not bare P150).
    suppress_as_assembly_only: dict[str, dict[str, Any]] = {}
    letter_children: dict[str, list[str]] = defaultdict(list)
    pe_children: dict[str, list[str]] = defaultdict(list)
    for sid, info in final_sections.items():
        parent = str(info.get("parent_mechanical") or "").upper()
        kind = info.get("kind") or ""
        if kind == "letter_motor_promotion" and parent:
            letter_children[parent].append(sid)
        if kind == "pe_ssv_section" and parent:
            pe_children[parent].append(sid)

    for parent, kids in letter_children.items():
        if parent and parent in final_sections and kids:
            # PL-3: when bare motor M{n} exists on this controller alongside M{n}A,
            # parent P{n} is a DISTINCT conveyor identity — never assembly-only.
            # (M220_AUX != M220A_AUX; suppressing P220 forced M220→P220A collision.)
            parsed_parent = parse_p_tag(parent)
            bare_motor = f"M{parsed_parent[0]}" if parsed_parent else ""
            if bare_motor and bare_motor in motors_on_ctrl:
                continue
            suppress_as_assembly_only[parent] = {
                "reason": "letter_motor_sections_promoted",
                "children": sorted(kids),
                "confidence": PROVEN_CROSS_TABLE,
                "rule": (
                    "When M{n}A.. letter motors promote P{n}A.. sections, mechanical "
                    "P{n} is the assembly body — do not emit P{n}_Conv "
                    "(skipped when bare M{n} also exists on controller)"
                ),
            }
            final_sections[parent]["assembly_only"] = True

    for parent, kids in pe_children.items():
        if not kids:
            continue
        # Suppress bare parent and lettered mechanical siblings (P150, P150A) —
        # PE/SSV _P1/_P2 tokens are the conveyor sections for PLC/Fast_Conv.
        family = [parent]
        for sid, minfo in mechanical.items():
            parsed = parse_p_tag(sid)
            if parsed and f"P{parsed[0]}" == parent and not (parsed[1] or "").startswith("_P"):
                family.append(sid)
        for memb in family:
            if memb not in final_sections:
                continue
            # Don't suppress a member that is itself a pe_ssv_section
            if (final_sections[memb].get("kind") or "") == "pe_ssv_section":
                continue
            suppress_as_assembly_only[memb] = {
                "reason": "pe_ssv_sections_promoted",
                "children": sorted(kids),
                "confidence": PROVEN_CROSS_TABLE,
                "rule": (
                    "When EZPE{n}_P1 photocells promote P{n}_P1 sections, "
                    "mechanical P{n}/P{n}A are assembly bodies — do not emit their Conv "
                    "(SSVEZPE solenoids alone never promote — GATE F)"
                ),
            }
            final_sections[memb]["assembly_only"] = True

    # Preferred Fast_Conv induct when downstream resolves to a bare parent with _P1 child
    preferred_induct: dict[str, str] = {}
    for parent, kids in pe_children.items():
        p1 = f"{parent}_P1"
        if p1 in kids or p1 in final_sections:
            preferred_induct[parent] = p1

    return {
        "machine": machine,
        "run_dir": str(run_dir),
        "generated_at": _ts(),
        "sections": dict(sorted(final_sections.items())),
        "assemblies": dict(sorted(final_assemblies.items())),
        "suppress_as_assembly_only": dict(sorted(suppress_as_assembly_only.items())),
        "preferred_induct": dict(sorted(preferred_induct.items())),
        "motors_on_controller": sorted(motors_on_ctrl.keys()),
        "mtrchain_chained_sections": sorted(mtr_chained_sections),
        "source_of_truth": "RUN Conveyor.asc + Mtrchain.asc + PE/SSV naming (finished PLC validation-only)",
    }


def infer_downstream_details(
    run_dir: Path | str,
    *,
    preferred_induct: dict[str, str] | None = None,
    suppress_as_assembly_only: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """section → {physical_downstream, control_downstream, confidence, provenance}.

    GATE I: physical topology and Fast_Conv control_downstream are separate.
    Passive physical segments (curves/slaves without independent control) must not
    interrupt control_downstream resolution — walk through preferred_induct /
    assembly suppress to the next CONTROL_SECTION.
    """
    run_dir = _norm_run_dir(run_dir)
    mtr_rows = _load_mtrchain_rows(run_dir)
    full_rows = _load_fullline_rows(run_dir)
    preferred_induct = {str(k).upper(): str(v).upper() for k, v in (preferred_induct or {}).items()}
    suppress = dict(suppress_as_assembly_only or {})
    out: dict[str, dict[str, Any]] = {}

    def _control_resolve(dst: str) -> str:
        """Map a physical/control token to the Fast_Conv control section."""
        du = (dst or "").upper()
        if not du:
            return du
        # Prefer _P1 induct when parent is assembly-only / has preferred child
        if du in preferred_induct:
            return str(preferred_induct[du]).upper()
        if du in suppress and preferred_induct.get(du):
            return str(preferred_induct[du]).upper()
        return du

    def _set(src: str, dst: str, provenance: dict[str, Any]) -> None:
        if not src or not dst or src == dst:
            return
        su, du = src.upper(), dst.upper()
        control_du = _control_resolve(du)
        prev = out.get(su)
        if prev and prev.get("control_downstream") == control_du:
            prev.setdefault("provenance", []).append(provenance)
            # Keep physical edge too
            if prev.get("physical_downstream") != du:
                prev.setdefault("physical_alternates", []).append(du)
            return
        if prev and prev.get("confidence") == PROVEN_CROSS_TABLE:
            # Keep first proven edge; record conflict
            prev.setdefault("conflicts", []).append(
                {"physical_downstream": du, "control_downstream": control_du, "provenance": provenance}
            )
            return
        out[su] = {
            "downstream": control_du,  # back-compat for Fast_Conv consumers
            "physical_downstream": du,
            "control_downstream": control_du,
            "confidence": PROVEN_CROSS_TABLE,
            "provenance": [provenance],
        }

    for row in mtr_rows:
        motor = _clean(row.get("Motor_Name"))
        timer = _clean(row.get("Timer_Name"))
        if not motor or not timer:
            continue
        next_mot = _parse_timer_motor(timer)
        if not next_mot:
            continue
        src = _motor_to_section(motor)
        dst = _motor_to_section(next_mot)
        if not src or not dst:
            continue
        _set(
            src,
            dst,
            {
                "kind": "mtrchain_timer_name",
                "table": "Mtrchain.asc",
                "motor": motor.upper(),
                "timer_name": timer,
                "next_motor": next_mot,
                "rule": (
                    "Timer_Name=tmM{next} means {next} starts before product leaves "
                    "current motor → downstream of current section is next section"
                ),
                "confidence": PROVEN_CROSS_TABLE,
            },
        )

    # Fullline Response IO stops upstream motor → that motor's section is upstream of Conveyor_Name
    for row in full_rows:
        sensor = _clean(row.get("Sensor_Name") or row.get("Desc"))
        conv = _clean(row.get("Conveyor_Name"))
        resp = _clean(row.get("Response IO"))
        if not conv or not resp:
            continue
        resp_u = resp.upper()
        # Response is a motor → motor section is upstream of conv (possibly sectionized via sensor)
        if _MOTOR_RE.match(resp_u):
            up_sec = _motor_to_section(resp_u)
            down_sec = conv.upper()
            # Prefer PE section token when sensor encodes _P1
            pe_sec = _section_from_pe_or_ssv(sensor) if sensor else None
            if pe_sec and parse_p_tag(pe_sec) and parse_p_tag(pe_sec)[1].startswith("_P"):
                # Sensor section may differ from Conveyor_Name (EZPE150_F1 → P150_P1 vs P150A)
                # Fullline Conveyor_Name is authoritative for which belt the full eye is on
                down_sec = conv.upper()
            if up_sec:
                _set(
                    up_sec,
                    down_sec,
                    {
                        "kind": "fullline_response_upstream",
                        "table": "Fullline.asc",
                        "sensor": sensor,
                        "conveyor_name": conv,
                        "response_io": resp_u,
                        "rule": (
                            "Fullline Response IO stops upstream motor "
                            "(Response motor ⇒ upstream of Conveyor_Name)"
                        ),
                        "confidence": PROVEN_CROSS_TABLE,
                    },
                )
        elif resp_u.startswith("SSV"):
            # Response SSV is release endpoint on (usually upstream) section — topology hint only
            ssv_sec = _section_from_pe_or_ssv(resp_u)
            if ssv_sec and conv:
                # Do not invent downstream from SSV response alone (hold valve, not flow)
                pass

    return out


def infer_downstream_from_mtrchain(
    run_dir: Path | str,
    *,
    preferred_induct: dict[str, str] | None = None,
) -> dict[str, str]:
    """section → downstream from RUN Mtrchain Timer_Name edges ONLY (PD-0035).

    Fullline / merge-latch / geometry evidence must NOT enter this map — those use
    a different provenance class at the stamp site. Never upgrade convenience
    inference to RUN_MTRCHAIN_PROVEN.

    When preferred_induct maps bare P{n} → P{n}_P1 (from PE/SSV section discovery),
    remap destination so Fast_Conv targets the induct section, not the assembly body.
    """
    details = infer_downstream_details(run_dir)
    prefer = {str(k).upper(): str(v).upper() for k, v in (preferred_induct or {}).items() if k and v}
    out: dict[str, str] = {}
    for k, v in details.items():
        if not (v.get("downstream") and v.get("confidence") == PROVEN_CROSS_TABLE):
            continue
        prov = v.get("provenance") or []
        # PD-0035: only stamp candidates whose provenance includes mtrchain_timer_name
        has_mtr = any(
            isinstance(p, dict) and p.get("kind") == "mtrchain_timer_name" for p in prov
        )
        if not has_mtr:
            continue
        ds = str(v["downstream"]).upper()
        if ds in prefer:
            ds = prefer[ds]
        out[k] = ds
    return out


def infer_downstream_from_fullline(
    run_dir: Path | str,
    *,
    preferred_induct: dict[str, str] | None = None,
) -> dict[str, str]:
    """section → downstream from Fullline Response IO only (not Mtrchain).

    Callers must stamp RUN_FULLLINE_DERIVED / REVIEW_REQUIRED — never RUN_MTRCHAIN_PROVEN.
    """
    details = infer_downstream_details(run_dir)
    prefer = {str(k).upper(): str(v).upper() for k, v in (preferred_induct or {}).items() if k and v}
    out: dict[str, str] = {}
    for k, v in details.items():
        if not v.get("downstream"):
            continue
        prov = v.get("provenance") or []
        has_full = any(
            isinstance(p, dict) and p.get("kind") == "fullline_response_upstream" for p in prov
        )
        has_mtr = any(
            isinstance(p, dict) and p.get("kind") == "mtrchain_timer_name" for p in prov
        )
        # Only Fullline-only edges (Mtrchain already covered elsewhere)
        if not has_full or has_mtr:
            continue
        ds = str(v["downstream"]).upper()
        if ds in prefer:
            ds = prefer[ds]
        out[k] = ds
    return out


def build_transport_relationship_matrix(
    run_dir: Path | str,
    machine: str,
    *,
    finished_path: Path | str | None = None,
) -> dict[str, Any]:
    """RUN-derived section topology matrix. Finished columns optional (validation only)."""
    run_dir = _norm_run_dir(run_dir)
    discovered = discover_sections(run_dir, machine)
    downstream = infer_downstream_details(run_dir)
    sections = discovered.get("sections") or {}

    finished_ds: dict[str, str] = {}
    if finished_path:
        # Optional validation — never used as generation source
        finished_ds = _optional_finished_downstream(Path(finished_path))

    rows = []
    for sid, info in sorted(sections.items()):
        ds = downstream.get(sid) or {}
        row = {
            "section": sid,
            "parent_mechanical": info.get("parent_mechanical"),
            "kind": info.get("kind"),
            "asc_type": info.get("asc_type"),
            "motor": info.get("motor") or "",
            "downstream": ds.get("downstream") or "",
            "downstream_confidence": ds.get("confidence") or UNRESOLVED,
            "downstream_provenance": ds.get("provenance") or [],
            "section_confidence": info.get("confidence"),
            "section_provenance": info.get("provenance") or [],
        }
        if finished_path:
            row["finished_downstream"] = finished_ds.get(sid.upper(), "")
            row["finished_match"] = (
                bool(row["downstream"])
                and row["downstream"].upper() == str(row["finished_downstream"]).upper()
            )
        rows.append(row)

    return {
        "generated_at": _ts(),
        "machine": machine,
        "run_dir": str(run_dir),
        "source_of_truth": "RUN + cross-table (Mtrchain Timer_Name, Fullline Response IO, PE/SSV)",
        "finished_validation_only": bool(finished_path),
        "finished_path": str(finished_path) if finished_path else None,
        "section_count": len(rows),
        "downstream_proven_count": sum(1 for r in rows if r["downstream"]),
        "rows": rows,
        "assemblies": discovered.get("assemblies") or {},
    }


def build_conveyor_type_matrix(
    run_dir: Path | str,
    machine: str,
    *,
    finished_path: Path | str | None = None,
) -> dict[str, Any]:
    """RUN-derived conveyor type_code matrix for discovered sections."""
    run_dir = _norm_run_dir(run_dir)
    discovered = discover_sections(run_dir, machine)
    rows_asc = _load_conveyor_rows(run_dir)

    # VFD numbers on this machine
    vfd_keys: set[str] = set()
    for row in rows_asc:
        rn = _clean(row.get("IO_Name"))
        if not re.match(r"^VFD", rn, re.I):
            continue
        if not _controller_device(row, machine):
            continue
        m = re.match(r"^VFD[\s\-_]*([A-Z0-9]*\d[A-Z0-9]{0,6})", rn, re.I)
        if m:
            c = re.sub(r"(_EN|_AUX|_FLT|_RUN|_OK)$", "", m.group(1), flags=re.I).upper()
            vfd_keys.add(c)
            dm = re.search(r"(\d{2,4})", c)
            if dm:
                vfd_keys.add(dm.group(1))

    mech_by_id = {}
    for row in rows_asc:
        n = normalize_io_name(_clean(row.get("IO_Name")))
        if n and _P_TAG_RE.match(n.upper()):
            mech_by_id[n.upper()] = row

    finished_types: dict[str, Any] = {}
    if finished_path:
        finished_types = _optional_finished_types(Path(finished_path))

    rows = []
    for sid, info in sorted((discovered.get("sections") or {}).items()):
        parent = info.get("parent_mechanical") or sid
        asc_type = info.get("asc_type") or ""
        drive = ""
        desc = ""
        src_row = mech_by_id.get(sid) or mech_by_id.get(parent)
        if src_row:
            asc_type = asc_type or (src_row.get("Type") or "").strip().upper()
            drive = _clean(src_row.get("Drive"))
            desc = _clean(src_row.get("General_Description"))
        is_vfd = bool(re.search(r"\bVFD\b", f"{sid} {desc} {drive}", re.I))
        if drive and drive not in ("0", "1", " ", "N", "~") and any(c.isalpha() for c in drive):
            is_vfd = True
        pm = re.match(r"^P(\d{2,4})", sid, re.I)
        if pm and (pm.group(1) in vfd_keys or sid[1:] in vfd_keys):
            is_vfd = True
        classified = classify_conv_type(asc_type, is_vfd)
        row = {
            "section": sid,
            "parent_mechanical": parent,
            "asc_type": asc_type or UNRESOLVED,
            "is_vfd": is_vfd,
            "type_code": classified["type_code"],
            "type_str": classified["type_str"],
            "confidence": classified["confidence"] if asc_type else UNRESOLVED,
            "provenance": classified["provenance"],
        }
        if finished_path:
            ft = finished_types.get(sid.upper())
            row["finished_type_code"] = ft
            row["finished_match"] = ft is not None and int(ft) == int(classified["type_code"])
        rows.append(row)

    return {
        "generated_at": _ts(),
        "machine": machine,
        "run_dir": str(run_dir),
        "source_of_truth": "RUN ASC Type + VFD evidence; library type codes (DOC_DEFINED)",
        "finished_validation_only": bool(finished_path),
        "finished_path": str(finished_path) if finished_path else None,
        "type_code_legend": {
            "0": "P1000 Transport+VFD",
            "1": "P2000 Accum+VFD",
            "2": "P4000 Accum+MS",
            "3": "P3000 Transport+MS",
        },
        "rows": rows,
    }


def _optional_finished_downstream(finished_path: Path) -> dict[str, str]:
    """Best-effort parse of finished L5X Fast_Conv next tags — validation only."""
    if not finished_path.is_file():
        return {}
    try:
        text = finished_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out: dict[str, str] = {}
    # Fast_Conv(P130A_Conv_AOI.Fast,P130A_Conv,...,P130B_Conv,...)
    for m in re.finditer(
        r"Fast_Conv\([^,]+,([A-Za-z0-9_]+)_Conv,[^,]+,[^,]+,([A-Za-z0-9_]+)_Conv",
        text,
    ):
        src, dst = m.group(1).upper(), m.group(2).upper()
        if dst in ("NO", "NEXT"):
            continue
        out[src] = dst
    return out


def _optional_finished_types(finished_path: Path) -> dict[str, int]:
    if not finished_path.is_file():
        return {}
    try:
        text = finished_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out: dict[str, int] = {}
    for m in re.finditer(r"([A-Za-z0-9_]+)_Conv\.Type\s*:=\s*(\d+)", text):
        out[m.group(1).upper()] = int(m.group(2))
    return out


def write_matrices(
    run_dir: Path | str,
    machine: str,
    out_dir: Path | str,
    *,
    finished_path: Path | str | None = None,
) -> dict[str, Path]:
    out_dir = Path(out_dir)
    if not out_dir.is_absolute():
        out_dir = (REPO_ROOT / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    rel = build_transport_relationship_matrix(run_dir, machine, finished_path=finished_path)
    typ = build_conveyor_type_matrix(run_dir, machine, finished_path=finished_path)
    p_rel = out_dir / "transport_relationship_matrix.json"
    p_typ = out_dir / "conveyor_type_matrix.json"
    p_rel.write_text(json.dumps(rel, indent=2), encoding="utf-8")
    p_typ.write_text(json.dumps(typ, indent=2), encoding="utf-8")
    return {"transport_relationship_matrix": p_rel, "conveyor_type_matrix": p_typ}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Discover conveyor sections + write relationship/type matrices")
    ap.add_argument("--run-dir", default="workspace/active/RUN")
    ap.add_argument("--machine", default="")
    ap.add_argument("--out", default="internal")
    ap.add_argument(
        "--finished",
        default="",
        help="Optional finished L5X for validation columns only (never generation)",
    )
    args = ap.parse_args(argv)
    run_dir = _norm_run_dir(args.run_dir)
    machine = (args.machine or "").strip()
    if not machine:
        machine = read_project_meta(run_dir).get("machine_name") or ""
    if not machine:
        print("ERROR: --machine required (or project.cfg machine_name)", file=sys.stderr)
        return 2
    finished = Path(args.finished) if args.finished else None
    discovered = discover_sections(run_dir, machine)
    downstream = infer_downstream_from_mtrchain(run_dir)
    paths = write_matrices(run_dir, machine, args.out, finished_path=finished)

    sections = discovered.get("sections") or {}
    expect = [
        "P130A",
        "P130B",
        "P130C",
        "P130D",
        "P130E",
        "P145A",
        "P145B",
        "P145C",
        "P145D",
        "P145E",
        "P136_P1",
        "P136_P2",
        "P150_P1",
        "P150_P2",
    ]
    present = [s for s in expect if s in sections]
    missing = [s for s in expect if s not in sections]
    ssv = resolve_ssv_endpoint("SSVEZPE150_P1", set(sections)) or resolve_ssv_endpoint(
        "SSV150_P1", set(sections)
    )
    print(f"machine={machine}")
    print(f"sections={len(sections)} assemblies={len(discovered.get('assemblies') or {})}")
    print(f"expected_present={present}")
    print(f"expected_missing={missing}")
    print(f"SSV150_P1/SSVEZPE150_P1 → {ssv}")
    print(f"P128 downstream → {downstream.get('P128', '')}")
    print(f"wrote {paths['transport_relationship_matrix']}")
    print(f"wrote {paths['conveyor_type_matrix']}")
    # Sample rows
    for sample in ("P128", "P130A", "P130E", "P145A", "P150_P1", "P136_P1"):
        ds = downstream.get(sample, "")
        info = sections.get(sample) or {}
        print(f"  {sample}: kind={info.get('kind')} ds={ds} conf={info.get('confidence')}")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
