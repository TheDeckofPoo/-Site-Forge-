#!/usr/bin/env python3
"""Corpus audit: RUN trees with multiple *-RTA-eipcfg.xml files."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_machine_source_scope import (  # noqa: E402
    read_machine_name,
    select_active_eipcfg,
)


def main() -> int:
    roots = [
        ROOT / "exports/learning/_extract",
        ROOT / "workspace/_corpus_peek",
        ROOT / "workspace/_mscatl_peek",
        ROOT / "workspace/_reno_peek",
        ROOT / "workspace/_virgin_orindy",
        ROOT / "workspace/_ordencp3_peek",
        ROOT / "workspace/cp4-run",
    ]
    rows = []
    for root in roots:
        if not root.is_dir():
            continue
        for cfg in sorted(root.rglob("project.cfg")):
            run = cfg.parent
            fortna = run / "FORTNA"
            if not fortna.is_dir():
                continue
            eips = sorted(fortna.glob("*eipcfg*.xml"))
            if len(eips) < 2:
                continue
            active = read_machine_name(run)
            sel = select_active_eipcfg(run, active)
            rows.append(
                {
                    "run": str(run),
                    "active_machine": active,
                    "eipcfg_files": [p.name for p in eips],
                    "selected": Path(sel["selected_eipcfg"]).name
                    if sel.get("selected_eipcfg")
                    else None,
                    "selection_reason": sel.get("selection_reason"),
                    "siblings": [s.get("source_file") for s in (sel.get("siblings") or [])],
                    "refused_sibling_fallback": sel.get("refused_sibling_fallback"),
                }
            )
    out = {
        "kind": "multi_eipcfg_corpus_audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(rows),
        "rows": rows,
    }
    path = ROOT / "exports/learning/multi_eipcfg_audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    txt = ["MULTI-EIPCFG AUDIT", f"count={len(rows)}", ""]
    for r in rows:
        txt.append(
            f"{r['active_machine']}: selected={r['selected']} "
            f"siblings={[Path(s).name for s in r['siblings']]} "
            f"files={r['eipcfg_files']}"
        )
    (ROOT / "exports/learning/multi_eipcfg_audit.txt").write_text(
        "\n".join(txt) + "\n", encoding="utf-8"
    )
    print(json.dumps({"count": len(rows), "path": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
