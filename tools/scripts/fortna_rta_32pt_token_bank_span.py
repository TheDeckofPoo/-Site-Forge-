#!/usr/bin/env python3
"""Shadow + optional production helper: RTA 32-pt token mid-span bank join.

Rule id: rta_32pt_token_direct_bank_span_match

Configio Desc forms like IB32DATA-61 / OB32PDATA-87 are not Rockwell catalog
strings. Exact bank==InputBank/OutputBank misses mid-span banks inside the
module DirectSize window (IB32 DirectIn=8 → banks base..base+7).

This module:
  - parses the token Desc
  - finds the unique EIPModules card whose direction bank span covers Configio.Bank
  - exposes shadow_resolve_run() (no production mutation)
  - optionally participates in PhysicalWordResolver when ENABLE_IN_PHYSICAL_WORD_RESOLVER

Do NOT treat ENABLE_IN_PHYSICAL_WORD_RESOLVER=True as silent promotion into
generic bank_match — assign_how remains the explicit candidate marker.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ASSIGN_HOW = "rta_32pt_token_direct_bank_span_match"
RULE_ID = "rta_32pt_token_direct_bank_span_match"

# Production path enabled after CP1 shadow PASS (46/46 token words would-bind;
# ASSIGNED 297→842). Still a named candidate rule — not a silent generic bank_match.
# Human may disable if corpus shadow finds counterexamples.
ENABLE_IN_PHYSICAL_WORD_RESOLVER = True

_TOKEN_RE = re.compile(
    r"^(?P<tok>IB32|OB32P)(?P<role>DATA|STATUS)-(?P<idx>\d+)$",
    re.I,
)

# tok → (catalog, direction, fallback Direct*Size for that direction)
_TOKEN_MAP: dict[str, tuple[str, str, int]] = {
    "IB32": ("1794-IB32", "I", 8),
    "OB32P": ("1794-OB32P", "O", 4),
}


def parse_32pt_token_desc(desc: str) -> dict[str, Any] | None:
    """Parse IB32DATA-61 / OB32PDATA-87 / IB32STATUS-141."""
    d = (desc or "").strip()
    if not d:
        return None
    m = _TOKEN_RE.match(d)
    if not m:
        return None
    tok = m.group("tok").upper()
    if tok not in _TOKEN_MAP:
        return None
    catalog, direction, fallback_span = _TOKEN_MAP[tok]
    return {
        "tok": tok,
        "role": m.group("role").upper(),
        "idx": int(m.group("idx")),
        "catalog": catalog,
        "direction": direction,
        "fallback_direct_size": fallback_span,
        "raw": d,
    }


def _module_dir_bank(mod: dict[str, Any], direction: str) -> int:
    """Prefer raw bank; fall back to effective_* when raw is 0."""
    which = "I" if direction == "I" else "O"
    raw_key = "input_bank" if which == "I" else "output_bank"
    eff_key = "effective_input_bank" if which == "I" else "effective_output_bank"
    try:
        raw = int(mod.get(raw_key)) if mod.get(raw_key) is not None else 0
    except (TypeError, ValueError):
        raw = 0
    if raw > 0:
        return raw
    try:
        eff = int(mod.get(eff_key)) if mod.get(eff_key) is not None else -1
    except (TypeError, ValueError):
        eff = -1
    return eff if eff >= 0 else raw


def _direct_span_for_module(
    mod: dict[str, Any], *, direction: str, fallback: int
) -> int:
    """DirectInputSize for I, DirectOutputSize for O; else token fallback."""
    key = "direct_input_size" if direction == "I" else "direct_output_size"
    try:
        v = int(mod.get(key)) if mod.get(key) is not None else 0
    except (TypeError, ValueError):
        v = 0
    if v > 0:
        return v
    return int(fallback) if fallback > 0 else 0


def _catalog_matches(mod_type: str, expected: str, tok: str) -> bool:
    mt = (mod_type or "").upper()
    cat = (expected or "").upper()
    if not mt:
        return False
    if cat and (cat == mt or cat in mt or mt in cat):
        return True
    # Token corroboration when type is 1794-IB32 / 1794-OB32P
    return bool(tok) and tok.upper() in mt


def module_bit_base_for_span(
    *,
    bank: int,
    span_base: int,
    span_size: int,
    capacity: int = 32,
) -> int:
    """Map Configio bank within Direct*Size span → module bit base (0 or 16…).

    Fortna Low+High consume two consecutive banks per 16 module bits.
    When the Direct span holds more pairs than capacity/16 (IB32 DirectIn=8 →
    4 pairs, 32-pt → 2 words), align to the trailing pairs (DATA/STATUS live
    at the end of the window on CP1).
    """
    try:
        b = int(bank)
        base = int(span_base)
        span = int(span_size)
        cap = int(capacity) if capacity and int(capacity) > 0 else 32
    except (TypeError, ValueError):
        return 0
    if span <= 0 or b < base:
        return 0
    pair_index = (b - base) // 2
    n_module_words = max(1, cap // 16)
    pairs_in_span = max(1, span // 2)
    if pairs_in_span > n_module_words:
        data_pair0 = pairs_in_span - n_module_words
        module_word = pair_index - data_pair0
    else:
        module_word = pair_index
    if module_word < 0:
        module_word = 0
    if module_word >= n_module_words:
        module_word = n_module_words - 1
    return int(module_word) * 16


def try_rta_32pt_token_direct_bank_span_match(
    desc: str,
    bank: int,
    adapters: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Unique module whose direction bank span covers Configio bank, or None.

    Span: [dir_bank, dir_bank + direct_size).
    """
    parsed = parse_32pt_token_desc(desc)
    if not parsed:
        return None
    try:
        bank_i = int(bank)
    except (TypeError, ValueError):
        return None
    if bank_i < 0:
        return None

    catalog = parsed["catalog"]
    direction = parsed["direction"]
    tok = parsed["tok"]
    fallback = parsed["fallback_direct_size"]
    hits: list[dict[str, Any]] = []

    for ad in adapters or []:
        for mod in ad.get("modules") or []:
            if (mod.get("connection") or "").upper() == "HEADNODE":
                continue
            mt = str(mod.get("type") or "")
            if "AENT" in mt.upper():
                continue
            if not _catalog_matches(mt, catalog, tok):
                continue
            dir_bank = _module_dir_bank(mod, direction)
            if direction == "I" and dir_bank <= 0:
                continue
            if direction == "O" and dir_bank < 0:
                continue
            span = _direct_span_for_module(
                mod, direction=direction, fallback=fallback
            )
            if span <= 0:
                continue
            if not (dir_bank <= bank_i < dir_bank + span):
                continue
            try:
                from fortna_hardware_family import channel_capacity_for_catalog

                cap = channel_capacity_for_catalog(mt) or 32
            except Exception:
                cap = 32
            bit_base = module_bit_base_for_span(
                bank=bank_i,
                span_base=dir_bank,
                span_size=span,
                capacity=cap,
            )
            hits.append(
                {
                    **mod,
                    "adapter_name": ad.get("name"),
                    "rio_name": ad.get("rio_name") or ad.get("name"),
                    "panel": ad.get("panel") or "",
                    "adapter_index": ad.get("adapter_index"),
                    "targetip": ad.get("targetip"),
                    "direction": direction,
                    "assign_how": ASSIGN_HOW,
                    "span_base_bank": dir_bank,
                    "span_size": span,
                    "configio_bank": bank_i,
                    "module_bit_base": bit_base,
                    "token_parsed": parsed,
                }
            )

    if len(hits) != 1:
        return None
    return hits[0]


def shadow_resolve_run(run_dir: Path, machine: str) -> dict[str, Any]:
    """Report how many currently-unresolved words this rule would bind.

    Does not mutate production PhysicalWordResolver state. Loads Configio +
    eipcfg/EIPModules via existing helpers.
    """
    from fortna_physical_word_resolver import PhysicalWordResolver

    run_dir = Path(run_dir)
    pwr = PhysicalWordResolver(run_dir, machine)
    pm = pwr.physical_map or {}
    adapters = list(pm.get("adapters") or [])
    # Prefer full topology adapters (carry banks / direct sizes)
    topo = pwr.topology or {}
    if topo.get("adapters"):
        adapters = list(topo.get("adapters") or [])

    unresolved = list(pm.get("unresolved") or [])
    words = pm.get("words") or {}
    would_bind: list[dict[str, Any]] = []
    skipped_ambiguous_or_miss = 0

    for row in unresolved:
        if str(row.get("reason") or "") not in (
            "no_eipmodules_bank_match",
            "",
        ) and row.get("reason") not in (None, "no_eipmodules_bank_match"):
            # Still try token Descs on any unresolved row
            pass
        w = row.get("octal_word")
        hit = None
        used_desc = ""
        used_bank = None
        for desc_key, bank_key in (
            ("low_desc", "low_bank"),
            ("high_desc", "high_bank"),
        ):
            desc = str(row.get(desc_key) or "")
            # Banks may only live on word entry; fall back to Configio via desc parse path
            bank = row.get(bank_key)
            if bank is None and w is not None and str(w) in words:
                bank = words[str(w)].get(bank_key)
            if bank is None:
                # unresolved rows don't always carry banks — probe topology Configio
                bank = _configio_bank_for_word_desc(pwr, w, desc)
            if not desc or bank is None:
                continue
            cand = try_rta_32pt_token_direct_bank_span_match(desc, int(bank), adapters)
            if cand:
                hit = cand
                used_desc = desc
                used_bank = int(bank)
                break
        if hit:
            would_bind.append(
                {
                    "octal_word": w,
                    "desc": used_desc,
                    "configio_bank": used_bank,
                    "module_name": hit.get("name"),
                    "type": hit.get("type"),
                    "direction": hit.get("direction"),
                    "span_base_bank": hit.get("span_base_bank"),
                    "span_size": hit.get("span_size"),
                    "assign_how": ASSIGN_HOW,
                    "rio_name": hit.get("rio_name"),
                }
            )
        else:
            # Only count token-shaped Descs as applicable misses
            low = str(row.get("low_desc") or "")
            high = str(row.get("high_desc") or "")
            if parse_32pt_token_desc(low) or parse_32pt_token_desc(high):
                skipped_ambiguous_or_miss += 1

    token_unresolved = sum(
        1
        for row in unresolved
        if parse_32pt_token_desc(str(row.get("low_desc") or ""))
        or parse_32pt_token_desc(str(row.get("high_desc") or ""))
    )

    return {
        "rule_id": RULE_ID,
        "assign_how": ASSIGN_HOW,
        "machine": machine,
        "run_dir": str(run_dir),
        "enable_in_resolver": ENABLE_IN_PHYSICAL_WORD_RESOLVER,
        "unresolved_total": len(unresolved),
        "token_unresolved": token_unresolved,
        "would_bind_count": len(would_bind),
        "token_miss_or_ambiguous": skipped_ambiguous_or_miss,
        "would_bind": would_bind,
        "assigned_words": len(words),
        "note": "shadow only — production path gated by ENABLE_IN_PHYSICAL_WORD_RESOLVER",
    }


def _configio_bank_for_word_desc(
    pwr: Any, word: Any, desc: str
) -> int | None:
    """Look up Configio bank for an octal word + Desc from resolver topology load."""
    try:
        from fortna_physical_word_resolver import _load_configio_rows
    except Exception:
        return None
    try:
        w_i = int(word)
    except (TypeError, ValueError):
        return None
    desc_u = (desc or "").strip().upper()
    if not desc_u:
        return None
    for row in _load_configio_rows(pwr.run_dir, pwr.machine) or []:
        try:
            if int(row.get("octal_word")) != w_i:
                continue
        except (TypeError, ValueError):
            continue
        if str(row.get("desc") or "").strip().upper() != desc_u:
            continue
        try:
            return int(row.get("bank"))
        except (TypeError, ValueError):
            return None
    return None


def apply_to_unresolved_word(
    low_desc: str,
    high_desc: str,
    low_bank: int | None,
    high_bank: int | None,
    adapters: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Try Low then High Desc/bank for a unique span hit."""
    for desc, bank in ((low_desc, low_bank), (high_desc, high_bank)):
        if not desc or bank is None:
            continue
        try:
            b = int(bank)
        except (TypeError, ValueError):
            continue
        hit = try_rta_32pt_token_direct_bank_span_match(desc, b, adapters)
        if hit:
            return hit
    return None


__all__ = [
    "ASSIGN_HOW",
    "RULE_ID",
    "ENABLE_IN_PHYSICAL_WORD_RESOLVER",
    "parse_32pt_token_desc",
    "module_bit_base_for_span",
    "try_rta_32pt_token_direct_bank_span_match",
    "apply_to_unresolved_word",
    "shadow_resolve_run",
]
