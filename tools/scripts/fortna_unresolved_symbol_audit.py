#!/usr/bin/env python3
"""Audit unresolved/unmapped Sawtooth gold-pack symbols against RUN evidence.

Inputs (allowed only):
  - exports/cp4-sawtooth-pass/parameter_map.json (+ provenance/sawtooth_generation)
  - tools/libraries/programs/Sawtooth_Merge_Program.L5X
  - workspace/cp4-run/RUN Fortna tables
  - exports/cp4-discovery/ (frozen)

Does NOT read finished PLC4. Does NOT classify by similar tag numbers alone.
Prefer RUN evidence over heuristics.
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

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402
from fortna_sawtooth_param import extract_ezpe_from_reserve_tm  # noqa: E402

RESOLUTIONS = (
    "RUN_EXPLICIT",
    "RUN_DERIVED_HIGH_CONFIDENCE",
    "GENERIC_LIBRARY_CONSTANT",
    "ENGINEER_CONFIGURED",
    "CONFIGURATION_REQUIRED",
    "GENERATION_NOT_SUPPORTED",
    "UNUSED_FOR_THIS_SITE",
    "UNKNOWN",
)

DEFAULT_PASS = ROOT / "exports" / "cp4-sawtooth-pass"
DEFAULT_PACK = ROOT / "tools" / "libraries" / "programs" / "Sawtooth_Merge_Program.L5X"
DEFAULT_RUN = ROOT / "workspace" / "cp4-run" / "RUN"
DEFAULT_DISC = ROOT / "exports" / "cp4-discovery"
DEFAULT_OUT = ROOT / "exports" / "cp4-semantics"

# Tables explicitly requested for reserve-eye / symbol search
SEARCH_TABLES = [
    "SawLane.asc",
    "SawMerge.asc",
    "HSSawLane.asc",
    "HSSawMerge.asc",
    "HSSawParm.asc",
    "HSSawState.asc",
    "HSSawSim.asc",
    "SawState.asc",
    "SawResvMode.asc",
    "Fulljam.asc",
    "Fullline.asc",
    "Jamcheck.asc",
    "Jamzones.asc",
    "CombinedJamZones.asc",
    "Conveyor.asc",
    "MergeInputs.asc",
    "Mtrchain.asc",
    "Errors.asc",
    "Encoders.asc",
    "Logic.asc",
    "Trigrset.asc",
    "timemenu.asc",
]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _clean(v: Any) -> str:
    return str(v or "").strip().strip('"')


def _valid(v: str) -> bool:
    return bool(v) and v.upper() not in {"", "N/A", "INVALID", "NONE", "~"}


def resolve_table(fortna: Path, name: str, machine: str = "ORNCCP4") -> Path | None:
    """Prefer controller overlay, else base .asc."""
    overlay = fortna / f"{name}.{machine}"
    base = fortna / name
    if overlay.is_file():
        return overlay
    if base.is_file():
        return base
    # Also accept bare name without .asc already
    return None


def load_run_indexes(run_dir: Path, machine: str = "ORNCCP4") -> dict[str, Any]:
    fortna = Path(run_dir) / "FORTNA"
    token_hits: dict[str, list[dict[str, str]]] = defaultdict(list)
    tables: dict[str, dict[str, Any]] = {}

    # Always scan Conveyor + requested tables
    names = list(SEARCH_TABLES)
    # also pick up any ORNCCP4 overlays for those stems
    for p in sorted(fortna.glob("*.asc*")):
        if p.name.lower().startswith(("old.", "backup.")):
            continue
        stem = p.name
        if stem.endswith(f".{machine}"):
            base = stem[: -(len(machine) + 1)]
        else:
            base = stem
        if base in SEARCH_TABLES or any(
            base.startswith(s.replace(".asc", "")) for s in SEARCH_TABLES
        ):
            if stem not in names and base not in names:
                names.append(stem)

    seen_paths: set[Path] = set()
    for name in names:
        path = resolve_table(fortna, name if name.endswith(".asc") or "." in name else f"{name}.asc", machine)
        if path is None:
            # try as-is
            cand = fortna / name
            path = cand if cand.is_file() else None
        if path is None or path in seen_paths:
            continue
        seen_paths.add(path)
        try:
            headers, rows = read_asc(path)
        except Exception as exc:  # noqa: BLE001
            tables[path.name] = {"error": str(exc), "path": str(path)}
            continue
        active = []
        for r in rows:
            # index all cell values that look like tokens
            for h, raw in r.items():
                val = _clean(raw)
                if not _valid(val):
                    continue
                if re.match(
                    r"^(?:P|PE|EZPE|VFD|ENC|M|MRG|tm|tmfc|SSV)?[A-Za-z]*\d[\w]*$",
                    val,
                    re.I,
                ) or val.startswith(("SAW_", "LANE_", "Enable_", "Use_", "MRG")):
                    token_hits[val.upper()].append(
                        {
                            "table": path.name,
                            "field": h,
                            "value": val,
                            "row_name": _clean(
                                r.get("Name")
                                or r.get("Desc")
                                or r.get("IO_Name")
                                or r.get("Sensor_Name")
                                or ""
                            ),
                        }
                    )
            # keep active named rows summary
            nm = _clean(r.get("Name") or r.get("Desc") or r.get("IO_Name") or "")
            if _valid(nm) and nm.lower() not in {"n/a"}:
                active.append({k: _clean(r.get(k)) for k in headers[:24]})
        tables[path.name] = {
            "path": str(path.relative_to(run_dir)).replace("\\", "/"),
            "headers": headers,
            "row_count": len(rows),
            "active_named_sample": active[:30],
        }

    return {"token_hits": dict(token_hits), "tables": tables}


def parse_pack_symbol_context(pack_path: Path, symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Find datatype + routine/instruction context for each symbol in the pack L5X."""
    text = pack_path.read_text(encoding="utf-8", errors="replace")
    # Tag declarations
    tag_meta: dict[str, dict[str, str]] = {}
    for m in re.finditer(
        r'<Tag\s+Name="([^"]+)"([^>]*)>',
        text,
    ):
        name = m.group(1)
        attrs = m.group(2)
        dt = re.search(r'DataType="([^"]+)"', attrs)
        tag_meta[name] = {
            "datatype": dt.group(1) if dt else "",
            "attrs": attrs.strip()[:200],
        }

    # Split by routines for context
    routine_blocks: list[tuple[str, str]] = []
    for m in re.finditer(
        r'<Routine\s+Name="([^"]+)"[^>]*>(.*?)</Routine>',
        text,
        re.S,
    ):
        routine_blocks.append((m.group(1), m.group(2)))

    out: dict[str, dict[str, Any]] = {}
    for sym in symbols:
        meta = tag_meta.get(sym, {})
        routines = []
        contexts = []
        for rname, body in routine_blocks:
            if sym not in body:
                continue
            routines.append(rname)
            # grab a few CDATA / line snippets containing the symbol
            for cm in re.finditer(r"<!\[CDATA\[(.*?)\]\]>", body, re.S):
                chunk = cm.group(1)
                if sym in chunk:
                    # compress whitespace
                    snip = re.sub(r"\s+", " ", chunk).strip()
                    if len(snip) > 240:
                        # center on symbol
                        i = snip.find(sym)
                        snip = snip[max(0, i - 80) : i + 160]
                    contexts.append({"routine": rname, "snippet": snip})
                    if len(contexts) >= 4:
                        break
            if len(contexts) >= 4:
                continue
            # ST Line text
            for lm in re.finditer(r"<Line[^>]*>(.*?)</Line>", body, re.S):
                chunk = lm.group(1)
                if sym in chunk:
                    snip = re.sub(r"\s+", " ", chunk).strip()
                    if len(snip) > 240:
                        i = snip.find(sym)
                        snip = snip[max(0, i - 80) : i + 160]
                    contexts.append({"routine": rname, "snippet": snip})
                    if len(contexts) >= 4:
                        break
        out[sym] = {
            "datatype": meta.get("datatype") or "",
            "declared_in_pack": sym in tag_meta,
            "routines": sorted(set(routines)),
            "instruction_context": contexts[:6],
        }
    return out


def classify_library_role(symbol: str, datatype: str, routines: list[str]) -> str:
    su = symbol.upper()
    if su.startswith("ENABLE_") or su.startswith("USE_"):
        return "feature_enable_gate"
    if su.startswith("EZPE"):
        return "lane_or_line_full_eye"
    if su.startswith("PE") and su.endswith("_J"):
        return "collector_jam_photoeye"
    if su.startswith("PE") and su.endswith("_I"):
        return "induct_or_intermediate_photoeye"
    if su.startswith("PE") and su.endswith("_P"):
        return "product_present_photoeye"
    if su.endswith("_CONV"):
        return "conveyor_udt"
    if su.endswith("_SAWMERGE_HMI"):
        return "sawtooth_hmi_faceplate"
    if su.startswith("MRG422_"):
        return "gapstore_or_unload_path_merge_struct"
    if su.startswith("MRG500_"):
        return "calibration_freeze_or_capture_helper"
    if su.startswith("MRG"):
        return "merge_control_struct"
    if datatype:
        return f"pack_tag:{datatype}"
    return "pack_symbol"


def likely_equipment(symbol: str, run_hits: list[dict[str, str]]) -> str:
    if run_hits:
        # Prefer Conveyor description-bearing hits
        for h in run_hits:
            if h.get("table", "").startswith("Conveyor"):
                return f"RUN device/token in {h['table']}.{h['field']} (row={h.get('row_name')})"
        h0 = run_hits[0]
        return f"RUN token in {h0['table']}.{h0['field']} (row={h0.get('row_name')})"
    su = symbol.upper()
    if su.startswith("ENABLE_") or su.startswith("USE_"):
        return "Logic feature gate (not a field device)"
    if su.startswith("MRG422"):
        return "Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family"
    if su.startswith("MRG500"):
        return "Gold-pack calibration/freeze helper family"
    if su.startswith("EZPE"):
        return "Full-eye photoeye (pack leftover if absent from RUN)"
    if su.endswith("_CONV"):
        return "Conveyor UDT instance in pack"
    if su.startswith("PE"):
        return "Photoeye UDT instance in pack"
    return "Unknown / pack-internal"


def candidate_tables_fields(
    symbol: str, run_hits: list[dict[str, str]]
) -> list[dict[str, str]]:
    out = []
    seen = set()
    for h in run_hits:
        key = (h["table"], h["field"], h.get("value"))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "table": h["table"],
                "field": h["field"],
                "value": h.get("value") or symbol,
                "row_name": h.get("row_name") or "",
            }
        )
    return out[:20]


def resolve_symbol(
    symbol: str,
    *,
    pass_reason: str,
    run_hits: list[dict[str, str]],
    lane_bindings: list[dict[str, Any]],
    discovery_tokens: set[str],
    pack_ctx: dict[str, Any],
) -> tuple[str, float, list[str], list[dict[str, Any]], list[str]]:
    """Return resolution, confidence, candidate_bindings, evidence, notes."""
    evidence: list[dict[str, Any]] = []
    notes: list[str] = []
    bindings: list[str] = []
    su = symbol.upper()

    for h in run_hits[:12]:
        evidence.append(
            {
                "kind": "RUN_TABLE_HIT",
                "table": h["table"],
                "field": h["field"],
                "value": h.get("value"),
                "row_name": h.get("row_name"),
            }
        )

    # Feature enables
    if su.startswith("ENABLE_") or su.startswith("USE_"):
        evidence.append(
            {
                "kind": "LIBRARY",
                "detail": f"Main/feature gate referenced in routines: {pack_ctx.get('routines')}",
            }
        )
        return (
            "ENGINEER_CONFIGURED",
            0.85,
            ["Set TRUE/FALSE per site feature (gap-store vs no-gap-store, reservation enable)"],
            evidence,
            ["Pass classified as feature enable — not a RUN field device"],
        )

    # Exact RUN token match
    if run_hits:
        # Conveyor equipment present
        conv_hits = [h for h in run_hits if h["table"].startswith("Conveyor")]
        saw_hits = [
            h
            for h in run_hits
            if h["table"].startswith(("SawLane", "SawMerge", "Fullline", "Fulljam", "Jam"))
        ]
        if conv_hits or saw_hits:
            # Is it one of the active sawtooth lane devices?
            lane_related = False
            for b in lane_bindings:
                for key in ("conveyor", "photoeye", "drive", "full_eye_ezpe"):
                    val = str(b.get(key) or "").upper()
                    if not val:
                        continue
                    if su == val or su == f"{val}_CONV" or su.startswith(val + "_"):
                        lane_related = True
                        bindings.append(
                            f"lane {b.get('lane_name')}: bind pack `{symbol}` ↔ RUN `{val}`"
                        )
            # Upstream/downstream of lane PE/drive?
            m = re.match(r"^(P|PE|EZPE|VFD)(\d+[A-Z]?)(.*)$", su)
            if m and not bindings:
                bindings.append(
                    f"Exact RUN token `{symbol}` exists — map pack tag to site IO/UDT of same name"
                )
            conf = 0.95 if (conv_hits and saw_hits) else 0.9
            return (
                "RUN_EXPLICIT",
                conf,
                bindings or [f"Use RUN token `{symbol}` as-is"],
                evidence,
                notes,
            )
        # Token exists somewhere but weak context
        return (
            "RUN_DERIVED_HIGH_CONFIDENCE",
            0.7,
            [f"Token appears in RUN tables: {sorted({h['table'] for h in run_hits})}"],
            evidence,
            notes,
        )

    # Discovery token set
    if su in discovery_tokens or any(su.startswith(t + "_") for t in discovery_tokens):
        evidence.append({"kind": "DISCOVERY", "detail": "Token related to discovery inventory"})
        return (
            "RUN_DERIVED_HIGH_CONFIDENCE",
            0.75,
            [f"Relate to discovery token family for `{symbol}`"],
            evidence,
            notes,
        )

    # MRG422 / MRG500 families — gold pack extras vs site MRG414 collector
    if su.startswith("MRG422_"):
        evidence.append(
            {
                "kind": "LIBRARY",
                "detail": "MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)",
            }
        )
        evidence.append(
            {
                "kind": "PASS",
                "detail": "Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422",
            }
        )
        return (
            "UNUSED_FOR_THIS_SITE",
            0.8,
            [
                "Do not rename MRG422→MRG414 by digit heuristic",
                "Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit",
            ],
            evidence,
            [
                "Digit-similarity to other merge numbers is NOT accepted as binding evidence",
            ],
        )

    if su.startswith("MRG500_"):
        evidence.append(
            {
                "kind": "LIBRARY",
                "detail": "MRG500_* used as calibration/freeze capture helpers in pack comments/routines",
            }
        )
        return (
            "GENERIC_LIBRARY_CONSTANT",
            0.75,
            ["Keep as pack helper tags unless site provides alternate calibration workflow"],
            evidence,
            notes,
        )

    # Pack conveyor/PE that is not in this site's RUN Conveyor inventory
    if re.match(r"^(P|PE|EZPE|VFD|ENC)\d", su):
        evidence.append(
            {
                "kind": "NEGATIVE_RUN",
                "detail": f"No exact token hit for `{symbol}` in scanned RUN Fortna tables",
            }
        )
        # Check if adjacent lane equipment — still do NOT bind by number alone
        notes.append(
            "No RUN exact match; refusing digit-similarity binding (policy)"
        )
        # Special: P418 is often collector companion in gold — still require RUN
        if su in {"P418_CONV", "PE418_I", "PE418_P"}:
            return (
                "CONFIGURATION_REQUIRED",
                0.55,
                [
                    "Gold collector companion devices — confirm whether site collector train includes them via Conveyor.asc before binding"
                ],
                evidence,
                notes,
            )
        return (
            "UNUSED_FOR_THIS_SITE",
            0.7,
            ["Omit or leave unmapped — no RUN equipment of this name"],
            evidence,
            notes,
        )

    if "feature enable" in (pass_reason or "").lower():
        return (
            "ENGINEER_CONFIGURED",
            0.8,
            [],
            evidence,
            notes,
        )

    return ("UNKNOWN", 0.3, [], evidence, notes or ["Insufficient evidence"])


def audit_reserve_eyes(
    run_idx: dict[str, Any],
    pmap: dict[str, Any],
    pack_path: Path,
) -> dict[str, Any]:
    """Dedicated investigation for LANE_0 EZPE217_F and LANE_4 EZPE212_F1 vs pack F2."""
    token_hits = run_idx["token_hits"]
    pack_text = pack_path.read_text(encoding="utf-8", errors="replace")
    pack_ezpe = sorted(set(re.findall(r"\bEZPE\d+[A-Z0-9_]*\b", pack_text)))

    def hits(*names: str) -> dict[str, list[dict[str, str]]]:
        return {n: token_hits.get(n.upper(), []) for n in names}

    lanes = {b.get("lane_name"): b for b in pmap.get("lane_bindings") or []}
    lane0 = lanes.get("LANE_0_P219") or {}
    lane4 = lanes.get("LANE_4_P214") or {}

    # Fullline rows via token index enrichment — also parse Fullline directly
    fortna = None
    fullline_rows = {}
    conveyor_rows = {}
    # find Conveyor/Fullline from tables paths
    for tname, meta in (run_idx.get("tables") or {}).items():
        if tname.startswith("Fullline.asc"):
            fortna = Path(ROOT / "workspace" / "cp4-run" / "RUN")  # noqa
            path = ROOT / "workspace" / "cp4-run" / "RUN" / meta["path"]
            _h, rows = read_asc(path)
            for r in rows:
                key = _clean(r.get("Desc") or r.get("Name") or "")
                if key:
                    fullline_rows[key] = {k: _clean(v) for k, v in r.items()}
        if tname.startswith("Conveyor.asc") and not tname.startswith("Conveyor.asc."):
            path = ROOT / "workspace" / "cp4-run" / "RUN" / meta["path"]
            _h, rows = read_asc(path)
            for r in rows:
                key = _clean(r.get("IO_Name") or r.get("Name") or "")
                if key:
                    conveyor_rows[key] = {
                        "IO_Name": key,
                        "General_Description": _clean(r.get("General_Description")),
                        "Type": _clean(r.get("Type")),
                        "Machine_Name": _clean(r.get("Machine_Name")),
                    }

    case_217 = {
        "lane": "LANE_0_P219",
        "run_reserve_tm": lane0.get("reserve_tm"),
        "extracted_ezpe": extract_ezpe_from_reserve_tm(str(lane0.get("reserve_tm") or "")),
        "pass_full_eye_ezpe": lane0.get("full_eye_ezpe"),
        "pass_provenance": lane0.get("full_eye_provenance"),
        "pass_note": lane0.get("full_eye_note"),
        "pack_has_extracted": "EZPE217_F" in pack_ezpe,
        "pack_ezpe_tags": pack_ezpe,
        "run_hits": hits("EZPE217_F", "tmfcEZPE217_F", "tmEZPE217_F", "PE217_F", "P217", "P219"),
        "fullline": fullline_rows.get("EZPE217_F"),
        "conveyor": conveyor_rows.get("EZPE217_F"),
        "pack_usage": (
            "RT_IO_Map_NoGapStore: IF EZPE127_F.Full THEN "
            "MRG414_astUNL_SlugBldCtrl[1].rQ1_SlugLength_Q := HMI Lane[1].ReleaseLengthFull "
            "ELSE ReleaseLength. This is slug-release-length selection when Use_GapStore_Belts=0 — "
            "not automatically the same mechanism as RUN SawLane.ReserveTM."
        ),
        "finding": (
            "RUN SawLane.ReserveTM explicitly names tmfcEZPE217_F for LANE_0_P219. "
            "Conveyor.asc and Fullline.asc both define EZPE217_F (FULL EYE ON P217 / Fullline→P217). "
            "Generic pack has NO EZPE217_F tag; it does have EZPE127_F used as Lane[1] full eye in "
            "RT_IO_Map_NoGapStore (different equipment — do NOT equate by digits). "
            "Pass marked CONFIGURATION REQUIRED because pack lacks counterpart — site symbol itself is RUN_EXPLICIT."
        ),
        "resolution_guidance": {
            "run_symbol_EZPE217_F": "RUN_EXPLICIT",
            "pack_binding": "CONFIGURATION_REQUIRED — add/bind EZPE217_F into site program; replace Lane[1] EZPE127_F.Full reference; do not substitute by digit rename alone",
            "do_not": "Do not rename EZPE127_F → EZPE217_F by digit similarity without confirming both ReserveTM and slug-length roles",
        },
        "confidence": 0.95,
    }

    case_212 = {
        "lane": "LANE_4_P214",
        "run_reserve_tm": lane4.get("reserve_tm"),
        "extracted_ezpe_from_reserve_tm": extract_ezpe_from_reserve_tm(
            str(lane4.get("reserve_tm") or "")
        ),
        "pass_full_eye_ezpe": lane4.get("full_eye_ezpe"),
        "pass_provenance": lane4.get("full_eye_provenance"),
        "pass_note": lane4.get("full_eye_note"),
        "pack_has_F1": "EZPE212_F1" in pack_ezpe,
        "pack_has_F2": "EZPE212_F2" in pack_ezpe,
        "pack_ezpe_tags": pack_ezpe,
        "run_hits": hits(
            "EZPE212_F1",
            "EZPE212_F2",
            "tmfcEZPE212_F1",
            "tmfcEZPE212_F2",
            "tmEZPE212_F1",
            "tmEZPE212_F2",
            "P212",
            "P214",
        ),
        "fullline_F1": fullline_rows.get("EZPE212_F1"),
        "fullline_F2": fullline_rows.get("EZPE212_F2"),
        "conveyor_F1": conveyor_rows.get("EZPE212_F1"),
        "conveyor_F2": conveyor_rows.get("EZPE212_F2"),
        "pack_usage": (
            "RT_IO_Map_NoGapStore: IF EZPE212_F2.Full THEN "
            "MRG414_astUNL_SlugBldCtrl[4].rQ1_SlugLength_Q := HMI Lane[4].ReleaseLengthFull "
            "ELSE ReleaseLength. Pack role here is slug-release-length selection (no gap-store path)."
        ),
        "finding": (
            "CONFLICT — do not auto-resolve. "
            "SawLane LANE_4_P214.ReserveTM=tmfcEZPE212_F1 (explicit reservation timer → EZPE212_F1). "
            "Fullline associates EZPE212_F1.Conveyor_Name=P212 and EZPE212_F2.Conveyor_Name=P214. "
            "Conveyor descriptions: F1='FULL EYE DETECTION ON P212'; F2='FULL EYE ON P212 DOWNSTREAM OF P308 MERGE'. "
            "Errors: F1='LANE FULL AT BIN MOD A ACCUM'; F2='LANE 1/2 FULL AT BIN MOD A ACCUM'. "
            "Generic pack declares/uses EZPE212_F2.Full for Lane[4] slug length in RT_IO_Map_NoGapStore. "
            "Prior pass fuzzy-mapped F1→F2 (RUN_DERIVED) — ReserveTM identity and pack Full-eye role are not proven to be the same sensor."
        ),
        "resolution_guidance": {
            "reserve_timer_symbol": "RUN_EXPLICIT tmfcEZPE212_F1 / EZPE212_F1",
            "pack_slug_length_full_eye": "EZPE212_F2 (library)",
            "fullline_conveyor_for_F2": "P214 (sawtooth lane conveyor name)",
            "fullline_conveyor_for_F1": "P212",
            "recommended_audit_resolution": "CONFIGURATION_REQUIRED",
            "do_not": "Do not rename F1↔F2 to force pack match; engineer must confirm ReserveTM eye vs slug-length Full eye (may differ)",
        },
        "confidence": 0.9,
    }

    return {
        "generated_at": _ts(),
        "pack_ezpe_tags": pack_ezpe,
        "LANE_0_ReserveTM_EZPE217_F": case_217,
        "LANE_4_ReserveTM_EZPE212_F1_vs_pack_F2": case_212,
        "other_lane_reserve_eyes": [
            {
                "lane": b.get("lane_name"),
                "reserve_tm": b.get("reserve_tm"),
                "full_eye_ezpe": b.get("full_eye_ezpe"),
                "provenance": b.get("full_eye_provenance"),
                "note": b.get("full_eye_note"),
                "pack_has": (b.get("full_eye_ezpe") or "") in pack_ezpe,
            }
            for b in pmap.get("lane_bindings") or []
        ],
    }


def build_merge_signal_map_seed(
    pmap: dict[str, Any],
    discovery: dict[str, Any],
    reserve_audit: dict[str, Any],
) -> dict[str, Any]:
    merge = (discovery.get("sawtooth") or {}).get("merges") or pmap
    # discovery loaded separately — handle both shapes
    return {
        "generated_at": _ts(),
        "status": "partial_seed",
        "merge": {
            "name": pmap.get("merge_name"),
            "motor_io": pmap.get("motor_io"),
            "reservation": pmap.get("reservation"),
            "lane_enable_delay_tm": pmap.get("lane_enable_delay_tm"),
            "slice_seconds": pmap.get("slice_seconds_merge"),
            "collector_digits": pmap.get("collector_digits"),
            "provenance": "RUN_EXPLICIT",
        },
        "lanes": [
            {
                "lane_name": b.get("lane_name"),
                "lane_index": b.get("lane_index"),
                "conveyor": b.get("conveyor"),
                "photoeye": b.get("photoeye"),
                "drive": b.get("drive"),
                "approach": b.get("approach"),
                "collision": b.get("collision"),
                "lane_input": b.get("lane_input"),
                "slice_seconds": b.get("slice_seconds"),
                "reserve_seconds": b.get("reserve_seconds"),
                "reserve_tm": b.get("reserve_tm"),
                "full_eye_ezpe_pass": b.get("full_eye_ezpe"),
                "full_eye_note": b.get("full_eye_note"),
                "signals_confidence": {
                    "photoeye": "RUN_EXPLICIT",
                    "drive": "RUN_EXPLICIT",
                    "reserve_tm": "RUN_EXPLICIT",
                    "full_eye_pack_bind": b.get("full_eye_provenance"),
                },
            }
            for b in pmap.get("lane_bindings") or []
        ],
        "reserve_eye_open_items": [
            "LANE_0: bind EZPE217_F (RUN_EXPLICIT device; missing from pack)",
            "LANE_4: confirm EZPE212_F1 (ReserveTM) vs EZPE212_F2 (pack/Fullline→P214) — CONFIGURATION_REQUIRED",
        ],
        "encoder_notes_seed": [
            {
                "encoder": e.get("encoder"),
                "enable": e.get("enable"),
                "ticks_per_foot": e.get("ticks_per_foot"),
                "target_fpm": e.get("target_fpm"),
                "jamzone": e.get("jamzone"),
                "provenance": e.get("provenance"),
            }
            for e in pmap.get("encoder_bindings") or []
        ],
        "vfd_notes_seed": {
            "merge_motor_io": pmap.get("motor_io"),
            "lane_drives": [
                {"lane": b.get("lane_name"), "drive": b.get("drive")}
                for b in pmap.get("lane_bindings") or []
            ],
            "note": "Full shared-VFD map lives in discovery vfd.json / pass vfd_generation.json",
        },
    }


def load_discovery_tokens(disc_dir: Path) -> set[str]:
    tokens: set[str] = set()
    for name in ("sawtooth.json", "vfd.json", "encoders.json", "equipment.json", "site_model.json"):
        path = disc_dir / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        blob = json.dumps(data)
        for m in re.findall(r"\b(?:P|PE|EZPE|VFD|ENC)\d+[A-Z0-9_]*\b", blob):
            tokens.add(m.upper())
    return tokens


def run_audit(
    *,
    pass_dir: Path,
    pack_path: Path,
    run_dir: Path,
    disc_dir: Path,
    out_dir: Path,
    machine: str = "ORNCCP4",
) -> dict[str, Any]:
    pmap = json.loads((pass_dir / "parameter_map.json").read_text(encoding="utf-8"))
    unmapped = list(pmap.get("unmapped_pack_symbols") or [])
    symbols = [u["symbol"] for u in unmapped]

    # Also include critical reserve-eye symbols not in the 69 list
    extras: list[dict[str, Any]] = []
    for b in pmap.get("lane_bindings") or []:
        ez = b.get("full_eye_ezpe")
        if not ez or ez in symbols or any(e["symbol"] == ez for e in extras):
            continue
        if b.get("full_eye_provenance") != "RUN_EXPLICIT":
            extras.append(
                {
                    "symbol": ez,
                    "classification": b.get("full_eye_provenance"),
                    "reason": b.get("full_eye_note") or "lane full-eye open item",
                    "extra_from_lane": b.get("lane_name"),
                }
            )
    # Always force-include EZPE212_F1 extracted from ReserveTM even if pass substituted F2
    if "EZPE212_F1" not in symbols and not any(e["symbol"] == "EZPE212_F1" for e in extras):
        extras.append(
            {
                "symbol": "EZPE212_F1",
                "classification": "CONFIGURATION REQUIRED",
                "reason": "LANE_4 ReserveTM extracts EZPE212_F1; pack/pass used EZPE212_F2",
                "extra_from_lane": "LANE_4_P214",
            }
        )
    if "EZPE217_F" not in symbols and not any(e["symbol"] == "EZPE217_F" for e in extras):
        extras.append(
            {
                "symbol": "EZPE217_F",
                "classification": "CONFIGURATION REQUIRED",
                "reason": "LANE_0 ReserveTM=tmfcEZPE217_F; no pack counterpart",
                "extra_from_lane": "LANE_0_P219",
            }
        )

    all_items = unmapped + extras
    all_syms = [i["symbol"] for i in all_items]

    print("Indexing RUN tables…")
    run_idx = load_run_indexes(run_dir, machine=machine)
    print("Parsing pack symbol context…")
    pack_ctx = parse_pack_symbol_context(pack_path, all_syms)
    disc_tokens = load_discovery_tokens(disc_dir)

    audited = []
    histogram: dict[str, int] = defaultdict(int)

    for item in all_items:
        sym = item["symbol"]
        ctx = pack_ctx.get(sym) or {}
        hits = (run_idx["token_hits"].get(sym.upper()) or [])[:]
        # also search without _Conv suffix etc already exact
        role = classify_library_role(sym, ctx.get("datatype") or "", ctx.get("routines") or [])
        equip = likely_equipment(sym, hits)
        tables = candidate_tables_fields(sym, hits)
        resolution, conf, bindings, evidence, notes = resolve_symbol(
            sym,
            pass_reason=item.get("reason") or "",
            run_hits=hits,
            lane_bindings=pmap.get("lane_bindings") or [],
            discovery_tokens=disc_tokens,
            pack_ctx=ctx,
        )
        # Special overrides for reserve eyes (prefer RUN evidence)
        if sym == "EZPE217_F":
            resolution = "RUN_EXPLICIT"
            conf = 0.95
            bindings = [
                "Add pack tag EZPE217_F (PE_UDT) and bind to site full eye on P217",
                "Wire reservation logic to tmfcEZPE217_F / EZPE217_F.Full — do not use EZPE127_F",
            ]
            notes = [
                "Symbol is RUN_EXPLICIT; pack absence makes emit CONFIGURATION_REQUIRED until tag added"
            ]
            evidence.append(
                {
                    "kind": "RUN_EXPLICIT",
                    "detail": "SawLane.LANE_0_P219.ReserveTM=tmfcEZPE217_F; Conveyor+Fullline define EZPE217_F",
                }
            )
        if sym == "EZPE212_F1":
            resolution = "RUN_EXPLICIT"
            conf = 0.95
            bindings = [
                "ReserveTM points at tmfcEZPE212_F1 — keep as reservation timer identity",
                "Pack currently references EZPE212_F2 — engineer must confirm which eye is Sawtooth full/reserve",
            ]
            notes = [
                "Presence of F1 in RUN is explicit; functional equivalence to pack F2 is NOT established",
                "Sawtooth lane-full role vs Fullline/line-full role remains CONFIGURATION_REQUIRED",
            ]
        if sym == "EZPE212_F2":
            # Device exists in RUN; do not treat prior pass F1→F2 fuzzy map as proven lane reserve bind
            resolution = "RUN_EXPLICIT"
            conf = 0.9
            bindings = [
                "RUN defines EZPE212_F2 (Fullline→P214; Conveyor 'FULL EYE ON P212 DOWNSTREAM OF P308 MERGE')",
                "Pack SR_LaneCntrl uses EZPE212_F2.Full — confirm whether site Sawtooth reserve should stay on F2 or move to F1 per ReserveTM",
            ]
            notes = [
                "Device token is RUN_EXPLICIT",
                "Equivalence to LANE_4 ReserveTM tmfcEZPE212_F1 is NOT proven — open CONFIGURATION_REQUIRED decision",
            ]
            evidence.append(
                {
                    "kind": "CONFLICT",
                    "detail": "SawLane.ReserveTM=tmfcEZPE212_F1 vs pack/Fullline-P214 EZPE212_F2",
                }
            )
        if sym == "EZPE127_F":
            # Pack leftover; no RUN
            if not hits:
                resolution = "UNUSED_FOR_THIS_SITE"
                conf = 0.85
                bindings = [
                    "Do not map to EZPE217_F by digit similarity",
                    "Site LANE_0 full eye is EZPE217_F per ReserveTM",
                ]
                notes = ["Gold-pack full eye without RUN device of same name"]

        # P*_Conv that exist in RUN for lane neighbors
        if re.match(r"^P\d+[A-Z]?_Conv$", sym, re.I):
            base = sym[: -len("_Conv")]
            base_hits = run_idx["token_hits"].get(base.upper()) or []
            if base_hits and not hits:
                # conveyor name exists without _Conv suffix
                evidence.append(
                    {
                        "kind": "RUN_EXPLICIT",
                        "detail": f"Conveyor/token `{base}` exists in RUN; pack UDT is `{sym}`",
                    }
                )
                for h in base_hits[:8]:
                    evidence.append(
                        {
                            "kind": "RUN_TABLE_HIT",
                            "table": h["table"],
                            "field": h["field"],
                            "value": h.get("value"),
                            "row_name": h.get("row_name"),
                        }
                    )
                tables = candidate_tables_fields(base, base_hits)
                # Is it an active sawtooth lane conveyor or explicit neighbor?
                lane_convs = {
                    str(b.get("conveyor") or "").upper()
                    for b in pmap.get("lane_bindings") or []
                }
                if base.upper() in lane_convs:
                    resolution = "RUN_EXPLICIT"
                    conf = 0.95
                    bindings = [f"Pack `{sym}` ↔ RUN conveyor `{base}` (active sawtooth lane)"]
                else:
                    # Neighbor may still be RUN_EXPLICIT equipment
                    resolution = "RUN_EXPLICIT"
                    conf = 0.9
                    bindings = [
                        f"Pack `{sym}` ↔ RUN conveyor `{base}` (present in RUN; confirm sawtooth role)"
                    ]
                equip = likely_equipment(base, base_hits)

        if re.match(r"^PE\d+[A-Z0-9_]*$", sym, re.I) and not hits:
            # already handled unused
            pass

        assert resolution in RESOLUTIONS, resolution
        histogram[resolution] += 1
        audited.append(
            {
                "symbol": sym,
                "datatype": ctx.get("datatype") or "",
                "declared_in_pack": ctx.get("declared_in_pack", False),
                "routines": ctx.get("routines") or [],
                "instruction_context": ctx.get("instruction_context") or [],
                "generic_library_role": role,
                "likely_equipment_or_function": equip,
                "candidate_run_tables_fields": tables,
                "candidate_bindings": bindings,
                "confidence": conf,
                "resolution": resolution,
                "evidence": evidence,
                "pass_classification": item.get("classification"),
                "pass_reason": item.get("reason"),
                "extra_from_lane": item.get("extra_from_lane"),
                "notes": notes,
            }
        )

    reserve = audit_reserve_eyes(run_idx, pmap, pack_path)
    disc_saw = {}
    if (disc_dir / "sawtooth.json").is_file():
        disc_saw = json.loads((disc_dir / "sawtooth.json").read_text(encoding="utf-8"))
    merge_seed = build_merge_signal_map_seed(pmap, {"sawtooth": disc_saw}, reserve)

    payload = {
        "generated_at": _ts(),
        "finished_plc4_used": False,
        "source_pass": str(pass_dir),
        "pack": str(pack_path),
        "run_dir": str(run_dir),
        "counts": {
            "unmapped_from_pass": len(unmapped),
            "extras_reserve_eyes": len(extras),
            "total_audited": len(audited),
        },
        "resolution_histogram": dict(sorted(histogram.items())),
        "policy": {
            "no_digit_similarity_binding": True,
            "prefer_run_evidence": True,
            "allowed_resolutions": list(RESOLUTIONS),
        },
        "symbols": audited,
        "reserve_eye_summary": {
            "EZPE217_F": reserve["LANE_0_ReserveTM_EZPE217_F"]["resolution_guidance"],
            "EZPE212_F1_vs_F2": reserve["LANE_4_ReserveTM_EZPE212_F1_vs_pack_F2"][
                "resolution_guidance"
            ],
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "unresolved_symbol_audit.json", payload)
    (out_dir / "unresolved_symbol_audit.md").write_text(
        audit_to_markdown(payload), encoding="utf-8"
    )
    _write_json(out_dir / "reserve_eye_analysis.json", reserve)
    (out_dir / "reserve_eye_analysis.md").write_text(
        reserve_to_markdown(reserve), encoding="utf-8"
    )
    _write_json(out_dir / "merge_signal_map.json", merge_seed)
    # encoder/vfd start notes
    notes = {
        "generated_at": _ts(),
        "encoders": merge_seed.get("encoder_notes_seed"),
        "vfd": merge_seed.get("vfd_notes_seed"),
        "status": "seed",
    }
    _write_json(out_dir / "encoder_vfd_notes_seed.json", notes)
    return payload


def audit_to_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Unresolved / Unmapped Sawtooth Symbol Audit")
    lines.append("")
    lines.append(f"Generated: `{payload.get('generated_at')}`")
    lines.append(f"Finished PLC4 used: **{payload.get('finished_plc4_used')}**")
    counts = payload.get("counts") or {}
    lines.append(
        f"Audited: **{counts.get('total_audited')}** "
        f"(pass unmapped {counts.get('unmapped_from_pass')}, "
        f"reserve-eye extras {counts.get('extras_reserve_eyes')})"
    )
    lines.append("")
    lines.append("## Resolution histogram")
    lines.append("")
    for k, v in (payload.get("resolution_histogram") or {}).items():
        lines.append(f"- `{k}`: **{v}**")
    lines.append("")
    lines.append("## Policy")
    lines.append("")
    lines.append("- Prefer RUN table evidence over heuristics")
    lines.append("- Do **not** bind by similar tag numbers alone")
    lines.append("- Finished PLC4 not consulted")
    lines.append("")
    lines.append("## Symbols")
    lines.append("")
    for s in payload.get("symbols") or []:
        lines.append(f"### `{s['symbol']}`")
        lines.append("")
        lines.append(f"- **Datatype:** `{s.get('datatype') or '—'}`")
        lines.append(
            f"- **Routines:** {', '.join(f'`{r}`' for r in s.get('routines') or []) or '—'}"
        )
        ctx = s.get("instruction_context") or []
        if ctx:
            lines.append("- **Instruction/context:**")
            for c in ctx[:3]:
                lines.append(f"  - `{c.get('routine')}`: `{c.get('snippet')}`")
        lines.append(f"- **Generic-library role:** {s.get('generic_library_role')}")
        lines.append(
            f"- **Likely equipment/function:** {s.get('likely_equipment_or_function')}"
        )
        ctf = s.get("candidate_run_tables_fields") or []
        if ctf:
            lines.append("- **Candidate RUN table(s)/field(s):**")
            for t in ctf[:8]:
                lines.append(
                    f"  - `{t.get('table')}`.`{t.get('field')}` "
                    f"= `{t.get('value')}` (row `{t.get('row_name')}`)"
                )
        else:
            lines.append("- **Candidate RUN table(s)/field(s):** —")
        binds = s.get("candidate_bindings") or []
        lines.append(
            "- **Candidate binding(s):** "
            + ("; ".join(binds) if binds else "—")
        )
        lines.append(f"- **Confidence:** {s.get('confidence')}")
        lines.append(f"- **Resolution:** `{s.get('resolution')}`")
        ev = s.get("evidence") or []
        if ev:
            lines.append("- **Evidence:**")
            for e in ev[:8]:
                if e.get("kind") == "RUN_TABLE_HIT":
                    lines.append(
                        f"  - RUN `{e.get('table')}`.`{e.get('field')}` "
                        f"= `{e.get('value')}` (row `{e.get('row_name')}`)"
                    )
                else:
                    lines.append(f"  - {e.get('kind')}: {e.get('detail') or e}")
        if s.get("notes"):
            lines.append(f"- **Notes:** {'; '.join(s['notes'])}")
        lines.append("")
    return "\n".join(lines)


def reserve_to_markdown(reserve: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Reserve Eye Analysis (Sawtooth)")
    lines.append("")
    lines.append(f"Generated: `{reserve.get('generated_at')}`")
    lines.append("")
    lines.append(
        f"Pack EZPE tags: {', '.join(f'`{x}`' for x in reserve.get('pack_ezpe_tags') or [])}"
    )
    lines.append("")
    c217 = reserve["LANE_0_ReserveTM_EZPE217_F"]
    lines.append("## LANE_0_P219 — ReserveTM → EZPE217_F (no pack counterpart)")
    lines.append("")
    lines.append(f"- **ReserveTM:** `{c217.get('run_reserve_tm')}`")
    lines.append(f"- **Extracted:** `{c217.get('extracted_ezpe')}`")
    lines.append(f"- **Pass full_eye_ezpe:** `{c217.get('pass_full_eye_ezpe')}` ({c217.get('pass_provenance')})")
    lines.append(f"- **Pack has EZPE217_F:** {c217.get('pack_has_extracted')}")
    lines.append(f"- **Conveyor.asc:** `{c217.get('conveyor')}`")
    lines.append(f"- **Fullline.asc:** `{c217.get('fullline')}`")
    if c217.get("pack_usage"):
        lines.append(f"- **Pack usage:** {c217.get('pack_usage')}")
    lines.append("")
    lines.append("### RUN hits")
    for name, hs in (c217.get("run_hits") or {}).items():
        if not hs:
            lines.append(f"- `{name}`: none")
            continue
        lines.append(f"- `{name}`:")
        for h in hs[:6]:
            lines.append(
                f"  - `{h.get('table')}`.`{h.get('field')}` (row `{h.get('row_name')}`)"
            )
    lines.append("")
    lines.append(f"### Finding")
    lines.append("")
    lines.append(c217.get("finding") or "")
    lines.append("")
    lines.append("### Resolution guidance")
    lines.append("")
    for k, v in (c217.get("resolution_guidance") or {}).items():
        lines.append(f"- **{k}:** {v}")
    lines.append(f"- **Confidence:** {c217.get('confidence')}")
    lines.append("")

    c212 = reserve["LANE_4_ReserveTM_EZPE212_F1_vs_pack_F2"]
    lines.append("## LANE_4_P214 — ReserveTM EZPE212_F1 vs pack EZPE212_F2")
    lines.append("")
    lines.append(f"- **ReserveTM:** `{c212.get('run_reserve_tm')}`")
    lines.append(
        f"- **Extracted from ReserveTM:** `{c212.get('extracted_ezpe_from_reserve_tm')}`"
    )
    lines.append(
        f"- **Pass full_eye_ezpe:** `{c212.get('pass_full_eye_ezpe')}` ({c212.get('pass_provenance')})"
    )
    lines.append(f"- **Pack has F1:** {c212.get('pack_has_F1')} · **F2:** {c212.get('pack_has_F2')}")
    lines.append(f"- **Fullline F1:** `{c212.get('fullline_F1')}`")
    lines.append(f"- **Fullline F2:** `{c212.get('fullline_F2')}`")
    lines.append(f"- **Conveyor F1:** `{c212.get('conveyor_F1')}`")
    lines.append(f"- **Conveyor F2:** `{c212.get('conveyor_F2')}`")
    if c212.get("pack_usage"):
        lines.append(f"- **Pack usage:** {c212.get('pack_usage')}")
    lines.append("")
    lines.append("### RUN hits")
    for name, hs in (c212.get("run_hits") or {}).items():
        if not hs:
            lines.append(f"- `{name}`: none")
            continue
        lines.append(f"- `{name}`:")
        for h in hs[:6]:
            lines.append(
                f"  - `{h.get('table')}`.`{h.get('field')}` (row `{h.get('row_name')}`)"
            )
    lines.append("")
    lines.append("### Finding")
    lines.append("")
    lines.append(c212.get("finding") or "")
    lines.append("")
    lines.append("### Resolution guidance")
    lines.append("")
    for k, v in (c212.get("resolution_guidance") or {}).items():
        lines.append(f"- **{k}:** {v}")
    lines.append(f"- **Confidence:** {c212.get('confidence')}")
    lines.append("")
    lines.append("## Other lane reserve eyes")
    lines.append("")
    for row in reserve.get("other_lane_reserve_eyes") or []:
        lines.append(
            f"- `{row.get('lane')}`: ReserveTM=`{row.get('reserve_tm')}` → "
            f"`{row.get('full_eye_ezpe')}` ({row.get('provenance')}); "
            f"pack_has={row.get('pack_has')}"
        )
    lines.append("")
    lines.append(
        "Searched: SawLane, SawMerge, HSSaw*, Fulljam, Fullline, Jamcheck, Jamzones, "
        "CombinedJamZones, Conveyor, MergeInputs, Mtrchain, Errors, Logic, Trigrset."
    )
    lines.append("")
    lines.append("No guessing / no rename-to-match-library performed.")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pass-dir", type=Path, default=DEFAULT_PASS)
    ap.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--discovery", type=Path, default=DEFAULT_DISC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--machine", default="ORNCCP4")
    args = ap.parse_args(argv)
    payload = run_audit(
        pass_dir=args.pass_dir,
        pack_path=args.pack,
        run_dir=args.run_dir,
        disc_dir=args.discovery,
        out_dir=args.out,
        machine=args.machine,
    )
    print(
        json.dumps(
            {
                "total_audited": payload["counts"]["total_audited"],
                "histogram": payload["resolution_histogram"],
                "out": str(args.out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
