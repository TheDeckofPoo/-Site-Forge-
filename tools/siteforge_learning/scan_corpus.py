#!/usr/bin/env python3
"""Overnight corpus scanner — inventory only.

Discovers *.tar.gz and extracted RUN dirs. Never mutates source archives.
No live API. No finished L5X for discovery.

Usage:
  python -m tools.siteforge_learning.scan_corpus \\
    --roots workspace/corpus_inbox workspace/inbox \\
    --out exports/learning
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import tarfile
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from fortna_asc import read_asc  # noqa: E402
from fortna_eip_adapter_bridge import (  # noqa: E402
    build_adapter_bridges,
    load_eipadapters_rows,
)
from fortna_hardware_family import detect_family_from_catalog  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    _load_eipmodules_rows,
    parse_eipcfg,
)
from fortna_project_identity import identity_from_run  # noqa: E402
from fortna_rack_discovery import classify_network_device  # noqa: E402

from siteforge_learning.classify_configio_dialect import (  # noqa: E402
    classify_configio_dialect,
    classify_configio_rows,
)
from siteforge_learning.cluster_unknowns import cluster_unknown_dialects  # noqa: E402
from siteforge_learning.corpus_models import (  # noqa: E402
    ARCHIVE_COMM,
    ARCHIVE_RUN,
    ARCHIVE_UNKNOWN,
    FORM_UNKNOWN,
    STATUS_CANDIDATE_RULE,
    STATUS_PRODUCTION_RULE,
    ArchiveManifest,
    BankCollision,
    DecoderRuleRecord,
    DialectHit,
    HardwareFamilyHit,
    InOutMaskStat,
)

# ---------------------------------------------------------------------------
# Constants / seeds
# ---------------------------------------------------------------------------

_ARCHIVE_NAME_RE = re.compile(
    r"^(?P<ts>\d{8}-\d{4})-(?P<body>.+?)-(?P<kind>RUN|COMM.*)?\.tar\.gz$",
    re.I,
)
_BODY_SPLIT_RE = re.compile(
    r"^(?P<project>.+)-(?P<machine>[A-Za-z0-9_]+)$"
)

_TABLE_HINTS = (
    "Configio.asc",
    "EIPModules.asc",
    "EIPAdapters.asc",
    "EIPModuleType.asc",
    "Conveyor.asc",
    "Mtrchain.asc",
    "Jamzones.asc",
    "MergeBoss.asc",
)

PEEK_RUN_HINTS = [
    ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN",
    ROOT / "workspace" / "_virgin_orindy" / "RUN",
    ROOT / "workspace" / "_ordencp3_peek" / "ORDENCP3" / "RUN",
    ROOT / "workspace" / "_plc2_run_peek" / "RUN",
    ROOT / "workspace" / "_reno_peek" / "20260813-1132-MSCRENO-MSCRENOPACK-RUN" / "RUN",
    ROOT / "workspace" / "_reno_peek" / "20260813-1132-MSCRENO-MSCRENOPICK-RUN" / "RUN",
    ROOT / "workspace" / "_reno_peek" / "20260813-1132-MSCRENO-MSCRENOSHIP-RUN" / "RUN",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sorted_dict(d: dict[str, Any]) -> dict[str, Any]:
    return {k: d[k] for k in sorted(d.keys())}


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def classify_archive_filename(filename: str) -> dict[str, str]:
    """Parse archive filename into class / project / machine / timestamp."""
    name = Path(filename).name
    upper = name.upper()
    archive_class = ARCHIVE_UNKNOWN
    if "COMM" in upper:
        archive_class = ARCHIVE_COMM
    elif upper.endswith("-RUN.TAR.GZ") or "-RUN.TAR.GZ" in upper or upper.endswith("RUN.TAR.GZ"):
        archive_class = ARCHIVE_RUN

    ts = project = machine = site = ""
    # Strip .tar.gz
    stem = name
    if stem.lower().endswith(".tar.gz"):
        stem = stem[:-7]
    # timestamp prefix
    m = re.match(r"^(\d{8}-\d{4})-(.+)$", stem)
    if m:
        ts = m.group(1)
        rest = m.group(2)
    else:
        rest = stem
    # trailing -RUN / -COMM*
    rest2 = re.sub(r"-(RUN|COMM[A-Za-z0-9_]*)$", "", rest, flags=re.I)
    # last hyphen token = machine/controller; remainder = project/site
    if "-" in rest2:
        project, machine = rest2.rsplit("-", 1)
        site = project
    else:
        project = rest2
        site = rest2
        machine = ""
    return {
        "archive_class": archive_class,
        "timestamp": ts,
        "project": project,
        "site": site,
        "controller": machine,
        "machine": machine,
        "filename": name,
    }


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_archives(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.name.lower().endswith(".tar.gz"):
            found.append(root.resolve())
            continue
        for p in sorted(root.rglob("*.tar.gz")):
            # skip learning extract scratch and nested _archive copies under peeks
            parts_l = [x.lower() for x in p.parts]
            if "_extract" in parts_l or "exports" in parts_l and "learning" in parts_l:
                if "_extract" in parts_l:
                    continue
            found.append(p.resolve())
    # unique deterministic
    uniq = sorted({p.resolve() for p in found}, key=lambda x: str(x).lower())
    return uniq


def discover_run_dirs(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        # Direct RUN
        if root.name.upper() == "RUN" and (root / "project.cfg").is_file():
            found.append(root.resolve())
            continue
        if (root / "RUN" / "project.cfg").is_file():
            found.append((root / "RUN").resolve())
        for p in sorted(root.rglob("project.cfg")):
            if p.parent.name.upper() == "RUN":
                # skip extract scratch
                if "_extract" in [x.lower() for x in p.parts]:
                    continue
                found.append(p.parent.resolve())
    return sorted({p.resolve() for p in found}, key=lambda x: str(x).lower())


def _is_corpus_inbox_empty(corpus_inbox: Path) -> bool:
    if not corpus_inbox.is_dir():
        return True
    return not any(corpus_inbox.glob("*.tar.gz"))


# ---------------------------------------------------------------------------
# Tar inventory (no full extract)
# ---------------------------------------------------------------------------


def inventory_tar_members(tar_path: Path) -> dict[str, Any]:
    tables: set[str] = set()
    eipcfg = eipmodules = eipadapters = eipmoduletype = configio = False
    members: list[str] = []
    with tarfile.open(tar_path, "r:gz") as tf:
        names = sorted(tf.getnames())
        members = names
        for n in names:
            bn = Path(n).name
            low = bn.lower()
            if low.startswith("configio.asc"):
                configio = True
                tables.add("Configio")
            if low.startswith("eipmodules.asc"):
                eipmodules = True
                tables.add("EIPModules")
            if low.startswith("eipadapters.asc"):
                eipadapters = True
                tables.add("EIPAdapters")
            if low.startswith("eipmoduletype.asc"):
                eipmoduletype = True
                tables.add("EIPModuleType")
            if "eipcfg" in low and low.endswith((".xml", ".xml.save")):
                eipcfg = True
                tables.add("eipcfg")
            for hint in _TABLE_HINTS:
                if bn.lower().startswith(hint.lower()):
                    tables.add(hint.split(".")[0])
    return {
        "member_count": len(members),
        "tables": sorted(tables),
        "eipcfg_present": eipcfg,
        "eipmodules_present": eipmodules,
        "eipadapters_present": eipadapters,
        "eipmoduletype_present": eipmoduletype,
        "configio_present": configio,
        "members": members,
    }


def _read_tar_text(tf: tarfile.TarFile, member_name: str) -> str | None:
    try:
        m = tf.getmember(member_name)
    except KeyError:
        return None
    f = tf.extractfile(m)
    if not f:
        return None
    data = f.read()
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _tar_member_endswith(members: list[str], suffix: str) -> list[str]:
    suf = suffix.replace("\\", "/").lower()
    return sorted(n for n in members if n.replace("\\", "/").lower().endswith(suf))


def _prefer_machine_overlay(candidates: list[str], machine: str) -> str | None:
    if not candidates:
        return None
    mach = (machine or "").strip()
    if mach:
        exact = [c for c in candidates if c.replace("\\", "/").endswith(f".{mach}")]
        if exact:
            return sorted(exact)[0]
    # prefer unsuffixed .asc over .OLD / .BAK
    plain = [
        c
        for c in candidates
        if re.search(r"\.(asc)$", Path(c).name, re.I)
        or re.search(r"Configio\.asc$", Path(c).name, re.I)
    ]
    # Prefer machine-less base when no machine
    base = [
        c
        for c in candidates
        if Path(c).name.lower() in ("configio.asc", "eipmodules.asc", "eipadapters.asc", "eipmoduletype.asc")
    ]
    if base:
        return sorted(base)[0]
    if plain:
        return sorted(plain)[0]
    return sorted(candidates)[0]


def read_asc_from_tar(
    tar_path: Path, member_name: str, tmp_dir: Path
) -> list[dict[str, Any]]:
    """Extract one member to scratch and parse via fortna_asc (source archive untouched)."""
    with tarfile.open(tar_path, "r:gz") as tf:
        try:
            m = tf.getmember(member_name)
        except KeyError:
            return []
        dest = tmp_dir / Path(member_name).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tf.extractfile(m) as src, dest.open("wb") as out:
            if src:
                out.write(src.read())
    try:
        _, rows = read_asc(dest)
        return list(rows or [])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Deep inventory from a filesystem RUN dir
# ---------------------------------------------------------------------------


def _load_configio_any(run_dir: Path, machine: str = "") -> list[dict[str, Any]]:
    fortna = run_dir / "FORTNA"
    mach = (machine or "").strip()
    candidates: list[Path] = []
    if mach:
        candidates.append(fortna / f"Configio.asc.{mach}")
    candidates.append(fortna / "Configio.asc")
    candidates.extend(sorted(fortna.glob("Configio.asc*")))
    seen: set[Path] = set()
    for p in candidates:
        if p in seen or not p.is_file():
            continue
        seen.add(p)
        # skip backups
        if any(x in p.name.upper() for x in (".OLD", ".BAK", ".BARRY", ".SAVE")):
            continue
        try:
            _, rows = read_asc(p)
            return list(rows or [])
        except Exception:
            continue
    return []


def _load_eipmoduletype_rows(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "PROJECT" / "EIPModuleType.asc"
    if not path.is_file():
        return []
    try:
        _, rows = read_asc(path)
        return list(rows or [])
    except Exception:
        return []


def find_bank_collisions(
    eip_rows: list[dict[str, Any]],
    *,
    archive_sha256: str = "",
    machine: str = "",
) -> list[BankCollision]:
    inputs: dict[int, list[dict[str, Any]]] = defaultdict(list)
    outputs: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in eip_rows:
        try:
            ib = int(r.get("input_bank"))
        except (TypeError, ValueError):
            ib = None
        try:
            ob = int(r.get("output_bank"))
        except (TypeError, ValueError):
            ob = None
        rec = {
            "adapter": r.get("adapter"),
            "slot": r.get("slot"),
            "type": r.get("type"),
            "name": r.get("name"),
            "direction": r.get("direction"),
        }
        # bank 0 is typically "unused opposite direction" — still report but flag
        if ib is not None:
            inputs[ib].append(rec)
        if ob is not None:
            outputs[ob].append(rec)
    out: list[BankCollision] = []
    for bank in sorted(set(inputs) & set(outputs)):
        # Skip trivial self-pairs where every module lists both banks equal unused
        in_mods = inputs[bank]
        out_mods = outputs[bank]
        # Real collision: an input-side listing and an output-side listing that
        # are not the exact same module identity
        in_ids = {(m.get("adapter"), m.get("slot"), m.get("type")) for m in in_mods}
        out_ids = {(m.get("adapter"), m.get("slot"), m.get("type")) for m in out_mods}
        cross = True
        if in_ids == out_ids and bank == 0:
            notes = "bank_0_shared_placeholder"
        elif in_ids & out_ids and not (in_ids - out_ids) and not (out_ids - in_ids):
            notes = "same_modules_list_both_banks"
            cross = bank != 0
        else:
            notes = "inputbank_on_one_outputbank_on_another"
        if bank == 0 and notes == "bank_0_shared_placeholder":
            # still emit for inventory completeness
            pass
        out.append(
            BankCollision(
                bank=bank,
                input_modules=in_mods,
                output_modules=out_mods,
                archive_sha256=archive_sha256,
                machine=machine,
                notes=notes,
            )
        )
        _ = cross
    return out


def inout_mask_stats(
    configio_rows: list[dict[str, Any]],
    *,
    archive_sha256: str = "",
    machine: str = "",
) -> list[InOutMaskStat]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for r in configio_rows:
        mask = str(r.get("In_Out") or r.get("in_out") or "").strip()
        if not mask:
            continue
        iface = str(r.get("Interface") or r.get("interface") or "").strip()
        key = (mask, iface)
        b = buckets.get(key)
        desc = str(r.get("Desc") or r.get("desc") or "").strip()
        if not b:
            buckets[key] = {
                "mask": mask,
                "interface": iface,
                "count": 0,
                "examples": [],
            }
            b = buckets[key]
        b["count"] += 1
        if desc and desc not in b["examples"] and len(b["examples"]) < 5:
            b["examples"].append(desc)
    return sorted(
        [
            InOutMaskStat(
                mask=v["mask"],
                count=v["count"],
                archive_sha256=archive_sha256,
                machine=machine,
                interface=v["interface"],
                examples=v["examples"],
            )
            for v in buckets.values()
        ],
        key=lambda s: (-s.count, s.mask, s.interface),
    )


def hardware_family_hits(
    run_dir: Path,
    *,
    archive_sha256: str = "",
    machine: str = "",
) -> list[HardwareFamilyHit]:
    hits: dict[tuple[str, str, str], HardwareFamilyHit] = {}

    def _add(catalog: str, source: str) -> None:
        cat = (catalog or "").strip()
        if not cat or cat.upper() in ("N/A", "INVALID", ""):
            return
        fam = detect_family_from_catalog(cat)
        nd = classify_network_device(cat, fam)
        key = (cat.upper(), fam, source)
        if key in hits:
            hits[key].count += 1
        else:
            hits[key] = HardwareFamilyHit(
                catalog=cat,
                hardware_family=fam,
                network_device_class=nd,
                source=source,
                archive_sha256=archive_sha256,
                machine=machine,
                count=1,
            )

    for r in _load_eipmoduletype_rows(run_dir):
        _add(str(r.get("Name") or r.get("Type") or ""), "EIPModuleType")
    for r in _load_eipmodules_rows(run_dir, machine):
        _add(str(r.get("type") or ""), "EIPModules")
    return sorted(
        hits.values(),
        key=lambda h: (-h.count, h.catalog, h.source),
    )


def adapter_bridge_coverage(
    run_dir: Path,
    machine: str,
    *,
    archive_sha256: str = "",
) -> dict[str, Any]:
    try:
        topo = parse_eipcfg(run_dir, machine)
    except Exception as exc:
        return {
            "archive_sha256": archive_sha256,
            "machine": machine,
            "run_dir": str(run_dir),
            "error": str(exc),
            "proven_bridge": 0,
            "exact_name_fallback": 0,
            "substring_fallback": 0,
            "unjoined": 0,
            "adapter_count": 0,
            "bridges": {},
        }
    stats = dict(topo.get("adapter_bridge_stats") or {})
    bridges = stats.get("bridges") or {}
    # Also compute raw bridge map for reporting
    try:
        eip_rows = _load_eipmodules_rows(run_dir, machine)
        names = sorted(
            {
                (r.get("adapter") or "").strip()
                for r in eip_rows
                if (r.get("adapter") or "").strip()
            }
        )
        ad_rows = load_eipadapters_rows(run_dir, machine)
        raw = build_adapter_bridges(
            eipmodules_adapter_names=names,
            eipadapters_rows=ad_rows,
            eipcfg_adapters=list(topo.get("adapters") or []),
        )
        bridge_summary = {
            k: v.to_dict() for k, v in sorted(raw.items(), key=lambda kv: kv[0])
        }
    except Exception:
        bridge_summary = bridges if isinstance(bridges, dict) else {}

    status_counts = Counter(
        str((b or {}).get("status") or "UNKNOWN") for b in bridge_summary.values()
    )
    return _sorted_dict(
        {
            "archive_sha256": archive_sha256,
            "machine": machine,
            "run_dir": str(run_dir),
            "adapter_count": len(topo.get("adapters") or []),
            "proven_bridge": int(stats.get("proven_bridge") or 0),
            "exact_name_fallback": int(stats.get("exact_name_fallback") or 0),
            "substring_fallback": int(stats.get("substring_fallback") or 0),
            "unjoined": int(stats.get("unjoined") or 0),
            "bridge_status_counts": _sorted_dict(dict(status_counts)),
            "bridges": {
                k: bridge_summary[k] for k in sorted(bridge_summary.keys())
            },
        }
    )


def alias_type_mismatches(
    run_dir: Path,
    machine: str,
    *,
    archive_sha256: str = "",
) -> list[dict[str, Any]]:
    """Collect ALIAS_CATALOG_MISMATCH markers from enriched eipcfg modules."""
    out: list[dict[str, Any]] = []
    try:
        topo = parse_eipcfg(run_dir, machine)
    except Exception:
        return out
    for ad in topo.get("adapters") or []:
        for mod in ad.get("modules") or []:
            mm = mod.get("alias_catalog_mismatch")
            if not mm:
                continue
            out.append(
                _sorted_dict(
                    {
                        "archive_sha256": archive_sha256,
                        "machine": machine,
                        "adapter": ad.get("name") or ad.get("rio_name"),
                        "slot": mod.get("slot"),
                        "eipcfg_or_name_type": mm.get("eipcfg_or_name_type"),
                        "eipmodules_type": mm.get("eipmodules_type"),
                        "classification": mm.get("classification"),
                    }
                )
            )
    return sorted(
        out,
        key=lambda r: (
            str(r.get("adapter") or ""),
            int(r.get("slot") or 0),
            str(r.get("eipmodules_type") or ""),
        ),
    )


def deep_inventory_run(
    run_dir: Path,
    *,
    archive_sha256: str = "",
    filename: str = "",
    archive_class: str = ARCHIVE_RUN,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"
    ident = identity_from_run(run_dir, archive=filename)
    machine = ident.machine
    project = ident.project_name

    cfg_rows = _load_configio_any(run_dir, machine)
    dialects = classify_configio_rows(
        cfg_rows, archive_sha256=archive_sha256, machine=machine
    )
    eip_rows = _load_eipmodules_rows(run_dir, machine)
    collisions = find_bank_collisions(
        eip_rows, archive_sha256=archive_sha256, machine=machine
    )
    masks = inout_mask_stats(
        cfg_rows, archive_sha256=archive_sha256, machine=machine
    )
    hw = hardware_family_hits(
        run_dir, archive_sha256=archive_sha256, machine=machine
    )
    bridge = adapter_bridge_coverage(
        run_dir, machine, archive_sha256=archive_sha256
    )
    aliases = alias_type_mismatches(
        run_dir, machine, archive_sha256=archive_sha256
    )

    # Presence flags from filesystem
    fortna = run_dir / "FORTNA"
    proj = run_dir / "PROJECT"
    eipcfg_present = bool(list(fortna.glob("*eipcfg*.xml"))) if fortna.is_dir() else False
    tables: set[str] = set()
    if any(fortna.glob("Configio.asc*")):
        tables.add("Configio")
    if any(proj.glob("EIPModules.asc*")):
        tables.add("EIPModules")
    if any(proj.glob("EIPAdapters.asc*")):
        tables.add("EIPAdapters")
    if any(proj.glob("EIPModuleType.asc*")):
        tables.add("EIPModuleType")
    if eipcfg_present:
        tables.add("eipcfg")

    manifest = ArchiveManifest(
        sha256=archive_sha256 or ("peek:" + hashlib.sha1(str(run_dir).encode()).hexdigest()[:16]),
        filename=filename or run_dir.parent.name,
        archive_class=archive_class,
        source_path=str(run_dir),
        project=project,
        site=project,
        controller=machine,
        machine=machine,
        timestamp="",
        tables=sorted(tables),
        eipcfg_present=eipcfg_present,
        eipmodules_present="EIPModules" in tables,
        eipadapters_present="EIPAdapters" in tables,
        eipmoduletype_present="EIPModuleType" in tables,
        configio_present="Configio" in tables,
        run_dir=str(run_dir),
        member_count=0,
        notes=["extracted_run_dir"],
    )
    return {
        "manifest": manifest,
        "dialects": dialects,
        "collisions": collisions,
        "masks": masks,
        "hardware": hw,
        "bridge": bridge,
        "aliases": aliases,
        "configio_row_count": len(cfg_rows),
        "eipmodules_row_count": len(eip_rows),
    }


def deep_inventory_tar(
    tar_path: Path,
    *,
    extract_root: Path,
    peek_index: dict[str, Path],
) -> dict[str, Any]:
    meta = classify_archive_filename(tar_path.name)
    digest = sha256_file(tar_path)
    inv = inventory_tar_members(tar_path)
    machine = meta["machine"]
    # Prefer existing peek RUN for same machine
    run_dir: Path | None = peek_index.get(machine.upper()) if machine else None
    notes = ["source_archive_unmodified"]
    if run_dir and run_dir.is_dir():
        notes.append(f"deep_via_peek:{run_dir}")
        deep = deep_inventory_run(
            run_dir,
            archive_sha256=digest,
            filename=tar_path.name,
            archive_class=meta["archive_class"],
        )
        # overlay archive identity from filename
        man = deep["manifest"]
        man.sha256 = digest
        man.filename = tar_path.name
        man.source_path = str(tar_path)
        man.archive_class = meta["archive_class"]
        man.timestamp = meta["timestamp"]
        man.project = meta["project"] or man.project
        man.site = meta["site"] or man.site
        man.controller = meta["controller"] or man.controller
        man.machine = man.machine or meta["machine"]
        man.member_count = inv["member_count"]
        man.tables = sorted(set(man.tables) | set(inv["tables"]))
        man.eipcfg_present = man.eipcfg_present or inv["eipcfg_present"]
        man.eipmodules_present = man.eipmodules_present or inv["eipmodules_present"]
        man.eipadapters_present = man.eipadapters_present or inv["eipadapters_present"]
        man.eipmoduletype_present = man.eipmoduletype_present or inv["eipmoduletype_present"]
        man.configio_present = man.configio_present or inv["configio_present"]
        man.notes = sorted(set(man.notes) | set(notes))
        return deep

    # Selective scratch extract for inventory-only parse
    scratch = extract_root / digest[:16]
    scratch.mkdir(parents=True, exist_ok=True)
    notes.append(f"selective_scratch:{scratch}")

    with tarfile.open(tar_path, "r:gz") as tf:
        members = inv["members"]
        # project.cfg for identity
        cfg_members = [n for n in members if n.replace("\\", "/").endswith("RUN/project.cfg")]
        project = meta["project"]
        if cfg_members:
            text = _read_tar_text(tf, cfg_members[0]) or ""
            for line in text.splitlines():
                if "MACHINENAME" in line.upper():
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        machine = parts[1].strip() or machine
                if "PROJECTNAME" in line.upper():
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        project = parts[1].strip() or project

    # Pull Configio / EIPModules into scratch for dialect + bank inventory
    dialects: list[DialectHit] = []
    collisions: list[BankCollision] = []
    masks: list[InOutMaskStat] = []
    hw: list[HardwareFamilyHit] = []
    aliases: list[dict[str, Any]] = []
    bridge: dict[str, Any] = {
        "archive_sha256": digest,
        "machine": machine,
        "note": "adapter_bridge_requires_run_extract",
        "proven_bridge": 0,
        "adapter_count": 0,
    }

    with tempfile.TemporaryDirectory(prefix="sf_corpus_") as td:
        tmp = Path(td)
        with tarfile.open(tar_path, "r:gz") as tf:
            members = inv["members"]
            cfg_cands = [
                n
                for n in members
                if Path(n).name.lower().startswith("configio.asc")
            ]
            cfg_member = _prefer_machine_overlay(cfg_cands, machine)
            cfg_rows: list[dict[str, Any]] = []
            if cfg_member:
                cfg_rows = read_asc_from_tar(tar_path, cfg_member, tmp)
                dialects = classify_configio_rows(
                    cfg_rows, archive_sha256=digest, machine=machine
                )
                masks = inout_mask_stats(
                    cfg_rows, archive_sha256=digest, machine=machine
                )

            # Selective extract of RUN skeleton for bridge when eipcfg present
            if inv["eipcfg_present"] and inv["eipmodules_present"]:
                wanted_suffixes = (
                    "project.cfg",
                    "EIPModules.asc",
                    f"EIPModules.asc.{machine}" if machine else "",
                    "EIPAdapters.asc",
                    f"EIPAdapters.asc.{machine}" if machine else "",
                    "EIPModuleType.asc",
                )
                eipcfg_members = [
                    n
                    for n in members
                    if "eipcfg" in Path(n).name.lower()
                    and Path(n).name.lower().endswith(".xml")
                ]
                extract_names = set()
                for n in members:
                    bn = Path(n).name
                    for suf in wanted_suffixes:
                        if suf and bn == suf:
                            extract_names.add(n)
                    if cfg_member and n == cfg_member:
                        extract_names.add(n)
                for n in eipcfg_members:
                    extract_names.add(n)
                # Also machine Configio overlay
                if cfg_member:
                    extract_names.add(cfg_member)

                for n in sorted(extract_names):
                    try:
                        tf.extract(n, path=scratch)
                    except Exception:
                        continue

                # Locate RUN dir under scratch
                run_candidates = list(scratch.rglob("project.cfg"))
                run_dir = None
                for pc in run_candidates:
                    if pc.parent.name.upper() == "RUN":
                        run_dir = pc.parent
                        break
                if run_dir:
                    deep = deep_inventory_run(
                        run_dir,
                        archive_sha256=digest,
                        filename=tar_path.name,
                        archive_class=meta["archive_class"],
                    )
                    man = deep["manifest"]
                    man.sha256 = digest
                    man.filename = tar_path.name
                    man.source_path = str(tar_path)
                    man.archive_class = meta["archive_class"]
                    man.timestamp = meta["timestamp"]
                    man.project = project or meta["project"]
                    man.site = meta["site"] or project
                    man.controller = machine or meta["controller"]
                    man.machine = machine or man.machine
                    man.member_count = inv["member_count"]
                    man.tables = sorted(set(inv["tables"]) | set(man.tables))
                    man.notes = sorted(set(notes) | set(man.notes))
                    return deep

        # Fallback: member-level only
        for r in []:  # placeholder keeps structure clear
            pass

    # EIPModuleType from tar for hardware families
    with tempfile.TemporaryDirectory(prefix="sf_mt_") as td2:
        tmp2 = Path(td2)
        mt_cands = [
            n
            for n in inv["members"]
            if Path(n).name.lower().startswith("eipmoduletype.asc")
        ]
        mt_member = _prefer_machine_overlay(mt_cands, machine)
        if mt_member:
            rows = read_asc_from_tar(tar_path, mt_member, tmp2)
            fam_hits: dict[tuple[str, str, str], HardwareFamilyHit] = {}
            for r in rows:
                cat = str(r.get("Name") or r.get("Type") or "").strip()
                if not cat:
                    continue
                fam = detect_family_from_catalog(cat)
                nd = classify_network_device(cat, fam)
                key = (cat.upper(), fam, "EIPModuleType")
                if key in fam_hits:
                    fam_hits[key].count += 1
                else:
                    fam_hits[key] = HardwareFamilyHit(
                        catalog=cat,
                        hardware_family=fam,
                        network_device_class=nd,
                        source="EIPModuleType",
                        archive_sha256=digest,
                        machine=machine,
                        count=1,
                    )
            hw = sorted(
                fam_hits.values(),
                key=lambda h: (-h.count, h.catalog, h.source),
            )

        em_cands = [
            n
            for n in inv["members"]
            if Path(n).name.lower().startswith("eipmodules.asc")
        ]
        em_member = _prefer_machine_overlay(em_cands, machine)
        if em_member:
            # Minimal bank collision via raw ASC (InputBank/OutputBank columns)
            rows = read_asc_from_tar(tar_path, em_member, tmp2)
            eip_rows = []
            for r in rows:
                adapter = str(r.get("Adapter") or "").strip()
                mt = str(r.get("Type") or "").strip()
                conn = str(r.get("Connection") or "").strip()
                if not adapter or adapter.upper() in ("N/A", "INVALID"):
                    continue
                if not mt or mt.upper() in ("N/A", "INVALID"):
                    continue
                if conn.upper() == "HEADNODE" or "AENT" in mt.upper():
                    continue
                try:
                    slot = int(float(r.get("Slot") or 0))
                except (TypeError, ValueError):
                    slot = 0
                try:
                    ib = int(float(r.get("InputBank") or 0))
                except (TypeError, ValueError):
                    ib = 0
                try:
                    ob = int(float(r.get("OutputBank") or 0))
                except (TypeError, ValueError):
                    ob = 0
                eip_rows.append(
                    {
                        "name": str(r.get("Name") or "").strip(),
                        "adapter": adapter,
                        "type": mt,
                        "slot": slot,
                        "input_bank": ib,
                        "output_bank": ob,
                        "direction": "",
                    }
                )
            collisions = find_bank_collisions(
                eip_rows, archive_sha256=digest, machine=machine
            )

    manifest = ArchiveManifest(
        sha256=digest,
        filename=tar_path.name,
        archive_class=meta["archive_class"],
        source_path=str(tar_path),
        project=project or meta["project"],
        site=meta["site"] or project or meta["project"],
        controller=machine or meta["controller"],
        machine=machine or meta["machine"],
        timestamp=meta["timestamp"],
        tables=inv["tables"],
        eipcfg_present=inv["eipcfg_present"],
        eipmodules_present=inv["eipmodules_present"],
        eipadapters_present=inv["eipadapters_present"],
        eipmoduletype_present=inv["eipmoduletype_present"],
        configio_present=inv["configio_present"],
        run_dir="",
        member_count=inv["member_count"],
        notes=notes,
    )
    return {
        "manifest": manifest,
        "dialects": dialects,
        "collisions": collisions,
        "masks": masks,
        "hardware": hw,
        "bridge": bridge,
        "aliases": aliases,
        "configio_row_count": sum(d.count for d in dialects),
        "eipmodules_row_count": 0,
    }


# ---------------------------------------------------------------------------
# Static seeds
# ---------------------------------------------------------------------------


def seed_decoder_knowledge_registry() -> list[DecoderRuleRecord]:
    return [
        DecoderRuleRecord(
            rule_id="fortna_octal_bit_labels",
            title="Fortna octal bit labels",
            status=STATUS_PRODUCTION_RULE,
            summary="IO_Address_Bit digit strings in [0-7]+ parse as base-8 (label 10 → logical 8 / High).",
            evidence_tests=["tests/io/test_fortna_bit_address.py"],
            related_forms=[],
            related_modules=["fortna_bit_address"],
        ),
        DecoderRuleRecord(
            rule_id="family_aware_data_index",
            title="Family-aware Data[] index",
            status=STATUS_PRODUCTION_RULE,
            summary="1794 Flex: Data[slot-1]; 1734 POINT: raw chassis slot; UNKNOWN never assumes Flex.",
            evidence_tests=["tests/io/test_hardware_family_1734.py"],
            related_forms=[],
            related_modules=["fortna_hardware_family"],
        ),
        DecoderRuleRecord(
            rule_id="flex_1794_low_high_word_domain",
            title="Flex 1794 Low/High word domain",
            status=STATUS_CANDIDATE_RULE,
            summary="Configio LoHi Low/High maps module half; octal high labels align to High domain.",
            evidence_tests=[],
            related_forms=[FORM_UNKNOWN],
            related_modules=["fortna_physical_word_resolver", "fortna_bit_address"],
        ),
        DecoderRuleRecord(
            rule_id="direction_aware_bank_selection",
            title="Direction-aware bank selection",
            status=STATUS_PRODUCTION_RULE,
            summary="Same numeric bank may be InputBank on one module and OutputBank on another — select by direction.",
            evidence_tests=[
                "tests/io/test_direction_aware_bank.py",
                "tests/io/test_plc5_io_endpoint_collision.py",
            ],
            related_forms=[],
            related_modules=["fortna_physical_word_resolver"],
        ),
        DecoderRuleRecord(
            rule_id="catalog_word_bank_configio",
            title="Catalog-word-bank Configio Desc",
            status=STATUS_PRODUCTION_RULE,
            summary="Desc form 1794-IA16-600-4 → catalog + Fortna word + Configio.Bank ↔ EIPModules banks.",
            evidence_tests=["tests/io/test_io_ownership_catalog_word_bank.py"],
            related_forms=["CATALOG_WORD_BANK"],
            related_modules=["fortna_physical_word_resolver", "fortna_io_ownership_profile"],
        ),
        DecoderRuleRecord(
            rule_id="catalog_prefix_index_bank",
            title="Catalog-prefix index / panel-catalog",
            status=STATUS_CANDIDATE_RULE,
            summary="Desc forms CP2-1794-IA16-3 and 1794-IA16-5 encode catalog + index; bank join rules vary by site evidence.",
            evidence_tests=["tests/io/test_plc2_configio_compiler.py"],
            related_forms=["CATALOG_INDEX"],
            related_modules=["fortna_physical_word_resolver"],
        ),
        DecoderRuleRecord(
            rule_id="remote_io_rack_taxonomy",
            title="Remote I/O rack taxonomy",
            status=STATUS_PRODUCTION_RULE,
            summary="Classify Ethernet nodes by catalog (REMOTE_IO_RACK / NETWORK_DRIVE / REMOTE_TERMINAL_BUS), not name alone.",
            evidence_tests=[
                "tests/io/test_rockwell_rack_discovery.py",
                "tests/io/test_direction_aware_bank.py",
            ],
            related_forms=[],
            related_modules=["fortna_rack_discovery"],
        ),
        DecoderRuleRecord(
            rule_id="exact_eipadapters_ip_bridge",
            title="Exact EIPAdapters TargetIP bridge",
            status=STATUS_PRODUCTION_RULE,
            summary="EIPModules.Adapter == EIPAdapters.Name and TargetIP == eipcfg.targetip (unique) → PROVEN.",
            evidence_tests=["tests/io/test_eip_adapter_bridge.py"],
            related_forms=[],
            related_modules=["fortna_eip_adapter_bridge"],
        ),
    ]


def evidence_authority_matrix() -> dict[str, Any]:
    """Static documented matrix (mirrors config/run_evidence_authority.json + learning notes)."""
    path = ROOT / "config" / "run_evidence_authority.json"
    base: dict[str, Any] = {}
    if path.is_file():
        try:
            base = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            base = {}
    learning_facts = [
        {
            "fact": "configio_dialect_form",
            "primary": ["Configio.Desc"],
            "supporting": ["EIPModules", "eipcfg"],
            "fallback": "UNKNOWN",
            "notes": "Classifier is structural only — never invents semantics for UNKNOWN",
        },
        {
            "fact": "physical_io_endpoint",
            "primary": ["Configio"],
            "supporting": ["EIPModules", "EIPAdapters", "eipcfg"],
            "fallback": "REVIEW_REQUIRED",
        },
        {
            "fact": "adapter_identity_bridge",
            "primary": ["EIPModules.Adapter", "EIPAdapters.Name", "EIPAdapters.TargetIP", "eipcfg.targetip"],
            "supporting": [],
            "fallback": "UNKNOWN",
            "notes": "Substring name match is DERIVED only — never PROVEN",
        },
        {
            "fact": "bank_direction_collision",
            "primary": ["EIPModules.InputBank", "EIPModules.OutputBank"],
            "supporting": ["Configio.In_Out", "Configio.Bank"],
            "fallback": "REVIEW_REQUIRED",
        },
        {
            "fact": "hardware_family",
            "primary": ["EIPModuleType", "EIPModules.Type", "catalog_signature"],
            "supporting": ["eipcfg module type"],
            "fallback": "UNKNOWN",
        },
        {
            "fact": "network_device_class",
            "primary": ["catalog_number"],
            "supporting": ["EIPModuleType connection"],
            "fallback": "UNKNOWN_NETWORK_DEVICE",
            "notes": "Beckhoff BK/KL → REMOTE_TERMINAL_BUS; AENT/AENTR → REMOTE_IO_RACK",
        },
        {
            "fact": "finished_l5x",
            "primary": [],
            "supporting": [],
            "fallback": "NOT_DISCOVERY_AUTHORITY",
            "notes": "Validation oracle only — corpus scanner never reads finished L5X",
        },
    ]
    return _sorted_dict(
        {
            "title": "Learning Evidence Authority Matrix",
            "generated_from": str(path.relative_to(ROOT)) if path.is_file() else "",
            "confidence_levels": base.get("confidence_levels")
            or ["PROVEN", "DERIVED", "ENGINEER_ASSIGNED", "REVIEW_REQUIRED", "UNKNOWN"],
            "forbidden_levels": base.get("forbidden_levels")
            or ["GUESSED", "ASSUMED", "PROBABLY"],
            "file_resolution_precedence": base.get("file_resolution_precedence") or [],
            "facts": learning_facts,
            "base_fact_count": len(base.get("facts") or []),
        }
    )


def rule_coverage_matrix(
    registry: list[DecoderRuleRecord],
    manifests: list[ArchiveManifest],
    dialects: list[DialectHit],
) -> dict[str, Any]:
    form_counts = Counter(d.configio_form for d in dialects)
    machines = sorted({m.machine for m in manifests if m.machine})
    rows = []
    for rule in sorted(registry, key=lambda r: r.rule_id):
        related = set(rule.related_forms or [])
        hit_count = sum(form_counts.get(f, 0) for f in related) if related else None
        rows.append(
            _sorted_dict(
                {
                    "rule_id": rule.rule_id,
                    "status": rule.status,
                    "evidence_tests": rule.evidence_tests,
                    "related_forms": rule.related_forms,
                    "dialect_hit_count": hit_count,
                    "peek_machines_available": machines,
                    "coverage": (
                        "TESTED"
                        if rule.status == STATUS_PRODUCTION_RULE
                        else "CANDIDATE"
                    ),
                }
            )
        )
    return _sorted_dict(
        {
            "title": "Decoder Rule Coverage Matrix",
            "machines_scanned": machines,
            "dialect_form_counts": _sorted_dict(dict(form_counts)),
            "rules": rows,
        }
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def build_investigation_queue(
    unknown_clusters: list[Any],
    collisions: list[BankCollision],
    aliases: list[dict[str, Any]],
    bridges: list[dict[str, Any]],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for c in unknown_clusters[:50]:
        d = c.to_dict() if hasattr(c, "to_dict") else dict(c)
        items.append(
            _sorted_dict(
                {
                    "kind": "UNKNOWN_CONFIGIO_CLUSTER",
                    "priority": "HIGH" if d.get("count", 0) >= 10 else "MEDIUM",
                    "cluster_id": d.get("cluster_id"),
                    "count": d.get("count"),
                    "examples": d.get("example_raw") or [],
                    "signature_id": d.get("signature_id"),
                    "fields": d.get("fields") or {},
                }
            )
        )
    # Non-zero meaningful bank collisions
    for bc in collisions:
        if bc.bank == 0 and "placeholder" in (bc.notes or ""):
            continue
        if bc.notes == "same_modules_list_both_banks":
            continue
        items.append(
            _sorted_dict(
                {
                    "kind": "BANK_COLLISION",
                    "priority": "HIGH",
                    "bank": bc.bank,
                    "machine": bc.machine,
                    "archive_sha256": bc.archive_sha256,
                    "notes": bc.notes,
                    "input_count": len(bc.input_modules),
                    "output_count": len(bc.output_modules),
                }
            )
        )
    for a in aliases[:40]:
        items.append(
            _sorted_dict(
                {
                    "kind": "ALIAS_CATALOG_MISMATCH",
                    "priority": "MEDIUM",
                    **a,
                }
            )
        )
    for b in bridges:
        unjoined = int(b.get("unjoined") or 0)
        substring = int(b.get("substring_fallback") or 0)
        if unjoined or substring:
            items.append(
                _sorted_dict(
                    {
                        "kind": "ADAPTER_BRIDGE_GAP",
                        "priority": "HIGH" if unjoined else "MEDIUM",
                        "machine": b.get("machine"),
                        "archive_sha256": b.get("archive_sha256"),
                        "unjoined": unjoined,
                        "substring_fallback": substring,
                        "proven_bridge": b.get("proven_bridge"),
                    }
                )
            )
    items = sorted(
        items,
        key=lambda x: (
            0 if x.get("priority") == "HIGH" else 1,
            str(x.get("kind") or ""),
            str(x.get("cluster_id") or x.get("bank") or x.get("machine") or ""),
        ),
    )
    return _sorted_dict({"count": len(items), "items": items})


def render_txt_report(title: str, lines: list[str]) -> str:
    body = "\n".join(lines)
    return f"{title}\n{'=' * len(title)}\n{body}\n"


def overnight_report(
    *,
    manifests: list[ArchiveManifest],
    dialects: list[DialectHit],
    unknown_clusters: list[Any],
    collisions: list[BankCollision],
    bridges: list[dict[str, Any]],
    notes: list[str],
    out_dir: Path,
) -> str:
    form_counts = Counter(d.configio_form for d in dialects for _ in range(d.count))
    class_counts = Counter(m.archive_class for m in manifests)
    lines = [
        f"generated_at: {_utc_now()}",
        f"out_dir: {out_dir}",
        f"archive_count: {len(manifests)}",
        f"archive_classes: {dict(sorted(class_counts.items()))}",
        f"dialect_rows_classified: {sum(d.count for d in dialects)}",
        f"dialect_forms: {dict(sorted(form_counts.items()))}",
        f"unknown_clusters: {len(unknown_clusters)}",
        f"bank_collisions: {len(collisions)}",
        f"adapter_bridge_reports: {len(bridges)}",
        "",
        "notes:",
    ]
    for n in notes:
        lines.append(f"  - {n}")
    lines.append("")
    lines.append("top_unknown_clusters:")
    for c in unknown_clusters[:15]:
        d = c.to_dict() if hasattr(c, "to_dict") else dict(c)
        ex = ", ".join((d.get("example_raw") or [])[:3])
        lines.append(
            f"  - {d.get('cluster_id')} count={d.get('count')} examples=[{ex}]"
        )
    lines.append("")
    lines.append("manifests:")
    for m in manifests:
        lines.append(
            f"  - {m.filename} class={m.archive_class} project={m.project} "
            f"machine={m.machine} sha256={m.sha256[:12]}…"
        )
    return render_txt_report("OVERNIGHT CORPUS REPORT", lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build_peek_index(extra_runs: list[Path] | None = None) -> dict[str, Path]:
    idx: dict[str, Path] = {}
    for p in list(PEEK_RUN_HINTS) + list(extra_runs or []):
        if not p.is_dir():
            continue
        try:
            ident = identity_from_run(p)
        except Exception:
            continue
        if ident.machine:
            idx[ident.machine.upper()] = p.resolve()
    return idx


def scan_corpus(roots: list[Path], out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    extract_root = out_dir / "_extract"
    extract_root.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []
    corpus_inbox = ROOT / "workspace" / "corpus_inbox"
    inbox = ROOT / "workspace" / "inbox"
    # Curtis/Gilfoyle random corpus drop (authoritative overnight sample)
    desktop_random = Path(r"C:\Users\curtiskricke\Desktop\Random Tar.gz")

    root_set = {r.resolve() for r in roots}
    if desktop_random.is_dir():
        root_set.add(desktop_random.resolve())
        n_desk = len(list(desktop_random.glob("*.tar.gz")))
        notes.append(
            f"primary random corpus: {desktop_random} ({n_desk} *.tar.gz)"
        )
    if _is_corpus_inbox_empty(corpus_inbox):
        notes.append(
            "workspace/corpus_inbox has no *.tar.gz — using Desktop Random Tar.gz "
            "+ workspace/inbox + extracted peeks"
        )
        if inbox.is_dir():
            root_set.add(inbox.resolve())
        for peek in PEEK_RUN_HINTS:
            if peek.is_dir():
                root_set.add(peek.resolve())
    roots = sorted(root_set, key=lambda p: str(p).lower())

    archives = discover_archives(roots)
    run_dirs = discover_run_dirs(roots)
    peek_index = build_peek_index(run_dirs)

    results: list[dict[str, Any]] = []
    seen_sha: set[str] = set()

    for tar_path in archives:
        # Skip nested copies under cp5-run/_archive if roots somehow include them —
        # still allow inbox.
        try:
            deep = deep_inventory_tar(
                tar_path, extract_root=extract_root, peek_index=peek_index
            )
        except Exception as exc:
            meta = classify_archive_filename(tar_path.name)
            digest = sha256_file(tar_path)
            deep = {
                "manifest": ArchiveManifest(
                    sha256=digest,
                    filename=tar_path.name,
                    archive_class=meta["archive_class"],
                    source_path=str(tar_path),
                    project=meta["project"],
                    site=meta["site"],
                    controller=meta["controller"],
                    machine=meta["machine"],
                    timestamp=meta["timestamp"],
                    notes=[f"inventory_error:{exc}"],
                ),
                "dialects": [],
                "collisions": [],
                "masks": [],
                "hardware": [],
                "bridge": {"error": str(exc), "machine": meta["machine"]},
                "aliases": [],
            }
        sha = deep["manifest"].sha256
        if sha in seen_sha:
            continue
        seen_sha.add(sha)
        results.append(deep)

    # Add peek RUN dirs not already covered by an archive machine match
    covered_machines = {
        (r["manifest"].machine or "").upper()
        for r in results
        if r["manifest"].machine
    }
    for run_dir in sorted(set(run_dirs) | set(p for p in PEEK_RUN_HINTS if p.is_dir()), key=lambda p: str(p).lower()):
        try:
            ident = identity_from_run(run_dir)
        except Exception:
            continue
        mach = (ident.machine or "").upper()
        if mach and mach in covered_machines:
            continue
        # Avoid double-counting peeks that match archive machines already inventoried
        deep = deep_inventory_run(
            run_dir,
            archive_sha256="",
            filename=f"peek:{run_dir}",
            archive_class=ARCHIVE_RUN,
        )
        sha = deep["manifest"].sha256
        if sha in seen_sha:
            continue
        seen_sha.add(sha)
        results.append(deep)
        if mach:
            covered_machines.add(mach)

    # Stable order
    results.sort(
        key=lambda r: (
            r["manifest"].archive_class,
            r["manifest"].project,
            r["manifest"].machine,
            r["manifest"].filename,
        )
    )

    manifests = [r["manifest"] for r in results]
    all_dialects: list[DialectHit] = []
    all_collisions: list[BankCollision] = []
    all_masks: list[InOutMaskStat] = []
    all_hw: list[HardwareFamilyHit] = []
    all_bridges: list[dict[str, Any]] = []
    all_aliases: list[dict[str, Any]] = []
    for r in results:
        all_dialects.extend(r.get("dialects") or [])
        all_collisions.extend(r.get("collisions") or [])
        all_masks.extend(r.get("masks") or [])
        all_hw.extend(r.get("hardware") or [])
        if r.get("bridge"):
            all_bridges.append(r["bridge"])
        all_aliases.extend(r.get("aliases") or [])

    unknown_hits = [d for d in all_dialects if d.configio_form == FORM_UNKNOWN]
    unknown_clusters = cluster_unknown_dialects(unknown_hits)

    registry = seed_decoder_knowledge_registry()
    authority = evidence_authority_matrix()
    coverage = rule_coverage_matrix(registry, manifests, all_dialects)
    queue = build_investigation_queue(
        unknown_clusters, all_collisions, all_aliases, all_bridges
    )

    # ---- Emit artifacts ----
    corpus_manifest = {
        "generated_at": _utc_now(),
        "archive_count": len(manifests),
        "archives": [m.to_dict() for m in manifests],
    }
    _write_json(out_dir / "corpus_manifest.json", corpus_manifest)

    form_counts = Counter()
    for d in all_dialects:
        form_counts[d.configio_form] += d.count
    summary = _sorted_dict(
        {
            "generated_at": _utc_now(),
            "roots": [str(r) for r in roots],
            "notes": notes,
            "archive_count": len(manifests),
            "archive_class_counts": _sorted_dict(dict(Counter(m.archive_class for m in manifests))),
            "machines": sorted({m.machine for m in manifests if m.machine}),
            "projects": sorted({m.project for m in manifests if m.project}),
            "dialect_form_counts": _sorted_dict(dict(form_counts)),
            "unknown_cluster_count": len(unknown_clusters),
            "bank_collision_count": len(all_collisions),
            "alias_mismatch_count": len(all_aliases),
            "hardware_family_hit_count": len(all_hw),
            "configio_rows_classified": sum(d.count for d in all_dialects),
        }
    )
    _write_json(out_dir / "corpus_summary.json", summary)
    _write_text(
        out_dir / "corpus_summary.txt",
        render_txt_report(
            "CORPUS SUMMARY",
            [f"{k}: {v}" for k, v in summary.items()],
        ),
    )

    _write_json(
        out_dir / "bank_collisions.json",
        {
            "count": len(all_collisions),
            "collisions": [c.to_dict() for c in all_collisions],
        },
    )
    _write_json(
        out_dir / "inout_masks.json",
        {
            "count": len(all_masks),
            "masks": [m.to_dict() for m in all_masks],
        },
    )
    _write_json(
        out_dir / "adapter_bridge_coverage.json",
        {"count": len(all_bridges), "reports": all_bridges},
    )
    _write_json(
        out_dir / "dialect_inventory.json",
        {
            "form_counts": _sorted_dict(dict(form_counts)),
            "hits": [d.to_dict() for d in sorted(all_dialects, key=lambda h: (-h.count, h.configio_form, h.raw_example, h.machine))],
            "unknown_clusters": [c.to_dict() for c in unknown_clusters],
        },
    )
    _write_json(
        out_dir / "hardware_families.json",
        {
            "count": len(all_hw),
            "hits": [h.to_dict() for h in sorted(all_hw, key=lambda x: (-x.count, x.catalog, x.machine))],
        },
    )
    _write_json(
        out_dir / "alias_type_mismatches.json",
        {"count": len(all_aliases), "mismatches": all_aliases},
    )

    _write_json(out_dir / "evidence_authority_matrix.json", authority)
    auth_lines = [
        f"confidence_levels: {authority.get('confidence_levels')}",
        f"forbidden_levels: {authority.get('forbidden_levels')}",
        "",
        "facts:",
    ]
    for f in authority.get("facts") or []:
        auth_lines.append(
            f"  - {f.get('fact')}: primary={f.get('primary')} "
            f"supporting={f.get('supporting')} fallback={f.get('fallback')}"
        )
    _write_text(
        out_dir / "evidence_authority_matrix.txt",
        render_txt_report("EVIDENCE AUTHORITY MATRIX", auth_lines),
    )

    _write_json(out_dir / "investigation_queue.json", queue)
    q_lines = [f"count: {queue.get('count')}", ""]
    for it in queue.get("items") or []:
        q_lines.append(
            f"  [{it.get('priority')}] {it.get('kind')} "
            f"{it.get('cluster_id') or it.get('bank') or it.get('machine') or ''}"
        )
    _write_text(
        out_dir / "investigation_queue.txt",
        render_txt_report("INVESTIGATION QUEUE", q_lines),
    )

    _write_json(
        out_dir / "decoder_knowledge_registry.json",
        {
            "count": len(registry),
            "rules": [r.to_dict() for r in registry],
        },
    )
    _write_json(out_dir / "rule_coverage_matrix.json", coverage)
    cov_lines = [
        f"machines_scanned: {coverage.get('machines_scanned')}",
        f"dialect_form_counts: {coverage.get('dialect_form_counts')}",
        "",
        "rules:",
    ]
    for row in coverage.get("rules") or []:
        cov_lines.append(
            f"  - {row.get('rule_id')} status={row.get('status')} "
            f"coverage={row.get('coverage')} tests={row.get('evidence_tests')}"
        )
    _write_text(
        out_dir / "rule_coverage_matrix.txt",
        render_txt_report("RULE COVERAGE MATRIX", cov_lines),
    )

    report = overnight_report(
        manifests=manifests,
        dialects=all_dialects,
        unknown_clusters=unknown_clusters,
        collisions=all_collisions,
        bridges=all_bridges,
        notes=notes,
        out_dir=out_dir,
    )
    _write_text(out_dir / "OVERNIGHT_CORPUS_REPORT.txt", report)

    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Site Forge corpus / learning scanner")
    ap.add_argument(
        "--roots",
        nargs="+",
        default=[
            r"C:\Users\curtiskricke\Desktop\Random Tar.gz",
            str(ROOT / "workspace" / "corpus_inbox"),
            str(ROOT / "workspace" / "inbox"),
        ],
        help="Roots to scan for *.tar.gz and RUN dirs",
    )
    ap.add_argument(
        "--out",
        default=str(ROOT / "exports" / "learning"),
        help="Output directory (default: exports/learning)",
    )
    args = ap.parse_args(argv)
    roots = [Path(r) for r in args.roots]
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    summary = scan_corpus(roots, out_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
