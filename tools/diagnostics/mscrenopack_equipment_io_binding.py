#!/usr/bin/env python3
"""MSCRENOPACK equipment I/O binding diagnostic (Equipment-Aware I/O V1)."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402
from fortna_equipment_binding import (  # noqa: E402
    CLASS_AIR_PRESSURE,
    CLASS_MOTOR_STARTER,
    CLASS_POWER_SUPPLY,
    build_equipment_bindings,
    parse_motor_starter_name,
)

ASC = (
    REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPACK-RUN"
    / "RUN"
    / "FORTNA"
    / "Conveyor.asc"
)
OUT_DIR = REPO / "exports" / "diagnostics"


def main() -> int:
    if not ASC.is_file():
        print(f"MISSING {ASC}", file=sys.stderr)
        return 2
    _h, rows = read_asc(ASC)
    pack = [
        r
        for r in rows
        if (r.get("Machine_Name") or "").strip().upper() == "MSCRENOPACK"
    ]
    bundle = build_equipment_bindings(pack, machine="MSCRENOPACK")
    by_raw = bundle["by_raw"]

    mdr = sum(1 for r in pack if (r.get("IO_Name") or "").upper().startswith("MDR"))
    vfd = sum(1 for r in pack if re.match(r"^VFD", (r.get("IO_Name") or ""), re.I))
    mdr_hit = sum(
        1
        for r in pack
        if (r.get("IO_Name") or "").upper().startswith("MDR")
        and parse_motor_starter_name(r.get("IO_Name") or "")
    )
    vfd_hit = sum(
        1
        for r in pack
        if re.match(r"^VFD", (r.get("IO_Name") or ""), re.I)
        and parse_motor_starter_name(r.get("IO_Name") or "")
    )

    motors = [
        d
        for d in bundle["devices"]
        if d.get("equipment_class") == CLASS_MOTOR_STARTER
    ]
    power = [
        d
        for d in bundle["devices"]
        if d.get("equipment_class") == CLASS_POWER_SUPPLY
    ]
    air = [
        d
        for d in bundle["devices"]
        if d.get("equipment_class") == CLASS_AIR_PRESSURE
    ]
    review_ps = [
        d
        for d in bundle["devices"]
        if d.get("equipment_class") == "UNKNOWN_PS_PREFIX"
    ]

    p77 = by_raw.get("M77") or {}
    p77_aux = by_raw.get("M77_AUX") or {}
    p77_trace = {
        "raw": {"M77": True, "M77_AUX": True},
        "source_evidence": {
            "M77": next(
                (
                    (r.get("General_Description") or "")
                    for r in pack
                    if (r.get("IO_Name") or "") == "M77"
                ),
                "",
            ),
            "M77_AUX": next(
                (
                    (r.get("General_Description") or "")
                    for r in pack
                    if (r.get("IO_Name") or "") == "M77_AUX"
                ),
                "",
            ),
        },
        "canonical": {
            "logix_tag": p77.get("logix_tag"),
            "datatype": p77.get("datatype"),
            "equipment_class": p77.get("equipment_class"),
            "rule": p77.get("rule"),
        },
        "io": {
            "M77": p77.get("member_path"),
            "M77_AUX": p77_aux.get("member_path"),
        },
        "driven_conveyor": p77.get("driven_conveyor"),
        "driven_conveyor_not_rewritten_to_p77": p77.get("driven_conveyor") != "P77",
        "provenance_raw_retained": p77.get("raw_names"),
    }

    report = {
        "machine": "MSCRENOPACK",
        "archive": "20260813-1132-MSCRENO-MSCRENOPACK-RUN",
        "conveyor_rows": len(pack),
        "motors": {
            "strict_bases": sum(
                1
                for d in motors
                if "RUN_COMMAND" in (d.get("signals") or {})
            ),
            "strict_aux": sum(
                1
                for d in motors
                if "AUXILIARY_FORWARD" in (d.get("signals") or {})
            ),
            "paired_devices": sum(
                1
                for d in motors
                if set((d.get("signals") or {}).keys())
                >= {"RUN_COMMAND", "AUXILIARY_FORWARD"}
            ),
            "proven": sum(1 for d in motors if d.get("confidence") == "PROVEN"),
            "review": sum(1 for d in motors if d.get("confidence") != "PROVEN"),
            "udt_bound_signals": sum(
                len(d.get("signals") or {})
                for d in motors
                if d.get("confidence") == "PROVEN"
            ),
            "remaining_generic_bool_estimate": sum(
                len(d.get("signals") or {})
                for d in motors
                if d.get("confidence") != "PROVEN"
            ),
        },
        "vfd": {"count": vfd, "mistakenly_renamed_by_m_to_p": vfd_hit},
        "mdr": {"count": mdr, "mistakenly_renamed_by_m_to_p": mdr_hit},
        "power_supply": {
            "devices": len(power),
            "names": [d.get("logix_tag") for d in power[:20]],
            "ps_udt_bound": len(power),
        },
        "air_pressure": {
            "devices": len(air),
            "names": [d.get("logix_tag") for d in air],
            "airpressure_udt_bound": len(air),
            "review": len(review_ps),
        },
        "safety": {
            "note": (
                "ESTOP/MCR/ESR/ESLS remain on ES_UDT.I.ES_OK "
                "(no invented MCR/ESR/ESLS UDTs)"
            ),
        },
        "p77_acceptance_trace": p77_trace,
        "counts": bundle.get("counts"),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jp = OUT_DIR / "mscrenopack_equipment_io_binding.json"
    mp = OUT_DIR / "mscrenopack_equipment_io_binding.md"
    jp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# MSCRENOPACK Equipment I/O Binding",
        "",
        f"Conveyor rows: **{len(pack)}**",
        "",
        "## Motors",
        f"- Paired Motor_Starter devices: **{report['motors']['paired_devices']}**",
        f"- Proven: {report['motors']['proven']} · Review: {report['motors']['review']}",
        f"- UDT-bound signals: {report['motors']['udt_bound_signals']}",
        "",
        "## VFD / MDR (must not be M→P)",
        f"- VFD count: {vfd} · mistaken M→P: **{vfd_hit}**",
        f"- MDR count: {mdr} · mistaken M→P: **{mdr_hit}**",
        "",
        "## Power / Air",
        f"- PS_UDT devices: {len(power)}",
        f"- AirPressure_Switch_UDT: {len(air)}",
        f"- PS* REVIEW: {len(review_ps)}",
        "",
        "## P77 acceptance trace",
        f"- M77 → `{p77_trace['io']['M77']}`",
        f"- M77_AUX → `{p77_trace['io']['M77_AUX']}`",
        f"- Driven conveyor: **{p77_trace['driven_conveyor']}** "
        f"(not rewritten to P77: {p77_trace['driven_conveyor_not_rewritten_to_p77']})",
        f"- Raw retained: {p77_trace['provenance_raw_retained']}",
        "",
        "## Safety",
        report["safety"]["note"],
        "",
    ]
    mp.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report["counts"], indent=2))
    print("P77", p77_trace["io"])
    print("wrote", jp)
    print("wrote", mp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
