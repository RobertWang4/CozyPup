"""default subscription_status to active

Revision ID: a221d46e0058
Revises: 20260420_02_schedules
Create Date: 2026-04-25 12:03:20.784726

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a221d46e0058'
down_revision: Union[str, Sequence[str], None] = '20260420_02_schedules'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Change users.subscription_status default from 'trial' to 'active'."""
    op.alter_column(
        'users',
        'subscription_status',
        server_default=sa.text("'active'"),
        existing_type=sa.String(20),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Revert users.subscription_status default back to 'trial'."""
    op.alter_column(
        'users',
        'subscription_status',
        server_default=sa.text("'trial'"),
        existing_type=sa.String(20),
        existing_nullable=False,
    )
