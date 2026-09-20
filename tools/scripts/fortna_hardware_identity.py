#!/usr/bin/env python3
"""Canonical hardware TYPE vs INSTANCE identity.

TYPE (catalog) may be shared by unlimited physical instances.
INSTANCE is unique: machine + adapter IP/index + slot (+ catalog).

Generic catalogs (1794-IA16, 1734-OA4, …) are NEVER instance aliases.
Only corroborated instance names (AENTR3, T_1794_AENT_2, hostnames) enter
the instance alias index. Conflicts require the same unique instance alias
mapping to incompatible physical keys — not catalog reuse.

Evidence precedence (no finished L5X):
  1. eipcfg XML  2. EIPModules  3. EIPAdapters/CSV/ModuleType
  4. Configio  5. IOCard  6. hosts aliases  7. human names (aliases only)

FortnaPlus GUI corroboration (Configuration → IO Utilities → IO Configure):
  Configio columns Desc, Bank, Octal_Word, LoHi, In_Out, I_O_Type, Interface,
  Granularity, Countdown, Status — matches Configio.asc semantics (not a new source).
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fortna_hardware_family import (
    channel_capacity_for_catalog,
    detect_family_from_catalog,
)
from fortna_physical_word_resolver import (
    _find_eipcfg,
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

# Rockwell-style catalog / drive type labels (NOT instance aliases)
_CATALOG_RE = re.compile(
    r"^(?:\d{4}-[A-Za-z0-9]+|PowerFlex\d+[A-Za-z0-9]*|PF\d+|1734[A-Za-z0-9\-]*|1794[A-Za-z0-9\-]*)$",
    re.I,
)


def _canon_id(*parts: Any) -> str:
    raw = "|".join(str(p).strip().upper() for p in parts if str(p).strip() != "")
    return "hw_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _norm_name(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def classify_name(name: str) -> str:
    """Return INSTANCE_ALIAS | TYPE_LABEL | SHARED_MODULE_LABEL | EMPTY."""
    s = (name or "").strip()
    if not s:
        return "EMPTY"
    # Pure catalog / family type
    if _CATALOG_RE.match(s):
        return "TYPE_LABEL"
    # eipcfg often repeats "AENTR1-IB8" / "AENTR3-IV8" on every similar slot
    if re.match(r"^AENTR\d+-(IB|OB|IA|OA|OW|IV|OV)\d+$", s, re.I):
        return "SHARED_MODULE_LABEL"
    if re.match(r"^1734[_-]?(IB|OB|IA|OA|OW|IV|OV)\d+(_\d+)?$", s, re.I):
        return "SHARED_MODULE_LABEL"
    if re.match(r"^1738[_-]?(IB|OB)\d+[A-Za-z0-9]*(_\d+)?$", s, re.I):
        return "SHARED_MODULE_LABEL"
    if re.match(r"^1794-[A-Z0-9]+-\d+$", s, re.I):
        # 1794-IA16-2 includes slot suffix in eipcfg — treat as instance-ish label
        # but still not globally unique across adapters; allow as instance alias
        # only when bound to parent+slot in registration (not bare catalog).
        return "INSTANCE_ALIAS"
    # Adapter instance names / hostnames
    if re.match(r"^(T_)?(1794[_-])?AENT(R)?\d+", s, re.I):
        return "INSTANCE_ALIAS"
    if re.match(r"^CP\d+RIO\d+", s, re.I):
        return "INSTANCE_ALIAS"
    # Default: instance candidate (hostname, Desc-like names)
    if _CATALOG_RE.match(s.replace("_", "-")):
        return "TYPE_LABEL"
    return "INSTANCE_ALIAS"


@dataclass
class HardwareType:
    type_id: str
    catalog_number: str
    family: str = ""
    direction: str = ""
    channel_capacity: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HardwareIdentity:
    """Physical INSTANCE (adapter or module), not a catalog type."""

    canonical_id: str
    device_class: str  # adapter | module
    type_id: str = ""
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
    aliases: list[str] = field(default_factory=list)  # INSTANCE aliases only
    type_labels: list[str] = field(default_factory=list)  # catalog/shared labels
    evidence: list[dict[str, Any]] = field(default_factory=list)
    confidence: str = "MEDIUM"
    status: str = STATUS_UNKNOWN
    machine: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inventory_hardware_files(run_dir: Path, machine: str) -> list[dict[str, Any]]:
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
                    fields: set[str] = set()
                    for el in ads[:3] + mods[:5]:
                        fields.update(el.attrib.keys())
                    rec["fields_found"] = sorted(fields)
                    if ads or mods:
                        rec["authority_candidate"] = True
                        rec["authority_role"] = "eipcfg_xml"
                elif "EIPMODULE" in name_u:
                    rec["authority_candidate"] = True
                    rec["authority_role"] = "eipmodules"
                elif "EIPCFG" in name_u or "EIPADAPTER" in name_u or "EIPCSV" in name_u:
                    rec["authority_candidate"] = True
                    rec["authority_role"] = "eip_adapters_csv_moduletype"
                elif "IOCARD" in name_u:
                    rec["authority_candidate"] = True
                    rec["authority_role"] = "iocard"
                elif "HOSTS" in name_u:
                    rec["authority_role"] = "hosts_alias"
            except Exception as exc:
                rec["error"] = str(exc)
            out.append(rec)
    return sorted(out, key=lambda r: (not r.get("authority_candidate"), r["path"]))


def classify_host_xml_value(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    roles = {i.get("authority_role") for i in inventory if i.get("authority_candidate")}
    if "eipcfg_xml" in roles and "eipmodules" in roles:
        return {
            "classification": "PARTIAL_VALUE",
            "note": (
                "eipcfg XML + EIPModules are primary authorities already used by Site Forge. "
                "No separate unused BOM XML. hosts = IP↔name aliases only. "
                "FortnaPlus GUI IO Configure corroborates Configio.asc columns."
            ),
            "already_used_by_site_forge": True,
            "new_unused_authority": False,
        }
    if "eipcfg_xml" in roles or "eipmodules" in roles:
        return {
            "classification": "HIGH_VALUE",
            "already_used_by_site_forge": True,
            "new_unused_authority": False,
        }
    return {"classification": "ABSENT", "already_used_by_site_forge": False}


def build_hardware_identity_model(
    run_dir: Path | str,
    machine: str,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    machine = (machine or "").strip()
    inventory = inventory_hardware_files(run_dir, machine)
    topo = parse_eipcfg(run_dir, machine)
    eipmods = _load_eipmodules_rows(run_dir, machine)

    types: dict[str, HardwareType] = {}
    identities: dict[str, HardwareIdentity] = {}
    conflicts: list[dict[str, Any]] = []
    # INSTANCE alias index only (never catalogs / shared module labels)
    instance_alias_index: dict[str, str] = {}
    catalog_reuse = 0

    def _type_for(catalog: str, direction: str = "") -> HardwareType:
        cat = (catalog or "").strip()
        tid = _canon_id("TYPE", cat or "UNKNOWN")
        if tid not in types:
            types[tid] = HardwareType(
                type_id=tid,
                catalog_number=cat,
                family=detect_family_from_catalog(cat),
                direction=direction,
                channel_capacity=channel_capacity_for_catalog(cat),
            )
        else:
            nonlocal_reuse = True
            _ = nonlocal_reuse
        return types[tid]

    def _add_instance_alias(hw: HardwareIdentity, name: str) -> None:
        kind = classify_name(name)
        if kind in {"EMPTY", "TYPE_LABEL", "SHARED_MODULE_LABEL"}:
            if kind != "EMPTY" and name not in hw.type_labels:
                hw.type_labels.append(name)
            return
        if name not in hw.aliases:
            hw.aliases.append(name)
        nn = _norm_name(name)
        prior = instance_alias_index.get(nn)
        if prior and prior != hw.canonical_id:
            other = identities.get(prior)
            # True conflict only if incompatible physical keys
            incompatible = False
            reasons = []
            if other and hw.device_class == "adapter" and other.device_class == "adapter":
                if hw.ip_address and other.ip_address and hw.ip_address != other.ip_address:
                    incompatible = True
                    reasons.append("ip_mismatch")
                if (
                    hw.adapter_index is not None
                    and other.adapter_index is not None
                    and hw.adapter_index != other.adapter_index
                    and hw.ip_address == other.ip_address
                ):
                    # same IP different index — still conflict on alias
                    incompatible = True
                    reasons.append("adapter_index_mismatch")
            if other and hw.device_class == "module" and other.device_class == "module":
                if hw.parent_canonical_id != other.parent_canonical_id:
                    incompatible = True
                    reasons.append("parent_adapter_mismatch")
                if (
                    hw.physical_slot is not None
                    and other.physical_slot is not None
                    and hw.physical_slot != other.physical_slot
                ):
                    incompatible = True
                    reasons.append("slot_mismatch")
                if (
                    hw.catalog_number
                    and other.catalog_number
                    and hw.catalog_number.upper() != other.catalog_number.upper()
                ):
                    incompatible = True
                    reasons.append("catalog_mismatch")
            if incompatible:
                conflicts.append(
                    {
                        "status": STATUS_CONFLICT,
                        "conflicting_instance_alias": name,
                        "canonical_a": prior,
                        "canonical_b": hw.canonical_id,
                        "ip_a": getattr(other, "ip_address", ""),
                        "ip_b": hw.ip_address,
                        "slot_a": getattr(other, "physical_slot", None),
                        "slot_b": hw.physical_slot,
                        "catalog_a": getattr(other, "catalog_number", ""),
                        "catalog_b": hw.catalog_number,
                        "reasons": reasons,
                        "sources": ["eipcfg_xml", "instance_alias_index"],
                    }
                )
                hw.status = STATUS_CONFLICT
                if other:
                    other.status = STATUS_CONFLICT
            # If compatible reuse of same alias string across siblings — do not index
            return
        instance_alias_index[nn] = hw.canonical_id

    # --- Adapters ---
    for i, ad in enumerate(topo.get("adapters") or []):
        rio = str(ad.get("rio_name") or ad.get("name") or "").strip()
        ip = str(ad.get("targetip") or "").strip()
        fam = str(ad.get("family") or "")
        head_cat = ""
        for m in ad.get("modules") or []:
            if (m.get("connection") or "").upper() == "HEADNODE" or "AENT" in str(
                m.get("type") or ""
            ).upper():
                head_cat = str(m.get("type") or m.get("catalog") or "")
                break
        ht = _type_for(head_cat or fam)
        cid = _canon_id("ADAPTER", machine, ip or f"idx{i}", i)
        hw = HardwareIdentity(
            canonical_id=cid,
            device_class="adapter",
            type_id=ht.type_id,
            adapter_family=fam or ht.family,
            catalog_number=head_cat,
            part_number=head_cat,
            adapter_index=i,
            ip_address=ip,
            source_names=[rio] if rio else [],
            evidence=[
                {
                    "source": "eipcfg_xml",
                    "ref": str(_find_eipcfg(run_dir, machine) or ""),
                    "fact": f"Adapter name={rio} targetip={ip} index={i}",
                }
            ],
            confidence="HIGH" if ip else "MEDIUM",
            status=STATUS_PROVEN if ip and rio else STATUS_DERIVED,
            machine=machine,
        )
        if head_cat:
            hw.type_labels.append(head_cat)
        if rio:
            _add_instance_alias(hw, rio)
        eip_name = str(ad.get("name") or "").strip()
        if eip_name and eip_name != rio:
            _add_instance_alias(hw, eip_name)
        identities[cid] = hw
        parent = cid

        for m in ad.get("modules") or []:
            if (m.get("connection") or "").upper() == "HEADNODE":
                continue
            cat = str(m.get("type") or m.get("catalog") or "").strip()
            try:
                slot = int(m.get("slot"))
            except (TypeError, ValueError):
                slot = None
            try:
                di = (
                    int(m.get("data_index"))
                    if m.get("data_index") is not None
                    else None
                )
            except (TypeError, ValueError):
                di = None
            direction = str(m.get("direction") or "")
            mt = _type_for(cat, direction)
            # Count catalog reuse across instances
            existing_same_cat = sum(
                1
                for x in identities.values()
                if x.device_class == "module"
                and x.catalog_number.upper() == cat.upper()
                and cat
            )
            if existing_same_cat:
                catalog_reuse += 1
            mcid = _canon_id("MODULE", machine, parent, slot if slot is not None else "?", cat)
            mhw = HardwareIdentity(
                canonical_id=mcid,
                device_class="module",
                type_id=mt.type_id,
                adapter_family=mt.family or fam,
                catalog_number=cat,
                part_number=cat,
                physical_slot=slot,
                data_index=di,
                direction=direction,
                channel_capacity=mt.channel_capacity,
                parent_canonical_id=parent,
                source_names=[str(m.get("name") or "").strip()] if m.get("name") else [],
                type_labels=[cat] if cat else [],
                evidence=[
                    {
                        "source": "eipcfg_xml",
                        "ref": f"{rio}.slot{slot}",
                        "fact": f"type={cat} slot={slot} data_index={di} dir={direction}",
                    }
                ],
                confidence="HIGH" if cat and slot is not None else "MEDIUM",
                status=STATUS_PROVEN if cat and slot is not None else STATUS_REVIEW,
                machine=machine,
            )
            # EIPModules corroboration — catalog mismatch = conflict, not silent
            for em in eipmods:
                em_ad = str(em.get("adapter") or "").strip()
                if _norm_name(em_ad) not in {
                    _norm_name(rio),
                    _norm_name(str(ad.get("name") or "")),
                }:
                    continue
                try:
                    if int(em.get("slot")) != slot:
                        continue
                except (TypeError, ValueError):
                    continue
                em_type = str(em.get("type") or "")
                mhw.evidence.append(
                    {
                        "source": "eipmodules",
                        "ref": f"adapter={em_ad} slot={em.get('slot')}",
                        "fact": (
                            f"type={em_type} input_bank={em.get('input_bank')} "
                            f"output_bank={em.get('output_bank')}"
                        ),
                    }
                )
                if em_type and cat and em_type.upper() != cat.upper():
                    conflicts.append(
                        {
                            "status": STATUS_CONFLICT,
                            "conflicting_instance_alias": f"{rio}:slot{slot}",
                            "canonical_a": mcid,
                            "canonical_b": mcid,
                            "catalog_a": cat,
                            "catalog_b": em_type,
                            "slot_a": slot,
                            "slot_b": slot,
                            "ip_a": ip,
                            "ip_b": ip,
                            "reasons": ["eipcfg_vs_eipmodules_catalog_mismatch"],
                            "sources": ["eipcfg_xml", "eipmodules"],
                        }
                    )
                    mhw.status = STATUS_CONFLICT
            # Instance alias: unique "1794-IA16-2" style name OK; bare catalog not
            mname = str(m.get("name") or "").strip()
            if mname:
                _add_instance_alias(mhw, mname)
            # Slot-qualified instance label
            if rio and slot is not None and cat:
                _add_instance_alias(mhw, f"{rio}:slot{slot}:{cat}")
            identities[mcid] = mhw

    # hosts — IP corroboration → instance aliases on adapters
    hosts_path = run_dir / "SystemFiles" / "hosts"
    if hosts_path.is_file():
        for line in hosts_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            hip, *names = parts
            for hw in identities.values():
                if hw.device_class == "adapter" and hw.ip_address == hip:
                    for n in names:
                        _add_instance_alias(hw, n)
                        hw.evidence.append(
                            {
                                "source": "hosts_alias",
                                "ref": "SystemFiles/hosts",
                                "fact": f"{hip} → {n}",
                            }
                        )

    adapters = [h.to_dict() for h in identities.values() if h.device_class == "adapter"]
    modules = [h.to_dict() for h in identities.values() if h.device_class == "module"]
    return {
        "kind": "hardware_identity_model",
        "version": 2,
        "machine": machine,
        "run_dir": str(run_dir),
        "evidence_precedence": EVIDENCE_PRECEDENCE,
        "configio_gui_corroboration": {
            "path": "Configuration → IO Utilities → IO Configure",
            "columns": [
                "Desc",
                "Bank",
                "Octal_Word",
                "LoHi",
                "In_Out",
                "I_O_Type",
                "Interface",
                "Granularity",
                "Countdown",
                "Status",
            ],
            "note": "Corroborates Configio.asc — not a generated screenshot source",
        },
        "inventory": inventory,
        "types": [t.to_dict() for t in types.values()],
        "adapters": adapters,
        "modules": modules,
        "instance_alias_index": instance_alias_index,
        "conflicts": conflicts,
        "stats": {
            "adapter_count": len(adapters),
            "module_count": len(modules),
            "hardware_type_count": len(types),
            "instance_alias_count": len(instance_alias_index),
            "true_conflict_count": len(conflicts),
            "catalog_type_reuse_count": catalog_reuse,
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
    """Attach canonical hardware fields. Catalog mismatch never silently accepted."""
    out = dict(claim)
    if not physical_hit:
        out.setdefault("hardware_identity_status", STATUS_UNKNOWN)
        return out

    rio = str(physical_hit.get("rio_name") or "")
    cat = str(physical_hit.get("type") or physical_hit.get("catalog") or "").strip()
    slot = physical_hit.get("eip_slot")
    di = physical_hit.get("data_index")
    fam = str(physical_hit.get("family") or detect_family_from_catalog(cat) or "")

    # Resolve adapter by instance alias / rio
    ad = None
    for a in identity_model.get("adapters") or []:
        names = {_norm_name(x) for x in (a.get("aliases") or []) + (a.get("source_names") or [])}
        if _norm_name(rio) in names:
            ad = a
            break

    mod = None
    mismatch: dict[str, Any] | None = None
    if ad and slot is not None:
        candidates = [
            m
            for m in identity_model.get("modules") or []
            if m.get("parent_canonical_id") == ad.get("canonical_id")
        ]
        for m in candidates:
            try:
                if int(m.get("physical_slot")) != int(slot):
                    continue
            except (TypeError, ValueError):
                continue
            mcat = str(m.get("catalog_number") or "").strip()
            if cat and mcat and mcat.upper() != cat.upper():
                mismatch = {
                    "status": STATUS_CONFLICT,
                    "reason": "enrich_catalog_mismatch",
                    "claim_catalog": cat,
                    "module_catalog": mcat,
                    "slot": slot,
                    "adapter": rio,
                    "canonical_module_id": m.get("canonical_id"),
                }
                # Do NOT attach this module
                continue
            if cat and mcat and mcat.upper() == cat.upper():
                mod = m
                break
            if not cat and mcat:
                mod = m
                break
            if cat and not mcat:
                mod = m
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
    if mismatch:
        out["canonical_module_id"] = ""
        out["hardware_identity_status"] = STATUS_CONFLICT
        out["hardware_identity_conflict"] = mismatch
        out["hardware_evidence_refs"] = [
            {
                "source": "enrich_claim_hardware",
                "ref": f"{rio}.slot{slot}",
                "fact": f"catalog mismatch claim={cat} module={mismatch['module_catalog']}",
            }
        ]
    else:
        out["canonical_module_id"] = (mod or {}).get("canonical_id") or ""
        out["hardware_identity_status"] = (
            (mod or {}).get("status")
            or (ad or {}).get("status")
            or (STATUS_DERIVED if cat else STATUS_UNKNOWN)
        )
        out["hardware_evidence_refs"] = list(
            (mod or {}).get("evidence") or (ad or {}).get("evidence") or []
        )[:6]
    return out
