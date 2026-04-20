"""add chat_audit_log table

Revision ID: 20260420_01_chat_audit
Revises: 20260418_notes
Create Date: 2026-04-20 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260420_01_chat_audit"
down_revision: Union[str, Sequence[str], None] = "20260418_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "pet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("species", sa.String(length=20), nullable=True),
        sa.Column("raw_query", sa.Text(), nullable=False),
        sa.Column(
            "is_emergency_route",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("retrieved_chunks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("llm_output", sa.Text(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("model_used", sa.String(length=100), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_chat_audit_created_at", "chat_audit_log", ["created_at"])
    op.create_index("ix_chat_audit_user_id", "chat_audit_log", ["user_id"])
    op.create_index("ix_chat_audit_pet_id", "chat_audit_log", ["pet_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_audit_pet_id", table_name="chat_audit_log")
    op.drop_index("ix_chat_audit_user_id", table_name="chat_audit_log")
    op.drop_index("ix_chat_audit_created_at", table_name="chat_audit_log")
    op.drop_table("chat_audit_log")
