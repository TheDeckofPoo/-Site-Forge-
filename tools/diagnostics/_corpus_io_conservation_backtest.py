#!/usr/bin/env python3
"""Corpus I/O conservation backtest after deterministic autogen fix.

Measures per available RUN peek (workspace peeks; PG corpus listed if reachable):
  - physical claims (Configio-backed raw claims)
  - emitted specialized / generic_bool mappings
  - true unclaimed capacity (NO_PointPlaceholder fill)
  - lost claims (PWR-resolved claim channels missing named IO_MAP)

Primary invariant: LOST CLAIMS = 0.
Does not tune virgin sites. Does not push.

Writes:
  exports/diagnostics/corpus_io_conservation_backtest.json
  exports/diagnostics/corpus_io_conservation_backtest.md
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(SCRIPTS))

from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_autogen import DEFAULT_LIBRARY, build_l5x, load_from_run  # noqa: E402

OUT_JSON = ROOT / "exports" / "diagnostics" / "corpus_io_conservation_backtest.json"
OUT_MD = ROOT / "exports" / "diagnostics" / "corpus_io_conservation_backtest.md"

# Prefer known peeks; path parent name is fallback when cfg parse fails.
PEEK_RUNS: list[tuple[str, Path]] = [
    ("MSCATL_CP3", ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"),
    ("ORINDYAC6", ROOT / "workspace" / "_virgin_orindy" / "RUN"),
    ("ORNCCP2", ROOT / "workspace" / "_plc2_run_peek" / "RUN"),
    ("ORNCCP4", ROOT / "workspace" / "cp4-run" / "RUN"),
    ("ORNCCP5", ROOT / "workspace" / "cp5-run" / "RUN"),
    ("ORDENCP3", ROOT / "workspace" / "_ordencp3_peek" / "ORDENCP3" / "RUN"),
    (
        "MSCRENOPICK",
        ROOT
        / "workspace"
        / "_reno_peek"
        / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
        / "RUN",
    ),
    (
        "MSCRENOPACK",
        ROOT
        / "workspace"
        / "_reno_peek"
        / "20260813-1132-MSCRENO-MSCRENOPACK-RUN"
        / "RUN",
    ),
    (
        "MSCRENOSHIP",
        ROOT
        / "workspace"
        / "_reno_peek"
        / "20260813-1132-MSCRENO-MSCRENOSHIP-RUN"
        / "RUN",
    ),
    ("PMARTOTW_AC1", ROOT / "workspace" / "_corpus_peek" / "PMARTOTW_AC1" / "RUN"),
    ("RESPICK", ROOT / "workspace" / "_corpus_peek" / "RESPICK" / "RUN"),
]


def _machine_from_cfg(run_dir: Path) -> str:
    cfg = run_dir / "project.cfg"
    if not cfg.is_file():
        return ""
    text = cfg.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"MACHINENAME\s*=\s*(\S+)", text, re.I)
    return (m.group(1).strip() if m else "") or ""


def _is_spare_name(name: str) -> bool:
    n = (name or "").strip().upper()
    if not n or n in {"SPARE", "N/A", "NONE", "INVALID"}:
        return True
    if n.startswith("SPARE") or "_SPARE" in n or n.endswith("SPARE"):
        return True
    return False


def _account_controller(label: str, run_dir: Path) -> dict[str, Any]:
    machine = _machine_from_cfg(run_dir) or label
    row: dict[str, Any] = {
        "controller": machine,
        "peek_label": label,
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "applicable": False,
        "status": "SKIP",
        "error": None,
    }
    if not (run_dir / "project.cfg").is_file():
        row["error"] = "missing project.cfg"
        return row

    try:
        evidence = build_evidence_bundle(run_dir, machine, project=machine)
    except Exception as ex:
        row["error"] = f"evidence: {ex}"
        row["traceback"] = traceback.format_exc(limit=4)
        return row

    raw_claims = list(evidence.get("raw_claims") or [])
    assigned = [
        c
        for c in raw_claims
        if str(c.get("deterministic_disposition") or "").upper() == "ASSIGNED"
        or not c.get("deterministic_disposition")
    ]
    # Prefer explicit ASSIGNED when present; else all physical raw claims.
    has_disp = any(c.get("deterministic_disposition") for c in raw_claims)
    physical_claims = assigned if has_disp else raw_claims
    spare_claims = [
        c
        for c in physical_claims
        if _is_spare_name(str(c.get("io_name") or c.get("claim_id") or ""))
    ]
    intentional_mute_names = sorted(
        {
            str(c.get("io_name") or "").strip()
            for c in spare_claims
            if str(c.get("io_name") or "").strip()
        }
    )

    cc = evidence.get("conservation_counts") or {}
    ss = (evidence.get("summary") or {}) if isinstance(evidence.get("summary"), dict) else {}

    # Controllers with zero physical claims are not applicable to LOST invariant
    # in the same way (ORDEN alternate-evidence / empty panels).
    if len(physical_claims) == 0 and int(cc.get("raw_physical_claims") or ss.get("raw_physical_claims") or 0) == 0:
        row.update(
            {
                "applicable": False,
                "status": "NO_PHYSICAL_CLAIMS",
                "physical_claims": 0,
                "emitted_specialized": 0,
                "emitted_generic_bool": 0,
                "true_unclaimed_placeholders": 0,
                "lost_claims": 0,
                "intentional_mute": intentional_mute_names,
                "lost_ok": True,
                "note": "zero physical claims — conservation N/A for emit path",
            }
        )
        return row

    try:
        inp = load_from_run(run_dir)
        inp.include_io_map = True
        inp.include_io_map_gold = False
        # Placeholders default on — matches product CLI / Atlanta regen.
        if hasattr(inp, "io_map_fill_placeholders"):
            setattr(inp, "io_map_fill_placeholders", True)
        _l5x, report = build_l5x(inp, Path(DEFAULT_LIBRARY))
    except Exception as ex:
        row["error"] = f"autogen: {ex}"
        row["traceback"] = traceback.format_exc(limit=6)
        row["physical_claims"] = len(physical_claims)
        row["status"] = "ERROR"
        return row

    lost = int(report.get("io_map_lost_claims_count") or 0)
    specialized = int(report.get("io_map_mapped_specialized") or 0)
    generic_bool = int(report.get("io_map_mapped_generic_bool") or 0)
    placeholders = int(report.get("io_map_placeholders") or 0)
    mapped = int(report.get("io_map_mapped") or 0)
    muted = int(report.get("io_map_muted") or 0)
    skipped_spare = int(report.get("io_map_skipped_spare") or 0)

    row.update(
        {
            "applicable": True,
            "status": "PASS" if lost == 0 else "FAIL_LOST_CLAIMS",
            "physical_claims": len(physical_claims),
            "raw_physical_claims_evidence": int(
                cc.get("raw_physical_claims")
                or ss.get("raw_physical_claims")
                or len(raw_claims)
            ),
            "emitted_mapped": mapped,
            "emitted_specialized": specialized,
            "emitted_generic_bool": generic_bool,
            "true_unclaimed_placeholders": placeholders,
            "lost_claims": lost,
            "lost_claims_sample": list(report.get("io_map_lost_claims_sample") or [])[:20],
            "io_map_muted": muted,
            "io_map_skipped_spare": skipped_spare,
            "io_map_mappable": int(report.get("io_map_mappable") or 0),
            "io_point_count": int(report.get("io_point_count") or 0),
            "intentional_mute": intentional_mute_names,
            "lost_ok": lost == 0,
            "autogen_machine": str(getattr(inp, "machine", "") or machine),
        }
    )
    return row


def _pg_corpus_snapshot() -> dict[str, Any]:
    try:
        from siteforge_warehouse.postgres_repository import make_engine
        from sqlalchemy import text

        eng = make_engine()
        if eng is None:
            return {"available": False, "reason": "make_engine returned None"}
        with eng.connect() as c:
            archives = [
                dict(r)
                for r in c.execute(
                    text(
                        "SELECT machine, complete, sync_status, discovered_path "
                        "FROM corpus.archives ORDER BY machine"
                    )
                ).mappings()
            ]
        complete = [a for a in archives if a.get("complete")]
        return {
            "available": True,
            "archive_count": len(archives),
            "complete_count": len(complete),
            "machines": sorted({str(a.get("machine") or "") for a in complete if a.get("machine")}),
            "note": (
                "PG corpus listed for coverage context; backtest measures workspace "
                "RUN peeks via load_from_run/build_l5x (not remote tar extract)."
            ),
        }
    except Exception as ex:
        return {"available": False, "reason": str(ex)}


def _try_pg_store(payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort store; diagnostic artifacts are authoritative."""
    try:
        from siteforge_warehouse.postgres_repository import make_engine
        from sqlalchemy import text

        eng = make_engine()
        if eng is None:
            return {"stored": False, "reason": "no engine"}
        # No dedicated diagnostics table — skip rather than invent schema.
        with eng.connect() as c:
            n = c.execute(text("SELECT COUNT(*) FROM corpus.archives")).scalar()
        return {
            "stored": False,
            "reason": (
                f"PG reachable (corpus.archives={n}) but no diagnostics artifact "
                "table; JSON/MD on disk are sufficient"
            ),
            "skipped": True,
        }
    except Exception as ex:
        return {"stored": False, "reason": str(ex), "skipped": True}


def render_md(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Corpus I/O conservation backtest")
    lines.append("")
    lines.append(f"Generated: `{payload['generated_at']}`")
    lines.append("")
    lines.append(
        "Primary invariant: **LOST CLAIMS = 0** "
        "(resolved physical claims must not silently become placeholders)."
    )
    lines.append("")
    lines.append("## Aggregate")
    lines.append("")
    lines.append(
        "| Controller | claims | specialized | generic_bool | placeholders | lost | mute | status |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |")
    for r in payload["controllers"]:
        if not r.get("applicable") and r.get("status") == "SKIP":
            continue
        mute = ", ".join(r.get("intentional_mute") or []) or "—"
        if len(mute) > 40:
            mute = mute[:37] + "…"
        lines.append(
            f"| `{r.get('controller')}` | {r.get('physical_claims', '—')} | "
            f"{r.get('emitted_specialized', '—')} | {r.get('emitted_generic_bool', '—')} | "
            f"{r.get('true_unclaimed_placeholders', '—')} | {r.get('lost_claims', '—')} | "
            f"{mute} | **{r.get('status')}** |"
        )
    lines.append("")
    agg = payload["aggregate"]
    lines.append(
        f"- Applicable controllers: **{agg['applicable']}** · "
        f"LOST=0: **{agg['lost_ok']}** · FAIL: **{agg['lost_fail']}**"
    )
    lines.append(f"- All applicable LOST=0: **{agg['all_lost_zero']}**")
    lines.append("")
    lines.append("## Atlanta expectation check")
    lines.append("")
    atl = payload.get("atlanta_check") or {}
    lines.append(
        f"- claims={atl.get('physical_claims')} (expect ~256) · "
        f"specialized={atl.get('emitted_specialized')} (expect ~149) · "
        f"generic_bool={atl.get('emitted_generic_bool')} (expect ~106) · "
        f"lost={atl.get('lost_claims')} (expect 0) · "
        f"mute={atl.get('intentional_mute')}"
    )
    lines.append(f"- match_expected: **{atl.get('match_expected')}**")
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append("- Claim authority: `build_evidence_bundle` raw physical claims")
    lines.append(
        "- Emit path: `load_from_run` → `build_l5x` (IO_MAP + placeholders; no gold Excel)"
    )
    lines.append(
        "- Counters from autogen report: specialized / generic_bool / placeholders / "
        "`io_map_lost_claims_count`"
    )
    lines.append("- Virgin sites measured only — not tuned")
    lines.append("")
    pg = payload.get("postgres") or {}
    lines.append("## PostgreSQL")
    lines.append("")
    if pg.get("corpus", {}).get("available"):
        lines.append(
            f"- Corpus reachable: {pg['corpus'].get('complete_count')} complete / "
            f"{pg['corpus'].get('archive_count')} archives"
        )
    else:
        lines.append(f"- Corpus: skipped — {pg.get('corpus', {}).get('reason')}")
    store = pg.get("store") or {}
    lines.append(f"- Artifact store: {store.get('reason') or store}")
    lines.append("")
    lines.append("## Errors / skips")
    lines.append("")
    errs = [r for r in payload["controllers"] if r.get("error") or r.get("status") in ("SKIP", "ERROR")]
    if not errs:
        lines.append("_None._")
    else:
        for r in errs:
            lines.append(
                f"- `{r.get('controller')}` ({r.get('status')}): {r.get('error') or 'n/a'}"
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    controllers: list[dict[str, Any]] = []
    for label, run_dir in PEEK_RUNS:
        print(f"== {label} :: {run_dir}")
        if not run_dir.is_dir():
            controllers.append(
                {
                    "controller": label,
                    "peek_label": label,
                    "run_dir": str(run_dir),
                    "applicable": False,
                    "status": "SKIP",
                    "error": "run dir missing",
                }
            )
            continue
        row = _account_controller(label, run_dir)
        controllers.append(row)
        print(
            f"   status={row.get('status')} claims={row.get('physical_claims')} "
            f"spec={row.get('emitted_specialized')} gen={row.get('emitted_generic_bool')} "
            f"ph={row.get('true_unclaimed_placeholders')} lost={row.get('lost_claims')} "
            f"mute={row.get('intentional_mute')}"
        )

    applicable = [r for r in controllers if r.get("applicable")]
    lost_ok = [r for r in applicable if r.get("lost_ok")]
    lost_fail = [r for r in applicable if not r.get("lost_ok")]

    atlanta = next((r for r in controllers if r.get("controller") == "MSCATL_CP3"), {})
    mute = set(atlanta.get("intentional_mute") or [])
    atlanta_check = {
        **{k: atlanta.get(k) for k in (
            "physical_claims",
            "emitted_specialized",
            "emitted_generic_bool",
            "true_unclaimed_placeholders",
            "lost_claims",
            "intentional_mute",
            "status",
        )},
        "match_expected": bool(
            atlanta.get("applicable")
            and atlanta.get("lost_claims") == 0
            and int(atlanta.get("physical_claims") or 0) == 256
            and int(atlanta.get("emitted_specialized") or 0) == 149
            and int(atlanta.get("emitted_generic_bool") or 0) == 106
            and "SPARE70207" in mute
        ),
    }

    corpus = _pg_corpus_snapshot()
    payload: dict[str, Any] = {
        "kind": "corpus_io_conservation_backtest",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "primary_invariant": "LOST_CLAIMS == 0",
        "method": {
            "evidence": "fortna_ai_io_evidence.build_evidence_bundle",
            "emit": "fortna_autogen.load_from_run + build_l5x (IO_MAP path)",
            "note": "Full library emit per peek (~few seconds); no virgin tuning",
        },
        "controllers": controllers,
        "aggregate": {
            "peek_count": len(controllers),
            "applicable": len(applicable),
            "lost_ok": len(lost_ok),
            "lost_fail": len(lost_fail),
            "all_lost_zero": len(applicable) > 0 and len(lost_fail) == 0,
        },
        "atlanta_check": atlanta_check,
        "postgres": {
            "corpus": corpus,
            "store": None,  # filled after write
        },
    }
    store = _try_pg_store(payload)
    payload["postgres"]["store"] = store

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    OUT_MD.write_text(render_md(payload), encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    print(
        "aggregate:",
        f"applicable={len(applicable)}",
        f"lost_ok={len(lost_ok)}",
        f"lost_fail={len(lost_fail)}",
        f"atlanta_match={atlanta_check.get('match_expected')}",
        f"pg_store_skipped={store.get('skipped')}",
    )
    return 0 if payload["aggregate"]["all_lost_zero"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
