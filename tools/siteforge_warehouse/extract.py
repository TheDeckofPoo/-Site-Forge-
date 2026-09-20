"""Build ArchiveEvidenceBundle from a RUN directory (no PhysicalWordResolver)."""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "tools" / "scripts"
_TOOLS = _REPO / "tools"
for _p in (_SCRIPTS, _TOOLS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from fortna_asc import read_asc  # noqa: E402
from fortna_evidence_purity import (  # noqa: E402
    INDEPENDENT_DERIVATION,
    RAW_RUN_EVIDENCE,
)
from fortna_io_claim_ledger import iter_raw_named_claims  # noqa: E402
from fortna_machine_source_scope import (  # noqa: E402
    SCOPE_ACTIVE,
    SCOPE_GLOBAL,
    classify_eipcfg_files,
    read_machine_name,
    read_project_name,
)

from siteforge_learning.classify_configio_dialect import (  # noqa: E402
    classify_configio_dialect,
)
from siteforge_learning.classify_configio_purpose import (  # noqa: E402
    classify_configio_purpose,
)
from siteforge_learning.corpus_models import (  # noqa: E402
    ARCHIVE_RUN,
    ARCHIVE_UNKNOWN,
)

from . import EXTRACTOR_VERSION
from .ids import fact_uid, normalize_archive_sha256
from .staging import ArchiveEvidenceBundle, ArchiveMeta

_BACKUP_MARKERS = (".OLD", ".BAK", ".BARRY", ".SAVE", ".BAK_")


def _rel(run_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(run_dir.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _is_backup(name: str) -> bool:
    u = name.upper()
    return any(m in u for m in _BACKUP_MARKERS)


def _birth(
    *,
    kind: str,
    archive_sha256: str,
    project: str,
    machine: str,
    source_path: str,
    source_row_index: int,
    machine_scope: str,
    evidence_class: str,
    extra: str = "",
) -> dict[str, Any]:
    return {
        "fact_uid": fact_uid(
            kind, archive_sha256, source_path, source_row_index, extra=extra
        ),
        "archive_sha256": archive_sha256,
        "project": project,
        "machine": machine,
        "source_path": source_path,
        "source_row_index": source_row_index,
        "machine_scope": machine_scope,
        "evidence_class": evidence_class,
        "extractor_version": EXTRACTOR_VERSION,
    }


def _pick_asc(candidates: list[Path], machine: str = "") -> Path | None:
    mach = (machine or "").strip()
    ordered: list[Path] = []
    if mach:
        for p in candidates:
            if p.name.upper().endswith("." + mach.upper()) and not _is_backup(p.name):
                ordered.append(p)
    for p in candidates:
        if p not in ordered and not _is_backup(p.name):
            ordered.append(p)
    for p in ordered:
        if p.is_file():
            return p
    return None


def _load_asc_rows(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.is_file():
        return []
    try:
        _, rows = read_asc(path)
        return list(rows or [])
    except Exception:
        return []


def _module_direction(mt: str) -> str:
    u = (mt or "").upper()
    if re.search(r"\bI[ABV]", u) or u.startswith(("1794-I", "1734-I", "1756-I")):
        return "I"
    if re.search(r"\bO[ABVW]", u) or u.startswith(("1794-O", "1734-O", "1756-O")):
        return "O"
    if "IA" in u or "IB" in u or "IV" in u or "IE" in u:
        return "I"
    if "OA" in u or "OB" in u or "OW" in u or "OE" in u:
        return "O"
    return ""


def _parse_eipcfg_xml(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Minimal eipcfg Adapter/Module parse — no PhysicalWordResolver."""
    adapters: list[dict[str, Any]] = []
    modules: list[dict[str, Any]] = []
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return [], []
    for ai, a in enumerate(root.findall(".//Adapter")):
        name = (a.attrib.get("name") or f"adapter_{ai}").strip()
        adapters.append(
            {
                "name": name,
                "targetip": (a.attrib.get("targetip") or "").strip(),
                "input_address": (
                    a.attrib.get("InputAddress") or a.attrib.get("inputaddress") or ""
                ),
                "output_address": (
                    a.attrib.get("OutputAddress") or a.attrib.get("outputaddress") or ""
                ),
                "adapter_index": ai,
            }
        )
        for mi, m in enumerate(a.findall("Module")):
            try:
                slot = int(float(m.attrib.get("slot") or 0))
            except (TypeError, ValueError):
                slot = 0
            modules.append(
                {
                    "adapter": name,
                    "slot": slot,
                    "type": (m.attrib.get("type") or "").strip(),
                    "name": (m.attrib.get("name") or "").strip(),
                    "connection": (m.attrib.get("connection") or "").strip(),
                    "module_index": mi,
                }
            )
    return adapters, modules


def _inventory_source_files(
    run_dir: Path,
    *,
    archive_sha256: str,
    project: str,
    machine: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    idx = 0
    for folder in ("FORTNA", "PROJECT"):
        base = run_dir / folder
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            if _is_backup(p.name):
                continue
            low = p.name.lower()
            kind = "other"
            if low.startswith("configio"):
                kind = "configio"
            elif low.startswith("eipmodules"):
                kind = "eipmodules"
            elif low.startswith("eipadapters"):
                kind = "eipadapters"
            elif low.startswith("eipmoduletype"):
                kind = "eipmoduletype"
            elif "eipcfg" in low and low.endswith((".xml", ".xml.save")):
                kind = "eipcfg"
            elif low.startswith("conveyor"):
                kind = "conveyor"
            elif low == "project.cfg" or p.name == "project.cfg":
                kind = "project_cfg"
            rel = _rel(run_dir, p)
            row = _birth(
                kind="source_file",
                archive_sha256=archive_sha256,
                project=project,
                machine=machine,
                source_path=rel,
                source_row_index=idx,
                machine_scope=SCOPE_GLOBAL,
                evidence_class=RAW_RUN_EVIDENCE,
                extra=kind,
            )
            row.update(
                {
                    "kind": kind,
                    "size_bytes": p.stat().st_size if p.exists() else None,
                    "notes": [],
                }
            )
            out.append(row)
            idx += 1
    cfg = run_dir / "project.cfg"
    if cfg.is_file() and not any(r["source_path"] == "project.cfg" for r in out):
        row = _birth(
            kind="source_file",
            archive_sha256=archive_sha256,
            project=project,
            machine=machine,
            source_path="project.cfg",
            source_row_index=idx,
            machine_scope=SCOPE_GLOBAL,
            evidence_class=RAW_RUN_EVIDENCE,
            extra="project_cfg",
        )
        row.update({"kind": "project_cfg", "size_bytes": cfg.stat().st_size, "notes": []})
        out.append(row)
    return out


def build_bundle_from_run_dir(
    run_dir: Path | str,
    archive_sha256: str,
    filename: str = "",
    discovered_path: str = "",
) -> ArchiveEvidenceBundle:
    """Extract Stage-1 evidence from a RUN directory.

    Raw table rows → RAW_RUN_EVIDENCE.
    Purpose / dialect annotations → INDEPENDENT_DERIVATION.
    Does NOT call PhysicalWordResolver.
    """
    run_dir = Path(run_dir)
    sha = normalize_archive_sha256(archive_sha256)
    project = read_project_name(run_dir) or ""
    machine = read_machine_name(run_dir) or ""
    if not filename:
        filename = run_dir.name
    if not discovered_path:
        discovered_path = str(run_dir)

    tables_present: list[str] = []
    notes: list[str] = []

    # --- scopes (eipcfg machine scoping) ---
    scopes: list[dict[str, Any]] = []
    for i, scoped in enumerate(classify_eipcfg_files(run_dir, machine)):
        row = _birth(
            kind="machine_source_scope",
            archive_sha256=sha,
            project=scoped.project or project,
            machine=machine,
            source_path=scoped.source_file,
            source_row_index=i,
            machine_scope=scoped.scope_status,
            evidence_class=INDEPENDENT_DERIVATION,
            extra=scoped.kind,
        )
        row.update(
            {
                "kind": scoped.kind,
                "source_machine_inferred": scoped.source_machine_inferred,
                "notes": list(scoped.notes or []),
            }
        )
        scopes.append(row)

    source_files = _inventory_source_files(
        run_dir, archive_sha256=sha, project=project, machine=machine
    )

    # --- Configio ---
    fortna = run_dir / "FORTNA"
    configio_path = _pick_asc(
        sorted(fortna.glob("Configio.asc*")) if fortna.is_dir() else [], machine
    )
    configio_raw = _load_asc_rows(configio_path)
    if configio_path:
        tables_present.append("Configio")
    configio_rows: list[dict[str, Any]] = []
    purpose_annotations: list[dict[str, Any]] = []
    dialect_annotations: list[dict[str, Any]] = []
    cfg_rel = _rel(run_dir, configio_path) if configio_path else "FORTNA/Configio.asc"

    for i, raw in enumerate(configio_raw):
        desc = str(raw.get("Desc") or raw.get("desc") or "").strip()
        bank = str(raw.get("Bank") or raw.get("bank") or "").strip()
        word = str(raw.get("Octal_Word") or raw.get("octal_word") or "").strip()
        lohi = str(raw.get("LoHi") or raw.get("lohi") or "").strip()
        in_out = str(raw.get("In_Out") or raw.get("in_out") or "").strip()
        iface = str(raw.get("Interface") or raw.get("interface") or "").strip()
        io_type = str(raw.get("I_O_Type") or raw.get("i_o_type") or "").strip()
        status = str(raw.get("Status") or raw.get("status") or "").strip()
        process = str(raw.get("Process") or raw.get("process") or "").strip()

        norm = {
            "desc": desc,
            "bank": bank,
            "octal_word": word,
            "lohi": lohi,
            "in_out": in_out,
            "interface": iface,
            "i_o_type": io_type,
            "status": status,
            "process": process,
        }
        purpose = classify_configio_purpose(norm)
        dialect = classify_configio_dialect(desc)

        row = _birth(
            kind="configio_row",
            archive_sha256=sha,
            project=project,
            machine=machine,
            source_path=cfg_rel,
            source_row_index=i,
            machine_scope=SCOPE_ACTIVE if machine else SCOPE_GLOBAL,
            evidence_class=RAW_RUN_EVIDENCE,
        )
        row.update(
            {
                "octal_word": word,
                "bank": bank,
                "lohi": lohi,
                "in_out": in_out,
                "desc": desc,
                "interface": iface,
                "i_o_type": io_type,
                "status": status,
                "process": process,
                "purpose": str(purpose.get("purpose") or ""),
                "purpose_meta": dict(purpose),
                "dialect_form": dialect.configio_form,
                "dialect_meta": dialect.to_dict(),
                "raw_fields": dict(raw),
            }
        )
        configio_rows.append(row)

        pur_ann = _birth(
            kind="purpose_annotation",
            archive_sha256=sha,
            project=project,
            machine=machine,
            source_path=cfg_rel,
            source_row_index=i,
            machine_scope=SCOPE_ACTIVE if machine else SCOPE_GLOBAL,
            evidence_class=INDEPENDENT_DERIVATION,
            extra="purpose",
        )
        pur_ann.update({"purpose": purpose.get("purpose"), "meta": dict(purpose)})
        purpose_annotations.append(pur_ann)

        dia_ann = _birth(
            kind="dialect_annotation",
            archive_sha256=sha,
            project=project,
            machine=machine,
            source_path=cfg_rel,
            source_row_index=i,
            machine_scope=SCOPE_ACTIVE if machine else SCOPE_GLOBAL,
            evidence_class=INDEPENDENT_DERIVATION,
            extra="dialect",
        )
        dia_ann.update(
            {
                "form": dialect.configio_form,
                "meta": dialect.to_dict(),
            }
        )
        dialect_annotations.append(dia_ann)

    # --- EIPModules ---
    proj = run_dir / "PROJECT"
    eip_path = _pick_asc(
        sorted(proj.glob("EIPModules.asc*")) if proj.is_dir() else [], machine
    )
    eip_raw = _load_asc_rows(eip_path)
    if eip_path:
        tables_present.append("EIPModules")
    eip_rel = _rel(run_dir, eip_path) if eip_path else "PROJECT/EIPModules.asc"
    eipmodules: list[dict[str, Any]] = []
    for i, raw in enumerate(eip_raw):
        adapter = str(raw.get("Adapter") or "").strip()
        mt = str(raw.get("Type") or "").strip()
        if not adapter or adapter.upper() in ("N/A", "INVALID"):
            continue
        if not mt or mt.upper() in ("N/A", "INVALID"):
            continue
        try:
            slot = int(float(raw.get("Slot") or 0))
        except (TypeError, ValueError):
            slot = 0
        try:
            ib = int(float(raw.get("InputBank") or 0))
        except (TypeError, ValueError):
            ib = 0
        try:
            ob = int(float(raw.get("OutputBank") or 0))
        except (TypeError, ValueError):
            ob = 0
        row = _birth(
            kind="eipmodule",
            archive_sha256=sha,
            project=project,
            machine=machine,
            source_path=eip_rel,
            source_row_index=i,
            machine_scope=SCOPE_ACTIVE if machine else SCOPE_GLOBAL,
            evidence_class=RAW_RUN_EVIDENCE,
            extra=f"{adapter}|{slot}",
        )
        row.update(
            {
                "name": str(raw.get("Name") or "").strip(),
                "adapter": adapter,
                "type": mt,
                "slot": slot,
                "connection": str(raw.get("Connection") or "").strip(),
                "input_bank": ib,
                "output_bank": ob,
                "direction": _module_direction(mt),
                "raw_fields": dict(raw),
            }
        )
        eipmodules.append(row)

    # --- EIPAdapters ---
    eipa_path = _pick_asc(
        sorted(proj.glob("EIPAdapters.asc*")) if proj.is_dir() else [], machine
    )
    eipa_raw = _load_asc_rows(eipa_path)
    if eipa_path:
        tables_present.append("EIPAdapters")
    eipa_rel = _rel(run_dir, eipa_path) if eipa_path else "PROJECT/EIPAdapters.asc"
    eipadapters: list[dict[str, Any]] = []
    for i, raw in enumerate(eipa_raw):
        name = str(raw.get("Name") or "").strip()
        if not name or name.upper() in ("N/A", "INVALID"):
            continue
        row = _birth(
            kind="eipadapter",
            archive_sha256=sha,
            project=project,
            machine=machine,
            source_path=eipa_rel,
            source_row_index=i,
            machine_scope=SCOPE_ACTIVE if machine else SCOPE_GLOBAL,
            evidence_class=RAW_RUN_EVIDENCE,
            extra=name,
        )
        row.update(
            {
                "name": name,
                "target_ip": str(raw.get("TargetIP") or "").strip(),
                "rack": str(raw.get("Rack") or "").strip(),
                "raw_fields": dict(raw),
            }
        )
        eipadapters.append(row)

    # --- EIPModuleType ---
    eipt_path = proj / "EIPModuleType.asc"
    if not eipt_path.is_file():
        eipt_path_opt = _pick_asc(
            sorted(proj.glob("EIPModuleType.asc*")) if proj.is_dir() else [], machine
        )
        eipt_path = eipt_path_opt or eipt_path
    eipt_raw = _load_asc_rows(eipt_path if eipt_path and eipt_path.is_file() else None)
    if eipt_raw:
        tables_present.append("EIPModuleType")
    eipt_rel = (
        _rel(run_dir, eipt_path)
        if eipt_path and Path(eipt_path).is_file()
        else "PROJECT/EIPModuleType.asc"
    )
    eipmodule_types: list[dict[str, Any]] = []
    for i, raw in enumerate(eipt_raw):
        type_name = str(
            raw.get("Type") or raw.get("Name") or raw.get("ModuleType") or ""
        ).strip()
        row = _birth(
            kind="eipmodule_type",
            archive_sha256=sha,
            project=project,
            machine=machine,
            source_path=eipt_rel,
            source_row_index=i,
            machine_scope=SCOPE_GLOBAL,
            evidence_class=RAW_RUN_EVIDENCE,
            extra=type_name or str(i),
        )
        row.update({"type_name": type_name, "raw_fields": dict(raw)})
        eipmodule_types.append(row)

    # --- eipcfg ---
    eipcfg_adapters: list[dict[str, Any]] = []
    eipcfg_modules: list[dict[str, Any]] = []
    eipcfg_files = sorted((run_dir / "FORTNA").glob("*eipcfg*.xml")) if fortna.is_dir() else []
    eipcfg_files = [p for p in eipcfg_files if not _is_backup(p.name)]
    if eipcfg_files:
        tables_present.append("eipcfg")
    # Prefer ACTIVE_MACHINE_SOURCE eipcfg when scoped
    active_paths = {
        s["source_path"] for s in scopes if s.get("machine_scope") == SCOPE_ACTIVE
    }
    preferred = [p for p in eipcfg_files if _rel(run_dir, p) in active_paths]
    parse_list = preferred or eipcfg_files
    for eipcfg_path in parse_list:
        rel = _rel(run_dir, eipcfg_path)
        scope_hit = next(
            (s for s in scopes if s.get("source_path") == rel), None
        )
        scope_status = (
            scope_hit["machine_scope"] if scope_hit else (SCOPE_ACTIVE if machine else SCOPE_GLOBAL)
        )
        ads, mods = _parse_eipcfg_xml(eipcfg_path)
        for i, ad in enumerate(ads):
            row = _birth(
                kind="eipcfg_adapter",
                archive_sha256=sha,
                project=project,
                machine=machine,
                source_path=rel,
                source_row_index=i,
                machine_scope=scope_status,
                evidence_class=RAW_RUN_EVIDENCE,
                extra=ad.get("name") or str(i),
            )
            row.update(
                {
                    "name": ad.get("name") or "",
                    "targetip": ad.get("targetip") or "",
                    "input_address": ad.get("input_address") or "",
                    "output_address": ad.get("output_address") or "",
                    "raw_fields": dict(ad),
                }
            )
            eipcfg_adapters.append(row)
        for i, mod in enumerate(mods):
            row = _birth(
                kind="eipcfg_module",
                archive_sha256=sha,
                project=project,
                machine=machine,
                source_path=rel,
                source_row_index=i,
                machine_scope=scope_status,
                evidence_class=RAW_RUN_EVIDENCE,
                extra=f"{mod.get('adapter')}|{mod.get('slot')}",
            )
            row.update(
                {
                    "adapter": mod.get("adapter") or "",
                    "slot": int(mod.get("slot") or 0),
                    "type": mod.get("type") or "",
                    "name": mod.get("name") or "",
                    "connection": mod.get("connection") or "",
                    "raw_fields": dict(mod),
                }
            )
            eipcfg_modules.append(row)

    # --- IO claims (raw Conveyor named claims — no resolver) ---
    io_claims: list[dict[str, Any]] = []
    try:
        claims = iter_raw_named_claims(run_dir, machine)
    except Exception as exc:
        claims = []
        notes.append(f"io_claims_error:{exc}")
    if claims:
        tables_present.append("Conveyor")
    for i, claim in enumerate(claims):
        row = _birth(
            kind="io_claim",
            archive_sha256=sha,
            project=project,
            machine=machine,
            source_path=str(claim.get("source_table") or "FORTNA/Conveyor.asc"),
            source_row_index=i,
            machine_scope=SCOPE_ACTIVE if machine else SCOPE_GLOBAL,
            evidence_class=RAW_RUN_EVIDENCE,
            extra=str(claim.get("name") or ""),
        )
        row.update(
            {
                "io_name": claim.get("name") or "",
                "fortna_word": str(claim.get("fortna_word") or ""),
                "fortna_bit": str(claim.get("fortna_bit") or ""),
                "word": claim.get("word"),
                "device_type": str(claim.get("type") or ""),
                "raw_fields": dict(claim),
            }
        )
        io_claims.append(row)

    # --- simple bank collisions as conflicts ---
    conflicts: list[dict[str, Any]] = []
    inputs: dict[int, list[dict[str, Any]]] = {}
    outputs: dict[int, list[dict[str, Any]]] = {}
    for m in eipmodules:
        ib = int(m.get("input_bank") or 0)
        ob = int(m.get("output_bank") or 0)
        inputs.setdefault(ib, []).append(m)
        outputs.setdefault(ob, []).append(m)
    for bank in sorted(set(inputs) & set(outputs)):
        if bank == 0:
            continue
        in_ids = {(m.get("adapter"), m.get("slot"), m.get("type")) for m in inputs[bank]}
        out_ids = {(m.get("adapter"), m.get("slot"), m.get("type")) for m in outputs[bank]}
        if in_ids == out_ids:
            continue
        row = _birth(
            kind="conflict",
            archive_sha256=sha,
            project=project,
            machine=machine,
            source_path=eip_rel,
            source_row_index=bank,
            machine_scope=SCOPE_ACTIVE if machine else SCOPE_GLOBAL,
            evidence_class=INDEPENDENT_DERIVATION,
            extra=f"bank_collision_{bank}",
        )
        row.update(
            {
                "conflict_kind": "BANK_COLLISION",
                "summary": f"Bank {bank} used as InputBank and OutputBank on different modules",
                "details": {
                    "bank": bank,
                    "input_modules": [
                        {"adapter": m.get("adapter"), "slot": m.get("slot"), "type": m.get("type")}
                        for m in inputs[bank]
                    ],
                    "output_modules": [
                        {"adapter": m.get("adapter"), "slot": m.get("slot"), "type": m.get("type")}
                        for m in outputs[bank]
                    ],
                },
            }
        )
        conflicts.append(row)

    # --- adapter bridges (exact name/IP when possible; no resolver) ---
    adapter_bridges: list[dict[str, Any]] = []
    eipa_by_name = {a["name"].casefold(): a for a in eipadapters if a.get("name")}
    eipcfg_by_ip = {
        (a.get("targetip") or "").strip(): a
        for a in eipcfg_adapters
        if (a.get("targetip") or "").strip()
    }
    seen_adapters: set[str] = set()
    for i, mod in enumerate(eipmodules):
        aname = str(mod.get("adapter") or "")
        if not aname or aname.casefold() in seen_adapters:
            continue
        seen_adapters.add(aname.casefold())
        eipa = eipa_by_name.get(aname.casefold())
        status = "UNKNOWN"
        conf = "UNKNOWN"
        tip = ""
        eipcfg_name = ""
        if eipa:
            tip = str(eipa.get("target_ip") or "")
            status = "DERIVED"
            conf = "DERIVED"
            if tip and tip in eipcfg_by_ip:
                eipcfg_name = str(eipcfg_by_ip[tip].get("name") or "")
                status = "PROVEN"
                conf = "PROVEN"
        row = _birth(
            kind="adapter_bridge",
            archive_sha256=sha,
            project=project,
            machine=machine,
            source_path=eipa_rel,
            source_row_index=i,
            machine_scope=SCOPE_ACTIVE if machine else SCOPE_GLOBAL,
            evidence_class=INDEPENDENT_DERIVATION,
            extra=aname,
        )
        row.update(
            {
                "eipmodules_adapter_name": aname,
                "eipadapters_name": (eipa or {}).get("name") or "",
                "target_ip": tip,
                "eipcfg_adapter_name": eipcfg_name,
                "status": status,
                "confidence": conf,
                "details": {},
            }
        )
        adapter_bridges.append(row)

    archive_class = ARCHIVE_RUN
    if not (run_dir / "project.cfg").is_file():
        archive_class = ARCHIVE_UNKNOWN
        notes.append("missing_project_cfg")

    meta = ArchiveMeta(
        archive_sha256=sha,
        filename=filename,
        archive_class=archive_class,
        discovered_path=discovered_path,
        size_bytes=None,
        project=project,
        site=project,
        machine=machine,
        timestamp_token="",
        tables_present=sorted(set(tables_present)),
        notes=notes,
    )
    return ArchiveEvidenceBundle(
        archive=meta,
        project=project,
        machine=machine,
        source_files=source_files,
        configio_rows=configio_rows,
        eipmodules=eipmodules,
        eipadapters=eipadapters,
        eipmodule_types=eipmodule_types,
        eipcfg_adapters=eipcfg_adapters,
        eipcfg_modules=eipcfg_modules,
        io_claims=io_claims,
        purpose_annotations=purpose_annotations,
        dialect_annotations=dialect_annotations,
        scopes=scopes,
        conflicts=conflicts,
        adapter_bridges=adapter_bridges,
        extractor_version=EXTRACTOR_VERSION,
    )
