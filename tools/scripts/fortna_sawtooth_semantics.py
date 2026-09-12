#!/usr/bin/env python3
"""CP4 Sawtooth semantic model — RUN + discovery + generic library evidence only.

Builds typed merge/lane/encoder/drive/reservation/sensor objects, provenance maps,
placeholder audits, and evidence-backed Conv_* real-logic fills.

Forbidden: finished PLC4, Greensboro hardcoding, guessing to inflate coverage.
Tracking/WCS remains GENERATION NOT YET SUPPORTED.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent

from fortna_sawtooth_param import (  # noqa: E402
    PROV_CFG,
    PROV_DERIVED,
    PROV_GENERIC,
    PROV_RUN,
    SawtoothParamMap,
    collector_id_from_motor_io,
    extract_ezpe_from_reserve_tm,
    load_lane_reserve_tm,
)

PROV_NOT_SUPPORTED = "GENERATION NOT YET SUPPORTED"
PROV_UNKNOWN = "UNKNOWN"
PROV_LIBRARY = "GENERIC_LIBRARY"

CLS_CAN = "CAN_GENERATE_REAL_LOGIC"
CLS_CFG = "CONFIGURATION_REQUIRED"
CLS_UNSUPPORTED = "UNSUPPORTED"
CLS_DOC = "DOCUMENTATION_ONLY"

# Semantic lane states for scenario tests (not full Logix emulation).
STATE_CLEAR = "CLEAR"
STATE_OCCUPIED = "OCCUPIED"
STATE_REQUEST = "REQUEST"
STATE_RESERVED = "RESERVED"
STATE_SLICING = "SLICING"
STATE_RELEASING = "RELEASING"
STATE_DISABLED = "DISABLED"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _clean(val: Any) -> str:
    return str(val or "").strip().strip('"')


def _vfd_base(symbol: str) -> str:
    m = re.match(r"(VFD\d+[A-Z]?)", (symbol or "").upper())
    return m.group(1) if m else (symbol or "").upper()


def _vfd_role(symbol: str, description: str = "") -> str:
    su = (symbol or "").upper()
    desc = (description or "").upper()
    if su.endswith("_EN") or "START VFD" in desc:
        return "EN"
    if su.endswith("_AUX") or "IS RUNNING" in desc:
        return "AUX"
    if su.endswith("_FLT") or "FAULTED" in desc:
        return "FLT"
    if su.startswith("VFD") and "_" not in su[3:]:
        # Bare VFD219 — RUN description often "START VFD…"
        if "START" in desc:
            return "EN"
        return "BASE"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SensorBinding:
    symbol: str
    role: str
    provenance: str
    lane_name: str | None = None
    detail: str = ""
    source: str = ""


@dataclass
class DriveBinding:
    symbol: str
    vfd_base: str
    role: str
    provenance: str
    lane_name: str | None = None
    conveyors: list[str] = field(default_factory=list)
    detail: str = ""
    source: str = ""


@dataclass
class ReservationBinding:
    symbol: str
    merge_name: str
    provenance: str
    detail: str = ""
    source: str = ""


@dataclass
class SawtoothEncoderModel:
    encoder: str
    io: str
    ticks_per_foot: float | None
    target_fpm: float | None
    enable: str | None
    jamzone: str | None
    sawtooth_associated: bool
    role: str
    provenance: str
    associations: list[dict[str, Any]] = field(default_factory=list)
    detail: str = ""
    pulses: int = 0  # scenario counter


@dataclass
class SawtoothLaneModel:
    name: str
    lane_index: int
    conveyor: str
    photoeye: SensorBinding | None
    drive: DriveBinding | None
    approach: str | None
    collision: str | None
    lane_input: str | None
    slice_seconds: float | None
    reserve_seconds: float | None
    reserve_tm: str | None
    full_eye: SensorBinding | None
    pack_full_eye_rename: dict[str, str] | None
    allowed_to_run: bool
    provenance: str
    state: str = STATE_CLEAR
    detail: str = ""


@dataclass
class SawtoothMergeModel:
    name: str
    motor_io: DriveBinding | None
    reservation: ReservationBinding | None
    lane_enable_delay_tm: str | None
    slice_seconds: float | None
    collector_digits: str
    lanes: list[SawtoothLaneModel] = field(default_factory=list)
    encoders: list[SawtoothEncoderModel] = field(default_factory=list)
    merge_available: bool = True
    provenance: str = PROV_RUN
    source_file: str = ""
    notes: list[str] = field(default_factory=list)

    def lane_by_name(self, name: str) -> SawtoothLaneModel | None:
        for lane in self.lanes:
            if lane.name == name:
                return lane
        return None

    def encoder_by_name(self, name: str) -> SawtoothEncoderModel | None:
        for enc in self.encoders:
            if enc.encoder == name:
                return enc
        return None


# ---------------------------------------------------------------------------
# RUN helpers (Fullline)
# ---------------------------------------------------------------------------


def load_fullline_map(run_dir: Path) -> dict[str, dict[str, str]]:
    """Sensor_Name → Fullline row fields. Allowed RUN input."""
    fortna = Path(run_dir) / "FORTNA"
    candidates = [fortna / "Fullline.asc.ORNCCP4", fortna / "Fullline.asc"]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return {}
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    if not lines:
        return {}
    headers = [_clean(h) for h in lines[0].split("~")]
    out: dict[str, dict[str, str]] = {}
    for ln in lines[1:]:
        cols = [_clean(c) for c in ln.split("~")]
        if len(cols) < len(headers):
            cols.extend([""] * (len(headers) - len(cols)))
        row = {headers[i]: cols[i] for i in range(len(headers))}
        sensor = (row.get("Sensor_Name") or "").upper()
        if not sensor or sensor in {"N/A", "INVALID", ""}:
            continue
        out[sensor] = row
    return out


def resolve_full_eye(
    *,
    lane_name: str,
    conveyor: str,
    reserve_tm: str,
    pack_symbols: set[str],
    fullline: dict[str, dict[str, str]],
) -> tuple[SensorBinding | None, dict[str, str] | None, str]:
    """Resolve reserve/full-eye using SawLane.ReserveTM + Fullline.asc.

    Never renames RUN F1↔F2. May map gold pack leftover EZPE127_F → EZPE217_F
    when Fullline + ReserveTM agree (RUN_DERIVED).
    """
    ezpe = extract_ezpe_from_reserve_tm(reserve_tm)
    if not ezpe:
        return None, None, "ReserveTM missing"

    fl = fullline.get(ezpe.upper())
    pack_upper = {s.upper() for s in pack_symbols}

    if ezpe.upper() in pack_upper:
        binding = SensorBinding(
            symbol=ezpe,
            role="full_eye",
            provenance=PROV_RUN,
            lane_name=lane_name,
            detail=f"ReserveTM={reserve_tm} exact pack symbol",
            source="SawLane.ReserveTM",
        )
        return binding, None, binding.detail

    # Paired F1/F2: ReserveTM may name F1 while pack holds F2 on lane conveyor.
    base = re.match(r"(EZPE\d+)", ezpe.upper())
    base_s = base.group(1) if base else ""
    if base_s and fl:
        fl_conv = (fl.get("Conveyor_Name") or "").upper()
        # Prefer pack symbol whose Fullline conveyor equals lane conveyor
        lane_pack = None
        for sym in sorted(pack_upper):
            if not sym.startswith(base_s):
                continue
            fl_sym = fullline.get(sym)
            if fl_sym and (fl_sym.get("Conveyor_Name") or "").upper() == (conveyor or "").upper():
                lane_pack = sym
                break
        if lane_pack and lane_pack != ezpe.upper():
            # Keep ReserveTM sensor as reserve_clear; pack eye is separate lane full eye
            binding = SensorBinding(
                symbol=lane_pack,
                role="full_eye_lane_conveyor",
                provenance=PROV_RUN,
                lane_name=lane_name,
                detail=(
                    f"ReserveTM={reserve_tm}→{ezpe} on {fl_conv}; "
                    f"pack/lane full eye {lane_pack} on {conveyor} (paired; do not rename F1↔F2)"
                ),
                source="SawLane.ReserveTM+Fullline.asc",
            )
            return binding, None, binding.detail

    # Gold leftover EZPE127_F with RUN EZPE217_F (no pack 217)
    if ezpe.upper() not in pack_upper and "EZPE127_F" in pack_upper and fl:
        rename = {"EZPE127_F": ezpe.upper()}
        binding = SensorBinding(
            symbol=ezpe.upper(),
            role="full_eye",
            provenance=PROV_DERIVED,
            lane_name=lane_name,
            detail=(
                f"ReserveTM={reserve_tm} / Fullline {ezpe} on "
                f"{fl.get('Conveyor_Name')}; map gold EZPE127_F→{ezpe}"
            ),
            source="SawLane.ReserveTM+Fullline.asc+pack",
        )
        return binding, rename, binding.detail

    if fl:
        binding = SensorBinding(
            symbol=ezpe,
            role="full_eye",
            provenance=PROV_RUN if ezpe.upper() in pack_upper else PROV_CFG,
            lane_name=lane_name,
            detail=(
                f"ReserveTM={reserve_tm}; Fullline conveyor={fl.get('Conveyor_Name')}; "
                f"pack_match={ezpe.upper() in pack_upper}"
            ),
            source="SawLane.ReserveTM+Fullline.asc",
        )
        return binding, None, binding.detail

    binding = SensorBinding(
        symbol=ezpe,
        role="full_eye",
        provenance=PROV_CFG,
        lane_name=lane_name,
        detail=f"ReserveTM={reserve_tm} has no Fullline/pack counterpart",
        source="SawLane.ReserveTM",
    )
    return binding, None, binding.detail


# ---------------------------------------------------------------------------
# Build semantic model
# ---------------------------------------------------------------------------


def build_semantic_model(
    discovery: dict[str, Any],
    *,
    run_dir: Path,
    pack_symbols: set[str] | None = None,
) -> SawtoothMergeModel:
    saw = discovery.get("sawtooth") or {}
    merges = saw.get("merges") or []
    merge = merges[0] if merges else {}
    motor_io = str(merge.get("motor_io") or "")
    collector = collector_id_from_motor_io(motor_io) or ""
    reserve_tm_by_lane = load_lane_reserve_tm(run_dir, machine="ORNCCP4")
    fullline = load_fullline_map(run_dir)
    pack_symbols = pack_symbols or set()

    motor_binding = None
    if motor_io:
        motor_binding = DriveBinding(
            symbol=motor_io,
            vfd_base=_vfd_base(motor_io),
            role=_vfd_role(motor_io, "IS RUNNING"),
            provenance=PROV_RUN,
            conveyors=[],
            detail="SawMerge.MotorIO",
            source="SawMerge.asc",
        )

    reservation = None
    if merge.get("reservation"):
        reservation = ReservationBinding(
            symbol=str(merge["reservation"]),
            merge_name=str(merge.get("name") or ""),
            provenance=PROV_RUN,
            detail="SawMerge.ReserveIN",
            source="SawMerge.asc",
        )

    model = SawtoothMergeModel(
        name=str(merge.get("name") or "SAWTOOTH_MERGE"),
        motor_io=motor_binding,
        reservation=reservation,
        lane_enable_delay_tm=str(merge.get("lane_enable_delay_tm") or "") or None,
        slice_seconds=merge.get("slice_seconds"),
        collector_digits=collector,
        provenance=str(merge.get("provenance") or PROV_RUN),
        source_file=str(merge.get("source_file") or ""),
        notes=[
            "Explicit RUN relationships beat numbering heuristics",
            "Encoder jamzone CITY COUNTER is not forced into Sawtooth without evidence",
            "Finished PLC4 not consulted",
        ],
    )

    for lane in saw.get("lanes") or []:
        lane_name = str(lane.get("name") or "")
        conv = str(lane.get("conveyor") or "").upper()
        pe = str(lane.get("photoeye") or "").upper()
        drive = str(lane.get("drive") or lane.get("vfd") or "").upper()
        idx = int(lane.get("lane_index") or 0)
        reserve_tm = (
            reserve_tm_by_lane.get(lane_name)
            or reserve_tm_by_lane.get(lane_name.upper())
            or ""
        )
        pe_bind = None
        if pe:
            pe_bind = SensorBinding(
                symbol=pe,
                role="photoeye",
                provenance=PROV_RUN,
                lane_name=lane_name,
                detail="SawLane.PhotoEyeIO",
                source="SawLane.asc",
            )
        drive_bind = None
        if drive:
            drive_bind = DriveBinding(
                symbol=drive,
                vfd_base=_vfd_base(drive),
                role=_vfd_role(drive, "START VFD" if drive.endswith("_EN") or drive == _vfd_base(drive) else ""),
                provenance=PROV_RUN,
                lane_name=lane_name,
                conveyors=[conv] if conv else [],
                detail="SawLane.DisableIO",
                source="SawLane.asc",
            )
        full_eye, rename, fe_detail = resolve_full_eye(
            lane_name=lane_name,
            conveyor=conv,
            reserve_tm=reserve_tm,
            pack_symbols=pack_symbols,
            fullline=fullline,
        )
        allowed = str(lane.get("allowed_to_run") or "Y").upper() in {"Y", "YES", "1", "TRUE"}
        model.lanes.append(
            SawtoothLaneModel(
                name=lane_name,
                lane_index=idx,
                conveyor=conv,
                photoeye=pe_bind,
                drive=drive_bind,
                approach=str(lane.get("approach") or "") or None,
                collision=str(lane.get("collision") or "") or None,
                lane_input=str(lane.get("lane_input") or "") or None,
                slice_seconds=lane.get("slice_seconds"),
                reserve_seconds=lane.get("reserve_seconds"),
                reserve_tm=reserve_tm or None,
                full_eye=full_eye,
                pack_full_eye_rename=rename,
                allowed_to_run=allowed,
                provenance=str(lane.get("provenance") or PROV_RUN),
                detail=fe_detail,
            )
        )

    for enc in (discovery.get("encoders") or {}).get("encoders") or []:
        jam = str(enc.get("jamzone") or "")
        assocs = list(enc.get("associations") or [])
        saw_assoc = any(
            a.get("type") in {"encoder_to_saw_merge_via_motor_io", "encoder_jamzone_sawtooth"}
            for a in assocs
        )
        jam_u = jam.upper()
        if saw_assoc or "SAWTOOTH" in jam_u:
            role = "SAWTOOTH_COLLECTOR"
            saw_assoc = True
        elif "CITY" in jam_u and "COUNTER" in jam_u:
            role = "CITY_COUNTER"
            saw_assoc = False
        else:
            role = "UNKNOWN"
        model.encoders.append(
            SawtoothEncoderModel(
                encoder=str(enc.get("encoder") or ""),
                io=str(enc.get("io") or ""),
                ticks_per_foot=enc.get("ticks_per_foot"),
                target_fpm=enc.get("target_fpm"),
                enable=str(enc.get("enable") or "") or None,
                jamzone=jam or None,
                sawtooth_associated=saw_assoc,
                role=role,
                provenance=str(enc.get("provenance") or PROV_RUN),
                associations=assocs,
                detail=f"jamzone={jam}; role={role}",
            )
        )

    # Attach shared VFD conveyors from discovery onto motor binding when present
    if model.motor_io:
        for vrow in (discovery.get("vfd") or {}).get("vfds") or []:
            if vrow.get("vfd") == model.motor_io.vfd_base:
                model.motor_io.conveyors = list(vrow.get("conveyors") or [])
                break

    for lane in model.lanes:
        pe = lane.photoeye.symbol if lane.photoeye else ""
        drv = lane.drive.symbol if lane.drive else ""
        pe_digits = re.search(r"(\d+)", pe)
        conv_digits = re.search(r"(\d+)", lane.conveyor or "")
        if pe_digits and conv_digits and pe_digits.group(1) != conv_digits.group(1):
            model.notes.append(
                f"Explicit cross-number bind kept: {lane.name} conveyor={lane.conveyor} "
                f"PE={pe} drive={drv}"
            )

    return model


def model_to_json(model: SawtoothMergeModel) -> dict[str, Any]:
    def _ser(obj: Any) -> Any:
        if hasattr(obj, "__dataclass_fields__"):
            return {k: _ser(v) for k, v in asdict(obj).items()}
        if isinstance(obj, list):
            return [_ser(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _ser(v) for k, v in obj.items()}
        return obj

    payload = _ser(model)
    payload["generated_at"] = _ts()
    payload["finished_plc4_used"] = False
    payload["lane_count"] = len(model.lanes)
    payload["method"] = "semantic_model_from_discovery_and_run"
    return payload


# ---------------------------------------------------------------------------
# Provenance maps
# ---------------------------------------------------------------------------


def build_merge_signal_map(model: SawtoothMergeModel) -> dict[str, Any]:
    mappings: list[dict[str, Any]] = []

    def add(signal: str, value: Any, *, role: str, provenance: str, source: str, detail: str = "") -> None:
        mappings.append(
            {
                "signal": signal,
                "value": value,
                "role": role,
                "provenance": provenance,
                "source": source,
                "detail": detail,
            }
        )

    add("merge_name", model.name, role="merge_identity", provenance=model.provenance, source=model.source_file)
    add(
        "collector_digits",
        model.collector_digits,
        role="collector",
        provenance=PROV_RUN if model.collector_digits else PROV_CFG,
        source="SawMerge.MotorIO",
    )
    if model.motor_io:
        add(
            "motor_io",
            model.motor_io.symbol,
            role="merge_motor",
            provenance=model.motor_io.provenance,
            source=model.motor_io.source,
            detail=f"vfd_base={model.motor_io.vfd_base} role={model.motor_io.role}",
        )
    if model.reservation:
        add(
            "reservation",
            model.reservation.symbol,
            role="reservation",
            provenance=model.reservation.provenance,
            source=model.reservation.source,
        )
    add(
        "lane_enable_delay_tm",
        model.lane_enable_delay_tm,
        role="lane_enable_delay",
        provenance=PROV_RUN if model.lane_enable_delay_tm else PROV_CFG,
        source="SawMerge.LaneEnableDelayTM",
    )
    add(
        "slice_seconds_merge",
        model.slice_seconds,
        role="merge_slice_time",
        provenance=PROV_RUN if model.slice_seconds is not None else PROV_CFG,
        source="SawMerge.pSliceSeconds",
    )
    add("lane_count", len(model.lanes), role="lane_count", provenance=PROV_RUN, source="SawLane")

    for lane in model.lanes:
        prefix = lane.name
        add(f"{prefix}.lane_index", lane.lane_index, role="lane_index", provenance=lane.provenance, source="SawLane.LaneNdx")
        add(f"{prefix}.conveyor", lane.conveyor, role="lane_conveyor", provenance=lane.provenance, source="SawLane.Name")
        if lane.photoeye:
            add(
                f"{prefix}.photoeye",
                lane.photoeye.symbol,
                role="lane_pe",
                provenance=lane.photoeye.provenance,
                source=lane.photoeye.source,
            )
        if lane.drive:
            add(
                f"{prefix}.drive",
                lane.drive.symbol,
                role="lane_drive",
                provenance=lane.drive.provenance,
                source=lane.drive.source,
                detail=f"vfd_base={lane.drive.vfd_base} role={lane.drive.role}",
            )
        add(
            f"{prefix}.approach",
            lane.approach,
            role="approach",
            provenance=PROV_RUN if lane.approach else PROV_CFG,
            source="SawLane.ApproachUP",
        )
        add(
            f"{prefix}.collision",
            lane.collision,
            role="collision",
            provenance=PROV_RUN if lane.collision else PROV_CFG,
            source="SawLane.CollisionUP",
        )
        add(
            f"{prefix}.lane_input",
            lane.lane_input,
            role="merge_input",
            provenance=PROV_RUN if lane.lane_input else PROV_CFG,
            source="SawLane.LaneIN",
        )
        add(
            f"{prefix}.slice_seconds",
            lane.slice_seconds,
            role="slice_seconds",
            provenance=PROV_RUN if lane.slice_seconds is not None else PROV_CFG,
            source="SawLane.SliceSeconds",
        )
        add(
            f"{prefix}.reserve_seconds",
            lane.reserve_seconds,
            role="reserve_seconds",
            provenance=PROV_RUN if lane.reserve_seconds is not None else PROV_CFG,
            source="SawLane.ReserveSeconds",
        )
        if lane.reserve_tm:
            add(
                f"{prefix}.reserve_tm",
                lane.reserve_tm,
                role="reserve_tm",
                provenance=PROV_RUN,
                source="SawLane.ReserveTM",
            )
        if lane.full_eye:
            add(
                f"{prefix}.full_eye",
                lane.full_eye.symbol,
                role=lane.full_eye.role,
                provenance=lane.full_eye.provenance,
                source=lane.full_eye.source,
                detail=lane.full_eye.detail,
            )
        if lane.pack_full_eye_rename:
            for old, new in lane.pack_full_eye_rename.items():
                add(
                    f"{prefix}.pack_rename",
                    f"{old}->{new}",
                    role="full_eye_pack_rename",
                    provenance=PROV_DERIVED,
                    source="Fullline+pack",
                    detail=lane.detail,
                )

    by_prov: dict[str, int] = {}
    for m in mappings:
        by_prov[m["provenance"]] = by_prov.get(m["provenance"], 0) + 1

    return {
        "generated_at": _ts(),
        "finished_plc4_used": False,
        "merge": model.name,
        "counts_by_provenance": by_prov,
        "mappings": mappings,
    }


def build_encoder_semantics(model: SawtoothMergeModel) -> dict[str, Any]:
    rows = []
    for enc in model.encoders:
        rows.append(
            {
                "encoder": enc.encoder,
                "io": enc.io,
                "ticks_per_foot": enc.ticks_per_foot,
                "target_fpm": enc.target_fpm,
                "enable": enc.enable,
                "jamzone": enc.jamzone,
                "role": enc.role,
                "sawtooth_associated": enc.sawtooth_associated,
                "provenance": enc.provenance,
                "associations": enc.associations,
                "detail": enc.detail,
                "generation_policy": (
                    CLS_CAN
                    if enc.sawtooth_associated
                    else CLS_DOC
                    if enc.role == "CITY_COUNTER"
                    else CLS_CFG
                ),
            }
        )
    return {
        "generated_at": _ts(),
        "finished_plc4_used": False,
        "policy": "ENC424 CITY COUNTER must not be forced into Sawtooth without evidence",
        "encoders": rows,
        "counts": {
            "total": len(rows),
            "sawtooth_associated": sum(1 for r in rows if r["sawtooth_associated"]),
            "city_counter": sum(1 for r in rows if r["role"] == "CITY_COUNTER"),
        },
    }


def build_vfd_semantics(discovery: dict[str, Any], model: SawtoothMergeModel) -> dict[str, Any]:
    devices = []
    for d in (discovery.get("vfd") or {}).get("devices") or []:
        io = str(d.get("io_name") or "")
        devices.append(
            {
                "io_name": io,
                "vfd_base": d.get("vfd_base") or _vfd_base(io),
                "role": _vfd_role(io, str(d.get("description") or "")),
                "description": d.get("description"),
                "provenance": d.get("provenance") or PROV_RUN,
                "source": d.get("source_file") or "Conveyor.asc",
            }
        )

    lane_drives = []
    for lane in model.lanes:
        if not lane.drive:
            continue
        lane_drives.append(
            {
                "lane": lane.name,
                "symbol": lane.drive.symbol,
                "vfd_base": lane.drive.vfd_base,
                "role": lane.drive.role,
                "conveyor": lane.conveyor,
                "provenance": lane.drive.provenance,
                "source": lane.drive.source,
            }
        )

    shared = []
    for vrow in (discovery.get("vfd") or {}).get("vfds") or []:
        convs = list(vrow.get("conveyors") or [])
        if len(convs) >= 2:
            shared.append(
                {
                    "vfd": vrow.get("vfd"),
                    "conveyors": convs,
                    "provenance": vrow.get("conveyor_mapping_provenance") or PROV_RUN,
                    "evidence": vrow.get("conveyor_mapping_evidence") or [],
                }
            )

    if model.motor_io:
        merge_motor = {
            "symbol": model.motor_io.symbol,
            "vfd_base": model.motor_io.vfd_base,
            "role": model.motor_io.role,
            "conveyors": model.motor_io.conveyors,
            "provenance": model.motor_io.provenance,
            "source": model.motor_io.source,
        }
    else:
        merge_motor = None

    return {
        "generated_at": _ts(),
        "finished_plc4_used": False,
        "rule": "VFD xxx / _EN / _AUX roles from RUN evidence; explicit RUN beats digit heuristic",
        "merge_motor": merge_motor,
        "lane_drives": lane_drives,
        "shared_relationships": shared,
        "devices": devices,
        "counts": {
            "devices": len(devices),
            "lane_drives": len(lane_drives),
            "shared": len(shared),
            "by_role": {
                role: sum(1 for d in devices if d["role"] == role)
                for role in sorted({d["role"] for d in devices})
            },
        },
    }


# ---------------------------------------------------------------------------
# Placeholder audit + real logic
# ---------------------------------------------------------------------------


def _extract_program_xml(text: str, program_name: str = "Sawtooth_Merge") -> str | None:
    m = re.search(
        rf'<Program Name="{re.escape(program_name)}"[^>]*>(.*?)</Program>',
        text,
        flags=re.S | re.I,
    )
    return m.group(0) if m else None


def _rung_entries_from_routine(text: str, routine: str) -> list[dict[str, str]]:
    m = re.search(
        rf'<Routine Name="{re.escape(routine)}" Type="RLL"[^>]*>(.*?)</Routine>',
        text,
        flags=re.S | re.I,
    )
    if not m:
        if re.search(rf'<Routine Name="{re.escape(routine)}" Type="RLL"\s*/>', text, flags=re.I):
            return [{"number": "empty", "comment": "", "text": "", "form": "self_closing"}]
        return []
    body = m.group(1)
    out = []
    for rm in re.finditer(
        r'<Rung Number="(\d+)"[^>]*>\s*(?:<Comment><!\[CDATA\[(.*?)\]\]></Comment>)?\s*'
        r"<Text><!\[CDATA\[(.*?)\]\]></Text>",
        body,
        flags=re.S,
    ):
        out.append(
            {
                "number": rm.group(1),
                "comment": (rm.group(2) or "").strip(),
                "text": (rm.group(3) or "").strip(),
                "form": "rung",
            }
        )
    return out


def audit_placeholders(
    l5x_path: Path,
    model: SawtoothMergeModel,
    *,
    program_name: str = "Sawtooth_Merge",
) -> dict[str, Any]:
    full = l5x_path.read_text(encoding="utf-8", errors="replace") if l5x_path.is_file() else ""
    scoped = _extract_program_xml(full, program_name) if full else None
    # Standalone parameterized program exports may lack <Program> wrapper
    text = scoped if scoped else full
    items: list[dict[str, Any]] = []

    pe_by_idx = {lane.lane_index: lane for lane in model.lanes}

    for routine in ("Conv_PE", "Conv_Enc", "Conv_Fast"):
        rungs = _rung_entries_from_routine(text, routine)
        if not rungs:
            items.append(
                {
                    "routine": routine,
                    "rung": None,
                    "classification": CLS_UNSUPPORTED,
                    "reason": "Routine missing from L5X",
                    "prior_text": None,
                }
            )
            continue
        for i, rung in enumerate(rungs):
            comment = rung.get("comment") or ""
            prior = rung.get("text") or ""
            is_nop = prior.strip() in {"", "NOP();"}
            classification = CLS_CFG
            reason = "Insufficient evidence for real logic"
            proposed = None
            lane = None
            enc = None
            label = None

            if routine == "Conv_PE":
                for ln in model.lanes:
                    if ln.name in comment or (ln.photoeye and ln.photoeye.symbol in comment):
                        lane = ln
                        break
                if lane is None and (i + 1) in pe_by_idx:
                    lane = pe_by_idx[i + 1]
                if lane is None and i < len(model.lanes):
                    lane = model.lanes[i]
                label = lane.name if lane else None
                if lane and lane.photoeye and lane.photoeye.provenance == PROV_RUN:
                    classification = CLS_CAN
                    reason = (
                        f"RUN PE {lane.photoeye.symbol} + library PE_UDT.I.PE_Clear pattern"
                    )
                    pe = lane.photoeye.symbol
                    idx = lane.lane_index
                    proposed = (
                        f"XIO({pe}.I.PE_Clear)OTE(SawSem_L{idx}_Occupied);"
                        f"XIC({pe}.I.PE_Clear)OTE(SawSem_L{idx}_Clear);"
                    )
                elif lane and not lane.photoeye:
                    classification = CLS_CFG
                    reason = f"{lane.name} missing PhotoEyeIO"
                else:
                    classification = CLS_CFG if is_nop else CLS_DOC
                    reason = "No RUN PE binding for rung"

            elif routine == "Conv_Enc":
                for e in model.encoders:
                    if e.encoder and e.encoder in comment:
                        enc = e
                        break
                if enc is None and i < len(model.encoders):
                    enc = model.encoders[i]
                label = enc.encoder if enc else None
                if enc and enc.sawtooth_associated and enc.enable:
                    classification = CLS_CAN
                    reason = (
                        f"{enc.encoder} sawtooth-associated via {enc.jamzone}; "
                        f"enable={enc.enable} (library P414_Enc.FPM pattern)"
                    )
                    proposed = (
                        f"XIC({enc.enable})OTE(SawSem_{enc.encoder}_Enable);"
                        f"XIO({enc.enable})OTE(SawSem_{enc.encoder}_Reset);"
                    )
                elif enc and enc.role == "CITY_COUNTER":
                    classification = CLS_DOC
                    reason = (
                        f"{enc.encoder} jamzone={enc.jamzone} — CITY COUNTER; "
                        "not forced into Sawtooth"
                    )
                    proposed = "NOP();"
                elif enc:
                    classification = CLS_CFG
                    reason = f"{enc.encoder} lacks sawtooth association evidence"
                else:
                    classification = CLS_CFG
                    reason = "No encoder binding"

            elif routine == "Conv_Fast":
                if i < len(model.lanes):
                    lane = model.lanes[i]
                label = lane.name if lane else None
                if lane and lane.photoeye and lane.conveyor:
                    classification = CLS_CAN
                    reason = (
                        f"RUN lane {lane.name} PE={lane.photoeye.symbol} conveyor={lane.conveyor}; "
                        "emit semantic exit-blocked (full Fast_Conv AOI rewrite unsupported)"
                    )
                    pe = lane.photoeye.symbol
                    idx = lane.lane_index
                    proposed = f"XIO({pe}.I.PE_Clear)OTE(SawSem_L{idx}_ExitBlocked);"
                else:
                    classification = CLS_CFG
                    reason = "Missing PE/conveyor for fast binding"

            items.append(
                {
                    "routine": routine,
                    "rung": rung.get("number"),
                    "lane_or_encoder": label,
                    "classification": classification,
                    "reason": reason,
                    "prior_text": prior,
                    "was_nop": is_nop,
                    "proposed_text": proposed,
                    "provenance": PROV_RUN
                    if classification == CLS_CAN
                    else (PROV_LIBRARY if classification == CLS_DOC else PROV_CFG),
                }
            )

    counts = {
        "total": len(items),
        "was_nop": sum(1 for i in items if i.get("was_nop")),
        CLS_CAN: sum(1 for i in items if i["classification"] == CLS_CAN),
        CLS_CFG: sum(1 for i in items if i["classification"] == CLS_CFG),
        CLS_UNSUPPORTED: sum(1 for i in items if i["classification"] == CLS_UNSUPPORTED),
        CLS_DOC: sum(1 for i in items if i["classification"] == CLS_DOC),
    }
    return {
        "generated_at": _ts(),
        "source_l5x": str(l5x_path),
        "program_scope": program_name if scoped else "whole_file",
        "finished_plc4_used": False,
        "counts": counts,
        "items": items,
    }


def build_semantic_tags_xml(model: SawtoothMergeModel) -> str:
    lines: list[str] = []

    def bool_tag(name: str) -> None:
        safe = re.sub(r"[^A-Za-z0-9_]", "_", name)
        lines.append(
            f'<Tag Name="{safe}" TagType="Base" DataType="BOOL" '
            f'Constant="false" ExternalAccess="Read/Write">'
            f'<Data Format="Decorated"><DataValue DataType="BOOL" Value="0"/></Data></Tag>'
        )

    for lane in model.lanes:
        idx = lane.lane_index
        for suffix in ("Occupied", "Clear", "ExitBlocked", "Request", "Reserved", "Slicing"):
            bool_tag(f"SawSem_L{idx}_{suffix}")
    for enc in model.encoders:
        if enc.sawtooth_associated:
            bool_tag(f"SawSem_{enc.encoder}_Enable")
            bool_tag(f"SawSem_{enc.encoder}_Reset")
        else:
            bool_tag(f"SawSem_{enc.encoder}_DocOnly")
    bool_tag("SawSem_MergeAvailable")
    return "".join(lines)


def build_semantic_conv_routines(model: SawtoothMergeModel, audit: dict[str, Any]) -> dict[str, str]:
    """Build Conv_* RLLContent from audit classifications — real logic only when CAN_GENERATE."""

    def _rungs(entries: list[tuple[str, str]]) -> str:
        parts = ["<RLLContent>"]
        for i, (comment, text) in enumerate(entries):
            parts.append(
                f'<Rung Number="{i}" Type="N">'
                f"<Comment><![CDATA[{comment}]]></Comment>"
                f"<Text><![CDATA[{text}]]></Text>"
                f"</Rung>"
            )
        parts.append("</RLLContent>")
        return "".join(parts)

    by_routine: dict[str, list[dict[str, Any]]] = {"Conv_PE": [], "Conv_Enc": [], "Conv_Fast": []}
    for it in audit.get("items") or []:
        r = it.get("routine")
        if r in by_routine:
            by_routine[r].append(it)

    out: dict[str, str] = {}
    for routine, items in by_routine.items():
        entries: list[tuple[str, str]] = []
        for it in items:
            cls = it.get("classification")
            comment = (
                f"{it.get('lane_or_encoder')} classification={cls} "
                f"reason={it.get('reason')} provenance={it.get('provenance')}"
            )
            if cls == CLS_CAN and it.get("proposed_text"):
                text = str(it["proposed_text"])
            elif cls == CLS_DOC:
                text = "NOP();"
            else:
                text = "NOP();"
            entries.append((comment, text))
        if not entries:
            entries.append((f"{routine} empty — CONFIGURATION REQUIRED", "NOP();"))
        out[routine] = _rungs(entries)
    return out


def force_replace_routines(
    xml: str,
    routines: dict[str, str],
    *,
    program_name: str = "Sawtooth_Merge",
) -> tuple[str, list[dict[str, str]]]:
    """Replace Conv_* only inside Sawtooth_Merge (do not touch Area_Slow/Fast)."""
    report: list[dict[str, str]] = []
    prog = _extract_program_xml(xml, program_name)
    if prog is None:
        # Standalone program file — replace globally
        out = xml
        for rname, content in routines.items():
            repl = f'<Routine Name="{rname}" Type="RLL">{content}</Routine>'
            pat = re.compile(
                rf'<Routine Name="{re.escape(rname)}" Type="RLL"[^>]*/>|'
                rf'<Routine Name="{re.escape(rname)}" Type="RLL"[^>]*>.*?</Routine>',
                flags=re.I | re.S,
            )
            if pat.search(out):
                out = pat.sub(repl, out, count=1)
                report.append({"routine": rname, "mode": "force_replace_whole_file"})
            else:
                report.append({"routine": rname, "mode": "MISSING"})
        return out, report

    new_prog = prog
    for rname, content in routines.items():
        repl = f'<Routine Name="{rname}" Type="RLL">{content}</Routine>'
        pat = re.compile(
            rf'<Routine Name="{re.escape(rname)}" Type="RLL"[^>]*/>|'
            rf'<Routine Name="{re.escape(rname)}" Type="RLL"[^>]*>.*?</Routine>',
            flags=re.I | re.S,
        )
        if pat.search(new_prog):
            new_prog = pat.sub(repl, new_prog, count=1)
            report.append({"routine": rname, "mode": f"force_replace_in_{program_name}"})
        else:
            report.append({"routine": rname, "mode": "MISSING_IN_PROGRAM"})
    out = xml.replace(prog, new_prog, 1)
    return out, report


def inject_semantic_tags(xml: str, tags_xml: str) -> tuple[str, str]:
    if not tags_xml:
        return xml, "skipped_empty"
    # Prefer Sawtooth_Merge program tags
    prog = _extract_program_xml(xml, "Sawtooth_Merge")
    if prog is not None:
        anchor = prog.find('Name="SawFid_LaneCount"')
        if anchor >= 0:
            end = prog.find("</Tag>", anchor)
            if end >= 0:
                end += len("</Tag>")
                new_prog = prog[:end] + tags_xml + prog[end:]
                return xml.replace(prog, new_prog, 1), "after_SawFid_LaneCount_in_Sawtooth_Merge"
        m = re.search(r"(<Tags[^>]*>)", prog, flags=re.I)
        if m:
            pos = m.end()
            new_prog = prog[:pos] + tags_xml + prog[pos:]
            return xml.replace(prog, new_prog, 1), "program_tags_Sawtooth_Merge"
    # Standalone / fallback
    anchor = xml.find('Name="SawFid_LaneCount"')
    if anchor >= 0:
        end = xml.find("</Tag>", anchor)
        if end >= 0:
            end += len("</Tag>")
            return xml[:end] + tags_xml + xml[end:], "after_SawFid_LaneCount"
    m = re.search(r"(<Program[^>]*>.*?<Tags[^>]*>)", xml, flags=re.S | re.I)
    if m:
        pos = m.end()
        return xml[:pos] + tags_xml + xml[pos:], "program_tags"
    idx = xml.find("</Tags>")
    if idx >= 0:
        return xml[:idx] + tags_xml + xml[idx:], "before_Tags_close"
    return xml, "FAILED"


def apply_semantic_renames(xml: str, model: SawtoothMergeModel) -> tuple[str, list[dict[str, Any]]]:
    renames: dict[str, str] = {}
    for lane in model.lanes:
        if lane.pack_full_eye_rename:
            renames.update(lane.pack_full_eye_rename)
    applied = []
    out = xml
    for old, new in sorted(renames.items(), key=lambda kv: len(kv[0]), reverse=True):
        if not old or old == new:
            continue
        n = out.count(old)
        if n:
            out = out.replace(old, new)
            applied.append({"from": old, "to": new, "occurrences": n, "provenance": PROV_DERIVED})
    return out, applied


# ---------------------------------------------------------------------------
# Semantic state transitions (scenario tests — not Logix emulation)
# ---------------------------------------------------------------------------


def lane_set_occupied(lane: SawtoothLaneModel, occupied: bool) -> None:
    if not lane.allowed_to_run:
        lane.state = STATE_DISABLED
        return
    if occupied:
        if lane.state in {STATE_CLEAR, STATE_RELEASING}:
            lane.state = STATE_OCCUPIED
    else:
        if lane.state in {STATE_RELEASING, STATE_OCCUPIED, STATE_REQUEST}:
            lane.state = STATE_CLEAR


def lane_request(lane: SawtoothLaneModel) -> bool:
    if not lane.allowed_to_run:
        lane.state = STATE_DISABLED
        return False
    if lane.state == STATE_OCCUPIED:
        lane.state = STATE_REQUEST
        return True
    return False


def lane_try_reserve(lane: SawtoothLaneModel, merge: SawtoothMergeModel) -> bool:
    if lane.state != STATE_REQUEST:
        return False
    if not merge.merge_available:
        return False
    lane.state = STATE_RESERVED
    merge.merge_available = False
    return True


def lane_start_slice(lane: SawtoothLaneModel) -> bool:
    if lane.state != STATE_RESERVED:
        return False
    lane.state = STATE_SLICING
    return True


def lane_release(lane: SawtoothLaneModel, merge: SawtoothMergeModel) -> bool:
    if lane.state != STATE_SLICING:
        return False
    lane.state = STATE_RELEASING
    merge.merge_available = True
    return True


def lane_clear(lane: SawtoothLaneModel) -> bool:
    if lane.state == STATE_RELEASING:
        lane.state = STATE_CLEAR
        return True
    if lane.state == STATE_OCCUPIED:
        lane.state = STATE_CLEAR
        return True
    return False


def encoder_advance(enc: SawtoothEncoderModel, pulses: int = 1) -> bool:
    if not enc.sawtooth_associated:
        return False
    enc.pulses += max(0, int(pulses))
    return True


def encoder_reset(enc: SawtoothEncoderModel) -> bool:
    if not enc.sawtooth_associated:
        return False
    enc.pulses = 0
    return True


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------


def validate_generated_l5x(
    l5x_path: Path,
    model: SawtoothMergeModel,
    *,
    expect_real_logic: bool = True,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    if not l5x_path.is_file():
        return {
            "generated_at": _ts(),
            "l5x": str(l5x_path),
            "ok": False,
            "checks": [{"name": "l5x_exists", "ok": False, "detail": "missing"}],
        }

    text = l5x_path.read_text(encoding="utf-8", errors="replace")
    check("l5x_exists", True, str(l5x_path))
    saw = _extract_program_xml(text, "Sawtooth_Merge") or text
    # SawFid markers may live in Sawtooth_Merge (preferred) or whole controller
    fid_scope = saw if "SawFid_LaneCount" in saw else text
    check("has_Sawtooth_Merge", "Sawtooth_Merge" in text)
    check("has_SawFid_LaneCount", "SawFid_LaneCount" in fid_scope)

    m = re.search(
        r'<Tag Name="SawFid_LaneCount"[^>]*>.*?Value="(\d+)"',
        fid_scope,
        flags=re.S,
    )
    lane_count_val = int(m.group(1)) if m else None
    check("lane_count_tag_equals_5", lane_count_val == 5, f"value={lane_count_val}")
    check("model_lane_count_equals_5", len(model.lanes) == 5, f"model={len(model.lanes)}")

    for lane in model.lanes:
        idx = lane.lane_index
        check(f"index_tag_L{idx}", f"SawFid_L{idx}_Index" in fid_scope)
        if lane.photoeye:
            check(
                f"pe_present_{lane.photoeye.symbol}",
                lane.photoeye.symbol in saw or lane.photoeye.symbol in fid_scope,
            )
        if lane.drive:
            check(
                f"drive_present_{lane.drive.symbol}",
                lane.drive.symbol in saw
                or lane.drive.symbol in fid_scope
                or f"Drive_{lane.drive.symbol}" in fid_scope,
            )
        if lane.conveyor:
            check(f"conv_marker_L{idx}", f"SawFid_L{idx}_Conv_{lane.conveyor}" in fid_scope)

    # Explicit relationship preserved
    lane116 = model.lane_by_name("LANE_3_P116")
    if lane116 and lane116.photoeye and lane116.drive:
        check(
            "LANE_3_P116_PE118_VFD118",
            lane116.photoeye.symbol == "PE118_P" and lane116.drive.symbol == "VFD118_EN",
            f"pe={lane116.photoeye.symbol} drive={lane116.drive.symbol}",
        )

    check("ENC414_ticks_tag", "SawFid_ENC414_TicksPerFoot" in fid_scope)
    check("VFD414_shared_P414", "SawFid_Shared_VFD414_P414" in text or "VFD414" in fid_scope)

    for routine in ("Conv_PE", "Conv_Enc", "Conv_Fast"):
        filled = bool(
            re.search(rf'<Routine Name="{routine}" Type="RLL">\s*<RLLContent>', saw)
        )
        check(f"{routine}_filled", filled)
        if expect_real_logic and routine == "Conv_PE":
            check(
                "Conv_PE_has_real_XIO_or_XIC",
                "XIO(" in saw and "SawSem_L" in saw and "Occupied" in saw,
                "expect SawSem occupied binding",
            )

    # No dangling SawSem OTE targets without tag definitions (Sawtooth scope)
    ote_targets = set(re.findall(r"OTE\((SawSem_[A-Za-z0-9_]+)\)", saw))
    tag_names = set(re.findall(r'<Tag Name="([^"]+)"', saw))
    tag_names |= set(re.findall(r'<Tag Name="([^"]+)"', text))
    dangling = sorted(t for t in ote_targets if t not in tag_names)
    check("no_dangling_SawSem_refs", not dangling, f"dangling={dangling[:10]}")

    # Timers / slice markers
    check("slice_timer_L1", "SawFid_L1_SliceSec" in fid_scope)
    check("reserve_timer_L3", "SawFid_L3_ReserveSec" in fid_scope)

    # ENC424 must not be classified as sawtooth forced
    enc424 = model.encoder_by_name("ENC424")
    if enc424:
        check(
            "ENC424_not_forced_sawtooth",
            not enc424.sawtooth_associated and enc424.role == "CITY_COUNTER",
            enc424.detail,
        )

    ok = all(c["ok"] for c in checks)
    return {
        "generated_at": _ts(),
        "l5x": str(l5x_path),
        "ok": ok,
        "passed": sum(1 for c in checks if c["ok"]),
        "failed": sum(1 for c in checks if not c["ok"]),
        "checks": checks,
    }


def count_resolution_buckets(
    merge_map: dict[str, Any],
    enc_sem: dict[str, Any],
    vfd_sem: dict[str, Any],
    audit_before: dict[str, Any],
    audit_after: dict[str, Any],
) -> dict[str, Any]:
    run_n = 0
    lib_n = 0
    cfg_n = 0
    unk_n = 0
    unsup_n = 0
    for m in merge_map.get("mappings") or []:
        p = m.get("provenance")
        if p == PROV_RUN:
            run_n += 1
        elif p in {PROV_LIBRARY, PROV_GENERIC, "GENERIC_LIBRARY_TEMPLATE"}:
            lib_n += 1
        elif p in {PROV_CFG, "CONFIGURATION REQUIRED", CLS_CFG}:
            cfg_n += 1
        elif p in {PROV_UNKNOWN, "UNKNOWN"}:
            unk_n += 1
        elif p == PROV_NOT_SUPPORTED:
            unsup_n += 1
        elif p == PROV_DERIVED:
            run_n += 1  # derived from RUN evidence
    for e in enc_sem.get("encoders") or []:
        if e.get("generation_policy") == CLS_CAN:
            run_n += 1
        elif e.get("generation_policy") == CLS_DOC:
            lib_n += 1
        elif e.get("generation_policy") == CLS_CFG:
            cfg_n += 1
    for d in vfd_sem.get("lane_drives") or []:
        if d.get("provenance") == PROV_RUN:
            run_n += 1
    return {
        "resolved_RUN": run_n,
        "resolved_library": lib_n,
        "CONFIGURATION_REQUIRED": cfg_n
        + (audit_after.get("counts") or {}).get(CLS_CFG, 0),
        "UNKNOWN": unk_n,
        "UNSUPPORTED": unsup_n
        + (audit_after.get("counts") or {}).get(CLS_UNSUPPORTED, 0)
        + 1,  # tracking/wcs
        "placeholder_before_nop": (audit_before.get("counts") or {}).get("was_nop"),
        "placeholder_after_nop": (audit_after.get("counts") or {}).get("was_nop"),
        "can_generate_before": (audit_before.get("counts") or {}).get(CLS_CAN),
        "can_generate_after_applied": (audit_after.get("counts") or {}).get(CLS_CAN),
    }


def inventory_pack_symbols_from_path(pack_path: Path) -> set[str]:
    if not pack_path.is_file():
        return set()
    text = pack_path.read_text(encoding="utf-8", errors="replace")
    return set(
        re.findall(
            r"\b(?:MRG\d+_[A-Za-z0-9_]+|P\d+[A-Z]?_Conv|P\d+[A-Z]?_Enc|"
            r"P\d+[A-Z]?_SawMerge_HMI|PE\d+[A-Z]?_[A-Z0-9]+|EZPE\d+[A-Z0-9_]*|"
            r"VFD\d+[A-Z0-9_]*|ENC\d+[A-Z0-9_]*)\b",
            text,
        )
    )


__all__ = [
    "SawtoothMergeModel",
    "SawtoothLaneModel",
    "SawtoothEncoderModel",
    "DriveBinding",
    "ReservationBinding",
    "SensorBinding",
    "build_semantic_model",
    "model_to_json",
    "build_merge_signal_map",
    "build_encoder_semantics",
    "build_vfd_semantics",
    "audit_placeholders",
    "build_semantic_conv_routines",
    "build_semantic_tags_xml",
    "force_replace_routines",
    "inject_semantic_tags",
    "apply_semantic_renames",
    "validate_generated_l5x",
    "lane_set_occupied",
    "lane_request",
    "lane_try_reserve",
    "lane_start_slice",
    "lane_release",
    "lane_clear",
    "encoder_advance",
    "encoder_reset",
    "STATE_CLEAR",
    "STATE_OCCUPIED",
    "STATE_REQUEST",
    "STATE_RESERVED",
    "STATE_SLICING",
    "STATE_RELEASING",
    "STATE_DISABLED",
    "CLS_CAN",
    "CLS_CFG",
    "CLS_UNSUPPORTED",
    "CLS_DOC",
]
