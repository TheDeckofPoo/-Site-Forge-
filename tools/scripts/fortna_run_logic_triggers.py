"""Parse RUN Logic.asc / horns.asc for proven IF→THEN command relationships.

Production Autogen may emit writers only from these RUN facts — never invent
seal-in, Stop PB, or digit-match ownership (PD-0002 / PD-0005 freeze).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _norm_run(run_dir: Path | str) -> Path:
    p = Path(run_dir)
    if (p / "FORTNA").is_dir():
        return p
    if (p / "RUN" / "FORTNA").is_dir():
        return p / "RUN"
    return p


def _part_token(blob: str) -> str:
    """Extract Fortna IO_Name from 'part named NAME DESC at I/O address…'."""
    m = re.search(
        r"part named\s+([A-Za-z0-9_]+)(?:\s|$)",
        blob or "",
        re.I,
    )
    return (m.group(1) if m else "").strip().upper()


def parse_logic_asc(run_dir: Path | str) -> list[dict[str, Any]]:
    """Return [{trigger, name, conditions:[{io,sense}], actions:[{io,sense}]}] from Logic.asc."""
    fortna = _norm_run(run_dir) / "FORTNA"
    path = fortna / "Logic.asc"
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    out: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        # Fortna tilde-CSV: normalize ~ to spaces for parsing
        line = raw_line.replace("~", " ")
        if "Trigger #" not in line and "TRIGGER #" not in line.upper():
            continue
        tm = re.search(
            r"REFERENCE\s+Trigger\s*#\s*(\d+)\s+Name\s+(.+?)$",
            line,
            re.I,
        )
        if not tm:
            continue
        trig_n = int(tm.group(1))
        trig_name = tm.group(2).strip()
        # Split IF … THEN … (tildes already spaces)
        if_m = re.search(
            r"IF\s+(.+?)\s+THEN\s+(.+?)\s+REFERENCE\s+Trigger",
            line,
            re.I | re.S,
        )
        if not if_m:
            continue
        cond_blob, act_blob = if_m.group(1), if_m.group(2)
        conditions: list[dict[str, str]] = []
        for part in re.split(r"\s+AND\s+IF\s+", cond_blob, flags=re.I):
            io = _part_token(part)
            if not io:
                continue
            sense = "ON" if re.search(r"\bIS ON\b", part, re.I) else (
                "OFF" if re.search(r"\bIS OFF\b", part, re.I) else "ON"
            )
            conditions.append({"io": io, "sense": sense})
        actions: list[dict[str, str]] = []
        for part in re.split(r"\s+AND\s+", act_blob, flags=re.I):
            if "TURN ON" in part.upper():
                io = _part_token(part)
                if io:
                    actions.append({"io": io, "sense": "ON"})
            elif "TURN OFF" in part.upper():
                io = _part_token(part)
                if io:
                    actions.append({"io": io, "sense": "OFF"})
        if not conditions or not actions:
            continue
        out.append(
            {
                "trigger": trig_n,
                "name": trig_name,
                "conditions": conditions,
                "actions": actions,
                "provenance": "RUN_LOGIC_ASC",
                "confidence": "PROVEN",
            }
        )
    return out


def mcr_command_writers_from_run(run_dir: Path | str) -> list[dict[str, Any]]:
    """Proven MCR coil writers: IF air-pressure OK → TURN ON MCR coil.

    ORNCCP2: Trigger #3 PS312→2MCR1, Trigger #4 PS320→3MCR1.
    Does NOT invent Start/Stop seal-in or E-stop permissives.
    """
    writers: list[dict[str, Any]] = []
    for t in parse_logic_asc(run_dir):
        acts = [a for a in t["actions"] if re.match(r"^\d*MCR\d*$", a["io"], re.I)]
        if not acts:
            continue
        # Only simple single-condition APRESS-style commands (exact RUN evidence)
        conds = t["conditions"]
        if len(conds) != 1 or conds[0]["sense"] != "ON":
            # Multi-condition MCR commands need engineer review — do not invent
            for a in acts:
                writers.append(
                    {
                        "coil": a["io"],
                        "status": "REVIEW_REQUIRED",
                        "reason": "MCR_COMMAND_MULTI_CONDITION_UNPROVEN",
                        "trigger": t["trigger"],
                        "name": t["name"],
                        "conditions": conds,
                    }
                )
            continue
        src = conds[0]["io"]
        for a in acts:
            if a["sense"] != "ON":
                continue
            writers.append(
                {
                    "coil": a["io"],
                    "condition_io": src,
                    "condition_sense": "ON",
                    "status": "PROVEN",
                    "trigger": t["trigger"],
                    "name": t["name"],
                    "rung": f"XIC({src})OTE({a['io']});",
                    "provenance": "RUN_LOGIC_ASC",
                    "confidence": "PROVEN",
                }
            )
    return writers


def parse_horns_asc(run_dir: Path | str) -> list[dict[str, Any]]:
    """horns.asc: CP2 & WH310 HORN → hornio=2WH (CS/station command tag)."""
    fortna = _norm_run(run_dir) / "FORTNA"
    path = fortna / "horns.asc"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[1:]:
        parts = [p.strip() for p in line.split("~")]
        if len(parts) < 2:
            continue
        name, hornio = parts[0], parts[1]
        if not name or name in {"N/A", ""} or hornio in {"INVALID", "N/A", ""}:
            continue
        if "HORN" not in name.upper() and not re.match(r"^CP\d+", name, re.I):
            continue
        # Extract CPn from name like "CP2 & WH310 HORN"
        cp = ""
        m = re.search(r"\b(CP\d+)\b", name, re.I)
        if m:
            cp = m.group(1).upper()
        companion = ""
        m2 = re.search(r"\b(WH\d+|WB\d+)\b", name, re.I)
        if m2:
            companion = m2.group(1).upper()
        rows.append(
            {
                "name": name,
                "cp": cp,
                "hornio": hornio.upper(),
                "companion_wh": companion,
                "provenance": "RUN_HORNS_ASC",
                "confidence": "PROVEN",
            }
        )
    return rows


def horn_fire_triggers_from_run(run_dir: Path | str) -> list[dict[str, Any]]:
    """Trigger #87: 2WH ON → WH310 ON; #88: 3WH → WH318."""
    out: list[dict[str, Any]] = []
    for t in parse_logic_asc(run_dir):
        if len(t["conditions"]) != 1 or len(t["actions"]) != 1:
            continue
        src, dst = t["conditions"][0], t["actions"][0]
        if src["sense"] != "ON" or dst["sense"] != "ON":
            continue
        # hornio → physical WH/WB
        if not (
            re.match(r"^\d*WH\d*$", src["io"], re.I)
            or re.match(r"^WH\d+", src["io"], re.I)
        ):
            continue
        if not (
            re.match(r"^WH\d+", dst["io"], re.I)
            or re.match(r"^WB\d+", dst["io"], re.I)
        ):
            continue
        out.append(
            {
                "source": src["io"],
                "dest": dst["io"],
                "trigger": t["trigger"],
                "name": t["name"],
                "rung": f"XIC({src['io']})OTE({dst['io']});",
                "provenance": "RUN_LOGIC_ASC",
                "confidence": "PROVEN",
            }
        )
    return out


def beacon_jam_triggers_from_run(run_dir: Path | str) -> list[dict[str, Any]]:
    """BeaconTrigger.asc jam→beacon relationships (WB406/WB400). REVIEW until jam AOI wired."""
    fortna = _norm_run(run_dir) / "FORTNA"
    path = fortna / "BeaconTrigger.asc"
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[1:]:
        parts = [p.strip() for p in line.split("~")]
        if len(parts) < 6:
            continue
        name, _host, beacon_rec, pattern, _pri, trigger_input = parts[:6]
        if not beacon_rec or beacon_rec in {"N/A", ""}:
            continue
        # BeaconRecord often "WB406 3-1 MERGE" — take first token
        beacon = beacon_rec.split()[0].upper()
        if not re.match(r"^WB\d+", beacon):
            continue
        out.append(
            {
                "beacon": beacon,
                "name": name,
                "pattern": pattern,
                "trigger_input": trigger_input,
                "status": "REVIEW_REQUIRED",
                "reason": "BEACON_JAM_WRITER_NEEDS_JAM_AOI_BINDING",
                "provenance": "RUN_BEACON_TRIGGER_ASC",
                "confidence": "DERIVED",
            }
        )
    return out


def build_run_command_evidence(run_dir: Path | str) -> dict[str, Any]:
    return {
        "mcr_writers": mcr_command_writers_from_run(run_dir),
        "horns": parse_horns_asc(run_dir),
        "horn_fires": horn_fire_triggers_from_run(run_dir),
        "beacons": beacon_jam_triggers_from_run(run_dir),
        "logic_triggers": parse_logic_asc(run_dir),
    }
