"""College Mode V1 — corpus coverage + maturity scorecard (no AI, no promotion).

Reports use LEARNING + VALIDATION archives only (HOLDOUT excluded).
Counts come from live PostgreSQL when configured; never invent semantic classes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from .config import is_postgres_configured
from .holdout import (
    HOLDOUT_FIREWALL_DOC,
    LEARNING_ELIGIBLE_ROLES,
    learning_eligible_archive_filter_sql,
)
from .postgres_repository import make_engine
from .warehouse_health import warehouse_health_snapshot

REPO = Path(__file__).resolve().parents[2]
RESEARCH = REPO / "exports" / "research"

COLLEGE_STAGES = ("FRESHMAN", "SOPHOMORE", "JUNIOR", "SENIOR", "GRADUATE")

# Measurable gates (actual warehouse counts — not invented semantic classes).
_STAGE_GATES: list[tuple[str, dict[str, Any]]] = [
    (
        "FRESHMAN",
        {
            "min_archives_complete": 1,
            "min_controllers": 1,
            "min_roles_assigned_pct": 0,
            "min_rule_candidates": 0,
            "min_field_tests": 0,
            "require_holdout_reserved": False,
            "min_score": 0,
        },
    ),
    (
        "SOPHOMORE",
        {
            "min_archives_complete": 10,
            "min_controllers": 5,
            "min_roles_assigned_pct": 50,
            "min_rule_candidates": 1,
            "min_field_tests": 0,
            "require_holdout_reserved": False,
            "min_score": 25,
        },
    ),
    (
        "JUNIOR",
        {
            "min_archives_complete": 30,
            "min_controllers": 20,
            "min_roles_assigned_pct": 90,
            "min_rule_candidates": 3,
            "min_field_tests": 1,
            "require_holdout_reserved": True,
            "min_score": 45,
        },
    ),
    (
        "SENIOR",
        {
            "min_archives_complete": 50,
            "min_controllers": 40,
            "min_roles_assigned_pct": 95,
            "min_rule_candidates": 5,
            "min_field_tests": 3,
            "require_holdout_reserved": True,
            "min_score": 65,
        },
    ),
    (
        "GRADUATE",
        {
            "min_archives_complete": 80,
            "min_controllers": 60,
            "min_roles_assigned_pct": 99,
            "min_rule_candidates": 8,
            "min_field_tests": 5,
            "require_holdout_reserved": True,
            "min_score": 85,
        },
    ),
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_count(conn: Any, sql: str, params: dict[str, Any] | None = None) -> int | None:
    try:
        return int(conn.execute(text(sql), params or {}).scalar() or 0)
    except Exception:
        conn.rollback()
        return None


def gather_corpus_coverage(*, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Real PG table / role / learning-eligible counts for coverage report."""
    snap = snapshot or warehouse_health_snapshot()
    out: dict[str, Any] = {
        "generated_at": _utcnow(),
        "postgres_configured": is_postgres_configured(),
        "connection": snap.get("connection"),
        "holdout_firewall": HOLDOUT_FIREWALL_DOC,
        "learning_eligible_roles": sorted(LEARNING_ELIGIBLE_ROLES),
        "archives_complete": snap.get("archives_complete"),
        "archives_failed": snap.get("archives_failed"),
        "controllers": snap.get("controllers"),
        "projects": snap.get("projects"),
        "database_size": snap.get("database_size"),
        "alembic_revision": snap.get("alembic_revision"),
        "dataset_roles": dict(snap.get("dataset_roles") or {}),
        "counts": dict(snap.get("counts") or {}),
        "learning_eligible": {},
        "unsupported_semantic_classes": [],
        "note": (
            "Coverage uses warehouse table counts and dataset_role only. "
            "No invented purpose / dialect / activity semantic classes."
        ),
    }

    if snap.get("connection") != "CONNECTED" or not is_postgres_configured():
        out["error"] = snap.get("error") or "POSTGRESQL_NOT_CONFIGURED"
        return out

    eng = make_engine()
    if eng is None:
        out["error"] = "engine_null"
        return out

    filt = learning_eligible_archive_filter_sql("a.dataset_role")
    with eng.connect() as c:
        out["learning_eligible"] = {
            "archives": _safe_count(
                c,
                f"SELECT COUNT(*) FROM corpus.archives a "
                f"WHERE a.complete IS TRUE AND {filt}",
            ),
            "controllers": _safe_count(
                c,
                f"SELECT COUNT(DISTINCT a.machine) FROM corpus.archives a "
                f"WHERE a.complete IS TRUE AND a.machine <> '' AND {filt}",
            ),
            "projects": _safe_count(
                c,
                f"SELECT COUNT(DISTINCT a.project) FROM corpus.archives a "
                f"WHERE a.complete IS TRUE AND a.project <> '' AND {filt}",
            ),
            "configio_rows": _safe_count(
                c,
                f"SELECT COUNT(*) FROM evidence.configio_rows e "
                f"JOIN corpus.archives a ON a.archive_sha256 = e.archive_sha256 "
                f"WHERE a.complete IS TRUE AND {filt}",
            ),
            "io_claims": _safe_count(
                c,
                f"SELECT COUNT(*) FROM evidence.io_claims e "
                f"JOIN corpus.archives a ON a.archive_sha256 = e.archive_sha256 "
                f"WHERE a.complete IS TRUE AND {filt}",
            ),
            "eipmodules": _safe_count(
                c,
                f"SELECT COUNT(*) FROM evidence.eipmodules e "
                f"JOIN corpus.archives a ON a.archive_sha256 = e.archive_sha256 "
                f"WHERE a.complete IS TRUE AND {filt}",
            ),
        }

        # Optional rule-reuse / unknown-cluster summaries (learning schema only)
        out["rule_candidates"] = {
            "total": _safe_count(c, "SELECT COUNT(*) FROM learning.rule_candidates"),
            "by_status": {},
        }
        try:
            rows = c.execute(
                text(
                    "SELECT status, COUNT(*) AS n FROM learning.rule_candidates "
                    "GROUP BY status ORDER BY n DESC"
                )
            ).mappings().all()
            out["rule_candidates"]["by_status"] = {
                str(r["status"]): int(r["n"]) for r in rows
            }
        except Exception:
            c.rollback()

        out["unknown_clusters"] = {
            "total": _safe_count(c, "SELECT COUNT(*) FROM learning.unknown_clusters"),
        }
        try:
            clusters = c.execute(
                text(
                    "SELECT cluster_id, count, pattern_hash "
                    "FROM learning.unknown_clusters "
                    "ORDER BY count DESC NULLS LAST LIMIT 25"
                )
            ).mappings().all()
            out["unknown_clusters"]["top"] = [dict(r) for r in clusters]
        except Exception:
            c.rollback()
            out["unknown_clusters"]["top"] = []

        # I/O conservation-style warehouse facts (counts only — no decoder claims)
        out["io_conservation_summary"] = {
            "learning_eligible_configio_rows": out["learning_eligible"].get(
                "configio_rows"
            ),
            "learning_eligible_io_claims": out["learning_eligible"].get("io_claims"),
            "learning_eligible_eipmodules": out["learning_eligible"].get("eipmodules"),
            "note": (
                "Warehouse row counts for LEARNING+VALIDATION only; "
                "not a per-site conservation ledger."
            ),
        }

        roles = out["dataset_roles"]
        assigned = sum(
            int(roles.get(r) or 0) for r in ("LEARNING", "VALIDATION", "HOLDOUT")
        )
        # Denominator = all archive rows (complete + failed), not complete-only
        total_arch = sum(int(v or 0) for v in roles.values()) or int(
            (out.get("counts") or {}).get("corpus.archives")
            or snap.get("archives_complete")
            or 0
        )
        out["roles_assigned"] = assigned
        out["roles_total_archives"] = total_arch
        out["roles_assigned_pct"] = (
            round(100.0 * assigned / total_arch, 2) if total_arch else 0.0
        )

    return out


def _clamp(n: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, n))


def compute_college_scorecard(
    coverage: dict[str, Any] | None = None,
    *,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Measurable College Mode stage from real warehouse counts."""
    cov = coverage or gather_corpus_coverage(snapshot=snapshot)
    snap = snapshot or {}
    if not snap and is_postgres_configured():
        snap = warehouse_health_snapshot()

    roles = dict(cov.get("dataset_roles") or snap.get("dataset_roles") or {})
    archives = int(cov.get("archives_complete") or snap.get("archives_complete") or 0)
    controllers = int(cov.get("controllers") or snap.get("controllers") or 0)
    projects = int(cov.get("projects") or snap.get("projects") or 0)
    holdout_n = int(roles.get("HOLDOUT") or 0)
    learning_n = int(roles.get("LEARNING") or 0)
    validation_n = int(roles.get("VALIDATION") or 0)
    unassigned_n = int(roles.get("UNASSIGNED") or 0)
    assigned = learning_n + validation_n + holdout_n
    role_total = sum(int(v or 0) for v in roles.values()) or archives
    assigned_pct = float(cov.get("roles_assigned_pct") or 0.0)
    if not assigned_pct and role_total:
        assigned_pct = 100.0 * assigned / role_total

    counts = dict(cov.get("counts") or snap.get("counts") or {})
    rule_n = int(
        (cov.get("rule_candidates") or {}).get("total")
        if (cov.get("rule_candidates") or {}).get("total") is not None
        else (counts.get("learning.rule_candidates") or 0)
    )
    field_tests = int(counts.get("learning.field_tests") or 0)
    unknown_n = int(
        (cov.get("unknown_clusters") or {}).get("total")
        if (cov.get("unknown_clusters") or {}).get("total") is not None
        else (counts.get("learning.unknown_clusters") or 0)
    )
    shadow_n = int(counts.get("learning.shadow_evaluations") or 0)
    ai_cost = float(snap.get("ai_total_recorded_cost_usd") or 0.0)

    le = cov.get("learning_eligible") or {}
    le_archives = int(le.get("archives") or 0)

    # Component scores 0–100 from measurable counts
    components = {
        "archives": round(_clamp(archives / 80.0 * 100.0), 2),
        "controllers": round(_clamp(controllers / 60.0 * 100.0), 2),
        "roles_assigned_pct": round(_clamp(assigned_pct), 2),
        "learning_validation_split": round(
            _clamp(
                (100.0 if (learning_n > 0 and validation_n > 0) else 0.0)
                + min(40.0, learning_n / 2.0)
                + min(20.0, validation_n * 5.0)
            ),
            2,
        ),
        "holdout_reserved": 100.0 if holdout_n > 0 else 0.0,
        "rule_candidates": round(_clamp(rule_n / 8.0 * 100.0), 2),
        "field_tests": round(_clamp(field_tests / 5.0 * 100.0), 2),
        "unknown_clusters_tracked": round(_clamp(unknown_n / 8.0 * 100.0), 2),
        "shadow_evaluations": round(_clamp(shadow_n / 3.0 * 100.0), 2),
        "ai_spend_discipline": 100.0 if ai_cost <= 0.0 else round(_clamp(100.0 - ai_cost * 50.0), 2),
    }
    weights = {
        "archives": 0.18,
        "controllers": 0.12,
        "roles_assigned_pct": 0.15,
        "learning_validation_split": 0.12,
        "holdout_reserved": 0.10,
        "rule_candidates": 0.12,
        "field_tests": 0.08,
        "unknown_clusters_tracked": 0.05,
        "shadow_evaluations": 0.04,
        "ai_spend_discipline": 0.04,
    }
    score = round(
        sum(components[k] * weights[k] for k in weights),
        2,
    )

    metrics_for_gates = {
        "archives_complete": archives,
        "controllers": controllers,
        "roles_assigned_pct": assigned_pct,
        "rule_candidates": rule_n,
        "field_tests": field_tests,
        "holdout_reserved": holdout_n > 0,
        "score": score,
    }

    stage = "FRESHMAN"
    stage_checks: dict[str, Any] = {}
    for name, gates in _STAGE_GATES:
        checks = {
            "archives_complete": archives >= int(gates["min_archives_complete"]),
            "controllers": controllers >= int(gates["min_controllers"]),
            "roles_assigned_pct": assigned_pct
            >= float(gates["min_roles_assigned_pct"]),
            "rule_candidates": rule_n >= int(gates["min_rule_candidates"]),
            "field_tests": field_tests >= int(gates["min_field_tests"]),
            "holdout_reserved": (
                (holdout_n > 0)
                if gates["require_holdout_reserved"]
                else True
            ),
            "score": score >= float(gates["min_score"]),
        }
        stage_checks[name] = {"gates": gates, "checks": checks, "passed": all(checks.values())}
        if all(checks.values()):
            stage = name

    return {
        "generated_at": _utcnow(),
        "stage": stage,
        "stages": list(COLLEGE_STAGES),
        "score": score,
        "components": components,
        "weights": weights,
        "metrics": {
            "archives_complete": archives,
            "controllers": controllers,
            "projects": projects,
            "dataset_roles": roles,
            "roles_assigned": assigned,
            "roles_unassigned": unassigned_n,
            "roles_assigned_pct": round(assigned_pct, 2),
            "learning_eligible_archives": le_archives,
            "rule_candidates": rule_n,
            "field_tests": field_tests,
            "unknown_clusters": unknown_n,
            "shadow_evaluations": shadow_n,
            "ai_total_recorded_cost_usd": ai_cost,
            "holdout_count": holdout_n,
        },
        "stage_checks": stage_checks,
        "holdout_firewall": HOLDOUT_FIREWALL_DOC,
        "connection": cov.get("connection") or snap.get("connection"),
        "alembic_revision": cov.get("alembic_revision") or snap.get("alembic_revision"),
        "database_size": cov.get("database_size") or snap.get("database_size"),
    }


def write_corpus_coverage_report(
    coverage: dict[str, Any] | None = None,
) -> dict[str, Path]:
    cov = coverage or gather_corpus_coverage()
    RESEARCH.mkdir(parents=True, exist_ok=True)
    jp = RESEARCH / "corpus_coverage_report.json"
    mp = RESEARCH / "CORPUS_COVERAGE_REPORT.md"
    jp.write_text(json.dumps(cov, indent=2, default=str), encoding="utf-8")

    roles = cov.get("dataset_roles") or {}
    le = cov.get("learning_eligible") or {}
    lines = [
        "# Corpus Coverage Report",
        "",
        f"Generated: {cov.get('generated_at')}",
        "",
        f"- Connection: **{cov.get('connection')}**",
        f"- Alembic: `{cov.get('alembic_revision')}`",
        f"- Database size: **{cov.get('database_size')}**",
        f"- Archives complete: {cov.get('archives_complete')} (failed {cov.get('archives_failed')})",
        f"- Controllers: {cov.get('controllers')} · Projects: {cov.get('projects')}",
        f"- Roles assigned: {cov.get('roles_assigned')} ({cov.get('roles_assigned_pct')}%)",
        "",
        "## Dataset roles",
        "",
    ]
    for k in ("LEARNING", "VALIDATION", "HOLDOUT", "UNASSIGNED"):
        if k in roles:
            lines.append(f"- {k}: {roles[k]}")
    for k, v in sorted(roles.items()):
        if k not in ("LEARNING", "VALIDATION", "HOLDOUT", "UNASSIGNED"):
            lines.append(f"- {k}: {v}")

    lines += [
        "",
        "## Learning-eligible (LEARNING + VALIDATION only)",
        "",
        f"_{HOLDOUT_FIREWALL_DOC}_",
        "",
    ]
    for k, v in le.items():
        lines.append(f"- `{k}`: {v}")

    lines += ["", "## Warehouse table counts", ""]
    for k, v in (cov.get("counts") or {}).items():
        lines.append(f"- `{k}`: {v}")

    rc = cov.get("rule_candidates") or {}
    lines += ["", "## Rule candidates", "", f"- total: {rc.get('total')}"]
    for st, n in (rc.get("by_status") or {}).items():
        lines.append(f"- `{st}`: {n}")

    uc = cov.get("unknown_clusters") or {}
    lines += ["", "## Unknown clusters", "", f"- total: {uc.get('total')}", ""]
    for row in uc.get("top") or []:
        lines.append(
            f"- `{row.get('cluster_id')}` count={row.get('count')} "
            f"pattern={row.get('pattern_hash')}"
        )

    io_sum = cov.get("io_conservation_summary") or {}
    lines += [
        "",
        "## I/O conservation summary (warehouse counts)",
        "",
        f"- learning_eligible_configio_rows: {io_sum.get('learning_eligible_configio_rows')}",
        f"- learning_eligible_io_claims: {io_sum.get('learning_eligible_io_claims')}",
        f"- learning_eligible_eipmodules: {io_sum.get('learning_eligible_eipmodules')}",
        f"- note: {io_sum.get('note')}",
        "",
        "## Notes",
        "",
        cov.get("note") or "",
        "",
    ]
    mp.write_text("\n".join(lines), encoding="utf-8")
    return {"json": jp, "md": mp}


def write_college_status_report(
    scorecard: dict[str, Any] | None = None,
    *,
    coverage: dict[str, Any] | None = None,
) -> dict[str, Path]:
    card = scorecard or compute_college_scorecard(coverage)
    RESEARCH.mkdir(parents=True, exist_ok=True)
    jp = RESEARCH / "siteforge_college_status.json"
    mp = RESEARCH / "SITEFORGE_COLLEGE_STATUS.md"
    jp.write_text(json.dumps(card, indent=2, default=str), encoding="utf-8")

    m = card.get("metrics") or {}
    lines = [
        "# Site Forge College Status",
        "",
        f"Generated: {card.get('generated_at')}",
        "",
        f"## Stage: **{card.get('stage')}** (score {card.get('score')}/100)",
        "",
        f"- Connection: {card.get('connection')}",
        f"- Alembic: `{card.get('alembic_revision')}`",
        f"- Database size: **{card.get('database_size')}**",
        "",
        "## Metrics",
        "",
        f"- Archives complete: {m.get('archives_complete')}",
        f"- Controllers: {m.get('controllers')} · Projects: {m.get('projects')}",
        f"- Roles assigned: {m.get('roles_assigned')} ({m.get('roles_assigned_pct')}%) "
        f"/ unassigned {m.get('roles_unassigned')}",
        f"- Dataset roles: `{m.get('dataset_roles')}`",
        f"- Learning-eligible archives: {m.get('learning_eligible_archives')}",
        f"- Rule candidates: {m.get('rule_candidates')}",
        f"- Field tests: {m.get('field_tests')}",
        f"- Unknown clusters: {m.get('unknown_clusters')}",
        f"- Shadow evaluations: {m.get('shadow_evaluations')}",
        f"- Holdout reserved: {m.get('holdout_count')}",
        f"- AI recorded cost: ${m.get('ai_total_recorded_cost_usd', 0):.2f}",
        "",
        "## Component scores",
        "",
    ]
    for k, v in (card.get("components") or {}).items():
        w = (card.get("weights") or {}).get(k)
        lines.append(f"- `{k}`: {v} (weight {w})")

    lines += ["", "## Stage gates", ""]
    for name in COLLEGE_STAGES:
        info = (card.get("stage_checks") or {}).get(name) or {}
        mark = "PASS" if info.get("passed") else "FAIL"
        lines.append(f"### {name} — {mark}")
        for ck, ok in (info.get("checks") or {}).items():
            lines.append(f"- {ck}: {'yes' if ok else 'no'}")
        lines.append("")

    lines += [
        "## Holdout firewall",
        "",
        HOLDOUT_FIREWALL_DOC,
        "",
    ]
    mp.write_text("\n".join(lines), encoding="utf-8")
    return {"json": jp, "md": mp}


def write_college_reports(
    *,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write coverage + college scorecard reports under exports/research/."""
    snap = snapshot or warehouse_health_snapshot()
    cov = gather_corpus_coverage(snapshot=snap)
    card = compute_college_scorecard(cov, snapshot=snap)
    cov_paths = write_corpus_coverage_report(cov)
    college_paths = write_college_status_report(card, coverage=cov)
    return {
        "coverage": cov,
        "college": card,
        "paths": {
            "corpus_coverage_json": cov_paths["json"],
            "corpus_coverage_md": cov_paths["md"],
            "college_status_json": college_paths["json"],
            "college_status_md": college_paths["md"],
        },
    }


def apply_dataset_roles(
    *,
    fill_unassigned_only: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """Assign dataset_role for archives in PostgreSQL.

    Default respects existing non-UNASSIGNED roles (manual / prior overrides).
    When fill_unassigned_only is False, recomputes every archive from SHA.
    """
    from .warehouse_health import assign_dataset_role

    if not is_postgres_configured():
        return {"error": "POSTGRESQL_NOT_CONFIGURED", "updated": 0}
    eng = make_engine()
    if eng is None:
        return {"error": "engine_null", "updated": 0}

    updated = 0
    skipped = 0
    by_role: dict[str, int] = {}
    samples: list[dict[str, str]] = []

    with eng.connect() as c:
        if fill_unassigned_only:
            sql = (
                "SELECT archive_sha256, dataset_role FROM corpus.archives "
                "WHERE dataset_role IS NULL OR dataset_role = '' "
                "OR upper(dataset_role) = 'UNASSIGNED' "
                "ORDER BY archive_sha256"
            )
        else:
            sql = (
                "SELECT archive_sha256, dataset_role FROM corpus.archives "
                "ORDER BY archive_sha256"
            )
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        rows = c.execute(text(sql)).mappings().all()
        for row in rows:
            sha = str(row["archive_sha256"])
            current = (row["dataset_role"] or "").strip().upper() or "UNASSIGNED"
            if fill_unassigned_only and current not in ("", "UNASSIGNED"):
                skipped += 1
                continue
            role = assign_dataset_role(sha)
            c.execute(
                text(
                    "UPDATE corpus.archives SET dataset_role = :r "
                    "WHERE archive_sha256 = :s"
                ),
                {"r": role, "s": sha},
            )
            updated += 1
            by_role[role] = by_role.get(role, 0) + 1
            if len(samples) < 10:
                samples.append(
                    {"archive_sha256": sha, "from": current, "to": role}
                )
        c.commit()

        # Final distribution
        dist_rows = c.execute(
            text(
                "SELECT COALESCE(dataset_role, 'UNASSIGNED') AS role, COUNT(*) AS n "
                "FROM corpus.archives GROUP BY 1 ORDER BY 2 DESC"
            )
        ).mappings().all()
        distribution = {r["role"]: int(r["n"]) for r in dist_rows}

    return {
        "updated": updated,
        "skipped": skipped,
        "fill_unassigned_only": fill_unassigned_only,
        "assigned_this_run": by_role,
        "distribution": distribution,
        "samples": samples,
    }


def ensure_archive_dataset_role(archive_sha: str, *, session: Any = None) -> str:
    """Assign role if missing/UNASSIGNED. Preserves existing LEARNING/VALIDATION/HOLDOUT."""
    from .ids import normalize_archive_sha256
    from .models import Archive
    from .warehouse_health import assign_dataset_role

    sha = normalize_archive_sha256(archive_sha)
    role = assign_dataset_role(sha)

    if session is not None:
        arch = session.get(Archive, sha)
        if arch is None:
            return role
        current = (arch.dataset_role or "").strip().upper()
        if current in ("", "UNASSIGNED"):
            arch.dataset_role = role
            return role
        return current

    if not is_postgres_configured():
        return role
    eng = make_engine()
    if eng is None:
        return role
    with eng.connect() as c:
        row = c.execute(
            text(
                "SELECT dataset_role FROM corpus.archives WHERE archive_sha256 = :s"
            ),
            {"s": sha},
        ).first()
        if row is None:
            return role
        current = (row[0] or "").strip().upper() or "UNASSIGNED"
        if current not in ("", "UNASSIGNED"):
            return current
        c.execute(
            text(
                "UPDATE corpus.archives SET dataset_role = :r "
                "WHERE archive_sha256 = :s "
                "AND (dataset_role IS NULL OR dataset_role = '' "
                "OR upper(dataset_role) = 'UNASSIGNED')"
            ),
            {"r": role, "s": sha},
        )
        c.commit()
    return role


__all__ = [
    "COLLEGE_STAGES",
    "apply_dataset_roles",
    "compute_college_scorecard",
    "ensure_archive_dataset_role",
    "gather_corpus_coverage",
    "write_college_reports",
    "write_college_status_report",
    "write_corpus_coverage_report",
]
