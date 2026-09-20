"""Warehouse V1 foundation — Stage-1 schemas and tables.

Revision ID: 0001_warehouse_v1
Revises:
Create Date: 2026-09-20

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_warehouse_v1"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMAS = (
    "siteforge_meta",
    "corpus",
    "evidence",
    "learning",
    "qualification",
    "app",
)

JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))

    # --- siteforge_meta ---
    op.create_table(
        "schema_info",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schema_info")),
        sa.UniqueConstraint("key", name=op.f("uq_schema_info_key")),
        schema="siteforge_meta",
    )
    op.create_table(
        "extractor_versions",
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("version", name=op.f("pk_extractor_versions")),
        schema="siteforge_meta",
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("roots", JSON, nullable=False),
        sa.Column("plan_summary", JSON, nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_runs")),
        schema="siteforge_meta",
    )

    # --- corpus ---
    op.create_table(
        "archives",
        sa.Column("archive_sha256", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("archive_class", sa.String(length=64), nullable=False),
        sa.Column("discovered_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("project", sa.String(length=256), nullable=False),
        sa.Column("site", sa.String(length=256), nullable=False),
        sa.Column("machine", sa.String(length=256), nullable=False),
        sa.Column("timestamp_token", sa.String(length=64), nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("sync_status", sa.String(length=32), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("tables_present", JSON, nullable=False),
        sa.Column("notes", JSON, nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("archive_sha256", name=op.f("pk_archives")),
        schema="corpus",
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project", sa.String(length=256), nullable=False),
        sa.Column("site", sa.String(length=256), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("project", "site", name="uq_projects_project_site"),
        schema="corpus",
    )
    op.create_table(
        "controllers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("archive_sha256", sa.String(length=64), nullable=False),
        sa.Column("project", sa.String(length=256), nullable=False),
        sa.Column("machine", sa.String(length=256), nullable=False),
        sa.Column("role_hints", JSON, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_controllers")),
        sa.UniqueConstraint(
            "archive_sha256", "machine", name="uq_controllers_archive_machine"
        ),
        schema="corpus",
    )
    op.create_index(
        "ix_controllers_archive_sha256",
        "controllers",
        ["archive_sha256"],
        unique=False,
        schema="corpus",
    )
    op.create_table(
        "source_files",
        sa.Column("fact_uid", sa.String(length=48), nullable=False),
        sa.Column("archive_sha256", sa.String(length=64), nullable=False),
        sa.Column("project", sa.String(length=256), nullable=False),
        sa.Column("machine", sa.String(length=256), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_row_index", sa.Integer(), nullable=False),
        sa.Column("machine_scope", sa.String(length=64), nullable=False),
        sa.Column("evidence_class", sa.String(length=64), nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("notes", JSON, nullable=False),
        sa.PrimaryKeyConstraint("fact_uid", name=op.f("pk_source_files")),
        schema="corpus",
    )
    op.create_index(
        "ix_source_files_archive_sha256",
        "source_files",
        ["archive_sha256"],
        unique=False,
        schema="corpus",
    )

    # --- evidence tables (shared birth-certificate columns) ---
    def _bc():
        return [
            sa.Column("fact_uid", sa.String(length=48), nullable=False),
            sa.Column("archive_sha256", sa.String(length=64), nullable=False),
            sa.Column("project", sa.String(length=256), nullable=False),
            sa.Column("machine", sa.String(length=256), nullable=False),
            sa.Column("source_path", sa.Text(), nullable=False),
            sa.Column("source_row_index", sa.Integer(), nullable=False),
            sa.Column("machine_scope", sa.String(length=64), nullable=False),
            sa.Column("evidence_class", sa.String(length=64), nullable=False),
            sa.Column("extractor_version", sa.String(length=64), nullable=False),
        ]

    def _evidence_indexes(table: str) -> None:
        op.create_index(
            f"ix_{table}_archive_sha256",
            table,
            ["archive_sha256"],
            unique=False,
            schema="evidence",
        )
        op.create_index(
            f"ix_{table}_machine",
            table,
            ["machine"],
            unique=False,
            schema="evidence",
        )

    op.create_table(
        "configio_rows",
        *_bc(),
        sa.Column("octal_word", sa.String(length=32), nullable=False),
        sa.Column("bank", sa.String(length=32), nullable=False),
        sa.Column("lohi", sa.String(length=32), nullable=False),
        sa.Column("in_out", sa.String(length=32), nullable=False),
        sa.Column("desc", sa.Text(), nullable=False),
        sa.Column("interface", sa.String(length=128), nullable=False),
        sa.Column("i_o_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("process", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("purpose_meta", JSON, nullable=False),
        sa.Column("dialect_form", sa.String(length=64), nullable=False),
        sa.Column("dialect_meta", JSON, nullable=False),
        sa.Column("raw_fields", JSON, nullable=False),
        sa.PrimaryKeyConstraint("fact_uid", name=op.f("pk_configio_rows")),
        schema="evidence",
    )
    _evidence_indexes("configio_rows")

    op.create_table(
        "eipmodules",
        *_bc(),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("adapter", sa.String(length=256), nullable=False),
        sa.Column("type", sa.String(length=128), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("connection", sa.String(length=64), nullable=False),
        sa.Column("input_bank", sa.Integer(), nullable=False),
        sa.Column("output_bank", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("raw_fields", JSON, nullable=False),
        sa.PrimaryKeyConstraint("fact_uid", name=op.f("pk_eipmodules")),
        schema="evidence",
    )
    _evidence_indexes("eipmodules")

    op.create_table(
        "eipadapters",
        *_bc(),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("target_ip", sa.String(length=64), nullable=False),
        sa.Column("rack", sa.String(length=64), nullable=False),
        sa.Column("raw_fields", JSON, nullable=False),
        sa.PrimaryKeyConstraint("fact_uid", name=op.f("pk_eipadapters")),
        schema="evidence",
    )
    _evidence_indexes("eipadapters")

    op.create_table(
        "eipmodule_types",
        *_bc(),
        sa.Column("type_name", sa.String(length=128), nullable=False),
        sa.Column("raw_fields", JSON, nullable=False),
        sa.PrimaryKeyConstraint("fact_uid", name=op.f("pk_eipmodule_types")),
        schema="evidence",
    )
    _evidence_indexes("eipmodule_types")

    op.create_table(
        "eipcfg_adapters",
        *_bc(),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("targetip", sa.String(length=64), nullable=False),
        sa.Column("input_address", sa.String(length=64), nullable=False),
        sa.Column("output_address", sa.String(length=64), nullable=False),
        sa.Column("raw_fields", JSON, nullable=False),
        sa.PrimaryKeyConstraint("fact_uid", name=op.f("pk_eipcfg_adapters")),
        schema="evidence",
    )
    _evidence_indexes("eipcfg_adapters")

    op.create_table(
        "eipcfg_modules",
        *_bc(),
        sa.Column("adapter", sa.String(length=256), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("connection", sa.String(length=64), nullable=False),
        sa.Column("raw_fields", JSON, nullable=False),
        sa.PrimaryKeyConstraint("fact_uid", name=op.f("pk_eipcfg_modules")),
        schema="evidence",
    )
    _evidence_indexes("eipcfg_modules")

    op.create_table(
        "io_claims",
        *_bc(),
        sa.Column("io_name", sa.String(length=256), nullable=False),
        sa.Column("fortna_word", sa.String(length=32), nullable=False),
        sa.Column("fortna_bit", sa.String(length=32), nullable=False),
        sa.Column("word", sa.Integer(), nullable=True),
        sa.Column("device_type", sa.String(length=64), nullable=False),
        sa.Column("raw_fields", JSON, nullable=False),
        sa.PrimaryKeyConstraint("fact_uid", name=op.f("pk_io_claims")),
        schema="evidence",
    )
    _evidence_indexes("io_claims")

    op.create_table(
        "conflicts",
        *_bc(),
        sa.Column("conflict_kind", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", JSON, nullable=False),
        sa.PrimaryKeyConstraint("fact_uid", name=op.f("pk_conflicts")),
        schema="evidence",
    )
    _evidence_indexes("conflicts")

    op.create_table(
        "machine_source_scopes",
        *_bc(),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("source_machine_inferred", sa.String(length=256), nullable=False),
        sa.Column("notes", JSON, nullable=False),
        sa.PrimaryKeyConstraint("fact_uid", name=op.f("pk_machine_source_scopes")),
        schema="evidence",
    )
    _evidence_indexes("machine_source_scopes")

    op.create_table(
        "adapter_bridges",
        *_bc(),
        sa.Column("eipmodules_adapter_name", sa.String(length=256), nullable=False),
        sa.Column("eipadapters_name", sa.String(length=256), nullable=False),
        sa.Column("target_ip", sa.String(length=64), nullable=False),
        sa.Column("eipcfg_adapter_name", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("details", JSON, nullable=False),
        sa.PrimaryKeyConstraint("fact_uid", name=op.f("pk_adapter_bridges")),
        schema="evidence",
    )
    _evidence_indexes("adapter_bridges")

    # --- learning ---
    op.create_table(
        "dialect_observations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("form", sa.String(length=64), nullable=False),
        sa.Column("structural_pattern_hash", sa.String(length=64), nullable=False),
        sa.Column("archive_sha256", sa.String(length=64), nullable=False),
        sa.Column("machine", sa.String(length=256), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("example_raw", sa.Text(), nullable=False),
        sa.Column("evidence_class", sa.String(length=64), nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("meta", JSON, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dialect_observations")),
        schema="learning",
    )
    op.create_index(
        "ix_dialect_observations_form",
        "dialect_observations",
        ["form"],
        unique=False,
        schema="learning",
    )
    op.create_table(
        "unknown_clusters",
        sa.Column("cluster_id", sa.String(length=128), nullable=False),
        sa.Column("pattern_hash", sa.String(length=64), nullable=False),
        sa.Column("structural_pattern", sa.Text(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("example_raw", JSON, nullable=False),
        sa.Column("archives", JSON, nullable=False),
        sa.Column("machines", JSON, nullable=False),
        sa.Column("fields", JSON, nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("cluster_id", name=op.f("pk_unknown_clusters")),
        schema="learning",
    )
    op.create_table(
        "rule_candidates",
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("production_auto_promote", sa.Boolean(), nullable=False),
        sa.Column("related_forms", JSON, nullable=False),
        sa.Column("related_modules", JSON, nullable=False),
        sa.Column("evidence_tests", JSON, nullable=False),
        sa.Column("honesty_notes", JSON, nullable=False),
        sa.Column("meta", JSON, nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("rule_id", name=op.f("pk_rule_candidates")),
        schema="learning",
    )
    op.create_table(
        "rule_coverage",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("archive_sha256", sa.String(length=64), nullable=False),
        sa.Column("machine", sa.String(length=256), nullable=False),
        sa.Column("cell_status", sa.String(length=64), nullable=False),
        sa.Column("details", JSON, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_coverage")),
        sa.UniqueConstraint(
            "rule_id", "archive_sha256", "machine", name="uq_rule_coverage_cell"
        ),
        schema="learning",
    )
    op.create_index(
        "ix_rule_coverage_rule_id",
        "rule_coverage",
        ["rule_id"],
        unique=False,
        schema="learning",
    )
    op.create_table(
        "rule_counterexamples",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("archive_sha256", sa.String(length=64), nullable=False),
        sa.Column("machine", sa.String(length=256), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", JSON, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_counterexamples")),
        schema="learning",
    )
    op.create_index(
        "ix_rule_counterexamples_rule_id",
        "rule_counterexamples",
        ["rule_id"],
        unique=False,
        schema="learning",
    )
    op.create_table(
        "investigation_sessions",
        sa.Column("investigation_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", JSON, nullable=False),
        sa.PrimaryKeyConstraint(
            "investigation_id", name=op.f("pk_investigation_sessions")
        ),
        schema="learning",
    )
    op.create_table(
        "provenance_edges",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("from_id", sa.String(length=128), nullable=False),
        sa.Column("to_id", sa.String(length=128), nullable=False),
        sa.Column("relation", sa.String(length=64), nullable=False),
        sa.Column("evidence_class", sa.String(length=64), nullable=False),
        sa.Column("archive_sha256", sa.String(length=64), nullable=False),
        sa.Column("meta", JSON, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provenance_edges")),
        schema="learning",
    )
    op.create_index(
        "ix_provenance_edges_from_id",
        "provenance_edges",
        ["from_id"],
        unique=False,
        schema="learning",
    )
    op.create_index(
        "ix_provenance_edges_to_id",
        "provenance_edges",
        ["to_id"],
        unique=False,
        schema="learning",
    )

    # --- qualification ---
    op.create_table(
        "qualification_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_key", sa.String(length=128), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("meta", JSON, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qualification_runs")),
        sa.UniqueConstraint("run_key", name=op.f("uq_qualification_runs_run_key")),
        schema="qualification",
    )
    op.create_table(
        "qualification_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_key", sa.String(length=128), nullable=False),
        sa.Column("check_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("details", JSON, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qualification_results")),
        schema="qualification",
    )
    op.create_index(
        "ix_qualification_results_run_key",
        "qualification_results",
        ["run_key"],
        unique=False,
        schema="qualification",
    )

    # --- app ---
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", JSON, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_settings")),
        schema="app",
    )

    # Seed schema_info
    op.execute(
        sa.text(
            "INSERT INTO siteforge_meta.schema_info (key, value) "
            "VALUES ('warehouse_stage', 'v1_foundation'), "
            "('extractor_version', 'warehouse_hw_io_v1.0.0')"
        )
    )


def downgrade() -> None:
    op.drop_table("settings", schema="app")
    op.drop_table("qualification_results", schema="qualification")
    op.drop_table("qualification_runs", schema="qualification")
    op.drop_table("provenance_edges", schema="learning")
    op.drop_table("investigation_sessions", schema="learning")
    op.drop_table("rule_counterexamples", schema="learning")
    op.drop_table("rule_coverage", schema="learning")
    op.drop_table("rule_candidates", schema="learning")
    op.drop_table("unknown_clusters", schema="learning")
    op.drop_table("dialect_observations", schema="learning")
    for t in (
        "adapter_bridges",
        "machine_source_scopes",
        "conflicts",
        "io_claims",
        "eipcfg_modules",
        "eipcfg_adapters",
        "eipmodule_types",
        "eipadapters",
        "eipmodules",
        "configio_rows",
    ):
        op.drop_table(t, schema="evidence")
    op.drop_table("source_files", schema="corpus")
    op.drop_table("controllers", schema="corpus")
    op.drop_table("projects", schema="corpus")
    op.drop_table("archives", schema="corpus")
    op.drop_table("sync_runs", schema="siteforge_meta")
    op.drop_table("extractor_versions", schema="siteforge_meta")
    op.drop_table("schema_info", schema="siteforge_meta")
    for schema in reversed(SCHEMAS):
        op.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
