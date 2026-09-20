#!/usr/bin/env python3
"""VFDDeviceModel — discrete Motor_Starter vs Ethernet VFD_UDT binding.

Gate F canonical drive model. Separates:
  - HardwareIOModel physical channels (word/bit → module data)
  - VFDDeviceModel drive identity + command/status roles + PLC tag binding

Does not invent Ethernet roles from names alone. SpdControl/Gpx INVALID
selections remain ABSENT_REFERENCE / NOT_CONFIGURED.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fortna_asc import read_asc

ABSENT = frozenset({"", "INVALID", "N/A", "NONE", "NA", "N", "~"})

# Discrete Conveyor suffix → semantic role (known-site proven set + safe aliases).
DISCRETE_ROLE_BY_SUFFIX = {
    "AUX": "RUNNING_FEEDBACK",
    "AUXILIARY": "RUNNING_FEEDBACK",
    "EN": "START_ENABLE_CMD",
    "ENABLE": "START_ENABLE_CMD",
    "RUN": "START_ENABLE_CMD",
    "CMD": "START_ENABLE_CMD",
    "START": "START_ENABLE_CMD",
    "FLT": "FAULT_STATUS",
    "FAULT": "FAULT_STATUS",
    "FAULTED": "FAULT_STATUS",
    "DRIVE_FLT": "FAULT_STATUS",
    "DRV_FLT": "FAULT_STATUS",
}

# Motor_Starter_UDT members used by fortna_autogen._vfd_ms_member (discrete path).
DISCRETE_MS_MEMBER = {
    "RUNNING_FEEDBACK": "I.Auxiliary_Forward",
    "START_ENABLE_CMD": "O.Run",
    "FAULT_STATUS": "Flt.PS_Flt",
}

BINDING_DISCRETE = "DISCRETE_MOTOR_STARTER"
BINDING_ETHERNET = "ETHERNET_VFD_UDT"
BINDING_UNKNOWN = "UNKNOWN"

# Ethernet-only optional command suffixes (PowerFlex LogicCommand / VFDOut bits).
# Known-site Conveyor rows never carry these — emit only when ETHERNET_VFD_UDT proven.
# Do NOT fabricate BOOL tags for these roles on discrete Motor_Starter sites.
ETHERNET_OPTIONAL_COMMAND_SUFFIXES = {
    "JOG": ("JOG_CMD", "VFDOut.Jog"),
    "CLR_FLT": ("CLEAR_FAULT_CMD", "VFDOut.ClearFaults"),
    "CLEAR_FLT": ("CLEAR_FAULT_CMD", "VFDOut.ClearFaults"),
    "CLEARFAULTS": ("CLEAR_FAULT_CMD", "VFDOut.ClearFaults"),
    "DIR_BIT0": ("DIR_FORWARD_CMD", "VFDOut.Forward"),
    "DIR_BIT1": ("DIR_REVERSE_CMD", "VFDOut.Reverse"),
    "LOC_CTRL": ("LOCAL_KEYPAD_CMD", "VFDOut.ForceKeypadCtrl"),
    "MOP_INC": ("MOP_INCREMENT_CMD", "VFDOut.MOPIncrement"),
    "MOP_DEC": ("MOP_DECREMENT_CMD", "VFDOut.MOPDecrement"),
    "ACC_BIT0": ("ACCEL_RATE1_CMD", "VFDOut.AccelRate1"),
    "ACC_BIT1": ("ACCEL_RATE2_CMD", "VFDOut.AccelRate2"),
    "DEC_BIT0": ("DECEL_RATE1_CMD", "VFDOut.DecelRate1"),
    "DEC_BIT1": ("DECEL_RATE2_CMD", "VFDOut.DecelRate2"),
}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(v: Any) -> str:
    return str(v or "").strip().strip('"')


def _absent(v: Any) -> bool:
    return _clean(v).upper() in ABSENT


def _vfd_base_and_suffix(io_name: str) -> tuple[str, str] | None:
    """Parse VFD<identity>[_SUFFIX]. Identity may be multi-letter (13RB)."""
    n = _clean(io_name)
    m = re.match(r"^(VFD\d+[A-Z]*)(?:_(.+))?$", n, re.I)
    if not m:
        return None
    base = m.group(1).upper()
    # Require at least one digit after VFD
    if not re.match(r"^VFD\d+[A-Z]*$", base, re.I):
        return None
    suf = (m.group(2) or "").upper()
    return base, suf


def is_ethernet_optional_command_suffix(suffix: str) -> bool:
    return (suffix or "").strip().upper() in ETHERNET_OPTIONAL_COMMAND_SUFFIXES


def ethernet_optional_command_member(suffix: str) -> str | None:
    """VFD_UDT member path fragment (VFDOut.*) for an optional ethernet command role."""
    hit = ETHERNET_OPTIONAL_COMMAND_SUFFIXES.get((suffix or "").strip().upper())
    return hit[1] if hit else None


def _role_for_point(io_name: str, desc: str, suffix: str) -> str:
    if suffix in DISCRETE_ROLE_BY_SUFFIX:
        return DISCRETE_ROLE_BY_SUFFIX[suffix]
    if suffix in ETHERNET_OPTIONAL_COMMAND_SUFFIXES:
        return ETHERNET_OPTIONAL_COMMAND_SUFFIXES[suffix][0]
    d = (desc or "").upper()
    if "HAS FAULTED" in d or "FAULT" in d:
        return "FAULT_STATUS"
    if "IS RUNNING" in d:
        return "RUNNING_FEEDBACK"
    if d.startswith("START ") or "START VFD" in d:
        return "START_ENABLE_CMD"
    if not suffix:
        return "START_ENABLE_CMD"
    return f"UNMAPPED_SUFFIX:{suffix}"


def _plc_num(vfd_base: str) -> str:
    m = re.match(r"^VFD(\d+[A-Z]*)$", vfd_base, re.I)
    return m.group(1) if m else vfd_base


def _load_spdcontrol_network_state(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "PROJECT" / "SpdControl.asc"
    fields = ["VFD_NetCTRL", "VFD_NetREF", "VFD_Reset", "VFD_Aux", "VFD_RstTimer"]
    out: dict[str, Any] = {
        "path": str(path) if path.is_file() else None,
        "configured_refs": [],
        "field_states": {},
        "ethernet_candidate": False,
    }
    if not path.is_file():
        out["field_states"] = {f: "ASC_MISSING" for f in fields}
        return out
    _hdr, rows = read_asc(path)
    for f in fields:
        vals = []
        for r in rows:
            v = _clean(r.get(f))
            if not _absent(v):
                vals.append(v)
        if vals:
            out["field_states"][f] = "CONFIGURED"
            out["configured_refs"].extend({"field": f, "value": v} for v in vals)
            out["ethernet_candidate"] = True
        else:
            out["field_states"][f] = "INVALID_OR_EMPTY"
    return out


def _load_gpx_vfd_state(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "FORTNA" / "GpxBelt.asc"
    fields = ["VFD_EN", "VFD_S1", "VFD_S2", "VFD_S3"]
    out: dict[str, Any] = {
        "path": str(path) if path.is_file() else None,
        "configured_refs": [],
        "field_states": {},
    }
    if not path.is_file():
        out["field_states"] = {f: "ASC_MISSING" for f in fields}
        return out
    _hdr, rows = read_asc(path)
    for f in fields:
        vals = [_clean(r.get(f)) for r in rows if not _absent(r.get(f))]
        out["field_states"][f] = "CONFIGURED" if vals else "INVALID_OR_EMPTY"
        out["configured_refs"].extend({"field": f, "value": v} for v in vals)
    return out


def build_vfd_device_model(
    run_dir: Path | str,
    machine: str = "",
) -> dict[str, Any]:
    """Build VFDDeviceModel list from RUN Conveyor + SpdControl/Gpx evidence."""
    run_dir = Path(run_dir)
    # Accept either .../RUN or .../RUN parent peek roots
    if (run_dir / "FORTNA" / "Conveyor.asc").is_file():
        root = run_dir
    elif (run_dir / "RUN" / "FORTNA" / "Conveyor.asc").is_file():
        root = run_dir / "RUN"
    else:
        raise FileNotFoundError(f"Conveyor.asc not found under {run_dir}")

    mach = _clean(machine).upper()
    conv_path = root / "FORTNA" / "Conveyor.asc"
    _hdr, rows = read_asc(conv_path)

    by_base: dict[str, dict[str, Any]] = {}
    for r in rows:
        name = _clean(r.get("IO_Name") or r.get("Name"))
        parsed = _vfd_base_and_suffix(name)
        if not parsed:
            continue
        base, suffix = parsed
        row_mach = _clean(r.get("Machine_Name"))
        if mach and (row_mach.upper() in ABSENT or row_mach.upper() != mach):
            continue

        desc = _clean(r.get("General_Description"))
        role = _role_for_point(name, desc, suffix)
        word = _clean(r.get("IO_Address_Word"))
        bit = _clean(r.get("IO_Address_Bit"))
        has_addr = bool(word) and word.upper() not in ABSENT

        rec = by_base.setdefault(
            base,
            {
                "device_id": base,
                "drive_identity": base,
                "machine_name": row_mach or None,
                "binding": BINDING_DISCRETE,
                "plc_tag": f"P{_plc_num(base)}_VFD",
                "plc_datatype": "Motor_Starter_UDT",
                "signals": [],
                "ownership": {
                    "source_table": "FORTNA/Conveyor.asc",
                    "owner_machine": row_mach or None,
                },
                "network": {
                    "spdcontrol_bound": False,
                    "module_bound": False,
                    "comm_state": "NOT_APPLICABLE_DISCRETE",
                },
                "provenance": "RUN_EXPLICIT",
            },
        )
        # Prefer non-empty machine if later rows fill it
        if row_mach and not rec.get("machine_name"):
            rec["machine_name"] = row_mach
            rec["ownership"]["owner_machine"] = row_mach

        signal = {
            "io_name": name,
            "suffix": suffix or "(bare)",
            "role": role,
            "description": desc,
            "type": _clean(r.get("Type")) or None,
            "word": word if has_addr else None,
            "bit": bit if has_addr and not _absent(bit) else None,
            "module_type_row": _clean(r.get("IO_Module_Type")) or None,
            "physical_endpoint": "CONFIGIO_CANDIDATE" if has_addr else None,
            "canonical_member": None,
            "reference_class": (
                "physical_discrete_io_candidate"
                if has_addr
                else "conveyor_catalog_named_object"
            ),
        }
        member = DISCRETE_MS_MEMBER.get(role)
        if member:
            signal["canonical_member"] = f"{rec['plc_tag']}.{member}"
        elif is_ethernet_optional_command_suffix(suffix):
            # Capability only — do not bind on DISCRETE_MOTOR_STARTER devices.
            eth_m = ethernet_optional_command_member(suffix)
            signal["reference_class"] = "ETHERNET_OPTIONAL_COMMAND"
            signal["activation"] = "REQUIRES_ETHERNET_VFD_UDT"
            signal["canonical_member_ethernet"] = (
                f"{rec['plc_tag']}.{eth_m}" if eth_m else None
            )
            signal["canonical_member"] = None
        rec["signals"].append(signal)

    spd = _load_spdcontrol_network_state(root)
    gpx = _load_gpx_vfd_state(root)

    devices = []
    for base in sorted(by_base.keys(), key=lambda s: (len(s), s)):
        rec = by_base[base]
        # Ethernet binding only when SpdControl has real (non-INVALID) refs.
        # Known sites: all INVALID → remain DISCRETE_MOTOR_STARTER.
        if spd.get("ethernet_candidate"):
            # Soft mark: still require engineer/module proof before generation flip
            rec["network"]["spdcontrol_bound"] = True
            rec["network"]["comm_state"] = "SPDCONTROL_CONFIGURED_REVIEW"
            rec["binding_review"] = BINDING_ETHERNET
        else:
            rec["binding_review"] = None
        # Sort signals for stability
        rec["signals"] = sorted(
            rec["signals"], key=lambda s: (s.get("role") or "", s.get("io_name") or "")
        )
        roles = sorted({s["role"] for s in rec["signals"]})
        rec["roles_present"] = roles
        devices.append(rec)

    return {
        "model": "VFDDeviceModel",
        "generated_at": _ts(),
        "run_dir": str(root),
        "machine_filter": mach or None,
        "binding_default": BINDING_DISCRETE,
        "hardware_io_rule": (
            "Physical channels belong in HardwareIOModel; VFDDeviceModel owns "
            "drive identity / roles / PLC UDT binding."
        ),
        "spdcontrol": spd,
        "gpxbelt": gpx,
        "device_count": len(devices),
        "devices": devices,
        "counts_by_binding": {
            BINDING_DISCRETE: sum(1 for d in devices if d["binding"] == BINDING_DISCRETE),
            BINDING_ETHERNET: sum(1 for d in devices if d["binding"] == BINDING_ETHERNET),
        },
        "notes": [
            "Known PLC2/4/5 sites use DISCRETE_MOTOR_STARTER (P###_VFD Motor_Starter_UDT).",
            "SpdControl VFD_Net* / VFD_Reset / VFD_Aux INVALID ⇒ NOT_CONFIGURED ethernet path.",
            "Do not emit VFD_UDT instances without configured network evidence.",
            "Optional JOG/CLR_FLT/DIR_BIT/LOC_CTRL/MOP_*/ACC_BIT roles are Ethernet "
            "VFDOut capability — gate by binding, never fabricate BOOL.",
        ],
        "ethernet_optional_command_suffixes": sorted(ETHERNET_OPTIONAL_COMMAND_SUFFIXES),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, help="Path to RUN or site peek root")
    ap.add_argument("--machine", default="", help="Machine_Name filter (e.g. ORNCCP5)")
    ap.add_argument("-o", "--out", default="", help="Write JSON to path")
    args = ap.parse_args()
    model = build_vfd_device_model(args.run, args.machine)
    text = json.dumps(model, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {out} ({model['device_count']} devices)")
    else:
        print(text)


if __name__ == "__main__":
    main()
