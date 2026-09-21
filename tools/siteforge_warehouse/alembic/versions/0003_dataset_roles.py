"""Add corpus.archives.dataset_role for LEARNING/VALIDATION/HOLDOUT governance.

Revision ID: 0003_dataset_roles
Revises: 0002_learning_loop_v1
Create Date: 2026-09-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_dataset_roles"
down_revision: Union[str, Sequence[str], None] = "0002_learning_loop_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "archives",
        sa.Column(
            "dataset_role",
            sa.String(length=32),
            nullable=False,
            server_default="UNASSIGNED",
        ),
        schema="corpus",
    )
    op.create_index(
        "ix_archives_dataset_role",
        "archives",
        ["dataset_role"],
        unique=False,
        schema="corpus",
    )


def downgrade() -> None:
    op.drop_index("ix_archives_dataset_role", table_name="archives", schema="corpus")
    op.drop_column("archives", "dataset_role", schema="corpus")
