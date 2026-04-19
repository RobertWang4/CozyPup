"""add notes to calendar_events

Revision ID: 20260418_notes
Revises: 130c8c7b4100
Create Date: 2026-04-18
"""
from alembic import op
import sqlalchemy as sa


revision = "20260418_notes"
down_revision = "130c8c7b4100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendar_events", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("calendar_events", "notes")
