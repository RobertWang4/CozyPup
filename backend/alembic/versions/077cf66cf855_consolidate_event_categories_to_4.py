"""consolidate event categories to 4

Revision ID: 077cf66cf855
Revises: ff0a42c6530e
Create Date: 2026-03-28 03:46:07.560221

Merge 7 event categories into 4:
  - excretion → abnormal
  - vaccine → medical
  - deworming → medical
  - (diet, daily, medical, abnormal stay as-is)
"""
from typing import Sequence, Union

from alembic import op


revision: str = '077cf66cf855'
down_revision: Union[str, Sequence[str], None] = 'ff0a42c6530e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Migrate existing data to new categories
    op.execute("UPDATE calendar_events SET category = 'abnormal' WHERE category = 'excretion'")
    op.execute("UPDATE calendar_events SET category = 'medical' WHERE category IN ('vaccine', 'deworming')")

    # 2. Alter the enum type: add nothing new (all 4 target values already exist),
    #    just need to remove old values. PostgreSQL doesn't support removing enum values
    #    directly, so we recreate the type.
    op.execute("ALTER TABLE calendar_events ALTER COLUMN category TYPE VARCHAR(20)")
    op.execute("DROP TYPE IF EXISTS eventcategory")
    op.execute("CREATE TYPE eventcategory AS ENUM ('daily', 'diet', 'medical', 'abnormal')")
    op.execute(
        "ALTER TABLE calendar_events ALTER COLUMN category TYPE eventcategory "
        "USING category::eventcategory"
    )


def downgrade() -> None:
    # Recreate old enum with all 7 values
    op.execute("ALTER TABLE calendar_events ALTER COLUMN category TYPE VARCHAR(20)")
    op.execute("DROP TYPE IF EXISTS eventcategory")
    op.execute(
        "CREATE TYPE eventcategory AS ENUM "
        "('diet', 'excretion', 'abnormal', 'vaccine', 'deworming', 'medical', 'daily')"
    )
    op.execute(
        "ALTER TABLE calendar_events ALTER COLUMN category TYPE eventcategory "
        "USING category::eventcategory"
    )
