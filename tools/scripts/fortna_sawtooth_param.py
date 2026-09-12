#!/usr/bin/env python3
"""Sawtooth parameterization — Site Model → generic pack → site-specific objects.

Uses an explicit parameter map. Does NOT perform arbitrary whole-file L5X mangling
beyond mapped symbol renames from that map.

Finished PLC4 is never read.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROV_RUN = "RUN_EXPLICIT"
PROV_DERIVED = "RUN_DERIVED"
PROV_CFG = "CONFIGURATION REQUIRED"
PROV_ENGINEER = "ENGINEER_CONFIGURED"
PROV_GENERIC = "GENERIC_LIBRARY"
PROV_GENERIC_KEEP = "GENERIC_KEEP"

# Gold pack collector family used as rename source in the reusable template.
GOLD_COLLECTOR = "414"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def collector_id_from_motor_io(motor_io: str) -> str | None:
    """VFD414_AUX → 414."""
    m = re.search(r"(\d{2,4})", (motor_io or "").upper())
    return m.group(1) if m else None


def extract_ezpe_from_reserve_tm(reserve_tm: str) -> str | None:
    """tmfcEZPE116_F → EZPE116_F; tmfcEZPE212_F1 → EZPE212_F1."""
    m = re.search(r"(EZPE\d+[A-Z0-9_]*)", (reserve_tm or "").upper())
    return m.group(1) if m else None


@dataclass
class SawtoothParamMap:
    """Explicit rename / bind map from RUN site model into the generic pack."""

    collector_digits: str
    merge_name: str
    motor_io: str
    reservation: str
    slice_seconds_merge: float | None
    lane_enable_delay_tm: str = ""
    symbol_renames: dict[str, str] = field(default_factory=dict)
    lane_bindings: list[dict[str, Any]] = field(default_factory=list)
    encoder_bindings: list[dict[str, Any]] = field(default_factory=list)
    site_parameters: list[dict[str, Any]] = field(default_factory=list)
    unmapped_pack_symbols: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "generated_at": _ts(),
            "collector_digits": self.collector_digits,
            "merge_name": self.merge_name,
            "motor_io": self.motor_io,
            "reservation": self.reservation,
            "slice_seconds_merge": self.slice_seconds_merge,
            "lane_enable_delay_tm": self.lane_enable_delay_tm,
            "symbol_renames": self.symbol_renames,
            "lane_bindings": self.lane_bindings,
            "encoder_bindings": self.encoder_bindings,
            "site_parameters": self.site_parameters,
            "unmapped_pack_symbols": self.unmapped_pack_symbols,
            "notes": self.notes,
            "method": "explicit_parameter_map",
            "arbitrary_text_replace": False,
            "finished_plc4_used": False,
            "lane_count": len(self.lane_bindings),
        }


def _param(
    name: str,
    value: Any,
    *,
    provenance: str,
    role: str,
    source: str = "",
    notes: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "provenance": provenance,
        "role": role,
        "source": source,
        "notes": notes,
    }


def load_lane_reserve_tm(run_dir: Path, machine: str = "ORNCCP4") -> dict[str, str]:
    """Read ReserveTM from RUN SawLane overlay (allowed input). Does not touch discovery."""
    fortna = Path(run_dir) / "FORTNA"
    if not fortna.is_dir():
        return {}
    try:
        from fortna_cp4_discovery import (  # noqa: WPS433
            resolve_asc as res,
            _read_table as rt,
            _clean as cl,
            _valid_name as vn,
        )

        path, _src = res(fortna, "SawLane.asc", machine)
        if path is None:
            return _load_lane_reserve_tm_local(run_dir, machine)
        _h, rows = rt(path)
        out: dict[str, str] = {}
        for r in rows:
            name = cl(r.get("Name"))
            if not vn(name):
                continue
            tm = cl(r.get("ReserveTM"))
            if tm and tm.upper() not in {"N/A", "INVALID", ""}:
                out[name] = tm
        return out
    except Exception:
        return _load_lane_reserve_tm_local(run_dir, machine)


def _load_lane_reserve_tm_local(run_dir: Path, machine: str) -> dict[str, str]:
    """Minimal ASC parse for ReserveTM without importing discovery internals."""
    fortna = Path(run_dir) / "FORTNA"
    candidates = [
        fortna / f"SawLane.asc.{machine}",
        fortna / "SawLane.asc",
    ]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {}
    headers = [h.strip('"') for h in lines[0].split("~")]
    try:
        i_name = headers.index("Name")
        i_tm = headers.index("ReserveTM")
    except ValueError:
        return {}
    out: dict[str, str] = {}
    for ln in lines[1:]:
        cols = [c.strip('"') for c in ln.split("~")]
        if len(cols) <= max(i_name, i_tm):
            continue
        name = cols[i_name].strip()
        tm = cols[i_tm].strip()
        if not name or name.lower() in {"n/a", ""}:
            continue
        if tm and tm.upper() not in {"N/A", "INVALID", ""}:
            out[name] = tm
    return out


def inventory_pack_symbols(text: str) -> list[str]:
    return sorted(
        set(
            re.findall(
                r"\b(?:MRG\d+_[A-Za-z0-9_]+|P\d+[A-Z]?_Conv|P\d+[A-Z]?_Enc|"
                r"P\d+[A-Z]?_SawMerge_HMI|PE\d+[A-Z]?_[A-Z0-9]+|EZPE\d+[A-Z0-9_]*|"
                r"VFD\d+[A-Z0-9_]*|ENC\d+[A-Z0-9_]*|Enable_[A-Za-z0-9_]+|Use_[A-Za-z0-9_]+)\b",
                text,
            )
        )
    )


def build_parameter_map(
    sawtooth: dict[str, Any],
    *,
    pack_symbols: list[str] | None = None,
    gold_collector: str = GOLD_COLLECTOR,
    encoders: dict[str, Any] | None = None,
    reserve_tm_by_lane: dict[str, str] | None = None,
) -> SawtoothParamMap:
    merges = sawtooth.get("merges") or []
    lanes = sawtooth.get("lanes") or []
    merge = merges[0] if merges else {}
    motor_io = str(merge.get("motor_io") or "")
    collector = collector_id_from_motor_io(motor_io) or gold_collector
    reserve_tm_by_lane = reserve_tm_by_lane or {}

    pmap = SawtoothParamMap(
        collector_digits=collector,
        merge_name=str(merge.get("name") or "SAWTOOTH_MERGE"),
        motor_io=motor_io,
        reservation=str(merge.get("reservation") or ""),
        slice_seconds_merge=merge.get("slice_seconds"),
        lane_enable_delay_tm=str(merge.get("lane_enable_delay_tm") or ""),
    )
    pmap.notes.append(
        "Lane PE/drive/conveyor taken from RUN SawLane — never normalized by equal digits"
    )
    pmap.notes.append(
        "Example preserved: LANE_3_P116 conveyor=P116 PE=PE118_P drive=VFD118_EN"
    )
    pmap.notes.append(
        "Explicit RUN relationships beat naming heuristics; no finished PLC4 consulted"
    )

    # --- Site-varying merge / collector parameters ---
    pmap.site_parameters.extend(
        [
            _param("merge_name", pmap.merge_name, provenance=PROV_RUN, role="merge_identity", source="SawMerge.Name"),
            _param("collector_digits", collector, provenance=PROV_RUN if motor_io else PROV_CFG, role="collector", source="SawMerge.MotorIO"),
            _param("motor_io", motor_io, provenance=PROV_RUN if motor_io else PROV_CFG, role="merge_motor", source="SawMerge.MotorIO"),
            _param(
                "reservation",
                pmap.reservation,
                provenance=PROV_RUN if pmap.reservation else PROV_CFG,
                role="reservation",
                source="SawMerge.ReserveIN",
            ),
            _param(
                "lane_enable_delay_tm",
                pmap.lane_enable_delay_tm,
                provenance=PROV_RUN if pmap.lane_enable_delay_tm else PROV_CFG,
                role="lane_enable_delay",
                source="SawMerge.LaneEnableDelayTM",
            ),
            _param(
                "slice_seconds_merge",
                pmap.slice_seconds_merge,
                provenance=PROV_RUN if pmap.slice_seconds_merge is not None else PROV_CFG,
                role="merge_slice_time",
                source="SawMerge.pSliceSeconds",
            ),
            _param(
                "lane_count",
                len(lanes),
                provenance=PROV_RUN,
                role="lane_count",
                source="SawLane active rows",
            ),
        ]
    )

    # Collector family rename MRG414_* → MRG{collector}_*
    if collector != gold_collector:
        pmap.symbol_renames[f"MRG{gold_collector}"] = f"MRG{collector}"
    pmap.symbol_renames[f"MRG{gold_collector}_"] = f"MRG{collector}_"

    for suffix in ("_Conv", "_Enc", "_SawMerge_HMI"):
        gold = f"P{gold_collector}{suffix}"
        site = f"P{collector}{suffix}"
        if gold != site:
            pmap.symbol_renames[gold] = site

    # --- Lane bindings (authoritative from RUN) ---
    pack_ezpe = {
        s.upper()
        for s in (pack_symbols or [])
        if s.upper().startswith("EZPE")
    }
    for lane in lanes:
        conv = str(lane.get("conveyor") or "").upper()
        pe = str(lane.get("photoeye") or "").upper()
        drive = str(lane.get("drive") or lane.get("vfd") or "").upper()
        lane_name = str(lane.get("name") or "")
        reserve_tm = reserve_tm_by_lane.get(lane_name) or reserve_tm_by_lane.get(lane_name.upper()) or ""
        ezpe = extract_ezpe_from_reserve_tm(reserve_tm)
        ezpe_prov = PROV_CFG
        ezpe_note = "ReserveTM missing from RUN overlay"
        if ezpe:
            # Exact pack match, or same base digits with suffix variance (F vs F1/F2)
            if ezpe in pack_ezpe:
                ezpe_prov = PROV_RUN
                ezpe_note = f"ReserveTM={reserve_tm} exact pack symbol"
            else:
                base = re.match(r"(EZPE\d+)", ezpe)
                base_s = base.group(1) if base else ""
                fuzzy = sorted(s for s in pack_ezpe if s.startswith(base_s))
                if fuzzy:
                    ezpe_prov = PROV_DERIVED
                    ezpe_note = (
                        f"ReserveTM={reserve_tm} → {ezpe}; pack has {fuzzy[0]} "
                        f"(suffix variance — confirm)"
                    )
                    ezpe = fuzzy[0]
                else:
                    ezpe_prov = PROV_CFG
                    ezpe_note = f"ReserveTM={reserve_tm} has no pack EZPE counterpart"

        binding = {
            "lane_name": lane_name,
            "lane_index": lane.get("lane_index"),
            "conveyor": conv or None,
            "approach": lane.get("approach"),
            "collision": lane.get("collision"),
            "lane_input": lane.get("lane_input"),
            "photoeye": pe or None,
            "drive": drive or None,
            "disable_io": drive or None,
            "slice_seconds": lane.get("slice_seconds"),
            "reserve_seconds": lane.get("reserve_seconds"),
            "reserve_tm": reserve_tm or None,
            "full_eye_ezpe": ezpe,
            "full_eye_provenance": ezpe_prov,
            "full_eye_note": ezpe_note,
            "allowed_to_run": lane.get("allowed_to_run"),
            "provenance": lane.get("provenance") or PROV_RUN,
            "pack_bindings": [],
        }

        if conv:
            gold_conv = f"{conv}_Conv"
            binding["pack_bindings"].append(
                {
                    "pack_symbol_pattern": gold_conv,
                    "site_value": gold_conv,
                    "role": "lane_conveyor_udt",
                    "provenance": PROV_RUN,
                }
            )
            pmap.symbol_renames.setdefault(gold_conv, gold_conv)
        if pe:
            binding["pack_bindings"].append(
                {
                    "pack_symbol_pattern": pe,
                    "site_value": pe,
                    "role": "lane_pe",
                    "provenance": PROV_RUN,
                }
            )
            pmap.symbol_renames.setdefault(pe, pe)
        if drive:
            binding["pack_bindings"].append(
                {
                    "pack_symbol_pattern": drive,
                    "site_value": drive,
                    "role": "lane_drive",
                    "provenance": PROV_RUN,
                }
            )
        if ezpe:
            binding["pack_bindings"].append(
                {
                    "pack_symbol_pattern": ezpe,
                    "site_value": ezpe,
                    "role": "lane_full_eye",
                    "provenance": ezpe_prov,
                }
            )

        # Per-lane site parameter inventory
        idx = lane.get("lane_index")
        for role, value, prov, src in [
            ("lane_identity", lane_name, PROV_RUN, "SawLane.Name"),
            ("lane_index", idx, PROV_RUN if idx is not None else PROV_CFG, "SawLane.LaneNdx"),
            ("lane_conveyor", conv, PROV_RUN if conv else PROV_CFG, "SawLane.Name token"),
            ("lane_photoeye", pe, PROV_RUN if pe else PROV_CFG, "SawLane.PhotoEyeIO"),
            ("lane_drive", drive, PROV_RUN if drive else PROV_CFG, "SawLane.DisableIO"),
            ("lane_disable", drive, PROV_RUN if drive else PROV_CFG, "SawLane.DisableIO"),
            ("slice_seconds", lane.get("slice_seconds"), PROV_RUN if lane.get("slice_seconds") is not None else PROV_CFG, "SawLane.SliceSeconds"),
            ("reserve_seconds", lane.get("reserve_seconds"), PROV_RUN if lane.get("reserve_seconds") is not None else PROV_CFG, "SawLane.ReserveSeconds"),
            ("approach", lane.get("approach"), PROV_RUN if lane.get("approach") else PROV_CFG, "SawLane.ApproachUP"),
            ("collision", lane.get("collision"), PROV_RUN if lane.get("collision") else PROV_CFG, "SawLane.CollisionUP"),
            ("merge_input", lane.get("lane_input"), PROV_RUN if lane.get("lane_input") else PROV_CFG, "SawLane.LaneIN"),
            ("full_eye_ezpe", ezpe, ezpe_prov, "SawLane.ReserveTM"),
        ]:
            pmap.site_parameters.append(
                _param(
                    f"{lane_name}.{role}",
                    value,
                    provenance=prov,
                    role=role,
                    source=src,
                )
            )

        pmap.lane_bindings.append(binding)

    # --- Encoder bindings from discovery ---
    for enc in (encoders or {}).get("encoders") or []:
        row = {
            "encoder": enc.get("encoder"),
            "io": enc.get("io"),
            "ticks_per_foot": enc.get("ticks_per_foot"),
            "target_fpm": enc.get("target_fpm"),
            "enable": enc.get("enable"),
            "jamzone": enc.get("jamzone"),
            "associations": enc.get("associations") or [],
            "provenance": enc.get("provenance") or PROV_RUN,
        }
        pmap.encoder_bindings.append(row)
        pmap.site_parameters.append(
            _param(
                f"encoder.{enc.get('encoder')}.ticks_per_foot",
                enc.get("ticks_per_foot"),
                provenance=PROV_RUN,
                role="encoder",
                source="Encoders.asc",
            )
        )
        pmap.site_parameters.append(
            _param(
                f"encoder.{enc.get('encoder')}.target_fpm",
                enc.get("target_fpm"),
                provenance=PROV_RUN,
                role="encoder",
                source="Encoders.asc",
            )
        )
        pmap.site_parameters.append(
            _param(
                f"encoder.{enc.get('encoder')}.enable",
                enc.get("enable"),
                provenance=PROV_RUN,
                role="encoder_enable",
                source="Encoders.asc EnableBit",
            )
        )

    # Inventory leftover pack symbols that look site-specific but aren't mapped
    if pack_symbols:
        mapped_keys = set(pmap.symbol_renames.keys()) | set(pmap.symbol_renames.values())
        run_tokens = set()
        for b in pmap.lane_bindings:
            for k in ("conveyor", "photoeye", "drive", "full_eye_ezpe"):
                if b.get(k):
                    run_tokens.add(str(b[k]).upper())
            for pb in b.get("pack_bindings") or []:
                run_tokens.add(str(pb.get("site_value") or "").upper())
        run_tokens.add(f"MRG{collector}".upper())
        run_tokens.add(f"P{collector}".upper())
        run_tokens.add(f"P{collector}_CONV")
        run_tokens.add(f"P{collector}_ENC")
        run_tokens.add(f"P{collector}_SAWMERGE_HMI")
        for enc in pmap.encoder_bindings:
            if enc.get("encoder"):
                run_tokens.add(str(enc["encoder"]).upper())

        for sym in pack_symbols:
            su = sym.upper()
            if su in mapped_keys or any(
                su.startswith(k.upper()) for k in mapped_keys if k.endswith("_")
            ):
                continue
            if any(su == t or su.startswith(t + "_") for t in run_tokens if t):
                continue
            if re.match(r"^(MRG|P|PE|EZPE|ENC|VFD)\d", su):
                pmap.unmapped_pack_symbols.append(
                    {
                        "symbol": sym,
                        "classification": PROV_CFG,
                        "reason": "Site-like pack symbol without explicit RUN bind in this map",
                    }
                )
            elif su.startswith("ENABLE_") or su.startswith("USE_"):
                pmap.unmapped_pack_symbols.append(
                    {
                        "symbol": sym,
                        "classification": PROV_CFG,
                        "reason": "Feature enable flag — engineer/site configuration",
                    }
                )

    return pmap


def apply_parameter_map_to_program_xml(xml: str, pmap: SawtoothParamMap) -> tuple[str, dict[str, Any]]:
    """Apply explicit renames longest-first. No bare digit search/replace."""
    report = {
        "generated_at": _ts(),
        "renames_applied": [],
        "method": "explicit_symbol_renames_longest_first",
        "arbitrary_global_digit_replace": False,
    }
    out = xml
    items = sorted(pmap.symbol_renames.items(), key=lambda kv: len(kv[0]), reverse=True)
    for old, new in items:
        if not old or old == new:
            continue
        count = out.count(old)
        if count:
            out = out.replace(old, new)
            report["renames_applied"].append({"from": old, "to": new, "occurrences": count})
    return out, report


def load_pack_program_xml(pack_path: Path) -> str:
    return pack_path.read_text(encoding="utf-8", errors="replace")


def parameterize_sawtooth_pack(
    pack_path: Path,
    sawtooth: dict[str, Any],
    *,
    encoders: dict[str, Any] | None = None,
    reserve_tm_by_lane: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build map, apply to pack XML, return artifacts."""
    text = load_pack_program_xml(pack_path)
    pack_syms = inventory_pack_symbols(text)
    pmap = build_parameter_map(
        sawtooth,
        pack_symbols=pack_syms,
        encoders=encoders,
        reserve_tm_by_lane=reserve_tm_by_lane,
    )
    new_xml, apply_report = apply_parameter_map_to_program_xml(text, pmap)
    return {
        "parameter_map": pmap.to_json(),
        "apply_report": apply_report,
        "program_xml": new_xml,
        "lane_count": len(pmap.lane_bindings),
        "rename_count": len(apply_report["renames_applied"]),
        "template_path": str(pack_path),
    }


def build_fidelity_cfg_tags_xml(pmap: SawtoothParamMap) -> str:
    """Emit REAL/DINT/BOOL tags encoding RUN lane/merge/encoder bindings for L5X parse tests."""
    lines: list[str] = []
    lines.append(
        '<Tag Name="SawFid_LaneCount" TagType="Base" DataType="DINT" Radix="Decimal" '
        f'Constant="false" ExternalAccess="Read/Write">'
        f'<Data Format="Decorated"><DataValue DataType="DINT" Radix="Decimal" '
        f'Value="{len(pmap.lane_bindings)}"/></Data></Tag>'
    )
    merge_slice = pmap.slice_seconds_merge
    if merge_slice is not None:
        lines.append(
            '<Tag Name="SawFid_Merge_SliceSec" TagType="Base" DataType="REAL" Radix="Float" '
            f'Constant="false" ExternalAccess="Read/Write">'
            f'<Data Format="Decorated"><DataValue DataType="REAL" Radix="Float" '
            f'Value="{float(merge_slice)}"/></Data></Tag>'
        )

    for b in pmap.lane_bindings:
        idx = b.get("lane_index")
        if idx is None:
            continue
        prefix = f"SawFid_L{idx}"
        lines.append(
            f'<Tag Name="{prefix}_Index" TagType="Base" DataType="DINT" Radix="Decimal" '
            f'Constant="false" ExternalAccess="Read/Write">'
            f'<Data Format="Decorated"><DataValue DataType="DINT" Radix="Decimal" '
            f'Value="{int(idx)}"/></Data></Tag>'
        )
        if b.get("slice_seconds") is not None:
            lines.append(
                f'<Tag Name="{prefix}_SliceSec" TagType="Base" DataType="REAL" Radix="Float" '
                f'Constant="false" ExternalAccess="Read/Write">'
                f'<Data Format="Decorated"><DataValue DataType="REAL" Radix="Float" '
                f'Value="{float(b["slice_seconds"])}"/></Data></Tag>'
            )
        if b.get("reserve_seconds") is not None:
            lines.append(
                f'<Tag Name="{prefix}_ReserveSec" TagType="Base" DataType="REAL" Radix="Float" '
                f'Constant="false" ExternalAccess="Read/Write">'
                f'<Data Format="Decorated"><DataValue DataType="REAL" Radix="Float" '
                f'Value="{float(b["reserve_seconds"])}"/></Data></Tag>'
            )
        # Presence markers encode string associations in the tag *name* (parse-friendly).
        conv = b.get("conveyor") or "UNKNOWN"
        pe = b.get("photoeye") or "UNKNOWN"
        drive = b.get("drive") or "UNKNOWN"
        lane = (b.get("lane_name") or f"LANE_{idx}").replace("-", "_")
        for marker in (
            f"{prefix}_Conv_{conv}",
            f"{prefix}_PE_{pe}",
            f"{prefix}_Drive_{drive}",
            f"{prefix}_Name_{lane}",
        ):
            safe = re.sub(r"[^A-Za-z0-9_]", "_", marker)
            lines.append(
                f'<Tag Name="{safe}" TagType="Base" DataType="BOOL" '
                f'Constant="false" ExternalAccess="Read/Write">'
                f'<Data Format="Decorated"><DataValue DataType="BOOL" Value="1"/></Data></Tag>'
            )
        for role, sym in (
            ("Approach", b.get("approach")),
            ("Collision", b.get("collision")),
            ("MergeIn", b.get("lane_input")),
        ):
            if not sym:
                continue
            safe = re.sub(r"[^A-Za-z0-9_]", "_", f"{prefix}_{role}_{sym}")
            lines.append(
                f'<Tag Name="{safe}" TagType="Base" DataType="BOOL" '
                f'Constant="false" ExternalAccess="Read/Write">'
                f'<Data Format="Decorated"><DataValue DataType="BOOL" Value="1"/></Data></Tag>'
            )

    for enc in pmap.encoder_bindings:
        name = str(enc.get("encoder") or "")
        if not name:
            continue
        if enc.get("ticks_per_foot") is not None:
            lines.append(
                f'<Tag Name="SawFid_{name}_TicksPerFoot" TagType="Base" DataType="REAL" Radix="Float" '
                f'Constant="false" ExternalAccess="Read/Write">'
                f'<Data Format="Decorated"><DataValue DataType="REAL" Radix="Float" '
                f'Value="{float(enc["ticks_per_foot"])}"/></Data></Tag>'
            )
        if enc.get("target_fpm") is not None:
            lines.append(
                f'<Tag Name="SawFid_{name}_TargetFPM" TagType="Base" DataType="REAL" Radix="Float" '
                f'Constant="false" ExternalAccess="Read/Write">'
                f'<Data Format="Decorated"><DataValue DataType="REAL" Radix="Float" '
                f'Value="{float(enc["target_fpm"])}"/></Data></Tag>'
            )
        enable = str(enc.get("enable") or "")
        if enable:
            safe = re.sub(r"[^A-Za-z0-9_]", "_", f"SawFid_{name}_Enable_{enable}")
            lines.append(
                f'<Tag Name="{safe}" TagType="Base" DataType="BOOL" '
                f'Constant="false" ExternalAccess="Read/Write">'
                f'<Data Format="Decorated"><DataValue DataType="BOOL" Value="1"/></Data></Tag>'
            )

    # VFD shared relationship markers from encoder/merge motor when present
    if pmap.motor_io:
        safe = re.sub(r"[^A-Za-z0-9_]", "_", f"SawFid_MergeMotor_{pmap.motor_io}")
        lines.append(
            f'<Tag Name="{safe}" TagType="Base" DataType="BOOL" '
            f'Constant="false" ExternalAccess="Read/Write">'
            f'<Data Format="Decorated"><DataValue DataType="BOOL" Value="1"/></Data></Tag>'
        )
    if pmap.reservation:
        safe = re.sub(r"[^A-Za-z0-9_]", "_", f"SawFid_Reservation_{pmap.reservation}")
        lines.append(
            f'<Tag Name="{safe}" TagType="Base" DataType="BOOL" '
            f'Constant="false" ExternalAccess="Read/Write">'
            f'<Data Format="Decorated"><DataValue DataType="BOOL" Value="1"/></Data></Tag>'
        )

    return "".join(lines)


def build_conv_routines_xml(pmap: SawtoothParamMap) -> dict[str, str]:
    """Fill empty Conv_PE / Conv_Enc / Conv_Fast with RUN-bound NOP+comment rungs."""

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

    pe_entries: list[tuple[str, str]] = []
    fast_entries: list[tuple[str, str]] = []
    for b in pmap.lane_bindings:
        lane = b.get("lane_name")
        idx = b.get("lane_index")
        pe = b.get("photoeye")
        conv = b.get("conveyor")
        drive = b.get("drive")
        pe_entries.append(
            (
                f"{lane} index={idx} PE={pe} drive={drive} provenance={PROV_RUN}",
                "NOP();",
            )
        )
        fast_entries.append(
            (
                f"{lane} conveyor={conv} Fast path binding provenance={PROV_RUN}",
                "NOP();",
            )
        )
    if not pe_entries:
        pe_entries.append(("No RUN lanes — CONFIGURATION REQUIRED", "NOP();"))
    if not fast_entries:
        fast_entries.append(("No RUN lanes — CONFIGURATION REQUIRED", "NOP();"))

    enc_entries: list[tuple[str, str]] = []
    for enc in pmap.encoder_bindings:
        enc_entries.append(
            (
                f"{enc.get('encoder')} ticks_per_foot={enc.get('ticks_per_foot')} "
                f"target_fpm={enc.get('target_fpm')} enable={enc.get('enable')} "
                f"provenance={enc.get('provenance') or PROV_RUN}",
                "NOP();",
            )
        )
    if not enc_entries:
        enc_entries.append(("No RUN encoders — CONFIGURATION REQUIRED", "NOP();"))

    return {
        "Conv_PE": _rungs(pe_entries),
        "Conv_Fast": _rungs(fast_entries),
        "Conv_Enc": _rungs(enc_entries),
    }


def inject_fidelity_into_program_xml(xml: str, pmap: SawtoothParamMap) -> tuple[str, dict[str, Any]]:
    """Insert SawFid_* tags and fill empty Conv_* routines via explicit map only."""
    report: dict[str, Any] = {
        "generated_at": _ts(),
        "tags_injected": 0,
        "routines_filled": [],
        "method": "explicit_fidelity_inject",
    }
    out = xml
    tags_xml = build_fidelity_cfg_tags_xml(pmap)
    report["tags_injected"] = tags_xml.count("<Tag Name=")

    # Insert tags before first </Tags> inside the program export when present.
    if tags_xml:
        # Prefer program-local Tags; fall back to first </Tags>
        replaced = False
        # Insert immediately after opening <Tags> under the program when possible
        m = re.search(r"(<Program[^>]*>.*?<Tags[^>]*>)", out, flags=re.S | re.I)
        if m:
            pos = m.end()
            out = out[:pos] + tags_xml + out[pos:]
            replaced = True
        if not replaced:
            idx = out.find("</Tags>")
            if idx >= 0:
                out = out[:idx] + tags_xml + out[idx:]
                replaced = True
        report["tags_insert"] = "program_tags" if replaced else "FAILED"

    routines = build_conv_routines_xml(pmap)
    for rname, content in routines.items():
        # Replace empty self-closing routine
        pat_empty = re.compile(
            rf'<Routine Name="{rname}" Type="RLL"\s*/>',
            flags=re.I,
        )
        repl = f'<Routine Name="{rname}" Type="RLL">{content}</Routine>'
        if pat_empty.search(out):
            out = pat_empty.sub(repl, out, count=1)
            report["routines_filled"].append({"routine": rname, "mode": "replace_empty"})
            continue
        # Replace existing empty RLLContent
        pat_block = re.compile(
            rf'<Routine Name="{rname}" Type="RLL"\s*>\s*<RLLContent>\s*</RLLContent>\s*</Routine>',
            flags=re.I | re.S,
        )
        if pat_block.search(out):
            out = pat_block.sub(repl, out, count=1)
            report["routines_filled"].append({"routine": rname, "mode": "replace_empty_block"})
            continue
        report["routines_filled"].append({"routine": rname, "mode": "SKIPPED_NONEMPTY_OR_MISSING"})

    return out, report
