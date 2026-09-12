"""add apple_transactions

Binds Apple `originalTransactionId` -> user so a StoreKit JWS cannot be
replayed onto a second account, and so App Store Server Notifications (which
identify a subscription only by originalTransactionId) can find the owner.

Revision ID: 20260912_01
Revises: 20260906_01
Create Date: 2026-09-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260912_01"
down_revision = "20260906_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "apple_transactions",
        sa.Column(
            "original_transaction_id", sa.String(length=64),
            primary_key=True, nullable=False,
        ),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("product_id", sa.String(length=100), nullable=True),
        sa.Column("last_transaction_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "ix_apple_transactions_user_id", "apple_transactions", ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_apple_transactions_user_id", table_name="apple_transactions")
    op.drop_table("apple_transactions")
