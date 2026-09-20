#!/usr/bin/env python3
"""Exact EIPModules → EIPAdapters → eipcfg identity bridge.

Chain (PROVEN only when all stages succeed uniquely):

  EIPModules.Adapter
      == EIPAdapters.Name          (exact; safe case/whitespace normalize)
  EIPAdapters.TargetIP
      == eipcfg Adapter.targetip   (exact)
  TargetIP identifies exactly one active eipcfg adapter

Substring/name similarity is NEVER upgraded to PROVEN.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fortna_asc import read_asc


STATUS_PROVEN = "PROVEN"
STATUS_DERIVED = "DERIVED"
STATUS_REVIEW = "REVIEW_REQUIRED"
STATUS_UNKNOWN = "UNKNOWN"


def _norm_name(s: str) -> str:
    """Safe identity normalize: strip + casefold. No hyphen/underscore rewrite."""
    return (s or "").strip().casefold()


def _norm_ip(s: str) -> str:
    return (s or "").strip()


@dataclass
class EIPAdapterBridgeEvidence:
    eipmodules_adapter_name: str = ""
    eipadapters_name: str = ""
    target_ip: str = ""
    eipcfg_adapter_name: str = ""
    eipcfg_target_ip: str = ""
    match_stage_1: str = ""  # EXACT_NAME | NO_NAME_MATCH | AMBIGUOUS_NAME
    match_stage_2: str = ""  # EXACT_IP | NO_IP_MATCH | AMBIGUOUS_IP | MISSING_IP
    source_refs: list[str] = field(default_factory=list)
    confidence: str = STATUS_UNKNOWN
    status: str = STATUS_UNKNOWN
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _find_eipadapters(run_dir: Path, machine: str = "") -> Path | None:
    proj = run_dir / "PROJECT"
    if not proj.is_dir():
        return None
    mach = (machine or "").strip()
    candidates: list[Path] = []
    if mach:
        candidates.append(proj / f"EIPAdapters.asc.{mach}")
    candidates.extend(sorted(proj.glob("EIPAdapters.asc*")))
    for p in candidates:
        if p.is_file():
            return p
    return None


def load_eipadapters_rows(run_dir: Path, machine: str = "") -> list[dict[str, Any]]:
    path = _find_eipadapters(run_dir, machine)
    if not path:
        return []
    try:
        _, rows = read_asc(path)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        name = (r.get("Name") or "").strip()
        if not name or name.upper() in ("N/A", "INVALID"):
            continue
        ip = (r.get("TargetIP") or "").strip()
        if not ip or ip.isspace():
            ip = ""
        out.append(
            {
                "name": name,
                "target_ip": ip,
                "rack": (r.get("Rack") or "").strip(),
                "ttl_modules": r.get("TtlModules"),
                "input_address": r.get("InputAddress") or "",
                "output_address": r.get("OutputAddress") or "",
                "source_path": str(path),
            }
        )
    return out


def build_adapter_bridges(
    *,
    eipmodules_adapter_names: list[str],
    eipadapters_rows: list[dict[str, Any]],
    eipcfg_adapters: list[dict[str, Any]],
) -> dict[str, EIPAdapterBridgeEvidence]:
    """Build exact bridges keyed by EIPModules.Adapter name (raw)."""
    by_ad_name: dict[str, list[dict[str, Any]]] = {}
    for row in eipadapters_rows:
        key = _norm_name(row.get("name") or "")
        if key:
            by_ad_name.setdefault(key, []).append(row)

    by_ip: dict[str, list[dict[str, Any]]] = {}
    for ad in eipcfg_adapters:
        ip = _norm_ip(ad.get("targetip") or ad.get("ip") or "")
        if ip:
            by_ip.setdefault(ip, []).append(ad)

    results: dict[str, EIPAdapterBridgeEvidence] = {}
    for raw_name in sorted({(n or "").strip() for n in eipmodules_adapter_names if (n or "").strip()}):
        ev = EIPAdapterBridgeEvidence(
            eipmodules_adapter_name=raw_name,
            source_refs=["EIPModules.Adapter", "EIPAdapters.Name", "EIPAdapters.TargetIP", "eipcfg.targetip"],
        )
        name_hits = by_ad_name.get(_norm_name(raw_name)) or []
        if not name_hits:
            ev.match_stage_1 = "NO_NAME_MATCH"
            ev.status = STATUS_UNKNOWN
            ev.confidence = STATUS_UNKNOWN
            ev.reason = "eipmodules_adapter_not_in_eipadapters"
            results[raw_name] = ev
            continue
        if len(name_hits) > 1:
            # Identical names — still OK if they share one TargetIP
            ips = {_norm_ip(h.get("target_ip") or "") for h in name_hits}
            ips.discard("")
            if len(ips) != 1:
                ev.match_stage_1 = "AMBIGUOUS_NAME"
                ev.status = STATUS_REVIEW
                ev.confidence = STATUS_REVIEW
                ev.reason = "multiple_eipadapters_rows_different_ips"
                results[raw_name] = ev
                continue
        hit = name_hits[0]
        ev.eipadapters_name = hit.get("name") or ""
        ev.target_ip = _norm_ip(hit.get("target_ip") or "")
        ev.match_stage_1 = "EXACT_NAME"
        if not ev.target_ip:
            ev.match_stage_2 = "MISSING_IP"
            ev.status = STATUS_REVIEW
            ev.confidence = STATUS_REVIEW
            ev.reason = "eipadapters_targetip_missing"
            results[raw_name] = ev
            continue
        ip_hits = by_ip.get(ev.target_ip) or []
        if not ip_hits:
            ev.match_stage_2 = "NO_IP_MATCH"
            ev.status = STATUS_UNKNOWN
            ev.confidence = STATUS_UNKNOWN
            ev.reason = "eipadapters_targetip_not_in_eipcfg"
            results[raw_name] = ev
            continue
        if len(ip_hits) > 1:
            ev.match_stage_2 = "AMBIGUOUS_IP"
            ev.status = STATUS_REVIEW
            ev.confidence = STATUS_REVIEW
            ev.reason = "targetip_matches_multiple_eipcfg_adapters"
            results[raw_name] = ev
            continue
        eipcfg = ip_hits[0]
        ev.eipcfg_adapter_name = (eipcfg.get("name") or "").strip()
        ev.eipcfg_target_ip = _norm_ip(eipcfg.get("targetip") or eipcfg.get("ip") or "")
        ev.match_stage_2 = "EXACT_IP"
        ev.status = STATUS_PROVEN
        ev.confidence = STATUS_PROVEN
        ev.reason = "exact_name_and_unique_targetip"
        results[raw_name] = ev
    return results


def enrich_adapters_via_exact_bridge(
    adapters: list[dict[str, Any]],
    eip_rows: list[dict[str, Any]],
    eipadapters_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Attach EIPModules banks onto eipcfg modules using exact IP bridge first.

    Sets per-module:
      bank_join: exact_ip_bridge | exact_name | substring | none
      adapter_bridge_status: PROVEN | DERIVED | REVIEW_REQUIRED | UNKNOWN
      adapter_bridge: evidence dict

    Returns summary stats.
    """
    mod_adapter_names = sorted({(r.get("adapter") or "").strip() for r in eip_rows if (r.get("adapter") or "").strip()})
    bridges = build_adapter_bridges(
        eipmodules_adapter_names=mod_adapter_names,
        eipadapters_rows=eipadapters_rows,
        eipcfg_adapters=adapters,
    )

    # EIPModules rows keyed by logical adapter name
    by_logical: dict[str, list[dict[str, Any]]] = {}
    for r in eip_rows:
        ad = (r.get("adapter") or "").strip()
        if ad:
            by_logical.setdefault(ad, []).append(r)

    # Map eipcfg adapter object id / name → proven logical EIPModules adapter name
    eipcfg_to_logical: dict[str, str] = {}
    for logical, ev in bridges.items():
        if ev.status == STATUS_PROVEN and ev.eipcfg_adapter_name:
            eipcfg_to_logical[ev.eipcfg_adapter_name] = logical
            # also key by targetip uniqueness already proven
            eipcfg_to_logical[f"ip:{ev.target_ip}"] = logical

    # Fallback indexes for non-proven paths (exact name / substring)
    by_adapter_keys: dict[str, list[dict[str, Any]]] = {}
    all_keys: list[str] = []
    for row in eip_rows:
        ad = (row.get("adapter") or "").strip()
        if not ad:
            continue
        by_adapter_keys.setdefault(ad, []).append(row)
        by_adapter_keys.setdefault(ad.replace("-", "_"), []).append(row)
        by_adapter_keys.setdefault(ad.replace("_", "-"), []).append(row)
        if ad not in all_keys:
            all_keys.append(ad)

    stats = {
        "proven_bridge": 0,
        "exact_name_fallback": 0,
        "substring_fallback": 0,
        "unjoined": 0,
        "bridges": {k: v.to_dict() for k, v in bridges.items()},
    }

    for ad in adapters:
        name = (ad.get("name") or "").strip()
        rio = (ad.get("rio_name") or "").strip()
        ip = _norm_ip(ad.get("targetip") or ad.get("ip") or "")
        mods = ad.get("modules") or []

        rows: list[dict[str, Any]] = []
        join = "none"
        bridge_ev: EIPAdapterBridgeEvidence | None = None
        bridge_status = STATUS_UNKNOWN

        # --- Stage A: exact IP bridge (PROVEN) ---
        logical = eipcfg_to_logical.get(name) or (eipcfg_to_logical.get(f"ip:{ip}") if ip else None)
        if logical:
            bridge_ev = bridges.get(logical)
            if bridge_ev and bridge_ev.status == STATUS_PROVEN:
                rows = by_logical.get(logical) or []
                join = "exact_ip_bridge"
                bridge_status = STATUS_PROVEN
                stats["proven_bridge"] += 1

        # --- Stage B: exact adapter name match (still PROVEN for name, weaker than IP bridge) ---
        if not rows:
            rows = by_adapter_keys.get(name) or by_adapter_keys.get(name.replace("_", "-")) or []
            if rows:
                join = "exact_name"
                bridge_status = STATUS_PROVEN
                # attach matching bridge evidence if any
                bridge_ev = bridges.get(name) or bridges.get(name.replace("_", "-")) or bridge_ev
                stats["exact_name_fallback"] += 1

        # --- Stage C: substring (DERIVED only — never PROVEN) ---
        if not rows:
            soft_key = None
            for key in all_keys:
                ku = key.upper().replace("_", "-")
                for cand in (name, rio):
                    cu = (cand or "").upper().replace("_", "-")
                    if cu and (cu in ku or ku in cu):
                        soft_key = key
                        break
                if soft_key:
                    break
            if soft_key:
                rows = by_logical.get(soft_key) or by_adapter_keys.get(soft_key) or []
                join = "substring"
                bridge_status = STATUS_DERIVED
                bridge_ev = bridges.get(soft_key)
                stats["substring_fallback"] += 1

        if not rows:
            stats["unjoined"] += 1
            ad["adapter_bridge_status"] = STATUS_UNKNOWN
            ad["bank_join"] = "none"
            continue

        ad["adapter_bridge_status"] = bridge_status
        ad["bank_join"] = join
        if bridge_ev:
            ad["adapter_bridge"] = bridge_ev.to_dict()

        by_slot = {int(r.get("slot") or -1): r for r in rows}
        for mod in mods:
            if (mod.get("connection") or "").upper() == "HEADNODE":
                continue
            try:
                slot = int(mod.get("slot") or -1)
            except (TypeError, ValueError):
                continue
            hit = by_slot.get(slot)
            if not hit:
                continue
            if hit.get("input_bank") is not None:
                mod["input_bank"] = int(hit["input_bank"])
            if hit.get("output_bank") is not None:
                mod["output_bank"] = int(hit["output_bank"])
            mod["bank_join"] = join
            mod["adapter_bridge_status"] = bridge_status
            if bridge_ev:
                mod["adapter_bridge"] = bridge_ev.to_dict()
            # Prefer EIPModules.Type as authoritative hardware type
            if hit.get("type"):
                mod["eipmodules_type"] = hit["type"]
                if (mod.get("type") or "").strip() and (mod.get("type") or "").strip().upper() != (
                    hit["type"] or ""
                ).strip().upper():
                    mod["alias_catalog_mismatch"] = {
                        "eipcfg_or_name_type": mod.get("type"),
                        "eipmodules_type": hit["type"],
                        "classification": "ALIAS_CATALOG_MISMATCH",
                    }

    return stats
