"""add vaccine_schedule and deworming_schedule tables

Structured-data path for vaccine/deworming SCHEDULES (timing + name only).
Dosage is intentionally NOT stored — that is vet-only territory and we
refuse dosage questions at the agent layer.

Revision ID: 20260420_02_schedules
Revises: 20260420_01_chat_audit
Create Date: 2026-04-20 00:00:01.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260420_02_schedules"
down_revision: Union[str, Sequence[str], None] = "20260420_01_chat_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vaccine_schedule",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("species", sa.String(length=10), nullable=False),
        sa.Column("vaccine_name", sa.Text(), nullable=False),
        sa.Column("core", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("age_weeks_start", sa.Integer(), nullable=True),
        sa.Column("age_weeks_end", sa.Integer(), nullable=True),
        sa.Column("interval_description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_vaccine_schedule_species", "vaccine_schedule", ["species"]
    )
    op.create_index(
        "ix_vaccine_schedule_species_name",
        "vaccine_schedule",
        ["species", "vaccine_name"],
    )

    op.create_table(
        "deworming_schedule",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("species", sa.String(length=10), nullable=False),
        sa.Column("parasite_category", sa.String(length=20), nullable=False),
        sa.Column("life_stage", sa.String(length=20), nullable=False),
        sa.Column("interval_description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_deworming_schedule_species", "deworming_schedule", ["species"]
    )
    op.create_index(
        "ix_deworming_schedule_lookup",
        "deworming_schedule",
        ["species", "parasite_category", "life_stage"],
    )


def downgrade() -> None:
    op.drop_index("ix_deworming_schedule_lookup", table_name="deworming_schedule")
    op.drop_index("ix_deworming_schedule_species", table_name="deworming_schedule")
    op.drop_table("deworming_schedule")
    op.drop_index("ix_vaccine_schedule_species_name", table_name="vaccine_schedule")
    op.drop_index("ix_vaccine_schedule_species", table_name="vaccine_schedule")
    op.drop_table("vaccine_schedule")
