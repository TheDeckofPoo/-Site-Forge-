"""Rebuild TFCP1 Safety inventory from virgin RUN and classify assignability."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))
os.chdir(REPO)
os.environ["FORTNA_PRISM_DISABLE"] = "1"

OUT = Path(__file__).with_name("tfcp1_live_safety_inventory.json")
TAR = REPO / "workspace" / "inbox" / "TFCP1-VIRGIN-DELIVERY-GATE-RUN.tar.gz"


def main() -> int:
    from apply_recipe import import_package
    from fortna_safety_endpoint_integrity import apply_endpoint_integrity_pipeline
    from fortna_safety_model import build_safety_model

    # Clear-ish import of virgin TAR
    meta = import_package(TAR)
    run_dir = Path(meta["run_dir"])
    machine = str(meta.get("machine") or "TFCP1")
    model = build_safety_model(run_dir=run_dir, machine=machine, areas=["TFCP1_Area"])
    devices = list(model.get("devices") or [])
    pipeline_report = None
    try:
        pipeline_report = apply_endpoint_integrity_pipeline(
            devices, run_dir=run_dir, machine=machine
        )
    except TypeError:
        try:
            pipeline_report = apply_endpoint_integrity_pipeline(devices, run_dir=run_dir)
        except Exception as e:
            print("enrich_skip", e)
    except Exception as e:
        print("enrich_skip", e)

    found = []
    assignable = []
    review = []
    reasons = Counter()
    for d in devices:
        name = d.get("name") or d.get("tag") or d.get("device")
        reason = (
            d.get("nonAssignableReason")
            or d.get("non_assignable_reason")
            or d.get("reasonCode")
            or d.get("reason")
            or d.get("reviewReason")
            or d.get("status")
            or d.get("classification")
            or ("assignable=false" if d.get("assignable") is False else None)
            or d.get("kind")
        )
        entry = {
            "name": name,
            "assignable": d.get("assignable"),
            "hardwareBacked": d.get("hardwareBacked") or d.get("hardware_backed"),
            "endpoint": d.get("physical_endpoint")
            or d.get("endpoint")
            or d.get("ioAddress")
            or d.get("address")
            or d.get("resolved_endpoint"),
            "safety_role": d.get("safety_role") or d.get("role"),
            "reason": reason,
            "sample_keys": sorted(d.keys())[:40],
        }
        found.append(entry)
        if d.get("assignable") is True:
            assignable.append(entry)
        else:
            review.append(entry)
            reasons[str(reason)] += 1

    out = {
        "import_meta": {
            "machine": machine,
            "run_dir": str(run_dir),
            "tar_sha256": meta.get("tar_sha256"),
            "archive_name": meta.get("archive_name"),
        },
        "found_count": len(found),
        "assignable_count": len(assignable),
        "review_count": len(review),
        "review_reason_counts": dict(reasons),
        "assignable": assignable,
        "review_sample": review[:25],
        "found_names": [f["name"] for f in found],
        "model_counts": model.get("counts"),
        "model_readiness": model.get("readiness"),
        "pipeline_report_keys": list(pipeline_report.keys())
        if isinstance(pipeline_report, dict)
        else None,
        "model_zones": [
            {
                "name": z.get("name"),
                "membersOrigin": z.get("membersOrigin"),
                "member_count": len(z.get("members") or []),
                "operational": z.get("operational"),
                "status": z.get("status"),
            }
            for z in (model.get("zones") or [])
        ],
    }
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    # also dump raw model for forensics
    (Path(__file__).with_name("tfcp1_live_safety_model.json")).write_text(
        json.dumps(model, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "found": out["found_count"],
                "assignable": out["assignable_count"],
                "review": out["review_count"],
                "assignable_names": [a["name"] for a in assignable],
                "review_reason_counts": out["review_reason_counts"],
                "zones": out["model_zones"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
