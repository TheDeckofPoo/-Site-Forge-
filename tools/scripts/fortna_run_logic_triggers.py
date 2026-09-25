"""Parse RUN Logic.asc / horns.asc for proven IF→THEN command relationships.

Production Autogen may emit writers only from these RUN facts — never invent
seal-in, Stop PB, or digit-match ownership (PD-0002 / PD-0005 freeze).

Foreign-site generalization: multi-condition MCR commands (AND IF …) are first-class.
Every IF condition is preserved; never silently drop a condition or special-case
site trigger numbers / device names.
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


def _part_token(blob: str) -> tuple[str, str]:
    """Extract Fortna IO identity from 'part named NAME DESC at I/O address…'.

    Returns (io_identity, status) where status is PARSED | MULTIWORD | UNRESOLVED.
    Never truncates multi-word evidence into a plausible short tag (e.g. FIRE).
    Multi-word identities are underscore-normalized for Logix (FIRE_ALARM_ACTIVE).
    """
    text = blob or ""
    m = re.search(
        r"part named\s+(.+?)\s+at\s+I/O\s+address",
        text,
        re.I,
    )
    if not m:
        # Fallback: classic first-token only when full span missing
        m2 = re.search(r"part named\s+([A-Za-z0-9_]+)", text, re.I)
        if m2:
            return m2.group(1).strip().upper(), "PARSED"
        return "", "UNRESOLVED"
    span = m.group(1).strip()
    if not span:
        return "", "UNRESOLVED"
    words = span.split()
    first = words[0]
    # Classic Fortna IO_Name: alphanumeric/underscore first token
    # (6ESR1AUX, PS210, CP2_MCR1_AUX, ENABLE_SORTER_CP6, …)
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$|^\d+[A-Za-z0-9_]*$", first):
        # Reject English lead-ins that start multi-word internal names
        if first.upper() not in {
            "FIRE", "THE", "DATA", "RATE", "MENU", "ITEM", "RECORD", "AIR",
        }:
            return first.upper(), "PARSED"
    # Multi-word identity: often "NAME NAME" (name repeated as description)
    # e.g. FIRE ALARM ACTIVE FIRE ALARM ACTIVE → FIRE_ALARM_ACTIVE
    half = len(words) // 2
    if half >= 2 and words[:half] == words[half : 2 * half]:
        ident = "_".join(words[:half]).upper()
        return ident, "MULTIWORD"
    # Otherwise take tokens until IS ON/OFF / IS ENERGIZED / IS ADEQUATE appear
    # in the remaining description — keep leading identity words that look like a name
    stop = {"IS", "AT", "EQUALS"}
    kept: list[str] = []
    for w in words:
        if w.upper() in stop:
            break
        kept.append(w)
        # Cap runaway descriptions
        if len(kept) >= 6:
            break
    if not kept:
        return "", "UNRESOLVED"
    ident = "_".join(kept).upper()
    # Never return a single English word like FIRE as if it were a proven tag
    if len(kept) == 1 and kept[0].upper() in {
        "FIRE", "THE", "DATA", "RATE", "AIR", "MENU",
    }:
        return ident, "UNRESOLVED"
    return ident, "MULTIWORD"


def parse_logic_asc(run_dir: Path | str) -> list[dict[str, Any]]:
    """Return [{trigger, name, conditions:[{io,sense}], actions:[{io,sense}]}] from Logic.asc.

    Preserves every IF / ~IF / AND IF / ~AND IF condition and every TURN ON/OFF action.
    Never drops a condition silently. Never truncates multi-word evidence into FIRE.
    """
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
        # Split subsequent conditions on bare IF or AND IF (after ~ normalize).
        # ORINDY Trigger #27: ... IS ON ~IF part named PS210 ... (no AND).
        for part in re.split(r"\s+(?:AND\s+)?IF\s+", cond_blob, flags=re.I):
            part = part.strip()
            if not part:
                continue
            io, tok_status = _part_token(part)
            sense = "ON" if re.search(r"\bIS ON\b", part, re.I) else (
                "OFF" if re.search(r"\bIS OFF\b", part, re.I) else "ON"
            )
            if not io or tok_status == "UNRESOLVED":
                conditions.append(
                    {
                        "io": io or "",
                        "sense": sense,
                        "raw": part[:240],
                        "status": "UNRESOLVED",
                        "token_status": tok_status,
                    }
                )
                continue
            conditions.append(
                {
                    "io": io,
                    "sense": sense,
                    "raw": part[:240],
                    "status": "PARSED",
                    "token_status": tok_status,
                }
            )
        actions: list[dict[str, str]] = []
        for part in re.split(r"\s+AND\s+", act_blob, flags=re.I):
            if "TURN ON" in part.upper():
                io, _st = _part_token(part)
                if io:
                    actions.append({"io": io, "sense": "ON"})
            elif "TURN OFF" in part.upper():
                io, _st = _part_token(part)
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
                "condition_count": len(conditions),
            }
        )
    return out


def _resolve_condition_operand(
    io: str,
    sense: str,
    *,
    token_status: str = "PARSED",
    raw_blob: str = "",
) -> dict[str, Any]:
    """Resolve a raw Fortna IO condition through the canonical binding layer.

    Never emit bare ES_UDT / structure as XIC — prefer BOOL members (.I.ES_OK,
    .I.Pressure_OK, etc.) when proven. Returns REVIEW when unresolved.

    Never stamp PROVEN after lossy truncation (e.g. FIRE from FIRE ALARM ACTIVE).
    """
    raw = str(io or "").strip()
    if not raw or token_status == "UNRESOLVED":
        return {
            "raw": raw,
            "operand": "",
            "sense": sense,
            "status": "REVIEW_REQUIRED",
            "reason": "EMPTY_OR_LOSSY_CONDITION_IO",
            "token_status": token_status,
            "raw_blob": (raw_blob or "")[:200],
        }
    # Prefer air-pressure / power / safety member bindings when available
    try:
        from fortna_equipment_binding import classify_power_or_air

        pa = classify_power_or_air(raw, "AIR PRESSURE IS ADEQUATE")
        if pa and pa.get("confidence") == "PROVEN" and pa.get("member"):
            return {
                "raw": raw,
                "operand": f"{pa['canonical_id']}.{pa['member']}",
                "sense": sense,
                "status": "PROVEN",
                "binding": pa,
                "token_status": token_status,
            }
    except Exception:
        pass
    try:
        from fortna_io_extract import classify_estop

        # AUX feedback / ESR feedback → ES_UDT.I.ES_OK (never whole UDT)
        desc = raw_blob or ""
        es = classify_estop(raw, direction="I", description=desc)
        if es and es.get("member") and es.get("confidence") in {"PROVEN", "HIGH"}:
            cid = es.get("canonical_id") or raw
            if re.match(r"^\d", str(cid)):
                cid = f"T_{cid}"
            return {
                "raw": raw,
                "operand": f"{cid}.{es['member']}",
                "sense": sense,
                "status": "PROVEN",
                "binding": es,
                "token_status": token_status,
            }
    except Exception:
        pass
    # Multi-word / underscore identities without a proven binding stay REVIEW —
    # do not invent a local BOOL writer for FIRE_ALARM_ACTIVE etc.
    if token_status == "MULTIWORD" or "_" in raw and not re.match(
        r"^(?:T_)?(?:CP\d+_)?[A-Z0-9]+(?:_[A-Z0-9]+)*$", raw, re.I
    ):
        # Allow classic underscore tags (CP2_MCR1_AUX, 5ESR1AUX_INT) through
        if not re.match(
            r"^(?:\d+[A-Z]+\d*[A-Z]*|CP\d+_[A-Z0-9_]+|[A-Z]+\d+[A-Z0-9_]*)$",
            raw,
            re.I,
        ):
            return {
                "raw": raw,
                "operand": "",
                "sense": sense,
                "status": "REVIEW_REQUIRED",
                "reason": "MULTIWORD_CONDITION_UNBOUND",
                "token_status": token_status,
                "raw_blob": (raw_blob or "")[:200],
            }
    # Studio-legal BOOL tag form for digit-leading names
    op = raw
    if re.match(r"^\d", raw):
        op = f"T_{raw}"
    return {
        "raw": raw,
        "operand": op,
        "sense": sense,
        "status": "PROVEN",
        "binding": None,
        "token_status": token_status,
    }


def _compose_condition_rung(resolved: list[dict[str, Any]]) -> str:
    """Build compound XIC/XIO chain preserving every condition's ON/OFF sense."""
    parts: list[str] = []
    for r in resolved:
        op = r.get("operand") or ""
        if not op:
            continue
        sense = str(r.get("sense") or "ON").upper()
        if sense == "OFF":
            parts.append(f"XIO({op})")
        else:
            parts.append(f"XIC({op})")
    return "".join(parts)


def mcr_command_writers_from_run(run_dir: Path | str) -> list[dict[str, Any]]:
    """Proven MCR coil writers from RUN Logic.asc — multi-condition capable.

    Preserves every IF condition. Emits a compound Boolean rung when all
    operands resolve. If any required condition is unresolved → REVIEW_REQUIRED
    (never emit a shortened approximation).

    Does NOT invent Start/Stop seal-in. Does NOT special-case site trigger #s.
    """
    writers: list[dict[str, Any]] = []
    for t in parse_logic_asc(run_dir):
        acts = [a for a in t["actions"] if re.match(r"^\d*MCR\d*$", a["io"], re.I)]
        if not acts:
            continue
        conds = t["conditions"]
        resolved = [
            _resolve_condition_operand(
                c.get("io") or "",
                c.get("sense") or "ON",
                token_status=str(c.get("token_status") or c.get("status") or "PARSED"),
                raw_blob=str(c.get("raw") or ""),
            )
            for c in conds
        ]
        unresolved = [
            r for r in resolved
            if r.get("status") != "PROVEN" or not r.get("operand")
        ]
        # Also treat empty-io / UNRESOLVED parse stubs as unresolved
        if any(
            (not (c.get("io") or "")) or str(c.get("status") or "") == "UNRESOLVED"
            for c in conds
        ):
            # force REVIEW — never stamp PROVEN after lossy normalization
            if not unresolved:
                unresolved = [r for r in resolved if True]

        for a in acts:
            if a["sense"] != "ON":
                writers.append(
                    {
                        "coil": a["io"],
                        "status": "REVIEW_REQUIRED",
                        "reason": "MCR_COMMAND_OFF_ACTION_UNSUPPORTED",
                        "trigger": t["trigger"],
                        "name": t["name"],
                        "conditions": conds,
                        "resolved_conditions": resolved,
                    }
                )
                continue
            if unresolved:
                writers.append(
                    {
                        "coil": a["io"],
                        "status": "REVIEW_REQUIRED",
                        "reason": "MCR_COMMAND_CONDITION_UNRESOLVED",
                        "trigger": t["trigger"],
                        "name": t["name"],
                        "conditions": conds,
                        "resolved_conditions": resolved,
                        "unresolved": [
                            {"raw": r.get("raw"), "reason": r.get("reason") or r.get("status")}
                            for r in unresolved
                        ],
                    }
                )
                continue
            cond_chain = _compose_condition_rung(resolved)
            if not cond_chain:
                writers.append(
                    {
                        "coil": a["io"],
                        "status": "REVIEW_REQUIRED",
                        "reason": "MCR_COMMAND_EMPTY_CONDITION_CHAIN",
                        "trigger": t["trigger"],
                        "name": t["name"],
                        "conditions": conds,
                    }
                )
                continue
            coil_raw = a["io"]
            # Studio-legal coil tag (digit-leading → T_*)
            coil = coil_raw if re.match(r"^[A-Za-z_]", coil_raw) else f"T_{coil_raw}"
            writers.append(
                {
                    "coil": coil_raw,
                    "coil_tag": coil,
                    "conditions": conds,
                    "resolved_conditions": resolved,
                    "condition_count": len(resolved),
                    "condition_io": resolved[0]["raw"] if len(resolved) == 1 else "",
                    "condition_sense": resolved[0]["sense"] if len(resolved) == 1 else "AND",
                    "status": "PROVEN",
                    "trigger": t["trigger"],
                    "name": t["name"],
                    "rung": f"{cond_chain}OTE({coil});",
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
    """Horn fire: hornio ON → physical WH/WB ON (any trigger # with that shape)."""
    out: list[dict[str, Any]] = []
    for t in parse_logic_asc(run_dir):
        if len(t["conditions"]) != 1 or len(t["actions"]) != 1:
            continue
        src, dst = t["conditions"][0], t["actions"][0]
        if src.get("sense") != "ON" or dst.get("sense") != "ON":
            continue
        if not src.get("io") or not dst.get("io"):
            continue
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
                "status": "PROVEN",
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
    """Aggregate RUN-proven command writers for Autogen Control_Station emit."""
    return {
        "mcr_writers": mcr_command_writers_from_run(run_dir),
        "horns": parse_horns_asc(run_dir),
        "horn_fires": horn_fire_triggers_from_run(run_dir),
        "beacons": beacon_jam_triggers_from_run(run_dir),
        "logic_triggers": parse_logic_asc(run_dir),
    }
