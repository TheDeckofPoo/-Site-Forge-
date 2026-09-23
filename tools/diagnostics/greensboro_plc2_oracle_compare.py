#!/usr/bin/env python3
"""Diagnostics-only Greensboro PLC2 finished-oracle vs Site Forge IO compare.

Loads the finished L5X IO_MAP oracle and Site Forge bindings (generated L5X
IO_MAP and/or physical_io_map from ORNCCP2 / Greensboro RUN peeks). Compares
endpoint → device / UDT / member. Never imported by production binders.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DIAG = Path(__file__).resolve().parent
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from l5x_io_map_oracle import (  # noqa: E402
    DEFAULT_ORACLE,
    build_oracle_io_map,
    parse_io_map_routines,
    parse_l5x_tag_datatypes,
    split_device_member,
)

OUT_JSON = ROOT / "exports" / "diagnostics" / "greensboro_plc2_io_oracle_compare.json"
OUT_MD = ROOT / "exports" / "diagnostics" / "greensboro_plc2_io_oracle_compare.md"

CLASSIFICATIONS = (
    "MATCH",
    "SITE_FORGE_WRONG_DEVICE",
    "SITE_FORGE_WRONG_UDT",
    "SITE_FORGE_WRONG_MEMBER",
    "SITE_FORGE_WRONG_ENDPOINT",
    "ORACLE_ADDS_INFO",
    "REVIEW_REQUIRED",
)

# Endpoint forms seen in physical_io_map notes / module_data_ref.
_ALT_ENDPOINT_RE = re.compile(
    r"(?P<adapter>[A-Za-z0-9_]+):(?P<dir>[IO])\.Data\[(?P<slot>\d+)\]\.(?P<bit>\d+)"
)
_COLON_FORM_RE = re.compile(
    r"(?P<adapter>[A-Za-z0-9_]+):(?P<slot>\d+):(?P<dir>[IO])\.Data\.(?P<bit>\d+)"
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _norm(s: str) -> str:
    return _clean(s).upper()


def normalize_endpoint(raw: str) -> str:
    """Normalize CP2RIO0:1:I.Data.8 / alt=… forms to CP2RIO0:I.Data[1].8."""
    s = _clean(raw)
    if not s:
        return ""
    m = _ALT_ENDPOINT_RE.search(s)
    if m:
        return (
            f"{m.group('adapter')}:{m.group('dir')}.Data[{m.group('slot')}].{m.group('bit')}"
        )
    m = _COLON_FORM_RE.search(s)
    if m:
        return (
            f"{m.group('adapter')}:{m.group('dir')}.Data[{m.group('slot')}].{m.group('bit')}"
        )
    return s


def discover_ornccp2_run(root: Path = ROOT) -> Path | None:
    """Find Greensboro / ORNCCP2 RUN under workspace peeks (if present)."""
    candidates = [
        root / "workspace" / "_plc2_run_peek" / "RUN",
        root / "workspace" / "cp4-run" / "RUN",
    ]
    # Any peek folder containing ORNCCP2 Configio / identity.
    peek_root = root / "workspace"
    if peek_root.is_dir():
        for p in sorted(peek_root.glob("_*/**/RUN")):
            candidates.append(p)
        for p in sorted(peek_root.glob("**/ORNCCP2*/**/RUN")):
            candidates.append(p)

    for run in candidates:
        if not run.is_dir():
            continue
        markers = [
            run / "FORTNA" / "Configio.asc.ORNCCP2",
            run / "PROJECT" / "EIPModules.asc.ORNCCP2",
            run / "identity.cfg",
        ]
        if any(m.is_file() for m in markers):
            # Prefer identity claiming ORNCCP2 when readable.
            ident = run / "identity.cfg"
            if ident.is_file():
                txt = ident.read_text(encoding="utf-8", errors="replace")
                if "ORNCCP2" in txt.upper() or "GREENSBORO" in txt.upper():
                    return run
            if (run / "FORTNA" / "Configio.asc.ORNCCP2").is_file():
                return run
    # Fall back: first candidate with ORNCCP2 overlay files.
    for run in candidates:
        if (run / "FORTNA" / "Configio.asc.ORNCCP2").is_file():
            return run
    return None


def discover_site_forge_l5x(root: Path = ROOT) -> Path | None:
    """Prefer newest ORNCCP2 Site Forge L5X; current/ before history/."""
    folders = (
        root / "exports" / "current",
        root / "exports" / "diagnostics" / "ornccp2_t2es_fix",
        root / "exports" / "plc2-fidelity",
        root / "exports" / "stabilization",
        root / "exports" / "autogen" / "history",
    )
    for folder in folders:
        if not folder.is_dir():
            continue
        pools = [p for p in list(folder.glob("ORNCCP2*.L5X")) + list(folder.glob("ORNCCP2.L5X")) if p.is_file()]
        if not pools:
            continue
        uniq = {p.resolve(): p for p in pools}
        return max(uniq.values(), key=lambda p: p.stat().st_mtime)
    return None


def discover_physical_io_map(root: Path = ROOT) -> Path | None:
    """Latest ORNCCP2 build physical_io_map.csv under workspace/.internal/builds."""
    builds = root / "workspace" / ".internal" / "builds"
    if not builds.is_dir():
        return None
    cands: list[Path] = []
    for b in builds.iterdir():
        if not b.is_dir():
            continue
        phys = b / "physical_io_map.csv"
        if not phys.is_file():
            continue
        # Prefer builds that mention ORNCCP2.
        tags = b / "ORNCCP2_Controller_Tags.csv"
        manifest_hit = False
        for m in b.glob("*.manifest.json"):
            try:
                if "ORNCCP2" in m.read_text(encoding="utf-8", errors="replace"):
                    manifest_hit = True
                    break
            except OSError:
                continue
        if tags.is_file() or manifest_hit:
            cands.append(phys)
    if not cands:
        # Any newest physical_io_map as weak fallback.
        all_phys = list(builds.glob("*/physical_io_map.csv"))
        return max(all_phys, key=lambda p: p.stat().st_mtime) if all_phys else None
    return max(cands, key=lambda p: p.stat().st_mtime)


def load_site_forge_from_l5x(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    dts = parse_l5x_tag_datatypes(text)
    mappings = parse_io_map_routines(text, tag_datatypes=dts)
    by_endpoint = {
        r["endpoint"]: r for r in mappings if not r.get("placeholder") and r.get("logical_tag")
    }
    by_device: dict[str, list[str]] = defaultdict(list)
    for r in by_endpoint.values():
        by_device[r["device"]].append(r["endpoint"])
    return {
        "kind": "l5x_io_map",
        "path": str(path),
        "tag_datatypes": dts,
        "mappings": mappings,
        "by_endpoint": by_endpoint,
        "by_device": dict(by_device),
    }


def load_site_forge_from_equipment_binding(
    run_dir: Path,
    physical_csv: Path | None = None,
) -> dict[str, Any]:
    """Join RUN equipment_binding (by raw Fortna name) onto physical endpoints.

    Diagnostics only — uses production binder as a library, never the reverse.
    """
    scripts = ROOT / "tools" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from fortna_asc import read_asc  # noqa: WPS433
    from fortna_equipment_binding import build_equipment_bindings  # noqa: WPS433

    conv = Path(run_dir) / "FORTNA" / "Conveyor.asc"
    if not conv.is_file():
        raise FileNotFoundError(conv)
    _h, rows = read_asc(conv)
    # Scope to ORNCCP2 when Machine_Name present
    scoped = [
        r
        for r in rows
        if not (r.get("Machine_Name") or "").strip()
        or (r.get("Machine_Name") or "").strip().upper() == "ORNCCP2"
    ]
    if not scoped:
        scoped = list(rows)
    bundle = build_equipment_bindings(scoped, machine="ORNCCP2")
    by_raw = bundle.get("by_raw") or {}

    phys = physical_csv or discover_physical_io_map()
    by_endpoint: dict[str, dict[str, Any]] = {}
    by_device: dict[str, list[str]] = defaultdict(list)
    mappings: list[dict[str, Any]] = []

    if phys and phys.is_file():
        csv_bundle = load_site_forge_from_physical_csv(phys)
        for ep, base in (csv_bundle.get("by_endpoint") or {}).items():
            raw = _clean(base.get("fortna_name") or base.get("device"))
            bind = by_raw.get(raw.upper()) if raw else None
            if bind and bind.get("member_path"):
                tag = _clean(bind.get("member_path"))
                device = _clean(bind.get("logix_tag") or bind.get("canonical_id"))
                member = _clean(bind.get("member"))
                if not member and "." in tag:
                    device, member = split_device_member(tag)
                entry = {
                    "routine": "",
                    "endpoint": ep,
                    "logical_tag": tag,
                    "device": device,
                    "member": member,
                    "datatype": _clean(bind.get("datatype")),
                    "placeholder": False,
                    "source": f"equipment_binding+{phys}",
                    "fortna_name": raw,
                    "confidence": bind.get("confidence"),
                    "rule": bind.get("rule"),
                }
            else:
                entry = dict(base)
                entry["source"] = f"physical_csv_unbound+{phys}"
                if bind and bind.get("confidence") == "REVIEW_REQUIRED":
                    entry["datatype"] = ""
                    entry["member"] = ""
                    entry["review_reason"] = bind.get("review_reason")
            by_endpoint[ep] = entry
            by_device[entry.get("device") or raw].append(ep)
            mappings.append(entry)
    else:
        # No physical map — expose binder by synthetic key raw-only (limited compare)
        for raw_u, bind in by_raw.items():
            if not bind.get("member_path"):
                continue
            tag = bind["member_path"]
            device = bind.get("logix_tag") or bind.get("canonical_id") or ""
            member = bind.get("member") or ""
            entry = {
                "endpoint": f"RAW:{raw_u}",
                "logical_tag": tag,
                "device": device,
                "member": member,
                "datatype": bind.get("datatype") or "",
                "placeholder": False,
                "source": "equipment_binding_only",
                "fortna_name": bind.get("raw_name"),
            }
            by_endpoint[entry["endpoint"]] = entry
            by_device[device].append(entry["endpoint"])
            mappings.append(entry)

    return {
        "kind": "equipment_binding",
        "path": str(run_dir),
        "tag_datatypes": {},
        "mappings": mappings,
        "by_endpoint": by_endpoint,
        "by_device": dict(by_device),
        "binding_counts": bundle.get("counts"),
        "binding_matrix": bundle.get("binding_matrix"),
    }


def load_site_forge_from_physical_csv(path: Path) -> dict[str, Any]:
    """Fallback bindings: fortna_name at endpoint (member/UDT unknown)."""
    rows = list(csv.DictReader(path.open(encoding="utf-8", errors="replace")))
    by_endpoint: dict[str, dict[str, Any]] = {}
    by_device: dict[str, list[str]] = defaultdict(list)
    mappings: list[dict[str, Any]] = []
    for row in rows:
        name = _clean(row.get("fortna_name"))
        if not name:
            continue
        notes = _clean(row.get("notes"))
        ref = _clean(row.get("module_data_ref"))
        endpoint = ""
        m_alt = re.search(r"alt=([^;]+)", notes)
        if m_alt:
            endpoint = normalize_endpoint(m_alt.group(1))
        if not endpoint:
            endpoint = normalize_endpoint(ref)
        if not endpoint:
            continue
        entry = {
            "routine": "",
            "endpoint": endpoint,
            "adapter": endpoint.split(":", 1)[0] if ":" in endpoint else "",
            "direction": "",
            "data_index": None,
            "bit": None,
            "logical_tag": name,
            "device": name,
            "member": "",
            "datatype": "",
            "placeholder": False,
            "rung": "",
            "source": str(path),
            "fortna_name": name,
            "device_type": _clean(row.get("device_type")),
        }
        m_ch = _ALT_ENDPOINT_RE.fullmatch(endpoint)
        if m_ch:
            entry["direction"] = m_ch.group("dir")
            entry["data_index"] = int(m_ch.group("slot"))
            entry["bit"] = int(m_ch.group("bit"))
        by_endpoint[endpoint] = entry
        by_device[name].append(endpoint)
        mappings.append(entry)
    return {
        "kind": "physical_io_map_csv",
        "path": str(path),
        "tag_datatypes": {},
        "mappings": mappings,
        "by_endpoint": by_endpoint,
        "by_device": dict(by_device),
    }


def udt_family(datatype: str, device: str = "", member: str = "") -> str:
    dt = _clean(datatype)
    if dt:
        return dt
    # Weak family hint from member when SF CSV lacks datatype.
    mem = _norm(member)
    dev = _norm(device)
    if "ES_OK" in mem or dev.startswith("ES") or "MCR" in dev or "ESR" in dev:
        return "ES_UDT?"
    if "PE_CLEAR" in mem or "PE_" in mem or re.match(r"^(?:EZ)?PE\d", dev):
        return "PE_UDT?"
    if "AUXILIARY_FORWARD" in mem or dev.endswith("_MS"):
        return "Motor_Starter_UDT?"
    if mem.endswith("PS_OK") or re.match(r"^(?:EZ)?PWS", dev):
        return "PS_UDT?"
    if "PRESSURE_OK" in mem:
        return "AirPressure_Switch_UDT?"
    if ".O.RUN" in f".{mem}" or dev.endswith("_CONV"):
        return "Conv_UDT?"
    return "UNKNOWN"


def classify_pair(
    oracle_row: dict[str, Any],
    sf_row: dict[str, Any] | None,
    sf_by_device: dict[str, list[str]],
) -> str:
    o_dev, o_mem = _norm(oracle_row.get("device") or ""), _norm(oracle_row.get("member") or "")
    o_dt = _norm(oracle_row.get("datatype") or "")
    o_ep = _clean(oracle_row.get("endpoint") or "")

    if sf_row is None:
        # Same logical device present on a different SF endpoint?
        eps = sf_by_device.get(oracle_row.get("device") or "") or []
        if eps and o_ep not in eps:
            return "SITE_FORGE_WRONG_ENDPOINT"
        return "ORACLE_ADDS_INFO"

    s_dev = _norm(sf_row.get("device") or "")
    s_mem = _norm(sf_row.get("member") or "")
    s_dt = _norm(sf_row.get("datatype") or "")
    s_tag = _norm(sf_row.get("logical_tag") or "")
    o_tag = _norm(oracle_row.get("logical_tag") or "")

    if o_tag and s_tag and o_tag == s_tag:
        # Exact logical path match; UDT mismatch still notable.
        if o_dt and s_dt and o_dt != s_dt:
            return "SITE_FORGE_WRONG_UDT"
        return "MATCH"

    if o_dev and s_dev and o_dev == s_dev:
        if o_dt and s_dt and o_dt != s_dt:
            return "SITE_FORGE_WRONG_UDT"
        if o_mem != s_mem:
            return "SITE_FORGE_WRONG_MEMBER"
        if o_dt and not s_dt:
            # CSV fallback often lacks datatype/member.
            return "SITE_FORGE_WRONG_MEMBER" if o_mem else "REVIEW_REQUIRED"
        return "REVIEW_REQUIRED"

    if o_dev and s_dev and o_dev != s_dev:
        return "SITE_FORGE_WRONG_DEVICE"

    return "REVIEW_REQUIRED"


def compare_oracle_to_site_forge(
    oracle: dict[str, Any],
    site_forge: dict[str, Any],
) -> dict[str, Any]:
    sf_by_ep: dict[str, dict[str, Any]] = site_forge.get("by_endpoint") or {}
    sf_by_device: dict[str, list[str]] = site_forge.get("by_device") or {}
    # Also index SF devices case-insensitively.
    sf_by_device_u = {_norm(k): v for k, v in sf_by_device.items()}

    rows: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    by_udt_family: dict[str, Counter[str]] = defaultdict(Counter)

    for o in oracle.get("mappings") or []:
        if o.get("placeholder") or not o.get("logical_tag"):
            continue
        ep = o["endpoint"]
        sf = sf_by_ep.get(ep)
        # Device-level wrong-endpoint uses exact device key first.
        device_index = dict(sf_by_device)
        if o.get("device") and _norm(o["device"]) in sf_by_device_u:
            device_index[o["device"]] = sf_by_device_u[_norm(o["device"])]
        cls = classify_pair(o, sf, device_index)
        fam = udt_family(o.get("datatype") or "", o.get("device") or "", o.get("member") or "")
        class_counts[cls] += 1
        by_udt_family[fam][cls] += 1
        rows.append(
            {
                "classification": cls,
                "endpoint": ep,
                "routine": o.get("routine"),
                "oracle": {
                    "logical_tag": o.get("logical_tag"),
                    "device": o.get("device"),
                    "member": o.get("member"),
                    "datatype": o.get("datatype"),
                },
                "site_forge": None
                if sf is None
                else {
                    "logical_tag": sf.get("logical_tag"),
                    "device": sf.get("device"),
                    "member": sf.get("member"),
                    "datatype": sf.get("datatype"),
                    "source": sf.get("source") or site_forge.get("path"),
                },
                "udt_family": fam,
            }
        )

    # SF-only endpoints (not in oracle) → review bag, not oracle-driven classes.
    oracle_eps = {r["endpoint"] for r in rows}
    sf_only = []
    for ep, sf in sf_by_ep.items():
        if ep in oracle_eps:
            continue
        if sf.get("placeholder"):
            continue
        sf_only.append(
            {
                "endpoint": ep,
                "logical_tag": sf.get("logical_tag"),
                "device": sf.get("device"),
                "member": sf.get("member"),
                "datatype": sf.get("datatype"),
            }
        )

    return {
        "counts_by_class": {k: class_counts.get(k, 0) for k in CLASSIFICATIONS},
        "counts_by_udt_family": {
            fam: dict(counter) for fam, counter in sorted(by_udt_family.items())
        },
        "compared": len(rows),
        "site_forge_only_endpoints": len(sf_only),
        "rows": rows,
        "site_forge_only_sample": sf_only[:40],
    }


def _sample_families(oracle: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Collect representative ES406 / PE / MS / PS / Conv oracle mappings."""
    want = {
        "ES406": [],
        "PE": [],
        "MS": [],
        "PS": [],
        "Conv": [],
    }
    for r in oracle.get("mappings") or []:
        if r.get("placeholder"):
            continue
        tag = r.get("logical_tag") or ""
        dev = r.get("device") or ""
        dt = r.get("datatype") or ""
        item = {
            "endpoint": r["endpoint"],
            "logical_tag": tag,
            "datatype": dt,
            "routine": r.get("routine"),
        }
        if "ES406" in tag or dev == "ES406":
            want["ES406"].append(item)
        if dt == "PE_UDT" or re.match(r"^(?:EZ)?PE\d", dev, re.I):
            if len(want["PE"]) < 12:
                want["PE"].append(item)
        if dt == "Motor_Starter_UDT" or re.search(r"_MS$", dev, re.I):
            if len(want["MS"]) < 12:
                want["MS"].append(item)
        if dt in {"PS_UDT", "AirPressure_Switch_UDT"} or re.match(
            r"^(?:EZ)?PWS|^PS\d", dev, re.I
        ):
            if len(want["PS"]) < 12:
                want["PS"].append(item)
        if dt == "Conv_UDT" or re.search(r"_Conv$", dev, re.I):
            if len(want["Conv"]) < 12:
                want["Conv"].append(item)
    return want


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Greensboro PLC2 IO Oracle Compare")
    lines.append("")
    lines.append(f"- Generated: `{report.get('generated_at')}`")
    lines.append(f"- Oracle: `{report.get('oracle_path')}`")
    lines.append(f"- RUN: `{report.get('run_path') or '(not found)'}`")
    sf = report.get("site_forge") or {}
    lines.append(f"- Site Forge source ({sf.get('kind')}): `{sf.get('path') or '(none)'}`")
    if report.get("physical_io_map_path"):
        lines.append(f"- physical_io_map: `{report['physical_io_map_path']}`")
    lines.append("")
    lines.append("## Counts by class")
    lines.append("")
    lines.append("| Class | Count |")
    lines.append("|---|---:|")
    for k in CLASSIFICATIONS:
        lines.append(f"| `{k}` | {(report.get('counts_by_class') or {}).get(k, 0)} |")
    lines.append("")
    lines.append(f"Compared oracle mappings: **{report.get('compared', 0)}**")
    lines.append(
        f"Site Forge-only endpoints (not in oracle): **{report.get('site_forge_only_endpoints', 0)}**"
    )
    lines.append("")
    lines.append("## Counts by UDT family")
    lines.append("")
    lines.append("| UDT family | Class breakdown |")
    lines.append("|---|---|")
    for fam, breakdown in (report.get("counts_by_udt_family") or {}).items():
        parts = ", ".join(f"{c}={n}" for c, n in sorted(breakdown.items()) if n)
        lines.append(f"| `{fam}` | {parts} |")
    lines.append("")
    lines.append("## Sample oracle mappings")
    lines.append("")
    samples = report.get("oracle_samples") or {}
    for fam, items in samples.items():
        lines.append(f"### {fam}")
        if not items:
            lines.append("_none_")
            lines.append("")
            continue
        for it in items[:8]:
            lines.append(
                f"- `{it.get('endpoint')}` → `{it.get('logical_tag')}`"
                f" ({it.get('datatype') or 'UNKNOWN'}) [{it.get('routine')}]"
            )
        lines.append("")
    lines.append("## Mismatch samples")
    lines.append("")
    mismatches = [
        r
        for r in report.get("rows") or []
        if r.get("classification") not in {"MATCH"}
    ]
    for r in mismatches[:40]:
        o = r.get("oracle") or {}
        s = r.get("site_forge") or {}
        lines.append(
            f"- **{r.get('classification')}** `{r.get('endpoint')}`: "
            f"oracle `{o.get('logical_tag')}` ({o.get('datatype')}) vs "
            f"SF `{s.get('logical_tag') if s else '—'}`"
            f" ({(s or {}).get('datatype') or '—'})"
        )
    lines.append("")
    lines.append(
        "_Diagnostics only. Finished L5X is validation authority; "
        "do not feed into fortna_autogen / equipment_binding._"
    )
    lines.append("")
    return "\n".join(lines)


def run_compare(
    *,
    oracle_path: Path,
    site_forge_l5x: Path | None = None,
    physical_io_map: Path | None = None,
    run_path: Path | None = None,
    prefer_binder: bool = True,
) -> dict[str, Any]:
    oracle = build_oracle_io_map(oracle_path)

    sf_bundle: dict[str, Any] | None = None
    l5x = site_forge_l5x or discover_site_forge_l5x()
    phys = physical_io_map or discover_physical_io_map()
    run = run_path if run_path is not None else discover_ornccp2_run()

    # Prefer live equipment_binding join when RUN is available (this task's binder).
    if prefer_binder and run and (Path(run) / "FORTNA" / "Conveyor.asc").is_file():
        try:
            sf_bundle = load_site_forge_from_equipment_binding(Path(run), phys)
        except Exception as exc:  # noqa: BLE001 — diagnostics fallback
            sf_bundle = None
            binder_error = str(exc)
        else:
            binder_error = None
    else:
        binder_error = None

    if sf_bundle is None and l5x and l5x.is_file():
        sf_bundle = load_site_forge_from_l5x(l5x)
    elif sf_bundle is None and phys and phys.is_file():
        sf_bundle = load_site_forge_from_physical_csv(phys)
    elif sf_bundle is None:
        sf_bundle = {
            "kind": "missing",
            "path": "",
            "tag_datatypes": {},
            "mappings": [],
            "by_endpoint": {},
            "by_device": {},
        }

    cmp = compare_oracle_to_site_forge(oracle, sf_bundle)
    report = {
        "generated_at": _ts(),
        "diagnostics_only": True,
        "oracle_path": str(oracle_path),
        "run_path": str(run) if run else None,
        "run_available": bool(run),
        "site_forge": {
            "kind": sf_bundle.get("kind"),
            "path": sf_bundle.get("path"),
            "mapping_count": len(sf_bundle.get("by_endpoint") or {}),
            "binding_counts": sf_bundle.get("binding_counts"),
            "binding_matrix": sf_bundle.get("binding_matrix"),
            "binder_error": binder_error,
        },
        "physical_io_map_path": str(phys) if phys and phys.is_file() else None,
        "oracle_mapping_count": oracle.get("mapped_count"),
        "oracle_udt_family_counts": oracle.get("udt_family_counts"),
        "oracle_samples": _sample_families(oracle),
        **cmp,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--oracle", type=Path, default=DEFAULT_ORACLE)
    ap.add_argument("--site-forge-l5x", type=Path, default=None)
    ap.add_argument("--physical-io-map", type=Path, default=None)
    ap.add_argument("--run", type=Path, default=None)
    ap.add_argument(
        "--prefer-l5x",
        action="store_true",
        help="Compare against generated Site Forge L5X instead of live equipment_binding",
    )
    ap.add_argument("--json-out", type=Path, default=OUT_JSON)
    ap.add_argument("--md-out", type=Path, default=OUT_MD)
    args = ap.parse_args(argv)

    if not args.oracle.is_file():
        print(f"MISSING oracle: {args.oracle}", file=sys.stderr)
        return 2

    report = run_compare(
        oracle_path=args.oracle,
        site_forge_l5x=args.site_forge_l5x,
        physical_io_map=args.physical_io_map,
        run_path=args.run,
        prefer_binder=not bool(args.prefer_l5x),
    )

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.md_out.write_text(render_markdown(report), encoding="utf-8")

    print(
        json.dumps(
            {
                "json_out": str(args.json_out),
                "md_out": str(args.md_out),
                "run_available": report.get("run_available"),
                "site_forge": report.get("site_forge"),
                "counts_by_class": report.get("counts_by_class"),
                "compared": report.get("compared"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
