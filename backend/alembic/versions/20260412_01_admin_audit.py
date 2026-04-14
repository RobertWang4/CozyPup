"""add is_admin and admin_audit_log

Revision ID: 20260412_01_admin_audit
Revises: 327333c23e8d
Create Date: 2026-04-12 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260412_01_admin_audit"
down_revision: Union[str, Sequence[str], None] = "327333c23e8d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "admin_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("admin_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.String(length=128), nullable=True),
        sa.Column("args_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_admin_created", "admin_audit_log", ["admin_user_id", "created_at"])
    op.create_index("ix_audit_target", "admin_audit_log", ["target_type", "target_id"])
    op.create_index("ix_audit_action_created", "admin_audit_log", ["action", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_action_created", table_name="admin_audit_log")
    op.drop_index("ix_audit_target", table_name="admin_audit_log")
    op.drop_index("ix_audit_admin_created", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
    op.drop_column("users", "is_admin")
