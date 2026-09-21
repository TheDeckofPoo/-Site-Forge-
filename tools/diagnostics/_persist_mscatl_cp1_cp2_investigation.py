#!/usr/bin/env python3
"""Persist MSCATL_CP1 + CP2 investigation into PostgreSQL and cluster unresolved families.

Writes:
  - corpus/evidence rows via warehouse extract+ingest (Configio, EIPModules, eipcfg, claims)
  - learning.investigation_sessions with resolved/unresolved, occupancy, failure reasons
  - learning.unknown_clusters + dialect_observations for structural unresolved families
  - exports/diagnostics/mscatl_cp1_cp2_investigation_persist.{json,md}
  - exports/diagnostics/mscatl_unresolved_family_clusters.{json,md}

Does NOT invent endpoints. Does NOT call AI (caller decides after cluster review).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "scripts"))

from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_evidence_purity import INDEPENDENT_DERIVATION, RAW_RUN_EVIDENCE  # noqa: E402
from fortna_hardware_io_model import build_hardware_io_model  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    _load_eipmodules_rows,
    parse_eipcfg,
)
from siteforge_warehouse.extract import build_bundle_from_run_dir  # noqa: E402
from siteforge_warehouse.ids import normalize_archive_sha256  # noqa: E402
from siteforge_warehouse.models import (  # noqa: E402
    DialectObservation,
    InvestigationSession,
    UnknownCluster,
)
from siteforge_warehouse.postgres_repository import make_engine  # noqa: E402
from siteforge_warehouse.writer import PostgresWarehouseWriter  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

INBOX = {
    "MSCATL_CP1": REPO
    / "workspace/inbox/20260813-1428-MSCATL-MSCATL_CP1-RUN.tar.gz",
    "MSCATL_CP2": REPO
    / "workspace/inbox/20260813-1428-MSCATL-MSCATL_CP2-RUN.tar.gz",
}
PEEKS = {
    "MSCATL_CP1": REPO / "workspace/_mscatl_peek/MSCATL_CP1/RUN",
    "MSCATL_CP2": REPO / "workspace/_mscatl_peek/MSCATL_CP2/RUN",
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _pattern_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


_DESC_FAMILY_RE = re.compile(
    r"^(?P<fam>[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)-(?P<idx>\d+)$"
)


def structural_signature(unresolved_row: dict[str, Any]) -> dict[str, Any]:
    """Structural signature for unresolved Configio words — no site names."""
    low = str(unresolved_row.get("low_desc") or "").strip()
    high = str(unresolved_row.get("high_desc") or "").strip()
    reason = str(unresolved_row.get("reason") or "").strip()
    direction = str(unresolved_row.get("direction") or "").strip()

    def fam(desc: str) -> str:
        if not desc:
            return ""
        m = _DESC_FAMILY_RE.match(desc)
        if m:
            return m.group("fam").upper()
        # strip trailing digits/hyphen index
        return re.sub(r"-\d+$", "", desc).upper() or desc.upper()

    low_f, high_f = fam(low), fam(high)
    family = low_f or high_f or "UNKNOWN"
    # Hardware class buckets
    if "POWERFLEX" in family or family.startswith("PF"):
        hw_class = "ETHERNET_DRIVE"
    elif "IB32" in family or "OB32" in family or "IA32" in family or "OA32" in family:
        hw_class = "POINT_OR_BLOCK_32"
    elif re.match(r"^\d{4}-", family):
        hw_class = "ROCKWELL_CATALOG"
    elif family.startswith("IB") or family.startswith("OB") or family.startswith("IA"):
        hw_class = "NAMED_IO_BLOCK"
    else:
        hw_class = "OTHER"

    sig = {
        "reason": reason or "unknown",
        "desc_family": family,
        "hw_class": hw_class,
        "has_high_desc": bool(high),
        "low_high_same_family": bool(low_f and high_f and low_f == high_f),
        "direction": direction or "UNKNOWN",
    }
    sig_key = "|".join(
        [
            sig["reason"],
            sig["hw_class"],
            sig["desc_family"],
            "H" if sig["has_high_desc"] else "L",
            "SAME" if sig["low_high_same_family"] else "DIFF",
            sig["direction"],
        ]
    )
    sig["signature"] = sig_key
    sig["pattern_hash"] = _pattern_hash(sig_key)
    return sig


def capture_machine(machine: str, run: Path, archive_sha: str) -> dict[str, Any]:
    ev = build_evidence_bundle(run, machine, project="MSCATL")
    raw = ev.get("raw_claims") or []
    disp = Counter(c.get("deterministic_disposition") for c in raw)
    ur = (ev.get("deterministic_resolver") or {}).get("unresolved_words") or []
    pwr = PhysicalWordResolver(run, machine)
    words = (pwr.physical_map or {}).get("words") or {}
    eipm = _load_eipmodules_rows(run, machine)
    topo = parse_eipcfg(run, machine)
    hw = build_hardware_io_model(run, machine)

    occupancy = []
    for ad in hw.get("adapters") or []:
        for mod in ad.get("modules") or []:
            chs = mod.get("channels") or []
            claimed = sum(
                1
                for c in chs
                if (c.get("logical_endpoint") or {}).get("name")
                or str(c.get("owner_state") or "").upper() == "ASSIGNED"
            )
            occupancy.append(
                {
                    "rio": ad.get("rio_name"),
                    "slot": mod.get("slot"),
                    "catalog": mod.get("catalog") or mod.get("type"),
                    "capacity": mod.get("channel_capacity"),
                    "channels": len(chs),
                    "claimed": claimed,
                    "occupancy_ratio": (
                        f"{claimed}/{mod.get('channel_capacity') or len(chs) or 0}"
                    ),
                }
            )

    unresolved_enriched = []
    for u in ur:
        row = dict(u)
        row.update(structural_signature(u))
        unresolved_enriched.append(row)

    fam_counts = Counter(u.get("desc_family") for u in unresolved_enriched)
    reason_counts = Counter(u.get("reason") for u in unresolved_enriched)
    sig_counts = Counter(u.get("signature") for u in unresolved_enriched)

    return {
        "machine": machine,
        "archive_sha256": archive_sha,
        "run_dir": str(run),
        "eipcfg_path": str((ev.get("eipcfg") or {}).get("path") or ""),
        "eipmodules_path": str((ev.get("eipmodules") or {}).get("path") or ""),
        "eipmodules_rows": len(eipm),
        "eipmodules_nonzero_banks": sum(
            1
            for r in eipm
            if int(r.get("input_bank") or 0) or int(r.get("output_bank") or 0)
        ),
        "eipcfg_adapters": len((topo.get("adapters") or [])),
        "configio_rows": len(ev.get("configio") or []),
        "raw_physical_claims": len(raw),
        "dispositions": dict(disp),
        "assigned": int(disp.get("ASSIGNED") or 0),
        "unresolved_claim_count": int(disp.get("physical_resolution_failure") or 0),
        "resolved_words": len(words),
        "unresolved_words": unresolved_enriched,
        "unresolved_reason_counts": dict(reason_counts),
        "unresolved_family_counts": dict(fam_counts),
        "unresolved_signature_counts": dict(sig_counts),
        "per_module_occupancy": occupancy,
        "claim_discovery_status": hw.get("claim_discovery_status"),
        "discovery_warning": hw.get("discovery_warning"),
        "evidence_status": ev.get("evidence_status"),
        "discovery_status": ev.get("discovery_status"),
        "conservation": ev.get("conservation"),
        "stage0": ev.get("stage0"),
    }


def ingest_raw(machine: str, run: Path, tar: Path, sha: str) -> dict[str, Any]:
    bundle = build_bundle_from_run_dir(
        run,
        archive_sha256=sha,
        filename=tar.name,
        discovered_path=str(tar.resolve()),
    )
    # Force machine/project identity for Atlanta peeks
    bundle.machine = machine
    bundle.project = bundle.project or "MSCATL"
    if bundle.archive:
        bundle.archive.machine = machine
        bundle.archive.project = bundle.project
        bundle.archive.site = "MSCATL"
        bundle.archive.filename = tar.name
        bundle.archive.discovered_path = str(tar.resolve())
        bundle.archive.size_bytes = tar.stat().st_size
        bundle.archive.archive_class = "RUN"
    writer = PostgresWarehouseWriter()
    writer.ensure_extractor_version()
    result = writer.ingest_bundle(bundle, force=True)
    counts = bundle.staging_counts() if hasattr(bundle, "staging_counts") else {}
    return {
        "ingest": result,
        "staging_counts": counts,
        "configio": int(counts.get("configio_rows") or len(bundle.configio_rows or [])),
        "eipmodules": int(counts.get("eipmodules") or len(bundle.eipmodules or [])),
        "eipcfg_modules": int(counts.get("eipcfg_modules") or 0),
        "io_claims": int(counts.get("io_claims") or len(bundle.io_claims or [])),
    }


def persist_investigation(captures: dict[str, dict[str, Any]]) -> str:
    eng = make_engine()
    assert eng is not None
    Session = sessionmaker(bind=eng, future=True)
    inv_id = "MSCATL_CP1_CP2_IO_PIPELINE_" + datetime.now(timezone.utc).strftime(
        "%Y%m%d"
    )
    with Session() as session:
        with session.begin():
            existing = session.get(InvestigationSession, inv_id)
            machines_meta: dict[str, Any] = {}
            for m, cap in captures.items():
                slim = {
                    k: v
                    for k, v in cap.items()
                    if k != "unresolved_words"
                }
                slim["unresolved_words_sample"] = (cap.get("unresolved_words") or [])[
                    :20
                ]
                slim["unresolved_words_count"] = len(cap.get("unresolved_words") or [])
                machines_meta[m] = slim
            meta = {
                "evidence_class": RAW_RUN_EVIDENCE,
                "git_commit_hint": "ba2a8ee+",
                "machines": machines_meta,
                "artifacts": [
                    "exports/diagnostics/mscatl_cp1_cp2_investigation_persist.json",
                    "exports/diagnostics/mscatl_unresolved_family_clusters.json",
                ],
            }
            fields = {
                "investigation_id": inv_id,
                "title": "MSCATL CP1+CP2 I/O pipeline investigation (persist+cluster)",
                "status": "CAPTURED",
                "started_at": datetime.now(timezone.utc),
                "meta": meta,
            }
            if existing:
                for k, v in fields.items():
                    if k != "investigation_id":
                        setattr(existing, k, v)
            else:
                session.add(InvestigationSession(**fields))
    return inv_id


def cluster_against_db(cp1_sigs: dict[str, int]) -> dict[str, Any]:
    """Compare CP1 unresolved signatures to Configio Desc families across DB."""
    eng = make_engine()
    assert eng is not None
    from sqlalchemy import text

    # Pull Configio descs from all machines for family co-occurrence
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT machine, project, archive_sha256, "desc", interface, bank, octal_word
                FROM evidence.configio_rows
                WHERE "desc" IS NOT NULL AND btrim("desc") <> ''
                  AND upper("desc") NOT IN ('N/A','')
                  AND "desc" NOT ILIKE 'Mem%'
                """
            )
        ).fetchall()

    # Also use local peeks for CP1/CP2 unresolved (authoritative for failure reasons)
    by_sig: dict[str, dict[str, Any]] = {}

    def touch(sig: dict[str, Any], machine: str, archive: str, example: dict) -> None:
        key = sig["pattern_hash"]
        cell = by_sig.setdefault(
            key,
            {
                "cluster_id": f"uc_{key}",
                "pattern_hash": key,
                "structural_pattern": sig["signature"],
                "fields": {
                    "reason": sig.get("reason"),
                    "hw_class": sig.get("hw_class"),
                    "desc_family": sig.get("desc_family"),
                    "direction": sig.get("direction"),
                },
                "count": 0,
                "machines": [],
                "archives": [],
                "example_raw": [],
                "cp1_hit": False,
                "in_cp1_unresolved": False,
            },
        )
        cell["count"] += 1
        if machine and machine not in cell["machines"]:
            cell["machines"].append(machine)
        if archive and archive not in cell["archives"]:
            cell["archives"].append(archive)
        if len(cell["example_raw"]) < 8:
            cell["example_raw"].append(example)

    # Mark CP1 unresolved signatures first
    cp1_hashes = set()
    for sig_key, n in cp1_sigs.items():
        sig = {
            "signature": sig_key,
            "pattern_hash": _pattern_hash(sig_key),
            "reason": sig_key.split("|")[0] if "|" in sig_key else "",
            "hw_class": sig_key.split("|")[1] if "|" in sig_key else "",
            "desc_family": sig_key.split("|")[2] if "|" in sig_key else "",
            "direction": sig_key.split("|")[-1] if "|" in sig_key else "",
        }
        cp1_hashes.add(sig["pattern_hash"])
        touch(
            sig,
            "MSCATL_CP1",
            "",
            {"source": "cp1_unresolved", "signature": sig_key, "count": n},
        )
        by_sig[sig["pattern_hash"]]["cp1_hit"] = True
        by_sig[sig["pattern_hash"]]["in_cp1_unresolved"] = True
        by_sig[sig["pattern_hash"]]["count"] = max(
            by_sig[sig["pattern_hash"]]["count"], int(n)
        )

    # Scan all Configio rows for matching desc families (co-occurrence across corpus)
    for r in rows:
        desc = str(r.desc or "").strip()
        m = _DESC_FAMILY_RE.match(desc)
        fam = (m.group("fam").upper() if m else re.sub(r"-\d+$", "", desc).upper())
        # Build candidate signatures that CP1 uses: reason may differ per site;
        # cluster primarily on hw_class + desc_family
        if "POWERFLEX" in fam:
            hw = "ETHERNET_DRIVE"
        elif any(x in fam for x in ("IB32", "OB32", "IA32", "OA32")):
            hw = "POINT_OR_BLOCK_32"
        elif re.match(r"^\d{4}-", fam):
            hw = "ROCKWELL_CATALOG"
        elif fam.startswith(("IB", "OB", "IA", "OA")):
            hw = "NAMED_IO_BLOCK"
        else:
            hw = "OTHER"
        # Family-level signature (reason-agnostic) for cross-site recurrence
        fam_sig_key = f"FAMILY|{hw}|{fam}"
        sig = {
            "signature": fam_sig_key,
            "pattern_hash": _pattern_hash(fam_sig_key),
            "reason": "FAMILY_COOCCURRENCE",
            "hw_class": hw,
            "desc_family": fam,
            "direction": "UNKNOWN",
        }
        touch(
            sig,
            str(r.machine or ""),
            str(r.archive_sha256 or ""),
            {
                "desc": desc,
                "machine": r.machine,
                "project": r.project,
                "octal_word": r.octal_word,
                "bank": r.bank,
            },
        )

    clusters = list(by_sig.values())
    # Recurring = appears on >=2 machines OR (CP1 unresolved family seen elsewhere)
    recurring = []
    for c in clusters:
        machines = [m for m in (c.get("machines") or []) if m]
        if c.get("in_cp1_unresolved") and len(machines) >= 2:
            c["recurring"] = True
            recurring.append(c)
        elif c.get("fields", {}).get("reason") == "FAMILY_COOCCURRENCE" and len(
            set(machines)
        ) >= 3:
            # only keep families that also appear in CP1 unresolved
            fam = c.get("fields", {}).get("desc_family")
            if any(
                fam
                and fam
                == by_sig[h].get("fields", {}).get("desc_family")
                and by_sig[h].get("in_cp1_unresolved")
                for h in cp1_hashes
            ):
                c["recurring"] = True
                recurring.append(c)
        else:
            c["recurring"] = False

    return {
        "clusters": sorted(clusters, key=lambda x: (-int(x.get("count") or 0), x["cluster_id"])),
        "recurring": recurring,
        "cp1_signature_hashes": sorted(cp1_hashes),
        "configio_rows_scanned": len(rows),
    }


def write_clusters_to_db(cluster_report: dict[str, Any]) -> int:
    eng = make_engine()
    assert eng is not None
    Session = sessionmaker(bind=eng, future=True)
    n = 0
    with Session() as session:
        with session.begin():
            for c in cluster_report.get("clusters") or []:
                if not (
                    c.get("in_cp1_unresolved")
                    or c.get("recurring")
                    or str(c.get("fields", {}).get("reason") or "").startswith(
                        "no_eipmodules"
                    )
                ):
                    # Persist CP1-related + recurring family co-occurrence only
                    if not c.get("in_cp1_unresolved") and not c.get("recurring"):
                        continue
                cid = c["cluster_id"]
                existing = session.get(UnknownCluster, cid)
                fields = {
                    "cluster_id": cid,
                    "pattern_hash": c.get("pattern_hash") or "",
                    "structural_pattern": c.get("structural_pattern") or "",
                    "count": int(c.get("count") or 0),
                    "example_raw": c.get("example_raw") or [],
                    "archives": c.get("archives") or [],
                    "machines": c.get("machines") or [],
                    "fields": {
                        **(c.get("fields") or {}),
                        "recurring": bool(c.get("recurring")),
                        "in_cp1_unresolved": bool(c.get("in_cp1_unresolved")),
                        "cp1_hit": bool(c.get("cp1_hit")),
                    },
                    "extractor_version": "warehouse_hw_io_v1.0.0",
                }
                if existing:
                    for k, v in fields.items():
                        if k != "cluster_id":
                            setattr(existing, k, v)
                else:
                    session.add(UnknownCluster(**fields))
                n += 1

            # Dialect observations for CP1 unresolved families
            for c in cluster_report.get("clusters") or []:
                if not c.get("in_cp1_unresolved"):
                    continue
                fam = (c.get("fields") or {}).get("desc_family") or "UNKNOWN"
                form = f"UNRESOLVED_{((c.get('fields') or {}).get('hw_class') or 'OTHER')}"
                # one observation row per form+machine+archive empty
                session.add(
                    DialectObservation(
                        form=form[:64],
                        structural_pattern_hash=c.get("pattern_hash") or "",
                        archive_sha256="",
                        machine="MSCATL_CP1",
                        count=int(c.get("count") or 1),
                        example_raw=json.dumps((c.get("example_raw") or [])[:3])[:2000],
                        evidence_class=INDEPENDENT_DERIVATION,
                        extractor_version="warehouse_hw_io_v1.0.0",
                        meta={
                            "desc_family": fam,
                            "signature": c.get("structural_pattern"),
                            "investigation": "MSCATL_CP1_CP2_IO_PIPELINE",
                        },
                    )
                )
    return n


def main() -> int:
    out_dir = REPO / "exports" / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)

    shas = {m: _sha256_file(p) for m, p in INBOX.items()}
    print("SHAs", shas)

    ingest_results = {}
    captures = {}
    for machine in ("MSCATL_CP1", "MSCATL_CP2"):
        run = PEEKS[machine]
        tar = INBOX[machine]
        sha = normalize_archive_sha256(shas[machine])
        print(f"== ingest {machine}")
        ingest_results[machine] = ingest_raw(machine, run, tar, sha)
        print("  ingest", ingest_results[machine].get("ingest"))
        print(f"== capture {machine}")
        captures[machine] = capture_machine(machine, run, sha)
        print(
            "  assigned",
            captures[machine]["assigned"],
            "unresolved",
            captures[machine]["unresolved_claim_count"],
            "families",
            captures[machine]["unresolved_family_counts"],
        )

    inv_id = persist_investigation(captures)
    print("investigation_session", inv_id)

    cp1_sigs = captures["MSCATL_CP1"].get("unresolved_signature_counts") or {}
    cluster_report = cluster_against_db(cp1_sigs)
    written = write_clusters_to_db(cluster_report)
    print(
        "clusters",
        len(cluster_report["clusters"]),
        "recurring",
        len(cluster_report["recurring"]),
        "written",
        written,
    )

    payload = {
        "title": "MSCATL CP1+CP2 investigation persist + unresolved family clusters",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "investigation_id": inv_id,
        "archive_shas": shas,
        "ingest": ingest_results,
        "captures": captures,
        "clusters": {
            "configio_rows_scanned": cluster_report["configio_rows_scanned"],
            "cluster_count": len(cluster_report["clusters"]),
            "recurring_count": len(cluster_report["recurring"]),
            "recurring": cluster_report["recurring"],
            "cp1_signatures": cp1_sigs,
        },
        "ai_gate": {
            "ai_allowed": len(cluster_report["recurring"]) > 0,
            "reason": (
                "Recurring structural families found across >=2 machines — "
                "one generalized AI investigation permitted on the cluster, "
                "not per endpoint."
                if cluster_report["recurring"]
                else "No multi-machine recurring unresolved family — AI not warranted."
            ),
            "budget_usd_target": 1.0,
        },
    }
    # Trim huge nested lists for secondary MD; full JSON keeps samples
    (out_dir / "mscatl_cp1_cp2_investigation_persist.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "mscatl_unresolved_family_clusters.json").write_text(
        json.dumps(
            {
                "cp1_signatures": cp1_sigs,
                "recurring": cluster_report["recurring"],
                "clusters_related_to_cp1": [
                    c
                    for c in cluster_report["clusters"]
                    if c.get("in_cp1_unresolved") or c.get("recurring")
                ],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    lines = [
        "# MSCATL CP1+CP2 investigation persist",
        "",
        f"**Investigation ID:** `{inv_id}`",
        "",
        "## Ingest",
        "",
    ]
    for m, r in ingest_results.items():
        lines += [
            f"### {m}",
            f"- archive SHA: `{shas[m]}`",
            f"- ingest status: `{r.get('ingest', {}).get('status')}`",
            f"- configio/eipmodules/io_claims staged: "
            f"{r.get('configio')}/{r.get('eipmodules')}/{r.get('io_claims')}",
            "",
        ]
    lines += ["## Capture summary", ""]
    for m, c in captures.items():
        lines += [
            f"### {m}",
            f"- raw physical claims: **{c['raw_physical_claims']}**",
            f"- ASSIGNED: **{c['assigned']}**",
            f"- unresolved claims: **{c['unresolved_claim_count']}**",
            f"- EIPModules nonzero banks: **{c['eipmodules_nonzero_banks']}/{c['eipmodules_rows']}**",
            f"- discovery: `{c.get('claim_discovery_status')}` / evidence `{c.get('evidence_status')}`",
            f"- unresolved families: `{c.get('unresolved_family_counts')}`",
            f"- unresolved reasons: `{c.get('unresolved_reason_counts')}`",
            "",
        ]
    lines += [
        "## Unresolved family clusters (CP1-centric)",
        "",
        f"- Configio rows scanned: **{cluster_report['configio_rows_scanned']}**",
        f"- Recurring clusters: **{len(cluster_report['recurring'])}**",
        "",
    ]
    for c in cluster_report["recurring"][:20]:
        lines.append(
            f"- `{c.get('structural_pattern')}` machines={c.get('machines')} "
            f"count={c.get('count')} fam={(c.get('fields') or {}).get('desc_family')}"
        )
    lines += [
        "",
        "## AI gate",
        "",
        f"- AI allowed: **{payload['ai_gate']['ai_allowed']}**",
        f"- {payload['ai_gate']['reason']}",
        "",
    ]
    (out_dir / "mscatl_cp1_cp2_investigation_persist.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    (out_dir / "mscatl_unresolved_family_clusters.md").write_text(
        "\n".join(
            [
                "# MSCATL unresolved family clusters",
                "",
                "## CP1 unresolved signatures",
                "",
                *[f"- `{k}` × {v}" for k, v in sorted(cp1_sigs.items(), key=lambda x: -x[1])],
                "",
                "## Recurring across corpus",
                "",
                *(
                    [
                        f"- `{c.get('structural_pattern')}` · machines={c.get('machines')} · n={c.get('count')}"
                        for c in cluster_report["recurring"]
                    ]
                    or ["- _(none)_"]
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )
    print("wrote diagnostics")
    print(json.dumps(payload["ai_gate"], indent=2))
    print(
        json.dumps(
            {
                m: {
                    "assigned": captures[m]["assigned"],
                    "unresolved": captures[m]["unresolved_claim_count"],
                    "families": captures[m]["unresolved_family_counts"],
                }
                for m in captures
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
