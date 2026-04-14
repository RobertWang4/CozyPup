"""add feature_flags and token_revocation

Revision ID: 20260412_04_flags_revoke
Revises: 20260412_03_user_flags
Create Date: 2026-04-13 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260412_04_flags_revoke"
down_revision: Union[str, Sequence[str], None] = "20260412_03_user_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feature_flags",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "token_revocation",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=True),
    )
    op.create_index("ix_token_revocation_revoked_at", "token_revocation", ["revoked_at"])


def downgrade() -> None:
    op.drop_index("ix_token_revocation_revoked_at", table_name="token_revocation")
    op.drop_table("token_revocation")
    op.drop_table("feature_flags")
