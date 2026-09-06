"""drop pending_actions

Phase 2b of the LangGraph migration replaced the pending_actions table with
LangGraph `interrupt()` + a Postgres checkpointer, so nothing reads or writes
this table any more.

Revision ID: 20260906_01
Revises: 20260613_01
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260906_01"
down_revision = "20260613_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("pending_actions")


def downgrade() -> None:
    op.create_table(
        "pending_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "session_id", UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=True,
        ),
    )
