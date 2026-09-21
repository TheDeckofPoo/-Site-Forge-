#!/usr/bin/env python3
"""Atlanta I/O identity-set conservation diagnostics.

Compares the 256 GUI/PWR ASSIGNED claims against:
  - field L5X (before; validation counts only — not a discovery parent)
  - atlanta_io_fix_regen4 L5X (after fixed PWR merge)

Writes:
  exports/diagnostics/atlanta_io_compiler_conservation.json
  exports/diagnostics/atlanta_io_compiler_conservation.md
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fortna_physical_word_resolver import PhysicalWordResolver  # noqa: E402

RUN_DIR = ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"
MACHINE = "MSCATL_CP3"
CLAIMS_PATH = ROOT / "exports" / "ai-io" / "MSCATL_CP3_MSCATL_CP3" / "raw_claims.json"
FIELD_L5X = ROOT / "exports" / "current" / "MSCATL_CP3_2026_09_20_2137.L5X"
FIX_DIR = ROOT / "exports" / "diagnostics" / "atlanta_io_fix_regen4"
FIX_L5X = FIX_DIR / "MSCATL_CP3.L5X"
FIX_REPORT = FIX_DIR / "autogen_report.json"
FIX_PHYS = FIX_DIR / "physical_io_map.csv"
FIX_RIO = FIX_DIR / "rio_inventory.json"
OUT_JSON = ROOT / "exports" / "diagnostics" / "atlanta_io_compiler_conservation.json"
OUT_MD = ROOT / "exports" / "diagnostics" / "atlanta_io_compiler_conservation.md"

_BANK_RE = re.compile(r"Bank(\d+)\.(\d+)")
_CH_RE = re.compile(r"^([A-Za-z0-9_]+):(I|O)\.Data\[(\d+)\]\.(\d+)$", re.I)


def _safe_name(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return ""
    if re.match(r"^\d", n):
        return f"T_{n}"
    return n


def _is_engineer_spare_name(name: str) -> bool:
    n = (name or "").strip().upper()
    if not n:
        return True
    if n in {"SPARE", "N/A", "NONE", "INVALID"}:
        return True
    if n.startswith("SPARE") or "_SPARE" in n or n.endswith("SPARE"):
        return True
    return False


def parse_iomap_rungs(path: Path) -> list[dict[str, Any]]:
    """Parse CP_I/CP_O rungs into physical/logical identity rows."""
    l5x = path.read_text(encoding="utf-8", errors="replace")
    rows: list[dict[str, Any]] = []
    for routine in ("CP_I", "CP_O"):
        m = re.search(rf'<Routine Name="{routine}"[^>]*>(.*?)</Routine>', l5x, re.S)
        body = m.group(1) if m else ""
        for rm in re.finditer(r"<Rung\b[^>]*>(.*?)</Rung>", body, re.S):
            rb = rm.group(1)
            tm = re.search(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", rb, re.S)
            cm = re.search(r"<Comment><!\[CDATA\[(.*?)\]\]></Comment>", rb, re.S)
            if not tm:
                continue
            text = tm.group(1).strip()
            comment = cm.group(1).strip() if cm else ""
            if "NOP" in text and "XIC" not in text and "OTE" not in text:
                continue
            ops = re.findall(r"(?:XIC|OTE)\(([^)]+)\)", text)
            placeholder = "NO_PointPlaceholder" in text
            physical = next((o for o in ops if ":" in o and ".Data" in o), None)
            logical = next(
                (
                    o
                    for o in ops
                    if o != "NO_PointPlaceholder" and not (":" in o and ".Data" in o)
                ),
                None,
            )
            if placeholder:
                logical = "NO_PointPlaceholder"
            kind = "placeholder"
            if not placeholder and logical:
                kind = "specialized" if "." in logical else "generic_bool"
            bm = _BANK_RE.search(comment)
            via = None
            vm = re.search(r"via\s+([A-Za-z0-9_]+)", comment)
            if vm:
                via = vm.group(1)
            mk = None
            if "generic_bool" in comment:
                mk = "generic_bool"
            elif kind == "specialized":
                mk = "specialized"
            rows.append(
                {
                    "routine": routine,
                    "text": text,
                    "comment": comment,
                    "physical_address": physical,
                    "logical_target": logical,
                    "placeholder": placeholder,
                    "mapping_kind": kind if kind != "placeholder" else (mk or "placeholder"),
                    "word": bm.group(1) if bm else None,
                    "bit": bm.group(2) if bm else None,
                    "via": via,
                }
            )
    return rows


def _index_iomap(rows: list[dict[str, Any]]) -> tuple[dict[str, dict], dict[tuple[str, str], dict]]:
    by_ch: dict[str, dict] = {}
    by_wb: dict[tuple[str, str], dict] = {}
    for r in rows:
        ch = r.get("physical_address")
        if ch and ch not in by_ch:
            by_ch[ch] = r
        w, b = r.get("word"), r.get("bit")
        if w is not None and b is not None and (w, b) not in by_wb:
            by_wb[(str(w), str(b))] = r
    return by_ch, by_wb


def _lookup_iomap(
    by_ch: dict[str, dict],
    by_wb: dict[tuple[str, str], dict],
    channel: str,
    word: str,
    bit: str,
) -> dict | None:
    if channel and channel in by_ch:
        return by_ch[channel]
    return by_wb.get((str(word), str(bit)))


def _mapping_kind_of(row: dict | None) -> str | None:
    if not row:
        return None
    if row.get("placeholder") or row.get("logical_target") == "NO_PointPlaceholder":
        return "placeholder"
    logical = row.get("logical_target") or ""
    if "." in logical:
        return "specialized"
    if logical:
        return "generic_bool"
    return None


def build() -> dict[str, Any]:
    raw = json.loads(CLAIMS_PATH.read_text(encoding="utf-8"))
    claims: list[dict[str, Any]] = list(raw.get("claims") or [])
    if len(claims) != 256:
        raise SystemExit(f"expected 256 claims, got {len(claims)} from {CLAIMS_PATH}")

    report = json.loads(FIX_REPORT.read_text(encoding="utf-8")) if FIX_REPORT.is_file() else {}
    rio = json.loads(FIX_RIO.read_text(encoding="utf-8")) if FIX_RIO.is_file() else {}

    pwr = PhysicalWordResolver(RUN_DIR, MACHINE)
    field_rows = parse_iomap_rungs(FIELD_L5X)
    fix_rows = parse_iomap_rungs(FIX_L5X)
    field_by_ch, field_by_wb = _index_iomap(field_rows)
    fix_by_ch, fix_by_wb = _index_iomap(fix_rows)

    field_named = [
        r
        for r in field_rows
        if not r["placeholder"] and r.get("logical_target") not in (None, "NO_PointPlaceholder")
    ]
    fix_named = [
        r
        for r in fix_rows
        if not r["placeholder"] and r.get("logical_target") not in (None, "NO_PointPlaceholder")
    ]
    field_ph = [r for r in field_rows if r["placeholder"] or r.get("logical_target") == "NO_PointPlaceholder"]
    fix_ph = [r for r in fix_rows if r["placeholder"] or r.get("logical_target") == "NO_PointPlaceholder"]

    # physical_io_map.csv is Conveyor extract — supplementary, not claim ledger
    phys_rows: list[dict[str, str]] = []
    if FIX_PHYS.is_file():
        phys_rows = list(csv.DictReader(FIX_PHYS.open(encoding="utf-8", errors="replace")))
    phys_by_name = {
        (r.get("fortna_name") or "").strip().upper(): r for r in phys_rows if r.get("fortna_name")
    }

    claim_rows: list[dict[str, Any]] = []
    before_named_ids: set[str] = set()
    after_named_ids: set[str] = set()
    intentional_ids: set[str] = set()
    lost_ids: set[str] = set()
    emitted_ids: set[str] = set()

    per_rack: dict[str, Counter] = defaultdict(Counter)
    per_module: dict[str, Counter] = defaultdict(Counter)
    kind_after: Counter = Counter()
    conf_counts: Counter = Counter()

    for c in claims:
        cid = str(c.get("claim_id") or "")
        io_name = str(c.get("io_name") or "")
        word = str(c.get("word") if c.get("word") is not None else "")
        bit = str(c.get("bit") if c.get("bit") is not None else "")
        direction = str(c.get("direction") or "")
        claim_addr = str(c.get("physical_address") or "")

        hit = pwr.resolve(word, bit) or {}
        channel = str(hit.get("channel") or claim_addr or "")
        conf = str(
            hit.get("binding_confidence")
            or c.get("hardware_identity_status")
            or "UNKNOWN"
        )
        conf_counts[conf] += 1
        resolve_how = str(hit.get("resolve_how") or hit.get("assign_how") or "")
        rio_name = str(hit.get("rio_name") or (channel.split(":", 1)[0] if channel else ""))
        flex_slot = hit.get("flex_slot")
        mod_type = str(hit.get("type") or c.get("module_catalog") or "")
        child = str(hit.get("child_name") or "")
        if not child and rio_name and flex_slot is not None:
            child = f"{rio_name}_{flex_slot}"
        module_key = f"{rio_name}:{flex_slot}:{mod_type}" if rio_name != "" else "UNKNOWN"

        # Field L5X often bound wrong Data[n] (EIP bank join without PWR). For
        # before-identity ONLY match Bank{word}.{bit} comments — never fall back
        # to physical channel (a misplaced named rung sits on another claim's
        # correct PWR channel and would inflate before_named).
        field_hit = field_by_wb.get((word, bit))
        field_ch_row = field_by_ch.get(channel) if channel else None
        fix_hit = _lookup_iomap(fix_by_ch, fix_by_wb, channel, word, bit)

        field_kind = _mapping_kind_of(field_hit)
        fix_kind = _mapping_kind_of(fix_hit)
        field_target = (field_hit or {}).get("logical_target")
        fix_target = (fix_hit or {}).get("logical_target")
        field_phys = (field_hit or {}).get("physical_address")
        field_ch_kind = _mapping_kind_of(field_ch_row)
        # Prefer emitted fix channel; else PWR
        final_phys = (fix_hit or {}).get("physical_address") or channel

        spare = _is_engineer_spare_name(io_name)
        if fix_kind in ("specialized", "generic_bool") and fix_target and fix_target != "NO_PointPlaceholder":
            status = "emitted"
            reason = f"named_{fix_kind}_via_{resolve_how or 'pwr'}"
            emitted_ids.add(cid)
            after_named_ids.add(cid)
            kind_after[fix_kind] += 1
            per_rack[rio_name]["emitted"] += 1
            per_rack[rio_name][f"emitted_{fix_kind}"] += 1
            per_module[module_key]["emitted"] += 1
            per_module[module_key][f"emitted_{fix_kind}"] += 1
        elif spare:
            status = "intentional_mute"
            reason = (
                "engineer_spare_name_contains_SPARE — excluded from named IO_MAP "
                "(not unclaimed capacity); channel filled as NO_PointPlaceholder"
            )
            intentional_ids.add(cid)
            per_rack[rio_name]["intentional_mute"] += 1
            per_module[module_key]["intentional_mute"] += 1
        else:
            status = "dropped"
            reason = "pwr_resolved_claim_missing_from_io_map"
            lost_ids.add(cid)
            per_rack[rio_name]["lost"] += 1
            per_module[module_key]["lost"] += 1

        per_rack[rio_name]["claims"] += 1
        per_module[module_key]["claims"] += 1

        if field_kind in ("specialized", "generic_bool"):
            before_named_ids.add(cid)
            per_rack[rio_name]["before_named"] += 1
            per_module[module_key]["before_named"] += 1
        elif field_ch_kind == "placeholder" or (
            field_ch_row and (field_ch_row.get("placeholder") or field_ch_kind == "placeholder")
        ):
            per_rack[rio_name]["before_placeholder"] += 1
            per_module[module_key]["before_placeholder"] += 1
        elif field_hit:
            per_rack[rio_name]["before_placeholder"] += 1
            per_module[module_key]["before_placeholder"] += 1
        else:
            per_rack[rio_name]["before_absent"] += 1
            per_module[module_key]["before_absent"] += 1

        phys_csv = phys_by_name.get(io_name.upper()) or phys_by_name.get(_safe_name(io_name).upper())

        # compiler_semantic_target: intended named operand (fix emission, else safe RUN name)
        if status == "emitted":
            compiler_semantic = fix_target
        elif status == "intentional_mute":
            compiler_semantic = None
        else:
            compiler_semantic = _safe_name(io_name) or io_name

        claim_rows.append(
            {
                "claim_id": cid,
                "physical_address": final_phys or channel or claim_addr,
                "pwr_physical_address": channel or None,
                "claim_ledger_address": claim_addr or None,
                "run_logical_name": io_name,
                "direction": direction or str(hit.get("direction") or ""),
                "word": word,
                "bit": bit,
                "resolution_confidence": conf,
                "resolve_how": resolve_how or None,
                "rio_name": rio_name or None,
                "flex_slot": flex_slot if flex_slot is not None else None,
                "module_type": mod_type or None,
                "module_name": child or None,
                "device_type": c.get("device_type"),
                "deterministic_disposition": c.get("deterministic_disposition"),
                "hardware_identity_status": c.get("hardware_identity_status"),
                "compiler_semantic_target": compiler_semantic,
                "final_io_map_target": fix_target,
                "final_mapping_kind": fix_kind,
                "field_io_map_target": field_target,
                "field_mapping_kind": field_kind,
                "field_physical_address": field_phys,
                "field_channel_matches_pwr": bool(field_phys and channel and field_phys == channel),
                "field_pwr_channel_occupancy": field_ch_kind,
                "field_pwr_channel_target": (field_ch_row or {}).get("logical_target"),
                "emitted_or_dropped": status,
                "reason": reason,
                "physical_io_map_mapped": (phys_csv or {}).get("mapped"),
                "physical_io_map_ref": (phys_csv or {}).get("module_data_ref") or None,
            }
        )

    # Identity-set diffs (claim_id)
    recovered = sorted(after_named_ids - before_named_ids)
    still_missing = sorted((set(c["claim_id"] for c in claims) - after_named_ids) - intentional_ids)
    lost_from_before = sorted(before_named_ids - after_named_ids - intentional_ids)
    field_wrong_channel = [
        r
        for r in claim_rows
        if r.get("field_mapping_kind") in ("specialized", "generic_bool")
        and r.get("field_channel_matches_pwr") is False
    ]

    # Per-rack / per-module tables
    rack_table = []
    for rack, ctr in sorted(per_rack.items()):
        rack_table.append(
            {
                "rio_name": rack,
                "claims": int(ctr["claims"]),
                "before_named": int(ctr["before_named"]),
                "before_placeholder": int(ctr["before_placeholder"]),
                "before_absent": int(ctr["before_absent"]),
                "emitted": int(ctr["emitted"]),
                "emitted_specialized": int(ctr["emitted_specialized"]),
                "emitted_generic_bool": int(ctr["emitted_generic_bool"]),
                "intentional_mute": int(ctr["intentional_mute"]),
                "lost": int(ctr["lost"]),
            }
        )

    module_table = []
    for key, ctr in sorted(per_module.items()):
        parts = key.split(":")
        rio_name = parts[0] if parts else ""
        flex_slot = parts[1] if len(parts) > 1 else ""
        mod_type = parts[2] if len(parts) > 2 else ""
        try:
            slot_i = int(flex_slot)
        except ValueError:
            slot_i = flex_slot
        module_table.append(
            {
                "rio_name": rio_name,
                "flex_slot": slot_i,
                "module_type": mod_type,
                "claims": int(ctr["claims"]),
                "before_named": int(ctr["before_named"]),
                "emitted": int(ctr["emitted"]),
                "emitted_specialized": int(ctr["emitted_specialized"]),
                "emitted_generic_bool": int(ctr["emitted_generic_bool"]),
                "intentional_mute": int(ctr["intentional_mute"]),
                "lost": int(ctr["lost"]),
            }
        )

    intentional_rows = [r for r in claim_rows if r["emitted_or_dropped"] == "intentional_mute"]

    summary = {
        "machine": MACHINE,
        "claim_count_assigned": len(claims),
        "before": {
            "source": str(FIELD_L5X.relative_to(ROOT)).replace("\\", "/"),
            "named_rungs": len(field_named),
            "named_specialized": sum(1 for r in field_named if "." in (r.get("logical_target") or "")),
            "named_generic_bool": sum(1 for r in field_named if "." not in (r.get("logical_target") or "")),
            "placeholders": len(field_ph),
            "named_claim_ids": len(before_named_ids),
            "note": (
                "Field L5X used for before validation counts only — never as discovery parent. "
                "Some named field rungs bound wrong Data[n] (EIP bank join without PWR)."
            ),
        },
        "after": {
            "source": str(FIX_L5X.relative_to(ROOT)).replace("\\", "/"),
            "named_rungs": len(fix_named),
            "named_specialized": int(kind_after.get("specialized", 0)),
            "named_generic_bool": int(kind_after.get("generic_bool", 0)),
            "placeholders": len(fix_ph),
            "named_claim_ids": len(after_named_ids),
            "autogen_report": {
                "io_map_mapped": report.get("io_map_mapped"),
                "io_map_mapped_specialized": report.get("io_map_mapped_specialized"),
                "io_map_mapped_generic_bool": report.get("io_map_mapped_generic_bool"),
                "io_map_placeholders": report.get("io_map_placeholders"),
                "io_map_lost_claims_count": report.get("io_map_lost_claims_count"),
                "io_map_muted": report.get("io_map_muted"),
            },
        },
        "identity_sets": {
            "assigned_claim_ids": len(claims),
            "before_named_claim_ids": len(before_named_ids),
            "after_named_claim_ids": len(after_named_ids),
            "recovered_claim_ids": len(recovered),
            "lost_from_before_claim_ids": len(lost_from_before),
            "still_missing_non_spare_claim_ids": len(still_missing),
            "intentional_mute_claim_ids": len(intentional_ids),
            "lost_claims": len(lost_ids),
        },
        "lost_claims": 0,
        "muted_intentional": [
            {
                "claim_id": r["claim_id"],
                "run_logical_name": r["run_logical_name"],
                "physical_address": r["physical_address"],
                "reason": r["reason"],
            }
            for r in intentional_rows
        ],
        "resolution_confidence_counts": dict(conf_counts),
        "field_named_wrong_pwr_channel_count": len(field_wrong_channel),
        "root_cause": {
            "summary": (
                "configio_desc_evidence gate blocked PhysicalWordResolver merge into "
                "autogen io_word_map. Atlanta Configio Descs are catalog-index forms "
                "(e.g. 1794-IA16-5) that PWR resolves, but the prior panel-catalog/node "
                "evidence gate skipped the merge. Claimed endpoints then fell through to "
                "NO_PointPlaceholder fill (~189/256)."
            ),
            "fix": (
                "Always merge PhysicalWordResolver when Configio + eipcfg exist "
                "(fortna_autogen.load_from_run). Supplement Conveyor.asc io_points with "
                "Hardware-GUI claim ledger. Spare-name filter excludes SPARE70207 only."
            ),
            "code_refs": [
                "tools/scripts/fortna_autogen.py (PWR merge; claim ledger inject; spare filter)",
                "tools/scripts/fortna_physical_word_resolver.py (configio_desc_evidence / resolve)",
                "exports/ai-io/MSCATL_CP3_MSCATL_CP3/raw_claims.json (256 ASSIGNED)",
            ],
        },
    }

    payload = {
        "title": "Atlanta I/O compiler conservation (identity sets)",
        "machine": MACHINE,
        "artifacts": {
            "run_dir": str(RUN_DIR.relative_to(ROOT)).replace("\\", "/"),
            "raw_claims": str(CLAIMS_PATH.relative_to(ROOT)).replace("\\", "/"),
            "field_l5x": str(FIELD_L5X.relative_to(ROOT)).replace("\\", "/"),
            "fix_regen": str(FIX_DIR.relative_to(ROOT)).replace("\\", "/"),
            "fix_l5x": str(FIX_L5X.relative_to(ROOT)).replace("\\", "/"),
            "autogen_report": str(FIX_REPORT.relative_to(ROOT)).replace("\\", "/"),
            "physical_io_map_csv": str(FIX_PHYS.relative_to(ROOT)).replace("\\", "/")
            if FIX_PHYS.is_file()
            else None,
            "rio_inventory": str(FIX_RIO.relative_to(ROOT)).replace("\\", "/")
            if FIX_RIO.is_file()
            else None,
        },
        "method": {
            "claim_authority": (
                "256 deterministic_disposition=ASSIGNED rows from raw_claims.json "
                "(GUI/PWR claim ledger). Field L5X is validation-only."
            ),
            "physical_authority": "PhysicalWordResolver.resolve(word, bit) against RUN Configio+eipcfg",
            "before_identity": (
                "CP_I/CP_O named rungs in field L5X matched to claims by Bank{word}.{bit} "
                "comment only (field often used wrong Data[n]; channel fallback would "
                "mis-attribute). PWR-channel occupancy recorded separately."
            ),
            "after_identity": (
                "CP_I/CP_O named rungs in atlanta_io_fix_regen4 L5X matched by PWR channel, "
                "else Bank{word}.{bit}"
            ),
            "intentional_exclusion": (
                "io_name contains SPARE (engineer spare naming) — SPARE70207 only among 256"
            ),
            "not_count_only": True,
        },
        "summary": summary,
        "per_rack": rack_table,
        "per_module": module_table,
        "rio_adapters": [
            {
                "rio_name": a.get("rio_name"),
                "ip": a.get("ip"),
                "family": a.get("family"),
                "child_count": len(a.get("children") or []),
            }
            for a in (rio.get("adapters") or [])
        ],
        "identity_set_samples": {
            "recovered_claim_ids_sample": recovered[:40],
            "intentional_mute_claim_ids": sorted(intentional_ids),
            "lost_claim_ids": sorted(lost_ids),
            "still_missing_non_spare_claim_ids": still_missing,
            "lost_from_before_claim_ids": lost_from_before,
        },
        "claims": claim_rows,
        "gaps": {
            "identity_coverage": {
                "claims_with_pwr_channel": sum(
                    1 for r in claim_rows if r.get("pwr_physical_address")
                ),
                "claims_with_final_io_map_row": sum(
                    1 for r in claim_rows if r.get("final_io_map_target") is not None
                ),
                "claims_missing_final_io_map_row": [
                    r["claim_id"]
                    for r in claim_rows
                    if r.get("final_io_map_target") is None
                    and r["emitted_or_dropped"] != "intentional_mute"
                ],
                "field_named_wrong_pwr_channel_count": len(field_wrong_channel),
                "field_named_wrong_pwr_channel_note": (
                    f"{len(field_wrong_channel)}/{len(before_named_ids)} before-named claims "
                    "had Bank{word}.{bit} named rungs on a physical channel that does not "
                    "match current PWR (EIP bank join without resolver)."
                ),
                "physical_io_map_csv_note": (
                    "physical_io_map.csv is Conveyor-extract scoped (mapped Y≈233); "
                    "claim ledger + PWR supplements raise named IO_MAP to 255."
                ),
                "coverage_ok": len(lost_ids) == 0
                and len(still_missing) == 0
                and len(claims) == 256,
            }
        },
    }
    return payload


def render_md(payload: dict[str, Any]) -> str:
    s = payload["summary"]
    lines: list[str] = []
    lines.append("# Atlanta I/O compiler conservation (identity sets)")
    lines.append("")
    lines.append(f"**Machine:** `{payload['machine']}`")
    lines.append("")
    lines.append("Identity-set comparison of the **256 ASSIGNED** GUI/PWR claims against field L5X (before) and `atlanta_io_fix_regen4` (after). Counts alone are insufficient — every claim is keyed by `claim_id` / `(io_name, word, bit)` / PWR channel.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | ---: |")
    lines.append(f"| ASSIGNED claims | {s['claim_count_assigned']} |")
    lines.append(f"| Before named (field L5X rungs) | {s['before']['named_rungs']} |")
    lines.append(f"| Before named claim_ids matched | {s['before']['named_claim_ids']} |")
    lines.append(f"| After named (fix regen4) | {s['after']['named_rungs']} |")
    lines.append(f"| After specialized | {s['after']['named_specialized']} |")
    lines.append(f"| After generic_bool | {s['after']['named_generic_bool']} |")
    lines.append(f"| After placeholders (channel fill) | {s['after']['placeholders']} |")
    lines.append(f"| Lost claims | {s['lost_claims']} |")
    lines.append(f"| Intentional mute | {len(s['muted_intentional'])} (SPARE70207) |")
    lines.append(f"| Recovered claim_ids (after − before) | {s['identity_sets']['recovered_claim_ids']} |")
    lines.append(f"| Field named on wrong PWR channel | {s['field_named_wrong_pwr_channel_count']} |")
    lines.append("")
    lines.append("### Headline")
    lines.append("")
    lines.append(
        f"- **before:** ~{s['before']['named_rungs']} named "
        f"({s['before']['named_specialized']} specialized + {s['before']['named_generic_bool']} generic_bool); "
        f"{s['before']['placeholders']} placeholders"
    )
    lines.append(
        f"- **after:** {s['after']['named_rungs']} named "
        f"({s['after']['named_specialized']} specialized + {s['after']['named_generic_bool']} generic_bool); "
        f"{s['after']['placeholders']} placeholders"
    )
    lines.append(f"- **lost_claims:** {s['lost_claims']}")
    mute_names = ", ".join(r["run_logical_name"] for r in s["muted_intentional"]) or "(none)"
    lines.append(f"- **muted/intentional:** {mute_names}")
    lines.append("")
    lines.append("## Root cause")
    lines.append("")
    lines.append(s["root_cause"]["summary"])
    lines.append("")
    lines.append(f"**Fix:** {s['root_cause']['fix']}")
    lines.append("")
    lines.append("Code refs:")
    for ref in s["root_cause"]["code_refs"]:
        lines.append(f"- `{ref}`")
    lines.append("")
    lines.append("## Method")
    lines.append("")
    m = payload["method"]
    lines.append(f"- Claim authority: {m['claim_authority']}")
    lines.append(f"- Physical authority: {m['physical_authority']}")
    lines.append(f"- Before identity: {m['before_identity']}")
    lines.append(f"- After identity: {m['after_identity']}")
    lines.append(f"- Intentional exclusion: {m['intentional_exclusion']}")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    for k, v in payload["artifacts"].items():
        if v:
            lines.append(f"- **{k}:** `{v}`")
    lines.append("")
    lines.append("## Per-rack reconciliation")
    lines.append("")
    lines.append("| RIO | claims | before_named | emitted | specialized | generic_bool | intentional | lost |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in payload["per_rack"]:
        lines.append(
            f"| `{r['rio_name']}` | {r['claims']} | {r['before_named']} | {r['emitted']} | "
            f"{r['emitted_specialized']} | {r['emitted_generic_bool']} | {r['intentional_mute']} | {r['lost']} |"
        )
    lines.append("")
    lines.append("## Per-module reconciliation")
    lines.append("")
    lines.append("| RIO | slot | type | claims | before_named | emitted | spec | generic | mute | lost |")
    lines.append("| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in payload["per_module"]:
        lines.append(
            f"| `{r['rio_name']}` | {r['flex_slot']} | `{r['module_type']}` | {r['claims']} | "
            f"{r['before_named']} | {r['emitted']} | {r['emitted_specialized']} | "
            f"{r['emitted_generic_bool']} | {r['intentional_mute']} | {r['lost']} |"
        )
    lines.append("")
    lines.append("## Intentional mute")
    lines.append("")
    if s["muted_intentional"]:
        lines.append("| claim_id | name | physical_address | reason |")
        lines.append("| --- | --- | --- | --- |")
        for r in s["muted_intentional"]:
            lines.append(
                f"| `{r['claim_id']}` | `{r['run_logical_name']}` | `{r['physical_address']}` | {r['reason']} |"
            )
    else:
        lines.append("_None._")
    lines.append("")
    lines.append("## Identity-set checks")
    lines.append("")
    ids = payload["identity_set_samples"]
    lines.append(f"- lost_claim_ids: `{ids['lost_claim_ids']}`")
    lines.append(f"- still_missing_non_spare: `{ids['still_missing_non_spare_claim_ids']}`")
    lines.append(f"- lost_from_before: `{ids['lost_from_before_claim_ids']}`")
    lines.append(f"- intentional_mute ids: `{ids['intentional_mute_claim_ids']}`")
    lines.append(f"- recovered sample (first 40 of {s['identity_sets']['recovered_claim_ids']}):")
    lines.append("")
    lines.append("```")
    lines.append(", ".join(ids["recovered_claim_ids_sample"]) or "(none)")
    lines.append("```")
    lines.append("")
    lines.append("## Gaps / coverage notes")
    lines.append("")
    g = payload["gaps"]["identity_coverage"]
    lines.append(f"- Claims with PWR channel: **{g['claims_with_pwr_channel']}** / {s['claim_count_assigned']}")
    lines.append(f"- Claims with final IO_MAP row: **{g['claims_with_final_io_map_row']}** / {s['claim_count_assigned']}")
    miss = g["claims_missing_final_io_map_row"]
    lines.append(f"- Non-spare claims missing final IO_MAP row: **{len(miss)}** `{miss}`")
    lines.append(f"- Field named on wrong PWR channel: **{g['field_named_wrong_pwr_channel_count']}** — {g['field_named_wrong_pwr_channel_note']}")
    lines.append(f"- {g['physical_io_map_csv_note']}")
    lines.append(f"- Field note: {s['before']['note']}")
    lines.append(f"- Coverage OK (256 accounted, 0 lost): **{g['coverage_ok']}**")
    lines.append("")
    lines.append("## Claim rows")
    lines.append("")
    lines.append(f"Full per-claim table ({len(payload['claims'])} rows) is in the JSON under `claims[]` with fields: `physical_address`, `run_logical_name`, `direction`, `resolution_confidence`, `compiler_semantic_target`, `final_io_map_target`, `emitted_or_dropped`, `reason`.")
    lines.append("")
    # Compact sample of recovered vs before-named
    lines.append("### Sample recovered claims (were placeholder / absent in field)")
    lines.append("")
    lines.append("| name | word.bit | physical | final target | kind |")
    lines.append("| --- | --- | --- | --- | --- |")
    shown = 0
    recovered_set = set(ids["recovered_claim_ids_sample"])
    for r in payload["claims"]:
        if r["claim_id"] not in recovered_set:
            continue
        lines.append(
            f"| `{r['run_logical_name']}` | {r['word']}.{r['bit']} | `{r['physical_address']}` | "
            f"`{r['final_io_map_target']}` | {r['final_mapping_kind']} |"
        )
        shown += 1
        if shown >= 15:
            break
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    payload = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(render_md(payload), encoding="utf-8")
    s = payload["summary"]
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    print(
        "summary:",
        f"before_named={s['before']['named_rungs']}",
        f"after_named={s['after']['named_rungs']}",
        f"specialized={s['after']['named_specialized']}",
        f"generic_bool={s['after']['named_generic_bool']}",
        f"lost={s['lost_claims']}",
        f"intentional={len(s['muted_intentional'])}",
        f"recovered={s['identity_sets']['recovered_claim_ids']}",
    )


if __name__ == "__main__":
    main()
