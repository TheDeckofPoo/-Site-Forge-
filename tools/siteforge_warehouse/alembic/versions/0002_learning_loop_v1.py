"""Learning Loop V1 — field tests, failures, signatures, AI, shadow eval.

Revision ID: 0002_learning_loop_v1
Revises: 0001_warehouse_v1
Create Date: 2026-09-21

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_learning_loop_v1"
down_revision: Union[str, Sequence[str], None] = "0001_warehouse_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # --- learning.field_tests ---
    op.create_table(
        "field_tests",
        sa.Column("field_test_id", sa.String(length=128), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("git_sha", sa.String(length=64), nullable=False),
        sa.Column("project", sa.String(length=256), nullable=False),
        sa.Column("machine", sa.String(length=256), nullable=False),
        sa.Column("archive_sha", sa.String(length=64), nullable=False),
        sa.Column("raw_physical_candidates", sa.Integer(), nullable=False),
        sa.Column("claims_created", sa.Integer(), nullable=False),
        sa.Column("claims_resolved", sa.Integer(), nullable=False),
        sa.Column("claims_unresolved", sa.Integer(), nullable=False),
        sa.Column("claims_emitted_specialized", sa.Integer(), nullable=False),
        sa.Column("claims_emitted_generic", sa.Integer(), nullable=False),
        sa.Column("claims_muted", sa.Integer(), nullable=False),
        sa.Column("claims_lost", sa.Integer(), nullable=False),
        sa.Column("racks", sa.Integer(), nullable=False),
        sa.Column("modules", sa.Integer(), nullable=False),
        sa.Column("unplaced_modules", sa.Integer(), nullable=False),
        sa.Column("transportation_objects", sa.Integer(), nullable=False),
        sa.Column("transportation_review", sa.Text(), nullable=False),
        sa.Column("safety_devices", sa.Integer(), nullable=False),
        sa.Column("safety_review", sa.Text(), nullable=False),
        sa.Column("build_status", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("artifact_paths", JSON, nullable=False),
        sa.Column("meta", JSON, nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("field_test_id", name=op.f("pk_field_tests")),
        schema="learning",
    )
    op.create_index(
        "ix_field_tests_archive_sha",
        "field_tests",
        ["archive_sha"],
        unique=False,
        schema="learning",
    )
    op.create_index(
        "ix_field_tests_machine",
        "field_tests",
        ["machine"],
        unique=False,
        schema="learning",
    )

    # --- learning.failure_events ---
    op.create_table(
        "failure_events",
        sa.Column("failure_uid", sa.String(length=128), nullable=False),
        sa.Column("field_test_id", sa.String(length=128), nullable=True),
        sa.Column("archive_sha", sa.String(length=64), nullable=False),
        sa.Column("machine", sa.String(length=256), nullable=False),
        sa.Column("subsystem", sa.String(length=64), nullable=False),
        sa.Column("pipeline_stage", sa.String(length=128), nullable=False),
        sa.Column("resolver_rule", sa.String(length=128), nullable=False),
        sa.Column("failure_code", sa.String(length=128), nullable=False),
        sa.Column("signature_id", sa.String(length=128), nullable=False),
        sa.Column("object_identity", sa.String(length=256), nullable=False),
        sa.Column("physical_catalog_family", sa.String(length=128), nullable=False),
        sa.Column("raw_fact_uids", JSON, nullable=False),
        sa.Column("source_scope", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("details", JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("failure_uid", name=op.f("pk_failure_events")),
        schema="learning",
    )
    op.create_index(
        "ix_failure_events_archive_sha",
        "failure_events",
        ["archive_sha"],
        unique=False,
        schema="learning",
    )
    op.create_index(
        "ix_failure_events_machine",
        "failure_events",
        ["machine"],
        unique=False,
        schema="learning",
    )
    op.create_index(
        "ix_failure_events_signature_id",
        "failure_events",
        ["signature_id"],
        unique=False,
        schema="learning",
    )
    op.create_index(
        "ix_failure_events_field_test_id",
        "failure_events",
        ["field_test_id"],
        unique=False,
        schema="learning",
    )
    op.create_index(
        "ix_failure_events_status",
        "failure_events",
        ["status"],
        unique=False,
        schema="learning",
    )

    # --- learning.structural_signatures ---
    op.create_table(
        "structural_signatures",
        sa.Column("signature_id", sa.String(length=128), nullable=False),
        sa.Column("subsystem", sa.String(length=64), nullable=False),
        sa.Column("structural_pattern", sa.Text(), nullable=False),
        sa.Column("pattern_hash", sa.String(length=64), nullable=False),
        sa.Column("dims", JSON, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "signature_id", name=op.f("pk_structural_signatures")
        ),
        schema="learning",
    )

    # --- learning.ai_investigations ---
    op.create_table(
        "ai_investigations",
        sa.Column("investigation_id", sa.String(length=128), nullable=False),
        sa.Column("signature_id", sa.String(length=128), nullable=False),
        sa.Column("cluster_id", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.Column("evidence_fact_uids", JSON, nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("proposed_rule", sa.Text(), nullable=False),
        sa.Column("proposed_guards", JSON, nullable=False),
        sa.Column("contradictions", JSON, nullable=False),
        sa.Column("confidence", sa.String(length=64), nullable=False),
        sa.Column("disposition", sa.String(length=64), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column("meta", JSON, nullable=False),
        sa.PrimaryKeyConstraint(
            "investigation_id", name=op.f("pk_ai_investigations")
        ),
        schema="learning",
    )
    op.create_index(
        "ix_ai_investigations_signature_id",
        "ai_investigations",
        ["signature_id"],
        unique=False,
        schema="learning",
    )

    # --- learning.shadow_evaluations ---
    op.create_table(
        "shadow_evaluations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("investigation_id", sa.String(length=128), nullable=True),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("controllers_applicable", sa.Integer(), nullable=False),
        sa.Column("claims_applicable", sa.Integer(), nullable=False),
        sa.Column("reproduced_resolved", sa.Integer(), nullable=False),
        sa.Column("newly_resolved_estimate", sa.Integer(), nullable=False),
        sa.Column("counterexamples", JSON, nullable=False),
        sa.Column("collisions", JSON, nullable=False),
        sa.Column("source_scope_violations", JSON, nullable=False),
        sa.Column("false_positive_risk", sa.String(length=64), nullable=False),
        sa.Column("details", JSON, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shadow_evaluations")),
        schema="learning",
    )
    op.create_index(
        "ix_shadow_evaluations_investigation_id",
        "shadow_evaluations",
        ["investigation_id"],
        unique=False,
        schema="learning",
    )


def downgrade() -> None:
    op.drop_table("shadow_evaluations", schema="learning")
    op.drop_table("ai_investigations", schema="learning")
    op.drop_table("structural_signatures", schema="learning")
    op.drop_table("failure_events", schema="learning")
    op.drop_table("field_tests", schema="learning")
