"""Holdout firewall — HOLDOUT archives must not feed learning pipelines.

HOLDOUT may be stored in the warehouse for reserved virgin / future evaluation,
but must not feed:
  - rule discovery
  - structural derivation
  - AI dossiers
  - counterexamples
  - decoder decisions
  - production promotion justification

Learning-eligible roles are LEARNING and VALIDATION only.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

HOLDOUT_ROLE = "HOLDOUT"
LEARNING_ELIGIBLE_ROLES = frozenset({"LEARNING", "VALIDATION"})
ALL_DATASET_ROLES = frozenset({"LEARNING", "VALIDATION", "HOLDOUT", "UNASSIGNED"})

HOLDOUT_FIREWALL_DOC = (
    "HOLDOUT may be stored but must not feed rule discovery / structural "
    "derivation / AI dossiers / counterexamples / decoder decisions / "
    "production promotion justification."
)


def is_learning_eligible_role(role: str | None) -> bool:
    """True when role is LEARNING or VALIDATION (not HOLDOUT / UNASSIGNED / null)."""
    return (role or "").strip().upper() in LEARNING_ELIGIBLE_ROLES


def is_holdout_role(role: str | None) -> bool:
    return (role or "").strip().upper() == HOLDOUT_ROLE


def learning_eligible_archive_filter_sql(
    column: str = "dataset_role",
    *,
    table_alias: str | None = None,
) -> str:
    """SQL predicate excluding HOLDOUT (and requiring LEARNING|VALIDATION).

    Use in WHERE clauses for rule discovery / coverage / college reports.
    Example: ``WHERE complete IS TRUE AND {learning_eligible_archive_filter_sql()}``
    """
    col = f"{table_alias}.{column}" if table_alias else column
    roles = ", ".join(f"'{r}'" for r in sorted(LEARNING_ELIGIBLE_ROLES))
    return f"({col} IN ({roles}))"


def learning_eligible_archive_filter(
    rows: Iterable[Mapping[str, Any]],
    *,
    role_key: str = "dataset_role",
) -> list[dict[str, Any]]:
    """Python helper: keep only LEARNING/VALIDATION rows (exclude HOLDOUT)."""
    out: list[dict[str, Any]] = []
    for row in rows:
        role = row.get(role_key) if isinstance(row, Mapping) else None
        if is_learning_eligible_role(role if isinstance(role, str) else None):
            out.append(dict(row))
    return out


def assert_no_holdout_in_learning_query(
    rows: Sequence[Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    *,
    role_key: str = "dataset_role",
) -> None:
    """Raise AssertionError if any row carries HOLDOUT — for tests / guards."""
    bad: list[Any] = []
    for row in rows:
        role = row.get(role_key) if isinstance(row, Mapping) else None
        if is_holdout_role(role if isinstance(role, str) else None):
            bad.append(row.get("archive_sha256") or row)
    if bad:
        raise AssertionError(
            f"HOLDOUT leaked into learning query ({len(bad)} row(s)): "
            f"{bad[:5]!r}. {HOLDOUT_FIREWALL_DOC}"
        )


__all__ = [
    "ALL_DATASET_ROLES",
    "HOLDOUT_FIREWALL_DOC",
    "HOLDOUT_ROLE",
    "LEARNING_ELIGIBLE_ROLES",
    "assert_no_holdout_in_learning_query",
    "is_holdout_role",
    "is_learning_eligible_role",
    "learning_eligible_archive_filter",
    "learning_eligible_archive_filter_sql",
]
