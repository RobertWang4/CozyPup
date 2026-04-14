"""add correlation_id to chats

Revision ID: 20260412_02_chats_cid
Revises: 20260412_01_admin_audit
Create Date: 2026-04-12 10:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260412_02_chats_cid"
down_revision: Union[str, Sequence[str], None] = "20260412_01_admin_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("correlation_id", sa.String(length=64), nullable=True))
    op.create_index("ix_chats_correlation_id", "chats", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_chats_correlation_id", table_name="chats")
    op.drop_column("chats", "correlation_id")
