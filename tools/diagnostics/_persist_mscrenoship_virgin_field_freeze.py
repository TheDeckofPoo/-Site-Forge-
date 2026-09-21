#!/usr/bin/env python3
"""Persist MSCRENOSHIP virgin field-test freeze (pre-behavior-change baseline)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "scripts"))

from fortna_safety_model import discover_safety_devices  # noqa: E402
from siteforge_warehouse.extract import build_bundle_from_run_dir  # noqa: E402
from siteforge_warehouse.ids import normalize_archive_sha256  # noqa: E402
from siteforge_warehouse.learning_loop import (  # noqa: E402
    capture_pipeline,
    persist_field_test_and_failures,
)
from siteforge_warehouse.writer import PostgresWarehouseWriter  # noqa: E402

MACHINE = "MSCRENOSHIP"
PROJECT = "MSCRENO"
GIT_SHA = "bdcc770"
RUN = REPO / "workspace/_reno_peek/20260813-1132-MSCRENO-MSCRENOSHIP-RUN/RUN"
TAR = REPO / "workspace/inbox/20260813-1132-MSCRENO-MSCRENOSHIP-RUN.tar.gz"
MANIFEST = REPO / "exports/current/MSCRENOSHIP_2026_09_21_0108.manifest.json"
L5X = REPO / "exports/current/MSCRENOSHIP_2026_09_21_0108.L5X"
BUILD = REPO / "workspace/.internal/builds/20260921-010813"
OUT = REPO / "exports/diagnostics"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    assert (RUN / "project.cfg").is_file(), RUN
    assert TAR.is_file(), TAR
    assert MANIFEST.is_file(), MANIFEST
    OUT.mkdir(parents=True, exist_ok=True)

    archive_sha = normalize_archive_sha256(sha256_file(TAR))
    print("archive_sha", archive_sha)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report = json.loads((BUILD / "autogen_report.json").read_text(encoding="utf-8"))
    equip = json.loads((BUILD / "equipment_plan.json").read_text(encoding="utf-8"))
    es = manifest.get("es_program") or {}
    stage0 = report.get("stage0") or {}

    safety_devs = discover_safety_devices(RUN, MACHINE)
    safety_count = len(safety_devs)
    members: list[str] = []
    for z in es.get("zones") or []:
        members.extend(z.get("members") or [])

    transport_count = int(report.get("conveyor_count") or 0)
    kind_counts = ((equip.get("inventory") or {}).get("kind_counts") or {})

    print("capturing pipeline...")
    cap = capture_pipeline(RUN, MACHINE, archive_sha=archive_sha)
    cap["git_sha"] = GIT_SHA
    cap["project"] = PROJECT
    cap["safety_devices"] = safety_count
    cap["safety_review"] = str(es.get("status") or "")
    cap["transportation_objects"] = transport_count
    cap["transportation_review"] = "conveyor_count from FIELD_VALIDATION build report"
    cap["meta"] = {
        "virgin_test": True,
        "machine": MACHINE,
        "project": PROJECT,
        "baseline_git_sha": GIT_SHA,
        "field_validation_output_only": True,
    }

    build_status = str(es.get("status") or "REVIEW_REQUIRED")
    if (manifest.get("review_items") or {}).get("complete") is False:
        build_status = "REVIEW_REQUIRED"

    notes = (
        "MSCRENOSHIP virgin field-test freeze; virgin_test=true; "
        f"git_sha={GIT_SHA}; eip_bank_state={cap.get('eip_bank_state')}; "
        f"es_status={es.get('status')}; stage0_build={stage0.get('build_status')}"
    )

    print("persisting field test...")
    persist = persist_field_test_and_failures(
        cap,
        archive_sha=archive_sha,
        build_status=build_status,
        notes=notes,
        artifact_paths=[
            "exports/current/MSCRENOSHIP_2026_09_21_0108.L5X",
            "exports/current/MSCRENOSHIP_2026_09_21_0108.manifest.json",
            "exports/diagnostics/mscrenoship_virgin_field_freeze.json",
            "exports/diagnostics/mscrenoship_virgin_field_freeze.md",
        ],
        meta={"virgin_test": True, "freeze": "mscrenoship_virgin_field_freeze"},
    )
    print("persist", persist)
    if not persist.get("ok"):
        print("FAIL persist", persist)
        return 1

    print("ingesting warehouse...")
    writer = PostgresWarehouseWriter()
    writer.ensure_extractor_version()
    known = writer.known_complete_shas()
    force = archive_sha not in known
    print("known_complete", archive_sha in known, "force", force)
    bundle = build_bundle_from_run_dir(
        RUN,
        archive_sha256=archive_sha,
        filename=TAR.name,
        discovered_path=str(TAR.resolve()),
    )
    bundle.machine = MACHINE
    bundle.project = PROJECT
    if bundle.archive:
        bundle.archive.machine = MACHINE
        bundle.archive.project = PROJECT
        bundle.archive.site = PROJECT
        bundle.archive.filename = TAR.name
        bundle.archive.discovered_path = str(TAR.resolve())
        bundle.archive.size_bytes = TAR.stat().st_size
        bundle.archive.archive_class = "RUN"
    ingest = writer.ingest_bundle(bundle, force=force)
    ingest_counts = ingest.get("counts") or bundle.staging_counts()
    print("ingest", ingest.get("status"), ingest_counts)

    owners = {
        "claimed_channels": cap.get("claimed_channels"),
        "claims_resolved": cap.get("claims_resolved"),
        "claims_unresolved": cap.get("claims_unresolved"),
        "assign_how_counts": cap.get("assign_how_counts"),
        "dispositions": cap.get("dispositions"),
    }
    safety_by_class: dict[str, int] = {}
    for d in safety_devs:
        cls = str((d.get("device_class") or d.get("class") or d.get("kind") or "UNKNOWN"))
        safety_by_class[cls] = safety_by_class.get(cls, 0) + 1

    freeze = {
        "kind": "mscrenoship_virgin_field_freeze",
        "virgin_test": True,
        "machine": MACHINE,
        "project": PROJECT,
        "git_sha": GIT_SHA,
        "baseline_sha": GIT_SHA,
        "archive_sha256": archive_sha,
        "field_test_id": persist.get("field_test_id"),
        "persist": persist,
        "ingest": {
            "status": ingest.get("status"),
            "archive_sha256": ingest.get("archive_sha256") or archive_sha,
            "force": force,
            "counts": ingest_counts,
        },
        "paths": {
            "run_dir": str(RUN),
            "inbox_tar": str(TAR),
            "l5x": str(L5X),
            "manifest": str(MANIFEST),
            "build_dir": str(BUILD),
        },
        "build_status": build_status,
        "manifest_es_status": es.get("status"),
        "counts": {
            "claims_created": cap.get("claims_created"),
            "claims_resolved": cap.get("claims_resolved"),
            "claims_unresolved": cap.get("claims_unresolved"),
            "raw_physical_candidates": cap.get("raw_physical_candidates"),
            "owners": owners,
            "safety_devices": safety_count,
            "safety_discover": {
                "device_count": safety_count,
                "by_class": safety_by_class,
                "sample_names": [
                    str(d.get("name") or d.get("io_name") or "")
                    for d in safety_devs[:20]
                ],
            },
            "safety_zone_members_emitted": len(set(members)),
            "safety_ready_zones": len(es.get("ready_zones") or []),
            "safety_review_zones": len(es.get("review_zones") or []),
            "transport_conveyors": transport_count,
            "transport": {
                "conveyor_count": report.get("conveyor_count"),
                "area_count": report.get("area_count"),
                "pe_device_count": report.get("pe_device_count"),
                "eip_adapter_count": report.get("eip_adapter_count"),
                "io_module_count": report.get("io_module_count"),
                "equipment_kind_counts": kind_counts,
            },
            "stage0": stage0,
            "racks": cap.get("racks"),
            "modules": cap.get("modules"),
            "eip_bank_state": cap.get("eip_bank_state"),
        },
        "capture_summary": {
            k: cap.get(k)
            for k in (
                "machine",
                "archive_sha",
                "eip_bank_state",
                "claims_created",
                "claims_resolved",
                "claims_unresolved",
                "assign_how_counts",
                "racks",
                "modules",
                "claimed_channels",
                "failure_code_counts",
                "signature_counts",
                "git_sha",
                "captured_at",
            )
        },
    }

    json_path = OUT / "mscrenoship_virgin_field_freeze.json"
    md_path = OUT / "mscrenoship_virgin_field_freeze.md"
    json_path.write_text(json.dumps(freeze, indent=2, default=str), encoding="utf-8")
    c = freeze["counts"]
    md = [
        "# MSCRENOSHIP virgin field-test freeze",
        "",
        "- **virgin_test:** true",
        f"- **field_test_id:** `{freeze['field_test_id']}`",
        f"- **archive_sha256:** `{archive_sha}`",
        f"- **git_sha:** `{GIT_SHA}`",
        f"- **build_status:** `{build_status}`",
        f"- **ingest:** `{freeze['ingest']['status']}` (force={force})",
        "",
        "## Key counts",
        "",
        f"- claims_created: {c['claims_created']}",
        f"- claims_resolved: {c['claims_resolved']}",
        f"- claims_unresolved: {c['claims_unresolved']}",
        f"- owners.claimed_channels: {owners.get('claimed_channels')}",
        f"- safety_devices (discover): {c['safety_devices']}",
        f"- safety_zone_members_emitted: {c['safety_zone_members_emitted']}",
        f"- safety_ready_zones: {c['safety_ready_zones']}",
        f"- safety_review_zones: {c['safety_review_zones']}",
        f"- transport_conveyors: {c['transport_conveyors']}",
        f"- racks/modules: {c['racks']}/{c['modules']}",
        f"- eip_bank_state: `{c['eip_bank_state']}`",
        "",
        "## Artifacts",
        "",
        f"- L5X: `{L5X}`",
        f"- Manifest: `{MANIFEST}`",
        f"- RUN: `{RUN}`",
        f"- Inbox tar: `{TAR}`",
        f"- Freeze JSON: `{json_path}`",
        "",
    ]
    md_path.write_text("\n".join(md), encoding="utf-8")
    print("wrote", json_path)
    print("wrote", md_path)
    print(
        "DONE",
        json.dumps(
            {
                "field_test_id": persist.get("field_test_id"),
                "archive_sha": archive_sha,
                "claims_created": c["claims_created"],
                "claims_resolved": c["claims_resolved"],
                "claims_unresolved": c["claims_unresolved"],
                "safety_devices": safety_count,
                "transport_conveyors": transport_count,
                "ingest": ingest.get("status"),
            }
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
