"""
Equipment inventory + build plan from a Fortna RUN package.

Maps tar equipment → Site Forge generation features (AOIs, packs, routines).
Good-not-perfect: drives scaffold from what the tar proves exists.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


def _find_fortna_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    for c in (run_dir / "FORTNA", run_dir / "RUN" / "FORTNA", run_dir):
        if (c / "Conveyor.asc").is_file() or c.is_dir() and any(c.glob("Conveyor.asc*")):
            return c
    return run_dir / "FORTNA"


def _find_project_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    for c in (run_dir / "PROJECT", run_dir / "RUN" / "PROJECT"):
        if c.is_dir():
            return c
    return run_dir / "PROJECT"


def _asc_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        from fortna_asc import read_asc

        _headers, rows = read_asc(path)
        return list(rows or [])
    except Exception:
        return []


def _row_blob(row: dict) -> str:
    return " ".join(str(v) for v in row.values() if v is not None)


def _nonempty_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        blob = _row_blob(r).strip().upper()
        if not blob:
            continue
        if blob.replace("~", "").replace(" ", "") in ("", "N"):
            continue
        if "INVALID" in blob and blob.count("INVALID") > 3:
            continue
        out.append(r)
    return out


def _row_machine(row: dict) -> str:
    d = {str(k).strip().strip('"'): v for k, v in (row or {}).items()}
    dlow = {str(k).lower(): v for k, v in d.items()}
    return str(
        d.get("Machine_Name")
        or dlow.get("machine_name")
        or dlow.get("machine")
        or ""
    ).strip().strip('"')


def _machine_matches(row_mach: str, controller: str) -> bool:
    """True if ASC row belongs to controller (blank/N/A = unscoped)."""
    rm = (row_mach or "").strip().upper()
    ctl = (controller or "").strip().upper()
    if not ctl:
        return True
    if not rm or rm in ("N/A", "INVALID", "NONE", "ALL", ""):
        return False  # plant-wide / untagged — do not count for per-PLC plan
    if rm == ctl:
        return True
    # Soft match: MSCRENOPACK vs PACK, or contains
    if ctl in rm or rm in ctl:
        return True
    try:
        from fortna_io_extract import row_machine_matches

        return bool(row_machine_matches(rm, ctl))
    except Exception:
        return False


def inventory_run(run_dir: Path, *, machine_name: str | None = None) -> dict:
    """Return equipment counts and flags from RUN tar extract.

    When machine_name is set (multi-controller plant ASC), counts/flags are
    scoped to that MACHINENAME so PACK/PICK/SHIP plans stay independent.
    """
    run_dir = Path(run_dir)
    # Normalize to folder that contains FORTNA or is RUN
    if (run_dir / "RUN").is_dir() and not (run_dir / "FORTNA").is_dir():
        base = run_dir / "RUN"
    else:
        base = run_dir
    fortna = _find_fortna_dir(
        base if (base / "FORTNA").is_dir() or (base / "Conveyor.asc").is_file() else run_dir
    )
    if not fortna.is_dir():
        fortna = _find_fortna_dir(run_dir)
    project = _find_project_dir(base if (base / "PROJECT").is_dir() else run_dir)

    try:
        from fortna_io_extract import equipment_kind
    except Exception:
        equipment_kind = None  # type: ignore

    # Prefer project.cfg MACHINENAME when caller did not pass one
    mach = (machine_name or "").strip()
    if not mach:
        try:
            from fortna_io_extract import read_project_meta

            meta = read_project_meta(base if (base / "project.cfg").is_file() else run_dir)
            mach = str(meta.get("machine_name") or "").strip()
        except Exception:
            mach = ""

    conv_path = next(iter(sorted(fortna.glob("Conveyor.asc*"))), fortna / "Conveyor.asc")
    conv_rows_all = _asc_rows(conv_path)
    if mach:
        conv_rows = [r for r in conv_rows_all if _machine_matches(_row_machine(r), mach)]
    else:
        conv_rows = conv_rows_all

    conveyors: list[str] = []
    vfd_names: list[str] = []
    pe_names: list[str] = []
    motors: list[str] = []
    beacon_names: list[str] = []
    types: Counter = Counter()
    kind_counts: Counter = Counter()

    for r in conv_rows:
        d = {str(k).strip().strip('"'): v for k, v in r.items()}
        dlow = {str(k).lower(): v for k, v in d.items()}
        name = str(
            d.get("IO_Name")
            or dlow.get("io_name")
            or dlow.get("name")
            or dlow.get("conveyor")
            or ""
        ).strip().strip('"')
        if not name:
            continue
        ctype = str(
            d.get("Type") or dlow.get("type") or dlow.get("convtype") or ""
        ).strip().strip('"')
        desc = str(
            d.get("General_Description")
            or d.get("Device_Description")
            or dlow.get("general_description")
            or ""
        )
        drive = str(d.get("Motor") or dlow.get("motor") or dlow.get("drive") or "")
        kind = "other"
        if equipment_kind:
            try:
                kind = equipment_kind(name, ctype, desc, drive=drive) or "other"
            except Exception:
                kind = "other"
        else:
            if re.match(r"^P\d+", name, re.I):
                kind = "conveyor"
            elif re.match(r"^VFD\d+", name, re.I):
                kind = "vfd"
            elif re.match(r"^(EZ)?PE\d+", name, re.I):
                kind = "photoeye"
        kind_counts[kind] += 1
        if kind == "conveyor" or re.match(r"^P\d+", name, re.I):
            base_n = re.match(r"^(P\d+[A-Z]?)", name, re.I)
            conveyors.append(base_n.group(1) if base_n else name)
            types[ctype or "(blank)"] += 1
        if kind == "vfd" or re.match(r"^VFD\d+", name, re.I):
            vfd_names.append(re.sub(r"(_EN|_AUX|_FLT|_RUN).*$", "", name, flags=re.I).upper())
        if kind == "photoeye" or re.match(r"^(EZ)?PE\d+", name, re.I):
            pe_names.append(name)
        if kind == "motor" or re.match(r"^M\d+", name, re.I):
            motors.append(name)
        if kind == "beacon":
            beacon_names.append(name)

    def table_count(fname: str) -> dict:
        p = next(iter(sorted(fortna.glob(fname + "*"))), fortna / fname)
        rows = _asc_rows(p)
        if mach:
            rows = [r for r in rows if _machine_matches(_row_machine(r), mach)]
        good = _nonempty_rows(rows)
        return {
            "file": p.name if p.is_file() else fname,
            "rows": len(rows),
            "usable": len(good),
            "scoped_to": mach or None,
        }

    enc = table_count("Encoders.asc")
    estop = table_count("EStop.asc")
    merges = table_count("Merges.asc")
    sorters = table_count("Sorters.asc")
    beacons = table_count("BeaconInfo.asc")
    mtr = table_count("Mtrchain.asc")
    ps = table_count("PowerSupply.asc")

    eip_adapters = 0
    eip_modules = 0
    if project.is_dir():
        ad = next(iter(sorted(project.glob("EIPAdapters.asc*"))), None)
        md = next(iter(sorted(project.glob("EIPModules.asc*"))), None)
        if ad:
            eip_adapters = len(_nonempty_rows(_asc_rows(ad)))
        if md:
            eip_modules = len(_nonempty_rows(_asc_rows(md)))

    # Sorter track tables (file presence is plant-wide in multi-PLC tars —
    # only count as sorter evidence when this machine has sorter/encoder rows,
    # or when no machine scope was applied).
    srt_track = any(fortna.glob("SrtTrack*.asc*"))
    srt_device = any(fortna.glob("SrtDevice*.asc*"))
    sorter_evidence = (
        sorters["usable"] > 0
        or enc["usable"] > 0
        or ((not mach) and (srt_track or srt_device))
    )

    conveyors_u = sorted(set(conveyors), key=lambda s: (len(s), s))
    vfds_u = sorted(set(vfd_names))
    pes_u = sorted(set(pe_names))
    motors_u = sorted(set(motors))
    beacons_from_conv = sorted(set(beacon_names))

    return {
        "run_dir": str(run_dir),
        "fortna_dir": str(fortna),
        "machine_name": mach or None,
        "counts": {
            "conveyors": len(conveyors_u),
            "vfds": len(vfds_u),
            "photoeyes_named": len(pes_u),
            "motors_named": len(motors_u),
            "beacons_in_conveyor": len(beacons_from_conv),
            "encoders_table_usable": enc["usable"],
            "estop_table_usable": estop["usable"],
            "merges_table_usable": merges["usable"],
            "sorters_table_usable": sorters["usable"],
            "beacons_usable": beacons["usable"],
            "motor_chains_usable": mtr["usable"],
            "power_supplies_usable": ps["usable"],
            "eip_adapters": eip_adapters,
            "eip_modules": eip_modules,
            "conveyor_asc_rows": len(conv_rows),
            "conveyor_asc_rows_all": len(conv_rows_all),
        },
        "kind_counts": dict(kind_counts),
        "conveyors": conveyors_u[:200],
        "vfds": vfds_u[:100],
        "photoeyes": pes_u[:200],
        "conveyor_types": dict(types.most_common(20)),
        "tables": {
            "encoders": enc,
            "estop": estop,
            "merges": merges,
            "sorters": sorters,
            "beacons": beacons,
            "mtrchain": mtr,
            "power_supply": ps,
        },
        "flags": {
            "has_srt_track": srt_track,
            "has_srt_device": srt_device,
            "has_eipcfg": bool(
                list(fortna.glob("*eipcfg*.xml")) + list(fortna.glob("*EIP*.xml"))
            ),
            "transport_heavy": len(conveyors_u) >= 20,
            "merge_candidate": merges["usable"] > 0 or len(conveyors_u) >= 30,
            "sorter_candidate": sorter_evidence,
        },
    }


def plan_from_inventory(inv: dict, *, existing_merges: list | None = None) -> dict:
    """
    Map inventory → generation features / packs / AOIs.

    Correlates with gold Greensboro PLC2/4/5 usage:
      transport → Fast_Conv, Slow_Flt, Slow_Jam, PE_Logic, Full_PE
      2:1 merge → Merge_2to1 (+ Conv_Merge) when merges configured or table usable
      sorter → Sorter_Track pack when sorter/ENC evidence
      VFD discrete → P###_VFD Motor_Starter_UDT (handled in IO path)
    """
    c = inv.get("counts") or {}
    flags = inv.get("flags") or {}
    merges = list(existing_merges or [])

    features = {
        "transport_fast_slow": c.get("conveyors", 0) > 0,
        "io_map": True,
        "pe_logic": c.get("photoeyes_named", 0) > 0 or c.get("conveyors", 0) > 0,
        "full_pe": c.get("photoeyes_named", 0) > 0,
        "motor_starter_flt": c.get("conveyors", 0) > 0,
        "vfd_as_motor_starter_udt": c.get("vfds", 0) > 0,
        "es_udt": c.get("estop_table_usable", 0) > 0,
        "merge_2to1": bool(merges) or (flags.get("merge_candidate") and c.get("merges_table_usable", 0) > 0),
        "sorter_track_pack": bool(flags.get("sorter_candidate")),
        "enc_riocard": c.get("encoders_table_usable", 0) > 0,
        "sys_pack": True,
        "comm_diag": c.get("eip_adapters", 0) > 0,
    }

    # AOIs expected in library / L5X when features on
    aois = []
    if features["transport_fast_slow"]:
        aois += ["Fast_Conv", "Slow_Flt", "Slow_Jam"]
    if features["pe_logic"]:
        aois += ["PE_Logic"]
    if features["full_pe"]:
        aois += ["Full_PE"]
    if features["merge_2to1"]:
        aois += ["Merge_2to1"]
    if features["enc_riocard"]:
        aois += ["Enc_RIOCard", "Enc_CounterCard", "Enc_Virtual_DistBased"]
    if features["sorter_track_pack"]:
        aois += [
            "TRK_Divert_WaveFunction",
            "TRK_Divert",
            "TRK_Pointer",
            "TRK_Lost_Package",
            "TRK_Induct_TokenUpdate",
        ]
    if features["comm_diag"]:
        aois += ["AOI_CommDiag"]

    packs = []
    if features["sys_pack"]:
        packs.append("Sys")
    if features["sorter_track_pack"]:
        packs.append("Sorter_Track")

    profile = "transport"
    if features["sorter_track_pack"] and c.get("conveyors", 0) < 40:
        profile = "sorter"
    elif features["merge_2to1"]:
        profile = "transport_merge"
    elif flags.get("transport_heavy"):
        profile = "transport"

    notes = []
    if flags.get("merge_candidate") and not merges and c.get("merges_table_usable", 0) == 0:
        notes.append(
            "Transport-heavy site but Merges.asc empty — configure 2:1 Merges UI (PLC2 pattern)."
        )
    if features["sorter_track_pack"]:
        notes.append("Sorter/ENC evidence — enable Sorter Track pack (PLC5 pattern).")
    if c.get("vfds", 0):
        notes.append(f"{c.get('vfds')} VFD* names — map to P###_VFD Motor_Starter_UDT in IO_MAP.")
    notes.append(
        "Sawtooth: optional Sawtooth_Merge pack available (from PLC4S pattern) — "
        "enable manually; not auto-emitted from tar yet."
    )

    return {
        "profile": profile,
        "features": features,
        "aois": sorted(set(aois)),
        "packs": packs,
        "merge_rows_configured": len(merges),
        "notes": notes,
        "inventory_counts": c,
    }


def inventory_and_plan(
    run_dir: Path,
    *,
    merges_2to1: list | None = None,
    machine_name: str | None = None,
) -> dict:
    inv = inventory_run(run_dir, machine_name=machine_name)
    plan = plan_from_inventory(inv, existing_merges=merges_2to1)
    return {"inventory": inv, "plan": plan}
