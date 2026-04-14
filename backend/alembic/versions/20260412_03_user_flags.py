"""add banned_until and deleted_at to users

Revision ID: 20260412_03_user_flags
Revises: 20260412_02_chats_cid
Create Date: 2026-04-12 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260412_03_user_flags"
down_revision: Union[str, Sequence[str], None] = "20260412_02_chats_cid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("banned_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_banned_until", "users", ["banned_until"])
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_index("ix_users_banned_until", table_name="users")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "banned_until")
