"""initial_schema_postgres

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-08-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. environment_snapshots
    op.create_table(
        "environment_snapshots",
        sa.Column("env_hash", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("library_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("env_hash"),
    )

    # 2. claims
    op.create_table(
        "claims",
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("generated_code", sa.Text(), nullable=False),
        sa.Column("original_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("data_snapshot_hash", sa.Text(), nullable=False),
        sa.Column("env_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="unverified", nullable=False),
        sa.PrimaryKeyConstraint("claim_id"),
    )

    # 3. reexecution_results
    op.create_table(
        "reexecution_results",
        sa.Column("reexecution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("matched", sa.Boolean(), nullable=False),
        sa.Column("diff_summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.claim_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("reexecution_id"),
    )

    # 4. drift_diagnoses
    op.create_table(
        "drift_diagnoses",
        sa.Column("diagnosis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reexecution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["reexecution_id"], ["reexecution_results.reexecution_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("diagnosis_id"),
    )


def downgrade() -> None:
    op.drop_table("drift_diagnoses")
    op.drop_table("reexecution_results")
    op.drop_table("claims")
    op.drop_table("environment_snapshots")
