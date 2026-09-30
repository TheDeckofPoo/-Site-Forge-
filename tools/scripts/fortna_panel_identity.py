#!/usr/bin/env python3
"""General panel ↔ adapter identity resolver (ORI-073).

Derives aliases from CURRENT RUN evidence only:
  Configio panel-token bank sets ↔ eipcfg adapter address envelopes + module banks.

Never hard-codes site names (EP*, AENTR*, MSC Reno, …).
Name similarity alone is insufficient.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any


_PANEL_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9]{1,15}$")


@dataclass
class PanelAdapterAlias:
    panel_token: str
    adapter_name: str
    rio_name: str = ""
    target_ip: str = ""
    status: str = "INSUFFICIENT"  # PROVEN | DERIVED | REVIEW_REQUIRED | CONFLICT | INSUFFICIENT
    confidence: float = 0.0
    provenance: list[dict[str, Any]] = field(default_factory=list)
    evidence_scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm_token(text: str) -> str:
    return str(text or "").strip().upper().replace("-", "_")


def is_bare_panel_token(text: str) -> bool:
    """True when Desc is a short panel id (EP1, PNALN, RIO52) — not a catalog Desc."""
    u = _norm_token(text)
    if not u or not _PANEL_TOKEN_RE.fullmatch(u):
        return False
    # Catalog-ish: 1734-OA4 / 1794-IA16
    if re.search(r"\d{4}", u):
        return False
    if re.search(r"(IA|IB|IM|OA|OB|OW|AENT)\d", u):
        return False
    return True


def _direction_from_in_out(mask: Any) -> str:
    try:
        from fortna_configio_direction import direction_from_in_out_mask

        mi = direction_from_in_out_mask(mask)
        d = str((mi or {}).get("direction") or "").upper()
        if d in ("I", "O"):
            return d
    except Exception:
        pass
    s = str(mask or "")
    if "1" in s:
        return "O"
    return "I"


def _module_is_output(mod: dict[str, Any]) -> bool:
    mt = (mod.get("type") or mod.get("catalog") or mod.get("name") or "").upper()
    d = (mod.get("direction") or "").upper()
    if d == "O":
        return True
    if d == "I":
        return False
    return any(x in mt for x in ("OA", "OB", "OW"))


def _module_is_input(mod: dict[str, Any]) -> bool:
    mt = (mod.get("type") or mod.get("catalog") or mod.get("name") or "").upper()
    d = (mod.get("direction") or "").upper()
    if d == "I":
        return True
    if d == "O":
        return False
    return any(x in mt for x in ("IA", "IB", "IM"))


def _bank_int(mod: dict[str, Any], which: str) -> int | None:
    """Return explicit bank including 0; None when unset."""
    key = "input_bank" if which.upper().startswith("I") else "output_bank"
    eff = (
        "effective_input_bank"
        if which.upper().startswith("I")
        else "effective_output_bank"
    )
    raw = mod.get(key)
    if raw is None or raw == "":
        pass
    else:
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            pass
    # FLEX effective banks only when raw unset
    ev = mod.get(eff)
    if ev is None or ev == "":
        return None
    try:
        return int(float(ev))
    except (TypeError, ValueError):
        return None


def adapter_bank_sets(adapter: dict[str, Any]) -> dict[str, set[int]]:
    """Collect input/output bank sets for bridged modules on one adapter."""
    ib: set[int] = set()
    ob: set[int] = set()
    for mod in adapter.get("modules") or []:
        conn = (mod.get("connection") or "").upper()
        mt = (mod.get("type") or "").upper()
        if conn == "HEADNODE" or (mt.startswith("1734-AENT") or mt.startswith("1794-AENT")):
            if "AENT" in mt and not any(x in mt for x in ("IA", "IB", "OA", "OB")):
                continue
        if _module_is_input(mod):
            b = _bank_int(mod, "I")
            if b is not None and b >= 0:
                ib.add(b)
        if _module_is_output(mod):
            b = _bank_int(mod, "O")
            if b is not None and b >= 0:
                ob.add(b)
    # Envelope fallback from adapter addresses when modules lack banks
    try:
        in_addr = int(float(adapter.get("input_address") or -1))
    except (TypeError, ValueError):
        in_addr = -1
    try:
        out_addr = int(float(adapter.get("output_address") or -1))
    except (TypeError, ValueError):
        out_addr = -1
    if not ib and in_addr >= 0:
        # POINT head status span: first discrete often InputAddress+8
        pass
    if not ob and out_addr >= 0:
        n_out = sum(1 for m in (adapter.get("modules") or []) if _module_is_output(m))
        if n_out:
            ob = set(range(out_addr, out_addr + n_out))
    if not ib and in_addr > 0:
        n_in = sum(1 for m in (adapter.get("modules") or []) if _module_is_input(m))
        first = in_addr + 8
        if n_in:
            ib = set(range(first, first + n_in))
    return {"I": ib, "O": ob}


def configio_panel_bank_sets(
    configio_rows: list[dict[str, Any]],
) -> dict[str, dict[str, set[int]]]:
    """Group Configio rows by bare panel Desc → {I: banks, O: banks}."""
    out: dict[str, dict[str, set[int]]] = {}
    for row in configio_rows or []:
        desc = str(row.get("desc") or "").strip()
        if not is_bare_panel_token(desc):
            # Also accept already-tokenized panel field
            panel = str(row.get("panel") or "").strip()
            if not is_bare_panel_token(panel):
                continue
            desc = panel
        token = _norm_token(desc)
        try:
            bank = int(row.get("bank"))
        except (TypeError, ValueError):
            continue
        if bank < 0:
            continue
        direction = _direction_from_in_out(row.get("in_out"))
        slot = out.setdefault(token, {"I": set(), "O": set()})
        slot[direction].add(bank)
    return out


def _unique_cover(
    panel_banks: dict[str, set[int]],
    adapters: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Return adapter that uniquely covers panel I+O bank sets."""
    covers: list[dict[str, Any]] = []
    p_i = panel_banks.get("I") or set()
    p_o = panel_banks.get("O") or set()
    if not p_i and not p_o:
        return None, []
    for ad in adapters:
        sets = adapter_bank_sets(ad)
        a_i, a_o = sets["I"], sets["O"]
        if p_i and not p_i.issubset(a_i):
            continue
        if p_o and not p_o.issubset(a_o):
            continue
        # Require at least one non-empty side to actually touch
        if not ((p_i and p_i & a_i) or (p_o and p_o & a_o)):
            continue
        covers.append(ad)
    if len(covers) == 1:
        return covers[0], covers
    return None, covers


def build_panel_identity_model(
    *,
    adapters: list[dict[str, Any]],
    configio_rows: list[dict[str, Any]],
    machine: str = "",
    eipcfg_path: str = "",
) -> dict[str, Any]:
    """Build panel-token ↔ adapter aliases with provenance.

    PROVEN when a panel's Configio bank sets uniquely cover exactly one adapter
    (I and/or O) with sufficient cardinality.
    """
    panel_banks = configio_panel_bank_sets(configio_rows)
    aliases: list[PanelAdapterAlias] = []
    conflicts: list[dict[str, Any]] = []
    insufficient: list[dict[str, Any]] = []

    # Index: panel_token -> alias
    by_panel: dict[str, PanelAdapterAlias] = {}
    # Index: adapter_name -> panel tokens
    by_adapter: dict[str, list[str]] = defaultdict(list)

    for token, banks in sorted(panel_banks.items()):
        p_i, p_o = banks.get("I") or set(), banks.get("O") or set()
        cardinality = len(p_i) + len(p_o)
        unique, covers = _unique_cover(banks, adapters)

        prov: list[dict[str, Any]] = [
            {
                "signal": "configio_panel_banks",
                "ref": f"Configio panel token {token}",
                "fact": f"I={sorted(p_i)} O={sorted(p_o)}",
            }
        ]
        if eipcfg_path:
            prov.append(
                {
                    "signal": "machine_eipcfg",
                    "ref": eipcfg_path,
                    "fact": f"active_machine={machine or '?'}",
                }
            )

        if unique is None:
            if len(covers) > 1:
                conflicts.append(
                    {
                        "panel_token": token,
                        "reason": "multiple_adapter_bank_covers",
                        "candidates": [a.get("name") for a in covers],
                        "banks": {"I": sorted(p_i), "O": sorted(p_o)},
                    }
                )
                alias = PanelAdapterAlias(
                    panel_token=token,
                    adapter_name="",
                    status="CONFLICT",
                    confidence=0.0,
                    provenance=prov
                    + [
                        {
                            "signal": "bank_range_cover",
                            "ref": "adapter module banks",
                            "fact": f"ambiguous covers={[a.get('name') for a in covers]}",
                        }
                    ],
                )
            else:
                insufficient.append(
                    {
                        "panel_token": token,
                        "reason": "no_unique_adapter_bank_cover",
                        "banks": {"I": sorted(p_i), "O": sorted(p_o)},
                    }
                )
                alias = PanelAdapterAlias(
                    panel_token=token,
                    adapter_name="",
                    status="INSUFFICIENT",
                    confidence=0.0,
                    provenance=prov,
                )
            aliases.append(alias)
            by_panel[token] = alias
            continue

        # Sufficiency: prefer both sides, or >=2 banks on one side
        both_sides = bool(p_i) and bool(p_o)
        strong = both_sides or cardinality >= 2
        ad_sets = adapter_bank_sets(unique)
        prov.append(
            {
                "signal": "bank_range_unique_cover",
                "ref": f"adapter {unique.get('name')}",
                "fact": (
                    f"panel I={sorted(p_i)} O={sorted(p_o)} ⊆ "
                    f"adapter I={sorted(ad_sets['I'])} O={sorted(ad_sets['O'])}"
                ),
            }
        )
        tip = str(unique.get("targetip") or "")
        if tip:
            prov.append(
                {
                    "signal": "adapter_address_envelope",
                    "ref": f"eipcfg Adapter {unique.get('name')}",
                    "fact": (
                        f"targetip={tip} "
                        f"InputAddress={unique.get('input_address')} "
                        f"OutputAddress={unique.get('output_address')}"
                    ),
                }
            )
        # Module-count corroboration
        n_in = sum(1 for m in (unique.get("modules") or []) if _module_is_input(m))
        n_out = sum(1 for m in (unique.get("modules") or []) if _module_is_output(m))
        if (p_i and len(p_i) == n_in) or (p_o and len(p_o) == n_out):
            prov.append(
                {
                    "signal": "module_tree_count",
                    "ref": f"adapter {unique.get('name')} module tree",
                    "fact": f"panel_banks I={len(p_i)}/{n_in} O={len(p_o)}/{n_out}",
                }
            )
            strong = True

        status = "PROVEN" if strong else "DERIVED"
        alias = PanelAdapterAlias(
            panel_token=token,
            adapter_name=str(unique.get("name") or ""),
            rio_name=str(unique.get("rio_name") or unique.get("name") or ""),
            target_ip=tip,
            status=status,
            confidence=0.95 if status == "PROVEN" else 0.7,
            provenance=prov,
            evidence_scores={
                "bank_cover": 1.0,
                "cardinality": float(cardinality),
                "both_sides": 1.0 if both_sides else 0.0,
            },
        )
        aliases.append(alias)
        by_panel[token] = alias
        by_adapter[alias.adapter_name].append(token)

    return {
        "ok": True,
        "machine": machine,
        "eipcfg_path": eipcfg_path,
        "aliases": [a.to_dict() for a in aliases],
        "by_panel": {k: v.to_dict() for k, v in by_panel.items()},
        "by_adapter": dict(by_adapter),
        "conflicts": conflicts,
        "insufficient": insufficient,
        "panel_banks": {
            k: {"I": sorted(v.get("I") or []), "O": sorted(v.get("O") or [])}
            for k, v in panel_banks.items()
        },
    }


def panels_equivalent(
    a: str,
    b: str,
    *,
    alias_model: dict[str, Any] | None,
) -> bool:
    """True when tokens are identical or PROVEN/DERIVED aliases of each other."""
    ta, tb = _norm_token(a), _norm_token(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    if not alias_model:
        return False
    by_panel = alias_model.get("by_panel") or {}
    # panel → adapter
    aa = by_panel.get(ta) or {}
    bb = by_panel.get(tb) or {}
    for side, other in ((aa, tb), (bb, ta)):
        st = str(side.get("status") or "")
        if st not in ("PROVEN", "DERIVED"):
            continue
        adn = _norm_token(side.get("adapter_name") or "")
        rio = _norm_token(side.get("rio_name") or "")
        if other and other in (adn, rio):
            return True
    # adapter name compared to panel token via reverse index
    by_ad = alias_model.get("by_adapter") or {}
    for ad_name, tokens in by_ad.items():
        adu = _norm_token(ad_name)
        toks = {_norm_token(t) for t in tokens}
        if ta in toks and tb == adu:
            # confirm status
            st = str((by_panel.get(ta) or {}).get("status") or "")
            if st in ("PROVEN", "DERIVED"):
                return True
        if tb in toks and ta == adu:
            st = str((by_panel.get(tb) or {}).get("status") or "")
            if st in ("PROVEN", "DERIVED"):
                return True
    return False


def apply_aliases_to_adapters(
    adapters: list[dict[str, Any]],
    alias_model: dict[str, Any],
) -> None:
    """Stamp adapter.panel from PROVEN/DERIVED aliases (in-place).

    Does NOT rename rio_name to the Configio panel token — Logix channels keep
    the eipcfg adapter identity (AENTR1, …). Panel is scope/alias only.
    If capacity-pack left a wrong panel-prefixed rio_name, restore eipcfg name.
    """
    by_ad = alias_model.get("by_adapter") or {}
    by_panel = alias_model.get("by_panel") or {}
    for ad in adapters or []:
        name = str(ad.get("name") or "")
        tokens = list(by_ad.get(name) or [])
        proven = [
            t
            for t in tokens
            if str((by_panel.get(t) or {}).get("status") or "") in ("PROVEN", "DERIVED")
        ]
        if not proven:
            continue
        panel = proven[0]
        ad["panel"] = panel
        ad["panel_aliases"] = proven
        ad["panel_identity_provenance"] = [
            by_panel.get(t) for t in proven if by_panel.get(t)
        ]
        # Preserve / restore eipcfg adapter name for channel rendering
        safe = re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_") or name
        rio = str(ad.get("rio_name") or "")
        # Wrong capacity-pack prefix (e.g. EP2RIO0 on AENTR1) → restore
        if not rio or any(
            rio.upper().startswith(t) and not rio.upper().startswith(safe.upper())
            for t in proven
        ):
            ad["rio_name"] = safe
            ad["naming_how"] = "panel_identity_eipcfg_name"
