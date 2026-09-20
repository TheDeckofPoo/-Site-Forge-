#!/usr/bin/env python3
"""Canonical HardwareIdentity — names are aliases, not truth.

Evidence precedence (discovered from RUN fixtures; no finished L5X):
  1. *-RTA*eipcfg.xml  — Adapter@targetip/name + Module@type/slot/connection
  2. EIPModules.asc[.MACHINE] — adapter, type/catalog, slot, input/output banks
  3. EIPAdapters / EIPCSV / EIPModuleType — corroboration
  4. Configio banks/interfaces/catalog-word-bank Desc — linkage hints
  5. IOCard.asc[.MACHINE] — interface aliases
  6. SystemFiles/hosts — IP ↔ hostname aliases only
  7. Human names (AENTR3, T_1794_AENT_3, …) — aliases only when corroborated

When high-quality sources disagree → HARDWARE_IDENTITY_CONFLICT (no silent pick).
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fortna_asc import read_asc
from fortna_hardware_family import (
    channel_capacity_for_catalog,
    detect_family_from_catalog,
)
from fortna_physical_word_resolver import (
    _find_eipcfg,
    _find_eipmodules,
    _load_eipmodules_rows,
    parse_eipcfg,
)

STATUS_PROVEN = "PROVEN"
STATUS_DERIVED = "DERIVED"
STATUS_REVIEW = "REVIEW_REQUIRED"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_CONFLICT = "HARDWARE_IDENTITY_CONFLICT"

EVIDENCE_PRECEDENCE = [
    "eipcfg_xml",
    "eipmodules",
    "eip_adapters_csv_moduletype",
    "configio",
    "iocard",
    "hosts_alias",
    "human_name_alias",
]


def _canon_id(*parts: Any) -> str:
    raw = "|".join(str(p).strip().upper() for p in parts if str(p).strip())
    return "hw_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _norm_name(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


@dataclass
class HardwareIdentity:
    canonical_id: str
    device_class: str  # adapter | module | unknown
    adapter_family: str = ""
    catalog_number: str = ""
    part_number: str = ""
    adapter_index: int | None = None
    physical_slot: int | None = None
    data_index: int | None = None
    direction: str = ""
    channel_capacity: int = 0
    ip_address: str = ""
    node: str = ""
    parent_canonical_id: str = ""
    source_names: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    confidence: str = "MEDIUM"
    status: str = STATUS_UNKNOWN
    machine: str = ""
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inventory_hardware_files(run_dir: Path, machine: str) -> list[dict[str, Any]]:
    """Inventory XML/ASC/hosts that may describe physical hardware."""
    run_dir = Path(run_dir)
    out: list[dict[str, Any]] = []
    patterns = [
        "**/*eipcfg*.xml",
        "**/*EIP*.asc*",
        "**/IOCard.asc*",
        "**/hosts*",
        "**/ABS_EIP*",
    ]
    seen: set[str] = set()
    for pat in patterns:
        for p in run_dir.glob(pat):
            if not p.is_file() or p.suffix.lower() == ".l5x":
                continue
            key = str(p.resolve())
            if key in seen:
                continue
            seen.add(key)
            rec: dict[str, Any] = {
                "path": str(p.relative_to(run_dir)).replace("\\", "/"),
                "abs_path": str(p),
                "size": p.stat().st_size,
                "file_type": p.suffix.lower() or "extless",
                "authority_candidate": False,
                "fields_found": [],
                "counts": {},
            }
            name_u = p.name.upper()
            try:
                if p.suffix.lower() == ".xml":
                    root = ET.parse(p).getroot()
                    rec["root_element"] = root.tag
                    ads = list(root.findall(".//Adapter"))
                    mods = list(root.findall(".//Module"))
                    rec["counts"] = {"adapters": len(ads), "modules": len(mods)}
                    fields = set()
                    for el in ads[:3] + mods[:5]:
                        fields.update(el.attrib.keys())
                    rec["fields_found"] = sorted(fields)
                    if ads or mods:
                        rec["authority_candidate"] = True
                        rec["authority_role"] = "eipcfg_xml"
                elif "EIPMODULE" in name_u:
                    rec["authority_candidate"] = True
                    rec["authority_role"] = "eipmodules"
                    rec["fields_found"] = [
                        "adapter", "type", "slot", "input_bank", "output_bank", "connection"
                    ]
                elif "EIPCFG" in name_u or "EIPADAPTER" in name_u or "EIPCSV" in name_u:
                    rec["authority_candidate"] = True
                    rec["authority_role"] = "eip_adapters_csv_moduletype"
                elif "IOCARD" in name_u:
                    rec["authority_candidate"] = True
                    rec["authority_role"] = "iocard"
                elif "HOSTS" in name_u:
                    rec["authority_role"] = "hosts_alias"
                    rec["authority_candidate"] = False  # alias only
            except Exception as exc:
                rec["error"] = str(exc)
            out.append(rec)
    return sorted(out, key=lambda r: (not r.get("authority_candidate"), r["path"]))


def build_hardware_identity_model(
    run_dir: Path | str,
    machine: str,
) -> dict[str, Any]:
    """Build canonical HardwareIdentity graph from RUN evidence."""
    run_dir = Path(run_dir)
    machine = (machine or "").strip()
    inventory = inventory_hardware_files(run_dir, machine)
    topo = parse_eipcfg(run_dir, machine)
    eipmods = _load_eipmodules_rows(run_dir, machine)

    identities: dict[str, HardwareIdentity] = {}
    conflicts: list[dict[str, Any]] = []
    name_index: dict[str, str] = {}  # normalized name → canonical_id

    def _register(hw: HardwareIdentity) -> None:
        identities[hw.canonical_id] = hw
        for n in hw.source_names + hw.aliases:
            nn = _norm_name(n)
            if not nn:
                continue
            prior = name_index.get(nn)
            if prior and prior != hw.canonical_id:
                conflicts.append(
                    {
                        "status": STATUS_CONFLICT,
                        "name": n,
                        "canonical_a": prior,
                        "canonical_b": hw.canonical_id,
                        "reason": "same_alias_name_maps_to_two_identities",
                    }
                )
                hw.status = STATUS_CONFLICT
                identities[prior].status = STATUS_CONFLICT
            else:
                name_index[nn] = hw.canonical_id

    # 1) Adapters from eipcfg
    for i, ad in enumerate(topo.get("adapters") or []):
        rio = str(ad.get("rio_name") or ad.get("name") or "").strip()
        ip = str(ad.get("targetip") or "").strip()
        fam = str(ad.get("family") or "")
        # Catalog from head module if present
        head_cat = ""
        for m in ad.get("modules") or []:
            if (m.get("connection") or "").upper() == "HEADNODE" or "AENT" in str(
                m.get("type") or ""
            ).upper():
                head_cat = str(m.get("type") or m.get("catalog") or "")
                break
        cid = _canon_id("ADAPTER", machine, ip or rio, head_cat or fam, i)
        aliases = []
        for a in (rio, ad.get("name"), head_cat):
            s = str(a or "").strip()
            if s and s not in aliases:
                aliases.append(s)
        # hosts-style T_ prefix variants as alias candidates only when IP matches later
        hw = HardwareIdentity(
            canonical_id=cid,
            device_class="adapter",
            adapter_family=fam or detect_family_from_catalog(head_cat),
            catalog_number=head_cat,
            part_number=head_cat,
            adapter_index=i,
            ip_address=ip,
            source_names=[rio] if rio else [],
            aliases=aliases,
            evidence=[
                {
                    "source": "eipcfg_xml",
                    "ref": str(_find_eipcfg(run_dir, machine) or ""),
                    "fact": f"Adapter name={rio} targetip={ip} family={fam}",
                }
            ],
            confidence="HIGH" if ip and head_cat else "MEDIUM",
            status=STATUS_PROVEN if ip and (rio or head_cat) else STATUS_DERIVED,
            machine=machine,
        )
        _register(hw)
        parent = cid

        # Child modules
        for m in ad.get("modules") or []:
            if (m.get("connection") or "").upper() == "HEADNODE":
                continue
            cat = str(m.get("type") or m.get("catalog") or "").strip()
            try:
                slot = int(m.get("slot"))
            except (TypeError, ValueError):
                slot = None
            try:
                di = int(m.get("data_index")) if m.get("data_index") is not None else None
            except (TypeError, ValueError):
                di = None
            direction = str(m.get("direction") or "")
            mcid = _canon_id("MODULE", machine, parent, cat, slot, di)
            mnames = []
            for a in (m.get("name"), cat, f"{rio}_{slot}" if rio and slot is not None else ""):
                s = str(a or "").strip()
                if s and s not in mnames:
                    mnames.append(s)
            # Corroborate with EIPModules banks
            evi = [
                {
                    "source": "eipcfg_xml",
                    "ref": f"{rio}.slot{slot}",
                    "fact": f"type={cat} slot={slot} data_index={di} direction={direction}",
                }
            ]
            status = STATUS_PROVEN if cat and slot is not None else STATUS_REVIEW
            for em in eipmods:
                if str(em.get("adapter") or "").strip() != str(ad.get("name") or rio).strip():
                    # also try rio_name match
                    if _norm_name(str(em.get("adapter") or "")) != _norm_name(rio):
                        if _norm_name(str(em.get("adapter") or "")) != _norm_name(
                            str(ad.get("name") or "")
                        ):
                            continue
                try:
                    if int(em.get("slot")) != slot:
                        continue
                except (TypeError, ValueError):
                    continue
                em_type = str(em.get("type") or "")
                if em_type and cat and em_type.upper() != cat.upper():
                    conflicts.append(
                        {
                            "status": STATUS_CONFLICT,
                            "canonical_id": mcid,
                            "reason": "eipcfg_vs_eipmodules_catalog_mismatch",
                            "eipcfg_catalog": cat,
                            "eipmodules_catalog": em_type,
                            "slot": slot,
                            "adapter": rio,
                        }
                    )
                    status = STATUS_CONFLICT
                evi.append(
                    {
                        "source": "eipmodules",
                        "ref": f"adapter={em.get('adapter')} slot={em.get('slot')}",
                        "fact": (
                            f"type={em_type} input_bank={em.get('input_bank')} "
                            f"output_bank={em.get('output_bank')}"
                        ),
                    }
                )
            mhw = HardwareIdentity(
                canonical_id=mcid,
                device_class="module",
                adapter_family=detect_family_from_catalog(cat) or fam,
                catalog_number=cat,
                part_number=cat,
                physical_slot=slot,
                data_index=di,
                direction=direction,
                channel_capacity=channel_capacity_for_catalog(cat),
                parent_canonical_id=parent,
                source_names=mnames[:1],
                aliases=mnames,
                evidence=evi,
                confidence="HIGH" if status == STATUS_PROVEN else "MEDIUM",
                status=status,
                machine=machine,
            )
            _register(mhw)

    # hosts aliases — IP corroboration only
    hosts_path = run_dir / "SystemFiles" / "hosts"
    if hosts_path.is_file():
        for line in hosts_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            ip, *names = parts
            for hw in identities.values():
                if hw.device_class == "adapter" and hw.ip_address == ip:
                    for n in names:
                        if n not in hw.aliases:
                            hw.aliases.append(n)
                            hw.evidence.append(
                                {
                                    "source": "hosts_alias",
                                    "ref": "SystemFiles/hosts",
                                    "fact": f"{ip} → {n}",
                                }
                            )

    adapters = [h.to_dict() for h in identities.values() if h.device_class == "adapter"]
    modules = [h.to_dict() for h in identities.values() if h.device_class == "module"]
    return {
        "kind": "hardware_identity_model",
        "version": 1,
        "machine": machine,
        "run_dir": str(run_dir),
        "evidence_precedence": EVIDENCE_PRECEDENCE,
        "inventory": inventory,
        "adapters": adapters,
        "modules": modules,
        "name_index": name_index,
        "conflicts": conflicts,
        "stats": {
            "adapter_count": len(adapters),
            "module_count": len(modules),
            "conflict_count": len(conflicts),
            "inventory_files": len(inventory),
            "authority_files": sum(1 for i in inventory if i.get("authority_candidate")),
        },
    }


def enrich_claim_hardware(
    claim: dict[str, Any],
    *,
    physical_hit: dict[str, Any] | None,
    identity_model: dict[str, Any],
) -> dict[str, Any]:
    """Attach canonical hardware fields to a claim (no invention)."""
    out = dict(claim)
    if not physical_hit:
        out.setdefault("hardware_identity_status", STATUS_UNKNOWN)
        return out
    rio = str(physical_hit.get("rio_name") or "")
    cat = str(physical_hit.get("type") or physical_hit.get("catalog") or "")
    slot = physical_hit.get("eip_slot")
    di = physical_hit.get("data_index")
    fam = str(physical_hit.get("family") or detect_family_from_catalog(cat) or "")
    # Find module identity
    mod = None
    for m in identity_model.get("modules") or []:
        if cat and str(m.get("catalog_number") or "").upper() != cat.upper():
            # allow match by parent alias + slot
            pass
        parent = m.get("parent_canonical_id")
        parent_ad = next(
            (a for a in identity_model.get("adapters") or [] if a["canonical_id"] == parent),
            None,
        )
        parent_names = set(_norm_name(x) for x in ((parent_ad or {}).get("aliases") or []))
        if _norm_name(rio) not in parent_names and rio:
            if parent_ad and _norm_name(rio) != _norm_name(
                (parent_ad.get("source_names") or ["x"])[0]
            ):
                continue
        try:
            if slot is not None and int(m.get("physical_slot")) != int(slot):
                continue
        except (TypeError, ValueError):
            continue
        mod = m
        break
    ad = None
    if mod:
        ad = next(
            (
                a
                for a in identity_model.get("adapters") or []
                if a["canonical_id"] == mod.get("parent_canonical_id")
            ),
            None,
        )
    if not ad:
        for a in identity_model.get("adapters") or []:
            if _norm_name(rio) in {_norm_name(x) for x in a.get("aliases") or []}:
                ad = a
                break

    out["adapter_family"] = fam or (ad or {}).get("adapter_family") or ""
    out["module_catalog"] = cat or (mod or {}).get("catalog_number") or ""
    out["physical_slot"] = slot if slot is not None else (mod or {}).get("physical_slot")
    out["data_index"] = di if di is not None else (mod or {}).get("data_index")
    out["direction"] = physical_hit.get("direction") or (mod or {}).get("direction") or ""
    out["channel_capacity"] = int(
        physical_hit.get("module_capacity")
        or (mod or {}).get("channel_capacity")
        or channel_capacity_for_catalog(cat)
        or 0
    )
    out["canonical_adapter_id"] = (ad or {}).get("canonical_id") or ""
    out["canonical_module_id"] = (mod or {}).get("canonical_id") or ""
    out["hardware_identity_status"] = (
        (mod or {}).get("status")
        or (ad or {}).get("status")
        or (STATUS_DERIVED if cat else STATUS_UNKNOWN)
    )
    out["hardware_evidence_refs"] = list((mod or {}).get("evidence") or (ad or {}).get("evidence") or [])[
        :6
    ]
    return out


def classify_host_xml_value(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify whether host/XML adds authority beyond what Site Forge already uses."""
    roles = {i.get("authority_role") for i in inventory if i.get("authority_candidate")}
    has_eipcfg = "eipcfg_xml" in roles
    has_eipmod = "eipmodules" in roles
    has_iocard = "iocard" in roles
    # Site Forge already parses eipcfg + EIPModules; hosts are alias-only;
    # no separate Rockwell BOM XML found in fixtures.
    if has_eipcfg and has_eipmod:
        return {
            "classification": "PARTIAL_VALUE",
            "note": (
                "eipcfg XML + EIPModules are HIGH value and already primary authorities. "
                "No additional host/hardware BOM XML with distinct part-number authority "
                "was found beyond these. hosts files are alias-only (IP↔name)."
            ),
            "solves": [
                "adapter identity (eipcfg)",
                "catalog/slot/family (eipcfg Module@type)",
                "bank linkage (EIPModules)",
                "IP mapping (eipcfg targetip + hosts alias)",
            ],
            "already_used_by_site_forge": True,
            "new_unused_authority": False,
        }
    if has_eipcfg or has_eipmod:
        return {
            "classification": "HIGH_VALUE",
            "note": "Partial EIP topology present — critical for identity",
            "already_used_by_site_forge": True,
            "new_unused_authority": False,
        }
    return {
        "classification": "ABSENT",
        "note": "No eipcfg/EIPModules authority files found",
        "already_used_by_site_forge": False,
        "new_unused_authority": False,
    }
