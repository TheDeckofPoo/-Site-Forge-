"""Classify TFCP1 Safety inventory: FOUND / ASSIGNABLE / REVIEW."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODEL = REPO / "exports" / "plc2-safety" / "safety_model_TFCP1.json"
OUT = Path(__file__).with_name("tfcp1_safety_inventory.json")


def main() -> None:
    j = json.loads(MODEL.read_text(encoding="utf-8"))
    devices = j.get("devices") or j.get("safetyDevices") or []
    found = []
    assignable = []
    review = []
    reasons = Counter()
    for d in devices:
        name = d.get("name") or d.get("device") or d.get("id")
        entry = {
            "name": name,
            "assignable": d.get("assignable"),
            "hardwareBacked": d.get("hardwareBacked"),
            "reason": d.get("nonAssignableReason")
            or d.get("reason")
            or d.get("reviewReason")
            or d.get("status")
            or d.get("classification")
            or d.get("kind"),
            "endpoint": d.get("physical_endpoint")
            or d.get("endpoint")
            or d.get("ioAddress")
            or d.get("address"),
            "safety_role": d.get("safety_role") or d.get("role"),
            "keys": sorted(d.keys())[:25],
        }
        found.append(entry)
        if d.get("assignable") is True:
            assignable.append(entry)
        else:
            review.append(entry)
            reasons[str(entry["reason"])] += 1

    out = {
        "machine": j.get("machine"),
        "found_count": len(found),
        "assignable_count": len(assignable),
        "review_count": len(review),
        "review_reason_counts": dict(reasons),
        "assignable_names": [a["name"] for a in assignable],
        "assignable_sample": assignable[:30],
        "review_sample": review[:20],
        "zones_in_model": [
            {
                "name": z.get("name"),
                "members": z.get("members"),
                "membersOrigin": z.get("membersOrigin"),
                "operational": z.get("operational"),
                "status": z.get("status"),
            }
            for z in (j.get("zones") or [])
        ],
        "counts": j.get("counts"),
        "readiness": j.get("readiness"),
    }
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "found": out["found_count"],
                "assignable": out["assignable_count"],
                "review": out["review_count"],
                "assignable_names": out["assignable_names"][:40],
                "review_reason_counts": out["review_reason_counts"],
                "zones": out["zones_in_model"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
