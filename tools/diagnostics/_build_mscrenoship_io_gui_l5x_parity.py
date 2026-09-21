#!/usr/bin/env python3
"""MSCRENOSHIP I/O GUI vs L5X parity diagnostics (identity sets).

Compares HardwareIOModel claimed channels (ASSIGNED / CLAIMED occupancy) against
field-validation L5X IO_MAP CP_I/CP_O unique physical addresses. Also audits
duplicate physical addresses in L5X (mapping_count>1).

Writes:
  exports/diagnostics/mscrenoship_io_gui_l5x_parity.json
  exports/diagnostics/mscrenoship_io_gui_l5x_parity.md

Diagnostic only — does not mutate production decoders.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fortna_hardware_io_model import (  # noqa: E402
    OWNER_ASSIGNED,
    OWNER_UNRESOLVED,
    OWNER_UNUSED_MAPPED,
    build_hardware_io_model,
)
from fortna_bit_address import parse_fortna_bit_address  # noqa: E402
from fortna_physical_word_resolver import PhysicalWordResolver  # noqa: E402

RUN_DIR = ROOT / "workspace" / "_reno_peek" / "20260813-1132-MSCRENO-MSCRENOSHIP-RUN" / "RUN"
MACHINE = "MSCRENOSHIP"
FIELD_L5X = ROOT / "exports" / "current" / "MSCRENOSHIP_2026_09_21_0108.L5X"
OUT_JSON = ROOT / "exports" / "diagnostics" / "mscrenoship_io_gui_l5x_parity.json"
OUT_MD = ROOT / "exports" / "diagnostics" / "mscrenoship_io_gui_l5x_parity.md"

_CH_RE = re.compile(
    r"^(?P<adapter>[A-Za-z0-9_]+):(?P<dir>[IO])\.Data\[(?P<slot>\d+)\]\.(?P<bit>\d+)$",
    re.I,
)
_BANK_RE = re.compile(r"Bank(\d+)\.(\d+)")

FOCUS_MODULES = (
    {"adapter": "AENTR_1", "slot": 6, "type_hint": "1734-IA4", "note": "GUI ~3/4 vs gen 4?"},
    {"adapter": "AENTR_1", "slot": 7, "type_hint": "1734-IA4", "note": "GUI ~3/4 vs gen 4?"},
    {"adapter": "AENTR_2", "slot": 5, "type_hint": "1734-IB8", "note": "GUI 1/8 vs many?"},
    {"adapter": "AENTR_3", "slot": 10, "type_hint": "1734-OB8E", "note": "GUI ~6/8 vs +1?"},
)

DUP_CLASSES = (
    "PROVEN_ALIAS",
    "PROVEN_SHARED_SEMANTIC",
    "OWNER_CONFLICT",
    "DUPLICATE_CLAIM",
    "DECODER_ERROR",
    "REVIEW_REQUIRED",
)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gui_occupancy(owner_state: str, logical_name: str = "") -> str:
    st = (owner_state or "").upper()
    name = (logical_name or "").strip()
    if st == OWNER_ASSIGNED and name and name.upper() not in {"SPARE", "UNCLAIMED"}:
        return "CLAIMED"
    if st == OWNER_UNRESOLVED:
        return "UNRESOLVED OWNER"
    if st in {OWNER_UNUSED_MAPPED, "UNKNOWN", "PROVEN_SPARE", "ENGINEER_SPARE"}:
        return "UNCLAIMED"
    if name and name.upper() not in {"SPARE", "UNCLAIMED", ""}:
        return "CLAIMED"
    return "UNCLAIMED"


def _logical_name(ch: dict[str, Any]) -> str:
    le = ch.get("logical_endpoint") if isinstance(ch.get("logical_endpoint"), dict) else {}
    return str(
        ch.get("engineering_owner")
        or ch.get("sourceName")
        or le.get("name")
        or ""
    ).strip()


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
            rows.append(
                {
                    "routine": routine,
                    "text": text,
                    "comment": comment,
                    "physical_address": physical,
                    "logical_target": logical,
                    "placeholder": placeholder,
                    "mapping_kind": kind,
                    "word": int(bm.group(1)) if bm else None,
                    "bit_label": bm.group(2) if bm else None,
                }
            )
    return rows


def _parse_channel(addr: str | None) -> dict[str, Any] | None:
    if not addr:
        return None
    m = _CH_RE.match(addr)
    if not m:
        return None
    return {
        "adapter": m.group("adapter"),
        "direction": m.group("dir").upper(),
        "data_index": int(m.group("slot")),
        "bit": int(m.group("bit")),
    }


def _bit_meta(bit_label: str | None) -> dict[str, Any]:
    if bit_label is None or bit_label == "":
        return {"logical_bit": None, "half": None, "module_bit": None, "raw_text": ""}
    addr = parse_fortna_bit_address(bit_label)
    return {
        "logical_bit": addr.logical_bit,
        "half": addr.half,
        "module_bit": addr.module_bit,
        "raw_text": addr.raw_text,
        "encoding": addr.encoding,
    }


def classify_duplicate(
    physical_address: str,
    mappings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify L5X physical-address collisions (mapping_count>1).

    Default REVIEW_REQUIRED unless clear Low/High same-word or shared-output
    evidence is present.
    """
    named = [
        m
        for m in mappings
        if not m.get("placeholder") and m.get("logical_target") not in (None, "NO_PointPlaceholder")
    ]
    targets = [str(m.get("logical_target") or "") for m in named]
    comments = [str(m.get("comment") or "") for m in named]
    words = {m.get("word") for m in named if m.get("word") is not None}
    bit_metas = [_bit_meta(m.get("bit_label")) for m in named]
    halves = {bm.get("half") for bm in bit_metas if bm.get("half")}
    module_bits = {bm.get("module_bit") for bm in bit_metas if bm.get("module_bit") is not None}
    bank_keys = {
        (m.get("word"), m.get("bit_label"))
        for m in named
        if m.get("word") is not None and m.get("bit_label") is not None
    }
    shared_marker = any(
        "REVIEW_SHARED" in c.upper() or "SHARED_OUTPUT" in c.upper() for c in comments
    )

    classification = "REVIEW_REQUIRED"
    evidence: list[str] = []
    hypothesis = ""

    if shared_marker and len(bank_keys) == 1:
        classification = "PROVEN_SHARED_SEMANTIC"
        evidence.append("L5X comment marks REVIEW_SHARED_OUTPUT on same Bank.word.bit")
        hypothesis = (
            "Autogen preserved multiple RUN-proven owners on one physical OUTPUT; "
            "GUI marks UNRESOLVED_OWNER / OWNER_CONFLICT while L5X emits all claims."
        )
    elif len(bank_keys) == 1 and len(set(targets)) > 1:
        classification = "OWNER_CONFLICT"
        evidence.append(f"same Bank{next(iter(bank_keys))[0]}.{next(iter(bank_keys))[1]} → distinct logical targets {targets}")
        hypothesis = (
            "Multiple Conveyor.asc IO_Name rows claim the same Fortna word.bit; "
            "HardwareIOModel collapses to UNRESOLVED_OWNER while IO_MAP emits every owner."
        )
    elif (
        len(words) == 1
        and halves == {"Low", "High"}
        and len(module_bits) == 1
        and len(bank_keys) > 1
    ):
        classification = "DECODER_ERROR"
        evidence.append(
            f"same-word Low+High halves collapse to module_bit={next(iter(module_bits))} "
            f"on {physical_address}; bank keys={sorted(bank_keys)}"
        )
        hypothesis = (
            "Configio High bank failed to join a distinct module (bank mismatch / "
            "output-bank collision), so high-half labels (octal 10-17) fan onto the "
            "Low module's bits 0-7 and collide with Low claims."
        )
    elif len(bank_keys) > 1 and len(set(targets)) > 1:
        # Distinct bank.bit identities on one physical channel without clear Lo/Hi pair
        classification = "DUPLICATE_CLAIM"
        evidence.append(f"distinct bank keys {sorted(bank_keys)} → {targets}")
        hypothesis = (
            "Distinct Fortna word.bit claims resolved to one physical channel; "
            "needs half/bank join review."
        )
    elif len(set(targets)) == 1 and len(named) > 1:
        classification = "PROVEN_ALIAS"
        evidence.append(f"repeated identical logical target {targets[0]}")
        hypothesis = "Duplicate rung text for the same logical/physical pair."
    else:
        evidence.append(f"targets={targets}; bank_keys={sorted(bank_keys)}; halves={sorted(halves)}")
        hypothesis = "Insufficient evidence for automatic classification."

    return {
        "physical_address": physical_address,
        "mapping_count": len(mappings),
        "named_mapping_count": len(named),
        "classification": classification,
        "logical_targets": targets,
        "bank_keys": [
            {"word": w, "bit_label": b} for (w, b) in sorted(bank_keys, key=lambda x: (x[0] or -1, str(x[1])))
        ],
        "halves": sorted(h for h in halves if h),
        "module_bits": sorted(b for b in module_bits if b is not None),
        "comments": comments,
        "evidence": evidence,
        "hypothesis": hypothesis,
        "mappings": [
            {
                "routine": m.get("routine"),
                "logical_target": m.get("logical_target"),
                "placeholder": m.get("placeholder"),
                "mapping_kind": m.get("mapping_kind"),
                "word": m.get("word"),
                "bit_label": m.get("bit_label"),
                "comment": m.get("comment"),
                "text": m.get("text"),
            }
            for m in mappings
        ],
    }


def _module_key(adapter: str, slot: int | None, mtype: str = "") -> str:
    return f"{adapter}:{slot}:{mtype}"


def build() -> dict[str, Any]:
    if not RUN_DIR.is_dir():
        raise SystemExit(f"RUN missing: {RUN_DIR}")
    if not FIELD_L5X.is_file():
        raise SystemExit(f"L5X missing: {FIELD_L5X}")

    model = build_hardware_io_model(RUN_DIR, MACHINE)
    pwr = PhysicalWordResolver(RUN_DIR, MACHINE)
    l5x_rows = parse_iomap_rungs(FIELD_L5X)

    l5x_by_phys: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in l5x_rows:
        pa = r.get("physical_address")
        if pa:
            l5x_by_phys[str(pa)].append(r)

    l5x_named_by_phys: dict[str, list[dict[str, Any]]] = {
        pa: [
            r
            for r in rows
            if not r.get("placeholder")
            and r.get("logical_target") not in (None, "NO_PointPlaceholder")
        ]
        for pa, rows in l5x_by_phys.items()
    }
    l5x_named_by_phys = {pa: rows for pa, rows in l5x_named_by_phys.items() if rows}
    l5x_unique_named = set(l5x_named_by_phys)
    l5x_placeholder_only = {
        pa
        for pa, rows in l5x_by_phys.items()
        if pa not in l5x_unique_named
        and any(r.get("placeholder") or r.get("logical_target") == "NO_PointPlaceholder" for r in rows)
    }

    gui_channels: list[dict[str, Any]] = []
    gui_claimed: set[str] = set()
    gui_unresolved: set[str] = set()
    gui_all_phys: set[str] = set()
    per_module: dict[str, dict[str, Any]] = {}

    for ad in model.get("adapters") or []:
        rio = str(ad.get("rio_name") or "")
        eip = str(ad.get("eipcfg_name") or ad.get("name") or "")
        for mod in ad.get("modules") or []:
            if mod.get("is_adapter_card"):
                continue
            slot = mod.get("slot")
            try:
                slot_i = int(slot) if slot is not None else None
            except (TypeError, ValueError):
                slot_i = None
            mtype = str(mod.get("type") or mod.get("catalog") or "")
            direction = str(mod.get("direction") or "")
            data_index = mod.get("data_index")
            mkey = _module_key(rio, slot_i, mtype)
            claimed_addrs: list[str] = []
            unresolved_addrs: list[str] = []
            channel_rows: list[dict[str, Any]] = []
            for ch in mod.get("channels") or []:
                pa = str(ch.get("physical_address") or "").strip()
                owner_state = str(ch.get("owner_state") or "")
                logical = _logical_name(ch)
                occ = _gui_occupancy(owner_state, logical)
                if pa:
                    gui_all_phys.add(pa)
                rec = {
                    "physical_address": pa or None,
                    "owner_state": owner_state,
                    "occupancy": occ,
                    "logical_name": logical or None,
                    "fortna_word": ch.get("fortna_word"),
                    "fortna_bit": ch.get("fortna_bit"),
                    "bit_half": ch.get("bit_half"),
                    "direction": ch.get("direction") or direction,
                    "rejection_reason": ch.get("rejection_reason"),
                    "owner_source": ch.get("owner_source"),
                    "adapter": rio,
                    "eipcfg_name": eip,
                    "module_slot": slot_i,
                    "module_type": mtype,
                    "data_index": data_index,
                }
                channel_rows.append(rec)
                gui_channels.append(rec)
                if owner_state == OWNER_ASSIGNED and pa:
                    gui_claimed.add(pa)
                    claimed_addrs.append(pa)
                elif owner_state == OWNER_UNRESOLVED and pa:
                    gui_unresolved.add(pa)
                    unresolved_addrs.append(pa)

            # L5X mapped unique phys for this adapter/data_index/direction
            try:
                di = int(data_index) if data_index is not None else slot_i
            except (TypeError, ValueError):
                di = slot_i
            dir_ch = (direction or "").upper()[:1]
            l5x_mapped: list[str] = []
            l5x_mapped_rows: list[dict[str, Any]] = []
            if rio and di is not None and dir_ch in {"I", "O"}:
                prefix = f"{rio}:{dir_ch}.Data[{di}]."
                for pa, rows in sorted(l5x_named_by_phys.items()):
                    if pa.startswith(prefix):
                        l5x_mapped.append(pa)
                        l5x_mapped_rows.extend(rows)

            claimed_set = set(claimed_addrs)
            mapped_set = set(l5x_mapped)
            per_module[mkey] = {
                "adapter": rio,
                "eipcfg_name": eip,
                "slot": slot_i,
                "type": mtype,
                "direction": direction,
                "data_index": di,
                "channel_capacity": mod.get("channel_capacity"),
                "gui_channel_count": len(channel_rows),
                "gui_claimed_n": len(claimed_set),
                "gui_unresolved_n": len(set(unresolved_addrs)),
                "gui_claimed_addrs": sorted(claimed_set),
                "gui_unresolved_addrs": sorted(set(unresolved_addrs)),
                "l5x_mapped_n": len(mapped_set),
                "l5x_mapped_addrs": sorted(mapped_set),
                "l5x_named_rung_count": len(l5x_mapped_rows),
                "parity_ok": len(claimed_set) == len(mapped_set) and claimed_set == mapped_set,
                "count_mismatch": len(claimed_set) != len(mapped_set),
                "claimed_only": sorted(claimed_set - mapped_set),
                "mapped_only": sorted(mapped_set - claimed_set),
                "channels": channel_rows,
            }

    # Identity-set diffs (ASSIGNED/CLAIMED vs L5X unique named phys)
    claimed_only = sorted(gui_claimed - l5x_unique_named)
    mapped_only = sorted(l5x_unique_named - gui_claimed)
    both = sorted(gui_claimed & l5x_unique_named)
    unresolved_also_mapped = sorted(gui_unresolved & l5x_unique_named)

    # Duplicate audit
    dup_audits: list[dict[str, Any]] = []
    for pa, rows in sorted(l5x_by_phys.items()):
        if len(rows) <= 1:
            continue
        dup_audits.append(classify_duplicate(pa, rows))
    dup_class_counts = Counter(d["classification"] for d in dup_audits)

    mismatched_modules = [
        m for m in per_module.values() if m.get("count_mismatch") or not m.get("parity_ok")
    ]
    mismatched_modules.sort(
        key=lambda m: (
            abs(int(m.get("l5x_mapped_n") or 0) - int(m.get("gui_claimed_n") or 0)),
            str(m.get("adapter") or ""),
            int(m.get("slot") or -1),
        ),
        reverse=True,
    )

    # Focus examples
    focus_out: list[dict[str, Any]] = []
    for spec in FOCUS_MODULES:
        adapter = spec["adapter"]
        slot = int(spec["slot"])
        match = None
        for m in per_module.values():
            if m.get("adapter") == adapter and m.get("slot") == slot:
                match = m
                break
        detail = {
            "focus_note": spec["note"],
            "adapter": adapter,
            "slot": slot,
            "type_hint": spec["type_hint"],
            "found": match is not None,
        }
        if match:
            detail.update(
                {
                    "type": match.get("type"),
                    "direction": match.get("direction"),
                    "data_index": match.get("data_index"),
                    "channel_capacity": match.get("channel_capacity"),
                    "gui_claimed_n": match.get("gui_claimed_n"),
                    "gui_unresolved_n": match.get("gui_unresolved_n"),
                    "l5x_mapped_n": match.get("l5x_mapped_n"),
                    "l5x_named_rung_count": match.get("l5x_named_rung_count"),
                    "count_mismatch": match.get("count_mismatch"),
                    "claimed_only": match.get("claimed_only"),
                    "mapped_only": match.get("mapped_only"),
                    "gui_channels": match.get("channels"),
                    "l5x_rows": [
                        {
                            "physical_address": r.get("physical_address"),
                            "logical_target": r.get("logical_target"),
                            "comment": r.get("comment"),
                            "placeholder": r.get("placeholder"),
                            "word": r.get("word"),
                            "bit_label": r.get("bit_label"),
                        }
                        for pa in match.get("l5x_mapped_addrs") or []
                        for r in l5x_by_phys.get(pa, [])
                    ]
                    + [
                        # include unresolved claimed phys L5X even if counted in mapped
                        {
                            "physical_address": r.get("physical_address"),
                            "logical_target": r.get("logical_target"),
                            "comment": r.get("comment"),
                            "placeholder": r.get("placeholder"),
                            "word": r.get("word"),
                            "bit_label": r.get("bit_label"),
                        }
                        for pa in (match.get("gui_unresolved_addrs") or [])
                        if pa not in set(match.get("l5x_mapped_addrs") or [])
                        for r in l5x_by_phys.get(pa, [])
                    ],
                    "duplicate_addrs_on_module": [
                        d
                        for d in dup_audits
                        if _parse_channel(d["physical_address"])
                        and _parse_channel(d["physical_address"])["adapter"] == adapter
                        and _parse_channel(d["physical_address"])["data_index"]
                        == match.get("data_index")
                    ],
                }
            )
            # Root-cause hint per focus
            if adapter == "AENTR_2" and slot == 5:
                winfo = (pwr.physical_map.get("words") or {}).get("1111") or {}
                detail["root_cause_hypothesis"] = (
                    "Word 1111 Low bank 76 joins AENTR_2 slot5 IB8, but High bank 4 is the "
                    "adapter OutputAddress / OB8E output_bank — not an input module. "
                    "High-half Conveyor bits (octal 11-17 → SSVD3..SSVD9) therefore fan onto "
                    "Data[5].1-.7 and collide with Low claims; GUI keeps 1 ASSIGNED + 7 "
                    "UNRESOLVED_OWNER while L5X emits both owners per channel."
                )
                detail["word_map_1111"] = {
                    "low_bank": winfo.get("low_bank"),
                    "high_bank": winfo.get("high_bank"),
                    "channel_base": winfo.get("channel_base"),
                    "type": winfo.get("type"),
                    "assign_how": winfo.get("assign_how"),
                }
            elif adapter == "AENTR_1" and slot in (6, 7):
                detail["root_cause_hypothesis"] = (
                    "IA4 high-half banks join the correct adjacent module, so capacity is 4. "
                    "GUI claimed_n=3 because one channel is OWNER_CONFLICT (two Conveyor "
                    "names on the same Bank.word.bit). L5X unique mapped_n=4 because it still "
                    "emits a named rung on the conflicted bit (often mapping_count=2)."
                )
            elif adapter == "AENTR_3" and slot == 10:
                detail["root_cause_hypothesis"] = (
                    "High half of word 1124 correctly lands on OB8E slot10. GUI claimed_n=6 "
                    "with one UNRESOLVED_OWNER on Data[10].5 where MSORTTR1 and VFDSSVSOL1 "
                    "share Bank1124.15 (REVIEW_SHARED_OUTPUT). L5X unique mapped_n=7 "
                    "(+1 vs GUI ASSIGNED) because the conflicted bit is still named."
                )
            else:
                detail["root_cause_hypothesis"] = match.get("count_mismatch") and (
                    "GUI ASSIGNED count differs from L5X unique named physical addresses on this module."
                ) or "Counts match on identity sets for this module."
        focus_out.append(detail)

    owner_states = dict((model.get("stats") or {}).get("owner_states") or {})
    summary = {
        "gui_assigned_claimed_n": len(gui_claimed),
        "gui_unresolved_n": len(gui_unresolved),
        "gui_physical_channel_n": len(gui_all_phys),
        "l5x_iomap_rung_n": len(l5x_rows),
        "l5x_named_rung_n": sum(len(v) for v in l5x_named_by_phys.values()),
        "l5x_unique_named_physical_n": len(l5x_unique_named),
        "l5x_placeholder_only_physical_n": len(l5x_placeholder_only),
        "l5x_duplicate_physical_n": len(dup_audits),
        "identity_both_n": len(both),
        "claimed_only_n": len(claimed_only),
        "mapped_only_n": len(mapped_only),
        "unresolved_also_in_l5x_n": len(unresolved_also_mapped),
        "modules_total": len(per_module),
        "modules_count_mismatch": sum(1 for m in per_module.values() if m.get("count_mismatch")),
        "modules_set_mismatch": sum(1 for m in per_module.values() if not m.get("parity_ok")),
        "dup_classification_counts": dict(dup_class_counts),
        "model_owner_states": owner_states,
    }

    root_causes = [
        {
            "id": "owner_conflict_emitted_in_l5x",
            "statement": (
                "HardwareIOModel marks OWNER_CONFLICT channels as UNRESOLVED_OWNER "
                "(not ASSIGNED/CLAIMED), while IO_MAP still emits every RUN-proven "
                "logical target on that physical address. Module claimed_n therefore "
                "undercounts vs L5X unique mapped_n by the conflicted bits."
            ),
            "evidence_modules": ["AENTR_1:6", "AENTR_1:7", "AENTR_3:10"],
            "recommended_gate": (
                "Parity gate should compare (ASSIGNED ∪ UNRESOLVED_OWNER) occupancy "
                "OR require IO_MAP to suppress/REVIEW conflicted inputs the same way "
                "GUI refuses CLAIMED. Do not treat claimed_n alone as conservation."
            ),
        },
        {
            "id": "high_half_bank_join_collapse_word_1111",
            "statement": (
                "MSCRENOSHIP Configio word 1111 High bank=4 does not match any 1734 "
                "input module (bank 4 is AENTR_2 OutputAddress / OB8E output_bank). "
                "PWR falls back to the Low IB8 and fans high-half octal bits onto "
                "Data[5].0-7, creating systematic Low+High duplicate physical addresses."
            ),
            "evidence_modules": ["AENTR_2:5"],
            "recommended_gate": (
                "Decoder gate: when High bank lookup fails for expected_direction, "
                "do NOT silently inherit Low module — emit unresolved half / "
                "REVIEW_REQUIRED instead of colliding module_bits. Also validate "
                "Configio High banks against synthesized POINT input banks before emit."
            ),
            "production_fix": (
                "Not applied in this diagnostic pass — needs generalized half-join "
                "failure handling plus Configio bank sanity check; small safe fix is "
                "not obvious without broader POINT empty-Desc corpus coverage."
            ),
        },
        {
            "id": "review_shared_output_vs_gui_conflict",
            "statement": (
                "Shared physical OUTPUTs with all RUN-proven owners are annotated "
                "REVIEW_SHARED_OUTPUT and kept in L5X, while GUI occupancy stays "
                "UNRESOLVED_OWNER. This is intentional compiler policy, not lost claims."
            ),
            "evidence_modules": ["AENTR_3:10"],
            "recommended_gate": (
                "Classify PROVEN_SHARED_SEMANTIC separately from DECODER_ERROR in "
                "parity dashboards; do not fail conservation solely on ASSIGNED count."
            ),
        },
    ]

    payload = {
        "ok": bool(model.get("ok")),
        "generated_at": _ts(),
        "machine": MACHINE,
        "run_dir": str(RUN_DIR),
        "field_l5x": str(FIELD_L5X),
        "method": {
            "gui_authority": "fortna_hardware_io_model.build_hardware_io_model",
            "gui_claimed_definition": (
                "owner_state==ASSIGNED (Hardware UI occupancy CLAIMED)"
            ),
            "l5x_authority": "IO_MAP routines CP_I/CP_O physical :I.Data/:O.Data operands",
            "l5x_mapped_definition": (
                "unique physical_address with non-placeholder logical_target"
            ),
            "compare": "identity sets of physical_address — not counts alone",
            "duplicate_classes": list(DUP_CLASSES),
        },
        "summary": summary,
        "identity_sets": {
            "gui_claimed_physical": sorted(gui_claimed),
            "l5x_unique_named_physical": sorted(l5x_unique_named),
            "both": both,
            "claimed_only": claimed_only,
            "mapped_only": mapped_only,
            "gui_unresolved_also_in_l5x": unresolved_also_mapped,
            "gui_unresolved_not_in_l5x": sorted(gui_unresolved - l5x_unique_named),
        },
        "focus_examples": focus_out,
        "modules_mismatched": [
            {
                "adapter": m["adapter"],
                "slot": m["slot"],
                "type": m["type"],
                "gui_claimed_n": m["gui_claimed_n"],
                "gui_unresolved_n": m["gui_unresolved_n"],
                "l5x_mapped_n": m["l5x_mapped_n"],
                "l5x_named_rung_count": m["l5x_named_rung_count"],
                "claimed_only": m["claimed_only"],
                "mapped_only": m["mapped_only"],
            }
            for m in mismatched_modules
        ],
        "modules": list(per_module.values()),
        "duplicate_physical_addresses": dup_audits,
        "root_cause_hypotheses": root_causes,
        "model_stats": model.get("stats"),
    }
    return payload


def render_md(payload: dict[str, Any]) -> str:
    s = payload.get("summary") or {}
    lines = [
        "# MSCRENOSHIP I/O GUI vs L5X parity",
        "",
        f"Generated: `{payload.get('generated_at')}`  ",
        f"**Machine:** `{payload.get('machine')}`  ",
        f"**RUN:** `{payload.get('run_dir')}`  ",
        f"**Field-validation L5X:** `{payload.get('field_l5x')}`",
        "",
        "## Method",
        "",
        "- GUI authority: `build_hardware_io_model` per-channel `physical_address`, `owner_state`, occupancy, logical names",
        "- GUI claimed = `owner_state == ASSIGNED` (UI occupancy **CLAIMED**)",
        "- L5X: parse IO_MAP `CP_I` / `CP_O` for `T_…:I.Data` / `:O.Data` patterns (here `AENTR_n:I|O.Data[s].b`)",
        "- Compare **identity sets** of physical addresses (not counts alone)",
        "- Flag modules where `gui_claimed_n != l5x_mapped_n`",
        "- Audit L5X `mapping_count>1` duplicates with explicit classification",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| GUI ASSIGNED / CLAIMED physical | {s.get('gui_assigned_claimed_n')} |",
        f"| GUI UNRESOLVED_OWNER physical | {s.get('gui_unresolved_n')} |",
        f"| GUI physical channels | {s.get('gui_physical_channel_n')} |",
        f"| L5X named rungs | {s.get('l5x_named_rung_n')} |",
        f"| L5X unique named physical | {s.get('l5x_unique_named_physical_n')} |",
        f"| Identity both (claimed ∩ L5X) | {s.get('identity_both_n')} |",
        f"| Claimed only (GUI − L5X) | {s.get('claimed_only_n')} |",
        f"| Mapped only (L5X − GUI claimed) | {s.get('mapped_only_n')} |",
        f"| UNRESOLVED also present in L5X | {s.get('unresolved_also_in_l5x_n')} |",
        f"| L5X duplicate physical addresses | {s.get('l5x_duplicate_physical_n')} |",
        f"| Modules with count mismatch | {s.get('modules_count_mismatch')} / {s.get('modules_total')} |",
        f"| Modules with set mismatch | {s.get('modules_set_mismatch')} / {s.get('modules_total')} |",
        "",
        "### Duplicate classifications",
        "",
        "| Class | Count |",
        "| --- | ---: |",
    ]
    for cls in DUP_CLASSES:
        lines.append(f"| `{cls}` | {(s.get('dup_classification_counts') or {}).get(cls, 0)} |")

    lines.extend(["", "## Focus examples (Curtis/Gilfoyle)", ""])
    for f in payload.get("focus_examples") or []:
        lines.extend(
            [
                f"### `{f.get('adapter')}` slot {f.get('slot')} ({f.get('type') or f.get('type_hint')})",
                "",
                f"Note: {f.get('focus_note')}",
                "",
                f"| Field | Value |",
                f"| --- | --- |",
                f"| capacity | {f.get('channel_capacity')} |",
                f"| GUI claimed_n (ASSIGNED) | {f.get('gui_claimed_n')} |",
                f"| GUI unresolved_n | {f.get('gui_unresolved_n')} |",
                f"| L5X unique mapped_n | {f.get('l5x_mapped_n')} |",
                f"| L5X named rung count | {f.get('l5x_named_rung_count')} |",
                f"| count_mismatch | {f.get('count_mismatch')} |",
                "",
                f"**Hypothesis:** {f.get('root_cause_hypothesis')}",
                "",
            ]
        )
        dups = f.get("duplicate_addrs_on_module") or []
        if dups:
            lines.append("Duplicate physical on module:")
            lines.append("")
            for d in dups:
                lines.append(
                    f"- `{d.get('physical_address')}` ×{d.get('mapping_count')} → "
                    f"**{d.get('classification')}** · targets `{d.get('logical_targets')}`"
                )
            lines.append("")
        chans = f.get("gui_channels") or []
        if chans:
            lines.append("| bit | physical | owner_state | occupancy | logical |")
            lines.append("| ---: | --- | --- | --- | --- |")
            for ch in chans:
                pa = ch.get("physical_address") or ""
                bit = _parse_channel(pa)
                lines.append(
                    f"| {bit['bit'] if bit else '?'} | `{pa}` | `{ch.get('owner_state')}` | "
                    f"{ch.get('occupancy')} | `{ch.get('logical_name') or ''}` |"
                )
            lines.append("")

    lines.extend(
        [
            "## Root-cause hypotheses",
            "",
        ]
    )
    for rc in payload.get("root_cause_hypotheses") or []:
        lines.extend(
            [
                f"### `{rc.get('id')}`",
                "",
                rc.get("statement") or "",
                "",
                f"**Evidence modules:** {', '.join(f'`{x}`' for x in (rc.get('evidence_modules') or []))}",
                "",
                f"**Recommended gate:** {rc.get('recommended_gate')}",
                "",
            ]
        )
        if rc.get("production_fix"):
            lines.append(f"**Production fix:** {rc.get('production_fix')}")
            lines.append("")

    lines.extend(
        [
            "## Modules with claimed_n ≠ mapped_n",
            "",
            "| Adapter | Slot | Type | GUI claimed | GUI unresolved | L5X mapped | Δ |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for m in payload.get("modules_mismatched") or []:
        if not m.get("gui_claimed_n") and not m.get("l5x_mapped_n") and not m.get("gui_unresolved_n"):
            # skip empty unused modules clutter
            if not m.get("claimed_only") and not m.get("mapped_only"):
                continue
        delta = int(m.get("l5x_mapped_n") or 0) - int(m.get("gui_claimed_n") or 0)
        if int(m.get("gui_claimed_n") or 0) == int(m.get("l5x_mapped_n") or 0):
            continue
        lines.append(
            f"| `{m.get('adapter')}` | {m.get('slot')} | `{m.get('type')}` | "
            f"{m.get('gui_claimed_n')} | {m.get('gui_unresolved_n')} | {m.get('l5x_mapped_n')} | {delta:+d} |"
        )

    lines.extend(
        [
            "",
            "## Duplicate physical addresses (L5X)",
            "",
            "| Physical | n | Class | Targets |",
            "| --- | ---: | --- | --- |",
        ]
    )
    for d in payload.get("duplicate_physical_addresses") or []:
        targets = ", ".join(f"`{t}`" for t in (d.get("logical_targets") or [])[:4])
        lines.append(
            f"| `{d.get('physical_address')}` | {d.get('mapping_count')} | "
            f"**{d.get('classification')}** | {targets} |"
        )

    idents = payload.get("identity_sets") or {}
    if idents.get("mapped_only"):
        lines.extend(
            [
                "",
                "## Mapped-only sample (L5X − GUI ASSIGNED)",
                "",
                "These are typically UNRESOLVED_OWNER conflict bits that IO_MAP still named:",
                "",
            ]
        )
        for pa in (idents.get("mapped_only") or [])[:40]:
            lines.append(f"- `{pa}`")
        extra = max(0, len(idents.get("mapped_only") or []) - 40)
        if extra:
            lines.append(f"- … +{extra} more (see JSON)")

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- JSON: `{OUT_JSON}`",
            f"- MD: `{OUT_MD}`",
            f"- Helper: `tools/diagnostics/_build_mscrenoship_io_gui_l5x_parity.py`",
            "",
            "Production decoder was **not** changed; recommended gates are recorded above.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    payload = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(render_md(payload), encoding="utf-8")
    s = payload["summary"]
    print(
        json.dumps(
            {
                "ok": payload.get("ok"),
                "out_json": str(OUT_JSON),
                "out_md": str(OUT_MD),
                "gui_claimed": s.get("gui_assigned_claimed_n"),
                "l5x_unique_named": s.get("l5x_unique_named_physical_n"),
                "claimed_only": s.get("claimed_only_n"),
                "mapped_only": s.get("mapped_only_n"),
                "dup_physical": s.get("l5x_duplicate_physical_n"),
                "dup_classes": s.get("dup_classification_counts"),
                "modules_count_mismatch": s.get("modules_count_mismatch"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
