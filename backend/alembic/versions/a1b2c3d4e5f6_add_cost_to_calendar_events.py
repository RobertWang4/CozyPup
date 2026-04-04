"""add cost to calendar_events

Revision ID: a1b2c3d4e5f6
Revises: 077cf66cf855
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "077cf66cf855"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendar_events", sa.Column("cost", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("calendar_events", "cost")
