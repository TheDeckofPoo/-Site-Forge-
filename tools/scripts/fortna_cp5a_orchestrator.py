#!/usr/bin/env python3
"""CP5A thin production orchestrator — RUN → CP1–CP4 → semantic cache.

Does NOT reimplement CP1–CP4. Does NOT invent engineering semantics.
Emits FORTNA_PROGRESS lines for Site Forge UI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_reference_resolver import build_reference_graph, write_graph  # noqa: E402
from fortna_semantics.bundle import run_cp4_bundle  # noqa: E402
from fortna_semantics.evidence import write_json  # noqa: E402


def progress(phase: str, detail: str = "", *, pct: float | None = None) -> None:
    payload = {"phase": phase, "detail": detail}
    if pct is not None:
        payload["pct"] = pct
    print(f"FORTNA_PROGRESS {json.dumps(payload, ensure_ascii=False)}", file=sys.stderr, flush=True)


def resolve_ac_name(run_dir: Path, explicit: str = "") -> str:
    if explicit:
        return explicit.strip().upper()
    cfg = run_dir / "project.cfg"
    if not cfg.is_file():
        # sometimes under PROJECT/
        alt = run_dir / "PROJECT" / "project.cfg"
        cfg = alt if alt.is_file() else cfg
    if cfg.is_file():
        text = cfg.read_text(encoding="latin-1", errors="replace")
        for line in text.splitlines():
            if "MACHINENAME" in line.upper() or line.upper().startswith("MACHINE"):
                parts = line.replace("=", " ").split()
                if len(parts) >= 2:
                    return parts[-1].strip().upper()
    # parent meta
    meta = ROOT / "workspace" / "active-meta.json"
    if meta.is_file():
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
            for k in ("machine", "controller"):
                if m.get(k):
                    return str(m[k]).upper()
            pn = str(m.get("project_name") or "")
            import re

            mm = re.search(r"_([A-Z0-9]+)$", pn, re.I)
            if mm:
                return mm.group(1).upper()
        except Exception:
            pass
    return "UNKNOWN"


def run_decoder_stack(
    *,
    run_dir: Path,
    ac_name: str,
    out_dir: Path,
) -> dict[str, Any]:
    """Orchestrate CP1–CP4 into out_dir. Returns summary + paths."""
    run_dir = Path(run_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fortna = run_dir / "FORTNA" / "fortna.mnu"
    project = run_dir / "PROJECT" / "project.mnu"
    if not fortna.is_file():
        return {
            "ok": False,
            "layer": "CP1",
            "error": f"CP1 DECODER ERROR: missing fortna.mnu under {run_dir}",
        }

    progress("Loading FortnaPlus schema", str(fortna), pct=5)
    progress("Loading RUN records + resolving relationships", ac_name, pct=20)
    try:
        graph_path = out_dir / "cp3-reference-graph.json"
        graph = build_reference_graph(
            fortna_mnu=fortna,
            project_mnu=project if project.is_file() else None,
            run_dir=run_dir,
            ac_name=ac_name,
        )
        digest = write_graph(graph, graph_path)
    except Exception as e:
        return {
            "ok": False,
            "layer": "CP3",
            "error": f"CP3 REFERENCE ERROR: {e}",
        }

    progress("Building engineering semantics", "CP4 adapters", pct=70)
    try:
        bundle = run_cp4_bundle(
            site="active",
            graph_path=graph_path,
            ac_name=ac_name,
            out_dir=out_dir,
        )
    except Exception as e:
        return {
            "ok": False,
            "layer": "CP4",
            "error": f"CP4 TRANSPORTATION ERROR: {e}",
        }

    # Canonical cache names expected by Electron
    write_json(out_dir / "cp4-semantic-bundle.json", bundle)
    # Also copy transport/mtrchain focused extracts
    summary = {
        "ok": True,
        "acName": ac_name,
        "runDir": str(run_dir),
        "outDir": str(out_dir),
        "cp3Graph": str(graph_path),
        "cp3Sha256": digest,
        "cp3Stats": graph.get("statistics") or {},
        "cp4Status": bundle.get("status"),
        "adapters": bundle.get("adapters") or {},
        "transportation": (bundle.get("adapterResults") or {}).get("Transportation") or {},
        "mtrchain": (bundle.get("adapterResults") or {}).get("Mtrchain") or {},
    }
    write_json(out_dir / "cp5a-decoder-summary.json", summary)
    progress("Decoder complete", f"bundle={bundle.get('status')}", pct=90)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CP5A decoder orchestrator")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--ac-name", default="")
    ap.add_argument("--out-dir", default="")
    args = ap.parse_args(argv)
    run_dir = Path(args.run_dir)
    ac = resolve_ac_name(run_dir, args.ac_name)
    out = Path(args.out_dir) if args.out_dir else (ROOT / "workspace" / "active" / "decoder")
    result = run_decoder_stack(run_dir=run_dir, ac_name=ac, out_dir=out)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
