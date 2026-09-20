#!/usr/bin/env python3
"""Select ONE hard blind site from PostgreSQL STRUCTURAL metrics ONLY.

MUST run BEFORE production decoding of the chosen site for this challenge.
Does not call PhysicalWordResolver / rack discovery / AI.
Excludes MSCATL_CP3 and ORNCCP4.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from siteforge_warehouse.postgres_repository import make_engine  # noqa: E402
from sqlalchemy import text  # noqa: E402

EXCLUDE_MACHINES = {"MSCATL_CP3", "ORNCCP4", "ORNCCP4".lower()}


SQL = """
WITH base AS (
  SELECT
    a.archive_sha256,
    a.project,
    a.machine,
    a.filename,
    a.complete,
    (SELECT COUNT(*) FROM evidence.configio_rows c
       WHERE c.archive_sha256 = a.archive_sha256 AND c.machine = a.machine) AS configio_n,
    (SELECT COUNT(*) FROM evidence.eipmodules m
       WHERE m.archive_sha256 = a.archive_sha256 AND m.machine = a.machine) AS eipmodule_n,
    (SELECT COUNT(DISTINCT m.type) FROM evidence.eipmodules m
       WHERE m.archive_sha256 = a.archive_sha256 AND m.machine = a.machine) AS eip_type_diversity,
    (SELECT COUNT(*) FROM evidence.eipcfg_modules em
       WHERE em.archive_sha256 = a.archive_sha256 AND em.machine = a.machine) AS eipcfg_module_n,
    (SELECT COUNT(*) FROM evidence.io_claims ic
       WHERE ic.archive_sha256 = a.archive_sha256 AND ic.machine = a.machine) AS io_claim_n,
    (SELECT COUNT(*) FROM evidence.conflicts cf
       WHERE cf.archive_sha256 = a.archive_sha256 AND cf.machine = a.machine) AS conflict_n,
    (SELECT COUNT(*) FROM evidence.adapter_bridges ab
       WHERE ab.archive_sha256 = a.archive_sha256 AND ab.machine = a.machine) AS bridge_n,
    (SELECT COUNT(*) FROM evidence.machine_source_scopes sc
       WHERE sc.archive_sha256 = a.archive_sha256) AS scope_n,
    (SELECT COUNT(*) FROM learning.dialect_observations d
       WHERE d.archive_sha256 = a.archive_sha256
         AND d.machine = a.machine
         AND UPPER(COALESCE(d.form, d.dialect_form, '')) = 'UNKNOWN') AS dialect_unknown_n,
    (SELECT COUNT(DISTINCT d.form) FROM learning.dialect_observations d
       WHERE d.archive_sha256 = a.archive_sha256 AND d.machine = a.machine) AS dialect_form_n
  FROM corpus.archives a
  WHERE a.complete IS TRUE
    AND COALESCE(a.machine, '') <> ''
    AND UPPER(a.machine) NOT IN ('MSCATL_CP3', 'ORNCCP4')
)
SELECT *,
  (
    LEAST(conflict_n, 50) * 8
    + LEAST(dialect_unknown_n, 200) * 0.05
    + LEAST(eip_type_diversity, 20) * 6
    + CASE WHEN eipcfg_module_n > 40 THEN 25 ELSE eipcfg_module_n * 0.4 END
    + CASE WHEN scope_n > 1 THEN 20 ELSE 0 END
    + CASE WHEN configio_n BETWEEN 200 AND 2000 THEN 15
           WHEN configio_n > 2000 THEN 10 ELSE configio_n * 0.02 END
    + CASE WHEN io_claim_n BETWEEN 200 AND 3000 THEN 20
           WHEN io_claim_n > 3000 THEN 12 ELSE io_claim_n * 0.01 END
    + CASE WHEN eipmodule_n >= 20 THEN 15 ELSE eipmodule_n * 0.5 END
  ) AS complexity_score
FROM base
WHERE configio_n > 50
  AND eipmodule_n > 5
  AND io_claim_n > 50
ORDER BY complexity_score DESC, conflict_n DESC, eip_type_diversity DESC, io_claim_n DESC
LIMIT 25
"""


def main() -> int:
    out_root = ROOT / "exports" / "demo" / "siteforge-reality-check-v1"
    out_root.mkdir(parents=True, exist_ok=True)
    eng = make_engine()
    assert eng is not None

    # Probe dialect column name
    with eng.connect() as c:
        cols = {
            r[0]
            for r in c.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='learning' AND table_name='dialect_observations'"
                )
            )
        }
    form_col = "form" if "form" in cols else "dialect_form"
    sql = SQL.replace("d.form, d.dialect_form", form_col).replace(
        "d.form", f"d.{form_col}"
    )
    # simpler: rebuild dialect bits if needed
    if "form" not in cols and "dialect_form" in cols:
        sql = SQL.replace("d.form, d.dialect_form", "d.dialect_form").replace(
            "UPPER(COALESCE(d.form, d.dialect_form, ''))",
            "UPPER(COALESCE(d.dialect_form, ''))",
        ).replace("COUNT(DISTINCT d.form)", "COUNT(DISTINCT d.dialect_form)")
    elif "form" in cols:
        sql = SQL.replace("d.form, d.dialect_form", "d.form").replace(
            "UPPER(COALESCE(d.form, d.dialect_form, ''))",
            "UPPER(COALESCE(d.form, ''))",
        )

    with eng.connect() as c:
        rows = [dict(r) for r in c.execute(text(sql)).mappings()]

    if not rows:
        raise SystemExit("No hard-site candidates from structural query")

    chosen = rows[0]
    payload = {
        "kind": "hard_site_selection",
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "selection_phase": "BEFORE_DECODER_OUTCOME",
        "decoder_outcome_known_at_selection": False,
        "confirmation": (
            "Selected using PostgreSQL structural complexity only "
            "(configio/eipmodules/eipcfg/io_claim COUNTS, conflicts, scopes, "
            "dialect UNKNOWN density, type diversity). "
            "No PhysicalWordResolver / discover_racks / AI / L5X consulted "
            "for this candidate before selection."
        ),
        "exclusions": ["MSCATL_CP3", "ORNCCP4"],
        "selected": {
            "archive_sha256": chosen["archive_sha256"],
            "project": chosen["project"],
            "machine": chosen["machine"],
            "filename": chosen["filename"],
            "complexity_score": float(chosen["complexity_score"]),
            "indicators": {
                k: chosen[k]
                for k in chosen
                if k
                not in (
                    "archive_sha256",
                    "project",
                    "machine",
                    "filename",
                    "complete",
                    "complexity_score",
                )
            },
        },
        "why_selected": (
            f"{chosen['machine']} ranked #1 on structural complexity_score="
            f"{float(chosen['complexity_score']):.1f}: "
            f"configio={chosen['configio_n']}, io_claims={chosen['io_claim_n']}, "
            f"eipmodules={chosen['eipmodule_n']}, type_diversity={chosen['eip_type_diversity']}, "
            f"eipcfg_modules={chosen['eipcfg_module_n']}, conflicts={chosen['conflict_n']}, "
            f"scopes={chosen['scope_n']}, dialect_unknown_obs={chosen['dialect_unknown_n']}."
        ),
        "complexity_indicators_used": [
            "configio_n",
            "io_claim_n",
            "eipmodule_n",
            "eip_type_diversity",
            "eipcfg_module_n",
            "conflict_n",
            "scope_n (sibling sources)",
            "dialect_unknown_n",
            "dialect_form_n",
        ],
        "top_candidates_preview": [
            {
                "rank": i + 1,
                "machine": r["machine"],
                "project": r["project"],
                "archive_sha256": r["archive_sha256"],
                "complexity_score": float(r["complexity_score"]),
                "configio_n": r["configio_n"],
                "io_claim_n": r["io_claim_n"],
                "eipmodule_n": r["eipmodule_n"],
                "conflict_n": r["conflict_n"],
                "eip_type_diversity": r["eip_type_diversity"],
            }
            for i, r in enumerate(rows[:10])
        ],
        "do_not_switch_after_ugly_result": True,
    }
    path = out_root / "hard_site_selection.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(path), "selected": payload["selected"]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
