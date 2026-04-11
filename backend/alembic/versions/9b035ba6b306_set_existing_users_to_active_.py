"""set existing users to active subscription

Revision ID: 9b035ba6b306
Revises: 1d1ce2791ff4
Create Date: 2026-04-11 02:51:48.057536

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b035ba6b306'
down_revision: Union[str, Sequence[str], None] = '1d1ce2791ff4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing users get "active" status so they're not affected by subscription system
    # Users created before subscription fields were added have:
    # - subscription_status = 'trial' (from column default)
    # - trial_start_date = NULL (not set during creation)
    # New users will have both fields properly populated.
    op.execute("""
        UPDATE users
        SET subscription_status = 'active'
        WHERE subscription_status = 'trial'
        AND trial_start_date IS NULL
    """)


def downgrade() -> None:
    """Downgrade schema."""
    pass
