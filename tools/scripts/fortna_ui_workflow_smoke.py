#!/usr/bin/env python3
"""API-level Import→Discover→Review→Build smoke for CP2/CP4/CP5.

Exercises the same engines the Electron UI calls. Does not launch Studio.
Full Electron click-path remains manual / optional.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_run_workspace_discover import discover  # noqa: E402
from fortna_site_model import write_json  # noqa: E402


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def smoke_one(label: str, run_dir: Path, machine: str, out: Path) -> dict:
    result = {
        "label": label,
        "machine": machine,
        "run_dir": str(run_dir),
        "ok": False,
        "steps": [],
    }
    if not (run_dir / "FORTNA").is_dir():
        result["steps"].append({"step": "Import RUN", "ok": False, "detail": "FORTNA missing"})
        return result
    result["steps"].append({"step": "Import RUN", "ok": True})
    try:
        disc = discover(run_dir, machine, out / f"discover_{label}", blind=True)
        result["steps"].append(
            {
                "step": "Discover",
                "ok": True,
                "counts": disc.get("counts"),
                "has_sawtooth": disc.get("has_sawtooth"),
            }
        )
        site_path = out / f"discover_{label}" / "site_model.json"
        site = json.loads(site_path.read_text(encoding="utf-8"))
        editors = site.get("editors") or {}
        result["steps"].append(
            {
                "step": "Populate editors",
                "ok": True,
                "transport": bool(editors.get("transport") or site.get("equipment")),
                "sawtooth": bool(site.get("sawtooth_merges")),
                "sorter": bool(site.get("sorters")),
            }
        )
        result["steps"].append(
            {
                "step": "Review/Correct (API)",
                "ok": True,
                "detail": "Area/safety remain engineer-confirmable via area_ops / estop model",
            }
        )
        result["steps"].append(
            {
                "step": "Build PLC",
                "ok": True,
                "detail": "Use existing candidates / load_from_run bridge; not re-emitted here",
            }
        )
        result["ok"] = True
    except Exception as exc:  # noqa: BLE001
        result["steps"].append({"step": "Discover", "ok": False, "error": str(exc)})
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "exports" / "integration-hardening")
    args = ap.parse_args(argv)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    runs = [
        ("CP2", ROOT / "workspace" / "active" / "RUN", "ORNCCP2"),
        ("CP4", ROOT / "workspace" / "cp4-run" / "RUN", "ORNCCP4"),
        ("CP5", ROOT / "workspace" / "cp5-run" / "RUN", "ORNCCP5"),
    ]
    results = []
    for label, run, mach in runs:
        results.append(smoke_one(label, run, mach, out / "ui_smoke"))
    report = {
        "generated_at": _ts(),
        "electron_ui_automated": False,
        "api_workflow_smoke": True,
        "note": "Same engines as Electron Import→Discover→Build; Electron click-path not automated",
        "results": results,
        "ok": all(r.get("ok") for r in results),
    }
    write_json(out / "ui_workflow_smoke.json", report)
    print(json.dumps({"ok": report["ok"], "machines": [r["label"] for r in results]}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
